# 06 — Model Router Architecture (Layer 4)

## 1. Purpose

Given a capability invocation, decide which concrete LLM handles it, get a configured client back, and record what it cost. This is the only layer that knows about specific model providers/IDs — everything upstream (capabilities, workflows) speaks in terms of _requirements_, not model names.

## 2. Provider-agnostic from day one, even with one provider wired up

The brief specifies Google Gemini as the initial (and only immediate) provider, with other cloud providers explicitly deferred to future phases. The Model Router is still built as a provider-agnostic abstraction now, not retrofitted later:

```python
class ModelProfile(BaseModel):
    id: UUID
    provider: str                 # "google" today; "anthropic" / "openai" / "local" later
    model_id: str                 # a config value, looked up at call time — never hardcoded
                                   # in capability code, so a model rename/deprecation is a
                                   # data change, not a code change
    tier: ModelTier                # FAST_CHEAP | BALANCED | HIGH_CAPABILITY
    context_window: int
    supports_tools: bool
    supports_structured_output: bool
    cost_per_1m_input: Decimal
    cost_per_1m_output: Decimal
    is_active: bool
```

Every provider is wrapped through LangChain's chat-model interface, so a `ModelProvider` adapter is the only thing that changes when a new provider is added — this is cheap insurance given the brief itself flags more providers as a near-term future phase, and given single-provider dependency is a named risk (see [14-risks-and-tradeoffs.md](14-risks-and-tradeoffs.md)).

Model IDs are intentionally _not_ hardcoded anywhere in capability or workflow code — they're looked up from `model_profiles` at call time, so a provider renaming or deprecating a model is a configuration change, not a code change or a redeploy.

## 3. Routing policy: rule-based, not learned — for now

**Chosen:** an ordered set of rules (`model_routing_rules`: capability key or category → tier → model profile, with org-level overrides and a fallback chain), editable without a redeploy.

**Alternative considered:** an adaptive/learned router that picks models based on historical outcome data.

**Why rule-based wins for v1:** principle #6 is explainable AI decisions — a routing decision is itself a decision, and "why did this capability run on this model" needs to be answerable as plainly as "why did this capability produce this output." A rule-based router's answer is always "because rule N matched"; a learned router's answer requires explaining a model's own black-box behavior, which undermines the same explainability goal it would be trying to serve. Rule-based is also trivially debuggable and testable. An adaptive router is a legitimate future upgrade once there's enough execution history to learn from — noted in [15-future-extensibility.md](15-future-extensibility.md) — but it should be opt-in and itself explainable (e.g., a bandit algorithm that logs its reasoning), not a black box bolted onto a system whose whole premise is explainability.

Example rules (illustrative):

| Capability category                                                    | Tier                                                                  | Rationale                                      |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------- |
| `documentation`, `requirement_analysis` (simple extraction)            | FAST_CHEAP                                                            | High volume, low ambiguity                     |
| `architecture_design`, `backend_dev`, `frontend_dev`, `qa` (diagnosis) | HIGH_CAPABILITY                                                       | Judgment-heavy, errors are expensive to unwind |
| Fallback on primary tier error/rate-limit                              | next tier down, same provider → then secondary provider if configured | Availability over optimality                   |

## 4. Cost and usage accounting

Every routed call writes a `usage_ledger` row (`org_id`, `project_id`, `capability_execution_id`, `model_profile_id`, `tokens_input/output`, `cost_usd`) — added to the schema specifically because the brief's listed entities didn't include one, despite the product being cost-driven by construction (every unit of engineering work spends real LLM tokens). See [README §5](README.md#5-weaknesses-identified-in-the-original-brief-and-how-this-design-resolves-them) item 2, and [07-database-schema.md](07-database-schema.md).

This feeds two things directly:

- **Budget enforcement** — before routing, the router checks the requesting org/project's usage against a configured monthly budget; over-budget requests are rejected (or, per org configuration, downgraded to a cheaper tier) rather than silently succeeding and surprising someone with a bill.
- **Analytics** — the Analytics screen in the brief's UI list needs exactly this data (cost by project, by capability, by workflow) and has nowhere else to get it from.

## 5. Interface

```python
# services/model_router/api.py — illustrative
class RoutingRequest(BaseModel):
    capability_key: str
    category: CapabilityCategory
    requires_tools: bool
    requires_structured_output: bool
    min_context_window: int | None
    org_id: UUID
    project_id: UUID

async def resolve(request: RoutingRequest) -> RoutedModel: ...  # -> configured LangChain chat model + params
async def record_usage(capability_execution_id: UUID, usage: TokenUsage) -> None: ...
```

Capabilities never call a provider SDK directly — always through `resolve()` — which is what makes provider swaps, budget gates, and usage accounting simultaneously enforceable in one place rather than scattered across every capability implementation.
