"""Entry point — installed as the `forgeai-worker` script (see pyproject.toml's
[project.scripts]). Wires a real engine/session and drives loop.run_iteration()
forever, sleeping between empty polls. Graceful shutdown on SIGINT/SIGTERM:
lets whatever claim is in flight finish rather than dying mid-transaction.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import uuid

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from forgeai_core.logging import configure_logging
from forgeai_worker.config import get_settings
from forgeai_worker.loop import run_iteration
from forgeai_workflow_engine.runner import UnconfiguredStageRunner

logger = structlog.get_logger()


async def run_forever() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, environment=settings.environment)

    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    # No NullPool here, unlike the test fixtures: this process has exactly one
    # event loop for its entire lifetime (asyncio.run() below), so connection
    # pooling is safe and worth having — NullPool exists to dodge a
    # *cross*-event-loop bug that only arises when the same engine outlives
    # the loop it was created on, which never happens to a long-running
    # single-process worker the way it does across separate test functions.
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    runner = UnconfiguredStageRunner()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # add_signal_handler isn't available on Windows' default (Proactor)
        # event loop — Ctrl-C still raises KeyboardInterrupt there, caught in
        # main() instead.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    logger.info("worker_starting", worker_id=worker_id)
    try:
        while not stop_event.is_set():
            async with session_factory() as db:
                did_work = await run_iteration(db, worker_id, runner)
            if not did_work:
                # Interruptible sleep: a stop signal wakes this immediately
                # instead of waiting out the full poll interval.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=settings.poll_interval_seconds
                    )
    finally:
        logger.info("worker_stopping", worker_id=worker_id)
        await engine.dispose()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_forever())
