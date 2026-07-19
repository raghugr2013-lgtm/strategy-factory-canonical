# PHASE 2 — IMPLEMENTATION MASTER PLAN
### The authoritative guide for Phase-2 implementation of the Strategy Factory

> **Status:** authoritative — ratified by operator on 2026-02-19.
> This document consolidates the four Phase-2 architecture reviews
> (2A, 2B, 2C, 2D) and the cross-cutting consolidated review into a
> single implementation reference. It defines the implementation
> sequence, dependencies, validation gates, rollback strategy,
> feature flags, success criteria, milestones, and per-stage
> checklists. **No implementation begins until this document is
> fully reviewed and approved.**

---

## 0. Table of contents

1. [Purpose & scope](#1-purpose--scope)
2. [Source documents (authoritative references)](#2-source-documents-authoritative-references)
3. [Universal design invariants](#3-universal-design-invariants)
4. [The Universal Health Contract](#4-the-universal-health-contract)
5. [Feature flag registry](#5-feature-flag-registry)
6. [Implementation stages & validation gates](#6-implementation-stages--validation-gates)
7. [Rollback strategy](#7-rollback-strategy)
8. [Success criteria per stage](#8-success-criteria-per-stage)
9. [Estimated milestones](#9-estimated-milestones)
10. [Per-stage implementation checklists](#10-per-stage-implementation-checklists)
11. [Risk register](#11-risk-register)
12. [Sign-off](#12-sign-off)

---

## 1. Purpose & scope

**Purpose.** Phase 2 evolves the Strategy Factory from a single-VPS
production deployment (Phase 1 complete) into an intelligent,
multi-source, capacity-aware, distribution-ready platform.

**Scope.** Four subsystems:

| Subsystem | Deliverable |
|---|---|
| **VIE** — Vendor-Independent Intelligence Engine | Provider routing hardened; budget accounting persisted; task map extended for UKIE parser tasks |
| **BI5** — Market Data Engine | Canonical M1 store + on-read derived timeframes; coverage-report first-class; realism sweep on canonical inputs |
| **UKIE** — Universal Knowledge Ingestion Engine | Six Knowledge Domains, connector fleet, license gate, trust ladder, governance cutover to `KnowledgeRepository`, promotion bridge |
| **COE** — Compute Orchestration Engine | 10-class workload taxonomy, priority lanes (P0/P1/P2), reservations, `WorkloadRequest` envelope, retry + dead-letter, provider-aware admission, distribution-ready contracts |

**Not in scope.**
- Live-trading order flow (Phase 3).
- Multi-node cluster deployment (COE γ contracts ready; enable in Phase 3).
- Custom embedding model training (Phase 3+).
- Human-in-the-loop KB promotion UI (Phase 3).
- Per-tenant fairness enforcement (placeholder only).

---

## 2. Source documents (authoritative references)

Every implementation decision defers to these documents. If this
master plan and a source document disagree on a technical detail, the
source document wins and this plan must be corrected.

| # | Document | Lines | Owns |
|---|---|---|---|
| 1 | `PHASE_2A_AI_ARCHITECTURE_REVIEW.md` | 634 | VIE internals |
| 2 | `PHASE_2B_MARKET_DATA_REVIEW.md` | 525 | BI5 internals |
| 3 | `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md` | 582 | UKIE internals, Knowledge-Domain model |
| 4 | `PHASE_2D_COMPUTE_ORCHESTRATION_REVIEW.md` | 780 | COE internals, workload taxonomy |
| 5 | `PHASE_2_CONSOLIDATED_REVIEW.md` | 507 | Cross-phase dependencies, integration hot-spots, invariants incl. Universal Health Contract |

**This document (`PHASE_2_IMPLEMENTATION_MASTER_PLAN.md`) is
implementation-only.** It does not restate design; it operationalises
it.

---

## 3. Universal design invariants

These invariants govern **every** line of Phase-2 code. Any code
review that catches a violation MUST reject the change until fixed.

1. **Additive & feature-gated.** Every new capability behind a flag; default OFF = byte-identical to pre-change behaviour.
2. **Rollback in 60 seconds.** Flag flip returns to pre-flag semantics without redeploy.
3. **`learning_only:True` is a hard rail.** No KB item may bypass this without an audited promotion.
4. **`eligible_for_deploy:True` requires human-in-the-loop.** No automation flips this.
5. **`StrategyRepository` is the sole read of production strategies.**
6. **`VIEClient` is the sole call of an LLM.** No SDK imports outside `/app/vie/`.
7. **`data_access.load_candles()` is the sole read of market data.**
8. **`BudgetTracker` is the sole owner of USD accounting.**
9. **`WorkloadQueue.submit()` is the sole submitter of async work** (once COE β on).
10. **All strategic-collection writes are idempotent and provenance-stamped.**
11. **Distribution-ready from day one.** No single-node assumptions in interfaces. Local + distributed drivers under the same Protocol. (See PHASE_2D §1.1.7)
12. **Measurable health everywhere.** Every subsystem emits `HealthSnapshot` (§4).
13. **Pure functions over I/O for sizing / scoring / admission.**
14. **Honest refusal over silent buffering.** `admit | defer | refuse` — never a blocking queue.
15. **Operator authority.** Every automated decision has an env override.

---

## 4. The Universal Health Contract

Every subsystem — VIE, BI5, UKIE, COE, plus the existing Meta-Learning,
Execution Intelligence, Market Intelligence, Portfolio, Factory-Eval —
emits the same seven-field `HealthSnapshot`. Full contract in
`PHASE_2_CONSOLIDATED_REVIEW.md §5.1`. Summary:

```
HealthSnapshot {
  subsystem, ts,
  health_score      (0..100),
  readiness_score   (0..100),
  confidence_score  (0..100),
  resource_usage    { cpu%, mem_mb, in_flight, queue_depth, budget_headroom },
  last_successful_run { at, duration_ms, ref },
  failure_count       { last_hour, last_day, since_boot },
  recovery_status     { state, reason, action_required, last_recovery_at }
}
```

**Where the contract lives:** `engines/health/contract.py` — ships in
COE α (Stage 1). Every downstream subsystem imports this dataclass.

**Aggregation endpoint:** `GET /api/health/system` — cross-subsystem
rollup + computed `platform_health_score`.

**Retrofit obligation:** existing subsystems (Meta-Learning, MI,
Execution) retrofit their diagnostic endpoints to emit
`HealthSnapshot` in **Stage 4** (final observability pass). Phase-1
diagnostic endpoints remain in service for backwards compatibility.

**The three questions the platform must always answer:**
1. What is healthy? → `state=="ok"` AND `health_score >= 80`.
2. What is degraded, and why? → `state != "ok"`, `reason` populated.
3. What action is required? → `action_required` from closed enum.

---

## 5. Feature flag registry

Every flag introduced by Phase 2. Defaults are OFF; flipping ON is
the enablement action; flipping OFF is the rollback.

### 5.1 COE flags

| Flag | Default | Stage | Effect when ON |
|---|---|---|---|
| `COE_ENABLED` | `false` | 1 | Master switch — enables COE α subsystems |
| `COE_HEALTH_CONTRACT_ENABLED` | `false` | 1 | Serve `/api/health/system` aggregator |
| `COE_HARD_TIMEOUT_ENABLED` | `false` | 1 | Wrap `task.run()` in `asyncio.wait_for` |
| `COE_CRASH_BUDGET_ENABLED` | `false` | 1 | CPU pool auto-recycle on crash threshold |
| `BUDGET_PERSIST` | `false` | 1 | Mirror `BudgetTracker` state to Mongo |
| `COE_LANES_ENABLED` | `false` | 2 | Enable P0/P1/P2 lanes |
| `COE_RESERVATIONS_ENABLED` | `false` | 2 | Enforce per-class reservation floors |
| `USE_IO_POOL` | `false` | 2 | Enable dedicated I/O thread pool |
| `USE_PROCESS_POOL_DEFAULT_ON` | `false` | 2 | Flip CPU pool ON by default (was already flag-gated) |
| `COE_METRICS_ENABLED` | `false` | 2 | Expose `/api/coe/metrics` for Prometheus |
| `COE_RETRY_ENABLED` | `false` | 4 | Wire retry policy at the dispatcher |
| `COE_DEAD_LETTER_ENABLED` | `false` | 4 | Enable dead-letter collection writes |
| `COE_PROVIDER_AWARE_ADMISSION` | `false` | 4 | Consult provider circuit before admitting AGENT |
| `COE_AGE_BOOST_ENABLED` | `false` | 4 | Age-boost score adjustment (starvation prevention) |
| `COE_ELASTIC_BAND_ENABLED` | `false` | 4 | BACKTEST ↔ MUTATION slot rebalancing |
| `OTEL_ENABLED` | `false` | 4 | Turn on OpenTelemetry span export |
| `ORCH_RESERVATION_<CLASS>` | (per-class default) | 2 | Operator override for reservation floor |
| `ORCH_HARD_TIMEOUT_<CLASS>` | (per-class default) | 1 | Operator override for per-class timeout |
| `ORCH_RETRY_<CLASS>_ATTEMPTS` | (per-class default) | 4 | Retry attempts |
| `ORCH_RETRY_<CLASS>_BACKOFF_MS` | `500,2000,10000` | 4 | Backoff schedule |

### 5.2 VIE flags

| Flag | Default | Stage | Effect when ON |
|---|---|---|---|
| `VIE_BUDGET_PERSIST` | `false` | 1 | Route budget writes through Mongo (shared with COE `BUDGET_PERSIST`) |
| `VIE_TASK_MAP_EXTENDED` | `false` | 1 | Register the 6 UKIE-parser tasks |
| `VIE_PROVIDER_HINT_RESPECT` | `false` | 1 | Honour `WorkloadRequest.provider_hint` |
| `VIE_CIRCUIT_STATE_EXPORT` | `false` | 4 | Export provider circuit state into admission verdict |

### 5.3 BI5 flags

| Flag | Default | Stage | Effect when ON |
|---|---|---|---|
| `BI5_CANONICAL_M1_READ_MODE` | `false` | 2 | `data_access.load_candles()` reads M1 + resamples on demand |
| `BI5_COVERAGE_REPORT_ENABLED` | `false` | 2 | Emit `coverage_report` collection + expose `/api/data/coverage` |
| `BI5_LEGACY_STORE_READ_ONLY` | `false` | 2 | Deprecate parallel M15/H1/H4/D1 stores to read-only |

### 5.4 UKIE flags

| Flag | Default | Stage | Effect when ON |
|---|---|---|---|
| `UKIE_DOMAIN_REGISTRY_ENABLED` | `false` | 3 | Land `KnowledgeDomain` enum + `KnowledgeDomainSpec` |
| `ENABLE_DOMAIN_ROUTING` | `false` | 3 | Route each `RawKnowledgeItem` to its domain lane |
| `ENABLE_LICENSE_GATE` | `false` | 3 | Run license classifier |
| `ENABLE_TRUST_SCORER` | `false` | 3 | Compute per-item trust tier |
| `ENABLE_DEDUP_CHECK` | `false` | 3 | Enforce within-domain canonical_hash uniqueness |
| `UKIE_GOVERNANCE_CUTOVER` | `false` | 3 | Redirect injector → `KnowledgeRepository.insert_ingested()` — **the critical cutover** |
| `UKIE_PROMOTE_BRIDGE_ENABLED` | `false` | 3 | Enable `POST /api/knowledge/promote/{item_id}` |
| `UKIE_CONNECTOR_<NAME>_ENABLED` | `false` | 4 | Per-connector enablement (arxiv, pdf, propfirm, tradingview, internal_mongo) |

### 5.5 Cross-cutting

| Flag | Default | Stage | Effect when ON |
|---|---|---|---|
| `PLATFORM_HEALTH_WEIGHT_<SUBSYSTEM>` | 1.0 | 4 | Operator tuning of platform-health aggregate |
| `PLATFORM_HEALTH_ALERT_THRESHOLD` | `60` | 4 | Alert when `platform_health_score` drops below |

---

## 6. Implementation stages & validation gates

Implementation proceeds in **four staged waves**. Every stage ends
with a **validation gate**; the next stage does not begin until the
gate passes.

```
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 1 — COE α + VIE hardening                                   │
│  ├── COE α: foundations (§3.1 PHASE_2D)                            │
│  └── VIE hardening: budget persist, task map, provider hint        │
│  ──────────────► VALIDATION GATE 1 ─────────────►                  │
│                                                                    │
│  STAGE 2 — COE β + BI5 refactor                                    │
│  ├── COE β: lanes, reservations, I/O pool                          │
│  └── BI5: canonical M1 read-side, coverage report                  │
│  ──────────────► VALIDATION GATE 2 ─────────────►                  │
│                                                                    │
│  STAGE 3 — UKIE α + UKIE β                                         │
│  ├── UKIE α: domain registry, connector Protocol                   │
│  └── UKIE β: pipeline stages, governance cutover                   │
│  ──────────────► VALIDATION GATE 3 ─────────────►                  │
│                                                                    │
│  STAGE 4 — COE γ + UKIE γ + Observability                          │
│  ├── COE γ: retries, dead-letter, provider-aware admission         │
│  ├── UKIE γ: connector fleet (5 connectors in parallel)            │
│  ├── Observability: HealthSnapshot retrofit + platform dashboard   │
│  └── FINAL VALIDATION GATE                                         │
└────────────────────────────────────────────────────────────────────┘
```

### 6.1 Stage 1 — COE α + VIE hardening

**Goal:** Land foundations. Every downstream stage depends on this.

**Deliverables (see §10.1 for granular checklist):**
- `engines/health/contract.py` — `HealthSnapshot` dataclass
- Extended `WorkloadClass` enum (10 classes)
- `WorkloadRequest` dataclass
- `HARD_TIMEOUT_S` on Task Protocol; wired via `asyncio.wait_for`
- CPU pool crash budget + auto-recycle
- `budget_state` Mongo mirror (both COE + VIE writes)
- VIE task map extended with 6 UKIE-parser tasks
- `provider_hint` propagation VIE ← COE

**Validation Gate 1 (all must pass):**

- [ ] All existing tests pass unchanged (`pytest backend/tests/`)
- [ ] `pytest backend/legacy/tests/` passes (~100 tests)
- [ ] With flags OFF: behaviour byte-identical to pre-Stage-1 — confirmed by smoke suite of Phase-1 endpoints
- [ ] With `COE_HEALTH_CONTRACT_ENABLED=true`: `GET /api/health/system` returns valid `HealthSnapshot` for COE + VIE
- [ ] With `COE_HARD_TIMEOUT_ENABLED=true`: a task exceeding its `HARD_TIMEOUT_S` is killed and marked failed
- [ ] With `BUDGET_PERSIST=true`: backend restart preserves daily USD spend (verified by simulated restart)
- [ ] With `VIE_TASK_MAP_EXTENDED=true`: all 6 UKIE-parser tasks route to at least one provider
- [ ] With `VIE_PROVIDER_HINT_RESPECT=true`: submitting a `WorkloadRequest.provider_hint="claude"` sends the LLM call to Anthropic
- [ ] No behaviour change to production strategies read path (Phase-1.6 `StrategyRepository` untouched)
- [ ] CPU pool crash budget test: kill a worker mid-flight; pool auto-recycles; new submissions succeed

### 6.2 Stage 2 — COE β + BI5 refactor

**Goal:** Priority lanes + reservations + I/O isolation; BI5 read-side
refactored to canonical M1.

**Deliverables:**
- `engines/coe/workload_queue.py` — in-memory `LocalQueueDriver`
- P0/P1/P2 lane semantics
- Reservation enforcement per class
- `engines/coe/io_pool.py` — dedicated thread pool
- Prometheus exporter at `/api/coe/metrics`
- `X-COE-Pressure` response header propagation
- BI5: `data_access.load_candles(symbol, timeframe)` — always reads M1, resamples on demand
- BI5: `coverage_report` collection + `/api/data/coverage` endpoint
- BI5: parallel timeframe stores flipped to read-only

**Validation Gate 2 (all must pass):**

- [ ] All Stage-1 validation gate items still pass
- [ ] With `COE_LANES_ENABLED=true`: submitting a P0 job while P2 queue is full → P0 dispatches first (verified by latency histogram)
- [ ] With `COE_RESERVATIONS_ENABLED=true`: filling BACKTEST class to capacity does NOT starve EXECUTION reservations (verified by injected load test)
- [ ] With `USE_IO_POOL=true`: a burst of 20 concurrent MARKET_DATA jobs does NOT block a concurrent BACKTEST from proceeding
- [ ] `/api/coe/metrics` returns valid Prometheus text; scrape config confirms all counters emit
- [ ] With `BI5_CANONICAL_M1_READ_MODE=true`: reading M15/H1/H4/D1 returns identical candles as the parallel stores (bit-for-bit, ± floating-point tolerance) — verified across ≥ 3 symbols × ≥ 4 timeframes × ≥ 100 candles
- [ ] `GET /api/data/coverage` returns coverage matrix for all symbols
- [ ] With `BI5_LEGACY_STORE_READ_ONLY=true`: writing to deprecated M15/H1/H4/D1 collections raises; reads still succeed
- [ ] Response header `X-COE-Pressure` appears on every `/api/*` call with a valid band (`idle`/`normal`/`high`/`critical`)
- [ ] Distribution-ready check: `WorkloadQueue` interface has both `LocalQueueDriver` and stub `DistributedQueueDriver` classes; the stub raises `NotImplementedError` for γ methods but the interface accepts both

### 6.3 Stage 3 — UKIE α + UKIE β

**Goal:** Six Knowledge Domains live; connector fleet ready to onboard.

**Deliverables:**
- `KnowledgeDomain` enum (6 canonical domains)
- `KnowledgeDomainSpec` registry
- `KnowledgeConnector` Protocol declaring `supported_domains`
- `RawKnowledgeItem` with `domain` field
- Existing GitHub logic re-wrapped as `GithubConnector`
- `domain_router` pipeline stage
- `license_gate.py`
- `trust_scorer.py` (5-tier ladder)
- `dedup_check.py` (within-domain)
- `KnowledgeRepository.insert_ingested(domain, item)` — the audited write
- `POST /api/knowledge/promote/{item_id}` — the audited bridge
- Retro-scoring: 55 existing rows backfilled with `domain=STRATEGY` + trust + license

**Validation Gate 3 (the most sensitive gate — includes governance cutover):**

- [ ] All Stage-2 validation gate items still pass
- [ ] `UKIE_DOMAIN_REGISTRY_ENABLED=true`: `GET /api/knowledge/domains` returns 6 domains with correct specs
- [ ] `ENABLE_DOMAIN_ROUTING=true`: submitting a `RawKnowledgeItem` with `domain=research` writes to `strategy_knowledge_base.research` (not `.strategies`)
- [ ] `ENABLE_LICENSE_GATE=true`: an item with no LICENSE file is routed to trust tier T1 (quarantine)
- [ ] `ENABLE_TRUST_SCORER=true`: every new ingested row has `trust_tier` populated
- [ ] `ENABLE_DEDUP_CHECK=true`: re-ingesting the same content_hash within the same domain is refused; identical hash in a different domain is allowed
- [ ] **Dry-run of governance cutover** (P2C.8) reproduces the last 10 ingestion runs producing the same normalised items minus the `eligible_for_deploy:False` change — MUST PASS BEFORE FLIPPING `UKIE_GOVERNANCE_CUTOVER=true`
- [ ] `UKIE_GOVERNANCE_CUTOVER=true`: new ingestions land in `KnowledgeRepository`; NO new rows appear in production `strategies` from ingestion
- [ ] `UKIE_PROMOTE_BRIDGE_ENABLED=true` + admin token: `POST /api/knowledge/promote/{item_id}` creates a `strategies` draft with `eligible_for_deploy:False` and `origin_kb_id`
- [ ] Non-admin user is refused by `POST /api/knowledge/promote/*` (auth 403)
- [ ] Retro-scoring: all 55 existing ingested_strategies rows have `domain=STRATEGY`, `trust_tier`, `license` — verified by direct Mongo count
- [ ] `HealthSnapshot` for UKIE returns valid data (health/readiness/confidence scores populated)

### 6.4 Stage 4 — COE γ + UKIE γ + Observability

**Goal:** Reliability + connector fleet + measurable health across
every legacy subsystem.

**Deliverables:**
- COE γ: retry executor, dead-letter collection, `/api/coe/dead-letter/*` endpoints
- COE γ: provider-aware admission (consult circuit-breaker)
- COE γ: age-boost score adjustment
- COE γ: elastic band redistribution
- UKIE γ: 5 connectors (`ArxivConnector`, `PdfConnector`, `PropFirmConnector`, `TradingViewConnector`, `InternalMongoConnector`)
- Observability: `HealthSnapshot` retrofit for Meta-Learning, MI, Execution, Portfolio, Factory-Eval
- Observability: `GET /api/health/system` aggregator returns ALL subsystems
- Observability: consolidated Grafana dashboard (capacity band, queue depths, budget headroom, coverage gaps, domain distribution, trust distribution, per-subsystem health)
- OpenTelemetry span export (optional)

**Final Validation Gate (production-readiness):**

- [ ] All Stage-3 validation gate items still pass
- [ ] With `COE_RETRY_ENABLED=true`: a transient network failure in a MARKET_DATA task triggers exponential backoff retry; succeeds on retry #2
- [ ] With `COE_DEAD_LETTER_ENABLED=true`: a persistent failure lands in `workload_dead_letter` after N attempts (N per class); `GET /api/coe/dead-letter` lists it; `POST /api/coe/dead-letter/{id}/requeue` succeeds
- [ ] With `COE_PROVIDER_AWARE_ADMISSION=true`: opening the Anthropic circuit → AGENT tasks needing Claude defer with `reason=provider_unavailable`; VIE reroutes to OpenAI; queue drains
- [ ] All 5 UKIE connectors dry-run successfully on ≥ 3 references each; each writes to correct domain(s)
- [ ] Every subsystem in the platform emits valid `HealthSnapshot` via `GET /api/<subsystem>/health` (COE, VIE, BI5, UKIE, Meta-Learning, MI, Execution, Portfolio, Factory-Eval)
- [ ] `GET /api/health/system` returns array of ≥ 9 subsystem blocks + `platform_health_score`
- [ ] Alertmanager configured on `platform_health_score < PLATFORM_HEALTH_ALERT_THRESHOLD` — verified by injected degradation
- [ ] Grafana dashboard renders all key metrics for ≥ 24-hour window
- [ ] Distribution-ready check: `WorkloadQueue.LocalDriver` and `WorkloadQueue.DistributedDriver` (stub) both satisfy the Protocol; swapping via env `COE_QUEUE_DRIVER=distributed` cleanly raises `NotImplementedError` on submit (proves the switch point works)
- [ ] Load test: 100 concurrent P0 requests under `pressure_band=high` see p95 admission latency < 200 ms

---

## 7. Rollback strategy

Rollback is a **flag flip**, not a redeploy. The discipline of Phase 2
is that every capability is dormant behind a flag; enablement is
opt-in. Rollback returns to the pre-flag world.

### 7.1 Per-stage rollback

| Stage | Rollback action | Recovery time |
|---|---|---|
| 1 | Set `COE_ENABLED=false`, `BUDGET_PERSIST=false`, `VIE_TASK_MAP_EXTENDED=false`, restart backend | ~30s (supervisor restart) |
| 2 | Set `COE_LANES_ENABLED=false`, `USE_IO_POOL=false`, `BI5_CANONICAL_M1_READ_MODE=false`, `BI5_LEGACY_STORE_READ_ONLY=false` | ~30s |
| 3 | Set `UKIE_GOVERNANCE_CUTOVER=false` — new ingestions revert to old mutation-pipeline path. **Data written to `KnowledgeRepository` before rollback is preserved; production `strategies` is untouched by definition** | ~30s |
| 4 | Set `COE_RETRY_ENABLED=false`, `COE_DEAD_LETTER_ENABLED=false`, `COE_PROVIDER_AWARE_ADMISSION=false`, `UKIE_CONNECTOR_<NAME>_ENABLED=false` for any connector causing issues | ~30s |

### 7.2 The single non-flag rollback: retro-scoring

Retro-scoring the 55 existing ingested rows in Stage 3 writes new
fields. To roll back:
- Fields are ADDITIVE — no old field is removed or overwritten
- To revert, execute a dry-run of the reverse-migration script (kept in `/backend/scripts/`) that `$unset`s the new fields
- Time cost: ~5 minutes (55 documents)

### 7.3 The one-way step: production strategies untouched

**Nothing in Phase 2 modifies the production `strategies` collection
except via the audited `POST /api/knowledge/promote/{item_id}`
bridge.** All rollback paths are safe by construction.

### 7.4 Data-loss risk assessment

| Change | Data-loss risk |
|---|---|
| `WorkloadQueue` in-memory during Stage 2 | LOW — jobs in-flight at rollback continue on the direct-dispatch path; queued jobs discarded (P2 only; P0 already dispatched) |
| `budget_state` Mongo mirror | ZERO — persistence is additive, in-memory tracker unchanged |
| Canonical M1 read-mode | ZERO — parallel stores retained read-only through the whole Stage 2 lifecycle; deletion is a **separate Phase 3 decision** |
| Governance cutover (Stage 3) | LOW — old rows preserved; new rows land in isolated KB; no production strategy modified |
| Dead-letter collection | ZERO — reads/writes are additive |

---

## 8. Success criteria per stage

Success criteria are **outcome-based**, not activity-based.

### 8.1 Stage 1

- ✅ No production incident during rollout
- ✅ Restart-preserved daily USD accounting (test: kill backend, restart, verify counters preserved)
- ✅ Task hard-timeout catches a runaway task (test: submit a `while True` task; verify it's killed at `HARD_TIMEOUT_S`)
- ✅ `HealthSnapshot` returned for COE + VIE via `/api/health/system`
- ✅ Byte-identical behaviour when all Stage-1 flags OFF

### 8.2 Stage 2

- ✅ p95 admission latency < 200ms under `pressure_band=high`
- ✅ P0 (interactive) requests never wait behind P2 (background) — verified by percentile latency
- ✅ Reservations honoured: EXECUTION admits at least `reservation` concurrent jobs even when BACKTEST is at capacity
- ✅ M1 canonical read produces identical candles to parallel-store reads (bit-for-bit ± tolerance) across ≥ 3 symbols × ≥ 4 timeframes
- ✅ `GET /api/data/coverage` returns complete coverage matrix

### 8.3 Stage 3

- ✅ **Zero unwanted writes to production `strategies`** during and after the governance cutover — verified by continuous audit query
- ✅ All 55 existing ingested rows carry `domain`, `trust_tier`, `license`
- ✅ Promotion bridge produces auditable draft rows in `strategies` with `eligible_for_deploy:False`
- ✅ Six domain sub-collections exist and are queryable

### 8.4 Stage 4

- ✅ Transient failures self-heal via retry; persistent failures land in dead-letter
- ✅ Provider outage automatically reroutes via circuit-breaker + VIE
- ✅ All ≥ 9 subsystems return valid `HealthSnapshot`
- ✅ `platform_health_score` computed and alertable
- ✅ Grafana dashboard renders all key metrics
- ✅ Under load: 100 concurrent P0 requests → p95 admission latency < 200ms

---

## 9. Estimated milestones

Assumes **one engineer per subsystem**, working focused-days.

| Stage | Focused days (serial) | With parallel tracks (2 engineers) | Calendar (assume 4 dev-days/week) |
|---|---|---|---|
| Stage 1 (COE α + VIE hardening) | 8 | 5 | 1–2 weeks |
| Stage 2 (COE β + BI5 refactor) | 9 | 5 | 1–2 weeks |
| Stage 3 (UKIE α + UKIE β) | 7 | 5 | 1–2 weeks |
| Stage 4 (COE γ + UKIE γ + observability) | 11 | 7 | 2 weeks |
| Validation buffer per gate | 1 × 4 = 4 | 1 × 4 = 4 | 1 week total |
| **TOTAL** | **39** | **26** | **~6–8 weeks calendar** |

**Buffer.** The estimate assumes no scope changes and stable
production. A 20% buffer (add 8 days / ~1 week) is prudent for
unexpected integration issues.

**Parallel-engineer prerequisite.** Stage 4 UKIE γ (5 connectors)
can be built in parallel by up to 5 engineers → ~1 day each. All
other parallel tracks assume 2 engineers.

---

## 10. Per-stage implementation checklists

### 10.1 Stage 1 checklist

#### 10.1.1 COE α

- [ ] Create `backend/engines/health/__init__.py`, `backend/engines/health/contract.py` — `HealthSnapshot` dataclass with all 7 fields per §4
- [ ] Create `backend/engines/health/aggregator.py` — `GET /api/health/system` router
- [ ] Extend `backend/legacy/engines/workload_classes.py` — add MARKET_DATA, KNOWLEDGE, EXECUTION, MONITORING, META_LEARNING; extend `_PROFILE_DEFAULTS` with `reservation` field
- [ ] Add `WorkloadRequest` dataclass in `backend/legacy/engines/orchestrator/types.py`
- [ ] Add `HARD_TIMEOUT_S: float`, `RETRY_POLICY: Literal[...]` to `Task` Protocol; default values
- [ ] Update all 17 existing task adapters with class-appropriate `HARD_TIMEOUT_S`
- [ ] Wrap `task.run(ctx)` with `asyncio.wait_for(..., timeout=task.HARD_TIMEOUT_S)` in `orchestrator/core.py._dispatch`
- [ ] Add crash budget + auto-recycle to `cpu_pool.py` — new `POOL_CRASH_THRESHOLD` env
- [ ] Add `budget_state` Mongo collection + persistence hooks in `budget_tracker.py`
- [ ] Add flag reads: `COE_ENABLED`, `COE_HEALTH_CONTRACT_ENABLED`, `COE_HARD_TIMEOUT_ENABLED`, `COE_CRASH_BUDGET_ENABLED`, `BUDGET_PERSIST`

#### 10.1.2 VIE hardening

- [ ] Register 6 UKIE-parser tasks in `vie/router.py` task map (per PHASE_2_CONSOLIDATED_REVIEW §4.5)
- [ ] Add `provider_hint: Optional[str]` param to `VIEClient.generate()` and `vie/router.route()`
- [ ] Ensure every `provider.generate()` completion calls `budget_tracker.record()` — audit the 6 provider adapters
- [ ] Add `VIE_TASK_MAP_EXTENDED`, `VIE_PROVIDER_HINT_RESPECT`, `VIE_BUDGET_PERSIST` flags

#### 10.1.3 Tests

- [ ] `backend/tests/test_health_contract.py` — validates `HealthSnapshot` shape + score bounds
- [ ] `backend/tests/test_workload_request.py` — validates serialisation
- [ ] `backend/tests/test_hard_timeout.py` — submits a runaway task, verifies kill
- [ ] `backend/tests/test_budget_persist.py` — records spend, kills tracker, reload, verifies preserved
- [ ] `backend/tests/test_provider_hint.py` — submits a hinted request, verifies routing

### 10.2 Stage 2 checklist

#### 10.2.1 COE β

- [ ] Create `backend/engines/coe/queue.py` — `WorkloadQueue` Protocol + `LocalQueueDriver` + stub `DistributedQueueDriver`
- [ ] Create `backend/engines/coe/io_pool.py` — thread pool + submit_io + get_pool_state
- [ ] Switch `orchestrator.tick` to consume from `WorkloadQueue.next()` under `COE_LANES_ENABLED=true`
- [ ] Add reservation enforcement in `orchestrator._workload_capacity()`
- [ ] Route MARKET_DATA, KNOWLEDGE, MONITORING through `io_pool`
- [ ] Create `backend/api/coe.py` — `/api/coe/state`, `/api/coe/metrics`, `/api/coe/jobs`, `/api/coe/reservations`
- [ ] Middleware: emit `X-COE-Pressure` header on every response

#### 10.2.2 BI5 refactor

- [ ] Update `data_access.load_candles(symbol, timeframe)` — always read M1, resample to requested TF using existing resampler
- [ ] Add `coverage_report` collection + writers
- [ ] Add `/api/data/coverage` endpoint
- [ ] Backfill any missing M1 hours from parallel stores before flipping `BI5_LEGACY_STORE_READ_ONLY=true`
- [ ] Wire `bi5_realism_sweep` to consume M1 canonical inputs (via `data_access`)

#### 10.2.3 Tests

- [ ] `backend/tests/test_workload_queue_local.py` — Protocol compliance, P0/P1/P2 ordering
- [ ] `backend/tests/test_reservations.py` — reservation floors honoured under pressure
- [ ] `backend/tests/test_io_pool.py` — bursty MARKET_DATA does not block BACKTEST
- [ ] `backend/tests/test_bi5_canonical_read.py` — resampled M15/H1/H4 matches parallel-store reads
- [ ] `backend/tests/test_coverage_report.py` — coverage matrix completeness

### 10.3 Stage 3 checklist

#### 10.3.1 UKIE α

- [ ] Create `backend/engines/knowledge/domains.py` — `KnowledgeDomain` enum + `KnowledgeDomainSpec` + registry with 6 canonical domains
- [ ] Extract `KnowledgeConnector` Protocol in `backend/legacy/engines/strategy_ingestion/connector.py`
- [ ] Refactor existing GitHub logic → `GithubConnector(supported_domains={STRATEGY})`
- [ ] Add `domain: KnowledgeDomain` field to `RawKnowledgeItem`
- [ ] Update `ingestion_runner` to accept the new Protocol + Item

#### 10.3.2 UKIE β

- [ ] `backend/engines/knowledge/domain_router.py` — dispatches by domain
- [ ] `backend/engines/knowledge/license_gate.py` — 5-outcome classifier (SPDX + heuristic)
- [ ] `backend/engines/knowledge/trust_scorer.py` — 5-tier ladder
- [ ] `backend/engines/knowledge/dedup_check.py` — within-domain canonical_hash
- [ ] Extend `KnowledgeRepository` with `insert_ingested(domain, item)` — the audited write
- [ ] Add per-domain sub-collections: `strategies`, `research`, `indicators`, `market`, `execution`, `internal_history`
- [ ] `POST /api/knowledge/promote/{item_id}` — admin-only, T4+ only, dedup check, writes draft to `strategies`
- [ ] Dry-run script: reproduce last 10 ingestion runs through new path → diff normalised output
- [ ] Retro-scoring script: backfill 55 existing rows with `domain=STRATEGY`, `trust_tier`, `license`
- [ ] `HealthSnapshot` implementation for UKIE

#### 10.3.3 Tests

- [ ] `backend/tests/test_domain_registry.py`
- [ ] `backend/tests/test_domain_routing.py` — item with `domain=research` writes to `research` collection
- [ ] `backend/tests/test_license_gate.py` — 5 outcomes verified
- [ ] `backend/tests/test_trust_scorer.py` — 5 tiers verified
- [ ] `backend/tests/test_dedup_check.py` — within-domain collision refused; cross-domain allowed
- [ ] `backend/tests/test_governance_cutover.py` — ingestion does not touch production `strategies`
- [ ] `backend/tests/test_promote_bridge.py` — admin promotes; non-admin refused

### 10.4 Stage 4 checklist

#### 10.4.1 COE γ

- [ ] Retry executor with per-class backoff schedule
- [ ] `workload_dead_letter` collection + `/api/coe/dead-letter/*` endpoints
- [ ] Consult `ai_workforce.circuit_breaker` in `admission_gate` for AGENT-class + BACKTEST-with-LLM
- [ ] Age-boost score adjustment in `orchestrator._score_task`
- [ ] Elastic band redistribution between BACKTEST ↔ MUTATION

#### 10.4.2 UKIE γ (in parallel)

- [ ] `ArxivConnector` (research)
- [ ] `PdfConnector` (research + strategy + execution + indicator)
- [ ] `PropFirmConnector` (execution)
- [ ] `TradingViewConnector` (strategy + indicator)
- [ ] `InternalMongoConnector` (internal_history — read-only mirror)

#### 10.4.3 Observability

- [ ] `HealthSnapshot` retrofit for Meta-Learning (`engines/meta_learning`)
- [ ] `HealthSnapshot` retrofit for MI (`engines/market_intel_engine`)
- [ ] `HealthSnapshot` retrofit for Execution (`engines/execution`)
- [ ] `HealthSnapshot` retrofit for Portfolio (`engines/portfolio`)
- [ ] `HealthSnapshot` retrofit for Factory-Eval (`engines/factory_eval`)
- [ ] `platform_health_score` aggregator + weights
- [ ] Prometheus scrape config
- [ ] Grafana dashboard: 5 panels (capacity, budget, coverage, domains, subsystem-health)
- [ ] Alertmanager rule: `platform_health_score < PLATFORM_HEALTH_ALERT_THRESHOLD`

#### 10.4.4 Tests

- [ ] `backend/tests/test_retry_backoff.py`
- [ ] `backend/tests/test_dead_letter.py`
- [ ] `backend/tests/test_provider_aware_admission.py`
- [ ] `backend/tests/test_connector_<name>.py` × 5
- [ ] `backend/tests/test_health_aggregator.py` — all 9 subsystems return valid snapshots

---

## 11. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Governance cutover (Stage 3) accidentally writes to production `strategies` | LOW | CRITICAL | Dry-run gate before flag flip; continuous audit query during rollout; instant rollback via `UKIE_GOVERNANCE_CUTOVER=false`; production `strategies` write path is separately guarded by `StrategyRepository` (Phase-1.6) |
| R2 | ProcessPool crash cascade takes down backend | LOW | HIGH | Crash budget + auto-recycle (Stage 1); `USE_PROCESS_POOL_DEFAULT_ON=false` remains until Stage 2 gate passes |
| R3 | BI5 M1 canonical read produces subtly different candles than parallel stores | MEDIUM | HIGH | Bit-for-bit diff test across ≥ 3 symbols × ≥ 4 timeframes as gate item; parallel stores retained read-only through Stage 2; flag `BI5_CANONICAL_M1_READ_MODE=false` reverts instantly |
| R4 | New workload classes (MARKET_DATA, KNOWLEDGE, EXECUTION, MONITORING, META_LEARNING) receive incorrect reservations, causing starvation | MEDIUM | MEDIUM | Per-class env overrides `ORCH_RESERVATION_<CLASS>`; gate item verifies EXECUTION reservation under BACKTEST saturation |
| R5 | VIE task-map extension routes new tasks to wrong provider | LOW | MEDIUM | Provider chain defined in code (auditable); each of 6 new tasks has explicit fallback chain; failing task journals reason |
| R6 | Retro-scoring the 55 existing UKIE rows corrupts data | LOW | MEDIUM | Dry-run first, no auto-mutate; reverse-migration script kept in `/backend/scripts/`; retro-scoring uses `$set` only (additive) |
| R7 | Health-contract retrofit for existing subsystems (Stage 4) breaks their diagnostic endpoints | LOW | LOW | Health endpoint is ADDITIVE (`GET /api/<sub>/health`); existing diagnostic endpoints untouched |
| R8 | Dead-letter collection grows unbounded | MEDIUM | LOW | TTL index on `first_failed_at` (default 90 days); operator dashboard shows count |
| R9 | Distribution-ready contracts add complexity without immediate benefit | MEDIUM | LOW | Local drivers are the only production path; distributed stubs raise `NotImplementedError`; interface is minimal (protocol-based). Alternative: not being distribution-ready would force a rewrite later — the cost is asymmetric. |
| R10 | Estimated milestones (§9) miss by > 30% | MEDIUM | LOW | 20% calendar buffer built in; validation gates catch scope drift; parallel tracks can be resequenced |

---

## 12. Sign-off

This master plan is authoritative once operator approves it in
writing (or via ratified session confirmation).

**Operator approvals recorded:**

- ✅ Phase 2 architecture direction — approved 2026-02-19
- ✅ Six Knowledge Domains — approved 2026-02-19
- ✅ COE direction with distribution-ready-from-day-one directive — approved 2026-02-19
- ✅ Universal Health Contract (measurable health as cross-cutting principle) — approved 2026-02-19
- ✅ Four-stage implementation with validation gates — approved 2026-02-19
- ⏳ **This master plan** — pending review

**When approved, execution begins with Stage 1.**

---

*Document metadata:*
- Created: 2026-02-19
- Depends on: PHASE_2A / 2B / 2C / 2D / PHASE_2_CONSOLIDATED_REVIEW
- Update policy: any deviation from this plan during implementation is recorded as an amendment at the bottom of this file; the plan is otherwise treated as immutable to preserve the implementation contract.
