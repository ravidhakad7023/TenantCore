from typing import Generator
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.token import TokenPayload
from sqlalchemy import select
from sqlalchemy.orm import joinedload

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    import uuid
    try:
        user_id = uuid.UUID(token_data.sub)
    except ValueError:
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

def get_tenant_membership(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.membership import OrganizationMembership
    import uuid

    try:
        organization_id = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format")

    membership = db.execute(
        select(OrganizationMembership).options(joinedload(OrganizationMembership.organization)).where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.organization_id == organization_id
        )
    ).scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this organization")

    return membership

def get_tenant_context(
    membership = Depends(get_tenant_membership),
    db: Session = Depends(get_db),
):
    if not membership.organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    return membership.organization

class RoleChecker:
    def __init__(self, required_role: str):
        self.required_role = required_role

    def __call__(self, membership = Depends(get_tenant_membership)):
        from app.models.membership import Role
        hierarchy = {
            Role.VIEWER: 1,
            Role.MEMBER: 2,
            Role.ADMIN: 3,
            Role.OWNER: 4
        }
        
        user_role_level = hierarchy.get(membership.role, 0)
        required_role_level = hierarchy.get(self.required_role, 5)

        if user_role_level < required_role_level:
            raise HTTPException(status_code=403, detail="Insufficient role permissions")
        
        return membership

