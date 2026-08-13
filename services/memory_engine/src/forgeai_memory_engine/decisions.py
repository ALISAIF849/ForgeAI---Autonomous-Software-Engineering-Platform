"""Structured memory: Architecture Decision Records, per
docs/architecture/05-memory-engine.md §4 — first-class rows with their own
columns, never vector-store entries. Superseding never edits a row in place:
`supersede()` creates a new ACCEPTED decision and points the old one at it
via `superseded_by_id`, so a project's architectural history reads as a
linear, append-mostly log where "why did we move away from X" is always
answerable.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.architecture_decision import ArchitectureDecision
from forgeai_core.models.enums import ArchitectureDecisionStatus
from forgeai_memory_engine.exceptions import (
    ArchitectureDecisionNotFoundError,
    DecisionNotDecidableError,
    DecisionNotSupersedableError,
)


class ArchitectureDecisionStore:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        context: str,
        decision: str,
        consequences: str | None = None,
        created_by: uuid.UUID | None = None,
        capability_execution_id: uuid.UUID | None = None,
    ) -> ArchitectureDecision:
        """Always starts PROPOSED — a decision is accepted or rejected via
        accept()/reject(), never created pre-decided, so there's always a
        real moment where the decision was made, not just recorded."""
        record = ArchitectureDecision(
            project_id=project_id,
            title=title,
            context=context,
            decision=decision,
            consequences=consequences,
            status=ArchitectureDecisionStatus.PROPOSED,
            created_by=created_by,
            capability_execution_id=capability_execution_id,
        )
        self._db.add(record)
        await self._db.flush()
        return record

    async def get(self, decision_id: uuid.UUID) -> ArchitectureDecision:
        record = await self._db.get(ArchitectureDecision, decision_id)
        if record is None:
            raise ArchitectureDecisionNotFoundError(decision_id)
        return record

    async def list_for_project(
        self, project_id: uuid.UUID, *, status: ArchitectureDecisionStatus | None = None
    ) -> list[ArchitectureDecision]:
        query = select(ArchitectureDecision).where(ArchitectureDecision.project_id == project_id)
        if status is not None:
            query = query.where(ArchitectureDecision.status == status)
        query = query.order_by(ArchitectureDecision.created_at.asc())
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def accept(self, decision_id: uuid.UUID) -> ArchitectureDecision:
        record = await self.get(decision_id)
        if record.status != ArchitectureDecisionStatus.PROPOSED:
            raise DecisionNotDecidableError(decision_id, record.status.value, "accept")
        record.status = ArchitectureDecisionStatus.ACCEPTED
        await self._db.flush()
        return record

    async def reject(self, decision_id: uuid.UUID) -> ArchitectureDecision:
        record = await self.get(decision_id)
        if record.status != ArchitectureDecisionStatus.PROPOSED:
            raise DecisionNotDecidableError(decision_id, record.status.value, "reject")
        record.status = ArchitectureDecisionStatus.REJECTED
        await self._db.flush()
        return record

    async def supersede(
        self,
        decision_id: uuid.UUID,
        *,
        title: str,
        context: str,
        decision: str,
        consequences: str | None = None,
        created_by: uuid.UUID | None = None,
        capability_execution_id: uuid.UUID | None = None,
    ) -> ArchitectureDecision:
        """Creates a new, already-ACCEPTED decision (superseding one supplants
        the old one immediately, not through its own PROPOSED review) and
        points the old decision at it. Returns the *new* decision."""
        old = await self.get(decision_id)
        if old.status != ArchitectureDecisionStatus.ACCEPTED:
            raise DecisionNotSupersedableError(decision_id, old.status.value)

        new_record = ArchitectureDecision(
            project_id=old.project_id,
            title=title,
            context=context,
            decision=decision,
            consequences=consequences,
            status=ArchitectureDecisionStatus.ACCEPTED,
            created_by=created_by,
            capability_execution_id=capability_execution_id,
        )
        self._db.add(new_record)
        await self._db.flush()

        old.status = ArchitectureDecisionStatus.SUPERSEDED
        old.superseded_by_id = new_record.id
        await self._db.flush()
        return new_record
