import uuid
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db, get_current_user, get_tenant_context, RoleChecker
from app.models.user import User
from app.models.organization import Organization
from app.models.membership import Role
from app.models.report import OrganizationReport, ReportStatus
from app.tasks.reports import generate_organization_report_task

router = APIRouter()

class ReportResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    status: ReportStatus
    created_by: Optional[uuid.UUID]
    summary_data: Optional[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

@router.post("", response_model=ReportResponse, dependencies=[Depends(RoleChecker(Role.MEMBER))])
def create_organization_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_context: Organization = Depends(get_tenant_context),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Enqueue a background job to generate an organization report.
    """
    report = OrganizationReport(
        organization_id=tenant_context.id,
        created_by=current_user.id,
        status=ReportStatus.PENDING,
        idempotency_key=idempotency_key
    )
    db.add(report)
    
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key is None:
            raise HTTPException(status_code=500, detail="Database integrity error")
            
        # If it failed and we have an idempotency key, it means a concurrent/previous 
        # request created the report. We just return the existing report.
        existing_report = db.execute(
            select(OrganizationReport).where(
                OrganizationReport.organization_id == tenant_context.id,
                OrganizationReport.created_by == current_user.id,
                OrganizationReport.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        
        if existing_report:
            return existing_report
        else:
            raise HTTPException(status_code=500, detail="Failed to fetch existing report after integrity error")
            
    db.refresh(report)

    # Enqueue the Celery task (ONLY AFTER commit is successful)
    generate_organization_report_task.delay(str(report.id), str(tenant_context.id))

    return report

@router.get("/{report_id}", response_model=ReportResponse, dependencies=[Depends(RoleChecker(Role.VIEWER))])
def get_organization_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_context: Organization = Depends(get_tenant_context)
):
    """
    Get the status and result of a generated organization report.
    """
    report = db.execute(
        select(OrganizationReport).where(OrganizationReport.id == report_id)
    ).scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    # Tenant isolation validation
    if report.organization_id != tenant_context.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return report
