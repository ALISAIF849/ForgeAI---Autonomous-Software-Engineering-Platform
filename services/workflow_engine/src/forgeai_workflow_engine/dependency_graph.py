"""Shared by definition validation (2.1 — rejecting a WorkflowDefinition whose
stages form a cycle) and, later, the Executor (2.3 — deciding which stages can
run in parallel). One implementation, not two, for the same underlying
question: "given these dependencies, what order can these things run in?"
"""

from __future__ import annotations

from forgeai_workflow_engine.exceptions import CyclicDependencyError


def topological_levels(stage_ids: list[str], depends_on: dict[str, list[str]]) -> list[list[str]]:
    """Groups stage IDs into ordered levels via Kahn's algorithm: every stage in
    one level has no dependency on any other stage in that same level (so they
    could run in parallel), and depends only on stages in strictly earlier
    levels. Raises CyclicDependencyError if the graph isn't a DAG.

    Callers are expected to have already validated that every ID in `depends_on`
    refers to a real stage — see UnknownStageDependencyError, checked separately
    in definition.py so a broken reference and a genuine cycle produce distinct,
    specific error messages rather than both collapsing into "cycle detected".
    """
    remaining = set(stage_ids)
    resolved: set[str] = set()
    levels: list[list[str]] = []

    while remaining:
        ready = sorted(
            stage_id
            for stage_id in remaining
            if all(dep in resolved for dep in depends_on.get(stage_id, []))
        )
        if not ready:
            raise CyclicDependencyError(sorted(remaining))
        levels.append(ready)
        resolved.update(ready)
        remaining.difference_update(ready)

    return levels
