from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from forgeai_core.workflow_enums import StageStatus

if TYPE_CHECKING:
    from forgeai_core.models.workflow_execution import WorkflowExecution


class WorkflowStageExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One attempt-tracked run of a single stage within a WorkflowExecution.
    `attempt_number` increments on each retry rather than each attempt
    getting its own row — the Retry Engine (sub-sprint 2.4) is expected to
    read this column, not count rows, to decide whether a retry limit has
    been reached."""

    __tablename__ = "workflow_stage_executions"

    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), index=True
    )
    workflow_stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_stages.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[StageStatus] = mapped_column(
        Enum(StageStatus, native_enum=False, length=32),
        default=StageStatus.PENDING,
        server_default=StageStatus.PENDING.value,
        index=True,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when a failed attempt is retryable (status RETRYING): the Retry
    # Engine (2.4) won't re-run the stage until now() reaches this — the
    # backoff delay, persisted so it survives a worker restart between ticks.
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow_execution: Mapped[WorkflowExecution] = relationship(back_populates="stage_executions")
