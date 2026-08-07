# 09 — Frontend Architecture

## 1. Structure (`apps/web`)

```
apps/web/
├── app/
│   ├── (marketing)/                 # public landing page
│   ├── (auth)/                        # login, signup, OAuth callback
│   ├── (workspace)/
│   │   └── [orgSlug]/
│   │       ├── dashboard/
│   │       ├── settings/
│   │       └── projects/
│   │           └── [projectSlug]/
│   │               ├── requirements/
│   │               ├── architecture/
│   │               ├── workflows/       # Workflow Timeline
│   │               ├── sprints/           # Sprint Board
│   │               ├── activity/            # Activity Feed
│   │               ├── deployments/
│   │               └── settings/
│   └── api/                             # Next.js route handlers — auth callbacks & webhook
│                                          # proxies ONLY, never business logic (see §2)
├── components/
│   ├── ui/                    # shadcn primitives
│   ├── workflow/                # Workflow Timeline nodes/edges (React Flow)
│   ├── architecture/              # Architecture Viewer nodes/edges (React Flow)
│   ├── sprint-board/
│   └── shared/
├── lib/
│   ├── api-client/           # thin wrapper around packages/sdk + react-query hooks
│   ├── auth/
│   └── realtime/                # SSE client hooks
├── hooks/
├── stores/                # zustand — ephemeral client UI state ONLY (see §3)
└── styles/
```

## 2. Why Next.js route handlers stay nearly empty

It would be tempting to put business logic in Next.js API routes (`app/api/...`) since they're right there. **Decision: they don't hold business logic** — only auth-cookie plumbing (OAuth callback exchange) and thin webhook-forwarding where a provider requires the callback URL to be on the same domain as the frontend. Every actual read/write goes straight to `apps/api`. Rationale: a second place that "sort of" implements business rules is exactly how frontend and backend drift out of sync — the FastAPI backend is the single source of truth for behavior, full stop, and the generated SDK ([08-api-design.md](08-api-design.md) §1) is what frontend code is allowed to call.

## 3. Data fetching: Server Components + TanStack Query, not one or the other

- **Server Components** handle initial page loads for data-heavy, non-live views (dashboard summaries, project lists, requirement lists) — fetched server-side with the auth cookie forwarded, avoiding a client-side loading waterfall and keeping time-to-first-content low.
- **TanStack Query (react-query)**, backed by the generated SDK, handles anything that needs live refetching, mutation, or optimistic updates on the client — the Sprint Board (drag-and-drop), the Workflow Timeline (live node status), approval actions.
- **Why not pure RSC:** the Workflow Timeline and Activity Feed need to update as events happen server-side, which server components alone can't do (they render once per navigation) — these views need a live client subscription.
- **Why not a pure client SPA:** would give up Next.js's server-rendering performance/SEO benefits for pages that don't need live updates (marketing pages, dashboard summaries), for no benefit.
- This hybrid is exactly what the App Router is designed to support, not a workaround — server components for the initial shell, client components (marked `"use client"`) for the interactive/live pieces nested inside.

**State ownership rule:** server state (anything that came from the API) lives _only_ in the react-query cache. Zustand stores hold _only_ ephemeral, purely-client state (canvas viewport position, panel collapsed/expanded, form draft state before submit). Server data is never copied into a Zustand store — that would create two sources of truth for the same fact and is a well-known source of stale-UI bugs.

## 4. Realtime: SSE, not WebSocket

**Chosen:** Server-Sent Events for the Activity Feed, Workflow Timeline, and Notifications.

**Why:** every one of these is server→client only — nothing the client sends back needs to ride the same live channel (approval decisions, comments, etc. are ordinary POST requests). SSE is plain HTTP: it auto-reconnects natively, doesn't require a protocol upgrade, and behaves predictably behind Vercel/Railway's infrastructure. WebSocket earns its complexity when there's genuine bidirectional low-latency traffic (e.g., a future collaborative-editing feature) — not needed yet, so it's deferred rather than adopted "just in case." See [15-future-extensibility.md](15-future-extensibility.md).

`lib/realtime/` wraps `EventSource` in a hook (`useProjectEvents(projectId)`) that both drives the Activity Feed directly and invalidates the relevant react-query cache keys when a relevant event arrives (e.g., a `workflow_execution.status_changed` event invalidates the Workflow Timeline's query) — one live channel, multiple UI surfaces react to it.

## 5. React Flow: two distinct canvases, not one generic graph component

- **Architecture Viewer** — renders `architecture_artifacts`: system/entity diagrams, mostly read-only, AI-generated layout with manual override. Custom node types per artifact kind (service, datastore, external system).
- **Workflow Timeline** — renders a `WorkflowExecution` as a DAG mirroring its `WorkflowDefinition` graph, with live status coloring (pending/running/waiting-approval/completed/failed) driven by the SSE stream in §4, and an inline approval action on `HumanApprovalNode` nodes.

These are kept as two separate component trees with distinct node/edge types rather than one "generic graph viewer," because their data shapes, update frequency (Architecture Viewer is nearly static; Workflow Timeline updates live), and interactions (approve/reject vs. pan/zoom/inspect) are different enough that a shared abstraction would need constant special-casing — a false economy.

## 6. Design system

shadcn/ui (Radix primitives + Tailwind) is the direct mechanism behind "must never look like ChatGPT": it's a composable component set for building conventional SaaS dashboard UI (tables, panels, command palettes, forms), not a chat-widget library. `packages/ui` wraps shadcn's generated components with ForgeAI's theme tokens once, consumed by every route group — the marketing site and the authenticated workspace share the same visual language without sharing layout code.

## 7. Type safety end-to-end

`packages/sdk` (generated, [08-api-design.md](08-api-design.md) §1) + `packages/types` (for entities/enums the SDK doesn't cover, like shared UI-only unions) mean a backend schema change that isn't reflected in the frontend fails at `tsc` time, not at runtime in a user's browser — this is the practical payoff of "strong typing" as an engineering standard, applied at the one boundary (frontend/backend) where it's most commonly lost.

> **Amendment (2026-08-04, repository-foundation pass):** §1's flat `components/workflow`, `components/architecture`, `components/sprint-board` structure was refined into a `features/` colocation pattern — each feature (`workflow-timeline/`, `architecture-viewer/`, `sprint-board/`, `activity-feed/`, ...) owns its own `components/`, `hooks/`, and `services/` subfolders, with the top-level `components/` reserved for things genuinely shared across 2+ features. This is a real improvement, not just a rename: it means deleting or substantially reworking one feature doesn't require hunting through unrelated global folders for its leftover pieces. `lib/api-client`, `lib/auth`, and `lib/realtime` were also renamed to `services/`, `services/auth/`, and `services/realtime/` respectively, to match the vocabulary used consistently across the rest of the stack. Full as-built structure and reasoning: [docs/engineering/01-repository-scaffolding.md](../engineering/01-repository-scaffolding.md) §5. Nothing about the data-fetching model (§3) or realtime transport (§4) changed — this amendment is scoped to folder organization only.
