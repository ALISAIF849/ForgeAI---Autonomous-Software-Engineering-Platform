# 04 — Capability Registry Architecture (Layer 3)

## 1. Why "capabilities," not "agents"

The brief is explicit: register reusable engineering capabilities instead of standing up fixed AI agents. The distinction is load-bearing, not cosmetic:

- A **fixed agent** ("the Backend Agent") tends to accumulate a large, vague responsibility ("write backend code") and an implicit, hard-to-audit prompt. Improving it means editing an agent's personality; testing it means eyeballing chat transcripts.
- A **Capability** is a narrow, versioned, contract-first unit: declared input schema, declared output schema, declared model requirements. Improving it means shipping a new version with a diffable change; testing it means asserting against the output schema like any other software interface.

This is the Strategy/Plugin pattern applied to engineering work: the Workflow Engine depends only on the _contract_ ("give me `architecture.design v2` given this input, get back output matching this schema"), never on a specific implementation — so implementations can be upgraded independently of the workflows that call them.

## 2. Anatomy of a Capability

```python
# services/capability_registry/base.py — illustrative, not final implementation
class Capability(Protocol):
    key: str                      # e.g. "requirements.analyze"
    version: str                  # e.g. "1.2.0" (semver)
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    category: CapabilityCategory  # requirement_analysis | architecture_design | backend_dev |
                                   # frontend_dev | qa | documentation | deployment
    default_model_tier: ModelTier # see 06-model-router.md

    async def execute(self, ctx: CapabilityContext, input: BaseModel) -> CapabilityResult: ...
```

`CapabilityContext` is what the Workflow Engine hands a capability at invocation time — it's the capability's _only_ access to the outside world, which is the enforcement point for least-privilege tool access (see [12-security-architecture.md](12-security-architecture.md) §4):

```python
class CapabilityContext(Protocol):
    project_id: UUID
    memory: MemoryEngineClient        # scoped to this project only
    model: ModelRouterClient          # resolves an LLM per this capability's declared needs
    tools: ToolRegistry               # scoped credentials — only what this project/capability needs
    workflow_execution_id: UUID | None
```

`CapabilityResult` always includes:

```python
class CapabilityResult(BaseModel):
    output: BaseModel                 # matches the capability's output_schema
    reasoning_summary: str            # human-readable explanation — see §5
    confidence: Literal["low", "medium", "high"] | None
    citations: list[MemorySourceRef]  # which memory/context this drew on
```

## 3. Registration

Capabilities register via decorator at import time into an in-process registry, mirrored to the `capabilities` table for discoverability (listing available capabilities in the UI, letting a workflow definition reference a capability by key without a hard code import):

```python
@capability_registry.register(
    key="architecture.design",
    version="1.0.0",
    category=CapabilityCategory.ARCHITECTURE_DESIGN,
    input_schema=ArchitectureDesignInput,
    output_schema=ArchitectureDesignOutput,
    default_model_tier=ModelTier.HIGH_CAPABILITY,
)
class ArchitectureDesignCapability:
    async def execute(self, ctx, input): ...
```

Multiple versions of the same `key` can be registered simultaneously. A `WorkflowDefinition` pins a specific version (or `"latest-compatible"` under a semver range) per node — the same reasoning as workflow-definition versioning in [03-workflow-engine.md](03-workflow-engine.md) §7: an in-flight execution should not change behavior because a capability shipped a new version underneath it.

## 4. Implementation is an internal detail

Nothing about the `Capability` interface requires a single LLM call. Internally, a capability can be:

- **A single structured-output LLM call** — most "analysis" and "documentation" category capabilities (e.g., `requirements.analyze`, `documentation.generate`).
- **A LangChain tool-calling loop** — capabilities needing to read files, run commands, or query external systems (e.g., `backend.implement` reading the existing codebase before writing a diff).
- **A small LangGraph subgraph** — capabilities with internal branching (e.g., `qa.run` might plan tests, run them, and self-correct once before returning).

The Workflow Engine and callers never need to know which of these a given capability does — that's precisely the point of the contract boundary in §1.

## 5. Explainability is part of the contract, not a UI afterthought

Per principle #6, every capability that exercises engineering judgment (design, review, planning — not purely mechanical capabilities like "format this document") must populate `reasoning_summary` in its result. This is enforced by category: the base class for judgment-bearing categories makes `reasoning_summary` a required, non-empty field at the schema level, so a capability _cannot_ return a decision without also returning why — it's a type error, not a style guideline. This is what lets the UI show "why did the AI suggest this architecture" as a first-class panel rather than reverse-engineering it from a raw model transcript, and it's what makes ADRs generated by `architecture.design` genuinely reviewable (see [05-memory-engine.md](05-memory-engine.md) §4).

## 6. Execution recording

Every invocation — whether from inside a `WorkflowExecution` or (for power users / debugging) invoked directly via API — creates a `CapabilityExecution` row: `capability_key`, `version`, `project_id`, `input`, `output`, `reasoning_summary`, `model_used`, `tokens_input/output`, `cost_usd`, `latency_ms`, `status`, timestamps. This single table is the backbone of three different features: the Activity Feed (what happened), cost analytics (what did it cost), and audit/debugging (what exactly did the AI see and decide). See [07-database-schema.md](07-database-schema.md).

## 7. Initial capability catalog (illustrative, not exhaustive)

| Key                    | Category             | Consumed by workflow                  |
| ---------------------- | -------------------- | ------------------------------------- |
| `requirements.analyze` | requirement_analysis | Gather Requirements                   |
| `architecture.design`  | architecture_design  | Generate Architecture                 |
| `sprint.plan`          | requirement_analysis | Plan Sprint                           |
| `backend.implement`    | backend_dev          | Implement Feature                     |
| `frontend.implement`   | frontend_dev         | Implement Feature                     |
| `qa.run`               | qa                   | Implement Feature, Fix Bug            |
| `pr.review`            | qa                   | Review Pull Request                   |
| `bug.diagnose`         | qa                   | Fix Bug, Investigate Production Issue |
| `docs.generate`        | documentation        | Implement Feature (post-merge)        |
| `deployment.plan`      | deployment           | Deploy Application                    |

Exact catalog and schemas are Sprint-level work; this table exists to validate that the registry's category taxonomy actually covers every workflow in the brief. It does.

## 8. What this buys later: a capability marketplace

Because capabilities are contract-first, versioned, and registered rather than hardcoded into workflows, third-party or org-specific custom capabilities become additive rather than architectural changes — expanded on in [15-future-extensibility.md](15-future-extensibility.md).
