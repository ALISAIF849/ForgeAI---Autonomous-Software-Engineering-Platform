from __future__ import annotations

from typing import Any

import pytest

from forgeai_capability_registry.definition import CapabilityDefinition
from forgeai_capability_registry.exceptions import (
    CapabilityIOValidationError,
    CapabilityNotFoundError,
    PermissionDeniedError,
)
from forgeai_capability_registry.executor import CapabilityExecutor
from forgeai_capability_registry.permissions import Permission
from forgeai_capability_registry.registry import CapabilityRegistry
from forgeai_capability_registry.sdk import CapabilityContext, CapabilityResult

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"greeting": {"type": "string"}},
    "required": ["greeting"],
}


def _context() -> CapabilityContext:
    return CapabilityContext(
        project_id=None, organization_id=None, workflow_execution_id=None, invoked_by_user_id=None
    )


class _GreetCapability:
    async def execute(
        self, context: CapabilityContext, input_data: dict[str, Any]
    ) -> CapabilityResult:
        return CapabilityResult(
            output={"greeting": f"Hello, {input_data['name']}!"}, reasoning_summary="greeted"
        )


class _BadOutputCapability:
    async def execute(
        self, context: CapabilityContext, input_data: dict[str, Any]
    ) -> CapabilityResult:
        return CapabilityResult(output={"wrong_key": "oops"}, reasoning_summary=None)


class _DefinitionAwareCapability:
    """Records the context it was called with, so tests can assert the
    executor actually populated capability_definition."""

    last_context: CapabilityContext | None = None

    async def execute(
        self, context: CapabilityContext, input_data: dict[str, Any]
    ) -> CapabilityResult:
        _DefinitionAwareCapability.last_context = context
        return CapabilityResult(output={"greeting": "hi"}, reasoning_summary=None)


def _definition(
    capability_id: str = "greet",
    *,
    permissions: frozenset[Permission] = frozenset(),
) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=capability_id,
        name=capability_id,
        version="1.0.0",
        owner="platform-team",
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        permissions=permissions,
    )


class TestExecuteHappyPath:
    async def test_calls_the_implementation_and_returns_its_result(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition(), _GreetCapability)
        executor = CapabilityExecutor(registry)

        result = await executor.execute("greet", "1.0.0", _context(), {"name": "Ada"})

        assert result.output == {"greeting": "Hello, Ada!"}

    async def test_an_unregistered_capability_raises(self) -> None:
        registry = CapabilityRegistry()
        executor = CapabilityExecutor(registry)

        with pytest.raises(CapabilityNotFoundError):
            await executor.execute("nope", "1.0.0", _context(), {})


class TestInputValidation:
    async def test_input_missing_a_required_property_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition(), _GreetCapability)
        executor = CapabilityExecutor(registry)

        with pytest.raises(CapabilityIOValidationError) as exc_info:
            await executor.execute("greet", "1.0.0", _context(), {})

        assert exc_info.value.kind == "input"

    async def test_valid_input_passes_through(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition(), _GreetCapability)
        executor = CapabilityExecutor(registry)

        result = await executor.execute("greet", "1.0.0", _context(), {"name": "Grace"})

        assert result.output["greeting"] == "Hello, Grace!"


class TestOutputValidation:
    async def test_output_not_matching_the_schema_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition(), _BadOutputCapability)
        executor = CapabilityExecutor(registry)

        with pytest.raises(CapabilityIOValidationError) as exc_info:
            await executor.execute("greet", "1.0.0", _context(), {"name": "Ada"})

        assert exc_info.value.kind == "output"


class TestPermissions:
    async def test_missing_a_required_permission_is_rejected_before_the_capability_runs(
        self,
    ) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _definition(permissions=frozenset({Permission.CALL_EXTERNAL_API})), _GreetCapability
        )
        executor = CapabilityExecutor(registry)

        with pytest.raises(PermissionDeniedError):
            await executor.execute("greet", "1.0.0", _context(), {"name": "Ada"})

    async def test_a_granted_required_permission_allows_execution(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _definition(permissions=frozenset({Permission.CALL_EXTERNAL_API})), _GreetCapability
        )
        executor = CapabilityExecutor(registry)

        result = await executor.execute(
            "greet",
            "1.0.0",
            _context(),
            {"name": "Ada"},
            granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
        )

        assert result.output == {"greeting": "Hello, Ada!"}


class TestCapabilityDefinitionInjection:
    async def test_the_implementation_receives_its_own_resolved_definition(self) -> None:
        registry = CapabilityRegistry()
        definition = _definition()
        registry.register(definition, _DefinitionAwareCapability)
        executor = CapabilityExecutor(registry)

        await executor.execute("greet", "1.0.0", _context(), {"name": "Ada"})

        assert _DefinitionAwareCapability.last_context is not None
        assert _DefinitionAwareCapability.last_context.capability_definition == definition
