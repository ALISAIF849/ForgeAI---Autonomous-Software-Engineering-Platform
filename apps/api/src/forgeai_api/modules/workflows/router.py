import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_api.db.session import get_db
from forgeai_api.dependencies.auth import get_current_user
from forgeai_api.dependencies.rbac import require_project_role
from forgeai_api.modules.workflows.dependencies import get_stage_runner
from forgeai_api.modules.workflows.schemas import (
    ApprovalPublic,
    CreateExecutionRequest,
    ResolveApprovalRequest,
    WorkflowExecutionDetail,
    WorkflowVersionDetail,
    WorkflowVersionPublic,
)
from forgeai_api.modules.workflows.service import WorkflowService
from forgeai_core.models.enums import OrgRole
from forgeai_core.models.organization_member import OrganizationMember
from forgeai_core.models.user import User
from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_version import WorkflowVersion
from forgeai_workflow_engine.definition import WorkflowDefinition
from forgeai_workflow_engine.runner import StageRunner

router = APIRouter(tags=["workflows"])


def _service(db: AsyncSession, runner: StageRunner) -> WorkflowService:
    return WorkflowService(db, runner)


# ---------------------------------------------------------------- definitions


@router.post(
    "/workflow-definitions",
    response_model=WorkflowVersionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def register_workflow_definition(
    definition: WorkflowDefinition,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
) -> WorkflowVersion:
    """Definitions are global, not project-scoped (a `workflows.key` is unique
    across the whole system) — any authenticated user can register a new one.
    Validation (cycles, unknown dependencies, version format) already
    happened as part of parsing `definition` itself; FastAPI/Pydantic rejects
    a malformed body with 422 before this handler ever runs."""
    return await _service(db, runner).register_definition(definition, created_by=current_user.id)


@router.get("/workflow-definitions/{key}/versions", response_model=list[WorkflowVersionPublic])
async def list_workflow_versions(
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
) -> list[WorkflowVersion]:
    del current_user  # authentication required, no further authorization for a global read
    return await _service(db, runner).list_versions(key)


@router.get("/workflow-definitions/{key}/versions/{version}", response_model=WorkflowVersionDetail)
async def get_workflow_version(
    key: str,
    version: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
) -> WorkflowVersion:
    del current_user
    return await _service(db, runner).get_version_detail(key, version)


# ----------------------------------------------------------------- executions


@router.post(
    "/projects/{project_id}/workflow-executions",
    response_model=WorkflowExecutionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_execution(
    project_id: uuid.UUID,
    request: CreateExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.DEVELOPER)),
) -> WorkflowExecutionDetail:
    return await _service(db, runner).create_and_start_execution(
        request, project_id=project_id, started_by=current_user.id
    )


@router.get(
    "/projects/{project_id}/workflow-executions/{execution_id}",
    response_model=WorkflowExecutionDetail,
)
async def get_workflow_execution(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.VIEWER)),
) -> WorkflowExecutionDetail:
    return await _service(db, runner).get_execution_detail(execution_id, project_id=project_id)


@router.post(
    "/projects/{project_id}/workflow-executions/{execution_id}/advance",
    response_model=WorkflowExecutionDetail,
)
async def advance_workflow_execution(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.DEVELOPER)),
) -> WorkflowExecutionDetail:
    """Manual tick — until a real worker loop exists to call advance() on a
    schedule (Sprint 2's still-pending worker-process piece), this is how a
    client drives a workflow past its first, automatically-run tick."""
    return await _service(db, runner).advance(execution_id, project_id=project_id)


@router.post(
    "/projects/{project_id}/workflow-executions/{execution_id}/pause",
    response_model=WorkflowExecutionDetail,
)
async def pause_workflow_execution(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.DEVELOPER)),
) -> WorkflowExecutionDetail:
    return await _service(db, runner).pause(execution_id, project_id=project_id)


@router.post(
    "/projects/{project_id}/workflow-executions/{execution_id}/resume",
    response_model=WorkflowExecutionDetail,
)
async def resume_workflow_execution(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.DEVELOPER)),
) -> WorkflowExecutionDetail:
    return await _service(db, runner).resume(execution_id, project_id=project_id)


@router.post(
    "/projects/{project_id}/workflow-executions/{execution_id}/cancel",
    response_model=WorkflowExecutionDetail,
)
async def cancel_workflow_execution(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.DEVELOPER)),
) -> WorkflowExecutionDetail:
    return await _service(db, runner).cancel(execution_id, project_id=project_id)


@router.post(
    "/projects/{project_id}/workflow-executions/{execution_id}/stages/{stage_execution_id}/skip",
    response_model=WorkflowExecutionDetail,
)
async def skip_workflow_stage(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    stage_execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.DEVELOPER)),
) -> WorkflowExecutionDetail:
    return await _service(db, runner).skip_stage(
        execution_id, stage_execution_id, project_id=project_id
    )


# ------------------------------------------------------------------ approvals


@router.get(
    "/projects/{project_id}/workflow-executions/{execution_id}/approvals",
    response_model=list[ApprovalPublic],
)
async def list_workflow_approvals(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.VIEWER)),
) -> list[WorkflowApproval]:
    return await _service(db, runner).list_approvals(execution_id, project_id=project_id)


@router.post(
    "/projects/{project_id}/workflow-executions/{execution_id}/approvals/{approval_id}/resolve",
    response_model=WorkflowExecutionDetail,
)
async def resolve_workflow_approval(
    project_id: uuid.UUID,
    execution_id: uuid.UUID,
    approval_id: uuid.UUID,
    request: ResolveApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runner: StageRunner = Depends(get_stage_runner),
    _member: OrganizationMember = Depends(require_project_role(OrgRole.DEVELOPER)),
) -> WorkflowExecutionDetail:
    return await _service(db, runner).resolve_approval(
        execution_id, approval_id, request, project_id=project_id, decided_by=current_user.id
    )
