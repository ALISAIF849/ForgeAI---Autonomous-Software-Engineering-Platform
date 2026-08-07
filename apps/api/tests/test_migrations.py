"""Alembic up/down round-trip — proves a migration doesn't corrupt state on
rollback, per docs/engineering/09-testing-strategy.md §3. The schema is already
applied by conftest.py's session-scoped `migrated_schema` fixture before this
test runs; this test still exercises the full down-then-up cycle explicitly,
it just doesn't need to be the one test that happens to apply it first.
"""

import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine


async def _table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
    await engine.dispose()
    return names


def test_upgrade_then_downgrade_round_trips_cleanly(
    migrated_schema: None, alembic_cfg: Config
) -> None:
    """Deliberately a sync test, not `async def` — alembic/env.py drives migrations
    via asyncio.run(), which cannot be called from inside a loop that's already
    running (which pytest-asyncio's own async-test loop would be). `alembic_cfg`
    is a fixture (see conftest.py), not an imported function — under
    `--import-mode=importlib`, `from conftest import X` doesn't work."""
    from forgeai_api.core.config import get_settings

    database_url = get_settings().database_url

    tables_after_upgrade = asyncio.run(_table_names(database_url))
    assert {
        "users",
        "organizations",
        "projects",
        "sessions",
        "alembic_version",
        "workflows",
        "workflow_versions",
        "workflow_stages",
        "workflow_executions",
        "workflow_stage_executions",
    } <= tables_after_upgrade

    command.downgrade(alembic_cfg, "base")
    tables_after_downgrade = asyncio.run(_table_names(database_url))
    assert tables_after_downgrade == {"alembic_version"}

    command.upgrade(alembic_cfg, "head")  # leave schema applied for any other test in the session
