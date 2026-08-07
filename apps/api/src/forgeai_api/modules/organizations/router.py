import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_api.db.session import get_db
from forgeai_api.dependencies.auth import get_current_user
from forgeai_api.dependencies.rbac import require_org_role
from forgeai_api.modules.organizations.schemas import OrganizationCreateRequest, OrganizationPublic
from forgeai_api.modules.organizations.service import OrganizationService
from forgeai_core.models.enums import OrgRole
from forgeai_core.models.organization import Organization
from forgeai_core.models.organization_member import OrganizationMember
from forgeai_core.models.user import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationPublic, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Creating an org has no role prerequisite — any authenticated user can
    create one, becoming its Owner. Invite/remove/transfer/leave/archive
    (the rest of the Organizations module) remain still-pending Sprint 1 work."""
    service = OrganizationService(db)
    return await service.create(request, owner_id=current_user.id)


@router.get("/{organization_id}", response_model=OrganizationPublic)
async def get_organization(
    organization_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _member: OrganizationMember = Depends(require_org_role(OrgRole.VIEWER)),
) -> Organization:
    """RBAC-protected: any org member (Viewer+) can view; enforced via
    require_org_role, not an ad hoc check in this function body."""
    service = OrganizationService(db)
    return await service.get(organization_id)
