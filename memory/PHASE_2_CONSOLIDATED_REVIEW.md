# Phase 2 — Consolidated Architecture Review
### Bringing Phases 2A · 2B · 2C · 2D together into a single implementation sequence

> **Status:** review only — no implementation yet.
> This document is the cross-cutting synthesis of the four Phase-2 architecture
> reviews. It does **not** repeat their content; it identifies the dependencies
> between them, groups work that can execute in parallel, flags the critical
> integration points, and proposes the sequenced order in which Phase-2
> implementation should proceed once approved.

---

## 0. The four subsystems at a glance

| Phase | Subsystem | Primary organising axis | Canonical entrypoint | Governance guarantee |
|---|---|---|---|---|
| **2A** | **VIE** — Vendor-Independent Intelligence Engine | Task type (e.g. `strategy_generation`, `knowledge_extraction`) | `factory-vie:/generate` (HTTP) via `app/vie/client.py` | Application code never imports a provider SDK; single choke point for cost + circuit-breaker + policy |
| **2B** | **BI5 Market Data Engine** | Instrument × source-timeframe (M1 canonical) | `data_access.load_candles(symbol, timeframe)` | One canonical M1 store; derived TFs computed on read; coverage as a first-class report |
| **2C** | **UKIE** — Universal Knowledge Ingestion Engine | **Knowledge Domain** (`strategy` · `research` · `indicator` · `market` · `execution` · `internal_history`) | `KnowledgeRepository.insert_ingested(domain, item)` | All items `learning_only:True, eligible_for_deploy:False`; one audited promotion bridge |
| **2D** | **COE** — Compute Orchestration Engine | Workload class (10 canonical classes) + priority lane (P0/P1/P2) | `WorkloadQueue.submit(WorkloadRequest)` | Honest refusal admission; per-class reservations; per-worker crash budget; retry + dead-letter |

Each subsystem is designed to be **individually deployable behind
feature flags**; nothing here requires a big-bang cutover. But there
are **hard dependencies** between them that dictate the implementation
order.

---

## 1. The dependency graph

```
                       ┌──────────────────────────────┐
                       │  Phase 2D — COE (foundation) │
                       │  workload queue, lanes,      │
                       │  reservations, retries,      │
                       │  budget persistence          │
                       └───────────────┬──────────────┘
                                       │  provides:
                                       │    • WorkloadRequest envelope
                                       │    • per-class fault isolation
                                       │    • budget_tracker (persisted)
                                       │
                    ┌──────────────────┴───────────────────┐
                    │                                       │
                    ▼                                       ▼
     ┌───────────────────────────┐            ┌───────────────────────────┐
     │  Phase 2A — VIE           │            │  Phase 2B — BI5 Market    │
     │  provider adapters,       │            │  Data Engine              │
     │  task-based router,       │            │  canonical M1 store,      │
     │  budget-aware selection   │◄──────┐    │  coverage reports,        │
     └───────────────┬───────────┘       │    │  BI5 realism sweep        │
                     │                   │    └───────────────┬───────────┘
                     │  provides:        │                    │  provides:
                     │    • AI parsing   │  UKIE needs        │    • market_kb inputs
                     │    • embeddings   │  VIE for parser    │    • execution_kb inputs
                     │                   │                    │
                     ▼                   │                    ▼
     ┌───────────────────────────────────┴────────────────────────────┐
     │  Phase 2C — UKIE                                                │
     │  KnowledgeDomain registry, connector Protocol, pipeline stages, │
     │  trust ladder, license gate, per-domain sub-collections         │
     └────────────────────────────────────────────────────────────────┘
```

**Reading the graph:**
- **COE (2D) is foundational.** Every other subsystem submits work; they all benefit from lanes, reservations, retries, and persistent budget accounting. Building COE first ensures 2A/2B/2C ride on a stable dispatch surface from day one.
- **VIE (2A) blocks UKIE parser.** The knowledge parser is an LLM call — routing it through VIE gets us cost accounting, circuit breakers, and provider-independence for free. UKIE without VIE would be a regression toward direct SDK use.
- **BI5 (2B) feeds two domains in UKIE.** The `market` and `execution` domains draw on the canonical M1 store + BI5 realism outputs. UKIE's `market` and `execution` connectors are natural consumers of 2B artifacts.
- **UKIE (2C) is a consumer, not a blocker.** It uses everything above; nothing below it depends on it.

---

