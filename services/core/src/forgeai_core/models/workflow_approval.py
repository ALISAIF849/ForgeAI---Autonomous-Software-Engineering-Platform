from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from forgeai_core.workflow_enums import ApprovalDecision


class WorkflowApproval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One human-approval gate instance — `decision` is null while pending
    (the row exists the moment execution reaches a HumanApprovalNode, per
    docs/architecture/03-workflow-engine.md §4/§5) and set once decided.
    `requested_from_role` supports "anyone with this role can decide" gates;
    `requested_from_user_id` supports "this specific person" gates — a stage
    can use either."""

    __tablename__ = "workflow_approvals"

    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), index=True
    )
    stage_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_stage_executions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    requested_from_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requested_from_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[ApprovalDecision | None] = mapped_column(
        Enum(ApprovalDecision, native_enum=False, length=32), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
