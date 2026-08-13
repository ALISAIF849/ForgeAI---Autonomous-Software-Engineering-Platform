from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.project import Project
from forgeai_memory_engine.events import EpisodicMemoryStore


async def _remember_at(
    store: EpisodicMemoryStore,
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    event_type: str,
    when: datetime,
    source: str = "test",
) -> uuid.UUID:
    """remember() then explicitly backdate created_at — Postgres' now() is
    stable within one transaction, so a tight loop of remember() calls
    without this would give several events an identical timestamp and make
    ordering assertions flaky rather than deterministic."""
    event = await store.remember(project_id=project_id, event_type=event_type, source=source)
    event.created_at = when
    await db.flush()
    return event.id


class TestRemember:
    async def test_remember_persists_the_event(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = EpisodicMemoryStore(db)

        event = await store.remember(
            project_id=project_id,
            event_type="workflow.completed",
            source="workflow_engine",
            payload={"execution_id": "abc"},
        )
        await db.commit()

        assert event.event_type == "workflow.completed"
        assert event.source == "workflow_engine"
        assert event.payload == {"execution_id": "abc"}

    async def test_remember_defaults_payload_to_an_empty_dict(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = EpisodicMemoryStore(db)

        event = await store.remember(project_id=project_id, event_type="note", source="user")
        await db.commit()

        assert event.payload == {}


class TestListForProject:
    async def test_returns_most_recent_first(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = EpisodicMemoryStore(db)
        now = datetime.now(UTC)
        await _remember_at(
            store, db, project_id, event_type="first", when=now - timedelta(minutes=2)
        )
        await _remember_at(
            store, db, project_id, event_type="second", when=now - timedelta(minutes=1)
        )
        await _remember_at(store, db, project_id, event_type="third", when=now)
        await db.commit()

        events = await store.list_for_project(project_id)

        assert [e.event_type for e in events] == ["third", "second", "first"]

    async def test_filters_by_event_type(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = EpisodicMemoryStore(db)
        now = datetime.now(UTC)
        await _remember_at(store, db, project_id, event_type="workflow.completed", when=now)
        await _remember_at(store, db, project_id, event_type="approval.granted", when=now)
        await db.commit()

        events = await store.list_for_project(project_id, event_type="approval.granted")

        assert [e.event_type for e in events] == ["approval.granted"]

    async def test_respects_limit(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = EpisodicMemoryStore(db)
        now = datetime.now(UTC)
        for i in range(5):
            await _remember_at(
                store, db, project_id, event_type=f"event-{i}", when=now - timedelta(minutes=i)
            )
        await db.commit()

        events = await store.list_for_project(project_id, limit=2)

        assert len(events) == 2

    async def test_before_cursor_excludes_events_at_or_after_it(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = EpisodicMemoryStore(db)
        now = datetime.now(UTC)
        await _remember_at(
            store, db, project_id, event_type="old", when=now - timedelta(minutes=10)
        )
        cursor_time = now - timedelta(minutes=5)
        await _remember_at(store, db, project_id, event_type="at_cursor", when=cursor_time)
        await _remember_at(store, db, project_id, event_type="new", when=now)
        await db.commit()

        events = await store.list_for_project(project_id, before=cursor_time)

        assert [e.event_type for e in events] == ["old"]

    async def test_only_returns_the_matching_projects_events(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, org_id, project_id = seeded_project
        # project_id is a real FK — a second event needs a second *real*
        # project to attach to, not an arbitrary UUID.
        other_project = Project(
            organization_id=org_id,
            name="Other Project",
            slug=f"other-{uuid.uuid4().hex[:8]}",
        )
        db.add(other_project)
        await db.flush()

        store = EpisodicMemoryStore(db)
        await store.remember(project_id=project_id, event_type="mine", source="test")
        await store.remember(project_id=other_project.id, event_type="not-mine", source="test")
        await db.commit()

        events = await store.list_for_project(project_id)

        assert [e.event_type for e in events] == ["mine"]
