from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_current_user, get_tenant_context, RoleChecker, get_tenant_membership
from app.db.session import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.membership import OrganizationMembership, Role
from app.schemas.organization import OrganizationCreate, OrganizationResponse, OrganizationUpdate, RoleUpdate, MembershipResponse

router = APIRouter()

@router.post("", response_model=OrganizationResponse)
def create_organization(
    org_in: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # Create Organization
        organization = Organization(name=org_in.name)
        db.add(organization)
        db.flush()

        # Create Membership with OWNER role
        membership = OrganizationMembership(
            user_id=current_user.id,
            organization_id=organization.id,
            role=Role.OWNER
        )
        db.add(membership)
        db.commit()
        db.refresh(organization)
        return organization
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.get("", response_model=List[OrganizationResponse])
def get_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Organization)
        .join(OrganizationMembership, Organization.id == OrganizationMembership.organization_id)
        .where(OrganizationMembership.user_id == current_user.id)
        .order_by(Organization.created_at.asc())
    )
    organizations = db.execute(stmt).scalars().all()
    return list(organizations)

@router.get("/{org_id}", response_model=OrganizationResponse)
def get_organization(
    organization: Organization = Depends(get_tenant_context),
):
    return organization

@router.patch("/{org_id}", response_model=OrganizationResponse)
def update_organization(
    org_in: OrganizationUpdate,
    org_id: str,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.ADMIN))
):
    if org_in.name is not None:
        organization.name = org_in.name
    
    db.commit()
    db.refresh(organization)
    return organization

@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    org_id: str,
    organization: Organization = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.OWNER))
):
    db.delete(organization)
    db.commit()

@router.get("/{org_id}/members", response_model=List[MembershipResponse])
def get_members(
    org_id: str,
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.VIEWER))
):
    import uuid
    try:
        organization_id = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format")

    stmt = select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id)
    memberships = db.execute(stmt).scalars().all()
    return list(memberships)

@router.patch("/{org_id}/members/{user_id}/role", response_model=MembershipResponse)
def update_member_role(
    org_id: str,
    user_id: str,
    role_in: RoleUpdate,
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(Role.OWNER))
):
    import uuid
    try:
        org_uuid = uuid.UUID(org_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    # Fetch target membership
    target_membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_uuid,
            OrganizationMembership.organization_id == org_uuid
        )
    ).scalar_one_or_none()

    if not target_membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    # Owner safety check
    if target_membership.role == Role.OWNER and role_in.role != Role.OWNER:
        owner_count = db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org_uuid,
                OrganizationMembership.role == Role.OWNER
            ).with_for_update()
        ).scalars().all()
        
        if len(owner_count) <= 1:
            db.rollback()
            raise HTTPException(status_code=400, detail="Cannot demote the last owner of the organization")

    target_membership.role = role_in.role
    db.commit()
    db.refresh(target_membership)
    return target_membership