## 2. Parallelisation opportunities

Within the ordered sequence, several tracks can proceed in parallel
without stepping on each other.

### 2.1 Parallel Track A — COE α + VIE minor extensions
These two do not touch each other's code:

| Track A (COE α — §3.1) | Track A' (VIE hardening — §3.1) |
|---|---|
| Extend `WorkloadClass` to 10 classes | Add `budget_persist` mode (write to Mongo) |
| Land `WorkloadRequest` dataclass | Wire circuit-breaker state into `ai_workforce.router` |
| Add HARD_TIMEOUT_S to Task Protocol | Add `provider_state` to admission verdict |
| Wire `asyncio.wait_for` around `task.run()` | Add per-provider concurrency budget in `BudgetTracker` |
| Land `budget_state` Mongo mirror | Register missing task adapters (`knowledge_extraction`) |

Both can be built in parallel by different engineers; both merge as
"COE.α ready + VIE-α ready" before anything downstream starts.

### 2.2 Parallel Track B — COE β + BI5 read-side refactor
Once COE.α ships, the BI5 read-side refactor (canonical M1 + derived TFs)
can proceed in parallel with COE.β (lanes + reservations + I/O pool):

| Track B (COE β) | Track B' (BI5 read-side) |
|---|---|
| Enable `WorkloadQueue` in-memory | Introduce `data_access.load_candles()` that always reads M1 + resamples on demand |
| Switch dispatcher to consume from queue | Backfill any missing M1 hours before deprecating M15/H1/H4/D1 stores |
| Enable reservations | Emit `coverage_report` (gaps as first-class citizens) |
| Land `io_pool.py` + route MARKET_DATA/KNOWLEDGE/MONITORING through it | Wire `bi5_realism_sweep` to consume M1 canonical inputs |
| Prometheus exporter at `/api/coe/metrics` | Land `/api/data/coverage` endpoint |

Track B' is naturally an I/O-heavy workload, so it benefits **as
soon as** the I/O pool from Track B is available — that's the
integration point.

### 2.3 Parallel Track C — VIE task routing + UKIE domain registry
Both can proceed once COE.α + VIE-α are done:

| Track C (VIE) | Track C' (UKIE) |
|---|---|
| Formalise task map for the six UKIE domains (`parse_strategy_code`, `parse_paper_abstract`, `parse_indicator_definition`, `parse_market_note`, `parse_execution_rule`, `parse_internal_history`) | Land `KnowledgeDomain` enum + `KnowledgeDomainSpec` registry (P2C.0) |
| Ensure each task has explicit provider chain + cost estimate | Extract `KnowledgeConnector` Protocol declaring `supported_domains` (P2C.1) |
| Add `provider_hint` propagation from `WorkloadRequest` | Introduce `RawKnowledgeItem` with `domain` field (P2C.2) |

Track C' is the highest-priority UKIE work; Track C unblocks the
parsing stage of the ingestion pipeline.

### 2.4 Parallel Track D — UKIE connectors (self-parallel)
Once UKIE's pipeline is stable (through P2C.9), every new connector is
one file. **All UKIE connectors can be built in parallel by different
engineers.** Suggested initial fleet:

- `ArxivConnector` (research)
- `PdfConnector` (research + strategy + execution)
- `PropFirmConnector` (execution)
- `TradingViewConnector` (strategy + indicator)
- `InternalMongoConnector` (internal_history — read-only mirror of our own strategies + outcome events)

---

## 3. The recommended implementation sequence

The sequence below is the **critical-path** ordering. Parallel tracks
from §2 attach to their respective phase.

### Phase order

| # | Phase | Duration (focused-days, optimistic) | Blocks what |
|---|---|---|---|
| **1** | **COE α — foundations** (§3.1) | ~5 days | Everything downstream |
| **2** | **VIE hardening** (§3.2) — runs in parallel with COE α | ~3 days | UKIE parser |
| **3** | **COE β — lanes + reservations + I/O pool** (§3.3) | ~5 days | BI5 read-side; UKIE pipeline scheduling |
| **4** | **BI5 read-side refactor** (§3.4) — runs in parallel with COE β | ~4 days | UKIE `market` + `execution` domain connectors |
| **5** | **UKIE α — domain registry + connector Protocol** (§3.5) | ~2 days | All UKIE connector work |
| **6** | **UKIE β — pipeline stages + governance cutover** (§3.6) | ~5 days | UKIE per-domain writes; connector fleet |
| **7** | **COE γ — retries + dead-letter + provider-aware admission** (§3.7) | ~4 days | Reliability; not a blocker for happy-path Phase 2 |
| **8** | **UKIE γ — connector fleet** (§3.8) — 5 connectors in parallel | ~1 day per connector | Broader knowledge coverage |
| **9** | **Consolidated observability** (§3.9) — Prometheus + dashboards | ~2 days | Operator visibility across the four subsystems |

