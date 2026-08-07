"""Integration tests for WorkflowQueue (2.3) against a real Postgres schema —
including a genuine concurrency test proving `SELECT ... FOR UPDATE SKIP
LOCKED` prevents two concurrent claimers from claiming the same entry, not
just that the SQL looks right.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.queue import WorkflowQueue
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import FakeStageRunner


async def _make_execution(db: AsyncSession, project_id: uuid.UUID, key_prefix: str) -> uuid.UUID:
    """A real WorkflowExecution row — workflow_queue.workflow_execution_id is a
    real FK, so a queue entry needs one to point at."""
    unique = uuid.uuid4().hex[:8]
    key = f"{key_prefix}-{unique}"
    definition = WorkflowDefinition(
        key=key, name=key, version="1.0.0", stages=[StageDefinition(id="a", name="A")]
    )
    workflow = await get_or_create_workflow(db, key, key)
    version = await register_version(db, workflow, definition)
    executor = WorkflowExecutor(db, FakeStageRunner())
    execution = await executor.create_execution(
        version, definition, project_id=project_id, input={}
    )
    await db.flush()
    return execution.id


class TestOrdering:
    async def test_claim_next_prefers_highest_priority(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        queue = WorkflowQueue(db)
        low_id = await _make_execution(db, project_id, "low")
        high_id = await _make_execution(db, project_id, "high")
        await queue.enqueue(low_id, priority=1)
        await queue.enqueue(high_id, priority=10)
        await db.commit()

        claimed = await queue.claim_next("worker-1")
        await db.commit()

        assert claimed is not None
        assert claimed.workflow_execution_id == high_id

    async def test_claim_next_is_fifo_within_the_same_priority(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        queue = WorkflowQueue(db)
        first_id = await _make_execution(db, project_id, "first")
        await queue.enqueue(first_id, priority=0)
        await db.commit()
        second_id = await _make_execution(db, project_id, "second")
        await queue.enqueue(second_id, priority=0)
        await db.commit()

        claimed = await queue.claim_next("worker-1")
        await db.commit()

        assert claimed is not None
        assert claimed.workflow_execution_id == first_id

    async def test_claim_next_skips_entries_scheduled_for_the_future(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        from datetime import UTC, datetime, timedelta

        _user_id, _org_id, project_id = seeded_project
        queue = WorkflowQueue(db)
        future_id = await _make_execution(db, project_id, "future")
        await queue.enqueue(
            future_id, priority=100, scheduled_for=datetime.now(UTC) + timedelta(hours=1)
        )
        ready_id = await _make_execution(db, project_id, "ready")
        await queue.enqueue(ready_id, priority=0)
        await db.commit()

        claimed = await queue.claim_next("worker-1")
        await db.commit()

        assert claimed is not None
        assert claimed.workflow_execution_id == ready_id

    async def test_queue_depth_counts_only_queued_entries(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        queue = WorkflowQueue(db)
        exec_id = await _make_execution(db, project_id, "depth")
        entry = await queue.enqueue(exec_id)
        await db.commit()

        before = await queue.queue_depth()
        await queue.mark_done(entry.id)
        await db.commit()
        after = await queue.queue_depth()

        assert after == before - 1


class TestConcurrentClaiming:
    async def test_two_concurrent_claimers_never_claim_the_same_entry(
        self,
        database_url: str,
        db: AsyncSession,
        seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        """The real point of `FOR UPDATE SKIP LOCKED`: two workers racing to
        claim from a two-entry queue must walk away with one entry each, never
        both grabbing the same one. Uses two independent sessions/engines —
        genuinely concurrent transactions, not one session pretending to be
        two."""
        _user_id, _org_id, project_id = seeded_project
        setup_queue = WorkflowQueue(db)
        entry_a_execution = await _make_execution(db, project_id, "race-a")
        entry_b_execution = await _make_execution(db, project_id, "race-b")
        await setup_queue.enqueue(entry_a_execution, priority=0)
        await setup_queue.enqueue(entry_b_execution, priority=0)
        await db.commit()

        async def _claim(worker_id: str) -> uuid.UUID | None:
            engine = create_async_engine(database_url, poolclass=NullPool)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                queue = WorkflowQueue(session)
                entry = await queue.claim_next(worker_id)
                if entry is None:
                    await session.commit()
                    await engine.dispose()
                    return None
                execution_id = entry.workflow_execution_id
                await session.commit()
            await engine.dispose()
            return execution_id

        results = await asyncio.gather(_claim("worker-a"), _claim("worker-b"))

        claimed_executions = [r for r in results if r is not None]
        assert len(claimed_executions) == 2
        assert set(claimed_executions) == {entry_a_execution, entry_b_execution}
        assert claimed_executions[0] != claimed_executions[1]
