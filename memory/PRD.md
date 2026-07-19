# Strategy Factory — Deployment + Phase-1 Certification PRD

## Original problem statement (session 1)

Complete the production deployment ONLY of the canonical repository
`raghugr2013-lgtm/strategy-factory-canonical` (branch `main`) to
`https://strategy.coinnike.com` on VPS `144.91.78.175`
(Ubuntu 24.04, Docker installed, images built, DNS live).

Blockers on entry: prod MongoDB, Caddy reverse proxy, prod `.env`.

## What is running in production today

- Application at `https://strategy.coinnike.com`
- Backend commit ≥ `546d0a9` + `e873af3` (ENABLE_* flags in factory-backend env block)
- Legacy full-recovery mount: **101 routers online**
- OpenAPI paths: **616**
- Reverse proxy: Caddy 2 auto-HTTPS on `vqb-network`
- MongoDB: self-hosted `factory-mongo` container on `vqb-network`, port not published to host
- All four factory-* containers on a single unified compose project `strategy-factory` from
  `/home/raghu/projects/strategy-factory-canonical`
- Meta-Learning default mode: **OBSERVE** (structurally cannot mutate)

## Sessions summary

### Session 1 — Production infra (COMPLETE)
- External Mongo (`/opt/factory-mongo/`)
- External Caddy (`/opt/caddy/`)
- Prod `.env` (`/home/raghu/projects/.../env`)
- Bootstrap script + safety features (snapshot, no-reset)

### Session 2 — Config-drift fix (COMPLETE)
- Root cause: `factory-backend.environment:` block was missing the three
  `ENABLE_*` flags → `_bool_env(default=False)` disabled all legacy routers
- Fix: 12-line patch to `infra/compose/docker-compose.prod.yml` (commit landed
  via Emergent auto-commit)

### Session 3 — Deployment unification (COMPLETE)
- Root cause: two `docker compose` projects merged under default name `compose`
  because both invocation `cwd`s ended in `infra/compose/`
- Fix: `COMPOSE_PROJECT_NAME=strategy-factory` pinned; stale `/opt/strategy-factory`
  factory-* containers removed by name; all four services recreated from
  `/home/raghu/projects/...canonical` under a single project.
  Result: legacy full-recovery mount = 101 routers, OpenAPI = 616 paths.

### Session 4 — Phase-1 autonomous validation (COMPLETE)
- 24/24 modules PASS
- 1 real defect found + fixed: `bi5_maturity` placeholder body (2-line body added)
- 0 broken frontend↔backend wires (89 unique frontend calls, 89 registered backend routes)
- 32 MongoDB collections auto-initialised
- Meta-Learning confirmed OBSERVE
- **GREEN SIGNAL — cleared for AI provider integration**
- Full report: `/app/memory/PHASE_1_CERTIFICATION.md`

## What's ready for Phase 2

- Controlled UI migration from the newer-UI repo (per session-1 deferred item).
- AI provider integration (Claude Anthropic recommended as first provider).
- ENABLE_FACTORY_RUNNER can be flipped to `true` in prod (compose already
  supports it under both services).

## Architecture Review Phase (Session 5 — COMPLETE)

**All four Phase-2 architecture reviews delivered, plus consolidated cross-review and authoritative implementation master plan:**

- `PHASE_2A_AI_ARCHITECTURE_REVIEW.md` — Vendor-Independent Intelligence Engine (VIE). 634 lines. **Approved.**
- `PHASE_2B_MARKET_DATA_REVIEW.md` — BI5 canonical-M1 read-side + coverage reports. 525 lines. **Approved.**
- `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md` — UKIE organised around six **Knowledge Domains** (`strategy`, `research`, `indicator`, `market`, `execution`, `internal_history`). 582 lines. **Approved with domain-first framing (updated 2026-02-19).**
- `PHASE_2D_COMPUTE_ORCHESTRATION_REVIEW.md` — COE: 10-class taxonomy, priority lanes, reservations, `WorkloadRequest`, retry + dead-letter, provider-aware admission, **distribution-ready from day one**. 780 lines. **Approved (2026-02-19).**
- `PHASE_2_CONSOLIDATED_REVIEW.md` — cross-phase implementation sequence + integration hot-spots + **Universal Health Contract** (measurable health as cross-cutting principle). ~580 lines. **Approved (2026-02-19).**
- `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md` — **the authoritative Phase-2 implementation guide.** Consolidates all reviews, defines 4 staged waves with validation gates, feature-flag registry, rollback strategy, per-stage checklists, risk register. **Pending final review before Stage 1 execution.**

