"""AI cost metrics (Sprint 18 Stage 5), computed from UsageLedgerEntry — the
real, persisted, per-completion-call cost ledger forgeai_model_router has
written since sub-sprint 3.2. Nothing here estimates cost; every value is a
sum over UsageLedgerEntry.cost_usd rows that actually exist.

A SUM over zero matching rows is well-defined ("$0 spent" is a real,
meaningful answer for a scope/window with no AI usage), so unlike the rate/
average metrics in workflow_metrics.py, these stay AVAILABLE even when no
usage occurred — see registry.py's module docstring for the general rule.

At least one of project_id/organization_id is required (MissingScopeError
otherwise): UsageLedgerEntry's project_id/organization_id are both nullable
independently, and computing across neither would mean reading every
tenant's usage at once.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.exceptions import MissingScopeError
from forgeai_analytics.registry import (
    MetricAvailability,
    MetricCategory,
    MetricDefinition,
    MetricResult,
    confidence_for_sample_size,
)
from forgeai_core.models.model_profile import ModelProfileRecord
from forgeai_core.models.usage_ledger_entry import UsageLedgerEntry


def _scope_filters(
    project_id: uuid.UUID | None, organization_id: uuid.UUID | None
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if project_id is not None:
        filters.append(UsageLedgerEntry.project_id == project_id)
    if organization_id is not None:
        filters.append(UsageLedgerEntry.organization_id == organization_id)
    return filters


class AITotalCostMetric:
    definition = MetricDefinition(
        id="ai_total_cost_usd",
        name="Total AI Cost",
        description=(
            "Sum of actual model-completion cost recorded in the usage ledger for the "
            "given scope and window."
        ),
        category=MetricCategory.COST,
        formula="SUM(usage_ledger.cost_usd)",
        data_sources=("usage_ledger",),
        window="custom",
        aggregation="sum",
        owner="platform-team",
    )

    async def calculate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult:
        if project_id is None and organization_id is None:
            raise MissingScopeError(self.definition.id)

        filters = _scope_filters(project_id, organization_id)
        costs = (
            (
                await db.execute(
                    select(UsageLedgerEntry.cost_usd).where(
                        UsageLedgerEntry.created_at >= window_start,
                        UsageLedgerEntry.created_at <= window_end,
                        *filters,
                    )
                )
            )
            .scalars()
            .all()
        )

        total = sum(costs, Decimal("0"))
        return MetricResult(
            metric_id=self.definition.id,
            availability=MetricAvailability.AVAILABLE,
            value=total,
            unit="usd",
            window_start=window_start,
            window_end=window_end,
            evidence={"completion_calls": len(costs)},
            confidence=confidence_for_sample_size(len(costs)),
        )


class AICostByModelMetric:
    definition = MetricDefinition(
        id="ai_cost_by_model",
        name="AI Cost by Model",
        description=(
            "Total cost, token usage, and call count broken down by model, for the "
            "given scope and window."
        ),
        category=MetricCategory.COST,
        formula=(
            "SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*) "
            "grouped by model_profiles.key"
        ),
        data_sources=("usage_ledger", "model_profiles"),
        window="custom",
        aggregation="sum_by_group",
        owner="platform-team",
    )

    async def calculate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult:
        if project_id is None and organization_id is None:
            raise MissingScopeError(self.definition.id)

        filters = _scope_filters(project_id, organization_id)
        rows = (
            await db.execute(
                select(
                    ModelProfileRecord.key,
                    func.coalesce(func.sum(UsageLedgerEntry.cost_usd), 0),
                    func.coalesce(func.sum(UsageLedgerEntry.input_tokens), 0),
                    func.coalesce(func.sum(UsageLedgerEntry.output_tokens), 0),
                    func.count(UsageLedgerEntry.id),
                )
                .join(
                    ModelProfileRecord, ModelProfileRecord.id == UsageLedgerEntry.model_profile_id
                )
                .where(
                    UsageLedgerEntry.created_at >= window_start,
                    UsageLedgerEntry.created_at <= window_end,
                    *filters,
                )
                .group_by(ModelProfileRecord.key)
            )
        ).all()

        by_model: dict[str, dict[str, str | int]] = {}
        total_cost = Decimal("0")
        total_calls = 0
        for model_key, cost, input_tokens, output_tokens, calls in rows:
            cost_decimal = Decimal(cost)
            by_model[model_key] = {
                "cost_usd": str(cost_decimal),
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens),
                "completion_calls": int(calls),
            }
            total_cost += cost_decimal
            total_calls += int(calls)

        return MetricResult(
            metric_id=self.definition.id,
            availability=MetricAvailability.AVAILABLE,
            value=total_cost,
            unit="usd",
            window_start=window_start,
            window_end=window_end,
            evidence={"by_model": by_model},
            confidence=confidence_for_sample_size(total_calls),
        )
