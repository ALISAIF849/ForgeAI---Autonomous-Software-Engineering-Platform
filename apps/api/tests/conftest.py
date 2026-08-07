"""Integration tests run against a real, ephemeral Postgres container — not
SQLite — per docs/engineering/09-testing-strategy.md §3: SQLite lacks JSONB/
native UUID/RLS and would validate a different database than production.
"""

import os
import uuid
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

from forgeai_core.models.enums import OrgRole
from forgeai_core.models.organization import Organization
from forgeai_core.models.organization_member import OrganizationMember
from forgeai_core.models.project import Project

API_ROOT = Path(__file__).resolve().parents[1]


def _build_alembic_config() -> Config:
    # script_location in alembic.ini is relative to the CWD Alembic runs from, not
    # to the ini file itself — fine from `apps/api/`, wrong from the repo root,
    # which is where pytest runs in this workspace. Set it explicitly, absolute.
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    """A fixture, not a plain importable function — under `--import-mode=importlib`
    (see pyproject.toml), conftest.py isn't implicitly on sys.path as a
    bare-importable module, so `from conftest import X` breaks. Fixtures are
    pytest's actual mechanism for sharing something across test files regardless
    of import mode; test_migrations.py requests this by parameter name instead."""
    return _build_alembic_config()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        "postgres:17-alpine", username="forgeai", password="forgeai", dbname="forgeai"
    ) as container:
        yield container


@pytest.fixture(scope="session", autouse=True)
def test_env(postgres_container: PostgresContainer) -> Iterator[None]:
    """Points Settings at the test container and clears get_settings()'s cache —
    required because it's an lru_cache'd zero-arg function, so a stale call before
    these env vars are set would otherwise poison every test in the session.
    """
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    os.environ["DATABASE_URL"] = f"postgresql+asyncpg://forgeai:forgeai@{host}:{port}/forgeai"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    # >= 32 bytes: PyJWT warns below that for HS256 (RFC 7518 §3.2) — worth
    # modeling a correctly-sized secret even in tests, not just suppressing the warning.
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"
    os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"

    from forgeai_api.core.config import get_settings

    get_settings.cache_clear()

    yield

    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def migrated_schema(test_env: None, alembic_cfg: Config) -> None:
    """Applies migrations once per session, explicitly — not left as a side
    effect of test_migrations.py happening to run first. pytest collects test
    files alphabetically by default, and `test_auth.py` sorts before
    `test_migrations.py`; relying on file-execution order for the schema to
    exist was a real bug here (auth tests failed with `relation "users" does
    not exist` until this fixture was added), not a hypothetical one."""
    from alembic import command

    command.upgrade(alembic_cfg, "head")


@pytest.fixture(autouse=True)
def _fresh_db_engine_per_test() -> Iterator[None]:
    """Function-scoped and autouse — see reset_engine_cache()'s docstring for why
    a module-level engine singleton must not survive across tests that each
    create their own TestClient (and therefore, potentially, their own event
    loop)."""
    from forgeai_api.db.session import reset_engine_cache

    reset_engine_cache()
    yield
    reset_engine_cache()


@pytest.fixture
def seed_project(
    test_env: None, _fresh_db_engine_per_test: None
) -> Callable[..., Coroutine[Any, Any, uuid.UUID]]:
    """Returns an async `seed(user_id, *, role=OrgRole.OWNER) -> project_id`
    factory. There's no Projects HTTP API yet (a real, separate gap from the
    workflows API this fixture supports testing — see the Sprint 2 status
    reports), so tests that need a project to scope workflow-execution
    requests to seed one directly.

    Deliberately its own throwaway engine, not `get_session_factory()`'s
    app-wide cached one: callers drive this from inside a fresh `asyncio.run()`
    (see test_workflows_api.py's `_run` helper, since TestClient itself is
    sync) — reusing the app's engine, bound to TestClient's own loop, from a
    *different* loop is exactly the cross-event-loop asyncpg bug
    db/session.py's get_engine() docstring warns about. A fresh engine here,
    disposed immediately after, sidesteps it entirely rather than risking it.
    """

    async def _seed(user_id: uuid.UUID, *, role: OrgRole = OrgRole.OWNER) -> uuid.UUID:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from forgeai_api.core.config import get_settings

        unique = uuid.uuid4().hex[:8]
        engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            org = Organization(name="Test Org", slug=f"org-{unique}", created_by=user_id)
            session.add(org)
            await session.flush()

            session.add(OrganizationMember(organization_id=org.id, user_id=user_id, role=role))

            project = Project(
                organization_id=org.id,
                name="Test Project",
                slug=f"proj-{unique}",
                owner_id=user_id,
                created_by=user_id,
            )
            session.add(project)
            await session.commit()
        await engine.dispose()
        return project.id

    return _seed
