"""Sprint 18 Stage 1 — the Metrics Registry. Every metric ForgeAI reports
carries a MetricDefinition (source, formula, data sources, window,
aggregation, owner) and every computed value is a MetricResult that's
either a real number with its evidence, or explicitly NOT_AVAILABLE with a
reason — never a silently estimated or fabricated number, per the sprint's
Core Principle. A category with no real underlying data source yet (see
dora_metrics.py) registers its definition normally and always returns
NOT_AVAILABLE; that is the intended, honest behavior here, not a placeholder
that fakes a number to "finish later."

AVAILABLE-with-zero vs. NOT_AVAILABLE is a deliberate, principled split, not
an arbitrary per-metric choice: a SUM over zero matching rows is
well-defined ("$0 spent" is a real, meaningful answer) and stays AVAILABLE;
a RATE or AVERAGE with a zero denominator is mathematically undefined and
is reported NOT_AVAILABLE rather than fabricating a 0% or a 0-second
average that would misrepresent "nothing happened" as "everything
succeeded instantly." Each calculator documents which case it is.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.exceptions import MetricAlreadyRegisteredError, MetricNotFoundError


class MetricCategory(enum.StrEnum):
    DELIVERY = "delivery"
    QUALITY = "quality"
    AI_USAGE = "ai_usage"
    COST = "cost"
    RELIABILITY = "reliability"
    ARCHITECTURE = "architecture"
    TECHNICAL_DEBT = "technical_debt"
    SECURITY = "security"


class MetricAvailability(enum.StrEnum):
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"


class MetricConfidence(enum.StrEnum):
    """Deterministic, evidence-volume-based — never an opaque/subjective
    judgment. Thresholds are intentionally simple and documented here, the
    one place they're defined."""

    HIGH = "high"
    LOW = "low"


def confidence_for_sample_size(sample_size: int, *, high_threshold: int = 5) -> MetricConfidence:
    return MetricConfidence.HIGH if sample_size >= high_threshold else MetricConfidence.LOW


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    id: str
    name: str
    description: str
    category: MetricCategory
    formula: str
    data_sources: tuple[str, ...]
    window: str
    aggregation: str
    owner: str


@dataclass(frozen=True, slots=True)
class MetricResult:
    metric_id: str
    availability: MetricAvailability
    value: Any | None
    unit: str | None
    window_start: datetime | None
    window_end: datetime | None
    evidence: dict[str, Any]
    confidence: MetricConfidence | None
    reason_unavailable: str | None = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_available(self) -> bool:
        return self.availability == MetricAvailability.AVAILABLE


class MetricCalculator(Protocol):
    definition: MetricDefinition

    async def calculate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult: ...


class MetricsRegistry:
    def __init__(self) -> None:
        self._calculators: dict[str, MetricCalculator] = {}

    def register(self, calculator: MetricCalculator) -> None:
        metric_id = calculator.definition.id
        if metric_id in self._calculators:
            raise MetricAlreadyRegisteredError(metric_id)
        self._calculators[metric_id] = calculator

    def get(self, metric_id: str) -> MetricCalculator:
        try:
            return self._calculators[metric_id]
        except KeyError:
            raise MetricNotFoundError(metric_id) from None

    def is_registered(self, metric_id: str) -> bool:
        return metric_id in self._calculators

    def list_definitions(self) -> list[MetricDefinition]:
        return [calculator.definition for calculator in self._calculators.values()]

    async def calculate(
        self,
        metric_id: str,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult:
        calculator = self.get(metric_id)
        return await calculator.calculate(
            db,
            organization_id=organization_id,
            project_id=project_id,
            window_start=window_start,
            window_end=window_end,
        )
