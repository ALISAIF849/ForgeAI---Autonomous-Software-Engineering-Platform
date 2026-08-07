# 12 — Documentation Standards

Every feature ships with the documentation that keeps it findable and its reasoning intact — not documentation for its own sake. The concrete rule for each required artifact:

## 1. README updates

**When:** a change adds a new package/service, changes how to run or configure something, or changes a command referenced in an existing README. **Where:** the README closest to the change — a new `services/*` package's own description lives in its `pyproject.toml` (already the convention established when these were scaffolded — see [01-repository-scaffolding.md](01-repository-scaffolding.md) §2), the root `README.md` only changes for repo-wide concerns (new top-level folder, changed quickstart). Not every change touches the root README — most shouldn't.

## 2. Architecture notes

**When:** a change alters something `docs/architecture/*.md` asserts as true — a different table gets added, a layer's responsibility shifts, a documented trade-off gets revisited with a different outcome. **How:** update the specific document in place if it's a clarification/correction, or add an **amendment note** (dated, explaining what changed and why — see the amendment notes added to [docs/architecture/01-repository-structure.md](../architecture/01-repository-structure.md) and [docs/architecture/09-frontend-architecture.md](../architecture/09-frontend-architecture.md) by this pass, as the pattern to follow) if it's a genuine revision of a prior decision rather than a typo fix. The rule of thumb: a typo or a clarification edits in place; a decision being _revisited_ gets recorded as having been revisited, the same way [docs/architecture/07-database-schema.md](../architecture/07-database-schema.md) §2's `architecture_decisions.superseded_by_id` never lets a superseded decision quietly disappear. Architecture docs are a historical record as much as a current-state reference — silently rewriting them defeats the "persistent engineering memory" principle they exist to serve.

## 3. API docs

**When:** any new or changed endpoint. **How:** a good FastAPI route docstring, accurate Pydantic `Field` descriptions, and a realistic `response_model` — because [docs/architecture/08-api-design.md](../architecture/08-api-design.md) §1 makes the OpenAPI schema the single source of truth, generated API docs (and the generated TS SDK) come from writing the endpoint well, not from hand-writing a separate markdown page that immediately starts drifting from the real behavior. Hand-written markdown API docs are actively discouraged for exactly this reason.

## 4. Sequence diagrams

**When:** a new `WorkflowDefinition`, or any change where an interaction crosses more than two processes/services in a way that's hard to describe in a sentence (e.g., a new approval-gate resume path, a new webhook-triggered flow). **Where:** a Mermaid `sequenceDiagram` in the relevant `docs/architecture/` document if it documents a lasting system behavior, or inline in the PR description if it's local to understanding that one change. Not required for a typical CRUD endpoint or a straightforward bug fix — the bar is "would a reviewer actually need this to follow what's happening," not "does this PR touch more than one file."

## 5. ADRs (Architecture Decision Records)

**When, concretely — an ADR is required if the change does any of the following:**

- Changes a decision already recorded in `docs/architecture/` (e.g., swapping a chosen library, reversing a trade-off in [docs/architecture/14-risks-and-tradeoffs.md](../architecture/14-risks-and-tradeoffs.md)).
- Introduces a new external dependency or third-party service (a new SaaS integration, a new database, a new major library the whole team will depend on).
- Establishes a new cross-cutting convention in `docs/engineering/` (a new standard every future PR will be held to).

**Not required** for a routine feature implementation that follows already-established patterns — most PRs don't need one, and requiring them universally would make ADRs noise instead of signal.

**Format:** [docs/adr/0000-adr-template.md](../adr/0000-adr-template.md), numbered sequentially, one decision per file, never edited after merge except to mark it superseded by a later ADR (same non-destructive-history principle as §2). [docs/adr/0001-record-architecture-decisions.md](../adr/0001-record-architecture-decisions.md) is the bootstrapping example — the decision to use this ADR process at all, recorded using the process itself.

## 6. What ties this together

All four artifact types above answer the same underlying question at a different scope: README (how do I run/use this), architecture notes (why is the system shaped this way, kept current), sequence diagrams (how does this specific interaction actually flow), ADR (why did we decide this, preserved even after the decision is later revisited). A PR is complete when whichever of these actually apply have been updated — not all four apply to most changes, and forcing all four on every PR would make this a checkbox exercise instead of documentation that's actually worth reading later.
