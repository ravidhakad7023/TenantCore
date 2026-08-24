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

def test_create_project():
    token = create_user_and_login()
    org = create_org(token)
    org_id = org["id"]

    resp = client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"name": "Project X"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Project X"

def test_list_and_paginate_projects():
    token = create_user_and_login()
    org = create_org(token)
    org_id = org["id"]

    client.post(f"/api/v1/organizations/{org_id}/projects", json={"name": "P1"}, headers={"Authorization": f"Bearer {token}"})
    client.post(f"/api/v1/organizations/{org_id}/projects", json={"name": "P2"}, headers={"Authorization": f"Bearer {token}"})

    resp = client.get(f"/api/v1/organizations/{org_id}/projects?page=1&page_size=1", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 1

def test_project_cross_tenant_isolation():
    token_a = create_user_and_login("a@example.com")
    token_b = create_user_and_login("b@example.com")

    org_a = create_org(token_a, "Org A")
    org_b = create_org(token_b, "Org B")

    # A creates project in Org A
    proj_a_resp = client.post(
        f"/api/v1/organizations/{org_a['id']}/projects",
        json={"name": "Proj A"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    proj_a_id = proj_a_resp.json()["id"]

    # B tries to get project A via Org A
    resp1 = client.get(
        f"/api/v1/organizations/{org_a['id']}/projects/{proj_a_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp1.status_code == 403 # B not in Org A

    # A tries to access project A via Org B path
    resp2 = client.get(
        f"/api/v1/organizations/{org_b['id']}/projects/{proj_a_id}",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp2.status_code == 403 # A not in Org B

    # What if B is somehow in Org A (VIEWER), but they try to get a project from Org B via Org A's path?
    # B gets project A in Org B path -> 404 because project A is not in Org B.
    # We can test this by adding B to Org A.
    from app.models.membership import OrganizationMembership, Role
    from app.models.user import User
    from sqlalchemy import select
    import uuid
    db = next(override_get_db())
    u_b = db.execute(select(User).where(User.email=="b@example.com")).scalar_one()
    db.add(OrganizationMembership(user_id=u_b.id, organization_id=uuid.UUID(org_a['id']), role=Role.VIEWER))
    db.commit()

    resp3 = client.get(
        f"/api/v1/organizations/{org_a['id']}/projects/{proj_a_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp3.status_code == 200 # Now B can access since they are in Org A.

def test_project_invalid_ids_and_not_found():
    token = create_user_and_login("projerr@example.com")
    org = create_org(token, "Org Err")

    # Invalid project ID
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/invalid-uuid", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
    assert "Invalid project ID" in resp.json()["detail"]

    resp = client.patch(f"/api/v1/organizations/{org['id']}/projects/invalid-uuid", json={"name": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400

    resp = client.delete(f"/api/v1/organizations/{org['id']}/projects/invalid-uuid", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400

    # Project not found
    import uuid
    not_found_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/organizations/{org['id']}/projects/{not_found_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404

    resp = client.patch(f"/api/v1/organizations/{org['id']}/projects/{not_found_id}", json={"name": "test"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404

    resp = client.delete(f"/api/v1/organizations/{org['id']}/projects/{not_found_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404

def test_project_rbac():
    token_owner = create_user_and_login("owner@example.com")
    org = create_org(token_owner, "Org RBAC")
    proj = client.post(f"/api/v1/organizations/{org['id']}/projects", json={"name": "P1"}, headers={"Authorization": f"Bearer {token_owner}"}).json()

    # Create Viewer
    token_viewer = create_user_and_login("viewer@example.com")
    
    from app.models.membership import OrganizationMembership, Role
    from app.models.user import User
    from sqlalchemy import select
    import uuid
    db = next(override_get_db())
    u_viewer = db.execute(select(User).where(User.email=="viewer@example.com")).scalar_one()
    db.add(OrganizationMembership(user_id=u_viewer.id, organization_id=uuid.UUID(org['id']), role=Role.VIEWER))
    db.commit()

    # Viewer tries to edit project
    resp = client.patch(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}", json={"name": "test"}, headers={"Authorization": f"Bearer {token_viewer}"})
    assert resp.status_code == 403

    # Viewer tries to delete project
    resp = client.delete(f"/api/v1/organizations/{org['id']}/projects/{proj['id']}", headers={"Authorization": f"Bearer {token_viewer}"})
    assert resp.status_code == 403
