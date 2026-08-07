from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import UUIDPrimaryKeyMixin


class QueueEntryStatus(enum.StrEnum):
    """Distinct from WorkflowStatus — this tracks the entry's position in the
    Workflow Queue (sub-sprint 2.3's dispatch mechanism), not the workflow's
    own execution state. A queue entry can be QUEUED while its
    WorkflowExecution is still PENDING, and gets removed/marked DONE once a
    worker has picked it up — the two statuses are related but not the same
    axis, same reasoning as Project's status vs. deleted_at split."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    DONE = "done"


class WorkflowQueueEntry(Base, UUIDPrimaryKeyMixin):
    """`workflow_execution_id` is deliberately NOT unique: an execution can be
    re-enqueued after each tick that leaves it still RUNNING (a worker's
    run_iteration, sub-sprint 2.9, does this whenever a stage is RETRYING with
    a future retry_after) — old, already-DONE entries for the same execution
    stay in the table as history, so a second live entry for the same
    execution must be allowed to coexist momentarily around that re-enqueue.
    """

    __tablename__ = "workflow_queue"

    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[QueueEntryStatus] = mapped_column(
        Enum(QueueEntryStatus, native_enum=False, length=16),
        default=QueueEntryStatus.QUEUED,
        server_default=QueueEntryStatus.QUEUED.value,
        index=True,
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
