# ForgeAI

An AI-native Software Engineering Workspace. Users manage structured **Engineering Workflows** — Gather Requirements, Generate Architecture, Plan Sprint, Implement Feature, Review Pull Request, Fix Bug, Deploy Application, Investigate Production Issue — instead of prompting a chatbot. See [docs/architecture/README.md](docs/architecture/README.md) for the full system design.

> **Status:** pre-Sprint-1. This repository currently contains architecture documentation and engineering-foundation scaffolding only — no application code yet. See [docs/engineering/SPRINT_0_CHECKLIST.md](docs/engineering/SPRINT_0_CHECKLIST.md) for what remains before the actual implentation starts.

## Stack

Next.js/React/TypeScript/Tailwind/shadcn/ui/React Flow (frontend) · FastAPI/SQLAlchemy/PostgreSQL/Redis/Alembic (backend) · LangGraph/LangChain/Gemini (AI) · Docker/GitHub Actions (infra) · Railway/Vercel (hosting).

## Repository layout

```
apps/          web (Next.js) · api (FastAPI) · worker (Arq — workflow/capability execution)
packages/      ui · config · sdk (generated) · types      — shared TypeScript
services/      core · workflow_engine · capability_registry · model_router ·
               memory_engine · prompts · integrations      — shared Python, used by both api and worker
infra/         railway · github-actions · docker (shared/reusable fragments only)
docs/          architecture (system design) · engineering (standards & process) · adr
tests/e2e/     cross-system Playwright tests only — everything else is colocated per app/package
scripts/       one-off dev scripts (seed data, setup)
tools/         internal developer tooling more substantial than a one-off script
```

Full rationale for every folder: [docs/engineering/01-repository-scaffolding.md](docs/engineering/01-repository-scaffolding.md).

## Documentation map

| Directory                                | Answers                                                                                                                                                                                             |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [docs/architecture/](docs/architecture/) | What are we building, and why is it shaped this way? (5-layer system, workflow engine, data model, security model, roadmap)                                                                         |
| [docs/engineering/](docs/engineering/)   | How do we work? (repo scaffolding, monorepo strategy, coding standards, git strategy, tooling, environments, Docker/CI design, testing, observability, security standards, documentation standards) |
| [docs/adr/](docs/adr/)                   | Individually dated, one-decision-per-file records of choices made _after_ the initial architecture pass — see [docs/adr/0000-adr-template.md](docs/adr/0000-adr-template.md)                        |

## Getting started (once Sprint 1 lands runnable app code)

```bash
corepack enable                 # provides pnpm via the version pinned in package.json
pnpm install                    # installs JS/TS deps across apps/*, packages/* and sets up Husky hooks
uv sync                         # installs Python deps across apps/api, apps/worker, services/* (uv fetches Python 3.12 automatically)
pnpm dev                        # once apps/web has real source (Sprint 1+)
```

Environment variables: copy `apps/api/.env.example` to `apps/api/.env.local` and `apps/web/.env.example` to `apps/web/.env.local`, then fill in real values from your team's secret store — never commit a populated `.env` file. Full catalog: [docs/engineering/06-environment-configuration.md](docs/engineering/06-environment-configuration.md).

## Contributing

Branching, commit conventions, code review expectations, and coding standards: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Not yet decided — do not treat this repository as open-sourced or externally licensed until this section is updated.
