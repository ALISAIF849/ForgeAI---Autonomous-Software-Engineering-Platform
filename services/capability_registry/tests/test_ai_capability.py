"""End-to-end tests for PromptDrivenCapability — proves the full chain
(CapabilityRegistry -> CapabilityExecutor -> PromptTemplate render -> Model
Router -> MockProvider) actually works together, not just that each package
passes its own isolated tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from forgeai_capability_registry.ai_capability import PromptDrivenCapability
from forgeai_capability_registry.definition import CapabilityDefinition
from forgeai_capability_registry.exceptions import CapabilityExecutionError
from forgeai_capability_registry.executor import CapabilityExecutor
from forgeai_capability_registry.permissions import Permission
from forgeai_capability_registry.registry import CapabilityRegistry
from forgeai_capability_registry.sdk import CapabilityContext
from forgeai_model_router.exceptions import AllModelsExhaustedError
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.provider import MockProvider
from forgeai_model_router.registry import ModelRegistry
from forgeai_model_router.router import ModelRouter
from forgeai_prompts.registry import PromptRegistry
from forgeai_prompts.template import PromptTemplate

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


class GreetCapability(PromptDrivenCapability):
    template_key = "greet"
    template_version = "1.0.0"


class UppercaseGreetCapability(PromptDrivenCapability):
    """Demonstrates overriding build_output() for a differently-shaped
    output_schema than the default {"text": ...}."""

    template_key = "greet"
    template_version = "1.0.0"

    def build_output(self, text: str) -> dict[str, Any]:
        return {"shout": text.upper()}


def _model_router(*, fail_first_n_calls: int = 0) -> tuple[ModelRouter, MockProvider]:
    registry = ModelRegistry()
    registry.register(
        ModelProfile(
            key="mock-fast",
            provider="mock",
            model_id="mock-fast-1",
            tier=ModelTier.FAST_CHEAP,
            context_window=8000,
            cost_per_1m_input=Decimal("0"),
            cost_per_1m_output=Decimal("0"),
        )
    )
    provider = MockProvider(fail_first_n_calls=fail_first_n_calls)
    return ModelRouter(registry, {"mock": provider}), provider


def _prompt_registry() -> PromptRegistry:
    registry = PromptRegistry()
    registry.register(
        PromptTemplate(
            key="greet",
            name="Greet",
            version="1.0.0",
            content="Say hello to {name}.",
            required_variables=["name"],
        )
    )
    return registry


def _capability_definition(capability_id: str = "greet-capability") -> CapabilityDefinition:
    return CapabilityDefinition(
        id=capability_id,
        name=capability_id,
        version="1.0.0",
        owner="platform-team",
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        supported_models=["mock-fast"],
        permissions=frozenset({Permission.CALL_EXTERNAL_API}),
    )


class TestEndToEndExecution:
    async def test_executes_via_the_mock_provider_and_returns_its_text(self) -> None:
        capability_registry = CapabilityRegistry()
        capability_registry.register(_capability_definition(), GreetCapability)
        executor = CapabilityExecutor(capability_registry)
        model_router, _provider = _model_router()
        context = CapabilityContext(
            project_id=None,
            organization_id=None,
            workflow_execution_id=None,
            invoked_by_user_id=None,
            model_router=model_router,
            prompt_registry=_prompt_registry(),
        )

        result = await executor.execute(
            "greet-capability",
            "1.0.0",
            context,
            {"name": "Ada"},
            granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
        )

        assert "Say hello to Ada." in result.output["text"]
        assert "mock-fast" in (result.reasoning_summary or "")

    async def test_build_output_can_be_overridden_for_a_different_schema(self) -> None:
        capability_registry = CapabilityRegistry()
        definition = _capability_definition("shout-capability")
        # Match the overridden build_output()'s actual shape.
        definition = definition.model_copy(
            update={
                "output_schema": {
                    "type": "object",
                    "properties": {"shout": {"type": "string"}},
                    "required": ["shout"],
                }
            }
        )
        capability_registry.register(definition, UppercaseGreetCapability)
        executor = CapabilityExecutor(capability_registry)
        model_router, _provider = _model_router()
        context = CapabilityContext(
            project_id=None,
            organization_id=None,
            workflow_execution_id=None,
            invoked_by_user_id=None,
            model_router=model_router,
            prompt_registry=_prompt_registry(),
        )

        result = await executor.execute(
            "shout-capability",
            "1.0.0",
            context,
            {"name": "Ada"},
            granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
        )

        assert result.output["shout"] == result.output["shout"].upper()
        assert "ADA" in result.output["shout"]

    async def test_a_provider_failure_genuinely_propagates_not_silently_swallowed(self) -> None:
        """PromptDrivenCapability calls ModelRouter.complete() with no
        retry_policy override, so it inherits the router's own default (0
        retries) — a failing provider must surface as a real exception all
        the way through the capability layer, not be hidden or faked into a
        fabricated success."""
        capability_registry = CapabilityRegistry()
        capability_registry.register(_capability_definition(), GreetCapability)
        executor = CapabilityExecutor(capability_registry)
        model_router, provider = _model_router(fail_first_n_calls=1)
        context = CapabilityContext(
            project_id=None,
            organization_id=None,
            workflow_execution_id=None,
            invoked_by_user_id=None,
            model_router=model_router,
            prompt_registry=_prompt_registry(),
        )

        with pytest.raises(AllModelsExhaustedError):
            await executor.execute(
                "greet-capability",
                "1.0.0",
                context,
                {"name": "Ada"},
                granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
            )

        assert provider.call_count == 1


class TestMissingContextDependencies:
    async def test_raises_when_context_has_no_model_router(self) -> None:
        capability_registry = CapabilityRegistry()
        capability_registry.register(_capability_definition(), GreetCapability)
        executor = CapabilityExecutor(capability_registry)
        context = CapabilityContext(
            project_id=None,
            organization_id=None,
            workflow_execution_id=None,
            invoked_by_user_id=None,
            prompt_registry=_prompt_registry(),
        )

        with pytest.raises(CapabilityExecutionError):
            await executor.execute(
                "greet-capability",
                "1.0.0",
                context,
                {"name": "Ada"},
                granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
            )

    async def test_raises_when_context_has_no_prompt_registry(self) -> None:
        capability_registry = CapabilityRegistry()
        capability_registry.register(_capability_definition(), GreetCapability)
        executor = CapabilityExecutor(capability_registry)
        model_router, _provider = _model_router()
        context = CapabilityContext(
            project_id=None,
            organization_id=None,
            workflow_execution_id=None,
            invoked_by_user_id=None,
            model_router=model_router,
        )

        with pytest.raises(CapabilityExecutionError):
            await executor.execute(
                "greet-capability",
                "1.0.0",
                context,
                {"name": "Ada"},
                granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
            )
