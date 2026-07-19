# Phase 2A — AI Architecture Review
### Vendor-Independent Intelligence Engine (VIE) — Design Before Implementation

> **Status:** review only — no code changes.
> This document surveys the VIE that already exists at commit `829f31d`,
> identifies what is production-grade today, what needs enhancement, and
> what must be added before AI-provider integration is enabled. The
> proposed changes preserve the existing service boundary and public
> contracts.

---

## 0. Where we stand today

The Strategy Factory already ships a partially-built VIE. This review
must be honest about that surface before proposing anything new,
otherwise we invent architecture that duplicates what's already there.

### 0.1 Physical layout (already deployed)

```
                   ┌──────────────┐
   HTTPS caller  →  │ factory-back │  ← Emergent-managed backend
                   │  end :8001   │    • app/vie/client.py (thin SDK)
                   │              │    • legacy/engines/ai_workforce/
                   │              │      router.py + circuit_breaker + scorer
                   └──────┬───────┘
                          │  HTTP  http://factory-vie:8100
                          ▼
                   ┌──────────────┐
                   │ factory-vie  │  ← Separate container, own image
                   │   :8100      │    /vie/  in the repo
                   │              │    • api.py    → /generate /probe /providers /health
                   │              │    • registry.py  (6 provider adapters, env-driven)
                   │              │    • router.py    (task → provider chain)
                   │              │    • providers/*  (openai, anthropic, gemini,
                   │              │                     groq, deepseek, kimi)
                   └──────────────┘
                          │
                          ▼
                    ┌──────────────────────────────────┐
                    │  external provider APIs          │
                    │  (only accessed FROM the VIE)    │
                    └──────────────────────────────────┘
```

**Critical invariant already in place:** application code (backend
routers, engines) never talks to a provider SDK directly. It always
goes through `app/vie/client.py` → HTTP → `factory-vie`. This means
adding, removing, or replacing a provider does **not** require touching
application code — the VIE is genuinely vendor-independent by design.

### 0.2 What is production-grade today (keep)

| Component | Location | Verdict |
|---|---|---|
| **Provider adapter contract** — one abstract method `generate(prompt, system, model, temperature, max_tokens) → {output, model, usage}` | `vie/providers/base.py` | ✅ Clean. Every provider conforms; adding a new provider is one class. |
| **Registry** — env-driven, missing keys = provider marked `unavailable` (no crash) | `vie/registry.py` | ✅ Correct failure mode. Boot is resilient. |
| **Task-based router** — `route(task, available_names) → ordered chain` | `vie/router.py` | ✅ Good starting shape. Task map is env-overridable via `VIE_TASK_MAP` JSON. Chains fall through on failure. |
| **Circuit breaker + scorer + telemetry** (workforce router) | `backend/legacy/engines/ai_workforce/router.py` (250 LoC), `circuit_breaker.py` (106 LoC), `scorer.py` (143 LoC) | ✅ Substantial. Already tracks per-provider success rate, applies score-based reordering, opens circuits on repeated failure. |
| **`llm_call_log` schema** — `ts, task, provider, model, outcome, latency_ms, tokens_in, tokens_out, error` | Mongo (production) | ✅ Right shape for cost + health analytics. |
| **`/probe` endpoint** — send a tiny prompt to every provider, measure latency and success | `vie/api.py:132` | ✅ Excellent — the primitive that a real health monitor is built on. |
| **`/api/llm/health-by-provider`, `/api/llm/diagnostics`** | `legacy/api/llm_health.py`, `llm_diagnostics.py` | ✅ Already surfaces per-provider health to the dashboard. |

**About 70% of the VIE architecture the review is asking for is
already implemented.** The gap is not "we need a VIE"; the gap is:
capability taxonomy, prompt versioning, embedding provider abstraction,
cost governance, and knowledge-engine wiring. That is what this
document focuses on.

### 0.3 What is missing or thin (the actual work)

