"""Sprint 18 Stage 2 — the four core DORA metrics. Every one of them is
honestly NOT_AVAILABLE: computing Deployment Frequency, Lead Time for
Changes, Change Failure Rate, or Mean Time to Recovery requires deployment
and incident records that don't exist anywhere in ForgeAI yet — there is no
persisted Deployment or Incident model, and no DevOps/Deployment workflow
that would produce one. The sprint's own Core Principle is explicit: "If
the required data does not exist: NOT_AVAILABLE. Do not estimate silently."
Registering these definitions now (rather than omitting them) keeps the
registry structurally complete and gives a caller one place to see exactly
what's missing and why, rather than a metric_id that simply doesn't exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.registry import (
    MetricAvailability,
    MetricCategory,
    MetricDefinition,
    MetricResult,
)

_NO_DEPLOYMENT_DATA = (
    "No deployment records exist in ForgeAI yet — this metric needs a persisted "
    "Deployment/Release model that the DevOps & Deployment integration doesn't produce yet."
)
_NO_INCIDENT_DATA = (
    "No incident records exist in ForgeAI yet — this metric needs a persisted "
    "Incident model that doesn't exist yet."
)


class _AlwaysUnavailableMetric:
    """Shared shape for the four DORA calculators below: same NOT_AVAILABLE
    contract every time, only the definition and reason differ."""

    def __init__(self, definition: MetricDefinition, reason: str) -> None:
        self.definition = definition
        self._reason = reason

    async def calculate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult:
        return MetricResult(
            metric_id=self.definition.id,
            availability=MetricAvailability.NOT_AVAILABLE,
            value=None,
            unit=None,
            window_start=window_start,
            window_end=window_end,
            evidence={},
            confidence=None,
            reason_unavailable=self._reason,
        )


def deployment_frequency_metric() -> _AlwaysUnavailableMetric:
    return _AlwaysUnavailableMetric(
        MetricDefinition(
            id="deployment_frequency",
            name="Deployment Frequency",
            description="Successful production deployments per time period.",
            category=MetricCategory.DELIVERY,
            formula="COUNT(successful production deployments) / period",
            data_sources=("deployments",),
            window="custom",
            aggregation="rate",
            owner="platform-team",
        ),
        _NO_DEPLOYMENT_DATA,
    )


def lead_time_for_changes_metric() -> _AlwaysUnavailableMetric:
    return _AlwaysUnavailableMetric(
        MetricDefinition(
            id="lead_time_for_changes",
            name="Lead Time for Changes",
            description="Time from first commit to production deployment.",
            category=MetricCategory.DELIVERY,
            formula="AVG(deployment.deployed_at - commit.first_commit_at)",
            data_sources=("deployments", "commits"),
            window="custom",
            aggregation="average",
            owner="platform-team",
        ),
        _NO_DEPLOYMENT_DATA,
    )


def change_failure_rate_metric() -> _AlwaysUnavailableMetric:
    return _AlwaysUnavailableMetric(
        MetricDefinition(
            id="change_failure_rate",
            name="Change Failure Rate",
            description="Share of production deployments that resulted in a failure.",
            category=MetricCategory.RELIABILITY,
            formula="COUNT(failed deployments) / COUNT(total deployments)",
            data_sources=("deployments",),
            window="custom",
            aggregation="rate",
            owner="platform-team",
        ),
        _NO_DEPLOYMENT_DATA,
    )


def mean_time_to_recovery_metric() -> _AlwaysUnavailableMetric:
    return _AlwaysUnavailableMetric(
        MetricDefinition(
            id="mean_time_to_recovery",
            name="Mean Time to Recovery",
            description="Average time from incident detection to service recovery.",
            category=MetricCategory.RELIABILITY,
            formula="AVG(incident.recovered_at - incident.detected_at)",
            data_sources=("incidents",),
            window="custom",
            aggregation="average",
            owner="platform-team",
        ),
        _NO_INCIDENT_DATA,
    )
