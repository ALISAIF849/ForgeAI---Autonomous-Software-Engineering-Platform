# 10 — Backend Architecture

## 1. Modular monolith, Clean Architecture per module

Per [02-service-architecture.md](02-service-architecture.md), this is one deployable (`apps/api`) plus one worker (`apps/worker`), not a microservice per layer. _Within_ that monolith, each bounded-context module follows the same four-layer internal structure:

```
modules/requirements/
├── router.py        # FastAPI routes — HTTP concerns only: parse request, call service, shape response
├── service.py        # business logic — orchestrates repositories + services/* engine packages
├── repository.py     # SQLAlchemy queries only — no business rules
├── schemas.py         # Pydantic request/response DTOs — never the ORM model directly over the wire
└── exceptions.py       # module-specific domain exceptions
```

(ORM models live in `services/core`, shared with `apps/worker` — see [01-repository-structure.md](01-repository-structure.md) §3.)

**Why this layering:** a router that calls a repository directly (skipping `service.py`) is how business rules end up duplicated across endpoints, or worse, half-enforced. Keeping `router → service → repository` as a strict one-directional chain — enforced by the same import-boundary linter mentioned in [01](01-repository-structure.md) §4 — means business logic has exactly one home per module, testable without HTTP or a database (mock the repository, test the service).

**Why DTOs are never the ORM model:** returning SQLAlchemy models directly from an endpoint leaks internal schema shape (column names, relationships) into the public API contract and makes it impossible to change the DB shape without also changing the API — the opposite of what a stable, versioned API needs. `schemas.py` is the translation boundary.

## 2. Dependency injection

FastAPI's `Depends()` system provides repositories and services to routers; provider functions (not global singletons) construct them per-request with a request-scoped DB session. This is what makes `service.py` testable in isolation — tests inject a fake/in-memory repository instead of hitting Postgres, reserving real-database integration tests for the repository layer itself and a smaller set of end-to-end flows (§5).

## 3. Async-first throughout

SQLAlchemy 2.0 async style + `asyncpg`. This isn't a stylistic preference — the backend's actual workload (LLM calls, external API calls to GitHub/Railway/Vercel, SSE streaming) is dominated by I/O wait, not CPU, and async lets one process handle many concurrent in-flight requests/streams without a thread per connection. It's also what makes `apps/worker` (built on **Arq**, an asyncio-native Redis queue) share code cleanly with `apps/api` — no sync/async boundary to bridge between the two.

**Arq vs. Celery, decided:** Arq is asyncio-native (matches FastAPI/LangGraph's async style directly, no `run_in_executor` bridging), backed by Redis (already in the stack — no new infrastructure), and simple to configure. Celery is more mature and has a richer ecosystem (Flower monitoring, multiple broker backends, more battle-tested at very large scale), but that maturity comes from solving problems — multi-broker support, sync-worker-pool complexity — this system doesn't have. Revisit if the job ecosystem grows complex enough to need Celery's tooling (see [14-risks-and-tradeoffs.md](14-risks-and-tradeoffs.md)).

## 4. Domain events via the outbox pattern

When a service performs a significant state change (workflow status change, approval decided, deployment completed), it writes a domain event to the `events` table **in the same database transaction** as the state change itself, rather than publishing directly to Redis pub/sub from application code. A separate relay process reads newly-committed events and publishes them (to Redis pub/sub, which `apps/api` relays to SSE subscribers, and to any async side-effect handlers like notification dispatch).

**Why the extra indirection:** if application code published directly to Redis _and_ wrote to Postgres as two separate steps, a crash between them would either lose the event (published-then-crash-before-commit is impossible since commit happens first, but commit-then-crash-before-publish is very possible) or, worse, publish an event for a transaction that then rolls back. The outbox pattern guarantees the event is published if and only if the transaction that produced it actually committed — the relay only ever reads durably-committed rows.

## 5. Testing strategy

| Layer       | Tool                                    | Scope                                                                                                                                                                                                                                                                                                                                                                           |
| ----------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit        | pytest + pytest-asyncio                 | `service.py` logic with fake repositories; `services/*` engine packages in isolation (no FastAPI, no queue)                                                                                                                                                                                                                                                                     |
| Integration | pytest + testcontainers (real Postgres) | `repository.py` query correctness, Alembic migration round-trips, RLS policy behavior                                                                                                                                                                                                                                                                                           |
| Contract    | pytest, schema-based                    | Every registered Capability's `input_schema`/`output_schema` round-trips through Pydantic validation; every `WorkflowDefinition` graph compiles and its irreversible-action nodes are gated (see [03-workflow-engine.md](03-workflow-engine.md) §5) — this check runs in CI, not just at runtime, so a workflow definition that violates the approval-gate rule fails the build |
| End-to-end  | Playwright                              | A small set of golden-path flows through the real UI against a real (test) backend — e.g., create project → gather requirements → generate architecture → approve                                                                                                                                                                                                               |

Test data via factory classes (`polyfactory`, which works directly off the Pydantic/SQLAlchemy models already in `services/core` rather than a separate fixture-definition language) — keeps fixtures from drifting out of sync with the schema they represent.

## 6. Observability baseline

Structured JSON logging (`structlog`) with a request-scoped correlation ID that's threaded through: API request → enqueued job → worker execution → any downstream capability/model calls — so a single `request_id` (or `workflow_execution_id` for async work) can trace a user action across both processes in the log stream. Full detail, including what's explicitly deferred to a later phase, in [11-deployment-architecture.md](11-deployment-architecture.md) §5.
