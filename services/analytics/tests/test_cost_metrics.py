"""Integration tests for the AI cost calculators — seeding real
ModelProfileRecord/UsageLedgerEntry rows (the same tables
forgeai_model_router.persistence writes in production) directly, then
verifying the calculators' SUM/GROUP BY queries against them."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.cost_metrics import AICostByModelMetric, AITotalCostMetric
from forgeai_analytics.exceptions import MissingScopeError
from forgeai_core.models.model_profile import ModelProfileRecord
from forgeai_core.models.usage_ledger_entry import UsageLedgerEntry

_WIDE_WINDOW_START = datetime(2000, 1, 1, tzinfo=UTC)
_WIDE_WINDOW_END = datetime(2100, 1, 1, tzinfo=UTC)


async def _model(db: AsyncSession, key: str) -> ModelProfileRecord:
    record = ModelProfileRecord(
        key=key,
        provider="mock",
        model_id=f"mock-{key}",
        tier="fast_cheap",
        context_window=8000,
        cost_per_1m_input=Decimal("1.00"),
        cost_per_1m_output=Decimal("2.00"),
    )
    db.add(record)
    await db.flush()
    return record


async def _usage(
    db: AsyncSession,
    model: ModelProfileRecord,
    *,
    cost: Decimal,
    project_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> None:
    db.add(
        UsageLedgerEntry(
            model_profile_id=model.id,
            organization_id=organization_id,
            project_id=project_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
    )
    await db.flush()


class TestAITotalCostMetric:
    async def test_no_usage_is_available_with_zero_value(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        """Zero matching rows is a well-defined sum ($0), not NOT_AVAILABLE —
        see registry.py's module docstring for why sums differ from rates."""
        _user_id, _org_id, project_id = seeded_project
        metric = AITotalCostMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.is_available is True
        assert result.value == Decimal("0")

    async def test_sums_cost_across_matching_entries(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, org_id, project_id = seeded_project
        model = await _model(db, "fast")
        await _usage(db, model, cost=Decimal("1.50"), project_id=project_id, organization_id=org_id)
        await _usage(db, model, cost=Decimal("2.25"), project_id=project_id, organization_id=org_id)
        await db.commit()
        metric = AITotalCostMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.value == Decimal("3.75")
        assert result.evidence == {"completion_calls": 2}

    async def test_missing_scope_raises(self, db: AsyncSession) -> None:
        metric = AITotalCostMetric()
        with pytest.raises(MissingScopeError):
            await metric.calculate(
                db,
                organization_id=None,
                project_id=None,
                window_start=_WIDE_WINDOW_START,
                window_end=_WIDE_WINDOW_END,
            )

    async def test_a_narrow_window_excludes_entries_outside_it(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        model = await _model(db, "fast")
        await _usage(db, model, cost=Decimal("9.99"), project_id=project_id)
        await db.commit()
        metric = AITotalCostMetric()
        far_future_start = datetime.now(UTC) + timedelta(days=365)

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=far_future_start,
            window_end=far_future_start + timedelta(days=1),
        )

        assert result.value == Decimal("0")


class TestAICostByModelMetric:
    async def test_breaks_cost_down_per_model(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        fast = await _model(db, "fast")
        smart = await _model(db, "smart")
        await _usage(db, fast, cost=Decimal("1.00"), project_id=project_id)
        await _usage(db, fast, cost=Decimal("1.00"), project_id=project_id)
        await _usage(db, smart, cost=Decimal("10.00"), project_id=project_id)
        await db.commit()
        metric = AICostByModelMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.value == Decimal("12.00")
        assert result.evidence["by_model"]["fast"]["completion_calls"] == 2
        assert Decimal(result.evidence["by_model"]["fast"]["cost_usd"]) == Decimal("2.00")
        assert Decimal(result.evidence["by_model"]["smart"]["cost_usd"]) == Decimal("10.00")

    async def test_no_usage_yields_an_empty_breakdown_not_unavailable(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        metric = AICostByModelMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.is_available is True
        assert result.value == Decimal("0")
        assert result.evidence["by_model"] == {}


class TestTenantIsolation:
    async def test_a_projects_cost_never_includes_another_projects_usage(
        self,
        db: AsyncSession,
        seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
        other_seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        _other_user_id, _other_org_id, other_project_id = other_seeded_project
        model = await _model(db, "shared-model")
        await _usage(db, model, cost=Decimal("5.00"), project_id=project_id)
        await _usage(db, model, cost=Decimal("999.00"), project_id=other_project_id)
        await db.commit()
        metric = AITotalCostMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.value == Decimal("5.00")

    async def test_organization_scoping_isolates_usage_with_no_project_id(
        self,
        db: AsyncSession,
        seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
        other_seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        _user_id, org_id, _project_id = seeded_project
        _other_user_id, other_org_id, _other_project_id = other_seeded_project
        model = await _model(db, "shared-model")
        # Neither entry has project_id set — only organization_id, exercising
        # the org-only scoping path (a completion call with no project context).
        await _usage(db, model, cost=Decimal("3.00"), organization_id=org_id)
        await _usage(db, model, cost=Decimal("777.00"), organization_id=other_org_id)
        await db.commit()
        metric = AITotalCostMetric()

        result = await metric.calculate(
            db,
            organization_id=org_id,
            project_id=None,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.value == Decimal("3.00")
