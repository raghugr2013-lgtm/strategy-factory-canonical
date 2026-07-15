# Strategy Factory — Evolution Roadmap 2026

**Purpose:** review the current v1.1.1 architecture and recommend the highest-impact next investments. Long-term north star: **evolve Strategy Factory from a strategy generator into a self-improving AI strategy research platform.**

---

## 1. Current-state assessment (Feb 2026, post-recovery)

| Layer | Status | Notes |
|---|---|---|
| Backend routing (90 legacy routers + Phase-1 core) | 🟢 healthy | zero known mismatches after `81cd724` |
| MongoDB persistence + migration path | 🟢 healthy | recovery migration idempotent, 2 080 docs live |
| Auto-maintenance (BID + BI5) | 🟢 healthy | persists, resumes, downloads Dukascopy on schedule |
| Knowledge Layer L1 + L2 | 🟡 minimal-viable | metadata retrieval only; 141 index rows live; no outcome-signal ingestion |
| AI Workforce (VIE + 6 providers) | 🟡 partial | env-key detection landed, but no health monitor, no cross-provider failover audit, no per-task routing knobs |
| Continuous learning loop | 🔴 not built | generate → validate → repair → backtest → optimize → mutate → learn → store is aspirational; only fragments exist |
| Portfolio intelligence | 🟡 fragmentary | routers mounted, correlation/regime scoring live, but not consulted before generation |
| Operator dashboard | 🟡 sparse | MissionBriefing exists; no scheduler-health/knowledge/last-generation tiles |

The recovery investment is complete. The next return on effort is highest in **closing the learning loop** and **replacing per-strategy generation with portfolio-aware generation**.

---

## 2. Recommended priority (my read of impact vs. build cost)

I'd order them differently from the raw P1–P5 list you sent, because a small piece of P3 (write outcomes back to the knowledge index) unlocks the rest of P1 for free:

| Rank | Investment | Why it moves the needle first | Rough cost |
|---|---|---|---|
| **1** | **Outcome-signal ingestion into the knowledge index** — piggyback on the existing validate / backtest / optimize / mutate endpoints and write a compact `outcome_events` collection, plus fold aggregate stats back into `strategy_knowledge_index`. Turns the learning layer from "text-similarity retrieval" into "outcome-conditioned retrieval". | Unlocks P1, P3 partially, and every downstream A/B test. Small, additive, ~2 days. | **S** |
| **2** | **AI Workforce health + failover audit** — instrument every provider call with structured latency / error / cost telemetry, expose `/api/llm/health` with per-provider circuit-breaker state, wire failover into `llm_runner.run_chat` so a dead provider transparently rotates to next-in-preference. | High operator visibility, immediate cost + reliability win. ~2 days. | **S** |
| **3** | **Continuous learning workflow orchestrator** — a supervisor that stitches generate → validate → repair → backtest → optimize → mutate and emits an `outcome_events` row at every stage. Reuses existing engines, adds a `learning_run_id` correlation ID. | This is the actual "self-improving" moat. ~1 week (thin) or ~3 weeks (production-grade). | **M** |
| **4** | **Portfolio-aware generation** — inject portfolio state (exposure, correlation matrix, regime tag, capital budget, allocated %) into the LLM system prompt via a new `portfolio_block` in the knowledge injection stream. Uses the existing `portfolio_intelligence` router. | Kills the biggest quality gap you'll see once P1–P3 are live — new strategies stop replicating existing exposure. ~1 week. | **M** |
| **5** | **Operator dashboard tiles** — assemble a single `/api/dashboard/health-mosaic` endpoint that returns all seven tiles at once (BID/BI5 last success, knowledge index size, provider health, scheduler health, injection usage, time-since-last-generation). Frontend adds a MosaicRail. | Purely visibility; low complexity but high operator confidence. ~2 days. | **S** |

Small housekeeping wins (all can ship any time, cost ~1 hour each):
- Purge stale pre-fix BI5 status rows on boot (**done this pass** — see below).
- Configurable `KNOWLEDGE_INJECTION` via `/api/knowledge/config` instead of env var.
- Weight curated repos above search-query repos in ingestion scoring.

