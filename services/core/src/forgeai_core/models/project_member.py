from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.enums import OrgRole
from forgeai_core.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.project import Project
    from forgeai_core.models.user import User


class ProjectMember(Base, UUIDPrimaryKeyMixin):
    """`is_favorite` lives here, not on Project — favoriting is a per-user relationship
    to a project, not a property of the project itself. Reusing the org role enum
    rather than inventing project-specific roles keeps one mental model of
    permission levels across both scopes; a project can still restrict a member
    below their org role, but never above it (enforced in the service layer, not
    here — this is just the data)."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, native_enum=False, length=16), default=OrgRole.DEVELOPER
    )
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship()