**Two operator directives baked into all documents (2026-02-19):**
1. **Distribution-ready from day one.** No single-node assumptions may leak into any Phase 2 subsystem. `WorkloadQueue`, `BudgetTracker`, `queue_pressure`, `host_capability` all define `LocalDriver` (α/β) + `DistributedDriver` (γ+) under the same Protocol. The current VPS is the first compute node, not the permanent architecture.
2. **Measurable health everywhere.** Every subsystem (VIE, BI5, UKIE, COE, Meta-Learning, MI, Execution, Portfolio, Factory-Eval) MUST expose the standard `HealthSnapshot` (7 fields: subsystem, ts, health_score, readiness_score, confidence_score, resource_usage, last_successful_run, failure_count, recovery_status). Contract ships in COE α (Stage 1) as `engines/health/contract.py`. Aggregated at `GET /api/health/system`.

**Staged implementation with validation gates:**
- **Stage 1** — COE α + VIE hardening → Validation Gate 1
- **Stage 2** — COE β + BI5 refactor → Validation Gate 2
- **Stage 3** — UKIE α + UKIE β (includes governance cutover) → Validation Gate 3
- **Stage 4** — COE γ + UKIE γ + Observability → Final Validation Gate

**Estimated:** ~26 focused-days with 2-engineer parallel tracks / ~6–8 weeks calendar. 20% buffer recommended.

**NO code changes yet.** Awaiting operator sign-off on `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md` before Stage 1 begins.

## Stage 1 Execution (Session 5, 2026-02-19 — COMPLETE, awaiting Gate-1 sign-off)

**Delivered:**
- `/app/backend/legacy/engines/health/` — Universal Health Contract (`HealthSnapshot` dataclass + providers registry + FastAPI router)
- `/app/backend/legacy/engines/coe/workload_request.py` — canonical `WorkloadRequest` envelope with `Lane` (P0/P1/P2) + `RetryPolicy` enums
- `WorkloadClass` extended from 5 → 10 classes with **conservative reservation floors** per operator directive (EXECUTION=2, MARKET_DATA=1, backgrounds=0)
- `Task.HARD_TIMEOUT_S` + `RETRY_POLICY` added to Protocol; wired via `asyncio.wait_for` in orchestrator dispatch (flag-gated)
- All **17 task adapters** carry class-appropriate `HARD_TIMEOUT_S` values
- CPU pool crash budget + auto-recycle (flag-gated)
- `BudgetTracker` Mongo persistence (`budget_state` collection); boot-time rehydration in `app/main.py` lifespan
- VIE hardening: 5 new UKIE-parser tasks in `DEFAULT_TASK_MAP`, `provider_hint` propagation, central budget-tracker recording
- **34/34 Stage-1 pytest tests passing**
- **Rollback verified live** in ~35 s: all 7 flags flipped OFF → backend byte-identical to Phase-1 → flipped back ON → `platform_health_score=100`

**Documents produced this session:**
- `/app/memory/BID_CANDLE_STORAGE_REVIEW.md` (553 lines) — architecture review of BID historical candle data. **Option D approved** (Canonical M1 + materialised HTF caches). Introduces the **Canonical Timeframe Service (CTS)** as a dedicated Stage-2 component; event-driven cache invalidation; monthly advisory-only provider-HTF verification; per-instrument `canonical_mode` for M1-history exceptions.
- `/app/memory/PHASE_2_VALIDATION_GATE_1_REPORT.md` — comprehensive Gate-1 assessment: features implemented, flag registry, validation results, performance impact, health metrics, risks, rollback verification, files changed. **Recommendation: PASS Validation Gate 1.**

