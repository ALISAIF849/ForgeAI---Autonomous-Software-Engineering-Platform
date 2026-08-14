from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.exceptions import MetricAlreadyRegisteredError, MetricNotFoundError
from forgeai_analytics.registry import (
    MetricAvailability,
    MetricCategory,
    MetricConfidence,
    MetricDefinition,
    MetricResult,
    MetricsRegistry,
    confidence_for_sample_size,
)


def _definition(metric_id: str = "example_metric") -> MetricDefinition:
    return MetricDefinition(
        id=metric_id,
        name="Example Metric",
        description="A metric used only in tests.",
        category=MetricCategory.DELIVERY,
        formula="COUNT(x)",
        data_sources=("example_table",),
        window="custom",
        aggregation="count",
        owner="platform-team",
    )


class _FixedMetric:
    def __init__(self, metric_id: str = "example_metric", *, value: int = 42) -> None:
        self.definition = _definition(metric_id)
        self._value = value

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
            availability=MetricAvailability.AVAILABLE,
            value=self._value,
            unit="count",
            window_start=window_start,
            window_end=window_end,
            evidence={"raw": self._value},
            confidence=MetricConfidence.HIGH,
        )


class TestRegistration:
    def test_register_then_get_round_trips(self) -> None:
        registry = MetricsRegistry()
        metric = _FixedMetric()

        registry.register(metric)

        assert registry.get("example_metric") is metric
        assert registry.is_registered("example_metric") is True

    def test_reregistering_the_same_id_is_rejected(self) -> None:
        registry = MetricsRegistry()
        registry.register(_FixedMetric())

        with pytest.raises(MetricAlreadyRegisteredError):
            registry.register(_FixedMetric())

    def test_getting_an_unregistered_metric_raises(self) -> None:
        registry = MetricsRegistry()
        with pytest.raises(MetricNotFoundError):
            registry.get("nope")

    def test_is_registered_false_for_unknown_id(self) -> None:
        registry = MetricsRegistry()
        assert registry.is_registered("nope") is False

    def test_list_definitions_returns_every_registered_definition(self) -> None:
        registry = MetricsRegistry()
        registry.register(_FixedMetric("metric_a"))
        registry.register(_FixedMetric("metric_b"))

        ids = {definition.id for definition in registry.list_definitions()}

        assert ids == {"metric_a", "metric_b"}


class TestCalculate:
    async def test_calculate_dispatches_to_the_registered_calculator(
        self, db: AsyncSession
    ) -> None:
        registry = MetricsRegistry()
        registry.register(_FixedMetric(value=7))
        window_start = datetime(2026, 1, 1, tzinfo=UTC)
        window_end = datetime(2026, 1, 8, tzinfo=UTC)

        result = await registry.calculate(
            "example_metric", db, window_start=window_start, window_end=window_end
        )

        assert result.is_available is True
        assert result.value == 7
        assert result.window_start == window_start
        assert result.window_end == window_end

    async def test_calculate_for_an_unregistered_metric_raises(self, db: AsyncSession) -> None:
        registry = MetricsRegistry()
        with pytest.raises(MetricNotFoundError):
            await registry.calculate(
                "nope",
                db,
                window_start=datetime(2026, 1, 1, tzinfo=UTC),
                window_end=datetime(2026, 1, 8, tzinfo=UTC),
            )


class TestConfidence:
    def test_high_confidence_at_or_above_the_threshold(self) -> None:
        assert confidence_for_sample_size(5) == MetricConfidence.HIGH
        assert confidence_for_sample_size(100) == MetricConfidence.HIGH

    def test_low_confidence_below_the_threshold(self) -> None:
        assert confidence_for_sample_size(1) == MetricConfidence.LOW
        assert confidence_for_sample_size(0) == MetricConfidence.LOW
