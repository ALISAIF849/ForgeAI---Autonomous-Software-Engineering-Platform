from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.enums import ProjectStatus, ProjectVisibility
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.organization import Organization
    from forgeai_core.models.project_member import ProjectMember


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Three independent lifecycle states, not one: `status` (active/archived) is a
    reversible, user-visible state change; `deleted_at` is a separate soft-delete
    marker (the Delete/Restore pair) that hides a project from normal views without
    losing data. A project can be archived AND later deleted — they're not the same
    axis, which is why this isn't a single enum with an extra "deleted" value."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_project_org_slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=16), default=ProjectStatus.ACTIVE
    )
    visibility: Mapped[ProjectVisibility] = mapped_column(
        Enum(ProjectVisibility, native_enum=False, length=16), default=ProjectVisibility.PRIVATE
    )
    tech_stack: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    organization: Mapped[Organization] = relationship(back_populates="projects")
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
