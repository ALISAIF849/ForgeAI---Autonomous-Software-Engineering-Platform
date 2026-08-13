from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import UUIDPrimaryKeyMixin


class MemoryEvent(Base, UUIDPrimaryKeyMixin):
    """Episodic memory, per docs/architecture/05-memory-engine.md §1: an
    append-only log of "everything that happened" for a project — broader
    than forgeai_workflow_engine's own WorkflowEvent (which is scoped to one
    WorkflowExecution's transitions). A workflow completing is one possible
    *source* of a MemoryEvent, not the same table — Memory Engine is a higher
    layer (5) than Workflow Engine (2) and doesn't replace its event bus,
    only optionally gets fed by it.

    No TimestampMixin, same reasoning as WorkflowEvent: append-only, never
    modified after being written, so there's no `updated_at` to track."""

    __tablename__ = "memory_events"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
