"""DB-backed implementations for the in-process abstractions from 3.1:
ModelProfileRepository persists what registry.ModelRegistry used to hold only
in memory, and UsageLedger is the real UsageRecorder (recorder.py) — the
same in-process-then-persisted sequence forgeai_workflow_engine already went
through (2.1 -> 2.2).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.model_profile import ModelProfileRecord
from forgeai_core.models.usage_ledger_entry import UsageLedgerEntry
from forgeai_model_router.exceptions import ModelNotFoundError
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.recorder import UsageRecorder
from forgeai_model_router.types import TokenUsage


def _to_domain(record: ModelProfileRecord) -> ModelProfile:
    return ModelProfile(
        key=record.key,
        provider=record.provider,
        model_id=record.model_id,
        tier=ModelTier(record.tier),
        context_window=record.context_window,
        supports_tools=record.supports_tools,
        supports_structured_output=record.supports_structured_output,
        cost_per_1m_input=record.cost_per_1m_input,
        cost_per_1m_output=record.cost_per_1m_output,
        is_active=record.is_active,
    )


class ModelProfileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save(self, profile: ModelProfile) -> None:
        """Upsert by key: create the row if this is a new key, otherwise
        update every mutable field in place — a profile's key is its stable
        identity, everything else (cost rates, active flag, tier) can
        legitimately change without becoming a "different" model."""
        result = await self._db.execute(
            select(ModelProfileRecord).where(ModelProfileRecord.key == profile.key)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = ModelProfileRecord(key=profile.key)
            self._db.add(record)

        record.provider = profile.provider
        record.model_id = profile.model_id
        record.tier = profile.tier.value
        record.context_window = profile.context_window
        record.supports_tools = profile.supports_tools
        record.supports_structured_output = profile.supports_structured_output
        record.cost_per_1m_input = profile.cost_per_1m_input
        record.cost_per_1m_output = profile.cost_per_1m_output
        record.is_active = profile.is_active
        await self._db.flush()

    async def get(self, key: str) -> ModelProfile | None:
        result = await self._db.execute(
            select(ModelProfileRecord).where(ModelProfileRecord.key == key)
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record is not None else None

    async def list_active(self) -> list[ModelProfile]:
        result = await self._db.execute(
            select(ModelProfileRecord).where(ModelProfileRecord.is_active.is_(True))
        )
        return [_to_domain(record) for record in result.scalars().all()]


class UsageLedger(UsageRecorder):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(
        self,
        model_key: str,
        usage: TokenUsage,
        *,
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        workflow_execution_id: uuid.UUID | None = None,
    ) -> None:
        result = await self._db.execute(
            select(ModelProfileRecord.id).where(ModelProfileRecord.key == model_key)
        )
        model_profile_id = result.scalar_one_or_none()
        if model_profile_id is None:
            raise ModelNotFoundError(model_key)

        self._db.add(
            UsageLedgerEntry(
                model_profile_id=model_profile_id,
                organization_id=organization_id,
                project_id=project_id,
                workflow_execution_id=workflow_execution_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost_usd,
            )
        )
        await self._db.flush()

    async def total_cost(
        self,
        *,
        project_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> Decimal:
        query = select(func.coalesce(func.sum(UsageLedgerEntry.cost_usd), 0))
        if project_id is not None:
            query = query.where(UsageLedgerEntry.project_id == project_id)
        if organization_id is not None:
            query = query.where(UsageLedgerEntry.organization_id == organization_id)
        result = await self._db.execute(query)
        return Decimal(result.scalar_one())
