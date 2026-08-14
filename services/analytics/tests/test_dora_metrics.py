"""The four DORA metrics must always report NOT_AVAILABLE — there is no
Deployment or Incident model anywhere in ForgeAI yet, so any other result
would be a fabricated number. These tests exist specifically to lock in
that honesty, not to assert a placeholder that's expected to change later."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.dora_metrics import (
    change_failure_rate_metric,
    deployment_frequency_metric,
    lead_time_for_changes_metric,
    mean_time_to_recovery_metric,
)
from forgeai_analytics.registry import MetricAvailability, MetricCalculator

_WINDOW_START = datetime(2026, 1, 1, tzinfo=UTC)
_WINDOW_END = datetime(2026, 1, 8, tzinfo=UTC)

_ALL_DORA_FACTORIES: list[Callable[[], MetricCalculator]] = [
    deployment_frequency_metric,
    lead_time_for_changes_metric,
    change_failure_rate_metric,
    mean_time_to_recovery_metric,
]


@pytest.mark.parametrize("make_metric", _ALL_DORA_FACTORIES)
async def test_every_dora_metric_is_honestly_not_available(
    db: AsyncSession, make_metric: Callable[[], MetricCalculator]
) -> None:
    metric = make_metric()

    result = await metric.calculate(
        db,
        organization_id=None,
        project_id=None,
        window_start=_WINDOW_START,
        window_end=_WINDOW_END,
    )

    assert result.availability == MetricAvailability.NOT_AVAILABLE
    assert result.value is None
    assert result.confidence is None
    assert result.reason_unavailable is not None and len(result.reason_unavailable) > 0


@pytest.mark.parametrize("make_metric", _ALL_DORA_FACTORIES)
def test_every_dora_metric_has_a_documented_definition(
    make_metric: Callable[[], MetricCalculator],
) -> None:
    definition = make_metric().definition

    assert definition.formula
    assert definition.data_sources
    assert definition.owner
