## Summary

<!-- What does this change, and why? Link the issue/ticket if one exists. -->

## Type of change

- [ ] `feat` — new capability/functionality
- [ ] `fix` — bug fix
- [ ] `refactor` — no behavior change
- [ ] `docs` — documentation / ADR only
- [ ] `chore` / `ci` / `build` — tooling, dependencies, pipeline

## Checklist

- [ ] Tests added/updated and passing locally (`pnpm test` / `uv run pytest` as applicable)
- [ ] `pnpm lint && pnpm typecheck` and `uv run ruff check . && uv run mypy .` pass
- [ ] No secrets, API keys, or populated `.env` files in this diff
- [ ] New/changed queries are scoped by `org_id`/`project_id` (see [docs/architecture/07-database-schema.md](../docs/architecture/07-database-schema.md) §4)
- [ ] If this touches a `WorkflowDefinition`: irreversible actions are behind a `HumanApprovalNode` (CI's approval-gate lint will fail otherwise — see [docs/architecture/03-workflow-engine.md](../docs/architecture/03-workflow-engine.md) §5)
- [ ] If this changes a previously-documented decision, or introduces a new external dependency/service: an ADR is included ([docs/adr/](../docs/adr/))
- [ ] Relevant docs updated (README, architecture notes, API docs) per [docs/engineering/12-documentation-standards.md](../docs/engineering/12-documentation-standards.md)

## How was this tested?

<!-- What did you actually run, beyond CI? Screenshots for UI changes. -->

## Anything reviewers should look at closely?

<!-- Call out risky bits, judgment calls, or things you're unsure about. -->
