import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_api.modules.organizations.exceptions import (
    OrganizationNotFoundError,
    OrganizationSlugTakenError,
)
from forgeai_api.modules.organizations.repository import OrganizationRepository
from forgeai_api.modules.organizations.schemas import OrganizationCreateRequest
from forgeai_core.models.organization import Organization


class OrganizationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._orgs = OrganizationRepository(db)

    async def create(self, request: OrganizationCreateRequest, owner_id: uuid.UUID) -> Organization:
        if await self._orgs.get_by_slug(request.slug) is not None:
            raise OrganizationSlugTakenError

        org = await self._orgs.create_with_owner(
            name=request.name,
            slug=request.slug,
            description=request.description,
            owner_id=owner_id,
        )
        await self._db.commit()
        return org

    async def get(self, organization_id: uuid.UUID) -> Organization:
        org = await self._orgs.get_by_id(organization_id)
        if org is None:
            raise OrganizationNotFoundError
        return org
