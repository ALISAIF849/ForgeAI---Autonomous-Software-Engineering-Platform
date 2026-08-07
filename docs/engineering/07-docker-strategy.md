# 07 — Docker Strategy

> **Status: design only.** Per this pass's explicit scope, no `Dockerfile` and no `docker-compose.yml` have been written. This document specifies what they should look like when Sprint 1 (or a dedicated infra sprint) writes them, so implementation follows a reviewed design rather than being improvised file by file.

## 1. Local development: Docker Compose

A single root-level `docker-compose.yml` brings up the full local stack: `postgres`, `redis`, `api`, `worker`, `web`. It exists for **"give me the whole system"** scenarios — testing a cross-service flow end-to-end, onboarding a new contributor who wants one command to get everything running, or reproducing a bug that only shows up with real inter-service traffic.

It is explicitly **not** the primary day-to-day inner-loop workflow for someone actively developing one app — running `apps/web`'s own dev server (`pnpm dev`, hot module reload) or `apps/api`'s own dev server (`uvicorn --reload`) directly on the host is faster to iterate against than rebuilding/restarting a container on every change. The expected pattern: `docker compose up postgres redis` for just the stateful dependencies, then run whichever app you're actively working on natively against those, and only reach for the full `docker compose up` when you specifically need the whole system running together.

A `docker-compose.override.yml` (or a `docker-compose.dev.yml`, loaded explicitly) layers dev-only concerns on top of the base file: bind-mounting source into containers for hot reload, exposing debug ports, relaxing resource limits — the base `docker-compose.yml` alone should already resemble production topology closely enough to catch integration issues early, with the override file being pure convenience on top.

## 2. Production: no docker-compose at all

This is worth stating plainly because it's a common point of confusion: **Railway does not deploy via `docker-compose.yml`.** Each Railway service (`api`, `worker`) builds and runs from its own `Dockerfile` independently, using Railway's own service/networking model ([docs/architecture/11-deployment-architecture.md](../architecture/11-deployment-architecture.md) §2). `docker-compose.yml` is a local-development convenience only — it has no role in how staging or production actually run. Nothing about the production deployment path depends on the compose file being correct or even present.

## 3. Service separation: one Dockerfile per app, co-located

- `apps/web/Dockerfile`, `apps/api/Dockerfile`, `apps/worker/Dockerfile` — each colocated with the app it packages, not centralized in `infra/`. Rationale already given in [01-repository-scaffolding.md](01-repository-scaffolding.md) §3.3: a Dockerfile's build steps mirror that specific app's dependency/build tooling, and whoever changes those dependencies should see the Dockerfile in the same diff.
- Each is a **multi-stage build**: a `deps` stage (install dependencies, cacheable independent of source changes), a `build` stage (compile/bundle — relevant for `web`; `api`/`worker` mostly skip this beyond installing the package itself), and a slim `runtime` stage that copies only what's needed to run, not the full build toolchain. This keeps production image size and attack surface down — a production container doesn't need a C compiler or the TypeScript compiler sitting in it.
- `infra/docker/` holds only genuinely shared fragments — e.g., a common Python base-image setup reused by `api` and `worker`'s Dockerfiles via multi-stage `COPY --from=` or a shared base image tag. If nothing ends up generic enough to share, this folder legitimately stays empty — that's not a sign something's missing, it's a sign the three apps' build needs turned out to be different enough not to force a shared abstraction that doesn't fit.

## 4. Networking

Local Compose: a single bridge network (Compose's default), services addressed by service name (`api` connects to `postgres:5432`, not `localhost:5432`) — this deliberately mirrors how Railway's private networking resolves services by name in staging/production, so the connection-string _shape_ doesn't need to change between local and deployed environments, only the host/credentials.

No service is exposed to the host network by default except what a developer actually needs to reach directly (`web` on `3000`, `api` on `8000`, `postgres`/`redis` for a local DB client) — internal-only services stay internal-only even in local Compose, so a local setup doesn't quietly rely on network exposure that production would never have.

## 5. Volumes

- **Named volume for Postgres data** (`postgres_data`), so `docker compose down && docker compose up` doesn't silently wipe local data — only `docker compose down -v` does, an explicit, deliberate action.
- **Bind mounts for source code in the dev override only** (hot reload) — never in a production image. Production images are immutable: code is baked in at build time via `COPY`, not mounted at runtime. Mixing these two models (mounting source in a "production-like" compose config) is a common source of "works in Docker locally, breaks on Railway" bugs, so the base `docker-compose.yml` should not bind-mount source at all — that's strictly a dev-override concern.

## 6. What Sprint 1 (or an infra-focused sprint) still needs to decide

- Exact base images per app (e.g., `node:22-slim` vs. `node:22-alpine` for `web`; `python:3.12-slim` for `api`/`worker`) — a real trade-off between image size and glibc-vs-musl compatibility with Python's compiled dependencies, better decided once real dependencies (and any C-extension packages) are known, not speculatively now.
- Whether `worker` needs anything beyond the base Python image for sandboxed capability execution ([docs/architecture/12-security-architecture.md](../architecture/12-security-architecture.md) §4) — that's a separate, security-reviewed decision, not bundled into the general Dockerfile strategy here.
