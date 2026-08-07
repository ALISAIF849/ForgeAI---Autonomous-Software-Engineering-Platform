# 11 — Security Standards

[docs/architecture/12-security-architecture.md](../architecture/12-security-architecture.md) designed the _system_. This document is its PR-level operationalization — what a specific change is held to, checked in review (§3 of [04-git-strategy.md](04-git-strategy.md)) and, where possible, by CI. It restates nothing at length; each item points back to the system design and adds the concrete, checkable rule.

## 1. Authentication

New endpoints declare their required auth mode explicitly via the standard dependency chain (`get_current_org_member(...)` or API-key equivalent, [docs/architecture/08-api-design.md](../architecture/08-api-design.md) §4) — never a hand-rolled auth check inside a route handler. A route with no auth dependency at all must be deliberately public (health checks, the login endpoint itself) and is called out as such in review, not an oversight waiting to be caught.

## 2. Authorization / RBAC

The four roles (`owner / admin / member / viewer`) are the only roles in v1 ([docs/architecture/12-security-architecture.md](../architecture/12-security-architecture.md) §2) — a PR introducing a new, more granular role is an architecture-level change requiring an ADR ([12-documentation-standards.md](12-documentation-standards.md)), not something to add ad hoc inside a single feature's implementation.

## 3. Secrets management

- Never a real credential in a commit — including test fixtures, seed data, or a "temporary" hardcoded value meant to be replaced later. If a placeholder is needed, it's obviously fake (`sk_test_placeholder`, not a syntactically-real-looking key).
- Any new integration credential (a new third-party API key type) goes through the same envelope-encryption helper used for existing user-provided secrets ([docs/architecture/12-security-architecture.md](../architecture/12-security-architecture.md) §3) — never stored plaintext "just for now."
- New env vars follow [06-environment-configuration.md](06-environment-configuration.md) §4's checklist, every time — including the `NEXT_PUBLIC_` decision, which is a security review point, not a naming preference.

## 4. Rate limiting

A new endpoint that spends LLM tokens or calls a metered external API is classified as "expensive" and rate-limited accordingly ([docs/architecture/08-api-design.md](../architecture/08-api-design.md) §5) before merge — not retrofitted after the first cost spike. This is a PR checklist item precisely because it's easy to forget on a new endpoint that "looks like" a normal CRUD route but happens to trigger a capability invocation.

## 5. Prompt injection mitigation

The concrete review question for anything touching a capability with tool access: **does this change widen what an LLM's output can cause to happen, and if so, is that action gated?** Checked against the four structural mitigations in [docs/architecture/12-security-architecture.md](../architecture/12-security-architecture.md) §4:

1. Tool credentials handed to the capability are scoped to the specific project, never broader.
2. Content from outside ForgeAI (PR bodies, issues, fetched pages) is passed as clearly-delimited untrusted input, never concatenated into the capability's own instruction channel.
3. Any irreversible action the capability's output could lead to is behind a structural approval gate ([docs/architecture/03-workflow-engine.md](../architecture/03-workflow-engine.md) §5) — not a prompt instruction telling the model to "ask before doing this," which is not a security boundary.
4. Any code execution the capability triggers happens in the sandboxed executor, never inline in `apps/api`/`apps/worker`.

A capability implementation that can't satisfy all four for a new tool-access grant doesn't ship until it can.

## 6. Input validation

Every new endpoint has Pydantic request/response schemas — no exceptions, including internal/admin-only endpoints. "It's only called by the frontend we control" is not a reason to skip validation; the schema is also the API's documentation and the generated SDK's source of truth ([docs/architecture/08-api-design.md](../architecture/08-api-design.md) §1), not only a safety mechanism.

## 7. API security

- CORS origin list is explicit per environment ([06-environment-configuration.md](06-environment-configuration.md) §2) — a PR does not add a wildcard or a broadened origin pattern to make local testing more convenient.
- Error responses never include a stack trace, raw exception text, or internal file paths outside local development — the exception-handling middleware ([docs/architecture/08-api-design.md](../architecture/08-api-design.md) §6) is the one place this is decided; a route handler catching and re-formatting its own errors differently is a review flag, not a stylistic choice.
- Webhook handlers verify the provider's signature before any other processing, full stop — this is checked first in the handler, not after some convenience logic has already run.

## 8. Supply chain

Dependabot/Renovate configuration and CI-time container image scanning (Trivy or equivalent) are tracked as [SPRINT_0_CHECKLIST.md](SPRINT_0_CHECKLIST.md) items rather than designed further here — they're standard, low-judgment setup once a GitHub remote and CI exist, not something this document needs to make a novel decision about.
