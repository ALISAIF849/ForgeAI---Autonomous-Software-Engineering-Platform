from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from forgeai_api.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        # NullPool: no connection reuse across requests, a fresh asyncpg connection
        # per checkout. Costs some latency pooling would otherwise save, but sidesteps
        # a real, reproduced-not-assumed class of bug where a pooled connection ends
        # up bound to a different event loop than the one currently running — surfaces
        # as an opaque `'NoneType' object has no attribute 'send'` deep in asyncio.
        # Revisit once there's real production load to tune pool size against.
        _engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


def reset_engine_cache() -> None:
    """Test-only escape hatch. asyncpg connections are bound to the event loop
    they were created on, and a naive module-level singleton engine — the right
    choice for a real running app process — breaks across test functions that
    each spin up their own TestClient (and therefore, on Windows' proactor loop
    in particular, potentially their own event loop): reusing the cached engine
    then fails deep in asyncio with an opaque `NoneType has no attribute 'send'`.
    Call this between tests so each gets an engine bound to its own loop."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
