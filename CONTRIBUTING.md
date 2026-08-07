# Contributing to ForgeAI

This is the short version. Full detail lives in [docs/engineering/](docs/engineering/) — this file exists so the essentials are visible without leaving the repo root.

## Before you branch

Read [docs/architecture/README.md](docs/architecture/README.md) if you haven't. Every change should trace back to a principle or layer described there — if it doesn't obviously fit, that's worth raising before writing code, not after.

## Branching and commits

- Branch from `main`: `feat/<short-description>`, `fix/<short-description>`, `chore/...`, `docs/...`, `refactor/...`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), enforced by commitlint on commit: `type(scope): summary` — e.g. `feat(workflow-engine): add checkpoint resume for interrupted nodes`. Valid scopes are the package/service names (see `commitlint.config.js`).
- Full rationale: [docs/engineering/04-git-strategy.md](docs/engineering/04-git-strategy.md).

## Before opening a PR

- `pnpm lint && pnpm typecheck && pnpm test` (JS/TS) and `uv run ruff check . && uv run mypy . && uv run pytest` (Python) — the pre-commit hook catches most of this automatically via lint-staged, but run the full suite before pushing.
- Fill out the PR template — it isn't boilerplate, the checklist items are what reviewers will actually check.
- If your change alters a decision recorded in `docs/architecture/` or introduces a new cross-cutting convention, add an ADR: [docs/adr/0000-adr-template.md](docs/adr/0000-adr-template.md). Rule of thumb in [docs/engineering/12-documentation-standards.md](docs/engineering/12-documentation-standards.md).

## Code review

Reviewers check against [docs/engineering/04-git-strategy.md](docs/engineering/04-git-strategy.md)'s code review checklist — tests, tenant-scoping on new queries, secrets handling, and (for anything touching a `WorkflowDefinition`) approval-gate placement on irreversible actions are the ones most worth double-checking, since they're the hardest to catch after merge.

## Coding standards

TypeScript, Python, naming, error handling, logging, and comment conventions: [docs/engineering/03-coding-standards.md](docs/engineering/03-coding-standards.md). These are enforced by CI where automatable (ESLint/Prettier/Ruff/mypy) and by review where not.

## Never

- Skip hooks (`--no-verify`) or force-push a shared branch.
- Commit a populated `.env` file or any real credential — see [docs/engineering/06-environment-configuration.md](docs/engineering/06-environment-configuration.md).
- Add a workflow definition that performs an irreversible action without a `HumanApprovalNode` gate — this is checked in CI (see [docs/architecture/03-workflow-engine.md](docs/architecture/03-workflow-engine.md) §5), and the build will fail, but it shouldn't need CI to catch it in review.