---

## 3. What I shipped this pass (immediate wins)

Committed to the local branch, ready to push:

### 3.1 Stale BI5 status cleanup
`app/main.py::lifespan` now runs a one-shot `delete_many` at boot against `auto_maintenance_status`, dropping any row whose `bi5_runner_error` still matches `"'dict' object has no attribute 'symbol'"` — that error string cannot be produced by the post-`976e04e` code, so any row carrying it is definitionally pre-fix debris. Idempotent (re-run is a no-op), non-fatal (never crashes boot). Log line: `"auto-maintenance: purged N stale pre-fix BI5 error rows"`.

This is the entirety of the code change this pass — everything else in this document is a proposal awaiting your steer.

---

## 4. Detailed recommendations per priority

### 4.1 Outcome-signal ingestion (my P1)

**Model change** — add one collection:
```
outcome_events
  _id: ObjectId
  learning_run_id: str      # correlation across the whole loop
  strategy_hash: str
  stage: "generate"|"validate"|"repair"|"backtest"|"optimize"|"mutate"
  status: "pass"|"fail"|"partial"|"skipped"
  reason: str               # short human-readable diagnosis
  metrics: {pf, dd, trades, sharpe, calmar, drawdown_days, ...}
  operator_feedback: {rating: 1..5, comment: str}?  # optional
  provider: str?            # openai|anthropic|...
  cost_usd: float?          # provider call cost
  duration_ms: int
  ts: datetime
```

**Read model change** — the knowledge indexer folds outcome_events per strategy_hash into a new per-index-row block:
```
strategy_knowledge_index[hash].outcomes = {
    validate: {pass_rate, common_fail_reasons[]}
    repair:   {success_rate, avg_iterations}
    backtest: {best_pf, best_dd, best_sharpe}
    optimize: {best_pf_uplift_pct, best_dd_reduction_pct}
    operator: {avg_rating, n_ratings}
}
```

**Retriever change** — outcomes multiplies the base score: winners with high `validate.pass_rate` + high `operator.avg_rating` get another +2.0.

**Where to hook** — none of the engines need to know about the collection. A single decorator `@emit_outcome("stage_name")` around the six existing endpoint handlers writes the events. Trivial, non-invasive.

### 4.2 AI Workforce failover + telemetry (my P2)

**Instrument `llm_runner.run_chat`** — around every VIE call, capture `(provider, model, latency_ms, ok, http_status, error_class, prompt_tokens, completion_tokens, cost_usd)` into a per-process circular buffer AND `llm_call_log` collection (already exists via `log_llm_call`).

**Circuit-breaker per provider** — track error rate over rolling 30-call window. If > 40 %, mark provider as `open`; retry health probe every 60 s. `run_chat` skips `open` providers and rotates to next-in-preference.

**Health endpoint** — `/api/llm/health` returns per-provider `{state:"closed"|"half_open"|"open", latency_p50_ms, error_rate_1h, tokens_1h, cost_1h_usd, last_success_ts, last_error, model}`. This is exactly the AI Workforce tile you asked for.

**Provider selection** — no config change. Existing `task_preference` in `llm_config.py` is authoritative; the circuit-breaker just filters unavailable providers before iteration.

### 4.3 Continuous learning workflow (my P3)

**Thin version (1 week)** — a `learning_supervisor` async task that:
1. Pulls the next `learning_run` off a Mongo work queue.
2. Calls existing endpoints in sequence: `generate → validate → (repair if fail) → backtest → optimize → mutate`.
3. Emits an `outcome_events` row per stage.
4. Writes the terminal doc to `strategy_library` with `learning_run_id` provenance.
5. Kicks the knowledge index rebuild.

**Production-grade (3 weeks)** — add branching (mutate-many, keep-best-of-N), backoff on repeat failures, per-stage cost budget, operator approval gate before promotion, dead-letter queue.

Recommend shipping the thin version first — it's the smallest change that gives you a full end-to-end learning loop.

### 4.4 Portfolio-aware generation (my P4)

