import uuid
from datetime import datetime
from pydantic import BaseModel

from app.models.task import TaskStatus, TaskPriority

class TaskBase(BaseModel):
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: datetime | None = None
    assigned_to: uuid.UUID | None = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None
    assigned_to: uuid.UUID | None = None
    version: int

class TaskResponse(TaskBase):
    id: uuid.UUID
    project_id: uuid.UUID
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    version: int
    
    model_config = {"from_attributes": True}

class TaskPageResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    page_size: int
