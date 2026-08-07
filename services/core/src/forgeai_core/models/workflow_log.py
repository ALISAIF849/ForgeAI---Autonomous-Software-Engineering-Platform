from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import UUIDPrimaryKeyMixin


class WorkflowLog(Base, UUIDPrimaryKeyMixin):
    """Distinct from WorkflowEvent: events are structured, typed lifecycle
    signals (workflow started, stage completed, ...) that other things react
    to; logs are free-text diagnostic output (what a capability printed while
    running) — same split as docs/engineering/10-logging-observability.md
    draws between structured application logs and everything else."""

    __tablename__ = "workflow_logs"

    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), index=True
    )
    stage_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_stage_executions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