**Awaiting:** operator sign-off on `PHASE_2_VALIDATION_GATE_1_REPORT.md` before Stage 2 begins.

## Stage 2 Execution (Session 5 continued, 2026-02-19 — IN PROGRESS)

**Approved by operator on 2026-02-19.** Stage 2 execution plan documented in `/app/memory/PHASE_2_STAGE_2_EXECUTION_PLAN.md` (10 sub-stages, ~10.5 focused-days serial).

**Completed sub-stages this session:**

- **2.α — Prep** ✅
  - Fixed hardcoded credentials in `tests/backend_test.py` — now reads `ADMIN_EMAIL` / `ADMIN_PASSWORD` from env with sane defaults matching `.env`. `TestHealth::test_health` + `test_version` now pass (previously all 22 tests failed).
  - Set conservative `ORCH_BUDGET_DAILY_USD=25.00` + `ORCH_BUDGET_MONTHLY_USD=500.00` in `.env`. `budget_headroom` now reporting `1.0` on `/api/health/coe`.

- **2.β — WorkloadQueue foundation** ✅
  - `engines/coe/queue.py` — `WorkloadQueue` Protocol + `get_queue()` factory + `COE_QUEUE_DRIVER=local|distributed` selection
  - `engines/coe/queue_local.py` — `LocalQueueDriver` in-memory implementation (3 lanes × N classes, `asyncio.Lock`-protected, cancel-safe)
  - `engines/coe/queue_distributed.py` — `DistributedQueueDriver` stub proving the switch-point works (raises `NotImplementedError` with clear Phase-3 pointer)
  - **17 new pytest tests passing** (`test_workload_queue.py`): P0>P1>P2 lane ordering, FIFO within lane, cancel(), peek(), snapshot(), size(), driver selection, invalid-lane fallback, Protocol compliance for both drivers
  - **Total Phase-2 tests: 51/51 passing**
  - Backend still healthy — no import cycles, boot log clean, `platform_health_score=100`

- **2.γ — Orchestrator integration** ✅
  - `_workload_capacity()` extended with reservation-aware floors (flag-gated `COE_RESERVATIONS_ENABLED`). When flag ON, per-class reservations guarantee minimum concurrency even when other classes are saturated. EXECUTION floor=2 honoured even when BACKTEST at capacity (verified by test).
  - New workload classes (`market_data`, `knowledge`, `execution`, `monitoring`, `meta_learning`) added to `caps_map` with unlimited caps + their reservation floors.
  - `Orchestrator._drain_queue(ctx, remaining)` — new method (flag-gated `COE_LANES_ENABLED`) that pulls from `WorkloadQueue.next()` before registry-based scoring. Unknown task_names dropped with a warning (not fatal). Cap-respecting.
  - Wired into `_tick()` at the top of the dispatch phase — queued jobs get first bite of `hard_cap_remaining`.
  - `ORCH_RESERVATION_<CLASS>` env overrides working per Stage 1 (verified again by test).

- **2.δ — I/O Pool** ✅
  - `engines/io_pool.py` — `ThreadPoolExecutor` mirroring the CPU pool pattern. Feature-gated `USE_IO_POOL`; fallback to `asyncio.to_thread` when off.
  - Sized to `min(32, 4 × cpu_count)`; env override `IO_POOL_SIZE`.
  - `submit_io(fn, *args, workload_class="io", **kwargs)` — records per-class submit counts.
  - **Isolation smoke verified**: 20 concurrent 100 ms blocking I/O jobs on a pool of 8 workers do NOT block a short coroutine from completing in < 200 ms.

