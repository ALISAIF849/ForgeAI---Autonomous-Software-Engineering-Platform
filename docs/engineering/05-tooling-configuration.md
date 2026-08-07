# 05 — Tooling Configuration

Every tool below has a real, committed config file — this document explains what each one does and why it's configured the way it is, rather than duplicating the config itself.

## 1. A deliberate deviation from the brief: Ruff replaces Black, not alongside it

The brief listed Ruff and Black as separate tools to configure. **They aren't both configured** — this is a case where the "improve weaknesses, explain the change" instruction applies to the tooling list itself, not just the architecture.

Ruff includes `ruff format`, a Black-compatible formatter, in the same tool that already does linting and import-sorting. Running Black _and_ Ruff's formatter on the same codebase means two formatters with their own (mostly but not perfectly identical) opinions about style, which either fight each other on edge cases or means Black is configured to defer to Ruff anyway — at which point it's not doing anything Ruff doesn't already do. There's no capability Black has that Ruff's formatter lacks for this codebase. One tool, one job, is simpler to configure, faster in CI and pre-commit (a single process instead of two), and removes an entire category of "which formatter actually wins" argument. `ruff format` is invoked exactly where Black would have been: pre-commit (`.lintstagedrc.json`) and CI (once implemented).

## 2. TypeScript/JavaScript

| Tool                          | Config                                                                                   | Job                                                                                                                                                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ESLint** (flat config, v9+) | [`eslint.config.mjs`](../../eslint.config.mjs)                                           | Correctness and pattern rules: unused vars, React hooks rules, consistent type-only imports, `no-console` beyond warn/error. Does _not_ handle formatting — that's Prettier's job, kept separate so the two never disagree about what "correct" means.           |
| **Prettier**                  | [`.prettierrc.json`](../../.prettierrc.json), [`.prettierignore`](../../.prettierignore) | Formatting only: quotes, semicolons, line width, trailing commas. Includes `prettier-plugin-tailwindcss` so Tailwind class lists get a single canonical ordering — otherwise class-order becomes a silent, unenforceable style debate in every component review. |

Both run in the pre-commit hook (via lint-staged, scoped to `apps/web/**` and `packages/**`) and are intended to run again in CI once implemented, so a contributor who skips hooks locally (or force-pushes past them) still can't merge unformatted/failing code.

## 3. Python

| Tool                     | Config                                                             | Job                                                                                                                                                                                                                                                                                          |
| ------------------------ | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ruff** (lint + format) | `[tool.ruff]` in the root [`pyproject.toml`](../../pyproject.toml) | Linting (`E`, `F`, `I` import-sort, `UP` pyupgrade, `B` bugbear, `SIM` simplify, `C4` comprehensions, `RUF` Ruff-specific) _and_ formatting, replacing both Flake8-equivalent linting and Black — see §1.                                                                                    |
| **mypy** (`--strict`)    | `[tool.mypy]` in the root `pyproject.toml`                         | Static type checking. This is a genuinely separate concern from lint/format — Ruff does not type-check — so mypy stays as its own tool. Runs with the `pydantic.mypy` plugin so Pydantic models are checked with full awareness of their validation semantics, not treated as plain classes. |

Both are configured once, at the workspace root, rather than per-`services/*` package — every Python package in the workspace is held to the same standard by construction, with no per-package opt-out.

## 4. Git hooks: Husky + lint-staged

- **Husky** (v9+, minimal hook files — see [`.husky/pre-commit`](../../.husky/pre-commit), [`.husky/commit-msg`](../../.husky/commit-msg)) wires git's native hook mechanism to run project tooling automatically; activated by the `prepare` script in the root `package.json`, so `pnpm install` is sufficient to get hooks working — no separate manual setup step to forget.
- **lint-staged** ([`.lintstagedrc.json`](../../.lintstagedrc.json)) runs the right tool against only the files actually staged for commit, not the whole repo — fast enough to run on every commit without friction. Deliberately covers **both** ecosystems in one config: TS/JS files under `apps/web` and `packages/*` get ESLint+Prettier, Python files under `apps/api`, `apps/worker`, and `services/*` get Ruff. This matters specifically because Husky/lint-staged are npm-ecosystem tools by origin — it would be easy to wire them up for the TS half of the repo and quietly leave Python commits unchecked at commit time (still caught by CI later, but the whole point of a pre-commit hook is catching it before it's even pushed).
- **commitlint** ([`commitlint.config.js`](../../commitlint.config.js)) runs on the commit message itself via the `commit-msg` hook, enforcing the Conventional Commits format from [04-git-strategy.md](04-git-strategy.md) §2.

## 5. Why pre-commit enforcement _and_ CI enforcement, not just one

Pre-commit hooks are fast local feedback but are trivially bypassable (`--no-verify`, or simply not running `pnpm install` locally). CI enforcement is the actual gate that can't be skipped by an individual contributor's local setup. Both exist because they solve different problems: pre-commit hooks save round-trips to CI for mistakes that are cheap to catch locally; CI enforcement is what the branch-protection rule in [04-git-strategy.md](04-git-strategy.md) §5 actually depends on. Neither one is a substitute for the other.

## 6. On version pinning in the committed configs

The root `package.json` and `pyproject.toml` pin indicative version ranges for these tools (e.g., `eslint": "^9.17.0"`). Treat these as a starting point, not a guarantee of the current latest release — resolve real, current versions with `pnpm up --latest` (JS) / `uv lock --upgrade` (Python) as part of the Sprint 0 checklist, rather than trusting exact numbers written during an architecture pass that may be months old by the time Sprint 0 is actually executed.
