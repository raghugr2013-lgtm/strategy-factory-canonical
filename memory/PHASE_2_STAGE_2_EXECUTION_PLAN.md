# Phase 2 — Stage 2 Execution Plan
### COE β + BI5 Refactor + BID Canonical M1 + CTS + WorkloadQueue

> **Status:** approved by operator on 2026-02-19.
> Assembled: 2026-02-19.
> Master plan reference: `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §6.2`
> extended with the BID canonical-M1 architecture (`BID_CANDLE_STORAGE_REVIEW.md`)
> and the Canonical Timeframe Service (`BID_CANDLE_STORAGE_REVIEW.md §10.5`).

---

## 1. Goal

Ship COE β (priority lanes + reservations + I/O pool + WorkloadQueue),
the BI5 read-side refactor, the BID canonical M1 read path, and the
Canonical Timeframe Service — all behind feature flags, all rollback
in 60 s, all with the same discipline demonstrated in Stage 1.

At the end: a **Market Data Validation Report** with objective
evidence that the new architecture is functionally correct and
operationally superior to the legacy per-TF path.

---

## 2. Sub-stages (executed in order, each independently gated)

| # | Sub-stage | Focus | Files | Est effort |
|---|---|---|---|---|
| 2.α | **Prep** | Test-infra fix (backend_test.py creds), conservative `ORCH_BUDGET_DAILY_USD` | `tests/backend_test.py`, `.env` | 0.5 d |
| 2.β | **WorkloadQueue foundation** | In-memory `LocalQueueDriver` with P0/P1/P2 lanes + reservations; stub `DistributedQueueDriver` for γ+ | `engines/coe/queue.py`, `engines/coe/queue_local.py`, `engines/coe/queue_distributed.py` (stub) | 1.5 d |
| 2.γ | **Orchestrator integration** | Wire `WorkloadQueue.next()` into orchestrator tick (flag-gated `COE_LANES_ENABLED`); enforce reservations under adaptive-concurrency caps | `orchestrator/core.py` | 1 d |
| 2.δ | **I/O pool** | Dedicated `ThreadPoolExecutor` for MARKET_DATA / KNOWLEDGE / MONITORING; feature-gated `USE_IO_POOL` | `engines/io_pool.py` | 0.5 d |
| 2.ε | **CTS foundation** | `CanonicalTimeframeService` Protocol + `LocalCTS` implementation; `data_access.load_candles()` re-entry point (flag-gated `BID_CANONICAL_M1_READ_MODE`) | `engines/cts/service.py`, `engines/cts/resampler.py`, `engines/data_access.py` | 1.5 d |
| 2.ζ | **HTF materialised cache** | `market_data_htf_cache` collection + event-driven invalidation + 3-axis sharding (`symbol|tf|yyyy-mm`) | `engines/cts/cache.py`, `engines/cts/invalidation.py` | 1.5 d |
| 2.η | **BI5 read-side consolidation** | BI5 resample path (already Option B in production) routed through CTS as the single implementer | `legacy/api/bi5_realism.py`, `legacy/engines/bi5_realism_sweep.py` | 1 d |
| 2.θ | **Coverage report + endpoints** | `coverage_report` collection + `/api/data/coverage` + `/api/cts/*` | `engines/cts/coverage.py`, `app/api/data.py` | 1 d |
| 2.ι | **Observability** | `X-COE-Pressure` response header + Prometheus text exporter at `/api/coe/metrics` | `app/main.py`, `engines/coe/metrics.py` | 1 d |
| 2.κ | **Market-data validation report** | End-of-stage report per operator directive (§4) | `/app/memory/PHASE_2_STAGE_2_MARKET_DATA_VALIDATION.md` | 1 d |

**Total:** ~10.5 focused days serial / ~7 days with 2-engineer parallel tracks.

---

## 3. Ordering rationale

- **2.α before everything** — the test infra is used by every subsequent sub-stage.
- **2.β + 2.γ before 2.ε** — CTS submissions ride on the workload queue.
- **2.δ before 2.ζ** — HTF materialisation is I/O-bound; benefits from the dedicated pool.
- **2.ε before 2.ζ** — the cache needs the CTS Protocol shape stable.
- **2.η after 2.ε** — BI5 consolidation reuses the CTS Protocol.
- **2.θ after 2.ζ** — coverage report reads cache state.
- **2.ι last** — observability wraps everything else.
- **2.κ absolutely last** — the report can only be written when there's real data to report on.

---

## 4. Success criteria — Validation Gate 2

All items must pass before Stage 3 begins:

