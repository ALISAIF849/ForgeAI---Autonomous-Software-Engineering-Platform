from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.enums import ArchitectureDecisionStatus
from forgeai_memory_engine.decisions import ArchitectureDecisionStore
from forgeai_memory_engine.exceptions import (
    ArchitectureDecisionNotFoundError,
    DecisionNotDecidableError,
    DecisionNotSupersedableError,
)


async def _record(
    store: ArchitectureDecisionStore, project_id: uuid.UUID, *, title: str = "Use Postgres"
) -> uuid.UUID:
    decision = await store.record(
        project_id=project_id,
        title=title,
        context="We need a primary datastore.",
        decision="Use PostgreSQL.",
        consequences="Operational familiarity, strong consistency.",
    )
    return decision.id


class TestRecordAndGet:
    async def test_record_creates_a_proposed_decision(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)

        decision = await store.record(
            project_id=project_id,
            title="Use Postgres",
            context="We need a primary datastore.",
            decision="Use PostgreSQL.",
        )
        await db.commit()

        assert decision.status == ArchitectureDecisionStatus.PROPOSED
        assert decision.superseded_by_id is None

    async def test_get_returns_the_recorded_decision(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        decision_id = await _record(store, project_id)
        await db.commit()

        fetched = await store.get(decision_id)

        assert fetched.title == "Use Postgres"

    async def test_get_an_unknown_id_raises(self, db: AsyncSession) -> None:
        store = ArchitectureDecisionStore(db)
        with pytest.raises(ArchitectureDecisionNotFoundError):
            await store.get(uuid.uuid4())


class TestListForProject:
    async def test_only_returns_that_projects_decisions(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        await _record(store, project_id, title="Decision A")
        await _record(store, project_id, title="Decision B")
        await db.commit()

        decisions = await store.list_for_project(project_id)

        assert {d.title for d in decisions} == {"Decision A", "Decision B"}

    async def test_filters_by_status(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        accepted_id = await _record(store, project_id, title="Will accept")
        await _record(store, project_id, title="Stays proposed")
        await store.accept(accepted_id)
        await db.commit()

        accepted = await store.list_for_project(
            project_id, status=ArchitectureDecisionStatus.ACCEPTED
        )

        assert [d.title for d in accepted] == ["Will accept"]


class TestAcceptReject:
    async def test_accept_transitions_proposed_to_accepted(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        decision_id = await _record(store, project_id)
        await db.commit()

        accepted = await store.accept(decision_id)
        await db.commit()

        assert accepted.status == ArchitectureDecisionStatus.ACCEPTED

    async def test_accepting_a_non_proposed_decision_raises(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        decision_id = await _record(store, project_id)
        await store.accept(decision_id)
        await db.commit()

        with pytest.raises(DecisionNotDecidableError):
            await store.accept(decision_id)

    async def test_reject_transitions_proposed_to_rejected(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        decision_id = await _record(store, project_id)
        await db.commit()

        rejected = await store.reject(decision_id)
        await db.commit()

        assert rejected.status == ArchitectureDecisionStatus.REJECTED

    async def test_rejecting_a_non_proposed_decision_raises(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        decision_id = await _record(store, project_id)
        await store.reject(decision_id)
        await db.commit()

        with pytest.raises(DecisionNotDecidableError):
            await store.reject(decision_id)


class TestSupersede:
    async def test_supersede_creates_a_new_accepted_decision_and_marks_the_old_one_superseded(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        old_id = await _record(store, project_id, title="Use REST")
        await store.accept(old_id)
        await db.commit()

        new_decision = await store.supersede(
            old_id,
            title="Use GraphQL",
            context="REST is proving limiting for nested resource fetches.",
            decision="Migrate the public API to GraphQL.",
        )
        await db.commit()

        assert new_decision.status == ArchitectureDecisionStatus.ACCEPTED
        assert new_decision.title == "Use GraphQL"

        old = await store.get(old_id)
        assert old.status == ArchitectureDecisionStatus.SUPERSEDED
        assert old.superseded_by_id == new_decision.id

    async def test_superseding_a_non_accepted_decision_raises(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        store = ArchitectureDecisionStore(db)
        decision_id = await _record(store, project_id)  # still PROPOSED
        await db.commit()

        with pytest.raises(DecisionNotSupersedableError):
            await store.supersede(
                decision_id,
                title="Replacement",
                context="...",
                decision="...",
            )