| Gap | Severity | Section |
|---|---|---|
| Task taxonomy is 6 buckets; the review lists 11 capabilities | Major | §2 |
| Model-per-provider is one static default; no capability→model table | Major | §2 |
| No cost accounting or budget enforcement — token counts are logged but never gate a call | Critical | §4 |
| Prompts are inline string literals scattered across ~40 engine files | Major | §5 |
| Embedding capability has zero coverage — no provider does embeddings today | Major | §6 |
| Knowledge Engine has a similarity API but AI cannot consult it during generation | Major | §7 |
| No governance boundary between what AI proposes and what enters the deploy path | Critical | §8 |

Everything else in this document elaborates on how to close those seven
gaps without breaking the two dozen callers that already talk to the VIE.

---

## 1. Multi-Provider Architecture

### 1.1 Current state
- Six providers, one adapter each, all conform to `BaseProvider.generate()`.
- Registry instantiates every provider regardless of key presence; the
  `available` flag is a runtime property.
- New provider = new file under `vie/providers/`, add to `_ORDER` +
  `_CLASSES` in `registry.py`. Zero application-code change.

### 1.2 Recommended enhancements

**R1.1 — Provider capabilities matrix.**
Extend `BaseProvider` with a **static class attribute** declaring what
the provider can do. Not what it's routed to (that's runtime routing),
but what it's *capable of* (a hard filter). Sketch:

```python
class OpenAIProvider(BaseProvider):
    name = "openai"
    api_key_env = "OPENAI_API_KEY"
    default_model = "gpt-4o-mini"
    capabilities = frozenset({
        "chat", "code_generation", "reasoning", "long_context",
        "embeddings", "vision", "structured_output", "tool_use",
    })
    max_context_tokens = 128_000
    supports_streaming = True
```

The router can then answer *"can any available provider serve this task?"*
by intersecting `task.required_capabilities` with each candidate's
`capabilities`. Groq cannot serve `embeddings`; the router should never
route an embedding job there.

**R1.2 — Provider tiers.**
Add a `tier` attribute (`fast | standard | frontier`). This lets the
router honour operator intent — a *fast* strategy critique should
prefer Groq/Gemini-Flash over Claude Opus even when both are healthy.

**R1.3 — Provider adapters over `litellm`.**
The current adapters call each provider's native SDK. The one existing
`llm_call_log` error line shows a `litellm` import path. **Recommendation:**
migrate every adapter to `litellm`'s unified interface. It normalises
the request/response shape, streaming, function-calling, and pricing
metadata across providers. Adding a 7th provider becomes a one-line
model-string change.

**R1.4 — OpenRouter as a meta-provider.**
Treat OpenRouter as a special adapter that itself exposes a `capabilities`
matrix by re-shaping OpenRouter's `/v1/models` catalogue. This gives us
instant access to any new model as the ecosystem evolves, without a
code change. Cost is slightly higher per token, but the latency to
adopt a new frontier model drops from days to zero.

### 1.3 Contract stability guarantee
The `POST /generate` HTTP contract on `factory-vie` stays byte-identical.
All of R1.1–R1.4 are internal to `vie/`. Existing backend callers
notice zero contract change.

---

## 2. Capability-Based Routing

### 2.1 Current state
`DEFAULT_TASK_MAP` in `vie/router.py` has 6 buckets:
`research | generation | validation | explanation | fast | default`.
Every entry is an ordered provider chain; no model selection, no
capability check, no request-shape awareness.

### 2.2 Recommended taxonomy — 12 capabilities

The user's list of 11 tasks, formalised as a **capability enum** with
explicit request-shape hints and default provider preference. This is
the single source of truth the router reads:

