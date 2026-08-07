"""Shared structlog setup for every process (apps/api, apps/worker) — plain
strings in, not a Settings object, so this has no dependency on any one
process's config class (which each process still defines separately; see
apps/worker/src/forgeai_worker/config.py's own docstring for why Settings
itself isn't shared the same way)."""

import logging
import sys

import structlog


def configure_logging(*, log_level: str, environment: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    renderer = (
        structlog.dev.ConsoleRenderer()
        if environment == "development"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
