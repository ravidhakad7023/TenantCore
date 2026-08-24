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
    try:
        db = TestingSessionLocal()
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

def create_user_and_login(email: str = "test@example.com", password: str = "password123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]

def create_org(token: str, name: str = "Org A"):
    return client.post("/api/v1/organizations", json={"name": name}, headers={"Authorization": f"Bearer {token}"}).json()

def test_create_and_assign_task():
    token = create_user_and_login("a@example.com")
    org = create_org(token, "Org A")
    
    # Get user id for assignment
    user_info = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    user_id = user_info["id"]

    proj = client.post(
        f"/api/v1/organizations/{org['id']}/projects",
        json={"name": "Project X"},
        headers={"Authorization": f"Bearer {token}"}
    ).json()

    task_resp = client.post(
        f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks",
        json={"title": "Task 1", "assigned_to": user_id},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert task_resp.status_code == 200
    assert task_resp.json()["assigned_to"] == user_id

def test_cross_tenant_assignment_blocked():
    token_a = create_user_and_login("a@example.com")
    token_b = create_user_and_login("b@example.com")

    user_b = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"}).json()["id"]

    org_a = create_org(token_a, "Org A")
    proj = client.post(
        f"/api/v1/organizations/{org_a['id']}/projects",
        json={"name": "Project X"},
        headers={"Authorization": f"Bearer {token_a}"}
    ).json()

    # User A tries to assign Task in Org A to User B (who is not in Org A)
    task_resp = client.post(
        f"/api/v1/organizations/{org_a['id']}/projects/{proj['id']}/tasks",
        json={"title": "Task 1", "assigned_to": user_b},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert task_resp.status_code == 400
    assert "not a member" in task_resp.json()["detail"]

def test_task_filtering_and_sorting():
    token = create_user_and_login()
    org = create_org(token)
    proj = client.post(f"/api/v1/organizations/{org['id']}/projects", json={"name": "Proj"}, headers={"Authorization": f"Bearer {token}"}).json()

    client.post(
        f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks",
        json={"title": "T1", "status": "TODO", "priority": "HIGH"},
        headers={"Authorization": f"Bearer {token}"}
    )
    client.post(
        f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks",
        json={"title": "T2", "status": "DONE", "priority": "LOW"},
        headers={"Authorization": f"Bearer {token}"}
    )

    # Filter by Status
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks?status=DONE", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["title"] == "T2"

    # Sort by Priority Desc
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks?sort_by=priority&sort_desc=true", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # LOW comes after HIGH lexicographically? Wait, Enums sorting in sqlite sorts by string value (HIGH vs LOW). 'LOW' > 'HIGH'. So Descending: LOW, then HIGH.
    items = resp.json()["items"]
    assert items[0]["priority"] == "LOW"
    assert items[1]["priority"] == "HIGH"

def test_task_filters_and_invalid_task_id():
    token = create_user_and_login("taskfilter@example.com")
    org = create_org(token)
    user_id = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"]

    proj = client.post(f"/api/v1/organizations/{org['id']}/projects", json={"name": "Proj"}, headers={"Authorization": f"Bearer {token}"}).json()

    client.post(
        f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks",
        json={"title": "T1", "status": "TODO", "priority": "HIGH", "assigned_to": user_id, "due_date": "2030-01-01T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"}
    )

    # test filtering by assigned_to
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks?assigned_to={user_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # test filtering by due_date_before
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks?due_date_before=2031-01-01T00:00:00Z", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # test invalid task ID
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks/invalid-uuid", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
    assert "Invalid task ID" in resp.json()["detail"]

    # test task not found
    import uuid
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404

    # test update invalid task ID
    resp = client.patch(
        f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks/invalid-uuid",
        json={"title": "test", "version": 1},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 400

    # test update task not found
    resp = client.patch(
        f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks/{uuid.uuid4()}",
        json={"title": "test", "version": 1},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404

    # test delete invalid task ID
    resp = client.delete(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks/invalid-uuid", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400

    # test delete task not found
    resp = client.delete(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}/tasks/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
