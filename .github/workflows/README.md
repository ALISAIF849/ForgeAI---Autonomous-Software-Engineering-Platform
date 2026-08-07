# CI/CD workflows — not yet implemented

This folder is intentionally empty of workflow YAML. The pipeline is fully **designed** in [docs/engineering/08-cicd-strategy.md](../../docs/engineering/08-cicd-strategy.md) (stages, triggers, environments, gates) but implementation was explicitly out of scope for the repository-foundation pass that created this placeholder — see that document's status note.

When implementation starts, this folder should end up with roughly:

```
lint.yml               # PR trigger
test.yml                # PR trigger
build.yml                 # PR trigger
deploy-staging.yml           # push to main
deploy-production.yml           # manual promotion, gated by the `production` GitHub Environment
```

Do not add ad-hoc workflow files here without first checking they match the design doc — the whole point of designing the pipeline before implementing it was to avoid CI config drifting into an unreviewed, ad-hoc pile of YAML.
