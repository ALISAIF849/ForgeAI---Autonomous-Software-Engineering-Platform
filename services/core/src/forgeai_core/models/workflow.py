from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.workflow_version import WorkflowVersion


class Workflow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The "family" record — `key` is what services/workflow_engine's
    WorkflowDefinition.id/key refers to. Immutable, version-pinned snapshots
    of the actual graph live in WorkflowVersion, not here."""

    __tablename__ = "workflows"

    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list[WorkflowVersion]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
