# 15 — Future Extensibility

Every entry below is a case where the architecture was deliberately shaped so a future capability is **additive** — a new registration, a new adapter, a new config row — rather than a redesign. This is the practical test of whether the layering in [02-service-architecture.md](02-service-architecture.md) actually holds: if adding something later requires touching multiple layers, the boundary was drawn in the wrong place.

## 1. Multi-model support

Adding OpenAI, Anthropic, or a self-hosted model means: implement one `ModelProvider` adapter over LangChain's chat-model interface, add rows to `model_profiles`, optionally add `model_routing_rules` preferring it for specific capability categories. No change to any capability, workflow, or the routing logic itself. This is the concrete validation of the Model Router abstraction decided in [06-model-router.md](06-model-router.md) — provider-agnostic in shape even with one provider live.

## 2. New capabilities, and eventually a capability marketplace

Because capabilities are contract-first and registered rather than hardcoded into the Workflow Engine ([04-capability-registry.md](04-capability-registry.md)), a new capability — whether built by ForgeAI or, eventually, by a third party or a customer's own org — is additive: implement the `Capability` protocol, register it, reference it from a workflow definition. The registry's category taxonomy and versioning already support a future "install a community/org-custom capability" flow without a schema change; a Capability Marketplace is a UI and a trust/review process layered on top of infrastructure that already exists, not a new subsystem.

## 3. New workflows

`WorkflowDefinition`s are versioned graph specs in a registry + database ([03-workflow-engine.md](03-workflow-engine.md) §7), not code wired directly into the API. New workflows the brief doesn't name yet — "Refactor Legacy Code," "Security Audit," "Performance Optimization," "Onboard Existing Codebase" — are new definitions, composed from existing or new capabilities, following the same node-type rules (including the non-negotiable approval gate on irreversible actions) that every other workflow follows.

## 4. Microservice extraction path

The modular monolith ([14-risks-and-tradeoffs.md](14-risks-and-tradeoffs.md) §2) was chosen for now, not permanently. Because `services/*` packages are already independent, extraction is a deployment change, not a rewrite:

1. **`apps/worker`'s execution engine** is the first realistic candidate — it's the most CPU/IO-heavy, independently-scalable piece (running many concurrent workflow/capability executions), and it already communicates with `apps/api` only through Redis, not in-process calls.
2. **A specific capability needing dedicated scaling** (e.g., a sandboxed code-execution capability that wants a large, isolated container fleet) could be extracted next, behind the same `Capability` contract callers already use.
3. **`apps/api` stays a monolith the longest** — it's the stable BFF/gateway, and splitting it further only pays off if specific modules within it develop genuinely independent scaling or deployment-cadence needs, which nothing in the current product shape suggests.

## 5. Additional cloud providers

`infra/` is already provider-namespaced (`infra/railway/`) rather than assuming Railway/Vercel forever. Adding `infra/aws/` or `infra/gcp/` later — consistent with the brief's own statement that "cloud providers are future phases" — doesn't touch application code, only deployment configuration, because the application never talks to Railway/Vercel APIs directly except through the `integrations/` package used by the **Deploy Application** workflow ([04-capability-registry.md](04-capability-registry.md), [11-deployment-architecture.md](11-deployment-architecture.md)).

## 6. Vector store migration

If `pgvector` is outgrown ([05-memory-engine.md](05-memory-engine.md) §2), the migration target (Qdrant, or a hosted pgvector-compatible service) sits entirely behind `MemoryEngine.recall()` — every capability and workflow calls that interface, never the storage layer directly, so this migration is invisible to the rest of the system by construction.

## 7. Enterprise features

SSO/SAML, custom RBAC roles beyond the four base roles, on-prem/VPC deployment for regulated customers, and org-level data residency are all additive to a data model that already scopes everything by `org_id`/`project_id` with RLS enforcement ([07-database-schema.md](07-database-schema.md) §4, [12-security-architecture.md](12-security-architecture.md)) — none of them require reshaping the tenancy model, only extending it (e.g., an `sso_connections` table per org, additional role rows, a deployment target that happens to be customer-controlled infrastructure rather than Railway).

## 8. Integration ecosystem

GitHub, Railway, and Vercel are the first entries in `services/integrations/`. Slack notifications, Jira/Linear sync, and similar third-party integrations follow the same plugin shape: a scoped client, credentials handled with the same envelope-encryption standard as any other user-provided secret ([12-security-architecture.md](12-security-architecture.md) §3), and either a new capability (if the integration does engineering work) or a notification-dispatch target (if it's purely informational).

## 9. What this list deliberately excludes

Nothing here is scoped or estimated — that's what [13-development-roadmap.md](13-development-roadmap.md) is for, once each item is actually prioritized. This document exists to show that the layering decisions made throughout this set weren't arbitrary: each one was checked against "what does this make easy or hard later," and the answer is recorded here rather than left implicit.