**Total critical-path effort** (single engineer, sequential): ~30 days.
**With parallel tracks fully staffed:** ~18 days.

### 3.1 COE α — foundations
See PHASE_2D §3 "Phase COE.α". Ships:
- extended `WorkloadClass` (10 classes)
- `WorkloadRequest` dataclass
- HARD_TIMEOUT_S on Task Protocol
- `asyncio.wait_for` around `task.run()`
- crash budget on CPU pool
- `budget_state` Mongo persistence

**No behaviour change with flags off.** Everything additive.

### 3.2 VIE hardening
- Wire `ai_workforce.circuit_breaker` state into `admission_gate` output (`provider_state` field).
- Persist `budget_tracker` state (Mongo mirror) — same collection introduced in COE α.
- Confirm all six UKIE-relevant tasks have provider chains + cost estimates in the task map.
- Add `provider_hint` propagation from `WorkloadRequest.provider_hint` through VIE `route()`.

### 3.3 COE β — lanes + reservations + I/O pool
See PHASE_2D §3 "Phase COE.β". Ships:
- `WorkloadQueue` in-memory with three lanes
- reservations per class
- `io_pool.py` for MARKET_DATA / KNOWLEDGE / MONITORING
- Prometheus exporter
- `X-COE-Pressure` header propagation

### 3.4 BI5 read-side refactor
See PHASE_2B §5-6. Ships:
- `data_access.load_candles(symbol, timeframe)` — always reads M1 + resamples
- `coverage_report` collection + `/api/data/coverage` endpoint
- Deprecation of parallel M15/H1/H4/D1 stores (kept read-only for one release)

Runs in parallel with COE β; benefits from I/O pool as soon as it lands.

### 3.5 UKIE α — domain registry + connector Protocol (P2C.0 + P2C.1 + P2C.2)
See PHASE_2C §7. Ships:
- `KnowledgeDomain` enum with six canonical domains
- `KnowledgeDomainSpec` registry
- `KnowledgeConnector` Protocol declaring `supported_domains`
- `RawKnowledgeItem` shape with `domain` field
- existing GitHub logic re-wrapped as `GithubConnector`

**Zero behaviour change** — same output as today, now going through
the new interface.

### 3.6 UKIE β — pipeline stages + governance cutover (P2C.3–P2C.9)
See PHASE_2C §7. Ships:
- `domain_router` stage
- `license_gate` (5-outcome classifier)
- `trust_scorer` (5-tier ladder)
- `dedup_check` (within-domain canonical_hash)
- `KnowledgeRepository.insert_ingested(domain, item)` — the one audited write
- `POST /api/knowledge/promote/{item_id}` — the audited bridge
- retro-scoring: backfill 55 existing rows with `domain=STRATEGY` + trust + license

**P2C.8 is the critical cutover** — flip injector from
mutation-pipeline to `KnowledgeRepository`. Requires dry-run
verification per PHASE_2C §7.

### 3.7 COE γ — retries + dead-letter + provider-aware admission
See PHASE_2D §3 "Phase COE.γ". Not on the critical path for Phase 2
functional completeness, but essential for production reliability.
Can be scheduled at any point after COE β.

### 3.8 UKIE γ — connector fleet (P2C.10)
Fully parallel — five connectors, five engineers, ~1 day each.
Order recommended by domain coverage priority:
1. `PdfConnector` (touches four domains — highest leverage per unit effort)
2. `ArxivConnector` (research)
3. `PropFirmConnector` (execution)
4. `TradingViewConnector` (strategy + indicator)
5. `InternalMongoConnector` (internal_history — enables self-improvement loop)

### 3.9 Consolidated observability
- Single `/api/coe/state` + `/api/vie/state` + `/api/data/coverage` + `/api/knowledge/state` dashboard.
- Prometheus scrape config aggregating all four subsystems.
- Grafana dashboard: capacity band, queue depths per class, budget headroom, coverage gaps, domain distribution, trust distribution.