- **Metrics scaffold** (feeds Market Data Validation Report per operator directive) ✅
  - `engines/metrics.py` — `MetricsRegistry` with counters, gauges, histograms, timers. In-memory; bounded to 10k samples per histogram; sub-microsecond overhead.
  - `Metric` catalogue class — canonical metric names for Phase 2: `coe_queue_submit_total`, `coe_queue_dispatch_total`, `coe_queue_latency_ms`, `coe_tick_ms`, `coe_dispatch_ms`, `coe_io_pool_submit_total`, `cts_aggregation_ms`, `cts_cache_hit_total`, `cts_cache_miss_total`, `cts_cache_write_ms`, `cts_rebuild_ms`, `cts_invalidation_total`.
  - `LocalQueueDriver` instrumented — every `submit()` counts `QUEUE_SUBMIT_TOTAL`; every `next()` counts `QUEUE_DISPATCH_TOTAL` + observes `QUEUE_LATENCY_MS` (submit→dispatch).

- **Coverage API contract preview** ✅
  - `/app/memory/COVERAGE_API_CONTRACT_PREVIEW.md` — full response schema for `GET /api/data/coverage` per operator directive (contract-first). Documents: query params, top-level shape (`summary`/`symbols`/`gaps`/`cache`/`provider`/`health`), per-symbol block, gap enumeration with tiered severity, HTF cache state, provider sync status, embedded CTS `HealthSnapshot`, Prometheus text format, 7 related endpoints (`/api/cts/*`), 5 design invariants, 5 open questions for operator.

**Total Phase-2 tests: 78/78 passing.** Backend healthy: `platform_health_score=100`; all 101 legacy routers still mount.

- **2.ε — CTS Foundation** ✅
  - `engines/cts/types.py` — `Candle`, `CandleWindow`, `Provenance`, `DataQualityState`, `RebuildReport`, `VerificationReport`. **Traceability invariant #17** baked in: every window carries provenance identifying canonical source, aggregation path, cache generation ts, cache version, cache bucket key, repair status, data quality state, gap count.
  - `engines/cts/resampler.py` — pure M1 → HTF aggregator via pandas `resample(rule).ohlc()` with `label="left", closed="left"` semantics. Deterministic; unit-testable in isolation. 3-axis bucket key helper.
  - `engines/cts/service.py` — `CanonicalTimeframeService` Protocol + `LocalCTS` implementation. `get_cts()` singleton factory (respects `CTS_DRIVER=local|distributed`). CTS registers its `HealthSnapshot` provider on import.
  - `engines/data_access.py` — `load_ohlc_bars()` routes through CTS when `BID_CANONICAL_M1_READ_MODE=true` AND `source="bid_1m"`. Legacy fallback on error. Byte-identical when flag OFF.
  - `app/main.py` — CTS module touched at boot so its health provider registers with the Universal Health Contract. `platform_health_score` aggregator now sees THREE subsystems: coe + vie + cts.

- **2.ζ — HTF Materialised Cache** ✅
  - `engines/cts/cache.py` — `HtfCache` reading/writing `market_data_htf_cache` collection. 3-axis sharding (`symbol|timeframe|yyyy-mm`) per §10.2. Event-driven invalidation via `HtfCache.invalidate()` (`BID_CACHE_EVENT_INVALIDATION=true`). Secondary time-based safety via `BID_HTF_CACHE_MAX_AGE_DAYS` (default 365).
  - Cache miss reasons instrumented: `disabled`, `no_db`, `read_error`, `not_found`, `stale`, `too_old`, `schema_mismatch`. Cache hit rate and misses recorded in `Metric` counters.
  - Write is best-effort; failure logs warning and caller still gets resampled data (never blocks the read path).

- **Traceability invariant added to BID review** (§10.6b) as platform invariant #17
- **CTS test suite** — 23 new tests covering: Provenance shape, all-field traceability, Candle roundtrip, resampler correctness for M1/M5/M15/H1, OHLC bar semantics (open=first, close=last, high=max, low=min, volume=sum), Protocol satisfaction, cache put/get/invalidate roundtrip, data_access route-through when flag ON, health snapshot shape, rebuild_bucket

