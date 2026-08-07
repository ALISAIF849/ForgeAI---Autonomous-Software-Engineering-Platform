"""Proves the workflow persistence models (sub-sprint 2.2) actually round-trip
through real Postgres — FK chain, JSONB columns, and enum columns — not just
that the tables exist (test_migrations.py already covers that). No
repository layer or API exists yet for these models (that's sub-sprint 2.3's
job, once the Executor needs to call it); this talks to the DB directly.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.organization import Organization
from forgeai_core.models.project import Project
from forgeai_core.models.user import User
from forgeai_core.models.workflow import Workflow
from forgeai_core.models.workflow_execution import WorkflowExecution
from forgeai_core.models.workflow_stage import WorkflowStage
from forgeai_core.models.workflow_stage_execution import WorkflowStageExecution
from forgeai_core.models.workflow_version import WorkflowVersion
from forgeai_core.workflow_enums import StageStatus, WorkflowStatus


async def _session(migrated_schema: None) -> AsyncSession:
    from forgeai_api.db.session import get_session_factory

    return get_session_factory()()


async def test_workflow_definition_chain_round_trips_through_real_postgres(
    migrated_schema: None,
) -> None:
    async with await _session(migrated_schema) as db:
        user = User(email="pm@example.com", username="pm", hashed_password="x")
        db.add(user)
        await db.flush()

        org = Organization(name="Acme", slug="acme-persistence-test", created_by=user.id)
        db.add(org)
        await db.flush()

        project = Project(organization_id=org.id, name="Demo", slug="demo", owner_id=user.id)
        db.add(project)
        await db.flush()

        workflow = Workflow(key="example-workflow", name="Example Workflow", created_by=user.id)
        db.add(workflow)
        await db.flush()

        version = WorkflowVersion(
            workflow_id=workflow.id,
            version="1.0.0",
            graph_spec={"key": "example-workflow", "version": "1.0.0", "stages": []},
        )
        db.add(version)
        await db.flush()

        stage = WorkflowStage(
            workflow_version_id=version.id,
            stage_key="plan",
            name="Plan",
            sequence_index=0,
            depends_on=[],
        )
        db.add(stage)
        await db.flush()

        execution = WorkflowExecution(
            workflow_id=workflow.id,
            workflow_version_id=version.id,
            project_id=project.id,
            status=WorkflowStatus.RUNNING,
            input={"goal": "test"},
            started_by=user.id,
        )
        db.add(execution)
        await db.flush()

        stage_execution = WorkflowStageExecution(
            workflow_execution_id=execution.id,
            workflow_stage_id=stage.id,
            status=StageStatus.RUNNING,
            input={"goal": "test"},
        )
        db.add(stage_execution)
        await db.commit()

        execution_id = execution.id

    async with await _session(migrated_schema) as db:
        result = await db.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        )
        reloaded = result.scalar_one()

        assert reloaded.status == WorkflowStatus.RUNNING
        assert reloaded.input == {"goal": "test"}

        stage_result = await db.execute(
            select(WorkflowStageExecution).where(
                WorkflowStageExecution.workflow_execution_id == execution_id
            )
        )
        reloaded_stage = stage_result.scalar_one()
        assert reloaded_stage.status == StageStatus.RUNNING
        assert reloaded_stage.attempt_number == 1


async def test_workflow_version_uniqueness_is_enforced_by_the_database(
    migrated_schema: None,
) -> None:
    """Confirms the uq_workflow_version constraint is real, not just declared
    in the ORM and never actually created by the migration."""
    from sqlalchemy.exc import IntegrityError

    async with await _session(migrated_schema) as db:
        workflow = Workflow(key="dup-version-test", name="Dup Version Test")
        db.add(workflow)
        await db.flush()

        db.add(WorkflowVersion(workflow_id=workflow.id, version="1.0.0", graph_spec={}))
        await db.commit()

    async with await _session(migrated_schema) as db:
        db.add(WorkflowVersion(workflow_id=workflow.id, version="1.0.0", graph_spec={}))
        try:
            await db.commit()
            raise AssertionError("Expected a duplicate (workflow_id, version) to be rejected.")
        except IntegrityError:
            await db.rollback()
