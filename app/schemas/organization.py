from pydantic import BaseModel
import uuid
from datetime import datetime

from app.models.membership import Role

class OrganizationBase(BaseModel):
    name: str

class OrganizationCreate(OrganizationBase):
    pass

class OrganizationUpdate(BaseModel):
    name: str | None = None

class OrganizationResponse(OrganizationBase):
    id: uuid.UUID
    created_at: datetime
    
    model_config = {"from_attributes": True}

class MembershipResponse(BaseModel):
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: Role

    model_config = {"from_attributes": True}

class RoleUpdate(BaseModel):
    role: Role

