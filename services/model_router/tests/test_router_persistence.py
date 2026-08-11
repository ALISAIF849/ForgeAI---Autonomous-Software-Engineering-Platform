"""Integration test tying ModelRouter (3.1) and UsageLedger (3.2) together
end to end against real Postgres — not just that each works in isolation,
but that the router actually calls the recorder it's handed with the right
values."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_model_router.persistence import ModelProfileRepository, UsageLedger
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.provider import MockProvider
from forgeai_model_router.registry import ModelRegistry
from forgeai_model_router.router import ModelRouter
from forgeai_model_router.types import CompletionRequest, ModelMessage, Role


class TestRouterRecordsUsageThroughTheLedger:
    async def test_a_successful_completion_persists_a_usage_ledger_row(
        self,
        db: AsyncSession,
        seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        _user_id, org_id, project_id = seeded_project
        profile_repo = ModelProfileRepository(db)
        await profile_repo.save(
            ModelProfile(
                key="fast",
                provider="mock",
                model_id="mock-fast-1",
                tier=ModelTier.FAST_CHEAP,
                context_window=8000,
                cost_per_1m_input=Decimal("1.00"),
                cost_per_1m_output=Decimal("2.00"),
            )
        )
        await db.commit()

        saved_profile = await profile_repo.get("fast")
        assert saved_profile is not None
        registry = ModelRegistry()
        registry.register(saved_profile)
        router = ModelRouter(registry, {"mock": MockProvider()})
        ledger = UsageLedger(db)

        response = await router.complete(
            ["fast"],
            CompletionRequest(messages=[ModelMessage(role=Role.USER, content="hello")]),
            usage_recorder=ledger,
            organization_id=org_id,
            project_id=project_id,
        )
        await db.commit()

        recorded_total = await ledger.total_cost(project_id=project_id)
        assert recorded_total == response.usage.cost_usd
        assert recorded_total > Decimal("0")
