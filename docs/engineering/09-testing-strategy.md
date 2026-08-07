# 09 — Testing Strategy

## 1. Philosophy

Tests exist to make refactors and AI-assisted changes safe, not to hit a coverage number. Two categories in this system need a genuinely different testing _philosophy_ from conventional CRUD-app testing — workflow orchestration and AI capability output — because "correct" doesn't mean "exact match" for either. Both get their own treatment below (§4, §5) rather than being squeezed into a generic unit/integration/e2e pyramid that doesn't actually fit them.

## 2. Unit tests

- **Scope:** a single function/class/service method, dependencies mocked or faked.
- **TS:** Vitest. **Python:** pytest + pytest-asyncio.
- Every `service.py` is tested against a fake repository, not a real database — this is what [docs/architecture/10-backend-architecture.md](../architecture/10-backend-architecture.md) §2's dependency-injection design is _for_: business logic testable without infrastructure.
- `services/*` engine packages (workflow_engine, capability_registry, model_router, memory_engine) are unit-tested standalone, with no FastAPI app and no queue running — validating [docs/architecture/01-repository-structure.md](../architecture/01-repository-structure.md) §3's premise that they're independently testable.

## 3. Integration tests

- **Scope:** a real Postgres instance (via testcontainers), a real repository, real queries.
- Validates: query correctness, Alembic migration round-trips (`upgrade` then `downgrade` doesn't corrupt state), and — specifically — Row-Level Security policy behavior. An RLS test that proves a cross-tenant query returns zero rows even when application-layer filtering is bypassed is not optional coverage — it's the actual proof that [docs/architecture/07-database-schema.md](../architecture/07-database-schema.md) §4's defense-in-depth claim holds, not just an assertion in a doc.

## 4. Workflow tests — deterministic, because orchestration logic should be

A `WorkflowDefinition`'s _sequencing_ (does it reach the right node next, does it pause at the approval gate, does it resume correctly from a checkpoint) is tested against a **mocked Model Router** that returns fixed, deterministic fake capability outputs — never real LLM calls. This is a deliberate split: whether the _graph_ behaves correctly is a software-correctness question with a definite right answer, testable exactly like any other state machine; whether a _capability's actual output_ is good is a completely different question (§5) that a deterministic test can't meaningfully answer anyway. Mixing the two — testing graph logic against real model calls — would make workflow tests slow, flaky, expensive, and only accidentally test orchestration, since a failure could mean either "the graph is wrong" or "the model said something unexpected" with no way to tell which from the test result alone.

Every registered `WorkflowDefinition` is additionally checked at compile/registration time (not just in a hand-written test) for the approval-gate rule from [docs/architecture/03-workflow-engine.md](../architecture/03-workflow-engine.md) §5 — this runs in CI as a contract check ([08-cicd-strategy.md](08-cicd-strategy.md) §1), so a workflow definition that omits a required approval gate fails the build automatically, not just when someone happens to write a test for that specific case.

## 5. AI prompt tests — regression signal, not correctness proof

LLM output isn't deterministic, so "assert exact output" tests don't apply. Three different techniques, used together, each answering a different question:

1. **Schema-conformance tests** — does a capability's output always validate against its declared `output_schema` ([docs/architecture/04-capability-registry.md](../architecture/04-capability-registry.md) §2), across a representative range of inputs? This _is_ a hard pass/fail, because the schema is a hard contract regardless of content quality.
2. **Recorded-response replay** (cassette-style) — record a real model response once, replay it in CI on every subsequent run. This keeps CI fast, free, and deterministic for testing _prompt template structure_ (did a prompt-template edit break how the response gets parsed) without hitting the live provider on every PR. Cassettes are refreshed deliberately (a scheduled job, not every CI run) against the live provider to catch drift in how the model responds over time — an intentionally separate, lower-frequency check from the main CI loop.
3. **Golden-set regression checks** — a fixed set of representative inputs with human-reviewed acceptance criteria (a rubric, or an LLM-as-judge assertion scoring against that rubric), run periodically rather than on every PR. **This is explicitly a directional/regression signal, not a correctness proof** — a golden-set pass doesn't mean the output is right, only that it hasn't measurably regressed against the baseline. Treating it as anything stronger than that would misrepresent what it actually checks, which matters given principle #6 (explainable AI decisions) — the testing story has to be honest about its own limits, not just the product's.

## 6. End-to-end tests

Playwright, in `tests/e2e/` (top-level, per [01-repository-scaffolding.md](01-repository-scaffolding.md) §3.4 — the one exception to "tests are colocated"). A small, deliberately not comprehensive set of golden-path flows through the real UI against a real (test) backend — e.g., create project → gather requirements → generate architecture → approve. These are the slowest, most expensive tests in the suite; kept few and high-value rather than attempting UI-level coverage of every branch, which unit/integration tests are far cheaper to provide.

## 7. What runs where

| Test type                      | Runs in pre-commit?                                           | Runs in CI (`test.yml`)?                          | Runs on a schedule?                          |
| ------------------------------ | ------------------------------------------------------------- | ------------------------------------------------- | -------------------------------------------- |
| Unit                           | No (too slow for every commit at scale, though fine early on) | Yes, every PR                                     | —                                            |
| Integration                    | No                                                            | Yes, every PR                                     | —                                            |
| Workflow (mocked)              | No                                                            | Yes, every PR                                     | —                                            |
| AI prompt — schema conformance | No                                                            | Yes, every PR                                     | —                                            |
| AI prompt — cassette replay    | No                                                            | Yes, every PR                                     | Cassettes refreshed on a schedule (see §5.2) |
| AI prompt — golden-set         | No                                                            | No (too slow/costly for every PR)                 | Yes, periodic                                |
| E2E                            | No                                                            | Yes, every PR (or at minimum pre-merge to `main`) | —                                            |
