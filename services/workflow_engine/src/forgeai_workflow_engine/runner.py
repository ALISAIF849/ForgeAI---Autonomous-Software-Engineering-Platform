"""The plug point for "how does a stage's work actually happen" — deliberately
generic and pluggable, matching Sprint 2/3's "capabilities are plugins"
philosophy. The real implementation (invoking the Capability Executor / AI
Execution Pipeline) doesn't exist yet — that's later, AI-focused work. This
defines the contract and a fake reference implementation, so the Executor
itself (this sub-sprint) is fully testable without real capability execution
existing.

An ABC, not a Protocol like capability_registry.sdk.Capability: `rollback` is
genuinely optional (most stages have nothing meaningful to undo until real
capabilities exist), and a Protocol has no clean way to give every structural
implementer a free default method — an ABC does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from forgeai_workflow_engine.definition import StageDefinition


@dataclass(frozen=True, slots=True)
class StageRunContext:
    workflow_execution_id: UUID
    project_id: UUID
    stage_input: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StageRunResult:
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class StageRunner(ABC):
    @abstractmethod
    async def run(self, stage: StageDefinition, context: StageRunContext) -> StageRunResult: ...

    async def rollback(self, stage: StageDefinition, context: StageRunContext) -> None:
        """Default no-op. A runner that doesn't override this is simply
        non-reversible — the Executor treats that as "nothing to undo", not
        an error (see executor.py's failure-handling path)."""
        return None


class UnconfiguredStageRunner(StageRunner):
    """The honest default for a caller (e.g. the API in apps/api) that needs
    *some* StageRunner to construct a WorkflowExecutor but has no real
    capability execution wired up yet — that's the Capability Executor / AI
    Execution Pipeline, still-pending Sprint 3 work. Fails every stage with a
    clear, explanatory error rather than silently pretending success like a
    test double would; a caller that wires in a real runner (or, in tests, an
    explicitly-labeled fake one) never reaches this class at all."""

    async def run(self, stage: StageDefinition, context: StageRunContext) -> StageRunResult:
        return StageRunResult(
            success=False,
            error=(
                f"No capability execution is configured for stage '{stage.id}' yet "
                "— the Capability Executor / AI Execution Pipeline hasn't been built."
            ),
        )


class FakeStageRunner(StageRunner):
    """Reference implementation for tests — deterministic, no I/O. Always
    succeeds unless the stage's key is listed in `fail_stage_keys`, so a test
    can script exactly which stages fail without needing real capability
    execution to exist. Records every call for assertions."""

    def __init__(self, fail_stage_keys: frozenset[str] = frozenset()) -> None:
        self.fail_stage_keys = fail_stage_keys
        self.run_calls: list[str] = []
        self.rollback_calls: list[str] = []

    async def run(self, stage: StageDefinition, context: StageRunContext) -> StageRunResult:
        self.run_calls.append(stage.id)
        if stage.id in self.fail_stage_keys:
            return StageRunResult(success=False, error=f"stage '{stage.id}' was scripted to fail")
        return StageRunResult(success=True, output={"stage_id": stage.id})

    async def rollback(self, stage: StageDefinition, context: StageRunContext) -> None:
        self.rollback_calls.append(stage.id)
