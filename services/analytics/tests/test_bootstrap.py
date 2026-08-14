from __future__ import annotations

from forgeai_analytics.bootstrap import build_default_registry


def test_the_default_registry_has_every_metric_registered_exactly_once() -> None:
    registry = build_default_registry()

    ids = [definition.id for definition in registry.list_definitions()]

    assert len(ids) == len(set(ids))
    assert set(ids) == {
        "workflow_success_rate",
        "workflow_average_duration_seconds",
        "workflow_average_retries",
        "ai_total_cost_usd",
        "ai_cost_by_model",
        "deployment_frequency",
        "lead_time_for_changes",
        "change_failure_rate",
        "mean_time_to_recovery",
    }