| Capability | Latency budget | Context | Preferred providers (fallback order) | Preferred model tier |
|---|---|---|---|---|
| `strategy_generation` | 20 s | ~4k in / ~2k out | anthropic → openai → gemini → deepseek | frontier |
| `strategy_critique` | 10 s | ~8k in / ~1k out | anthropic → openai → gemini | standard |
| `strategy_mutation` | 15 s | ~4k in / ~2k out | deepseek → openai → anthropic | standard |
| `code_generation` (cAlgo cbot) | 30 s | ~8k in / ~4k out | anthropic → openai → deepseek | frontier |
| `documentation` | 20 s | ~8k in / ~2k out | anthropic → openai → gemini | standard |
| `knowledge_extraction` (PDF/text → structured) | 25 s | ~32k in / ~4k out | gemini → anthropic → openai | standard |
| `embeddings` | 2 s | ~8k in / N/A | openai → gemini | (see §6) |
| `summarization` | 8 s | up to 128k in / ~1k out | gemini → anthropic → groq | fast |
| `classification` (verdict/label) | 3 s | ~2k in / ~200 out | groq → gemini → deepseek | fast |
| `research` (open-ended, tool-use) | 60 s | ~16k in / ~4k out | anthropic → openai → gemini | frontier |
| `long_context_reasoning` (>32k tokens) | 30 s | 200k+ | gemini → anthropic | frontier |
| `guardrails_check` (safety classifier) | 3 s | ~2k in / ~100 out | groq → deepseek | fast |

**Router selection algorithm** (proposed, replaces `route()`):

```
def route(cap: Capability, req: GenerateRequest) -> list[ProviderChoice]:
    # 1. Hard filter: provider must be available AND declare the capability
    candidates = [p for p in registry.available()
                  if cap.name in p.capabilities]

    # 2. Context filter: drop providers whose max_context < req.context_tokens
    candidates = [p for p in candidates
                  if p.max_context_tokens >= req.context_tokens_est]

    # 3. Health filter: exclude providers with open circuit breakers
    candidates = [p for p in candidates
                  if not circuit_breaker.is_open(p.name)]

    # 4. Cost gate: exclude providers whose est. cost exceeds request budget
    candidates = [p for p in candidates
                  if cost_estimator.estimate(p, req) <= req.max_cost_usd]

    # 5. Score-sort by (tier match, historical success rate, latency p50, cost)
    return sorted(candidates, key=lambda p: scorer.score(p, cap, req))
```

Each of the five filters is independent, testable, and toggleable via
env flags for gradual rollout.

**Task→capability mapping** is a thin lookup table in the caller:
`generate_strategy()` → `Capability.strategy_generation`. Callers never
name providers; they name capabilities. Provider choice is 100% VIE's
concern.

### 2.3 The routing dial

Every VIE call accepts an optional **routing hint** object:

```json
{
  "capability": "strategy_generation",
  "quality_bias": 0.8,   // 0=cheapest, 1=best
  "latency_budget_ms": 20000,
  "max_cost_usd": 0.10,
  "provider_hint": null  // operator override, respected but audited
}
```

`quality_bias` is the single knob dashboards expose. Everything else
has a sensible default from the capability table.

---

## 3. Provider Health

### 3.1 Current state
- `ai_workforce/circuit_breaker.py` implements per-provider circuit
  breakers with open/half-open/closed states.
- `/api/llm/health-by-provider` returns rolling success rate per
  provider.
- `/vie/probe` sends a canary prompt to every available provider.

### 3.2 Recommended enhancements

**R3.1 — Health scorer, not just a boolean.**
Instead of `available: bool`, compute a rolling **health score** per
(provider, capability) pair:

```
health = 0.4*(success_rate_5min) + 0.3*(1 - p95_latency_norm)
       + 0.2*(1 - error_rate_1h) + 0.1*(1 - rate_limit_1h)
```

The router sorts by this composite, not by a flat "available" flag.

**R3.2 — Retry policy in the router, not the caller.**
`vie/router.py` should own the retry loop:
```
for provider in ordered_candidates:
    try:  return call(provider, request, timeout=capability.timeout)
    except (RateLimit, Timeout, TransientError):
        breaker.record_failure(provider);  continue
    except Non-retryable:
        raise
raise NoProviderAvailable(...)
```
Callers get one clean result or one clean exception — never a
half-retried mess.

**R3.3 — Adaptive degradation.**
When *no* frontier provider is healthy, the router should be allowed
to *degrade* — either serve a lower-tier model or return a structured
`degraded_result` envelope that flags the caller. The current path
returns an exception; UI hides the problem instead of showing it.

**R3.4 — Continuous background probing.**
The existing `/probe` endpoint is on-demand. A background task should
call it every N seconds (default 300 s) and update the health-scorer
inputs so the router doesn't need to learn about a provider outage
from a real user request. Cost: ~$0.001/day at 300 s interval per
provider.

