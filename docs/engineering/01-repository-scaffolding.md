# 01 — Repository Scaffolding

This document has two jobs: show the as-built folder tree and package catalog, and reconcile it explicitly against the folder structure suggested in the Prompt-2 brief (offered as "improve if needed" — so the differences are spelled out here, not silently applied).

## 1. As-built tree

```
forgeai/
├── apps/
│   ├── web/                       # Next.js — see §5
│   ├── api/                       # FastAPI — see §4
│   └── worker/                    # Arq — job handlers mirror apps/api's module boundaries,
│                                   #   but hold no HTTP concerns at all
├── packages/                      # TypeScript, pnpm workspace members
│   ├── ui/                        # shadcn/ui-based design system
│   ├── config/                    # shared tsconfig base (ESLint/Tailwind config land here too
│   │                               #   once apps/web exists for real — see 05-tooling-configuration.md)
│   ├── sdk/                       # generated OpenAPI client — src/generated/ is never hand-edited
│   └── types/                     # shared TS types NOT covered by the generated SDK
├── services/                      # Python, uv workspace members — shared by apps/api and apps/worker
│   ├── core/                      # domain entities, ORM models, DB session/base, shared utilities
│   ├── workflow_engine/           # Layer 2
│   ├── capability_registry/       # Layer 3
│   ├── model_router/              # Layer 4
│   ├── memory_engine/             # Layer 5
│   ├── prompts/                   # versioned prompt templates — see §3.2
│   └── integrations/              # GitHub / Railway / Vercel clients
├── infra/
│   ├── docker/                    # shared/reusable Docker fragments only — see §3.3
│   ├── railway/                   # Railway service configs
│   └── github-actions/            # reusable workflow fragments (composite actions, once CI exists)
├── docs/
│   ├── architecture/              # system design (prior pass)
│   ├── engineering/                # this handbook
│   └── adr/                         # dated, one-decision-per-file records
├── tests/
│   └── e2e/                        # cross-system Playwright tests ONLY — see §3.4
├── scripts/                        # one-off dev scripts: seed data, local setup
├── tools/                           # more substantial internal tooling — see §3.5
├── .github/
│   ├── workflows/                    # currently a placeholder — see 08-cicd-strategy.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── CODEOWNERS
├── .husky/                           # pre-commit, commit-msg hooks
└── [root config — see §2]
```