---

## 4. Integration hot-spots (where phases meet)

These are the places where two subsystems must agree on a contract.
Each is a small, well-defined API — flag any drift here early.

### 4.1 VIE ↔ COE — task-workload alignment
Every AI-bearing task in the orchestrator registry should map to a
VIE `task` in the router. Today the workforce router picks a provider;
COE α adds a `provider_hint` on `WorkloadRequest`. VIE MUST honour
the hint when present, otherwise fall through to router policy.

Contract: `WorkloadRequest.provider_hint: Optional[str]` → passed into
`VIEClient.generate(..., provider_hint=...)` → VIE `route()` consults
the hint before applying the score-based chain.

### 4.2 VIE ↔ COE — budget accounting
`BudgetTracker` in COE is the single source of truth for provider
spend. VIE MUST call `budget_tracker.register_call(provider)` on
launch and `budget_tracker.record(provider, cost_usd, tokens)` on
completion. No double-counting — COE α adds Mongo mirror; VIE reads
via the same tracker.

Contract: **VIE does not maintain its own budget state.** All
accounting goes through `orchestrator.budget_tracker` (or its Mongo
mirror). VIE-α task: ensure every `provider.generate()` completion
calls `record()` unconditionally.

### 4.3 BI5 ↔ COE — data-load as a workload class
Every BI5 top-up (`market_data_topup` task) runs under
`WorkloadClass.MARKET_DATA` (new class in §1.2 of PHASE_2D). BI5
realism sweep runs as `WorkloadClass.META_LEARNING`.

Contract: BI5 read-side (canonical M1 store) exposes a synchronous
`data_access.load_candles()` for interactive callers **plus** an async
version that runs under COE workload class MARKET_DATA for scheduled
bulk loads.

### 4.4 BI5 ↔ UKIE — market + execution domain feed
BI5's `coverage_report` + `bi5_realism` outputs become inputs to the
UKIE `market` and `execution` domains via `InternalMongoConnector`.
This is a **read-only** connector — it mirrors internal Mongo state
into the KB for AI reasoning; it does not create new rows.

Contract: `InternalMongoConnector.supported_domains =
{KnowledgeDomain.MARKET, KnowledgeDomain.EXECUTION,
KnowledgeDomain.INTERNAL_HISTORY}`. Read frequency governed by the
same COE MARKET_DATA / KNOWLEDGE workload gates.

### 4.5 UKIE ↔ VIE — parser task
UKIE's parser is a VIE call — one task per domain. Six new tasks
registered in `vie/router.py`:

| Domain | VIE task | Suggested provider chain |
|---|---|---|
| strategy | `parse_strategy_code` | `openai_gpt5, claude_sonnet, gemini_flash` |
| research | `parse_paper_abstract` | `claude_sonnet, openai_gpt5, gemini_flash` |
| indicator | `parse_indicator_definition` | `openai_gpt5_mini, gemini_flash` |
| market | `parse_market_note` | `gemini_flash, openai_gpt5_mini` |
| execution | `parse_execution_rule` | `claude_sonnet, openai_gpt5` |
| internal_history | `parse_internal_history` | (bypass — read Mongo directly, no LLM) |

### 4.6 UKIE ↔ COE — connector rate limits as workload gates
Each `KnowledgeConnector.rate_limit()` declares its own per-second /
per-minute cap. The COE MARKET_DATA / KNOWLEDGE workload gates
enforce them at the admission layer, not inside the connector.

Contract: Connector declares intent; COE enforces it. This means a
connector cannot exceed its rate limit even under manual
`POST /api/coe/jobs` submission — the admission gate refuses excess.

---

## 5. Cross-cutting invariants (guardrails for every phase)

These invariants apply across ALL four subsystems. Any implementation
that violates one should be rejected in review:

1. **Additive & feature-gated.** No new subsystem replaces an old one at boot; every new capability is a flag flip away from being dormant.
2. **Rollback in 60 seconds.** Turning any flag OFF returns the system to its pre-flag byte-identical behaviour.
3. **`learning_only:True` is a hard rail.** No UKIE-ingested item, no KB-derived artefact, no promotion-in-progress item ever leaves the `strategy_knowledge_base` DB without an explicit, audited, admin-gated action.
4. **`eligible_for_deploy:True` requires human-in-the-loop.** No automation, no cron, no orchestrator tick, can flip this bit on a strategy row. Only the promotion bridge — with `admin` role + audit row — can.
5. **`StrategyRepository` is the sole read of production strategies.** No engine reads `strategies` collection directly; the Phase-1.6 wrap remains in force.
6. **`VIEClient` is the sole call of an LLM.** No engine imports `openai`, `anthropic`, `google-generativeai`, etc. All AI goes through VIE. This means:
   - No SDK imports in `/app/backend/*` outside `app/vie/`
   - Provider adapters live in `/app/vie/providers/` — nowhere else
