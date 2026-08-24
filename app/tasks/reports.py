import logging
import uuid
from sqlalchemy.exc import OperationalError
from sqlalchemy import select
from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.models.report import OrganizationReport, ReportStatus
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, autoretry_for=(OperationalError,), retry_kwargs={'max_retries': 3, 'countdown': 5})
def generate_organization_report_task(self, report_id: str, org_id: str):
    db = SessionLocal()
    try:
        r_id = uuid.UUID(report_id)
        o_id = uuid.UUID(org_id)

        # Fetch the report
        report = db.execute(
            select(OrganizationReport).where(OrganizationReport.id == r_id)
        ).scalar_one_or_none()

        if not report:
            logger.error(f"Report {report_id} not found.")
            return

        # Tenant isolation validation
        if report.organization_id != o_id:
            logger.error(f"Tenant isolation error: Report {report_id} does not belong to organization {org_id}.")
            return

        # Idempotency check
        if report.status in (ReportStatus.COMPLETED, ReportStatus.FAILED):
            logger.info(f"Report {report_id} is already {report.status.value}. Skipping execution.")
            return

        try:
            # Query projects belonging ONLY to org_id
            projects = db.execute(
                select(Project).where(Project.organization_id == o_id)
            ).scalars().all()
            
            project_ids = [p.id for p in projects]

            # Query tasks belonging ONLY to these projects
            if project_ids:
                tasks = db.execute(
                    select(Task).where(Task.project_id.in_(project_ids))
                ).scalars().all()
            else:
                tasks = []

            # Generate summary
            total_projects = len(projects)
            total_tasks = len(tasks)
            
            completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.DONE)
            in_progress_tasks = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
            pending_tasks = sum(1 for t in tasks if t.status == TaskStatus.TODO)
            
            high_priority = sum(1 for t in tasks if t.priority == TaskPriority.HIGH)
            medium_priority = sum(1 for t in tasks if t.priority == TaskPriority.MEDIUM)
            low_priority = sum(1 for t in tasks if t.priority == TaskPriority.LOW)
            
            summary_data = {
                "organization_id": str(o_id),
                "total_projects": total_projects,
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "in_progress_tasks": in_progress_tasks,
                "pending_tasks": pending_tasks,
                "tasks_by_priority": {
                    "HIGH": high_priority,
                    "MEDIUM": medium_priority,
                    "LOW": low_priority
                }
            }

            # Update report
            report.summary_data = summary_data
            report.status = ReportStatus.COMPLETED
            db.commit()
            logger.info(f"Report {report_id} generated successfully.")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error generating report {report_id}: {str(e)}")
            report.status = ReportStatus.FAILED
            db.commit()
            raise e
            
    finally:
        db.close()
