# 08 — API Design

## 1. Shape: versioned REST + SSE, generated client, no hand-written frontend fetch calls

- All HTTP endpoints under `/api/v1/...`. Versioning from day one — this is a platform other tools (CI, CLI, integrations) will call, not just the first-party frontend, so breaking changes need a documented path from day one rather than retrofitted later.
- FastAPI's auto-generated OpenAPI schema is the single source of truth for the contract. `packages/sdk` is generated from it (via `openapi-typescript` + a thin typed fetch wrapper) on every backend schema change (CI check: fail the build if the committed SDK is stale relative to the live schema). The frontend never hand-writes a `fetch()` call or duplicates a type — every request/response shape is derived, not re-declared. This directly enforces DRY and strong typing across the frontend/backend boundary, and it's the main payoff of the monorepo decision in [01-repository-structure.md](01-repository-structure.md).
- Realtime updates (workflow status, activity feed, notifications) are **Server-Sent Events**, not WebSocket — see [09-frontend-architecture.md](09-frontend-architecture.md) §4 for the rationale (traffic is server→client only for these use cases; SSE is plain HTTP, which is simpler to run behind Railway/Vercel and auto-reconnects natively).

## 2. Modules

Mirrors the backend module structure in [01](01-repository-structure.md) §4 — each API module is one FastAPI router owned by the matching backend module:

| Module          | Representative endpoints                                                                                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `auth`          | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/oauth/github/callback`                                                                               |
| `organizations` | `GET/POST /organizations`, `POST /organizations/{id}/members`                                                                                                                  |
| `projects`      | `GET/POST /projects`, `GET /projects/{id}`, `PATCH /projects/{id}`                                                                                                             |
| `requirements`  | `GET/POST /projects/{id}/requirements`, `PATCH /requirements/{id}`                                                                                                             |
| `architecture`  | `GET /projects/{id}/architecture/decisions`, `GET /projects/{id}/architecture/artifacts`                                                                                       |
| `sprints`       | `GET/POST /projects/{id}/sprints`, `GET/POST /projects/{id}/milestones`, `GET/PATCH /tasks/{id}`                                                                               |
| `workflows`     | `GET /workflows/definitions`, `POST /workflows/{key}/start`, `POST /workflow-executions/{id}/resume`, `POST /workflow-executions/{id}/cancel`, `GET /workflow-executions/{id}` |
| `capabilities`  | `GET /capabilities`, `GET /capabilities/{key}/schema`, `POST /capabilities/{key}/invoke` (standalone/debug invocation)                                                         |
| `approvals`     | `GET /approvals?status=pending`, `POST /approvals/{id}/decide`                                                                                                                 |
| `conversations` | `GET/POST /projects/{id}/conversations`, `POST /conversations/{id}/messages`                                                                                                   |
| `deployments`   | `GET /projects/{id}/deployments`, `POST /projects/{id}/deployments`, `GET /deployments/{id}/logs`                                                                              |
| `notifications` | `GET /notifications`, `POST /notifications/{id}/read`                                                                                                                          |
| `audit`         | `GET /organizations/{id}/audit-logs` (admin-only)                                                                                                                              |
| `webhooks`      | `POST /webhooks/github`, `POST /webhooks/railway`, `POST /webhooks/vercel` (inbound, signature-verified)                                                                       |
| `events`        | `GET /projects/{id}/events/stream` (SSE)                                                                                                                                       |

`memory` (Layer 5) deliberately has **no general-purpose public endpoint** — it's consumed internally by capabilities via `CapabilityContext.memory`, not exposed as a raw search API. A narrow `GET /projects/{id}/memory/search` exists only for admin/debug tooling, gated behind the same RBAC as audit logs.

## 3. Authentication

Two modes, matching the two audiences called out in [README §5](README.md#5-weaknesses-identified-in-the-original-brief-and-how-this-design-resolves-them) item 3:

| Mode         | Used by                           | Mechanism                                                                                                                                                                                    |
| ------------ | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Session auth | The web app                       | Short-lived JWT access token + rotating refresh token, both in httpOnly/secure/sameSite=strict cookies — never exposed to JS, closing off the most common XSS-token-theft path               |
| API key auth | CI, CLI, third-party integrations | `Authorization: Bearer forge_sk_...`, hashed at rest, scoped (read-only / specific modules / specific project), revocable, `last_used_at` tracked so unused keys are easy to find and retire |

OAuth (GitHub first, given the product's natural integration point) sits in front of session auth as a login method, not a separate auth mode — it terminates in the same JWT/refresh-cookie issuance as password login.

## 4. Authorization

- RBAC at the organization level: `owner / admin / member / viewer`, checked via a FastAPI dependency (`get_current_org_member(min_role=...)`) applied per-route.
- Project-level membership can narrow (not widen) an org role — e.g., a `member` can be restricted to specific projects; a `viewer` never gets write access regardless of project membership.
- Every dependency that resolves "current org/project" is also what sets the RLS session variable described in [07-database-schema.md](07-database-schema.md) §4 — authorization and tenant-isolation share one resolution path so they can't drift apart.

## 5. Validation, rate limiting, and cost control at the API boundary

- Every request/response validated by Pydantic schemas — no unvalidated payload reaches a service method.
- Redis-backed rate limiting per API key/user, tiered by endpoint cost: cheap (CRUD reads) vs. expensive (`POST /capabilities/{key}/invoke`, `POST /workflows/{key}/start` — anything that spends LLM tokens). This is a second gate in front of the Model Router's own budget enforcement ([06-model-router.md](06-model-router.md) §4) — the API layer stops abusive/runaway _request volume_, the Model Router stops runaway _spend_; they guard different failure modes and neither substitutes for the other.
- Webhook endpoints verify provider signatures (GitHub HMAC, etc.) before touching the database, and are otherwise treated as untrusted input — see [12-security-architecture.md](12-security-architecture.md) §4 for why webhook/PR/issue content specifically gets treated with more suspicion than ordinary API input.

## 6. Error handling

Consistent problem-detail-style error responses (`type`, `title`, `status`, `detail`, `instance` — RFC 7807 shape) from a single exception-handling middleware, so the generated SDK can present one typed error shape to the frontend regardless of which module raised it. Domain-specific exceptions (e.g., `WorkflowDefinitionNotActive`, `ApprovalAlreadyDecided`) are defined per-module and mapped centrally, keeping the mapping (not the exception hierarchy) as the single place that decides HTTP status codes.
