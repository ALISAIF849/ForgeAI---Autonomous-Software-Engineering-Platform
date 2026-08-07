from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from forgeai_core.workflow_enums import WorkflowStatus

if TYPE_CHECKING:
    from forgeai_core.models.workflow_stage_execution import WorkflowStageExecution


class WorkflowExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One running (or completed, paused, ...) instance of a WorkflowVersion,
    scoped to a project. `status` is persisted state for
    services/workflow_engine's WorkflowStateMachine — this table is what
    lets an execution survive a worker restart, per
    docs/architecture/03-workflow-engine.md §4."""

    __tablename__ = "workflow_executions"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="RESTRICT"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, native_enum=False, length=32),
        default=WorkflowStatus.DRAFT,
        server_default=WorkflowStatus.DRAFT.value,
        index=True,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    current_stage_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    stage_executions: Mapped[list[WorkflowStageExecution]] = relationship(
        back_populates="workflow_execution", cascade="all, delete-orphan"
    )
