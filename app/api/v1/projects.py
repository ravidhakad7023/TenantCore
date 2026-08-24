import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.api.deps import get_current_user, get_tenant_context, RoleChecker
from app.db.session import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.membership import Role
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectPageResponse
from app.core.redis import get_cache, set_cache, delete_cache
from app.api.rate_limit import RateLimiter

router = APIRouter()

@router.post("", response_model=ProjectResponse)
def create_project(
    org_id: str,
    project_in: ProjectCreate,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(RoleChecker(Role.MEMBER))
):
    project = Project(
        organization_id=organization.id,
        name=project_in.name,
        description=project_in.description,
        created_by=current_user.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@router.get("", response_model=ProjectPageResponse)
def list_projects(
    org_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.VIEWER)),
    __=Depends(RateLimiter())
):
    stmt = select(Project).where(Project.organization_id == organization.id)
    
    if search:
        stmt = stmt.where(Project.name.ilike(f"%{search}%"))
        
    # Count total
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(total_stmt).scalar() or 0
    
    # Paginate
    stmt = stmt.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    projects = db.execute(stmt).scalars().all()
    
    return ProjectPageResponse(
        items=list(projects),
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    org_id: str,
    project_id: str,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.VIEWER))
):
    try:
        p_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")
        
    cache_key = f"tenant:{organization.id}:project:{project_id}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return ProjectResponse(**cached_data)

    project = db.execute(
        select(Project).where(
            Project.id == p_uuid,
            Project.organization_id == organization.id
        )
    ).scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project_resp = ProjectResponse.model_validate(project)
    set_cache(cache_key, project_resp.model_dump(mode="json"), ttl=300)
    
    return project

@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    org_id: str,
    project_id: str,
    project_in: ProjectUpdate,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.MEMBER))
):
    try:
        p_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    project = db.execute(
        select(Project).where(
            Project.id == p_uuid,
            Project.organization_id == organization.id
        )
    ).scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description
        
    db.commit()
    db.refresh(project)
    
    cache_key = f"tenant:{organization.id}:project:{project_id}"
    delete_cache(cache_key)
    
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    org_id: str,
    project_id: str,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.ADMIN))
):
    try:
        p_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    project = db.execute(
        select(Project).where(
            Project.id == p_uuid,
            Project.organization_id == organization.id
        )
    ).scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db.delete(project)
    db.commit()
    
    cache_key = f"tenant:{organization.id}:project:{project_id}"
    delete_cache(cache_key)
