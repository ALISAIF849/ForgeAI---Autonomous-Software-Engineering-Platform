"""Builds the default MetricsRegistry ForgeAI ships with — every metric this
package currently knows how to compute (or honestly reports as
NOT_AVAILABLE), wired into one registry a caller can query by id. Adding a
metric later is additive here, not a redesign of anything that already
depends on MetricsRegistry.
"""

from __future__ import annotations

from forgeai_analytics.cost_metrics import AICostByModelMetric, AITotalCostMetric
from forgeai_analytics.dora_metrics import (
    change_failure_rate_metric,
    deployment_frequency_metric,
    lead_time_for_changes_metric,
    mean_time_to_recovery_metric,
)
from forgeai_analytics.registry import MetricsRegistry
from forgeai_analytics.workflow_metrics import (
    WorkflowAverageDurationMetric,
    WorkflowRetryRateMetric,
    WorkflowSuccessRateMetric,
)


def build_default_registry() -> MetricsRegistry:
    registry = MetricsRegistry()
    registry.register(WorkflowSuccessRateMetric())
    registry.register(WorkflowAverageDurationMetric())
    registry.register(WorkflowRetryRateMetric())
    registry.register(AITotalCostMetric())
    registry.register(AICostByModelMetric())
    registry.register(deployment_frequency_metric())
    registry.register(lead_time_for_changes_metric())
    registry.register(change_failure_rate_metric())
    registry.register(mean_time_to_recovery_metric())
    return registry
