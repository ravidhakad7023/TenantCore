import pytest
from fastapi.testclient import TestClient
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.api.deps import get_db

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

def test_create_and_get_report():
    email = f"report_api_{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org_resp = client.post("/api/v1/organizations", json={"name": "Report API Org"}, headers=headers)
    org_id = org_resp.json()["id"]

    # Mock the delay call to avoid requiring running Celery
    with patch("app.api.v1.reports.generate_organization_report_task.delay") as mock_delay:
        post_resp = client.post(f"/api/v1/organizations/{org_id}/reports", headers=headers)
        
        assert post_resp.status_code == 200
        report_data = post_resp.json()
        assert report_data["status"] == "PENDING"
        assert report_data["organization_id"] == org_id
        
        mock_delay.assert_called_once_with(report_data["id"], org_id)

        # Test GET report
        get_resp = client.get(f"/api/v1/organizations/{org_id}/reports/{report_data['id']}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == report_data["id"]

def test_report_cross_tenant_isolation():
    email_a = f"usera_{uuid.uuid4()}@example.com"
    email_b = f"userb_{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email_a, "password": "password123"})
    client.post("/api/v1/auth/register", json={"email": email_b, "password": "password123"})
    
    token_a = client.post("/api/v1/auth/login", json={"email": email_a, "password": "password123"}).json()["access_token"]
    token_b = client.post("/api/v1/auth/login", json={"email": email_b, "password": "password123"}).json()["access_token"]
    
    org_a = client.post("/api/v1/organizations", json={"name": "Org A"}, headers={"Authorization": f"Bearer {token_a}"}).json()["id"]
    org_b = client.post("/api/v1/organizations", json={"name": "Org B"}, headers={"Authorization": f"Bearer {token_b}"}).json()["id"]

    with patch("app.api.v1.reports.generate_organization_report_task.delay"):
        post_resp = client.post(f"/api/v1/organizations/{org_a}/reports", headers={"Authorization": f"Bearer {token_a}"})
        report_a_id = post_resp.json()["id"]

    # User B tries to access Report A through Org B path
    get_resp = client.get(f"/api/v1/organizations/{org_b}/reports/{report_a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert get_resp.status_code == 403 # Access Denied / cross tenant isolation
