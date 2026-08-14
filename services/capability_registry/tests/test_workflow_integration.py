"""The end-to-end proof that Sprint 2's Workflow Engine and Sprint 3's
Capability Registry / Model Router / Prompt Templates backfills are actually
wired together, not just individually tested: a real WorkflowDefinition,
persisted via a real WorkflowExecutor against a real Postgres schema, whose
one stage runs through CapabilityStageRunner into CapabilityExecutor into a
PromptDrivenCapability into a real ModelRouter and MockProvider — no mocks of
this package's own or workflow_engine's objects anywhere in the chain."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_capability_registry.ai_capability import PromptDrivenCapability
from forgeai_capability_registry.definition import CapabilityDefinition
from forgeai_capability_registry.executor import CapabilityExecutor
from forgeai_capability_registry.permissions import Permission
from forgeai_capability_registry.registry import CapabilityRegistry
from forgeai_capability_registry.stage_runner import CapabilityStageRunner
from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.provider import MockProvider
from forgeai_model_router.registry import ModelRegistry
from forgeai_model_router.router import ModelRouter
from forgeai_prompts.registry import PromptRegistry
from forgeai_prompts.template import PromptTemplate
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version

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


def _model_router() -> ModelRouter:
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
    return ModelRouter(registry, {"mock": MockProvider()})


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


def _capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDefinition(
            id="greet-capability",
            name="greet-capability",
            version="1.0.0",
            owner="platform-team",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            supported_models=["mock-fast"],
            permissions=frozenset({Permission.CALL_EXTERNAL_API}),
        ),
        GreetCapability,
    )
    return registry


class TestCapabilityBackedWorkflowStage:
    async def test_a_workflow_stage_actually_runs_a_capability_end_to_end(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project

        unique = uuid.uuid4().hex[:8]
        key = f"greet-workflow-{unique}"
        definition = WorkflowDefinition(
            key=key,
            name=key,
            version="1.0.0",
            stages=[
                StageDefinition(id="greet", name="Greet", capability="greet-capability@1.0.0"),
            ],
        )
        workflow = await get_or_create_workflow(db, key, key)
        version = await register_version(db, workflow, definition)
        await db.commit()

        stage_runner = CapabilityStageRunner(
            CapabilityExecutor(_capability_registry()),
            model_router=_model_router(),
            prompt_registry=_prompt_registry(),
            granted_permissions=frozenset({Permission.CALL_EXTERNAL_API}),
        )
        executor = WorkflowExecutor(db, stage_runner)

        execution = await executor.create_execution(
            version, definition, project_id=project_id, input={"name": "Ada"}
        )
        await db.commit()
        await executor.submit(execution.id)
        await db.commit()
        await executor.start(execution.id)
        await db.commit()

        completed = await executor.advance(execution.id)
        await db.commit()

        assert completed.status == WorkflowStatus.COMPLETED
        pairs = await executor.get_stage_executions(execution.id)
        greet_execution = next(se for se, stage_key in pairs if stage_key == "greet")
        assert greet_execution.status == StageStatus.COMPLETED
        assert greet_execution.output is not None
        assert "Say hello to Ada." in greet_execution.output["text"]

    async def test_a_stage_referencing_an_unregistered_capability_fails_the_workflow(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project

        unique = uuid.uuid4().hex[:8]
        key = f"missing-capability-workflow-{unique}"
        definition = WorkflowDefinition(
            key=key,
            name=key,
            version="1.0.0",
            stages=[
                StageDefinition(id="ghost", name="Ghost", capability="does-not-exist@9.9.9"),
            ],
        )
        workflow = await get_or_create_workflow(db, key, key)
        version = await register_version(db, workflow, definition)
        await db.commit()

        stage_runner = CapabilityStageRunner(CapabilityExecutor(_capability_registry()))
        executor = WorkflowExecutor(db, stage_runner)

        execution = await executor.create_execution(
            version, definition, project_id=project_id, input={"name": "Ada"}
        )
        await db.commit()
        await executor.submit(execution.id)
        await db.commit()
        await executor.start(execution.id)
        await db.commit()

        failed = await executor.advance(execution.id)
        await db.commit()

        assert failed.status == WorkflowStatus.FAILED