**R3.5 — Explicit timeouts.**
Every capability declares its own timeout (see §2.2 table). The
current 60 s hard-coded timeout is wrong for `classification` (should
be 3 s) and wrong for `long_context_reasoning` (should be 60 s+).

---

## 4. Cost Management

### 4.1 Current state
- `llm_call_log` records `tokens_in`, `tokens_out`, `provider`, `model`.
- No cost table anywhere.
- No budget enforcement.
- No cost visibility in the dashboard.

### 4.2 The design

**R4.1 — Cost table.**
A static JSON at `vie/cost_table.json` mapping
`(provider, model) → {input_usd_per_1k, output_usd_per_1k, embedding_usd_per_1k}`.
Refreshed manually when providers update pricing (quarterly at most).
Falls back to a conservative default when a model is unrecognised.

**R4.2 — Cost estimator.**
Pure function:
```
estimate(provider, model, tokens_in_est, tokens_out_est) → USD
```
Called by the router *before* dispatch (§2.2 step 4). Blocks calls that
would exceed the request's `max_cost_usd`.

**R4.3 — Post-call cost recording.**
Every `llm_call_log` insert now also records `cost_usd`, derived from
actual `usage.prompt_tokens` + `usage.completion_tokens` × cost table.
Zero new schema — just a computed field.

**R4.4 — Budget envelopes.**
Three enforceable budgets (all soft-configurable, hard-coded defaults):
- **Per-request** (`max_cost_usd`, from the routing hint)
- **Per-user per-24h** (default $5)
- **Global per-24h** (default $100 — a circuit-breaker for runaway loops)

Enforcement point: single middleware in `vie/api.py` that reads
current spend from `llm_call_log` and rejects with HTTP 429 + a
`budget_exceeded` structured error when the envelope is used up.

**R4.5 — Dashboard.**
`/api/knowledge/costs/24h` (new endpoint, thin aggregation) →
`{by_provider: {…}, by_capability: {…}, by_user: {…}, total_usd: …}`.
Dashboard renders it as a stacked bar. The existing dashboard "providers
available: 1/6" cell becomes an actionable "$X.XX spent today · Y%
of budget" cell.

**R4.6 — Comparative-cost surface.**
For every `/generate` response, VIE optionally includes
`alternatives: [{provider, model, est_cost_usd, est_quality_score}]`
so operators can see *what the router chose not to use and why*. This
is the auditability that keeps trust in autonomous routing.

---

## 5. Prompt Architecture

### 5.1 Current state
Inline string literals in ~40 engine files. Every prompt is a code
change. No history, no diffing, no A/B.

### 5.2 The design

**R5.1 — Prompt Registry.**
A new package `backend/app/prompts/` containing:
```
prompts/
├── __init__.py
├── registry.py            # Registry.get("strategy_generation", version="1.2")
├── loader.py              # loads YAML/JSON from prompts/library/
└── library/
    ├── strategy_generation/
    │   ├── v1.0.yaml
    │   ├── v1.1.yaml
    │   └── current -> v1.1.yaml    (symlink)
    ├── strategy_critique/
    │   └── v1.0.yaml
    ...
```

**R5.2 — Prompt file schema.**
```yaml
name: strategy_generation
version: "1.1"
description: |
  Generate a candidate strategy JSON given a pair, timeframe, style.
capability: strategy_generation
system_message: |
  You are a quantitative trading strategist. Return ONLY the
  strategy JSON object; no prose.
user_template: |
  Generate a strategy for {pair} on the {timeframe} timeframe.
  Style: {style}. Include entry rules, exit rules, and 3 free
  parameters with sensible bounds.
input_variables: [pair, timeframe, style]
output_schema:
  $ref: schemas/strategy_v1.json
tests:
  - name: xauusd_h4_smoke
    inputs: {pair: XAUUSD, timeframe: H4, style: breakout}
    assertions:
      - jsonpath: $.entry_rules
        exists: true
```

