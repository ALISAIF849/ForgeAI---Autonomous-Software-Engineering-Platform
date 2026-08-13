from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_memory_engine.engine import MemoryEngine


class TestMemoryEngineFacade:
    async def test_decisions_and_events_are_backed_by_the_same_session(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        memory = MemoryEngine(db)

        decision = await memory.decisions.record(
            project_id=project_id,
            title="Adopt trunk-based development",
            context="Long-lived branches were causing painful merges.",
            decision="Adopt trunk-based development with short-lived feature branches.",
        )
        event = await memory.events.remember(
            project_id=project_id,
            event_type="decision.recorded",
            source="memory_engine",
            payload={"decision_id": str(decision.id)},
        )
        await db.commit()

        fetched_decision = await memory.decisions.get(decision.id)
        events = await memory.events.list_for_project(project_id)

        assert fetched_decision.title == "Adopt trunk-based development"
        assert events[0].id == event.id
