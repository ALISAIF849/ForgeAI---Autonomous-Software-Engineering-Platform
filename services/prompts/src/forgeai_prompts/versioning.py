"""Strict 'N.N.N' version parsing — intentionally duplicated from
forgeai_workflow_engine.definition.parse_version rather than shared, because
services/prompts is deliberately a zero-internal-dependency package
(docs/engineering/01-repository-scaffolding.md §3: "prompts" has no listed
workspace dependency, not even forgeai-core) — it should stay usable in
isolation (e.g. exported as plain data to a future prompt-management UI)
without pulling in the rest of the platform's dependency graph for one
~10-line function.
"""

from __future__ import annotations

from forgeai_prompts.exceptions import InvalidVersionError


def parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise InvalidVersionError(version)
    major, minor, patch = (int(part) for part in parts)
    return (major, minor, patch)
