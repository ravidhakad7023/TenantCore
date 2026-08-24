import uuid
from datetime import datetime
from pydantic import BaseModel

class ProjectBase(BaseModel):
    name: str
    description: str | None = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

class ProjectResponse(ProjectBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

class ProjectPageResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
