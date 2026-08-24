import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import ForeignKey, DateTime, UniqueConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Role(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"

class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[Role] = mapped_column(String(50), nullable=False, default=Role.MEMBER, server_default=Role.MEMBER.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="memberships")
    organization: Mapped["Organization"] = relationship("Organization", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uix_user_org"),
    )
