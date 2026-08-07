"""Org-role RBAC, enforced as a FastAPI dependency rather than checked ad hoc
inside route handlers — every route that needs a role check declares it in its
signature, so a missing check is visible in the route's own type signature,
not something a reviewer has to trace into the function body to notice.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_api.core.exceptions import ForbiddenError
from forgeai_api.db.session import get_db
from forgeai_api.dependencies.auth import get_current_user
from forgeai_core.models.enums import OrgRole
from forgeai_core.models.organization_member import OrganizationMember
from forgeai_core.models.project import Project
from forgeai_core.models.user import User

# Lower rank = more privileged. Compared numerically rather than relying on enum
# member order, which isn't guaranteed to carry meaning for a StrEnum.
_ROLE_RANK: dict[OrgRole, int] = {
    OrgRole.OWNER: 0,
    OrgRole.ADMIN: 1,
    OrgRole.DEVELOPER: 2,
    OrgRole.VIEWER: 3,
}


def require_org_role(
    min_role: OrgRole,
) -> Callable[..., Coroutine[Any, Any, OrganizationMember]]:
    """Returns a dependency requiring the caller to be a member of the
    organization named by the route's `organization_id` path parameter, with
    at least `min_role` privilege. Usage: `Depends(require_org_role(OrgRole.ADMIN))`.
    """

    async def dependency(
        organization_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> OrganizationMember:
        result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == current_user.id,
            )
        )
        member = result.scalar_one_or_none()
        if member is None:
            raise ForbiddenError("You are not a member of this organization.")
        if _ROLE_RANK[member.role] > _ROLE_RANK[min_role]:
            raise ForbiddenError(f"This action requires at least the {min_role.value} role.")
        return member

    return dependency


def require_project_role(
    min_role: OrgRole,
) -> Callable[..., Coroutine[Any, Any, OrganizationMember]]:
    """Same idea as require_org_role, resolved through the route's `project_id`
    path parameter instead — workflow-execution routes are project-scoped, and
    a project's membership is really its owning organization's membership.
    Deliberately a single joined query rather than "load the Project, then
    check membership": that would 404 a nonexistent project before the
    membership check ever runs, leaking whether a given project ID exists to
    a caller who isn't even a member of anything relevant to it. Joining means
    a bad project_id and a real-but-forbidden one produce the same 403, same
    reasoning as require_org_role's own non-member-vs-nonexistent-org case."""

    async def dependency(
        project_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> OrganizationMember:
        result = await db.execute(
            select(OrganizationMember)
            .join(Project, Project.organization_id == OrganizationMember.organization_id)
            .where(Project.id == project_id, OrganizationMember.user_id == current_user.id)
        )
        member = result.scalar_one_or_none()
        if member is None:
            raise ForbiddenError("You are not a member of this project's organization.")
        if _ROLE_RANK[member.role] > _ROLE_RANK[min_role]:
            raise ForbiddenError(f"This action requires at least the {min_role.value} role.")
        return member

    return dependency
