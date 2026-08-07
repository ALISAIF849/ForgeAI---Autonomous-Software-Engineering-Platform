# 03 — Coding Standards

These are mandatory, not suggestions — enforced by CI where a tool can check them (ESLint/Prettier/Ruff/mypy — [05-tooling-configuration.md](05-tooling-configuration.md)), by code review where a tool can't.

## 1. TypeScript

- **Strict mode always.** `packages/config/tsconfig.base.json` sets `strict: true` and `noUncheckedIndexedAccess: true` — every package extends it, none loosen it. An array/object index access that might be `undefined` must be handled, not assumed away.
- **No `any`.** Use `unknown` and narrow, or a precise generic. `@typescript-eslint/no-explicit-any` is an error, not a warning. If a truly dynamic shape is unavoidable (e.g., a webhook payload before validation), it gets a named type alias documenting _why_ it's loose, not a bare `any`.
- **Type imports are explicit:** `import type { Foo } from "..."` for type-only imports (`@typescript-eslint/consistent-type-imports`), so a bundler can always tell what's erasable at build time.
- **Prefer type inference for locals, explicit return types for exported functions.** A function other modules call should have its return type written out — it's documentation that breaks loudly if the implementation drifts from what callers expect.
- **No default exports** for anything except Next.js files that require them (`page.tsx`, `layout.tsx`). Named exports make refactors (rename, find-all-references) and auto-imports reliable in a way default exports don't.
- **Server state lives in react-query, never copied into Zustand.** Restated from [docs/architecture/09-frontend-architecture.md](../architecture/09-frontend-architecture.md) §3 because it's the single most common source of stale-UI bugs when violated — worth being explicit that this is a standard, not just an architectural note.

## 2. Python

- **Type hints on every function signature** — parameters and return type. `mypy --strict` enforces this repo-wide; there's no per-module opt-out.
- **Pydantic models for every data shape crossing a boundary** — API request/response, capability input/output, event payloads. A plain `dict` never crosses a module boundary as if it were structured data.
- **Async all the way down** in `apps/api`, `apps/worker`, and `services/*` — no blocking I/O calls inside async functions (blocking DB drivers, `requests` instead of an async HTTP client, unbounded `time.sleep`). `services/core` may contain sync, framework-independent domain logic where nothing is I/O-bound — that's fine, async has no benefit there.
- **No bare `except:`.** Catch specific exception types. A catch-all is only acceptable at a genuine system boundary (a top-level request handler that must always return a response) and must re-raise or log with full context, never silently swallow.
- **Dataclasses/Pydantic over dict-shaped "objects."** If something has a fixed shape and is passed around, it's a typed class, not a dict accessed by string keys scattered across the codebase.

## 3. Naming conventions

| What                       | Convention                                                           | Example                                                                |
| -------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| TS files (components)      | `PascalCase.tsx`                                                     | `WorkflowTimeline.tsx`                                                 |
| TS files (non-component)   | `kebab-case.ts`                                                      | `use-project-events.ts`                                                |
| TS variables/functions     | `camelCase`                                                          | `getWorkflowStatus`                                                    |
| TS types/interfaces        | `PascalCase`, no `I`/`T` prefix                                      | `WorkflowExecution`, not `IWorkflowExecution`                          |
| Python files/modules       | `snake_case.py`                                                      | `workflow_executor.py`                                                 |
| Python classes             | `PascalCase`                                                         | `WorkflowExecutor`                                                     |
| Python functions/variables | `snake_case`                                                         | `get_workflow_status`                                                  |
| Python constants           | `UPPER_SNAKE_CASE`                                                   | `DEFAULT_TIMEOUT_SECONDS`                                              |
| DB tables/columns          | `snake_case`, plural table names                                     | `workflow_executions.started_by`                                       |
| Env vars                   | `UPPER_SNAKE_CASE`, `NEXT_PUBLIC_` prefix only when genuinely public | see [06-environment-configuration.md](06-environment-configuration.md) |

## 4. Folder naming

`kebab-case` for every directory, no exceptions, in both the TS and Python trees — including Python packages at the folder level (`services/workflow_engine` is the one deliberate exception: the _importable Python package name_ must be `snake_case` to be a valid Python identifier, so service folders use `snake_case` to match the package they contain; everything else — `apps/`, `packages/`, feature folders under `apps/web/features/`, doc folders — is `kebab-case`). If a folder name and its contained package/module name would otherwise disagree, the importability constraint wins.

## 5. API naming (REST)

