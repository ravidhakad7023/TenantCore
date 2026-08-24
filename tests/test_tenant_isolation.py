import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def run_around_tests():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def create_user_and_login(email: str, password: str = "password123"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return response.json()["access_token"]

def test_tenant_isolation_strict_boundaries():
    token_a = create_user_and_login("user_a@example.com")
    token_b = create_user_and_login("user_b@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates Org A
    org_a_resp = client.post("/api/v1/organizations", json={"name": "Org A"}, headers=headers_a)
    org_a_id = org_a_resp.json()["id"]

    # User B creates Org B
    org_b_resp = client.post("/api/v1/organizations", json={"name": "Org B"}, headers=headers_b)
    org_b_id = org_b_resp.json()["id"]

    # User A creates Project A in Org A
    proj_a_resp = client.post(f"/api/v1/organizations/{org_a_id}/projects", json={"name": "Proj A"}, headers=headers_a)
    proj_a_id = proj_a_resp.json()["id"]

    # User B creates Project B in Org B
    proj_b_resp = client.post(f"/api/v1/organizations/{org_b_id}/projects", json={"name": "Proj B"}, headers=headers_b)
    proj_b_id = proj_b_resp.json()["id"]

    # User A creates Task A in Project A
    task_a_resp = client.post(f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}/tasks", json={"title": "Task A"}, headers=headers_a)
    task_a_id = task_a_resp.json()["id"]

    # 1. User A tries to access Org B -> 403
    resp = client.get(f"/api/v1/organizations/{org_b_id}", headers=headers_a)
    assert resp.status_code == 403

    # 2. User A tries to read Project B via Org B -> 403
    resp = client.get(f"/api/v1/organizations/{org_b_id}/projects/{proj_b_id}", headers=headers_a)
    assert resp.status_code == 403

    # 3. User A tries to read Project B by spoofing Org A -> 404
    resp = client.get(f"/api/v1/organizations/{org_a_id}/projects/{proj_b_id}", headers=headers_a)
    assert resp.status_code == 404

    # 4. User A tries to modify Project B by spoofing Org A -> 404
    resp = client.patch(f"/api/v1/organizations/{org_a_id}/projects/{proj_b_id}", json={"name": "Hacked"}, headers=headers_a)
    assert resp.status_code == 404

    # 5. User A tries to delete Project B by spoofing Org A -> 404
    resp = client.delete(f"/api/v1/organizations/{org_a_id}/projects/{proj_b_id}", headers=headers_a)
    assert resp.status_code == 404

    # 6. User A tries to access Task in Org B via spoofing -> 404
    resp = client.get(f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}/tasks/{task_a_id}", headers=headers_b)
    assert resp.status_code == 403

    # 7. User A tries to assign task to User B (not in Org A)
    user_b_id = client.get("/api/v1/auth/me", headers=headers_b).json()["id"]
    resp = client.patch(
        f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}/tasks/{task_a_id}", 
        json={"assigned_to": user_b_id, "version": 1}, 
        headers=headers_a
    )
    assert resp.status_code == 400
    assert "not a member" in resp.json()["detail"].lower()
