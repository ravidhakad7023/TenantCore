import pytest
import uuid
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

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

def create_user_and_login(email: str = "test@example.com", password: str = "password123"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return response.json()["access_token"]

@pytest.fixture
def auth_headers_reliability():
    token = create_user_and_login("rel_user@example.com", "password123")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_transaction_rollback_on_failure(auth_headers_reliability, db_session):
    # We patch the database session's commit to simulate a failure during organization creation
    with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("Simulated DB failure")):
        response = client.post(
            "/api/v1/organizations",
            headers=auth_headers_reliability,
            json={"name": "Failed Org"}
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "Internal server error"

    # Verify that the transaction rolled back: the org should not exist
    orgs = db_session.execute(text("SELECT id FROM organizations WHERE name = 'Failed Org'")).fetchall()
    assert len(orgs) == 0

def test_concurrent_task_update_conflict(auth_headers_reliability, db_session):
    # Setup: create org, project, task
    org_resp = client.post("/api/v1/organizations", headers=auth_headers_reliability, json={"name": "OCC Org"})
    org_id = org_resp.json()["id"]

    proj_resp = client.post(f"/api/v1/organizations/{org_id}/projects", headers=auth_headers_reliability, json={"name": "OCC Proj"})
    proj_id = proj_resp.json()["id"]

    task_resp = client.post(f"/api/v1/organizations/{org_id}/projects/{proj_id}/tasks", headers=auth_headers_reliability, json={
        "title": "OCC Task"
    })
    task_id = task_resp.json()["id"]
    version1 = task_resp.json()["version"]
    assert version1 == 1

    # First update succeeds
    upd1 = client.patch(f"/api/v1/organizations/{org_id}/projects/{proj_id}/tasks/{task_id}", headers=auth_headers_reliability, json={
        "title": "OCC Task v2",
        "version": version1
    })
    assert upd1.status_code == 200
    version2 = upd1.json()["version"]
    assert version2 == 2
    assert upd1.json()["title"] == "OCC Task v2"

    # Second update with STALE version receives 409
    upd2 = client.patch(f"/api/v1/organizations/{org_id}/projects/{proj_id}/tasks/{task_id}", headers=auth_headers_reliability, json={
        "title": "OCC Task Stale",
        "version": version1
    })
    assert upd2.status_code == status.HTTP_409_CONFLICT

    # Verify newer data remains intact
    get_task = client.get(f"/api/v1/organizations/{org_id}/projects/{proj_id}/tasks/{task_id}", headers=auth_headers_reliability)
    assert get_task.json()["title"] == "OCC Task v2"
    assert get_task.json()["version"] == 2

def test_atomic_owner_demotion(auth_headers_reliability, db_session):
    org_resp = client.post("/api/v1/organizations", headers=auth_headers_reliability, json={"name": "Demotion Org"})
    org_id = org_resp.json()["id"]

    user_id = db_session.execute(text("SELECT id FROM users WHERE email = 'rel_user@example.com'")).scalar()
    
    demote_resp = client.patch(f"/api/v1/organizations/{org_id}/members/{user_id}/role", headers=auth_headers_reliability, json={
        "role": "MEMBER"
    })
    assert demote_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "last owner" in demote_resp.json()["detail"]

@patch("app.api.v1.reports.generate_organization_report_task.delay")
def test_idempotency_report_creation(mock_delay, auth_headers_reliability, db_session):
    org_resp = client.post("/api/v1/organizations", headers=auth_headers_reliability, json={"name": "Idempotency Org"})
    org_id = org_resp.json()["id"]

    idem_key = f"req-{uuid.uuid4()}"

    # First request
    resp1 = client.post(f"/api/v1/organizations/{org_id}/reports", headers={
        **auth_headers_reliability,
        "Idempotency-Key": idem_key
    })
    assert resp1.status_code == 200
    report_id_1 = resp1.json()["id"]
    mock_delay.assert_called_once()
    mock_delay.reset_mock()

    # Second request with the same idempotency key
    resp2 = client.post(f"/api/v1/organizations/{org_id}/reports", headers={
        **auth_headers_reliability,
        "Idempotency-Key": idem_key
    })
    assert resp2.status_code == 200
    report_id_2 = resp2.json()["id"]
    
    # Assert we got the same report back
    assert report_id_1 == report_id_2
    
    # Assert no second Celery task was enqueued
    mock_delay.assert_not_called()

    # Test that different orgs can use the same idempotency key
    org_resp2 = client.post("/api/v1/organizations", headers=auth_headers_reliability, json={"name": "Idempotency Org 2"})
    org_id2 = org_resp2.json()["id"]
    resp3 = client.post(f"/api/v1/organizations/{org_id2}/reports", headers={
        **auth_headers_reliability,
        "Idempotency-Key": idem_key
    })
    assert resp3.status_code == 200
    assert resp3.json()["id"] != report_id_1
    mock_delay.assert_called_once()
