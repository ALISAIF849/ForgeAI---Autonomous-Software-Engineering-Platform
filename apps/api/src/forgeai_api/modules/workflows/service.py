"""Orchestrates WorkflowExecutor (forgeai_workflow_engine) for the HTTP layer.

Every mutating method re-validates that the execution/stage/approval named in
the URL actually belongs to the project also named in the URL — the Executor
itself is deliberately project-agnostic (it only knows a `project_id` value
to stamp on records, not an ownership rule), so "does this caller's project
actually own this execution" is an authorization concern this layer owns, not
the Executor's. Without it, a member of Project A who merely knows another
project's execution_id could act on it via Project A's URL.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_api.modules.workflows.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    InvalidWorkflowTransitionError,
    StageExecutionNotFoundError,
    StageNotSkippableError,
    UnsupportedApprovalDecisionError,
    WorkflowExecutionNotFoundError,
    WorkflowVersionAlreadyRegisteredError,
    WorkflowVersionNotFoundError,
)
from forgeai_api.modules.workflows.repository import WorkflowRepository
from forgeai_api.modules.workflows.schemas import (
    CreateExecutionRequest,
    ResolveApprovalRequest,
    StageExecutionPublic,
    WorkflowExecutionDetail,
)
from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_execution import WorkflowExecution
from forgeai_core.models.workflow_version import WorkflowVersion
from forgeai_workflow_engine.definition import WorkflowDefinition
from forgeai_workflow_engine.exceptions import (
    ApprovalAlreadyDecidedError as EngineApprovalAlreadyDecidedError,
)
from forgeai_workflow_engine.exceptions import (
    DefinitionAlreadyRegisteredError,
)
from forgeai_workflow_engine.exceptions import (
    ExecutionNotFoundError as EngineExecutionNotFoundError,
)
from forgeai_workflow_engine.exceptions import (
    InvalidTransitionError as EngineInvalidTransitionError,
)
from forgeai_workflow_engine.exceptions import (
    StageNotSkippableError as EngineStageNotSkippableError,
)
from forgeai_workflow_engine.exceptions import (
    UnsupportedApprovalDecisionError as EngineUnsupportedApprovalDecisionError,
)
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.loader import DefinitionLoader
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import StageRunner


class WorkflowService:
    def __init__(self, db: AsyncSession, runner: StageRunner) -> None:
        self._db = db
        self._repo = WorkflowRepository(db)
        self._executor = WorkflowExecutor(db, runner)

    # ------------------------------------------------------------ definitions

    async def register_definition(
        self, definition: WorkflowDefinition, *, created_by: uuid.UUID
    ) -> WorkflowVersion:
        try:
            workflow = await get_or_create_workflow(
                self._db, definition.key, definition.name, created_by=created_by
            )
            version = await register_version(self._db, workflow, definition)
        except DefinitionAlreadyRegisteredError as exc:
            raise WorkflowVersionAlreadyRegisteredError(str(exc)) from exc
        await self._db.commit()
        return version

    async def list_versions(self, key: str) -> list[WorkflowVersion]:
        return await self._repo.list_versions(key)

    async def get_version_detail(self, key: str, version: str) -> WorkflowVersion:
        row = await self._repo.get_version(key, version)
        if row is None:
            raise WorkflowVersionNotFoundError
        return row

    # ------------------------------------------------------------- executions

    async def create_and_start_execution(
        self,
        request: CreateExecutionRequest,
        *,
        project_id: uuid.UUID,
        started_by: uuid.UUID,
    ) -> WorkflowExecutionDetail:
        version = await self._repo.get_version(request.workflow_key, request.version)
        if version is None:
            raise WorkflowVersionNotFoundError
        definition = DefinitionLoader.load_from_dict(version.graph_spec)

        execution = await self._executor.create_execution(
            version, definition, project_id=project_id, input=request.input, started_by=started_by
        )
        await self._executor.submit(execution.id)
        await self._executor.start(execution.id)
        # One tick for free: a client asking to run a workflow expects its
        # first ready stage(s) to actually start, not to need a second manual
        # advance() call before anything visibly happens.
        await self._executor.advance(execution.id)
        await self._db.commit()
        return await self._build_detail(execution.id)

    async def get_execution_detail(
        self, execution_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> WorkflowExecutionDetail:
        await self._validated_execution(execution_id, project_id)
        return await self._build_detail(execution_id)

    async def advance(
        self, execution_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> WorkflowExecutionDetail:
        await self._validated_execution(execution_id, project_id)
        await self._executor.advance(execution_id)
        await self._db.commit()
        return await self._build_detail(execution_id)

    async def pause(
        self, execution_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> WorkflowExecutionDetail:
        await self._validated_execution(execution_id, project_id)
        try:
            await self._executor.pause(execution_id)
        except EngineInvalidTransitionError as exc:
            raise InvalidWorkflowTransitionError(str(exc)) from exc
        await self._db.commit()
        return await self._build_detail(execution_id)

    async def resume(
        self, execution_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> WorkflowExecutionDetail:
        await self._validated_execution(execution_id, project_id)
        try:
            await self._executor.resume(execution_id)
        except EngineInvalidTransitionError as exc:
            raise InvalidWorkflowTransitionError(str(exc)) from exc
        await self._db.commit()
        return await self._build_detail(execution_id)

    async def cancel(
        self, execution_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> WorkflowExecutionDetail:
        await self._validated_execution(execution_id, project_id)
        try:
            await self._executor.cancel(execution_id)
        except EngineInvalidTransitionError as exc:
            raise InvalidWorkflowTransitionError(str(exc)) from exc
        await self._db.commit()
        return await self._build_detail(execution_id)

    async def skip_stage(
        self,
        execution_id: uuid.UUID,
        stage_execution_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
    ) -> WorkflowExecutionDetail:
        await self._validated_execution(execution_id, project_id)
        await self._validated_stage_execution_id(execution_id, stage_execution_id)
        try:
            await self._executor.skip_stage(stage_execution_id)
        except EngineStageNotSkippableError as exc:
            raise StageNotSkippableError from exc
        await self._db.commit()
        return await self._build_detail(execution_id)

    # -------------------------------------------------------------- approvals

    async def list_approvals(
        self, execution_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> list[WorkflowApproval]:
        await self._validated_execution(execution_id, project_id)
        return await self._repo.list_approvals(execution_id)

    async def resolve_approval(
        self,
        execution_id: uuid.UUID,
        approval_id: uuid.UUID,
        request: ResolveApprovalRequest,
        *,
        project_id: uuid.UUID,
        decided_by: uuid.UUID,
    ) -> WorkflowExecutionDetail:
        await self._validated_execution(execution_id, project_id)
        await self._validated_approval_id(execution_id, approval_id)
        try:
            await self._executor.resolve_approval(
                approval_id, request.decision, decided_by=decided_by, comment=request.comment
            )
        except EngineApprovalAlreadyDecidedError as exc:
            raise ApprovalAlreadyDecidedError from exc
        except EngineUnsupportedApprovalDecisionError as exc:
            raise UnsupportedApprovalDecisionError(str(exc)) from exc
        await self._db.commit()
        return await self._build_detail(execution_id)

    # ------------------------------------------------------------------ internals

    async def _validated_execution(
        self, execution_id: uuid.UUID, project_id: uuid.UUID
    ) -> WorkflowExecution:
        try:
            execution = await self._executor.get_execution(execution_id)
        except EngineExecutionNotFoundError as exc:
            raise WorkflowExecutionNotFoundError from exc
        if execution.project_id != project_id:
            # Same reasoning as require_project_role: don't distinguish
            # "doesn't exist" from "exists but isn't yours" in the response.
            raise WorkflowExecutionNotFoundError
        return execution

    async def _validated_stage_execution_id(
        self, execution_id: uuid.UUID, stage_execution_id: uuid.UUID
    ) -> None:
        pairs = await self._executor.get_stage_executions(execution_id)
        if not any(stage_execution.id == stage_execution_id for stage_execution, _key in pairs):
            raise StageExecutionNotFoundError

    async def _validated_approval_id(
        self, execution_id: uuid.UUID, approval_id: uuid.UUID
    ) -> WorkflowApproval:
        approval = await self._db.get(WorkflowApproval, approval_id)
        if approval is None or approval.workflow_execution_id != execution_id:
            raise ApprovalNotFoundError
        return approval

    async def _build_detail(self, execution_id: uuid.UUID) -> WorkflowExecutionDetail:
        execution = await self._executor.get_execution(execution_id)
        pairs = await self._executor.get_stage_executions(execution_id)
        stages = [
            StageExecutionPublic(
                id=stage_execution.id,
                stage_key=stage_key,
                status=stage_execution.status,
                attempt_number=stage_execution.attempt_number,
                output=stage_execution.output,
                error=stage_execution.error,
                started_at=stage_execution.started_at,
                completed_at=stage_execution.completed_at,
            )
            for stage_execution, stage_key in pairs
        ]
        return WorkflowExecutionDetail(
            id=execution.id,
            workflow_id=execution.workflow_id,
            workflow_version_id=execution.workflow_version_id,
            project_id=execution.project_id,
            status=execution.status,
            input=execution.input,
            error=execution.error,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            created_at=execution.created_at,
            stages=stages,
        )
