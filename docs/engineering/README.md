# ForgeAI — Engineering Handbook

Status: **Draft for review — Sprint 1 has not started.**
Scope: the repository foundation and process standards every future sprint builds on.

This is a distinct concern from [docs/architecture/](../architecture/): that directory records **what** ForgeAI is and **why** it's shaped that way (the system design). This directory records **how the team works** — repo layout, tooling, conventions, and process. The split mirrors a distinction most engineering orgs converge on eventually (system design docs vs. an engineering handbook); drawing it now avoids one directory becoming an unstructured mix of both concerns as it grows.

## How to read this set of documents

| #   | Document                                                     | Answers                                                                                                   |
| --- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| —   | [README.md](README.md)                                       | This index.                                                                                               |
| 01  | [Repository Scaffolding](01-repository-scaffolding.md)       | What's the as-built folder tree, and how does it reconcile with the Prompt-2 brief's suggested structure? |
| 02  | [Monorepo Strategy](02-monorepo-strategy.md)                 | pnpm + Turborepo + uv, vs. npm workspaces or Nx — why?                                                    |
| 03  | [Coding Standards](03-coding-standards.md)                   | TypeScript, Python, naming, imports, error handling, logging, comments — what's mandatory?                |
| 04  | [Git Strategy](04-git-strategy.md)                           | Branching, commits, PR review, versioning.                                                                |
| 05  | [Tooling Configuration](05-tooling-configuration.md)         | ESLint, Prettier, Ruff, mypy, Husky, lint-staged — what each does and why it's configured this way.       |
| 06  | [Environment Configuration](06-environment-configuration.md) | Every env var, by app and by environment, with security notes.                                            |
| 07  | [Docker Strategy](07-docker-strategy.md)                     | Compose structure, service separation, networking, volumes — **design only, no Dockerfiles yet.**         |
| 08  | [CI/CD Strategy](08-cicd-strategy.md)                        | Pipeline stages and gates — **design only, no workflow YAML yet.**                                        |
| 09  | [Testing Strategy](09-testing-strategy.md)                   | Unit, integration, e2e, workflow tests, and — distinctly — AI prompt tests.                               |
| 10  | [Logging & Observability](10-logging-observability.md)       | Structured logging, error reporting, audit/workflow logs, metrics, health endpoints.                      |
| 11  | [Security Standards](11-security-standards.md)               | The PR-level operationalization of `docs/architecture/12-security-architecture.md`.                       |
| 12  | [Documentation Standards](12-documentation-standards.md)     | What every feature must ship with — README updates, ADRs, diagrams.                                       |
| —   | [SPRINT_0_CHECKLIST.md](SPRINT_0_CHECKLIST.md)               | What must be true before Sprint 1 implementation begins.                                                  |

## Scope of this pass

Per the brief this was produced from: **no business logic, no authentication implementation, no database models, no APIs.** What follows is the engineering foundation only — real config where a config file is the deliverable (linting, formatting, workspace wiring), and design documentation where the brief explicitly deferred implementation (Docker, CI/CD). Where a folder is scaffolded but intentionally holds no code yet, its manifest says so directly rather than leaving an unexplained empty directory.

## What changed from the brief's example structure, in one place

The brief's example folder tree was offered as "improve if needed." It was improved in a few places, reconciled against the system architecture from the prior pass, and the full reasoning for each change is in [01-repository-scaffolding.md](01-repository-scaffolding.md) §3. Briefly, for anyone comparing the two trees side by side: `apps/worker` was kept (the brief's example omitted it, but Layer 2–5 execution structurally cannot run inside the API request cycle — see `docs/architecture/02-service-architecture.md`); `workflows`/`capabilities`/`memory` moved from `packages/` to `services/` as Python packages, since LangGraph/LangChain are Python, not TypeScript; the brief's `prompts` idea was kept and relocated there for the same reason; `docker/` was split into co-located Dockerfiles, a root-level `docker-compose.yml`, and `infra/docker/` for shared fragments only; a blanket top-level `tests/` became colocated tests per app plus a narrow `tests/e2e/` for genuine cross-system tests; and `tools/` was added as suggested, with an explicit boundary against `scripts/` so the two don't become duplicate dumping grounds.
