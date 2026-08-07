"""Integration tests for resolve_approval() (2.5) against a real Postgres
schema — approving/rejecting/requesting-changes on a real WorkflowApproval
row created by advance()'s approval gate, and confirming the stage actually
runs (or the workflow actually fails, rollback included) as a consequence."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_stage import WorkflowStage
from forgeai_core.models.workflow_stage_execution import WorkflowStageExecution
from forgeai_core.workflow_enums import ApprovalDecision, StageStatus, WorkflowStatus
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    UnsupportedApprovalDecisionError,
)
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import FakeStageRunner


async def _create_started_execution(
    db: AsyncSession,
    executor: WorkflowExecutor,
    key: str,
    stages: list[StageDefinition],
    project_id: uuid.UUID,
) -> uuid.UUID:
    unique = uuid.uuid4().hex[:8]
    full_key = f"{key}-{unique}"
    definition = WorkflowDefinition(key=full_key, name=full_key, version="1.0.0", stages=stages)
    workflow = await get_or_create_workflow(db, full_key, full_key)
    version = await register_version(db, workflow, definition)
    execution = await executor.create_execution(
        version, definition, project_id=project_id, input={}
    )
    await executor.submit(execution.id)
    await executor.start(execution.id)
    await db.commit()
    return execution.id


async def _stage_execution(
    db: AsyncSession, execution_id: uuid.UUID, stage_key: str
) -> WorkflowStageExecution:
    result = await db.execute(
        select(WorkflowStageExecution)
        .join(WorkflowStage, WorkflowStageExecution.workflow_stage_id == WorkflowStage.id)
        .where(
            WorkflowStageExecution.workflow_execution_id == execution_id,
            WorkflowStage.stage_key == stage_key,
        )
    )
    return result.scalar_one()


async def _pending_approval(db: AsyncSession, execution_id: uuid.UUID) -> WorkflowApproval:
    result = await db.execute(
        select(WorkflowApproval).where(
            WorkflowApproval.workflow_execution_id == execution_id,
            WorkflowApproval.decision.is_(None),
        )
    )
    return result.scalar_one()


class TestApprove:
    async def test_approve_resumes_and_runs_the_stage_to_completion(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "approve",
            [StageDefinition(id="a", name="A", requires_approval=True)],
            project_id,
        )

        await executor.advance(execution_id)
        await db.commit()
        approval = await _pending_approval(db, execution_id)
        assert runner.run_calls == []  # never ran before approval

        resolved = await executor.resolve_approval(
            approval.id, ApprovalDecision.APPROVE, decided_by=None, comment="looks good"
        )
        await db.commit()

        assert resolved.decision == ApprovalDecision.APPROVE
        assert resolved.decided_at is not None
        assert resolved.comment == "looks good"
        assert runner.run_calls == ["a"]

        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.COMPLETED
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.COMPLETED

    async def test_approve_on_a_non_terminal_stage_leaves_workflow_running(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "approve-then-more",
            [
                StageDefinition(id="a", name="A", requires_approval=True),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
            project_id,
        )

        await executor.advance(execution_id)
        await db.commit()
        approval = await _pending_approval(db, execution_id)

        await executor.resolve_approval(approval.id, ApprovalDecision.APPROVE)
        await db.commit()

        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.RUNNING
        stage_b = await _stage_execution(db, execution_id, "b")
        assert stage_b.status == StageStatus.PENDING

        # A subsequent advance() picks up "b" normally.
        final = await executor.advance(execution_id)
        await db.commit()
        assert final.status == WorkflowStatus.COMPLETED
        assert runner.run_calls == ["a", "b"]

    async def test_request_changes_reruns_the_stage(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "request-changes",
            [StageDefinition(id="a", name="A", requires_approval=True)],
            project_id,
        )

        await executor.advance(execution_id)
        await db.commit()
        approval = await _pending_approval(db, execution_id)

        resolved = await executor.resolve_approval(approval.id, ApprovalDecision.REQUEST_CHANGES)
        await db.commit()

        assert resolved.decision == ApprovalDecision.REQUEST_CHANGES
        assert runner.run_calls == ["a"]
        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.COMPLETED


class TestReject:
    async def test_reject_fails_the_workflow_and_marks_the_stage_failed(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "reject",
            [StageDefinition(id="a", name="A", requires_approval=True)],
            project_id,
        )

        await executor.advance(execution_id)
        await db.commit()
        approval = await _pending_approval(db, execution_id)

        resolved = await executor.resolve_approval(
            approval.id, ApprovalDecision.REJECT, comment="not ready"
        )
        await db.commit()

        assert resolved.decision == ApprovalDecision.REJECT
        assert runner.run_calls == []  # rejected — never ran

        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.FAILED
        assert execution.error is not None and "reject" in execution.error
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.FAILED

    async def test_reject_rolls_back_already_completed_stages(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "reject-rollback",
            [
                StageDefinition(id="a", name="A"),
                StageDefinition(id="b", name="B", depends_on=["a"], requires_approval=True),
            ],
            project_id,
        )

        await executor.advance(execution_id)  # completes "a"
        await db.commit()
        await executor.advance(execution_id)  # "b" is now ready and gets gated
        await db.commit()
        approval = await _pending_approval(db, execution_id)

        await executor.resolve_approval(approval.id, ApprovalDecision.REJECT)
        await db.commit()

        assert runner.rollback_calls == ["a"]


class TestErrors:
    async def test_resolving_a_nonexistent_approval_raises(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        executor = WorkflowExecutor(db, FakeStageRunner())
        with pytest.raises(ApprovalNotFoundError):
            await executor.resolve_approval(uuid.uuid4(), ApprovalDecision.APPROVE)

    async def test_resolving_an_already_decided_approval_raises(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FakeStageRunner())
        execution_id = await _create_started_execution(
            db,
            executor,
            "double-resolve",
            [StageDefinition(id="a", name="A", requires_approval=True)],
            project_id,
        )
        await executor.advance(execution_id)
        await db.commit()
        approval = await _pending_approval(db, execution_id)
        await executor.resolve_approval(approval.id, ApprovalDecision.APPROVE)
        await db.commit()

        with pytest.raises(ApprovalAlreadyDecidedError):
            await executor.resolve_approval(approval.id, ApprovalDecision.APPROVE)

    async def test_escalate_decision_is_rejected_and_leaves_approval_unresolved(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FakeStageRunner())
        execution_id = await _create_started_execution(
            db,
            executor,
            "escalate-unsupported",
            [StageDefinition(id="a", name="A", requires_approval=True)],
            project_id,
        )
        await executor.advance(execution_id)
        await db.commit()
        approval = await _pending_approval(db, execution_id)

        with pytest.raises(UnsupportedApprovalDecisionError):
            await executor.resolve_approval(approval.id, ApprovalDecision.ESCALATE)

        await db.refresh(approval)
        assert approval.decision is None
