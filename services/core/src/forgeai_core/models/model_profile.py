from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.usage_ledger_entry import UsageLedgerEntry


class ModelProfileRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The persisted counterpart of forgeai_model_router.profile.ModelProfile
    (sub-sprint 3.1) — same bootstrap sequence as Workflow/WorkflowVersion:
    a validated Pydantic shape first, a DB row once persistence is actually
    needed (sub-sprint 3.2). Unlike WorkflowVersion's graph_spec, a
    ModelProfile's fields map cleanly onto real columns — no nested graph
    structure that would need JSON — so this stores them directly rather
    than blobbing the whole profile."""

    __tablename__ = "model_profiles"

    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(255))
    tier: Mapped[str] = mapped_column(String(32))
    context_window: Mapped[int] = mapped_column(Integer)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    supports_structured_output: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    cost_per_1m_input: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    cost_per_1m_output: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    usage_entries: Mapped[list[UsageLedgerEntry]] = relationship(back_populates="model_profile")