**R5.3 — Every call includes the prompt version.**
`GenerateRequest` gains `prompt: {name, version}` alongside the
literal `prompt` string (which becomes the *fallback* for callers that
don't yet use the registry). `llm_call_log` gains `prompt_name` +
`prompt_version` columns → full audit trail.

**R5.4 — Prompt tests.**
Every prompt YAML has an `tests:` block. A CI step runs each prompt
against a stub provider (mocked) to prove the template renders and the
output-schema validator accepts a canonical example. Failing prompts
fail CI — no untested prompt reaches production.

**R5.5 — Provider-independence guarantee.**
Prompts are provider-neutral by design. Every prompt YAML has
optional per-provider *overlays* for tuning:
```yaml
provider_overlays:
  anthropic:
    system_message_prefix: "Think step by step. "
  openai:
    response_format: { type: "json_object" }
```
The overlay is applied by the VIE at dispatch time; the caller stays
provider-agnostic.

**R5.6 — Rollback.**
Bumping the `current ->` symlink is the only production change. Zero
code change to roll a prompt back.

---

## 6. Embedding Architecture

### 6.1 Current state
- `EmbeddingSimilarityStub` in `app/knowledge/similarity.py` raises
  `NotImplementedError`. Reserved for Phase 2.
- Knowledge API (`/api/knowledge/nearest`) picks its backend via
  `SIMILARITY_BACKEND=rule_based|embedding` env var — contract already
  stable across the swap.
- No provider adapter today implements embeddings.

### 6.2 The design (do not implement yet — this is the spec)

**R6.1 — Embedding provider capability.**
Extend `BaseProvider` with `embed(text: str | list[str], model: str | None) → list[list[float]]`. Only providers that
declare `"embeddings"` in `capabilities` implement it; the base class
raises `NotSupportedError` by default.

**R6.2 — Embedding store.**
A new collection `strategy_embeddings` in the *KB database only*
(never the production DB):
```
{
  strategy_id, canonical_hash,
  embedding_provider, embedding_model,
  embedding_version,           # bumped when we re-embed the corpus
  dim,                         # 1536 for text-embedding-3-small
  vector: [float * dim],
  computed_at,
  learning_only: True          # inherits the KB guardrail
}
```
Indexed on `strategy_id` + `embedding_version`. Vector search is done
with `$vectorSearch` (Atlas) or naive cosine (self-hosted); the two
paths differ only in the query executor, not the schema.

**R6.3 — `EmbeddingSimilarity` implementation.**
Fills in the `SimilarityBackend.rank` stub. At query time:
1. Look up query embedding — either compute fresh (60 % of the time)
   or retrieve a cached embedding by `canonical_hash`.
2. Fetch top-k by cosine distance from `strategy_embeddings`.
3. Return `SimilarityMatch` list — *identical shape* as
   `RuleBasedSimilarity`. Callers of `/api/knowledge/nearest` see the
   same JSON.

**R6.4 — Backfill job.**
A one-time script `scripts/embed_kb_corpus.py` runs through the 140
KB strategies, calls `vie.embed()`, writes `strategy_embeddings`.
Idempotent — re-running skips already-embedded rows for the current
`embedding_version`. Cost estimate: 140 rows × ~500 tokens × 
$0.02 / 1M tokens = **$0.0014 total**. Negligible.

**R6.5 — Contract stability.**
`/api/knowledge/nearest` response is byte-identical between the two
backends. `SimilarityMatch` fields are the API surface; both backends
populate them. This was designed in during Phase 1.6 §E — validated
by inspection.

---

## 7. Knowledge Engine Integration

### 7.1 Current state
- Historical KB is isolated (Phase 1.5) — `strategy_knowledge_base` DB.
- `KnowledgeRepository` structurally refuses writes and prepends
  `{learning_only: True}` to every read/aggregate (Phase 1.6 §A).
- Knowledge API exists (`/api/knowledge/*`, 6 endpoints).
- AI cannot yet consult the KB during strategy generation because
  there's no wiring — the AI-facing flows don't call the Knowledge
  API today.

### 7.2 The design

**R7.1 — Reasoning context injection.**
When VIE serves a `strategy_generation` capability, it *may* fetch
the top-k KB neighbours (via `/api/knowledge/nearest`) and prepend
them to the prompt as **reasoning context**:

```
CONTEXT (historical strategies with similar structure — READ-ONLY):
{{#each neighbours}}
  Strategy {{strategy_id}} ({{pair}} {{timeframe}}):
    PF={{legacy_metrics.profit_factor}}, return={{legacy_metrics.total_return_pct}}%
    Failure reason: {{evaluation.overfit_risk > 60 ? "high overfit risk" : "underperformed OOS"}}
{{/each}}

Learn from the failures above. Do NOT propose a strategy that is a
near-duplicate of any listed row (canonical_hash: {{list}}).
```

**R7.2 — Two enforcement rails.**

1. **Prompt-side (soft):** the reasoning context is a *hint*, not a
   filter. The AI is told the historical fingerprints; it may still
   propose a near-duplicate. That's fine — rail 2 catches it.
2. **Repository-side (hard):** after the AI returns a candidate,
   compute its `canonical_hash`. Query `KnowledgeRepository` for a
   canonical match. If any KB row matches, the response is annotated
   `historical_lineage: {matches: [...], warning: "structural clone of KB row X"}` — but the strategy still enters the strategies collection with `eligible_for_deploy: False` (draft state) so it can never leak into deployment without going through the current-framework pipeline.

**R7.3 — What AI can do, formally.**
Read-only capabilities the AI **may** consume:
- `/api/knowledge/nearest` — retrieve context
- `/api/knowledge/families/{hash}` — inspect a family
- `/api/knowledge/champions` — see what worked historically
- `/api/knowledge/strategy/{id}` — deep-dive a specific historical entry

Capabilities AI **cannot** consume by design (there are no such
endpoints — the surface doesn't exist):
- Write to `strategy_knowledge_base` (refused by `KnowledgeRepository`)
- Read from `strategies` production collection unless as an
  identified caller with a JWT — no service-role bypass
- Skip the `StrategyRepository` filter — impossible, since the
  strategies API only accepts writes to `eligible_for_deploy: False`
  (draft) state, and the promotion path goes through governance code
  that lives outside the AI-callable surface

**R7.4 — Audit trail.**
Every AI call that consumes KB context writes a row to
`knowledge_query_log`: `{caller, capability, query_hash, retrieved_ids, ts}`.
This is what makes meta-learning possible in a later phase — you can
see which historical entries the AI actually used and correlate to
outcomes.

---

## 8. Governance — hard invariants

The following are **structural, not procedural**. They cannot be
bypassed by an AI regardless of prompt phrasing, because they live at
layers the AI cannot reach.

### 8.1 What AI can never do

| Attempted action | Blocker |
|---|---|
| Directly write to production `strategies` | Only `POST /api/strategies` accepts writes; requires a real JWT identity; new strategies default to `eligible_for_deploy: False` |
| Bypass `eligible_for_deploy` on reads | `StrategyRepository` (Phase 1.6-final) — 3 sites, 0 residual direct reads |
| Read/modify historical KB via any active path | `KnowledgeRepository` (Phase 1.6 §A) — every write method raises `_ImmutableError` |
| Skip validation | Governance pipeline lives in `backend/legacy/api/governance.py` — not exposed to VIE |
| Modify portfolio allocation | `/api/portfolio/*` requires `admin` or `developer` role; VIE has no role |
| Escape the routing budget | Budget middleware is in `vie/api.py`, not the caller — the AI's own prompt can't disable it |
| Escalate to `deployment_readiness: READY` | `evaluate_from_legacy_metrics()` in `app/knowledge/evaluation.py` is structurally incapable of emitting READY (locked by unit test) |

### 8.2 What AI *can* do

- Propose a draft strategy → written to `strategies` with
  `eligible_for_deploy: False`, visible to human operators via
  the normal UI
- Critique a strategy → response goes into a UI panel; no side-effects
- Suggest a mutation → output is a new draft (as above)
- Consult the KB for reasoning → read-only, audited

The pipeline from "AI draft" → "deployed strategy" runs through the
same governance code as a human-authored strategy. AI is a peer, not
a superuser.

---

## 9. Roadmap — sequenced, testable, reversible

Each step ships behind a feature flag and can be rolled back
independently. **No step depends on a later step.**

| # | Step | Prereq | Effort | Reversible? |
|---|---|---|---|---|
| **P2.1** | Wire the first provider key (Anthropic) into prod `.env`; restart factory-vie; confirm `/api/vie/providers` shows it available; test the existing `/generate` for `research` and `explanation` tasks | none | 30 min | Yes — remove key |
| **P2.2** | Introduce `Capability` enum + capability→provider table (§2.2). Replace `route()` with the capability-aware selector. Existing `task=` callers keep working via a shim | P2.1 | 1 day | Yes — feature flag `VIE_CAPABILITY_ROUTER=false` |
| **P2.3** | Cost table + estimator + post-call `cost_usd` field in `llm_call_log` | P2.2 | 1 day | Yes — cost is additive; no gating yet |
| **P2.4** | Global + per-user 24h budgets + 429 enforcement middleware | P2.3 | 0.5 day | Yes — set budgets to $999 to effectively disable |
| **P2.5** | Prompt Registry (§5) with 3 seed prompts migrated (`strategy_generation`, `strategy_critique`, `strategy_mutation`). Registry-aware VIE dispatch behind `VIE_PROMPT_REGISTRY=true` | P2.2 | 2 days | Yes — flag off returns to inline prompts |
| **P2.6** | Health scorer + adaptive routing + background probing | P2.2 | 1 day | Yes — flag off returns to static chain |
| **P2.7** | Cost + provider-health dashboard cards (frontend, ~150 LoC) | P2.3, P2.6 | 1 day | Yes — pure UI |
| **P2.8** | Embedding capability + `strategy_embeddings` collection + backfill of 140 KB rows + `EmbeddingSimilarityStub.rank` implementation. `SIMILARITY_BACKEND=embedding` flip. | P2.2 | 1.5 days | Yes — `SIMILARITY_BACKEND=rule_based` reverts |
| **P2.9** | Knowledge Engine ↔ VIE reasoning-context injection (§7) with `historical_lineage` audit annotation | P2.5, P2.8 | 1 day | Yes — flag off skips context injection |
| **P2.10** | Migrate the ~40 legacy engine inline prompts to the Registry (parallel with feature-flag safety) | P2.5 | 3–5 days | Per-prompt |

**Approx total time to full Phase 2 coverage:** ~2 weeks of focused
work if run sequentially. P2.1–P2.4 is roughly one working day and
delivers the platform's first real AI-assisted operation.

---

## 10. What is deliberately NOT in this phase

- **No implementation.** This document is design-only.
- **No prompt authoring.** New prompts will be written under P2.5+,
  not now.
- **No provider keys.** No `.env` changes.
- **No test fixtures against real providers.** All prompt tests run
  against a stub provider until P2.1 lands the first real key.

---

## 11. Alignment with the review's success criteria

| Criterion | Where addressed | Status |
|---|---|---|
| Multi-provider without app-code change | §1 + existing VIE contract | ✅ Already true; enhanced with capabilities matrix |
| Capability-based routing over 11 tasks | §2 taxonomy of 12 capabilities | ✅ Designed |
| Provider health with failover/retry/degradation | §3 five sub-recommendations | ✅ Designed |
| Cost management + budgets + dashboard | §4 six sub-recommendations | ✅ Designed |
| Versioned/reusable/audited prompts | §5 Prompt Registry | ✅ Designed |
| Embedding architecture (no impl) | §6 R6.1–R6.5 | ✅ Designed |
| KB integration as read-only reasoning | §7 R7.1–R7.4 | ✅ Designed |
| AI cannot deploy / modify portfolios / bypass governance | §8.1 matrix + §8.2 what AI *can* do | ✅ Designed |
| Roadmap | §9 ten steps, each reversible | ✅ Provided |

## 12. Recommended next call

Approve or amend §2.2 (capability taxonomy) and §9 (roadmap), then
execute **P2.1** — a 30-minute step that connects the first provider
and confirms the existing VIE serves a real `/generate` request. That
gives us a live baseline to build the rest of Phase 2 on top of.

Everything else is downstream of that first successful call.
