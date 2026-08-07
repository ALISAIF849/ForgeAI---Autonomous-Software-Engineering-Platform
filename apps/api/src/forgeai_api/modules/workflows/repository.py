import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow import Workflow
from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_version import WorkflowVersion


class WorkflowRepository:
    """Read queries the Executor itself has no reason to own — it operates on
    a specific, already-known WorkflowVersion row, never "look one up by
    key+version string" or "list every version of this key", both of which
    are API-surface concerns (a client picking which version to run)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_workflow_by_key(self, key: str) -> Workflow | None:
        result = await self._db.execute(select(Workflow).where(Workflow.key == key))
        return result.scalar_one_or_none()

    async def get_version(self, key: str, version: str) -> WorkflowVersion | None:
        result = await self._db.execute(
            select(WorkflowVersion)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .where(Workflow.key == key, WorkflowVersion.version == version)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, key: str) -> list[WorkflowVersion]:
        result = await self._db.execute(
            select(WorkflowVersion)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .where(Workflow.key == key)
            .order_by(WorkflowVersion.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_approvals(self, execution_id: uuid.UUID) -> list[WorkflowApproval]:
        result = await self._db.execute(
            select(WorkflowApproval)
            .where(WorkflowApproval.workflow_execution_id == execution_id)
            .order_by(WorkflowApproval.created_at.asc())
        )
        return list(result.scalars().all())