7. **`data_access.load_candles()` is the sole read of market data.** Callers do not read `market_data` collection directly.
8. **`BudgetTracker` is the sole owner of USD accounting.** No engine records cost outside `orchestrator/budget_tracker.py`.
9. **`WorkloadQueue.submit()` is the sole submitter of async work** (once COE β is on). Direct `orchestrator.dispatch_task()` calls survive only as a fallback path when `COE_LANES_ENABLED=false`.
10. **Every write to any of the eight strategic collections** (`strategies, outcome_events, mutation_runs, factory_eval_reports, ingested_items, coverage_report, budget_state, workload_queue`) is idempotent and carries a provenance stamp.
11. **Distribution-ready from day one** (operator directive, 2026-02-19). No layer of Phase 2 may hard-code single-node assumptions. Every counter, every queue, every budget MUST be behind an interface whose local-memory implementation is Phase-2α/β and whose distributed implementation is Phase-2γ+ — the switch is a driver swap, not a rewrite. Concretely: `WorkloadQueue`, `BudgetTracker`, `queue_pressure.snapshot()`, `host_capability` all use protocol-based backends with `local` / `distributed` implementations under the same interface. The current VPS is the **first compute node**, not the permanent architecture.
12. **Measurable health everywhere** (operator directive, 2026-02-19). Every major subsystem MUST expose the same seven-field standardised health surface via `GET /api/<subsystem>/health`. Details in §5.1.

### 5.1 The Universal Health Contract (new)

Every Phase-2 subsystem (VIE, BI5, UKIE, COE, plus the existing
Meta-Learning, Execution Intelligence, Market Intelligence, Portfolio,
Factory-Eval subsystems) MUST expose a health endpoint returning
**exactly this shape**:

```json
{
  "subsystem":       "coe" | "vie" | "bi5" | "ukie" | "meta_learning" | "execution" | ...,
  "ts":              "<UTC iso>",

  "health_score":    0..100,   // aggregate health — see §5.1.1
  "readiness_score": 0..100,   // are we prepared to accept new work?
  "confidence_score":0..100,   // how much do we trust the recent output?

  "resource_usage": {
    "cpu_percent":       0..100,
    "mem_mb":            <int>,
    "in_flight":         <int>,
    "queue_depth":       <int>,
    "budget_headroom":   0..1     // USD remaining / daily cap
  },

  "last_successful_run": {
    "at":       "<UTC iso>" | null,
    "duration_ms": <int> | null,
    "ref":      "<id / correlation>" | null
  },

  "failure_count": {
    "last_hour":  <int>,
    "last_day":   <int>,
    "since_boot": <int>
  },

  "recovery_status": {
    "state":        "ok" | "degraded" | "critical" | "recovering",
    "reason":       "<short human-readable string>",
    "action_required": "none"
                    | "operator_review"
                    | "restart_component"
                    | "reset_budget"
                    | "clear_dead_letter"
                    | "wait_for_backoff"
                    | "manual_intervention",
    "last_recovery_at": "<UTC iso>" | null
  }
}
```

#### 5.1.1 Score computation contract

- **`health_score`** — a WEIGHTED combination of failure_count (last hour), circuit-breaker state (if any), queue overflow events (if any), and dependency health.
  Deterministic pure function; each subsystem publishes its formula.
- **`readiness_score`** — how much *headroom* is available RIGHT NOW.
  Function of `resource_usage.budget_headroom`, `queue_depth / class_capacity`, and provider circuit states (for AI-bearing subsystems).
- **`confidence_score`** — how much do we trust the OUTPUT?
  For VIE: recent success rate + provider agreement rate.
  For BI5: coverage completeness + cert freshness.
  For UKIE: trust-tier distribution + connector-health.
  For COE: reservation-satisfaction rate.
  For Meta-Learning: recent verdict stability.

Every score is a **pure function over the last-N snapshot window**.
No score depends on external state.

