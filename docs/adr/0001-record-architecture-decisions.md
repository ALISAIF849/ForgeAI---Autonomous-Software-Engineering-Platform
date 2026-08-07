# ADR-0001: Record architecture decisions as ADRs

**Status:** Accepted
**Date:** 2026-08-04
**Deciders:** Founding team

## Context

ForgeAI's own core principles include persistent engineering memory and explainable decisions ([docs/architecture/README.md](../architecture/README.md) §2) — applied to the product it's building. Those principles should hold for building ForgeAI itself, not only for the projects ForgeAI manages on behalf of users. Without a deliberate mechanism, the reasoning behind a decision tends to live only in a PR discussion or a Slack thread, both of which are effectively unsearchable and unlinkable within a year.

## Decision

Record architecture-significant decisions as Architecture Decision Records under `docs/adr/`, one file per decision, numbered sequentially, using the template at [0000-adr-template.md](0000-adr-template.md). The concrete trigger for "does this need an ADR" is defined in [docs/engineering/12-documentation-standards.md](../engineering/12-documentation-standards.md) §5, not left to individual judgment case by case.

## Alternatives considered

| Option                                                    | Rejected because                                                                                                                                                                         |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Decisions recorded only in PR descriptions                | Not indexed, not discoverable without knowing which PR to look for, easy to lose when a PR is squash-merged                                                                              |
| A single running `DECISIONS.md` log                       | Becomes an unstructured wall of text as it grows; no clean way to mark one decision as superseding another                                                                               |
| No formal record — rely on `docs/architecture/*.md` alone | Those documents describe current-state design; they're not well suited to preserving _why a prior version was different_, which is exactly what matters when revisiting a decision later |

## Consequences

Every architecture-significant PR now carries slightly more overhead (writing the ADR). In exchange, "why did we do it this way" has a durable, linkable answer six months later, and a decision being _revisited_ is visible as a superseding ADR rather than a silent, undocumented reversal that makes old context misleading.

## Revisit when

If ADRs are consistently being skipped in practice (check: are there architecture-significant PRs merged without one, found via the checklist in [docs/engineering/04-git-strategy.md](../engineering/04-git-strategy.md) §3), that's a signal the trigger criteria in the documentation standard are unclear or too broad — tighten the criteria rather than letting the process lapse silently.
