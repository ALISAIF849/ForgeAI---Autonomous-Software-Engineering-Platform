# 02 — Monorepo Strategy

## 1. The options, compared

|                                | pnpm + Turborepo (+ uv)                                    | npm workspaces                                      | Nx                                                     | Single tool for everything              |
| ------------------------------ | ---------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------ | --------------------------------------- |
| Install speed / disk use       | Fast, content-addressable store, strict by default         | Slower, no strict isolation (phantom deps possible) | Same as underlying package manager                     | —                                       |
| Task orchestration & caching   | Turborepo: dependency-graph-aware, local + remote cache    | None built in — needs a separate tool anyway        | Built in, most mature                                  | —                                       |
| Polyglot (TS + Python) support | Each ecosystem uses its native tool (pnpm/uv) — no forcing | N/A (JS-only)                                       | Plugin-based, thinner for Python than for JS           | Would mean picking Nx or similar anyway |
| Learning curve                 | Two familiar, ecosystem-native tools                       | Lowest (it's just npm)                              | Highest — its own generators, executors, config format | —                                       |
| Ecosystem/plugin maturity      | High (both are widely adopted, actively maintained)        | High but limited to what npm itself does            | High for JS, thinner for polyglot                      | —                                       |

## 2. Decision

**pnpm workspaces + Turborepo** for the TypeScript side (`apps/web`, `packages/*`), **uv workspaces** for the Python side (`apps/api`, `apps/worker`, `services/*`), unified by a root `Makefile`-equivalent script surface (`package.json` scripts delegate to `turbo`; Python-side equivalents delegate to `uv run`) rather than one tool trying to own both ecosystems.

This was already the direction set in the architecture pass ([docs/architecture/01-repository-structure.md](../architecture/01-repository-structure.md) §1); this document exists to make the comparison explicit and give the trade-offs their own home now that the coding standards and tooling docs need to reference a settled decision.

## 3. Why not npm workspaces

npm workspaces would work, but two gaps matter enough to avoid it: no strict dependency isolation by default (a package can accidentally resolve a dependency it never declared, because npm hoists everything into one flat `node_modules` — this class of bug is exactly what pnpm's stricter linking prevents), and no built-in task orchestration or caching, which means adopting Turborepo (or an equivalent) on top of npm workspaces anyway — at which point the question is just "npm or pnpm as the package manager underneath Turborepo," and pnpm wins on install speed and strictness with no real downside for a project this size.

## 4. Why not Nx

Nx is a legitimate, more full-featured alternative — its task graph, caching, and code generators are more mature than Turborepo's. It was set aside for two reasons specific to this project: it's strongest in mostly-JS/TS organizations, and this repo is genuinely half Python (`services/*`, `apps/api`, `apps/worker`) with its own idiomatic tooling (`uv`, `ruff`, `mypy`, `pytest`) that doesn't benefit much from Nx's plugin model — using Nx well here would mean either running Python through Nx's JS-centric executors (friction) or running two orchestration layers anyway (Nx for TS, something else for Python), which is the same "two ecosystem-native tools" shape as the chosen approach, just with more configuration surface. Nx also has a steeper learning curve (its own generator/executor vocabulary) that isn't worth paying for at a small founding team's current scale. **Revisit if:** the TS side grows enough packages that Turborepo's caching/graph features stop being sufficient, or the team grows enough that Nx's generators (scaffolding new packages consistently) start paying for their setup cost.

## 5. Why two workspace tools instead of one for everything

The alternative to "pnpm for TS, uv for Python" is forcing one tool to manage both — which in practice means bending Python dependency management through a JS-ecosystem tool (awkward, fights the grain of both ecosystems' native tooling and their respective communities' conventions) or vice versa. Two small, each-ecosystem-idiomatic tools, unified only at the script-invocation level (`pnpm dev`, `uv run pytest`), is simpler to reason about than one tool doing an unnatural cross-language job — this is the same reasoning already applied to ESLint/Ruff (§5 of [05-tooling-configuration.md](05-tooling-configuration.md)) and ESLint/ruff not overlapping in scope.

## 6. What this buys, concretely

- `pnpm install` and `uv sync` each do exactly one job and can be run independently — a Python-only change doesn't require touching `node_modules`, and vice versa.
- Turborepo's affected-graph means CI only lints/tests/builds packages that actually changed (and their dependents) — not the whole repo on every PR, which matters once `packages/*` and `services/*` both have real content.
- Either workspace tool can be swapped later (e.g., Turborepo → Nx, if the earlier trade-off tips) without touching the other ecosystem's tooling at all, since they were never coupled together in the first place.
