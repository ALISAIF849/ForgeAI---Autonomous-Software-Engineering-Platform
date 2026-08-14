"""The "Capability SDK" — what a capability *implementation* (as opposed to
its declarative CapabilityDefinition metadata) conforms to.

CapabilityContext now carries real handles to the Model Router and Prompt
Registry (sub-sprint 3.6) in addition to identifying IDs — a capability
implementation reaches these through `context`, never by constructing its own
ModelRouter/PromptRegistry, because CapabilityRegistry stores
`type[Capability]` and instantiates it with zero arguments
(CapabilityExecutor does `implementation_cls()`); there is no constructor
seam to inject dependencies through. `capability_definition` is populated by
CapabilityExecutor itself (not by whoever originally builds the context) so
an implementation can look at its own declared `supported_models` without
hardcoding a model key. Memory access isn't here yet — no Context Builder
wires the Memory Engine into an execution yet.

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

from forgeai_capability_registry.definition import CapabilityDefinition
from forgeai_model_router.router import ModelRouter
from forgeai_prompts.registry import PromptRegistry


@dataclass(frozen=True, slots=True)
class CapabilityContext:
    """Everything a capability's execute() call receives about the situation
    it's running in. `extra` is an explicit, typed escape hatch for
    still-unformalized additions rather than an untyped **kwargs — so it's
    visible in the type signature that something is being passed here ad hoc,
    and easy to grep for once it graduates to a real field."""

    project_id: UUID | None
    organization_id: UUID | None
    workflow_execution_id: UUID | None
    invoked_by_user_id: UUID | None
    model_router: ModelRouter | None = None
    prompt_registry: PromptRegistry | None = None
    capability_definition: CapabilityDefinition | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """A capability's raw return value, before CapabilityExecutor's Output
    Validation step checks `output` against the definition's output_schema.
    `reasoning_summary` is required-in-spirit per
    docs/architecture/04-capability-registry.md §5 (explainability) but not
    enforced as non-empty at this layer yet — that enforcement point is
    revisited once more real capabilities exist to enforce it against."""

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
