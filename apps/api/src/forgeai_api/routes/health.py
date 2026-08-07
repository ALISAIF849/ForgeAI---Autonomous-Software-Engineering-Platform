"""Liveness vs. readiness, deliberately not one combined /health endpoint — an
orchestrator restart-looping a healthy process because the database is briefly
unreachable is exactly the failure mode this split avoids. See
docs/engineering/10-logging-observability.md §6. Not versioned/under /api/v1:
an orchestrator checking health shouldn't need to know the API version.
"""

from fastapi import APIRouter, status
from sqlalchemy import text

from forgeai_api.db.session import get_session_factory

router = APIRouter(tags=["health"])


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness() -> dict[str, str]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}
