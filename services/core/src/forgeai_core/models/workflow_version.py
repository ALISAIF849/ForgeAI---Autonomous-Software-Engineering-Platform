from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.workflow import Workflow
    from forgeai_core.models.workflow_stage import WorkflowStage


class WorkflowVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One immutable, registered snapshot of a workflow's graph —
    `graph_spec` is the serialized form of
    services/workflow_engine's WorkflowDefinition (the Pydantic model that
    validated it before it ever reached this table). Never edited in place
    once created: a workflow change is a new row, not an update to this one —
    the same discipline docs/architecture/03-workflow-engine.md §7 already
    established, now actually enforced by a table that has no update path in
    the repository layer (sub-sprint 2.3), only inserts."""

    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(32))
    graph_spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    workflow: Mapped[Workflow] = relationship(back_populates="versions")
    stages: Mapped[list[WorkflowStage]] = relationship(
        back_populates="workflow_version", cascade="all, delete-orphan"
    )
