# 10 — Logging & Observability

This operationalizes [docs/architecture/10-backend-architecture.md](../architecture/10-backend-architecture.md) §6 and [docs/architecture/11-deployment-architecture.md](../architecture/11-deployment-architecture.md) §5 into the concrete artifacts the brief asked for.

## 1. Structured logging

`structlog` (Python: `apps/api`, `apps/worker`, `services/*`) and `pino` (TypeScript: `apps/web` server-side code) — key-value structured output, never string-concatenated messages. Every log line inside a request or job carries the correlation ID (`request_id` for an API request, `workflow_execution_id` for a background job), threaded through from the originating HTTP request or enqueue call down through every downstream call it triggers — this is what makes it possible to pull every log line related to one user action out of the combined stream, across both processes, without a distributed tracing system in place yet.

## 2. Error reporting

Sentry (or an equivalent — this is the one reasonable default named here, not a locked decision) — chosen for wide framework support across both halves of the stack (Next.js and FastAPI/Python have first-class SDKs), and a free/cheap tier appropriate for a pre-revenue stage. Captures unhandled exceptions in both `apps/web` and `apps/api`/`apps/worker`, tagged with the same correlation ID as the structured logs, so an error report and its surrounding log context can be cross-referenced.

## 3. Audit logs

Not a separate logging system — the `audit_logs` table ([docs/architecture/07-database-schema.md](../architecture/07-database-schema.md) §2, Group 3) _is_ the audit log, written directly by the specific service methods that perform privileged actions (approval decisions, deployments, role changes, API key changes). Deliberately not a generic "log everything" middleware layered on top — a middleware-level audit log tends to be noisy and low-signal (it captures that an endpoint was hit, not what specifically changed or why), where the actual compliance/debugging value is in a small number of precisely-recorded privileged actions.

## 4. Workflow logs

Also not a separate system — `workflow_executions` and `capability_executions` ([docs/architecture/07-database-schema.md](../architecture/07-database-schema.md) §2, Group 2) already record exactly what a "workflow log" would: what ran, in what order, with what input/output, at what cost, with what reasoning summary. Building a second, parallel log store for the same information would just be a second copy of the same data going out of sync with the first. The Workflow Timeline and Activity Feed UIs read directly from these tables — they're both a product feature and the observability surface for workflow execution at once.

## 5. Metrics

**What to measure**, once metrics exist at all: request latency/error rate per API endpoint, LLM token spend rate (from `usage_ledger`), workflow success/failure rate by definition, Arq queue depth and job-processing lag.

**MVP approach:** a lightweight Prometheus-compatible `/metrics` endpoint exposed by `apps/api` (a small, well-established FastAPI middleware — not custom-built), scraped by whatever's convenient at the current hosting scale (Railway's own metrics, or a free-tier Grafana Cloud target). This is deliberately minimal — full dashboards, alerting rules, and SLOs are Phase-4-territory ([docs/architecture/13-development-roadmap.md](../architecture/13-development-roadmap.md)), not something to build out before there's production traffic to make them meaningful.

## 6. Health endpoints

Two, not one — because they answer different questions an orchestrator needs to ask:

- **`GET /health/live`** — liveness: is the process itself up and able to respond at all? No dependency checks. If this fails, the orchestrator should restart the process.
- **`GET /health/ready`** — readiness: can this instance actually serve traffic right now (is the database reachable, is Redis reachable)? If this fails but liveness passes, the process is up but shouldn't receive traffic yet (e.g., mid-startup, or a dependency is briefly down) — the orchestrator should wait, not restart, since restarting wouldn't fix an external dependency being unavailable.

Conflating these into one `/health` endpoint is a common mistake that causes an orchestrator to restart-loop a perfectly healthy process just because a downstream dependency (like the database, during a brief maintenance window) is temporarily unreachable.

## 7. What's explicitly deferred

Distributed tracing (OpenTelemetry spans across `apps/api` → `apps/worker` → LLM provider), SLO dashboards, and alerting policy are not designed here — restated from [docs/architecture/11-deployment-architecture.md](../architecture/11-deployment-architecture.md) §5 because it's worth being consistent about what's deferred vs. silently missing. The correlation-ID convention adopted now (§1) is exactly what a future OpenTelemetry migration would key spans on, so nothing built at this stage needs to be redone when that happens — only extended.
