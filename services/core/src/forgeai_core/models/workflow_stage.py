from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.workflow_version import WorkflowVersion


class WorkflowStage(Base, UUIDPrimaryKeyMixin):
    """A normalized, queryable row per stage per version — the same stages
    already live inside WorkflowVersion.graph_spec as JSON, but that shape
    can't be indexed or joined against (e.g. "every stage using capability
    X" or "the stage a given WorkflowStageExecution belongs to"). This table
    exists for exactly that: referential integrity and queryability, derived
    from graph_spec at version-registration time, not a second source of truth
    to keep manually in sync."""

    __tablename__ = "workflow_stages"
    __table_args__ = (
        UniqueConstraint("workflow_version_id", "stage_key", name="uq_workflow_stage_key"),
    )

    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    stage_key: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    sequence_index: Mapped[int] = mapped_column(Integer)
    depends_on: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    capability_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retry_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    timeout_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    allow_skip: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    workflow_version: Mapped[WorkflowVersion] = relationship(back_populates="stages")
