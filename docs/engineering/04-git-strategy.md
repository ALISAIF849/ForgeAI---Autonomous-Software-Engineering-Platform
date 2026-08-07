# 04 — Git Strategy

## 1. Branching model: trunk-based, not GitFlow

- `main` is always deployable and auto-deploys to staging on every merge ([docs/architecture/11-deployment-architecture.md](../architecture/11-deployment-architecture.md) §3). There is no long-lived `develop` branch.
- Short-lived feature branches off `main`: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`, `refactor/<slug>`, `ci/<slug>` — merged back via PR, squash-merged for a linear, one-commit-per-change history on `main`.
- No long-lived `release/*` or `hotfix/*` branches. A production hotfix is a normal `fix/*` branch off `main`, going through the same PR + staging-then-production-promotion path — just prioritized, not structurally different.

**Why not GitFlow:** GitFlow's extra branch types (`develop`, `release/*`, `hotfix/*`) earn their overhead when a team needs to coordinate multiple release versions in flight at once — e.g., shipping a patch to v1.x while v2.0 is still being developed on `develop`. ForgeAI has one production version, continuously deployed; there's nothing for those extra branches to coordinate. Adopting GitFlow here would add process weight with no corresponding problem it solves — worth stating explicitly since GitFlow is still the default mental model a lot of engineers reach for.

## 2. Commit convention: Conventional Commits, enforced

`type(scope): summary`, enforced by commitlint on every commit via the Husky `commit-msg` hook ([commitlint.config.js](../../commitlint.config.js)):

- **Types:** `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `perf`.
- **Scope:** the package/service name that changed (`api`, `worker`, `workflow-engine`, `web`, `ui`, `docs`, ...) — the scope list is an explicit enum tied to real package names (§2 of [01-repository-scaffolding.md](01-repository-scaffolding.md)), not free text, so `git log --grep` and changelog generation can reliably filter by "what part of the system changed."
- **Why this is enforced, not just encouraged:** conventional commits are what makes automated changelog generation and semver bumping (§4) possible later without someone hand-writing a changelog from memory — the discipline has to start on commit one, since retrofitting commit history is not possible.

## 3. Pull requests

Every change to `main` goes through a PR — no direct pushes to `main` (enforced by branch protection once the GitHub repo exists, see [SPRINT_0_CHECKLIST.md](SPRINT_0_CHECKLIST.md)). The PR template ([.github/PULL_REQUEST_TEMPLATE.md](../../.github/PULL_REQUEST_TEMPLATE.md)) is the enforced checklist; this document explains the reasoning behind the items reviewers actually push back on:

### Code review checklist (what a reviewer is checking for beyond "does this work")

1. **Tests included and passing** — not just "tests exist," but tests that would actually fail if the change were wrong (a test that can't fail isn't coverage).
2. **New/changed queries are tenant-scoped.** Any new repository method touching a table with `org_id`/`project_id` must filter on it explicitly — this is the single highest-consequence category of bug in the whole system ([docs/architecture/07-database-schema.md](../architecture/07-database-schema.md) §4), and RLS is a second layer, not a reason to skip checking the first.
3. **No secrets in the diff.** Scan for anything that looks like a key/token/connection string, even in a file that looks innocuous (a fixture, a `.env`-shaped file that shouldn't be committed at all).
4. **Workflow definition changes carry an approval gate on any irreversible action.** CI's approval-gate lint catches this mechanically once implemented ([docs/architecture/03-workflow-engine.md](../architecture/03-workflow-engine.md) §5) — review still checks it, because a lint rule catching a missing gate is a safety net, not a substitute for a human noticing the workflow shouldn't have reached that point unattended in the first place.
5. **Capability schema changes are backward-compatible or version-bumped**, per [docs/architecture/04-capability-registry.md](../architecture/04-capability-registry.md) §3 — an in-flight workflow execution should never break because a capability it depends on changed shape underneath it.
6. **Docs updated where the standard requires it** — see [12-documentation-standards.md](12-documentation-standards.md) for exactly when.
7. **No skipped hooks/checks** (`--no-verify`, disabled lint rules inline without justification) without a documented reason in the PR description.

## 4. Versioning strategy

Two independent versioning concepts exist in this system — worth distinguishing explicitly, since conflating them is an easy mistake:

- **The application's release version** — SemVer (`v0.x.y` during initial development, `v1.0.0` at first general-availability release), tracked as git tags cut from `main` at deploy time, with a `CHANGELOG.md` generated from Conventional Commit history (tooling choice — e.g., `release-please` or `changesets` — deferred to when CI/CD is actually implemented, see [08-cicd-strategy.md](08-cicd-strategy.md); not decided yet because it depends on the CI implementation this pass explicitly excludes).
- **A `WorkflowDefinition`'s or `Capability`'s own version** — independent semver per definition, already established in the architecture pass ([docs/architecture/03-workflow-engine.md](../architecture/03-workflow-engine.md) §7, [docs/architecture/04-capability-registry.md](../architecture/04-capability-registry.md) §3), tracking that specific definition's contract, not the application build it ships in. A single application release can ship several unrelated workflow-definition version bumps, or none.

Packages under `packages/*` and `services/*` are **workspace-private** (`"private": true` / no `[project].classifiers` publish config) — not independently published to npm/PyPI. Their `version` field exists for internal tracking only; there's no public package version to manage until/unless one of them is deliberately extracted and published (see [docs/architecture/15-future-extensibility.md](../architecture/15-future-extensibility.md) §4).

## 5. Branch protection (to configure once a GitHub remote exists)

Required for `main`, tracked as a Sprint 0 checklist item rather than described as already active (it isn't — there's no remote yet):

- Require PR review (at least one approval) before merge.
- Require status checks to pass (once CI exists — [08-cicd-strategy.md](08-cicd-strategy.md)) before merge.
- Require branches to be up to date before merge.
- No force-push, no direct push, to `main`.
- Require the `production` GitHub Environment's manual approval gate for any deploy job targeting production ([docs/architecture/11-deployment-architecture.md](../architecture/11-deployment-architecture.md) §3).
