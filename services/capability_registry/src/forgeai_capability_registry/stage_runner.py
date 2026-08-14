"""Bridges forgeai_workflow_engine's StageRunner plug point to this
package's CapabilityExecutor — the piece that lets a real WorkflowExecutor
tick actually run a real capability, replacing
forgeai_workflow_engine.runner.UnconfiguredStageRunner in production. Lives
here (not in workflow_engine): per that package's own stated principle it
must stay domain-agnostic with no AI/capability dependency, so the
one-directional adapter dependency goes this way instead.

StageDefinition.capability is an opaque string workflow_engine never
interprets. This module owns the one convention that gives it meaning here:
"capability_id@version" (e.g. "summarize-text@1.0.0") — pinning a specific
version rather than always resolving "latest", consistent with this
codebase's existing versioning stance (WorkflowVersion, PromptTemplate) that
an in-flight execution keeps running against the version it started on.
"""

from __future__ import annotations

from forgeai_capability_registry.exceptions import CapabilityRegistryError
from forgeai_capability_registry.executor import CapabilityExecutor
from forgeai_capability_registry.permissions import Permission
from forgeai_capability_registry.sdk import CapabilityContext
from forgeai_model_router.router import ModelRouter
from forgeai_prompts.registry import PromptRegistry
from forgeai_workflow_engine.definition import StageDefinition
from forgeai_workflow_engine.runner import StageRunContext, StageRunner, StageRunResult


class InvalidCapabilityReferenceError(Exception):
    """`stage.capability` isn't in the 'capability_id@version' shape this
    runner requires — raised as a normal Python exception (not a
    CapabilityRegistryError: nothing about it involves the registry) and
    caught inside run() itself, since StageRunner.run() must return a failed
    StageRunResult rather than propagate."""

    def __init__(self, capability_ref: str | None) -> None:
        self.capability_ref = capability_ref
        super().__init__(
            f"Stage capability reference {capability_ref!r} is not in the required "
            "'capability_id@version' shape."
        )


def parse_capability_reference(capability: str | None) -> tuple[str, str]:
    if not capability or "@" not in capability:
        raise InvalidCapabilityReferenceError(capability)
    capability_id, _, version = capability.partition("@")
    if not capability_id or not version:
        raise InvalidCapabilityReferenceError(capability)
    return capability_id, version


class CapabilityStageRunner(StageRunner):
    """The real StageRunner: `model_router`/`prompt_registry` are attached to
    every CapabilityContext this runner builds (a capability that doesn't
    need them simply doesn't read them), and `granted_permissions` is a
    single static grant set applied to every capability this runner
    executes — a deliberately simple starting policy, not a per-capability or
    per-org permission model, which doesn't exist yet."""

    def __init__(
        self,
        executor: CapabilityExecutor,
        *,
        model_router: ModelRouter | None = None,
        prompt_registry: PromptRegistry | None = None,
        granted_permissions: frozenset[Permission] = frozenset(),
    ) -> None:
        self._executor = executor
        self._model_router = model_router
        self._prompt_registry = prompt_registry
        self._granted_permissions = granted_permissions

    async def run(self, stage: StageDefinition, context: StageRunContext) -> StageRunResult:
        try:
            capability_id, version = parse_capability_reference(stage.capability)
        except InvalidCapabilityReferenceError as exc:
            return StageRunResult(success=False, error=str(exc))

        capability_context = CapabilityContext(
            project_id=context.project_id,
            organization_id=None,
            workflow_execution_id=context.workflow_execution_id,
            invoked_by_user_id=None,
            model_router=self._model_router,
            prompt_registry=self._prompt_registry,
        )

        try:
            result = await self._executor.execute(
                capability_id,
                version,
                capability_context,
                context.stage_input,
                granted_permissions=self._granted_permissions,
            )
        except CapabilityRegistryError as exc:
            return StageRunResult(success=False, error=str(exc))
        # Anything beyond a CapabilityRegistryError (a model provider
        # exhausting its fallback chain, a bug in a capability's own
        # execute()) is still this runner's job to convert into a failed
        # StageRunResult rather than let escape — the Executor's advance()
        # tick has no handling for a StageRunner that raises, and a stage
        # genuinely failing must go through the normal retry/failure path,
        # not crash the tick.
        except Exception as exc:
            return StageRunResult(success=False, error=f"{type(exc).__name__}: {exc}")

        return StageRunResult(success=True, output=result.output)
