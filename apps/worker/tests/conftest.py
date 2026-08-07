"""Integration tests run against a real, ephemeral Postgres container — not
SQLite — same reasoning as services/workflow_engine/tests/conftest.py and
apps/api/tests/conftest.py (docs/engineering/09-testing-strategy.md §3). Uses
Base.metadata.create_all() directly, same as workflow_engine's own tests and
for the same reason: these tests exercise the worker loop's behavior against
a real schema, not migration correctness.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from forgeai_core.db.base import Base
from forgeai_core.models import *  # noqa: F403 — registers every model on Base.metadata
from forgeai_core.models.organization import Organization
from forgeai_core.models.project import Project
from forgeai_core.models.user import User


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        "postgres:17-alpine", username="forgeai", password="forgeai", dbname="forgeai"
    ) as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return f"postgresql+asyncpg://forgeai:forgeai@{host}:{port}/forgeai"


@pytest.fixture(scope="session", autouse=True)
def _schema(database_url: str) -> None:
    async def _create() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())


@pytest.fixture(autouse=True)
async def _clean_tables(database_url: str) -> None:
    """Function-scoped, autouse, and a dependency of `db` (below) — every test
    starts against empty tables. Needed for the same reason as
    workflow_engine's own tests: claim_next()'s "next queued entry" ordering
    would otherwise be polluted by rows an earlier test left behind."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
async def db(database_url: str, _clean_tables: None) -> AsyncIterator[AsyncSession]:
    # NullPool + a fresh engine per test: see
    # apps/api/src/forgeai_api/db/session.py's get_engine() docstring — a
    # pooled connection surviving across two tests' different event loops is a
    # reproduced, not hypothetical, class of bug on this stack.
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def seeded_project(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A minimal User -> Organization -> Project chain, freshly created per
    test, for the workflow tables to FK against. Returns (user_id, org_id,
    project_id)."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"worker-{unique}@example.com",
        username=f"worker{unique}",
        hashed_password="x",
    )
    db.add(user)
    await db.flush()

    org = Organization(name="Test Org", slug=f"org-{unique}", created_by=user.id)
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id,
        name="Test Project",
        slug=f"proj-{unique}",
        owner_id=user.id,
        created_by=user.id,
    )
    db.add(project)
    await db.flush()
    await db.commit()

    return user.id, org.id, project.id