**Total Phase-2 tests: 101/101 passing.** Backend healthy: `platform_health_score=100`; three subsystems registered (coe, cts, vie).

- **2.η — BI5 through CTS ✅**
  - `engines/bi5_realism.py::_load_bi5_bars` now honours `BI5_CTS_ROUTING=true` — when flag ON, delegates to `CTS.load_candles()`. This closes the "two truths" gap between BID and BI5 by putting them behind the SAME resampler. Legacy `_load_and_resample_bi5` path preserved as fallback on any error. Byte-identical when flag OFF.

- **2.θ — Coverage API ✅**
  - `engines/coverage_router.py` — `GET /api/data/coverage` + `GET /api/data/coverage/{symbol}` implemented against the locked contract in `COVERAGE_API_CONTRACT_PREVIEW.md`. Six top-level blocks (`summary`/`symbols`/`gaps`/`cache`/`provider`/`health`); `?include=` filter; symbol filter; JSON only in this Stage (Prometheus text-format at `/api/coe/metrics`).
  - Aggregates from live sources: Mongo `market_data` distinct-symbol query, `HtfCache.snapshot()`, `MetricsRegistry.snapshot()`, CTS `health_snapshot()`.
  - Feature-gated `COE_COVERAGE_REPORT_ENABLED=false` → HTTP 503.

- **2.ι — Prometheus exporter + X-COE-Pressure header ✅**
  - `engines/coe_metrics_router.py` — `GET /api/coe/metrics` in Prometheus text exposition format (counters, gauges, histograms as summaries with p50/p95/p99 quantiles). `GET /api/coe/state` — JSON snapshot.
  - `engines/coe_pressure_middleware.py` — Starlette middleware stamping `X-COE-Pressure: <band>` header on every `/api/*` response. Reads `queue_pressure.snapshot()`. Zero-cost when flag OFF.
  - Both mounted in `app/main.py`. Verified live: `X-COE-Pressure: idle` appears on `/api/health/coe`; `/api/coe/metrics` returns valid `# TYPE ... counter` / `# TYPE ... summary` lines with proper label sets.

- **Operational Dashboard Mockup ✅**
  - `/app/memory/OPERATIONAL_DASHBOARD_MOCKUP.md` — text-based mockup per operator directive. 8 panels in the mandated priority order (platform health → coverage → gaps → cache → provider → queue → budget → trends). Escalation-driven alerts, access model (admin full / researcher read-only / anonymous denied), refresh discipline, per-panel data-source table showing every endpoint already exists at end of Stage 2. Five open questions for operator.

**Total Phase-2 tests: 111/111 passing.** Backend healthy with all Stage-2 endpoints live:
- `/api/health/system` — 3 subsystems, platform_health_score=100
- `/api/health/{coe,cts,vie}` — full `HealthSnapshot`
- `/api/coe/metrics` — Prometheus text format
- `/api/coe/state` — JSON metrics snapshot
- `/api/data/coverage` + `/api/data/coverage/{symbol}` — locked-contract response
- `X-COE-Pressure` header on every `/api/*` response

All Stage-2 code remains DORMANT behind default-off flags — zero production behaviour change.

**Sub-stages remaining before Validation Gate 2:**
- 2.κ — Market Data Validation Report (evidence gathering + report writing)
- Validation Gate 2 report

**All Stage-2 code changes remain feature-flagged and dormant.** Zero behaviour change until flags are enabled.

## Backlog (P2 / cosmetic)

- Duplicate `operation_id` warning at `legacy/api/admin.py:list_users` (30-sec fix)
- Remove accidental self-submodule pointer at repo root
  (`git rm --cached strategy-factory-canonical`)
- Optional: nightly `mongodump` cron in `factory-mongo` compose

## Test credentials — local validation (NOT production)

See `/app/memory/test_credentials.md`. Production admin credentials (unchanged from session 1):
- Email: `admin@coinnike.com`
- Password: `Tmn0SECEyDxV1KqfbHMw` — rotate after first login
