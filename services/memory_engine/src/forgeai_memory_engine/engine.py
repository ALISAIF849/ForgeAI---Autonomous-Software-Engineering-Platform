"""The facade a caller actually depends on — `MemoryEngine(db).decisions` /
`.events` — rather than wiring up ArchitectureDecisionStore and
EpisodicMemoryStore separately everywhere. Matches
docs/architecture/05-memory-engine.md §3's illustrative interface only
partially: `remember()`/`recall()`/`get_context_bundle()` there describe the
*semantic*-memory-inclusive interface. This sub-sprint (4.1) has no semantic
memory yet (needs a real embedding provider and a pgvector-enabled Postgres,
neither wired in) — `.events.remember()` here is episodic memory specifically,
not the general-purpose `remember()` the doc sketches. Naming it identically
to a not-yet-built method would be dishonest about what actually exists.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_memory_engine.decisions import ArchitectureDecisionStore
from forgeai_memory_engine.events import EpisodicMemoryStore


class MemoryEngine:
    def __init__(self, db: AsyncSession) -> None:
        self.decisions = ArchitectureDecisionStore(db)
        self.events = EpisodicMemoryStore(db)
