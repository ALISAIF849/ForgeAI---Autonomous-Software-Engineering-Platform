# 05 — Memory Engine Architecture (Layer 5)

This layer is what makes "persistent engineering memory" (principle #5) real rather than aspirational, and it's the clearest structural difference between ForgeAI and a chatbot with a long context window. A chat session forgets when it ends; a ForgeAI project accumulates institutional memory that every future workflow execution can draw on.

## 1. Four kinds of memory, not one

Treating "memory" as a single undifferentiated store (typically: "throw everything in a vector DB") is the single most common design mistake in this space — it makes retrieval noisy (structured facts competing with prose for similarity-search relevance) and makes anything resembling "what did we decide and why" impossible to answer reliably. Instead:

| Kind                  | What it holds                                                                                                                 | Storage                                                   | Retrieval                                                                             |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Structured memory** | Requirements, Features, Architecture Decisions, Milestones, Tasks — first-class entities with their own columns               | Regular Postgres tables                                   | Direct SQL query/filter — never similarity search                                     |
| **Episodic memory**   | An append-only log of everything that happened: workflow started, capability executed, approval granted, deployment succeeded | `events` table                                            | Filtered/paginated query (powers the Activity Feed); older events get summarized (§5) |
| **Semantic memory**   | Unstructured context an LLM needs to recall: conversation snippets, decision rationale prose, review comments                 | `memory_entries` table with a `pgvector` embedding column | Vector similarity search, optionally hybrid with recency/metadata filters             |
| **Working memory**    | The in-flight state of one `WorkflowExecution` — not durable cross-workflow memory                                            | LangGraph checkpoint (Postgres-backed)                    | Scoped to that execution only; see [03-workflow-engine.md](03-workflow-engine.md)     |

Working memory is listed here specifically to draw the boundary clearly: it is _not_ the Memory Engine's concern, even though it also lives in Postgres. Conflating "state of the currently running graph" with "durable project memory" is an easy mistake that would couple the Workflow Engine and Memory Engine unnecessarily.

## 2. Why `pgvector`, not a dedicated vector database

**Chosen:** semantic memory embeddings live in PostgreSQL via the `pgvector` extension, in the same database as everything else.

**Alternative considered:** a dedicated vector store (Pinecone, Weaviate, Qdrant).

**Why `pgvector` wins here:** running a second stateful system has real operational cost (a second thing to back up, monitor, keep consistent with the primary store, pay for) that isn't justified at ForgeAI's expected scale — per-project semantic memory in the thousands to low-millions of entries, not the tens-of-millions-plus range where dedicated ANN indexes clearly outperform `pgvector`'s. Keeping embeddings in Postgres also means a `recall()` query can join semantic search against structured filters (`project_id`, `memory_type`, date range) in one query instead of round-tripping between two systems.

**This is a bounded choice, not an unlimited-scale claim.** If a project's semantic memory volume or query latency crosses a threshold where `pgvector`'s ANN index degrades, the migration path is to move embeddings to a dedicated store _behind the same `MemoryEngine.recall()` interface_ — callers never notice. Documented as a revisit trigger in [14-risks-and-tradeoffs.md](14-risks-and-tradeoffs.md).

## 3. Interface

```python
# services/memory_engine/api.py — illustrative
async def remember(project_id: UUID, memory_type: MemoryType, content: str, metadata: dict,
                    source_event_id: UUID | None = None, embed: bool = True) -> MemoryEntry: ...

async def recall(project_id: UUID, query: str, memory_types: list[MemoryType] | None = None,
                  top_k: int = 8, filters: dict | None = None) -> list[MemoryEntry]: ...

async def get_context_bundle(project_id: UUID, capability_key: str, workflow_execution_id: UUID | None
                              ) -> ContextBundle: ...
```

`get_context_bundle` is the method capabilities actually call (via `CapabilityContext.memory`, see [04-capability-registry.md](04-capability-registry.md) §2) — it's a curated assembly, not a raw dump: relevant structured records (e.g., the project's current requirements and latest accepted architecture), a hybrid recall over semantic memory, and a bounded slice of recent episodic events, combined into a token-budgeted bundle sized for the target capability. This is the system's Retrieval-Augmented Generation assembly point.

## 4. Architecture Decisions are first-class, not vector-store entries

Given "architecture history" is explicitly called out in the brief, and given principle #6 (explainable AI decisions), architecture decisions get a dedicated structured table (`architecture_decisions`) modeled directly on the ADR format — `title`, `context`, `decision`, `consequences`, `status` (proposed/accepted/superseded), `superseded_by_id`. This means:

- A user can read a project's entire architectural history as a linear, human-readable log — not by querying a vector store and hoping the right chunks surface.
- Superseding a decision is explicit (a new ADR points back at the old one), not an implicit overwrite — so "why did we move away from X" is always answerable.
- Every ADR records which `CapabilityExecution` (if any) produced it, chaining back to the exact reasoning summary and model that generated it — full traceability from decision to justification to the AI invocation that proposed it.

This directly parallels how _this document set_ is written and how ForgeAI's own future incremental decisions should be recorded in `docs/adr/` (see [01-repository-structure.md](01-repository-structure.md) §2) — the same discipline applied at the platform level, the per-project level, and now the data-model level.

## 5. Compaction

Episodic memory is append-only and unbounded by nature — a long-lived project will accumulate a large `events` history. A background job (running in `apps/worker`, see [10-backend-architecture.md](10-backend-architecture.md)) periodically summarizes events older than a configurable window (e.g., 90 days) into higher-level semantic-memory entries (e.g., "In Q1, the team shipped 14 features across 6 sprints, with 2 architecture revisions") — keeping `recall()` fast and the context bundles in §3 from being dominated by stale detail. Raw events are never deleted (audit requirements — see [12-security-architecture.md](12-security-architecture.md)), only excluded from default recall once summarized.

## 6. What Memory Engine deliberately does not do

It does not make decisions, and it does not call other layers unprompted. It's a pure store-and-retrieve service — every other layer decides _when_ to write to or read from it. This keeps it testable in isolation and prevents a specific failure mode where "memory" quietly becomes a second orchestration engine with its own opinions about workflow logic.
