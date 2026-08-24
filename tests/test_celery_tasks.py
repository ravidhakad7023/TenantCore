import pytest
import uuid
from app.tasks.reports import generate_organization_report_task
from app.models.report import OrganizationReport, ReportStatus
from sqlalchemy import select
from unittest.mock import patch
from app.db.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def run_around_tests():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with patch("app.tasks.reports.SessionLocal", new=TestingSessionLocal):
        yield
    Base.metadata.drop_all(bind=engine)

def test_celery_task_success():
    from fastapi.testclient import TestClient
    from app.main import app
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # 1. Setup user, org, project, task
    email = f"task_user_{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org_resp = client.post("/api/v1/organizations", json={"name": "Report Org"}, headers=headers)
    org_id = org_resp.json()["id"]

    # Project
    proj_resp = client.post(f"/api/v1/organizations/{org_id}/projects", json={"name": "Report Project"}, headers=headers)
    proj_id = proj_resp.json()["id"]

    # Task
    client.post(f"/api/v1/organizations/{org_id}/projects/{proj_id}/tasks", json={"title": "Report Task"}, headers=headers)

    # 2. Create a PENDING report directly via DB
    db = TestingSessionLocal()
    report = OrganizationReport(organization_id=uuid.UUID(org_id), created_by=None, status=ReportStatus.PENDING)
    db.add(report)
    db.commit()
    report_id = str(report.id)
    db.close()

    # 3. Execute the Celery task synchronously
    generate_organization_report_task(report_id, org_id)

    # 4. Verify results
    db = TestingSessionLocal()
    report_after = db.execute(select(OrganizationReport).where(OrganizationReport.id == uuid.UUID(report_id))).scalar_one()
    assert report_after.status == ReportStatus.COMPLETED
    assert report_after.summary_data is not None
    assert report_after.summary_data["total_projects"] == 1
    assert report_after.summary_data["total_tasks"] == 1
    db.close()

def test_celery_task_tenant_isolation():
    # If report_id belongs to Org A, but org_id passed is Org B, it should not process.
    from app.models.organization import Organization
    db = TestingSessionLocal()
    org_a = Organization(name="Org A")
    org_b = Organization(name="Org B")
    db.add_all([org_a, org_b])
    db.commit()
    db.refresh(org_a)
    db.refresh(org_b)
    
    report = OrganizationReport(organization_id=org_a.id, created_by=None, status=ReportStatus.PENDING)
    db.add(report)
    db.commit()
    report_id = str(report.id)
    org_b_id = str(org_b.id)
    db.close()

    # Execution with wrong org_id
    generate_organization_report_task(report_id, org_b_id)

    db = TestingSessionLocal()
    report_after = db.execute(select(OrganizationReport).where(OrganizationReport.id == uuid.UUID(report_id))).scalar_one()
    assert report_after.status == ReportStatus.PENDING # Remains unchanged
    db.close()

def test_celery_task_idempotency():
    from app.models.organization import Organization
    db = TestingSessionLocal()
    org = Organization(name="Idempotent Org")
    db.add(org)
    db.commit()
    db.refresh(org)

    report = OrganizationReport(organization_id=org.id, created_by=None, status=ReportStatus.COMPLETED, summary_data={"test": 1})
    db.add(report)
    db.commit()
    report_id = str(report.id)
    org_id = str(org.id)
    db.close()

    # Execution should not raise exception and should exit gracefully
    generate_organization_report_task(report_id, org_id)

    db = TestingSessionLocal()
    report_after = db.execute(select(OrganizationReport).where(OrganizationReport.id == uuid.UUID(report_id))).scalar_one()
    assert report_after.status == ReportStatus.COMPLETED
    assert report_after.summary_data == {"test": 1}
    db.close()

def test_celery_task_report_not_found():
    # Provide valid UUID for a report that doesn't exist
    from app.models.organization import Organization
    db = TestingSessionLocal()
    org = Organization(name="Org")
    db.add(org)
    db.commit()
    org_id = str(org.id)
    db.close()

    report_id = str(uuid.uuid4())
    # Should not crash, just return
    generate_organization_report_task(report_id, org_id)

def test_celery_task_processing_error():
    # Simulate DB failure during processing
    from app.models.organization import Organization
    db = TestingSessionLocal()
    org = Organization(name="Error Org")
    db.add(org)
    db.commit()
    db.refresh(org)

    report = OrganizationReport(organization_id=org.id, created_by=None, status=ReportStatus.PENDING)
    db.add(report)
    db.commit()
    report_id = str(report.id)
    org_id = str(org.id)
    db.close()

    real_session = TestingSessionLocal()
    
    original_execute = real_session.execute
    def fake_execute(*args, **kwargs):
        if "project" in str(args[0]).lower():
            raise Exception("Simulated processing error")
        return original_execute(*args, **kwargs)

    with patch("app.tasks.reports.SessionLocal", return_value=real_session):
        with patch.object(real_session, "execute", side_effect=fake_execute):
            with pytest.raises(Exception, match="Simulated processing error"):
                generate_organization_report_task(report_id, org_id)

    db = TestingSessionLocal()
    report_after = db.execute(select(OrganizationReport).where(OrganizationReport.id == uuid.UUID(report_id))).scalar_one()
    assert report_after.status == ReportStatus.FAILED
    assert report_after.summary_data is None # no data generated
    db.close()