#### 5.1.2 The three questions the platform must always answer

The health contract exists so the platform can always answer:
1. **What is healthy?** — any subsystem with `recovery_status.state == "ok"` and `health_score ≥ 80`.
2. **What is degraded, and why?** — any subsystem with `state != "ok"` reports its `reason` and `failure_count`.
3. **What action is required?** — every non-ok state carries an `action_required` from the closed enum, so operators can respond without reading logs first.

#### 5.1.3 Aggregation

- `GET /api/health/system` — cross-subsystem rollup. Returns an array of subsystem health blocks + a computed **platform_health_score** (weighted average, weights operator-tunable via env `PLATFORM_HEALTH_WEIGHT_<SUBSYSTEM>`).
- Prometheus exporter (COE β) emits every field as a labelled metric.
- Alertmanager rules can then fire on `platform_health_score < 60` or any `action_required != "none"`.

#### 5.1.4 Implementation discipline

- The contract lives in `engines/health/contract.py` as a `@dataclass HealthSnapshot` — every subsystem imports and populates the SAME dataclass. No bespoke shapes.
- Subsystems produce their `HealthSnapshot` via a pure `compute_health()` function; the routing endpoint is a thin wrapper.
- The dataclass ships in COE α (foundational — everyone depends on it). Existing subsystems (Meta-Learning, MI, Execution) retrofit their diagnostic endpoints to also emit `HealthSnapshot` in Stage 4.

---

## 6. What we deliberately postpone

Not everything belongs in Phase 2. The following are called out here
so nobody adds them mid-sprint:

- **Multi-node / distributed execution** (COE γ+). Single-node is sufficient for the current VPS; the contracts stay distribution-ready.
- **Live-trading execution** as an active workload. `EXECUTION` class exists in COE α, but no live orders flow until Phase 3.
- **Human-in-the-loop review UI** for KB promotions. Backend API exists in UKIE β; frontend is a Phase 3 item.
- **Custom embedding models** for UKIE domains. Phase 2 uses provider-embedded defaults (OpenAI + Gemini via VIE); custom models are a Phase 3 optimisation.
- **Per-tenant fairness in COE.** Placeholder field on `WorkloadRequest.tenant_id` reserved; enforcement is Phase 3+.

---

## 7. Approval checklist

Before Phase 2 implementation begins, the operator should sign off on:

- [ ] The **six Knowledge Domains** in PHASE_2C §1.0 are correct and complete.
- [ ] The **ten Workload Classes** in PHASE_2D §1.2 cover the full factory workload; reservation floors are acceptable.
- [ ] The **VIE task map** in §4.5 above lists the correct provider chains per task.
- [ ] The **critical cutover** (P2C.8, UKIE governance) is scheduled during a low-traffic window.
- [ ] The **BI5 read-side refactor** (§3.4) can safely deprecate the parallel timeframe stores without breaking existing consumers.
- [ ] **Rollback flags** (`COE_ENABLED`, `COE_LANES_ENABLED`, `ENABLE_DOMAIN_ROUTING`, `USE_PROCESS_POOL`, etc.) are all documented and safe to toggle.
- [ ] The **integration hot-spots** in §4 have owners assigned.

---

## 8. Recommended next call

Approve or amend the sequence in §3. Then execute in order:

1. **COE α** (5 days) — everything downstream benefits.
2. **VIE hardening** in parallel (3 days).
3. **COE β** (5 days) + **BI5 read-side** in parallel (4 days).
4. **UKIE α** (2 days) → **UKIE β** (5 days) — the governance cutover.
5. **COE γ** (4 days) + **UKIE γ** (5 connectors × 1 day, all parallel).
6. **Consolidated observability** (2 days).

**Do not begin implementation until the sequence is approved.** The
four architecture reviews (2A, 2B, 2C, 2D) are the source of truth
for each subsystem's internals; this document is the source of truth
for how they compose.

---

*Reviewed against:*
`/app/memory/PHASE_2A_AI_ARCHITECTURE_REVIEW.md` (634 lines),
`/app/memory/PHASE_2B_MARKET_DATA_REVIEW.md` (525 lines),
`/app/memory/PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md` (updated to Knowledge-Domain framing),
`/app/memory/PHASE_2D_COMPUTE_ORCHESTRATION_REVIEW.md` (new).

*Status:* **Architecture review only. No code changes proposed. Approval required before Phase 2 implementation begins.**
