from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_model_router.exceptions import ModelNotFoundError
from forgeai_model_router.persistence import ModelProfileRepository, UsageLedger
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.types import TokenUsage


def _profile(key: str, *, is_active: bool = True) -> ModelProfile:
    return ModelProfile(
        key=key,
        provider="mock",
        model_id=f"mock-{key}",
        tier=ModelTier.FAST_CHEAP,
        context_window=8000,
        cost_per_1m_input=Decimal("1.00"),
        cost_per_1m_output=Decimal("2.00"),
        is_active=is_active,
    )


class TestModelProfileRepository:
    async def test_save_then_get_round_trips(self, db: AsyncSession) -> None:
        repo = ModelProfileRepository(db)
        await repo.save(_profile("fast"))
        await db.commit()

        loaded = await repo.get("fast")

        assert loaded is not None
        assert loaded.key == "fast"
        assert loaded.provider == "mock"
        assert loaded.tier == ModelTier.FAST_CHEAP
        assert loaded.cost_per_1m_input == Decimal("1.00")

    async def test_getting_an_unknown_key_returns_none(self, db: AsyncSession) -> None:
        repo = ModelProfileRepository(db)
        assert await repo.get("nope") is None

    async def test_saving_again_with_the_same_key_updates_in_place(self, db: AsyncSession) -> None:
        repo = ModelProfileRepository(db)
        await repo.save(_profile("fast"))
        await db.commit()

        updated = _profile("fast", is_active=False)
        await repo.save(updated)
        await db.commit()

        loaded = await repo.get("fast")
        assert loaded is not None
        assert loaded.is_active is False

    async def test_list_active_excludes_inactive_profiles(self, db: AsyncSession) -> None:
        repo = ModelProfileRepository(db)
        await repo.save(_profile("active-1"))
        await repo.save(_profile("active-2"))
        await repo.save(_profile("inactive", is_active=False))
        await db.commit()

        active = await repo.list_active()

        assert {p.key for p in active} == {"active-1", "active-2"}


class TestUsageLedger:
    async def test_record_persists_a_row(self, db: AsyncSession) -> None:
        profile_repo = ModelProfileRepository(db)
        await profile_repo.save(_profile("fast"))
        await db.commit()
        ledger = UsageLedger(db)

        await ledger.record(
            "fast", TokenUsage(input_tokens=100, output_tokens=50, cost_usd=Decimal("0.0002"))
        )
        await db.commit()

        total = await ledger.total_cost()
        assert total == Decimal("0.0002")

    async def test_recording_against_an_unknown_model_key_raises(self, db: AsyncSession) -> None:
        ledger = UsageLedger(db)
        with pytest.raises(ModelNotFoundError):
            await ledger.record(
                "nope", TokenUsage(input_tokens=1, output_tokens=1, cost_usd=Decimal("0.01"))
            )

    async def test_total_cost_scoped_by_project(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, org_id, project_id = seeded_project
        profile_repo = ModelProfileRepository(db)
        await profile_repo.save(_profile("fast"))
        await db.commit()
        ledger = UsageLedger(db)

        await ledger.record(
            "fast",
            TokenUsage(input_tokens=1, output_tokens=1, cost_usd=Decimal("1.00")),
            project_id=project_id,
            organization_id=org_id,
        )
        await ledger.record(
            "fast", TokenUsage(input_tokens=1, output_tokens=1, cost_usd=Decimal("5.00"))
        )
        await db.commit()

        assert await ledger.total_cost(project_id=project_id) == Decimal("1.00")
        assert await ledger.total_cost() == Decimal("6.00")

    async def test_total_cost_with_no_entries_is_zero(self, db: AsyncSession) -> None:
        ledger = UsageLedger(db)
        assert await ledger.total_cost() == Decimal("0")
