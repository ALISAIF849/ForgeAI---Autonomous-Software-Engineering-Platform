import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.enums import OrgRole
from forgeai_core.models.organization import Organization
from forgeai_core.models.organization_member import OrganizationMember


class OrganizationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, organization_id: uuid.UUID) -> Organization | None:
        return await self._db.get(Organization, organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._db.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def create_with_owner(
        self, *, name: str, slug: str, description: str | None, owner_id: uuid.UUID
    ) -> Organization:
        org = Organization(name=name, slug=slug, description=description, created_by=owner_id)
        self._db.add(org)
        await self._db.flush()

        self._db.add(
            OrganizationMember(organization_id=org.id, user_id=owner_id, role=OrgRole.OWNER)
        )
        await self._db.flush()
        return org