- [ ] All Stage-1 validation items still pass
- [ ] `WorkloadQueue.LocalDriver` in-memory: P0 job dispatched before P2 under saturation (unit test)
- [ ] Reservations honoured: BACKTEST filling capacity does NOT starve EXECUTION reservation floor (unit test)
- [ ] `USE_IO_POOL=true`: 20 concurrent MARKET_DATA jobs do NOT block a concurrent BACKTEST (unit test)
- [ ] `BID_CANONICAL_M1_READ_MODE=true`: `load_candles("EURUSD", "H1")` returns identical candles to legacy M15/H1 rows (bit-for-bit ± float tolerance) across ≥ 3 symbols × ≥ 4 timeframes × ≥ 100 candles
- [ ] `BID_HTF_CACHE_ENABLED=true`: first read materialises; second read hits cache; invalidation event triggers re-materialise
- [ ] `X-COE-Pressure` header appears on every `/api/*` response
- [ ] `/api/coe/metrics` returns valid Prometheus text
- [ ] `/api/data/coverage` returns coverage matrix
- [ ] `/api/cts/state` returns CTS `HealthSnapshot`
- [ ] Distribution-ready check: `WorkloadQueue.LocalDriver` and `WorkloadQueue.DistributedDriver` (stub) both satisfy the Protocol; swapping via env raises cleanly
- [ ] Rollback: every 2.β–2.ι flag OFF → backend byte-identical to Stage 1
- [ ] Market Data Validation Report (§5) complete

---

## 5. Market Data Validation Report (deliverable at end of Stage 2)

Per operator directive — filed as
`/app/memory/PHASE_2_STAGE_2_MARKET_DATA_VALIDATION.md` at Sub-stage
2.κ. Must include:

1. **Canonical M1 integrity validation** — audit query against `market_data`; count of M1 rows per symbol; gap distribution; provider-diff sample
2. **CTS aggregation accuracy** — for ≥ 3 symbols × ≥ 4 timeframes × ≥ 100 candles, resampled HTF from M1 vs legacy per-TF rows: bit-for-bit diff, tolerance report
3. **Cache generation statistics** — buckets materialised, generation-time distribution (p50 / p95 / p99), storage footprint
4. **Cache hit/miss ratios** — per-TF hit rate, cold-start vs warm reads
5. **Performance comparison** — legacy read path (direct per-TF Mongo query) vs CTS path (M1 + resample + cache): p50/p95/p99 latency; throughput under 100 concurrent reads
6. **Historical rebuild verification** — force-invalidate a monthly bucket; re-materialise; compare byte-for-byte against pre-invalidation state
7. **Gap detection and repair verification** — inject a synthetic gap; run gap-analyzer; confirm detection + repair; confirm HTF cache invalidation cascades
8. **BI5 ↔ BID consistency observations** — for the last 30 days, diff H1 candles derived from BI5 vs H1 candles derived from BID M1; tabulate divergence tier breakdown per §10.3 of `BID_CANDLE_STORAGE_REVIEW.md`

Report format mirrors `PHASE_2_VALIDATION_GATE_1_REPORT.md` — evidence-based, tabulated, no assumptions.

---

## 6. Feature flag catalogue (Stage 2)

Every flag defaults **OFF**. Rollback = flag flip.

| Flag | Sub-stage | Effect ON |
|---|---|---|
| `COE_LANES_ENABLED` | 2.γ | Route dispatch through `WorkloadQueue` |
| `COE_RESERVATIONS_ENABLED` | 2.γ | Enforce per-class reservation floors |
| `USE_IO_POOL` | 2.δ | Enable I/O ThreadPoolExecutor |
| `BID_CANONICAL_M1_READ_MODE` | 2.ε | Route `load_candles()` through CTS (M1 + resample) |
| `BID_HTF_CACHE_ENABLED` | 2.ζ | Materialise `market_data_htf_cache` |
| `BID_CACHE_EVENT_INVALIDATION` | 2.ζ | Enable event-driven cache invalidation |
| `BID_HTF_CACHE_MAX_AGE_DAYS` | 2.ζ | Secondary safety TTL (default 365) |
| `BID_LEGACY_TF_ROWS_READ_ONLY` | 2.ζ | Deprecate per-TF rows in `market_data` |
| `INSTRUMENT_REGISTRY_ENABLED` | 2.ε | Per-instrument `canonical_mode` (m1/native_tf) |
| `BI5_CTS_ROUTING` | 2.η | Route BI5 realism sweep resample via CTS |
| `COE_COVERAGE_REPORT_ENABLED` | 2.θ | Emit coverage matrix |
| `X_COE_PRESSURE_HEADER_ENABLED` | 2.ι | Emit `X-COE-Pressure` on responses |
| `COE_METRICS_ENABLED` | 2.ι | Expose `/api/coe/metrics` |

---

## 7. Non-goals for Stage 2

- **No dead-letter / retry executor** — that's Stage 3 (COE γ).
- **No provider-aware admission gate** — that's Stage 3.
- **No connector fleet (UKIE γ)** — that's Stage 4.
- **No deletion of legacy per-TF rows in `market_data`** — kept read-only through Stage 2; deletion is a separate Phase-3 decision.
- **No InfluxDB / Parquet migration** — reserved for Phase 3+ if warranted.
- **No live-trading order flow** — Phase 3.

---

## 8. Sign-off

- ✅ **Stage 2 execution plan** — approved by operator on 2026-02-19
- Sub-stage progress tracked in `PRD.md`; each sub-stage closes with a small verification pass
- Validation Gate 2 report + Market Data Validation Report both required before Stage 3 begins
