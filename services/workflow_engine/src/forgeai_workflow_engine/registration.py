"""Turns a validated, in-memory WorkflowDefinition (services/workflow_engine's
own Pydantic model) into the persisted WorkflowVersion + WorkflowStage rows
the Executor reads at run time. Deliberately separate from the Executor
itself: registration happens once, when a definition is published; the
Executor runs many times against what registration already wrote — mixing
the two would blur "set up the plan" with "follow the plan".
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow import Workflow
from forgeai_core.models.workflow_stage import WorkflowStage
from forgeai_core.models.workflow_version import WorkflowVersion
from forgeai_workflow_engine.definition import WorkflowDefinition
from forgeai_workflow_engine.exceptions import DefinitionAlreadyRegisteredError


async def get_or_create_workflow(
    db: AsyncSession, key: str, name: str, *, created_by: uuid.UUID | None = None
) -> Workflow:
    from sqlalchemy import select

    result = await db.execute(select(Workflow).where(Workflow.key == key))
    workflow = result.scalar_one_or_none()
    if workflow is not None:
        return workflow

    workflow = Workflow(key=key, name=name, created_by=created_by)
    db.add(workflow)
    await db.flush()
    return workflow


async def register_version(
    db: AsyncSession, workflow: Workflow, definition: WorkflowDefinition
) -> WorkflowVersion:
    """Persists `definition` as a new, immutable WorkflowVersion — raises if
    (workflow.key, definition.version) already exists, the same "immutable
    once registered" discipline as WorkflowRegistry.register() (sub-sprint
    2.1), now enforced at the database layer too via the uq_workflow_version
    constraint, not only in the in-process registry."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    existing = await db.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == definition.version,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DefinitionAlreadyRegisteredError(workflow.key, definition.version)

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=definition.version,
        graph_spec=definition.model_dump(mode="json"),
    )
    db.add(version)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Race: two callers registering the same version concurrently — the
        # pre-check above narrows the window but can't close it entirely.
        raise DefinitionAlreadyRegisteredError(workflow.key, definition.version) from exc

    for index, stage in enumerate(definition.stages):
        db.add(
            WorkflowStage(
                workflow_version_id=version.id,
                stage_key=stage.id,
                name=stage.name,
                sequence_index=index,
                depends_on=stage.depends_on,
                capability_key=stage.capability,
                retry_policy=stage.retry_policy.model_dump(mode="json"),
                timeout_policy=stage.timeout.model_dump(mode="json"),
                requires_approval=stage.requires_approval,
                allow_skip=stage.allow_skip,
            )
        )
    await db.flush()
    return version