- Resource paths are plural nouns: `/projects`, `/workflow-executions`, not `/project`, `/getProjects`.
- Nesting reflects real ownership, capped at two levels: `/projects/{id}/requirements`, not deeper chains — a third level (`/projects/{id}/requirements/{id}/comments`) becomes its own top-level resource with a filter query param instead (`/comments?requirement_id=...`), because deeply nested REST paths get unwieldy to version and cache.
- Actions that aren't pure CRUD are verbed sub-resources, not query params: `POST /workflow-executions/{id}/resume`, not `PATCH /workflow-executions/{id}?action=resume`.
- Every response envelope shape and error shape is consistent across modules — see [docs/architecture/08-api-design.md](../architecture/08-api-design.md) §6 (RFC 7807-style errors). A module does not invent its own error format.

## 6. Environment variables

Full catalog in [06-environment-configuration.md](06-environment-configuration.md). The naming rule: `UPPER_SNAKE_CASE`, namespaced by concern when ambiguous (`RATE_LIMIT_DEFAULT_PER_MINUTE`, not `LIMIT`), and — the one rule that's a security control, not a style preference — `NEXT_PUBLIC_` is used if and only if the value is genuinely safe to ship to every browser. It is never added to satisfy a type checker or "just in case."

## 7. Imports

- **TypeScript:** absolute imports from workspace root (`@forgeai/ui`, `@forgeai/types`) for cross-package imports; relative imports (`./`, `../`) within a single package/feature only — never a relative import that reaches across a package boundary (`../../../packages/ui/...`). Import order enforced by ESLint: external packages, then internal workspace packages, then relative — each group alphabetized, blank line between groups.
- **Python:** absolute imports from the package root (`from forgeai_workflow_engine.graphs import ...`), enforced/sorted by Ruff's isort integration (`known-first-party` is configured per package in the root `pyproject.toml`). No wildcard imports (`from x import *`) anywhere.
- **No cross-module-boundary imports that skip the public interface** — a module reaches another module's `service.py`, never its `repository.py` or ORM models directly. This is the import-boundary rule from [docs/architecture/01-repository-structure.md](../architecture/01-repository-structure.md) §4, enforced by CI lint once implemented in Sprint 1 tooling.

## 8. Error handling

- **Errors are typed, not stringly-typed.** Domain-specific exception classes per module (`WorkflowDefinitionNotActive`, `ApprovalAlreadyDecided`), mapped centrally to HTTP status codes — never `raise Exception("something went wrong")`, and never a generic `HTTPException(400, "bad request")` with no machine-readable error code for the frontend to branch on.
- **Never swallow an error silently.** If a caught exception isn't re-raised, it's logged with full context (what operation, what IDs, what input) at a level that will actually be seen (`error`, not `debug`).
- **User-facing error messages never leak internals** — no stack traces, no raw DB error text, no internal file paths in a production API response. Full detail (what a client and internal logs each see) is a body an exception handler middleware owns once, not something every route reimplements.
- **Frontend:** every data-fetching hook has an explicit error state the UI renders something for — no unhandled promise rejections, no silent `catch(() => {})`.

## 9. Logging

- **Structured, always** — `structlog` (Python) / `pino` (TS), key-value fields, never string-concatenated log lines that need regex to parse later. Full design: [10-logging-observability.md](10-logging-observability.md).
- **Every log line inside a request or job carries the correlation ID** (`request_id` or `workflow_execution_id`) — this is what makes a log stream traceable across `apps/api` → `apps/worker` → an LLM/external call, and it's the reason ad hoc `print()`/`console.log()` debugging is disallowed in committed code (`no-console` is an ESLint error beyond `warn`/`error`; Python has no `print()` outside scripts/tools).
- **Never log a secret** — API keys, tokens, password hashes, raw JWTs. If a payload might contain one (e.g., logging a full request body), it goes through a redaction helper, not straight to the log sink.

## 10. Comments

- **Default to none.** Well-named functions/variables and small functions are the primary documentation. A comment that restates what the code already says (`// increment counter`) is noise and gets removed in review.
- **Write one only when the _why_ isn't obvious from the code** — a non-obvious constraint, a workaround for a specific upstream bug (link the issue), an invariant that would be easy to accidentally break. This mirrors the standard this entire project is being built under, applied consistently rather than as a special case for AI-authored code.
- **No commented-out code** in anything merged to `main`. Git history is the record of what used to be there; a commented-out block is not.

## 11. Documentation

Per-feature documentation requirements (what must accompany a PR, when an ADR is required, when a diagram is required) are their own standard, not folded in here — see [12-documentation-standards.md](12-documentation-standards.md).
