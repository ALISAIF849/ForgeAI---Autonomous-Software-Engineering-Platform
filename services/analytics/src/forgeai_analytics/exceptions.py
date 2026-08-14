"""Every domain error this package raises. Same one-file, one-base-class
convention as forgeai_workflow_engine.exceptions / forgeai_capability_registry.exceptions
/ forgeai_integrations.exceptions.
"""

from __future__ import annotations


class AnalyticsError(Exception):
    """Base class for every error this package raises."""


class MetricNotFoundError(AnalyticsError):
    def __init__(self, metric_id: str) -> None:
        self.metric_id = metric_id
        super().__init__(f"No metric registered with id '{metric_id}'.")


class MetricAlreadyRegisteredError(AnalyticsError):
    def __init__(self, metric_id: str) -> None:
        self.metric_id = metric_id
        super().__init__(f"Metric '{metric_id}' is already registered.")


class MissingScopeError(AnalyticsError):
    """Raised when a calculator is asked to compute a metric with no
    project/organization scope at all — distinct from NOT_AVAILABLE (which
    means "the data doesn't exist"), this means the caller made a request
    that could only be answered by reading across tenants, which this
    package refuses to do (Sprint 18 Stage 36 / Strict Rule 5: never expose
    cross-tenant analytics)."""

    def __init__(self, metric_id: str) -> None:
        self.metric_id = metric_id
        super().__init__(
            f"Metric '{metric_id}' requires a project_id and/or organization_id scope — "
            "computing it with no scope would mean reading across tenants."
        )
