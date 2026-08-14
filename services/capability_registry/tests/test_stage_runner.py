"""Unit tests for CapabilityStageRunner — proves it correctly adapts
workflow_engine's StageRunner contract to CapabilityExecutor without needing
a real WorkflowExecutor/DB (that full chain is exercised separately in
test_workflow_integration.py)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from forgeai_capability_registry.definition import CapabilityDefinition
from forgeai_capability_registry.executor import CapabilityExecutor
from forgeai_capability_registry.permissions import Permission
from forgeai_capability_registry.registry import CapabilityRegistry
from forgeai_capability_registry.sdk import CapabilityContext, CapabilityResult
from forgeai_capability_registry.stage_runner import (
    CapabilityStageRunner,
    InvalidCapabilityReferenceError,
    parse_capability_reference,
)
from forgeai_workflow_engine.definition import StageDefinition
from forgeai_workflow_engine.runner import StageRunContext

_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}


class _GreetCapability:
    async def execute(
        self, context: CapabilityContext, input_data: dict[str, Any]
    ) -> CapabilityResult:
        return CapabilityResult(
            output={"name": f"hello {input_data['name']}"}, reasoning_summary=None
        )


class _BoomCapability:
    async def execute(
        self, context: CapabilityContext, input_data: dict[str, Any]
    ) -> CapabilityResult:
        raise RuntimeError("capability blew up")


def _definition(
    capability_id: str = "greet", *, permissions: frozenset[Permission] = frozenset()
) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=capability_id,
        name=capability_id,
        version="1.0.0",
        owner="platform-team",
        input_schema=_SCHEMA,
        output_schema=_SCHEMA,
        permissions=permissions,
    )


def _context(stage_input: dict[str, Any] | None = None) -> StageRunContext:
    return StageRunContext(
        workflow_execution_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        stage_input=stage_input or {"name": "Ada"},
    )


class TestParseCapabilityReference:
    def test_parses_a_well_formed_reference(self) -> None:
        assert parse_capability_reference("greet@1.0.0") == ("greet", "1.0.0")

    @pytest.mark.parametrize("bad", [None, "", "greet", "greet@", "@1.0.0"])
    def test_rejects_malformed_references(self, bad: str | None) -> None:
        with pytest.raises(InvalidCapabilityReferenceError):
            parse_capability_reference(bad)


class TestRun:
    async def test_a_registered_capability_runs_successfully(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition(), _GreetCapability)
        runner = CapabilityStageRunner(CapabilityExecutor(registry))

        result = await runner.run(
            StageDefinition(id="s1", name="Stage 1", capability="greet@1.0.0"), _context()
        )

        assert result.success is True
        assert result.output == {"name": "hello Ada"}

    async def test_a_malformed_capability_reference_fails_cleanly_not_raising(self) -> None:
        registry = CapabilityRegistry()
        runner = CapabilityStageRunner(CapabilityExecutor(registry))

        result = await runner.run(
            StageDefinition(id="s1", name="Stage 1", capability=None), _context()
        )

        assert result.success is False
        assert "capability_id@version" in (result.error or "")

    async def test_an_unregistered_capability_fails_cleanly_not_raising(self) -> None:
        registry = CapabilityRegistry()
        runner = CapabilityStageRunner(CapabilityExecutor(registry))

        result = await runner.run(
            StageDefinition(id="s1", name="Stage 1", capability="nope@1.0.0"), _context()
        )

        assert result.success is False
        assert result.error is not None

    async def test_a_permission_denial_fails_cleanly_not_raising(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _definition(permissions=frozenset({Permission.CALL_EXTERNAL_API})), _GreetCapability
        )
        runner = CapabilityStageRunner(CapabilityExecutor(registry))

        result = await runner.run(
            StageDefinition(id="s1", name="Stage 1", capability="greet@1.0.0"), _context()
        )

        assert result.success is False

    async def test_a_granted_permission_allows_the_run(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _definition(permissions=frozenset({Permission.CALL_EXTERNAL_API})), _GreetCapability
        )
        runner = CapabilityStageRunner(
            CapabilityExecutor(registry),
            granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
        )

        result = await runner.run(
            StageDefinition(id="s1", name="Stage 1", capability="greet@1.0.0"), _context()
        )

        assert result.success is True

    async def test_a_bug_inside_the_capability_itself_fails_cleanly_not_raising(self) -> None:
        """The one boundary that must never let an exception escape run():
        a capability's own execute() raising something CapabilityExecutor
        doesn't wrap (not a CapabilityRegistryError) still has to become a
        failed StageRunResult, not crash the WorkflowExecutor tick calling
        this runner."""
        registry = CapabilityRegistry()
        registry.register(_definition(), _BoomCapability)
        runner = CapabilityStageRunner(CapabilityExecutor(registry))

        result = await runner.run(
            StageDefinition(id="s1", name="Stage 1", capability="greet@1.0.0"), _context()
        )

        assert result.success is False
        assert "capability blew up" in (result.error or "")
