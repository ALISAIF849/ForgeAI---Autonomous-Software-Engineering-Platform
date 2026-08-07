# Sprint 0 Checklist

Everything below must be true before Sprint 1 (first real implementation) begins. Grouped by who/what it depends on — the repo-scaffolding group is done as of this pass; everything else requires either a human decision, an external account, or tooling this pass deliberately didn't install/run.

## Repository foundation — done in this pass

- [x] Monorepo scaffolded: `apps/`, `packages/`, `services/`, `infra/`, `docs/`, `scripts/`, `tools/`, `tests/e2e/`
- [x] Root workspace config: `package.json`, `pnpm-workspace.yaml`, `turbo.json`, root `pyproject.toml` (uv workspace)
- [x] Every `packages/*` and `services/*` member has a real manifest, wired via workspace-internal dependencies
- [x] Linting/formatting configured: ESLint (flat config), Prettier, Ruff (lint + format), mypy (strict)
- [x] Git hooks configured: Husky (`pre-commit` → lint-staged, `commit-msg` → commitlint), covering **both** TS and Python
- [x] `.env.example` for `apps/web` and `apps/api`/`apps/worker`, documented in [06-environment-configuration.md](06-environment-configuration.md)
- [x] `.github/PULL_REQUEST_TEMPLATE.md`, `.github/CODEOWNERS` (placeholder handles — see below)
- [x] `docs/engineering/` handbook (this document set) and `docs/adr/` (template + ADR-0001)
- [x] Local git repository initialized (`main` branch, no commits yet — see below)

## Requires a human decision or external account — not yet done

- [ ] **Replace placeholder handles in `.github/CODEOWNERS`** with real GitHub usernames/teams
- [ ] **Create the GitHub repository** (or confirm the intended one) and push this history to it
- [ ] **Configure branch protection on `main`** per [04-git-strategy.md](04-git-strategy.md) §5 (requires the GitHub remote to exist first)
- [ ] **Decide and add a license** — `README.md`'s License section is intentionally left unresolved; this is almost certainly proprietary for a VC-backed SaaS product, but that's a decision for the team/counsel, not an assumption to bake in silently
- [ ] **Provision Railway project** (Postgres + Redis + `api`/`worker` services, per [docs/architecture/11-deployment-architecture.md](../architecture/11-deployment-architecture.md))
- [ ] **Provision Vercel project** for `apps/web`
- [ ] **Obtain a Google Gemini API key** (dev-tier to start, per [06-environment-configuration.md](06-environment-configuration.md) §2)
- [ ] **Register a GitHub OAuth App** (dev + staging + production — separate apps per environment, per [06-environment-configuration.md](06-environment-configuration.md) §2)
- [ ] **Create a Sentry project** (or confirm the alternative chosen — [10-logging-observability.md](10-logging-observability.md) §2)
- [ ] **Set up a team secret-sharing channel** (password manager team vault or equivalent) for distributing real `.env.local` values — never Slack/email in plaintext
- [ ] **Populate Railway's and Vercel's environment variable stores** with real staging values (production values only once there's something to deploy)

## Requires tooling this pass didn't install/run

- [ ] `corepack enable` (or `npm i -g pnpm`) — pnpm itself isn't installed globally in this environment yet, only resolvable via corepack
- [ ] `pnpm install` at the repo root (also activates Husky hooks via the `prepare` script)
- [ ] `uv sync` at the repo root (uv will fetch Python 3.12 automatically per `.python-version` — the system's Python 3.10 is not used)
- [ ] Resolve real current versions for pinned tooling (`pnpm up --latest`, `uv lock --upgrade`) rather than trusting the indicative versions written during this pass — see [05-tooling-configuration.md](05-tooling-configuration.md) §6
- [ ] Verify `pnpm lint`, `uv run ruff check .`, `uv run mypy .` all run cleanly against the current (empty) scaffold — a sanity check that the configs themselves are valid before anyone builds on top of them

## Requires implementing what this pass deliberately left as design-only

- [ ] Write the actual `Dockerfile`s (`apps/web`, `apps/api`, `apps/worker`) and `docker-compose.yml`, per [07-docker-strategy.md](07-docker-strategy.md)
- [ ] Implement the actual `.github/workflows/*.yml` files, per [08-cicd-strategy.md](08-cicd-strategy.md)
- [ ] Get a trivial PR (e.g., this checklist item itself) green through the full implemented CI pipeline, as proof the pipeline design actually works before real feature PRs depend on it

## Process sign-off

- [ ] `docs/architecture/` (prior pass) reviewed and accepted by the team
- [ ] `docs/engineering/` (this pass) reviewed and accepted by the team
- [ ] ADR-0001 (recording architecture decisions) merged as the first real commit through the real PR process — i.e., the process documents itself working before Sprint 1 starts
- [ ] Everyone who'll write code in Sprint 1 has read [CONTRIBUTING.md](../../CONTRIBUTING.md) and [03-coding-standards.md](03-coding-standards.md)

## Explicitly not blocking Sprint 1

Per [docs/architecture/13-development-roadmap.md](../architecture/13-development-roadmap.md), Phase 4 items (SSO/SAML, custom RBAC roles, dedicated observability stack, SOC 2 groundwork) are not Sprint 0 requirements — listed there, not repeated here, so this checklist stays focused on what's actually blocking, not a re-statement of the full roadmap.