Root-level: `docker-compose.yml` (not yet written — design only, see [07-docker-strategy.md](07-docker-strategy.md)), `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `pyproject.toml`, `eslint.config.mjs`, `.prettierrc.json`, `.lintstagedrc.json`, `commitlint.config.js`, `.gitignore`, `.editorconfig`, `.gitattributes`, `.nvmrc`, `.python-version`, `README.md`, `CONTRIBUTING.md`.

## 2. Package catalog

| Package             | Path                           | Language         | Responsibility                       | Depends on (internal)                      |
| ------------------- | ------------------------------ | ---------------- | ------------------------------------ | ------------------------------------------ |
| web                 | `apps/web`                     | TS / Next.js     | User-facing app                      | ui, types, sdk, config                     |
| api                 | `apps/api`                     | Python / FastAPI | HTTP/WS surface                      | core                                       |
| worker              | `apps/worker`                  | Python / Arq     | Workflow & capability execution      | core                                       |
| ui                  | `packages/ui`                  | TS               | Design system                        | types                                      |
| config              | `packages/config`              | TS               | Shared base config                   | —                                          |
| sdk                 | `packages/sdk`                 | TS               | Generated API client                 | —                                          |
| types               | `packages/types`               | TS               | Shared types (non-generated)         | —                                          |
| core                | `services/core`                | Python           | Domain entities, ORM models, DB base | —                                          |
| workflow_engine     | `services/workflow_engine`     | Python           | Layer 2                              | core, memory_engine                        |
| capability_registry | `services/capability_registry` | Python           | Layer 3                              | core, model_router, memory_engine, prompts |
| model_router        | `services/model_router`        | Python           | Layer 4                              | core                                       |
| memory_engine       | `services/memory_engine`       | Python           | Layer 5                              | core                                       |
| prompts             | `services/prompts`             | Python           | Prompt templates                     | —                                          |
| integrations        | `services/integrations`        | Python           | External API clients                 | core                                       |

Every row above has a real manifest in the repo (`package.json` or `pyproject.toml`) declaring these dependencies via workspace protocol (`workspace:*` / `{ workspace = true }`), so `pnpm install` / `uv sync` resolve the internal dependency graph immediately — this isn't just a table, it's enforced by the actual workspace config the moment real source lands in Sprint 1.

## 3. Reconciliation with the brief's example tree

The brief's tree was explicitly offered as a starting point to improve on. Here's every place this scaffold differs from it, and why — nothing below is a silent change.

### 3.1 `apps/worker` — kept, not in the brief's example

The brief's example listed only `apps/web` and `apps/api`. The architecture from the prior pass ([docs/architecture/02-service-architecture.md](../architecture/02-service-architecture.md) §3) established that workflow and capability execution — anything that calls an LLM or runs for more than a request/response cycle — must run outside the API process, in a separate worker. Dropping `apps/worker` now would mean either blocking HTTP requests on LLM calls (unacceptable latency, and it prevents the "approval gate costs nothing while waiting" property the Workflow Engine depends on) or re-adding the worker later as a disruptive restructure. It's kept.

### 3.2 `packages/workflows`, `packages/capabilities`, `packages/memory` → relocated to `services/`, as Python

The brief's example put `workflows`, `capabilities`, and `memory` under `packages/` — which, by monorepo convention (and by the sibling entries `ui`, `shared`, `config` in the same list), means TypeScript. But the AI orchestration stack is LangGraph/LangChain — Python, per the stack decided in the prior pass. Implementing the Workflow Engine, Capability Registry, and Memory Engine as TypeScript packages would contradict that. What actually belongs in TypeScript is the **type/contract surface** of these concepts for the frontend to render against (a workflow's node graph shape, a capability's input schema) — and that already has a home: `packages/types` (or, once generated, `packages/sdk`, since these types are ultimately mirrors of the backend's Pydantic schemas). A dedicated `packages/workflows` holding only re-exported types would be a package whose entire contents duplicate what `packages/sdk`/`packages/types` already provide — an extra layer of indirection with nothing of its own in it. So: the real implementations live in `services/workflow_engine`, `services/capability_registry`, `services/memory_engine` (Python, matching the architecture), and their TS-facing shape flows through the SDK like every other backend concept.

`prompts`, however, was a genuinely good addition not present in the original architecture pass — externalizing prompt templates as versioned, independently-reviewable artifacts (rather than inline strings inside capability code) is a real best practice for AI systems: it lets a prompt-wording change show up as a focused diff distinct from a logic change, and it's a precondition for later A/B testing prompts without touching capability code at all. It's adopted, relocated to `services/prompts` for the same Python-not-TypeScript reason as the other three.

### 3.3 `docker/` (flat, top-level) → split three ways

A single top-level `docker/` folder was in the brief's example. In practice, Docker artifacts have three different natural homes depending on how often they're touched and by whom:

- **`docker-compose.yml` at the repo root**, not nested — because `docker compose up` from the repo root is the universal, muscle-memory entry point for "give me the whole local stack," and burying it in a subfolder just adds friction to the single most common local-dev command.
- **A `Dockerfile` co-located with each app** (`apps/web/Dockerfile`, `apps/api/Dockerfile`, `apps/worker/Dockerfile`, once written) — because a Dockerfile is tightly coupled to the app it packages (its build steps mirror that app's own dependency/build tooling), and co-location means whoever changes an app's dependencies is looking at its Dockerfile in the same diff, not hunting for it in a separate top-level folder.
- **`infra/docker/`** for anything genuinely shared across multiple images (a common base image, reusable build-stage snippets) — this is the only piece that actually deserves a shared top-level home, because it's the only piece that's genuinely cross-cutting rather than owned by one app.

Full detail: [07-docker-strategy.md](07-docker-strategy.md).

### 3.4 Top-level `tests/` (for everything) → colocated, with a narrow `tests/e2e/` exception

The brief's example put a single top-level `tests/` folder alongside `apps/`, `packages/`, etc. A blanket top-level test folder covering every app and package is a weaker choice at this scale for two concrete reasons: it separates a test from the code it verifies (harder to find, easier to let drift when the source moves and the test doesn't), and it doesn't cleanly support a polyglot repo where the TS side and Python side use entirely different test runners and discovery conventions (vitest/Playwright vs. pytest) — a shared folder would just end up re-partitioned by language inside itself anyway. Unit and integration tests are colocated per app/package (`apps/api/tests/`, `apps/web/**/*.test.tsx`) instead — full rationale already established in [docs/architecture/10-backend-architecture.md](../architecture/10-backend-architecture.md) §5.

The one kind of test that genuinely doesn't belong to any single app is a full end-to-end browser test exercising the real running stack across web+api+worker together — that's kept at the top level, narrowly, as `tests/e2e/`, so it's not falsely homed under `apps/web` when it's actually testing the whole system.

### 3.5 `tools/` — adopted, with a boundary against `scripts/`

Not in the original architecture pass; a reasonable addition. To keep it from becoming a second, competing dumping ground alongside `scripts/`: **`scripts/`** is for small, single-purpose, rarely-changed dev scripts (seed data, local environment setup) that don't need their own dependency management or tests. **`tools/`** is for anything more substantial — internal CLIs, codegen tooling, custom lint rules — that would benefit from its own manifest, dependencies, and tests, but isn't a product package. If something in `scripts/` grows dependencies or tests of its own, that's the signal it should move to `tools/`, not stay and accumulate.

### 3.6 `shared` → not adopted as a package name; consolidated into `types`

The brief's example included a `packages/shared`. It wasn't created as a separate package — the architecture pass already established `packages/types` for exactly this purpose (shared TS types), and a second, more vaguely-named `shared` package invites becoming an unstructured catch-all over time (a well-known monorepo anti-pattern: a generically-named "shared"/"common"/"utils" package tends to accumulate unrelated code precisely because its name doesn't constrain what belongs in it). If a genuine need for shared _runtime_ utility functions — not types — emerges later, it should get an equally specific name (`packages/dates`, `packages/formatting`, whatever the actual content is) rather than a catch-all.

### 3.7 `infrastructure/` vs. `infra/` — kept as `infra/`

Purely a naming difference from the brief's `infrastructure/`. Kept as `infra/` for consistency with the prior architecture pass, which already used and documented this name — renaming now would create a needless discrepancy between the two document sets for no functional benefit. Both spellings are common in the wild; this isn't a substantive decision either way.

## 4. Backend internal structure (`apps/api`)

Operationalizes [docs/architecture/10-backend-architecture.md](../architecture/10-backend-architecture.md) with the concrete folder names the brief asked for explicitly (Dependencies and Middleware weren't broken out as their own top-level concepts in the prior pass — they are here):

```
apps/api/src/forgeai_api/
├── main.py                # app factory, middleware/router registration
├── core/
│   ├── config.py            # Settings (pydantic-settings) — env vars land here, see 06-environment-configuration.md
│   ├── security.py            # password hashing, JWT issuance/verification
│   ├── logging.py               # structlog configuration
│   └── exceptions.py              # base exception types + global handler registration
├── dependencies/             # FastAPI Depends() providers: DB session, current user/org,
│                              #   RLS-scope binder — the resolution path referenced in
│                              #   docs/architecture/08-api-design.md §4
├── middleware/                 # request-ID injection, RLS session-var binding, rate limiting, CORS
├── db/
│   ├── session.py                # async session factory
│   └── base.py                     # declarative base (actual models live in services/core — see below)
├── modules/                          # one per bounded context: workspace, requirements,
│   └── <bounded_context>/             #   architecture, workflows, capabilities, sprints,
│       ├── router.py                   #   conversations, approvals, deployments,
│       ├── service.py                   #   notifications, audit
│       ├── repository.py
│       ├── schemas.py
│       └── exceptions.py
└── events/                                # outbox relay, SSE broadcaster
```

**Where "Domain" and "Models" live:** both in `services/core`, not `apps/api` — because `apps/worker` needs the same ORM models and domain entities, and duplicating them between two processes is exactly the drift risk [docs/architecture/01-repository-structure.md](../architecture/01-repository-structure.md) §3 was written to avoid. Within `services/core`, the two are kept distinct: `domain/` holds framework-independent entities, value objects, and enums (business rules that don't need a database — e.g., what state transitions a workflow status allows); `models/` holds the SQLAlchemy ORM classes that map those concepts to Postgres tables. This gives a real Domain/Models split without going as far as a full hexagonal mapper layer between them — for CRUD-shaped entities the ORM model _is_ the practical domain representation, and adding a translation layer everywhere would be exactly the kind of premature abstraction the project's own engineering standards reject. **Both folders are scaffolded empty** — this prompt's rules exclude generating database models, so `services/core/models/` stays empty until Sprint 1.

**Where "Workflows" and "Capabilities" live:** the brief's item 3 groups these under "Backend Architecture" folders. They're deliberately _not_ nested inside `apps/api` — they're `services/workflow_engine` and `services/capability_registry`, for the same shared-with-worker reason as Domain/Models above (§3.1 in this document, and [docs/architecture/01-repository-structure.md](../architecture/01-repository-structure.md) §3). `apps/api/modules/workflows/` and `apps/api/modules/capabilities/` do still exist — but they're the thin HTTP layer (start/resume/cancel/list endpoints) that calls into `services/workflow_engine`/`services/capability_registry`, not where the orchestration logic itself lives.

## 5. Frontend internal structure (`apps/web`)

Operationalizes [docs/architecture/09-frontend-architecture.md](../architecture/09-frontend-architecture.md) with the concrete folder names the brief asked for explicitly, refining that document's flat `components/` split into a feature-colocation structure (an improvement worth calling out on its own merits, not only because it was requested — see the amendment note in that document):

```
apps/web/
├── app/                      # App Router — routes only: page.tsx, layout.tsx, loading.tsx, error.tsx.
│                               #   No business logic lives directly in a route file.
├── components/                 # Shared, presentational components used by 2+ features
│                                #   (beyond packages/ui's primitives). If a component is only
│                                #   used by one feature, it belongs in that feature folder instead.
├── features/                     # Feature-scoped modules: workflow-timeline/, architecture-viewer/,
│   └── <feature>/                  #   sprint-board/, activity-feed/, requirement-wizard/ — each may
│       ├── components/               #   contain its own components/hooks/services, colocated rather
│       ├── hooks/                      #   than scattered across global folders (see 09-frontend-
│       └── services/                     #   architecture.md's amendment note)
├── hooks/                       # Cross-feature reusable hooks (useDebounce, useMediaQuery)
├── services/                      # API-calling layer: thin wrappers around packages/sdk +
│                                    #   react-query hook factories (renamed from the prior pass's
│                                    #   lib/api-client — see amendment note); includes auth/ and
│                                    #   realtime/ (SSE client) subfolders
├── stores/                         # zustand — ephemeral client UI state ONLY, never server state
│                                    #   (docs/architecture/09-frontend-architecture.md §3)
├── providers/                        # React context providers (theme, query client, session) —
│                                      #   composed once in app/layout.tsx
├── layouts/                            # Shared layout shells (workspace shell, marketing shell)
├── types/                                # Local TS types not in packages/types or packages/sdk
└── lib/utils/                              # Framework-agnostic utilities (formatting, class-name merge)
```

`components/` vs. `features/*/components/` is the one distinction worth being disciplined about as the app grows: global `components/` is for things genuinely reused across unrelated features (a data table, a confirmation dialog); anything specific to one feature's UI stays inside that feature's folder so deleting or substantially changing a feature doesn't require hunting through an unrelated global folder for its leftover pieces.
