import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import get_current_user, get_tenant_context, RoleChecker
from app.db.session import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.membership import Role, OrganizationMembership
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskPriority
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse, TaskPageResponse

router = APIRouter()

def validate_project(db: Session, project_id: str, organization_id: uuid.UUID) -> uuid.UUID:
    try:
        p_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")
        
    project_exists = db.execute(
        select(Project.id).where(
            Project.id == p_uuid,
            Project.organization_id == organization_id
        )
    ).scalar_one_or_none()
    
    if not project_exists:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return p_uuid

def validate_assigned_to(db: Session, assigned_to: uuid.UUID, organization_id: uuid.UUID):
    membership = db.execute(
        select(OrganizationMembership.id).where(
            OrganizationMembership.user_id == assigned_to,
            OrganizationMembership.organization_id == organization_id
        )
    ).scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=400, detail="Assigned user is not a member of the organization")

@router.post("", response_model=TaskResponse)
def create_task(
    org_id: str,
    project_id: str,
    task_in: TaskCreate,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(RoleChecker(Role.MEMBER))
):
    p_uuid = validate_project(db, project_id, organization.id)
    
    if task_in.assigned_to:
        validate_assigned_to(db, task_in.assigned_to, organization.id)
        
    task = Task(
        project_id=p_uuid,
        title=task_in.title,
        description=task_in.description,
        status=task_in.status,
        priority=task_in.priority,
        due_date=task_in.due_date,
        assigned_to=task_in.assigned_to,
        created_by=current_user.id
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

@router.get("", response_model=TaskPageResponse)
def list_tasks(
    org_id: str,
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    assigned_to: Optional[uuid.UUID] = None,
    due_date_before: Optional[datetime] = None,
    sort_by: Optional[str] = Query(None, regex="^(created_at|due_date|priority)$"),
    sort_desc: bool = True,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.VIEWER))
):
    p_uuid = validate_project(db, project_id, organization.id)
    
    stmt = select(Task).where(Task.project_id == p_uuid)
    
    if status:
        stmt = stmt.where(Task.status == status)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if assigned_to:
        stmt = stmt.where(Task.assigned_to == assigned_to)
    if due_date_before:
        stmt = stmt.where(Task.due_date <= due_date_before)
        
    # Count total
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(total_stmt).scalar() or 0
    
    # Sorting
    if sort_by:
        col = getattr(Task, sort_by)
        stmt = stmt.order_by(col.desc() if sort_desc else col.asc())
    else:
        stmt = stmt.order_by(Task.created_at.desc())
        
    # Paginate
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    tasks = db.execute(stmt).scalars().all()
    
    return TaskPageResponse(
        items=list(tasks),
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    org_id: str,
    project_id: str,
    task_id: str,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.VIEWER))
):
    p_uuid = validate_project(db, project_id, organization.id)
    
    try:
        t_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")
        
    task = db.execute(
        select(Task).where(
            Task.id == t_uuid,
            Task.project_id == p_uuid
        )
    ).scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return task

@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    org_id: str,
    project_id: str,
    task_id: str,
    task_in: TaskUpdate,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.MEMBER))
):
    p_uuid = validate_project(db, project_id, organization.id)
    
    try:
        t_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.execute(
        select(Task).where(
            Task.id == t_uuid,
            Task.project_id == p_uuid
        )
    ).scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.version != task_in.version:
        raise HTTPException(status_code=409, detail="Task version conflict")

    if task_in.assigned_to is not None:
        validate_assigned_to(db, task_in.assigned_to, organization.id)
        task.assigned_to = task_in.assigned_to
        
    if task_in.title is not None:
        task.title = task_in.title
    if task_in.description is not None:
        task.description = task_in.description
    if task_in.status is not None:
        task.status = task_in.status
    if task_in.priority is not None:
        task.priority = task_in.priority
    if task_in.due_date is not None:
        task.due_date = task_in.due_date
        
    try:
        db.commit()
        db.refresh(task)
    except StaleDataError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task was updated concurrently")

    return task

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    org_id: str,
    project_id: str,
    task_id: str,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.ADMIN))
):
    p_uuid = validate_project(db, project_id, organization.id)
    
    try:
        t_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.execute(
        select(Task).where(
            Task.id == t_uuid,
            Task.project_id == p_uuid
        )
    ).scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    db.delete(task)
    db.commit()
