"""The "Capability SDK" — what a capability *implementation* (as opposed to
its declarative CapabilityDefinition metadata) conforms to. Deliberately
minimal at this sub-sprint: CapabilityContext only carries identifying IDs so
far. Memory access, model routing, and tool access are added to it as
sub-sprints 3.3-3.6 land (Model Router, Memory Engine, Context Builder,
Executor) — a capability implementation should not assume more than what's
documented here yet.

The definition and the implementation are kept as two separate things on
purpose (a capability's metadata vs. its code), per
docs/architecture/04-capability-registry.md §1: callers depend only on the
contract, never on a specific implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CapabilityContext:
    """Everything a capability's execute() call receives about the situation
    it's running in. `extra` is an explicit, typed escape hatch for
    sub-sprint-specific additions (e.g. a not-yet-formalized memory handle)
    rather than an untyped **kwargs — so it's visible in the type signature
    that something is being passed here ad hoc, and easy to grep for once it
    graduates to a real field."""

    project_id: UUID | None
    organization_id: UUID | None
    workflow_execution_id: UUID | None
    invoked_by_user_id: UUID | None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """A capability's raw return value, before the AI Execution Pipeline's
    Output Validation step (sub-sprint 3.6) checks `output` against the
    definition's output_schema. `reasoning_summary` is required-in-spirit per
    docs/architecture/04-capability-registry.md §5 (explainability) but not
    enforced as non-empty at this layer yet — that enforcement point is
    revisited once real capabilities exist to enforce it against."""

    output: dict[str, Any]
    reasoning_summary: str | None
    produced_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class Capability(Protocol):
    """The interface every capability implementation must satisfy. Structural
    (a Protocol, not an ABC) so an implementation doesn't need to inherit from
    anything this package defines — any object with a matching `execute`
    method satisfies it, keeping capability authors decoupled from this
    package's own class hierarchy."""

    async def execute(
        self, context: CapabilityContext, input_data: dict[str, Any]
    ) -> CapabilityResult: ...
