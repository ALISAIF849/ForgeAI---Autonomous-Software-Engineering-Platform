from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import UUIDPrimaryKeyMixin


class WorkflowMetric(Base, UUIDPrimaryKeyMixin):
    """One row per execution with concrete aggregate columns, not a generic
    name/value table — a metrics dashboard wants "average duration across
    executions" style queries, which an EAV shape makes needlessly awkward.
    Written once the execution reaches a terminal state (sub-sprint 2.3)."""

    __tablename__ = "workflow_metrics"

    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), unique=True, index=True
    )
    total_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    queue_wait_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    stages_completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    stages_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retries_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
