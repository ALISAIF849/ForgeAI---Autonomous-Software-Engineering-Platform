from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.model_profile import ModelProfileRecord


class UsageLedgerEntry(Base, UUIDPrimaryKeyMixin):
    """One row per completion call actually made — the record that makes
    cost real rather than estimated, per docs/architecture/06-model-router.md
    §4: "added to the schema specifically because the brief's listed
    entities didn't include one, despite the product being cost-driven by
    construction." `organization_id`/`project_id`/`workflow_execution_id`
    are all nullable: a completion call doesn't always happen inside a
    workflow (e.g. an ad hoc call), and the caller may not always have
    org/project context to attribute it to. No `capability_execution_id`
    yet — that table doesn't exist until the Capability Executor does;
    adding the column now would be a FK to nothing.
    """

    __tablename__ = "usage_ledger"

    model_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_profiles.id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    # No `updated_at` — an append-only ledger row is never edited after
    # insert, same reasoning as WorkflowEvent's own created_at-only shape.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    model_profile: Mapped[ModelProfileRecord] = relationship(back_populates="usage_entries")