**Portfolio snapshot** — before each generate call, fetch:
```
GET /api/portfolio-intelligence/current
GET /api/portfolio-intelligence/correlation
GET /api/regime/current  (or the equivalent)
```
Compose a `portfolio_block` string:
```
Current portfolio state:
  active strategies: 14 (long: 9, short: 5)
  exposure by pair: EURUSD 32%, XAUUSD 21%, GBPUSD 18%, ...
  regime tag: risk-off / trending-USD
  free capital budget: 34%
  correlation clusters:
    - EURUSD/GBPUSD trend-following ρ=0.71 → adding more is redundant
    - XAUUSD mean-reversion is isolated → good diversifier
```

Inject this above the `## Prior knowledge` block in the LLM system prompt (already there in `strategy_engine._try_llm_generation`). Same on/off env flag as knowledge, or unify into one config surface.

### 4.5 Operator dashboard mosaic (my P5)

Single new endpoint:
```
GET /api/dashboard/health-mosaic
→ {
    "bid_last_success": {"ts": ISO, "symbols_fresh": 6, "symbols_stale": 0},
    "bi5_last_success": {"ts": ISO, "symbols_fresh": 6, "symbols_stale": 2},
    "knowledge_index":   {"total": 141, "last_rebuild": ISO, "coverage_by_pair": {...}},
    "ai_providers":      {"open": 0, "closed": 4, "half_open": 1, "last_error_provider": null},
    "scheduler":         {"enabled": true, "next_bid_run": ISO, "next_bi5_run": ISO},
    "knowledge_injection": {"enabled_via_env": true, "invocations_1h": 42, "last_prompt_length_chars": 1837},
    "last_generation":     {"ts": ISO, "strategy_hash": "...", "status": "pass"}
}
```

Frontend adds a `MosaicRail` component in the Command Shell rendering these seven tiles in a single column — no new backend fetches per tile, one call fills them all.

### 4.6 Housekeeping wins

**A. Make `KNOWLEDGE_INJECTION` UI-configurable.** Move the flag from env var to a Mongo `knowledge_config._id="global"` doc with `{injection_enabled: bool, top_k: int, include_failures: bool, tfidf_rerank: bool}`. Add `POST /api/knowledge/config` (admin). Reasoning: operators shouldn't have to `docker exec` + `.env` edits to A/B a flag; and per-deployment overrides can layer via env if we keep env-var as fallback.

**B. Prioritise curated repos over search results.** In `collector.py`, tag each ingested row with `source_kind = "curated" | "search"`. Downstream in `strategy_ingestion/normalizer.py`, add a `+0.5` score bump for curated. This directly answers: *"prioritize curated repositories over increasing the number of indexed strategies."*

**C. Stale BI5 cleanup on boot.** ← Shipped this pass.

---

## 5. Non-recommendations (things NOT to build)

- **Do NOT introduce a vector database yet.** Metadata retrieval is producing usable results (141 rows indexed against 2 080 source docs; `_score` differentiates cleanly in eyeball tests). Adding pgvector/qdrant/faiss doubles the ops surface for a marginal quality bump. Revisit only after outcome-signal ingestion (P1) proves the ceiling of pure metadata.
- **Do NOT rewrite the generation prompt template from scratch.** The v01 template plus a `## Prior knowledge` block plus a `## Portfolio state` block is already close to what a real quant research desk would prompt. Iterate; don't restart.
- **Do NOT gate live trading on the learning loop yet.** Recovered strategies are learning-only (via `__migration_source` fence). Newly-generated ones from the loop should also go through a *human-approval* gate before live trading until you have at least 200 loop-generated outcomes to compare against.

---

## 6. What I need from you

Pick 1–3 of the ranked recommendations above to ship next. My default recommendation:

1. **P1 outcome-signal ingestion** (small, unlocks everything)
2. **P2 AI Workforce health + failover** (small, immediate operator confidence)
3. **P5 mosaic dashboard** (small, makes P1 + P2 visible)

That is ~1 week of net-new code for a step-change in observability + a proper learning loop foundation. P3 continuous learning and P4 portfolio-aware can then be built on top of the P1 outcome events without any of P1/P2/P5 changing shape.

If you'd rather I dive straight into any specific one (or a different combination), just say the word and I'll start.
