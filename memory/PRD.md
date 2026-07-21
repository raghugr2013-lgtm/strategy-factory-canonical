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

**Sub-stages remaining before Validation Gate 2:** ✅ COMPLETE + APPROVED
- 2.κ — Market Data Validation Report — `PHASE_2_STAGE_2_MARKET_DATA_VALIDATION_REPORT.md` ✅
- Validation Gate 2 Report — `PHASE_2_VALIDATION_GATE_2_REPORT.md` ✅
- **Operator sign-off received (2026-02-19).**

## Phase 2 Stage 3.α — UKIE Foundation (2026-02-19) ✅

Foundation architecture ONLY per operator directive — no pipeline
stages, no governance cutover, no retro-scoring.

- **P2C.0 — `KnowledgeDomain` registry** ✅
  - `engines/knowledge/domains.py` — enum with the six canonical
    domains (`strategy`, `research`, `indicator`, `market`,
    `execution`, `internal_history`); `KnowledgeDomainSpec` frozen
    dataclass carrying every operator-mandated field (`display_name`,
    `description`, `storage_collection`, `required_fields`,
    `default_trust_floor`, `ai_context_policy`,
    `default_retention_policy`, `searchable`, `version`); immutable
    `KNOWLEDGE_DOMAIN_REGISTRY` module-level constant.
  - Extensibility contract: every field has a default; adding a
    seventh domain is one entry.

- **P2C.1 — `KnowledgeConnector` Protocol + `GithubConnector`** ✅
  - `engines/knowledge/connector.py` — `@runtime_checkable Protocol`
    with capability metadata (`ConnectorCapabilities` dataclass:
    `supports_discovery`, `supports_incremental_sync`,
    `supports_versioning`, `supports_rate_limits`,
    `supports_metadata_only`, all default False); supporting
    dataclasses `RateLimit`, `DiscoveryQuery`, `Reference`;
    `RawKnowledgeItem` envelope with the `domain` field + hard-rail
    guardrails (`learning_only=True`, `eligible_for_deploy=False`).
  - `engines/knowledge/connectors/github.py` — `GithubConnector`
    wraps existing `strategy_ingestion.collector`. Declares
    `supported_domains={STRATEGY}` and honest capability set.
    **Zero behaviour change to the legacy path** — legacy
    `ingestion_runner` continues to call `collector` directly.

- **Registry + read-only API** ✅
  - `engines/knowledge/registry.py` — combined domain re-exports +
    connector registry with `register_connector` / `get_connector` /
    `list_connectors` / `connectors_for_domain`. Auto-registers
    `GithubConnector` at import time.
  - `engines/knowledge/router.py` — `/api/knowledge/domains`,
    `/api/knowledge/domains/{domain}`,
    `/api/knowledge/connectors`,
    `/api/knowledge/connectors/{name}`,
    `/api/knowledge/domains/{domain}/connectors`. Flag-gated by
    `UKIE_DOMAIN_REGISTRY_ENABLED=false` → HTTP 503.

- **Stage 3.α tests: 50 / 50 passing.** Cumulative Phase-2 tests:
  **158 / 158** (Stage 1: 34 + Stage 2: 74 + Stage 3.α: 50).

- **Deliverable:** `/app/memory/PHASE_2_STAGE_3_ALPHA_NOTES.md`
  documenting the foundation contract for Stage 3.β consumers.

**Feature flag introduced (default OFF):**
- `UKIE_DOMAIN_REGISTRY_ENABLED` — mounts `/api/knowledge/domains/*` +
  `/api/knowledge/connectors/*`

Live verification (preview pod, flag ON):
- `/api/knowledge/domains` returns 6 domains with full spec shape
- `/api/knowledge/connectors` returns `github` with declared capabilities
- `/api/health/system` unchanged: platform_health_score=100 across coe / vie / cts

**Explicit non-goals honoured** — Stage 3.α ships ONLY the domain
registry, connector Protocol, GithubConnector adapter, registry, and
read-only API. Pipeline stages, governance cutover, retro-scoring,
and additional connectors are Stage 3.β / Stage 4.

## Phase 2 Stage 3.β — UKIE Pipeline + Governance Integration (2026-02-19) ✅

Focused scope per operator approval: pipeline stages + repository +
dry-run harness. NO promotion bridge, NO retro-scoring, NO new
connectors.

**Files delivered under `/app/backend/legacy/engines/knowledge/`:**
- `constants.py` — `PIPELINE_VERSION` (0.1.0) + `PIPELINE_CONTRACT_VERSION` (0.1.0) + `KNOWLEDGE_DB_NAME`
- `domain_router.py` — P2C.4 — pure dispatch by domain; flag: `ENABLE_DOMAIN_ROUTING`
- `license_gate.py` — P2C.5 — 5-outcome classifier (SPDX + heuristic); flag: `ENABLE_LICENSE_GATE`
- `trust_scorer.py` — P2C.6 — 5-tier ladder with parser_confidence default 0.8; flag: `ENABLE_TRUST_SCORER`
- `dedup_check.py` — P2C.7 — within-domain hash uniqueness (cross-domain allowed); flag: `ENABLE_DEDUP_CHECK`
- `repository.py` — P2C.8 — `KnowledgeRepository.insert_ingested()` audited write; hard-rail enforcement (`learning_only=True`, `eligible_for_deploy=False` regardless of item state); idempotent upsert; version stamps on every doc; flag: `UKIE_GOVERNANCE_CUTOVER` (dormant when off)
- `pipeline.py` — ordered composition; `PipelineOutcome` + `PipelineSummary` with version stamps
- `dry_run.py` — shadow-mode harness; three input sources (`items` / `last_n_from_ingestion_runs` / `synthetic_fixture`); deterministic `stage_3_beta_default` fixture covers all 6 domains + all 5 license outcomes + a hash-collision case
- `router.py` — extended with `POST /api/knowledge/dry-run`, `GET /api/knowledge/pipeline/{status,last-run}`

**Version-aware from day one** — operator's architectural
refinement: every stored doc + every outcome carries both
`pipeline_version` (implementation) and `pipeline_contract_version`
(semantics) + `processed_at`. Retro-processing and audit trails
distinguish "rerun" from "semantic shift" by design.

**Stage 3.β tests: 66 / 66 passing.** Cumulative Phase-2 tests:
**224 / 224** (Stage 1: 34 + Stage 2: 74 + Stage 3.α: 50 +
Stage 3.β: 66).

**Deliverable:** `/app/memory/PHASE_2_STAGE_3_BETA_NOTES.md` documents
implementation, evidence, dry-run results, and the pre-cutover
checklist.

**Feature flags introduced (all default OFF):**
- `ENABLE_DOMAIN_ROUTING`
- `ENABLE_DEDUP_CHECK`
- `ENABLE_LICENSE_GATE`
- `ENABLE_TRUST_SCORER`
- `UKIE_GOVERNANCE_CUTOVER` — the critical cutover; guards Mongo writes

Live verification (preview pod, `UKIE_DOMAIN_REGISTRY_ENABLED=true`,
all other flags OFF):
- `/api/knowledge/pipeline/status` reports 5 flags OFF, versions 0.1.0
- `POST /api/knowledge/dry-run` (default fixture) → 7 items, all six domains, dormant=7
- With stage flags ON (isolated test): trust distribution `T5=1, T3=3, T2=2, T1=1`; license distribution `permissive=4, strong_copyleft=1, proprietary=1, unknown=1`
- `/api/health/system` unchanged: platform_score=100 · [coe, vie, cts]

**Explicit non-goals honoured** — no promote bridge, no retro-scoring,
no new connectors, no repository read/query surface, no changes to
legacy `strategy_ingestion/*`. Stage 3.γ (promote bridge +
retro-scoring) is a separate follow-up requiring its own operator
approval.

## Phase 2 Validation Gate 3 Report (2026-02-19) ✅

- `/app/memory/PHASE_2_VALIDATION_GATE_3_REPORT.md` — comprehensive
  readiness assessment for Stage 3 (α + β). Result: **PASS**.
- Live rollback verified: all 6 UKIE flags OFF → every
  `/api/knowledge/*` endpoint returns 503; `/api/health/system`
  unchanged (platform_score=100 across coe/vie/cts).
- 224 / 224 cumulative Phase-2 tests passing.
- No Stage-3 feature flag enabled in production; awaiting operator
  sign-off on Gate 3 before coherent UKIE activation.
- Post-approval sequence documented: (1) complete Stage-2 BI5 shadow
  diff; (2) coherent UKIE activation per Gate 3 §5.1; (3) Stage 3.γ
  planning (promote bridge + retro-scoring — separate approval);
  (4) Stage 4 kickoff (connector fleet + COE γ + observability
  finalisation); (5) backend feature freeze + VPS validation windows.

## BI5 ↔ BID Shadow Validation (2026-02-19) ✅

- **Analytical convergence proven** — 27/27 tests drive both legacy
  BI5 resampler AND CTS resampler over identical M1 fixtures across
  all six timeframes (M5/M15/M30/H1/H4/D1) and multiple input
  lengths; **bit-identical OHLCV output** (float64-precision).
- **Two real bugs surfaced and fixed** by the harness:
  1. `bi5_realism._TF_TO_PANDAS` uppercase `"1H"`/`"4H"` deprecated
     in pandas 2.x → fixed to lowercase (matches CTS)
  2. CTS resampler lacked explicit trailing-partial guard → applied
     Recommendation R3 (mirrored BI5's guard) — both paths now
     agree bit-for-bit on non-power-of-timeframe M1 lengths
- **Harness delivered**: `engines/bi5_bid_diff.py` (330 lines) +
  `engines/bi5_bid_diff_router.py` (75 lines) — admin-only,
  feature-gated by `BI5_BID_DIFF_ENABLED=false` (default OFF).
  Read-only. Produces summary + per-bucket detailed audit artifact
  (JSON or CSV) with 18-column shape covering OHLCV + basis-point
  deltas + tier classification per bucket.
- **24-hour production observation runbook** documented in
  `BI5_BID_SHADOW_VALIDATION_REPORT.md §7` — pre-run checks, hourly
  curl loop, pass/fail gates, post-observation cleanup.
- **Pass criteria (operator's thresholds):** ≥ 99% of overlapping
  buckets in `informational` tier (< 10 bps) AND zero
  `governance_review` (≥ 50 bps).
- **Live-verified**: endpoint returns 503 with `BI5_BID_DIFF_ENABLED`
  off; `/api/health/system` unchanged.
- **Cumulative tests: 251 / 251 passing** (previous 224 + 27 new BI5
  diff).

## Phase 2 Stage 3.γ — Implementation Plan (planning only, 2026-02-19)

Document: `/app/memory/PHASE_2_STAGE_3_GAMMA_PLAN.md`

Scope planned (awaiting operator approval — no code will land until
sign-off):
- **P2C.9 Promote Bridge**: `POST /api/knowledge/promote/{item_id}` —
  admin + flag-gated (`UKIE_PROMOTE_BRIDGE_ENABLED`); T4+ items with
  permissive/weak_copyleft licence; dedup-checked; hard rails
  re-stamped at write-time; audit trail in
  `strategy_knowledge_base.promote_events`; per-item rollback path.
- **P2C.11 Retro-scoring**: `POST /api/knowledge/retro-score` —
  admin + flag-gated (`UKIE_RETRO_SCORE_ENABLED`) + physical
  `confirm_write` guard string; idempotent one-off backfill of ~55
  legacy `ingested_strategies` rows into
  `strategy_knowledge_base.strategies` via the Stage-3.β pipeline;
  dry-run default; per-run rollback path; ALSO gated by
  `UKIE_GOVERNANCE_CUTOVER` for the actual write (retro-scoring
  cannot bypass the governance cutover by design).
- **Non-goals**: no health-provider retrofit, no query API, no new
  connectors, no bulk auto-promote (all Stage 4).
- **Rollback SLA**: individual per-item + global `deleteMany`
  filters + flag flip — all within the 60-s platform SLA.

**All Stage-2 code changes remain feature-flagged and dormant.** Zero behaviour change until flags are enabled.

## Phase 2 Stage 3.γ — IMPLEMENTED (2026-07-20) ✅

Document: `/app/memory/PHASE_2_STAGE_3_GAMMA_NOTES.md`
Gate report: `/app/memory/PHASE_2_VALIDATION_GATE_4_REPORT.md`

Landed sequence (per operator directive):
1. **P2C.9 α** — Promote endpoint + preconditions + audit collection, dry-run only ✅
2. **P2C.9 β** — Writer + rollback endpoint (flag-gated) ✅
3. **P2C.11 α** — Retro-score runner + `retro_score_runs`, dry-run only ✅
4. **P2C.11 β** — Commit path dual-gated + rollback endpoint ✅
5. **Tests** — 38 new unit tests, all passing (24 promote + 14 retro-score) ✅
6. **Documentation** — Stage 3.γ notes complete ✅
7. **Validation Gate 4 Report** — draft submitted, PASS ✅

New files (all in `backend/legacy/engines/knowledge/`):
- `promote.py` (pure precondition checker)
- `promote_bridge.py` (writer + audit + demote)
- `promote_router.py` (endpoints)
- `retro_score.py` (batch runner + mapping + rollback)
- `retro_score_router.py` (endpoints)

Modified files:
- `repository.py` — added `retro_score_run_id` kwarg (backward-compat: None by default; no shape change to Stage-3.β write path)
- `__init__.py` — new exports
- `router.py` — mounts the two Stage-3.γ sub-routers on the same `/api/knowledge` prefix

New feature flags introduced (all default OFF):
- `UKIE_PROMOTE_BRIDGE_ENABLED` — master switch for the promote endpoints
- `UKIE_PROMOTE_DRY_RUN` — default dry-run behaviour when the master is on (default TRUE)
- `UKIE_RETRO_SCORE_ENABLED` — master switch for the retro-score endpoints

Reused pre-existing flag:
- `UKIE_GOVERNANCE_CUTOVER` — retro-score real writes require this too (dual gate)

New endpoints (all self-guard with HTTP 503 when their master flag is off):
- `POST /api/knowledge/promote/{item_id}` (+`?dry_run=0|1`)
- `POST /api/knowledge/promote/{item_id}/rollback`
- `POST /api/knowledge/retro-score`
- `POST /api/knowledge/retro-score/rollback/{run_id}`

New Mongo collections (created lazily on first write; audit-quality):
- `strategy_knowledge_base.promote_events` — every promote/demote attempt
- `strategy_knowledge_base.retro_score_runs` — every retro-score run summary + rollbacks

Cumulative UKIE + BI5 unit tests: **181 / 181 passing**
(143 prior + 38 new for Stage 3.γ).

**Every Stage-3.γ flag defaults OFF. Zero behaviour change in
production until the operator flips a flag.**

Next steps (all pending operator review of this milestone):
1. Coherent UKIE Activation (Gate 3 §13 sequence)
2. BI5 shadow 24-hour observation window
3. Stage 4 kickoff (connector fleet + COE γ + observability finalisation)

## Phase 4 Master Plan — APPROVED (2026-07-20) ✅

Document: `/app/memory/PHASE_4_MASTER_PLAN.md` (1,060 lines)

Approved scope: P4A Connector Fleet · P4B COE γ · P4C UKIE γ · P4D
Observability Finalisation. Coherent UKIE Activation DEFERRED until
post-Backend-Feature-Freeze per operator directive.

## Phase 4 P4A — Connector Fleet: IMPLEMENTED (2026-07-20) ✅

Document: `/app/memory/PHASE_4_P4A_CONNECTOR_FLEET_NOTES.md`

Landed:
- **Scaffolding (P4A.0)**: `connector_auth.py` (NoAuth / ApiKeyAuth /
  BearerAuth / OAuthClientCredentials) · `connector_retry.py`
  (RetryPolicy + 3 named policies) · `connector_health.py`
  (ConnectorState + ConnectorObserver) · `connectors/base.py`
  (AbstractConnector with retry composition + health snapshots).
- **Five connectors** (P4A.1–P4A.5): ArxivConnector, PdfConnector,
  PropFirmConnector, TradingViewConnector, InternalMongoConnector.
- **Registry**: flag-aware two-level filtering (framework switch +
  per-connector flag); legacy connectors unaffected.
- **Health endpoints**: `GET /api/knowledge/connectors/health` and
  `/api/knowledge/connectors/{name}/health` (both gate on the
  framework flag → HTTP 503 when off).

New feature flags introduced (all default OFF):
- `UKIE_CONNECTOR_FRAMEWORK_ENABLED` (master switch)
- `UKIE_CONNECTOR_ARXIV_ENABLED`
- `UKIE_CONNECTOR_PDF_ENABLED`
- `UKIE_CONNECTOR_PROPFIRM_ENABLED`
- `UKIE_CONNECTOR_TRADINGVIEW_ENABLED`
- `UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED`

Live network I/O is deferred (seed-mode default). Each connector
accepts an injectable HTTP client / DB getter — flipping a per-connector
flag with no client injected keeps behaviour byte-identical to the
seed list. Live wiring lands post-Freeze during Coherent UKIE Activation.

Cumulative unit tests: **239 / 239 passing**
(181 prior + 58 new P4A: 30 scaffolding + 28 concrete connectors).

**Every P4A flag defaults OFF. Zero production behaviour change.**

Remaining Stage-4 work (per approved plan, no activation until
Backend Feature Freeze):
- P4B — COE γ
- P4C — UKIE γ
- P4D — Observability Finalisation
- Validation Gate 5
- Backend Feature Freeze

## Phase 4 P4B — COE γ: IMPLEMENTED (2026-07-20) ✅

Document: `/app/memory/PHASE_4_P4B_COE_GAMMA_NOTES.md`

Landed as an additive `engines/coe_gamma/` package (pre-existing
orchestrator unmodified — composition via injected hooks):
- **P4B.1 Retry executor** — per-class exponential-backoff with
  policies matching plan §4.1 (market_data 5×, agent 3×, backtest 2×,
  execution 0×, monitoring/knowledge 3×, meta_learning 3×). Pass-through
  when flag off.
- **P4B.2 Dead-letter repository** — `workload_dead_letter` collection
  with record/list/get/requeue/discard/depth. Every method short-
  circuits with `flag_off` when disabled.
- **P4B.3 Work recovery** — boot-time stale in-flight sweep with
  injected requeue/dead-letter hooks; idempotent.
- **P4B.4 Provider-aware admission** — decision surface consulting an
  injected `breaker_state_lookup`; gates `agent`/`backtest` classes;
  HALF_OPEN admits with `probe=True`.
- **P4B.5 Age boost** — pure priority-delta math; env-tunable
  thresholds; returns 0.0 when flag off.
- **P4B.6 Elastic bands** — BACKTEST↔MUTATION capacity loans capped
  at 50% of donor reservation, only when donor idle + receiver above
  high-water.
- **P4B.7 Budget hard-cap** — daily USD ceiling above the pre-existing
  soft-cap; refuses `agent`/`backtest` on breach; returns headroom
  in decision object.
- **P4B.8 Operator controls** — circuit-reset + queue pause/resume with
  audit sink; each action returns a stamped `OperatorAction` row.

New endpoints (all self-guard 503 when flag off):
- `GET /api/coe/dead-letter[?class=&limit=&offset=&include_discarded=]`
- `GET /api/coe/dead-letter/depth[?class=]`
- `GET /api/coe/dead-letter/{row_id}`
- `POST /api/coe/dead-letter/{row_id}/requeue`
- `POST /api/coe/dead-letter/{row_id}/discard`
- `POST /api/coe/circuit-breaker/{provider}/reset`
- `POST /api/coe/queue/pause`
- `POST /api/coe/queue/resume`

New feature flags introduced (all default OFF):
- `COE_RETRY_ENABLED`
- `COE_DEAD_LETTER_ENABLED`
- `COE_WORK_RECOVERY_ENABLED`
- `COE_PROVIDER_AWARE_ADMISSION`
- `COE_AGE_BOOST_ENABLED`
- `COE_ELASTIC_BAND_ENABLED`
- `COE_BUDGET_HARD_CAP_ENABLED`
- `COE_OPERATOR_CONTROLS_ENABLED`

New Mongo collections (created lazily on first write):
- `workload_dead_letter` — dead-letter rows (TTL 90d to be applied
  at activation time via `engines/db_indexes.py`)
- `coe_operator_events` — operator-action audit rows

Cumulative unit tests: **275 / 275 passing**
(239 prior + 36 new P4B).

**Every P4B flag defaults OFF. Zero production behaviour change.**

Remaining Stage-4 work:
- P4C — UKIE γ
- P4D — Observability Finalisation
- Validation Gate 5
- Backend Feature Freeze

## Phase 4 P4C — UKIE γ: IMPLEMENTED (2026-07-20) ✅

Document: `/app/memory/PHASE_4_P4C_UKIE_GAMMA_NOTES.md`

Landed as additive modules inside `engines/knowledge/`
(pre-existing Stage 3.α/β/γ untouched):
- **P4C.1 Retrieval API** — `POST /api/knowledge/query`. Read-only
  ranking-aware query over `strategy_knowledge_base`. Never returns
  `content_bytes`; `content_preview` gated on domain `ai_context_policy`.
- **P4C.2 Ranking v2** — layered multipliers (trust × license ×
  recency × contested × endorsement) over base similarity.
  `strong_copyleft` / `proprietary` licences yield 0.0 (structural
  hide). Flag off → identity (base similarity byte-identical).
- **P4C.3 Lifecycle sweeper** — respects per-domain
  `default_retention_policy` (`forever` / `365d` / `180d` / `session`).
  Decay annotation for market/execution. Audit rows in
  `lifecycle_events`. Dry-run default.
- **P4C.4 Confidence evolution** — endorsement + contradiction event
  stores. Contradiction stamps `contested=true` on both KB rows.
- **P4C.5 Governance policy language** — **ADVISORY ONLY**. Rule
  engine over `promote_policies` collection. Stamps `advisory_tags`
  on KB rows. Never calls the promote bridge; Stage-3.γ per-item
  operator-approved discipline preserved.

New endpoints (all self-guard 503 when flag off):
- `POST /api/knowledge/query`
- `POST /api/knowledge/lifecycle-sweep`
- `POST /api/knowledge/endorsement`
- `POST /api/knowledge/contradiction`
- `POST /api/knowledge/governance/evaluate/{kb_id}`

New feature flags (all default OFF):
- `UKIE_QUERY_API_ENABLED`
- `UKIE_RANKING_V2_ENABLED`
- `UKIE_LIFECYCLE_SWEEP_ENABLED`
- `UKIE_CONFIDENCE_EVOLUTION_ENABLED`
- `UKIE_GOVERNANCE_POLICY_ENABLED`

New Mongo collections (created lazily on first write):
- `lifecycle_events` — retention sweep audit rows
- `knowledge_endorsement_events` — one row per endorsement
- `knowledge_contradiction_events` — one row per contradiction pair
- `promote_policies` — operator-authored policy documents

Cumulative unit tests: **302 / 302 passing**
(275 prior + 27 new P4C).

**Every P4C flag defaults OFF. Zero production behaviour change.**
**Governance never auto-promotes** — Stage-3.γ invariant preserved.

Remaining Stage-4 work:
- P4D — Observability Finalisation
- Validation Gate 5
- Backend Feature Freeze

## Phase 4 P4D — Observability Finalisation: IMPLEMENTED (2026-07-20) ✅

Document: `/app/memory/PHASE_4_P4D_OBSERVABILITY_NOTES.md`

Landed all 7 sub-milestones from PHASE_4_MASTER_PLAN §6:
- **P4D.1 UKIE health provider** — `/api/knowledge/ukie/health` (renamed post-Phase-0 to avoid collision with the Phase-1 KB probe at `/api/knowledge/health`); composes
  `ukie` block with 23 tracked flags, per-domain row counts, connector
  fleet snapshots, 24h audit-event counters.
- **P4D.2 Connector-event persistence helper** —
  `snapshot_observation_for_persistence()` serialiser (live persistence
  hook wired at activation).
- **P4D.3 Knowledge metrics** — `/api/knowledge/metrics` with per-domain
  aggregates, trust/license distributions, time-windowed counts,
  promote/retro-score summaries.
- **P4D.4/5 Dashboards + alerts** — Grafana JSON (10 panels) + 6
  Alertmanager rules (each opt-in via `ALERT_*_ENABLED`), shipped in
  `docs/observability/`.
- **P4D.6 Audit visibility** — 3 read endpoints
  (`/api/knowledge/promote-events`, `/retro-score-runs`, `/connector-events`)
  with paged filters.
- **P4D.8 Subsystem HealthSnapshot retrofits** — 5 additive `/api/<sub>/health`
  endpoints (meta-learning · mi · execution · portfolio · factory-eval).
  Pre-existing subsystem diagnostic endpoints UNTOUCHED.

10 new endpoints, all self-guard HTTP 503 when their flag is off.

New feature flags (all default OFF):
- `UKIE_HEALTH_PROVIDER_ENABLED`
- `UKIE_METRICS_ENABLED`
- `UKIE_AUDIT_VISIBILITY_ENABLED`
- `UKIE_CONNECTOR_EVENTS_PERSIST_ENABLED` (reserved for activation hook)
- 5 × `<SUB>_HEALTH_PROVIDER_ENABLED`
- 6 × `ALERT_*_ENABLED` (individual alert rules)

Cumulative unit tests: **323 / 323 passing**
(302 prior + 21 new P4D).

**Every P4D flag defaults OFF. Zero production behaviour change.**

## Stage 4 COMPLETE

All four workstreams (P4A → P4D) landed, tested, and dormant:
- P4A Connector Fleet — 58 tests
- P4B COE γ — 36 tests
- P4C UKIE γ — 27 tests
- P4D Observability Finalisation — 21 tests
- **Total Stage-4 additions: 142 new unit tests**

Cumulative Phase-2 + Stage-4 test count: **323 / 323 passing**.

Remaining before Coherent UKIE Activation:
- Validation Gate 5 (readiness assessed in P4D notes; **READY**)
- Backend Feature Freeze

## Phase 4 — Validation Gate 5: PASS (2026-07-20) ✅

Document: `/app/memory/PHASE_4_VALIDATION_GATE_5_REPORT.md`

**Verdict:** PASS (pending operator sign-off).

Cross-checked deliverables:
- **P4A** — connector fleet scaffolding + 5 concrete connectors ✅
- **P4B** — 8 COE γ components + 8 endpoints ✅
- **P4C** — retrieval + ranking v2 + lifecycle + confidence + governance (advisory) ✅
- **P4D** — UKIE health + metrics + audit visibility + 5 subsystem retrofits + dashboards + alerts ✅

Feature-flag audit: **34 Stage-4 flags verified OFF at process boot.**
Rollback SLAs: every workstream ≤ 60s per platform target.
Backward compatibility: no shape change to Stage-1..3 endpoints or Mongo collections.
Stage 3.γ safety rails: all intact (hard rails, promote discipline, legacy read-only, governance advisory-only).
Cumulative unit tests: **323 / 323 passing** (142 new Stage-4 vs target ≥ 105).

Post-Gate-5 roadmap (all pending operator approval):
- Backend Feature Freeze
- Coherent UKIE Activation (staged phase A → E per Master Plan §8.4)
- VPS deployment
- Paper broker validation
- 24-hour validation
- 72-hour validation
- Recommendation Mode
- Autonomous Mode
- Frontend implementation

**Production posture remains unchanged until explicit activation approval.**

## Backend Feature Freeze — DECLARED (2026-07-20) ✅

Document: `/app/memory/BACKEND_FEATURE_FREEZE.md`

Backend declared **FEATURE-COMPLETE** at v1.1.0-stage4
(commit `3ed832a`). Deliverables:
- **Feature inventory** — 12 subsystems (Phase 1 core + Phase 2
  stages + Phase 4 workstreams)
- **API inventory** — 71 `/api/*` routes across 18 groups
- **Database schema inventory** — 2 databases, ~9 new Stage-4
  collections (all lazy-created, dormant)
- **Feature-flag inventory** — 40+ flags catalogued; 34 Stage-4
  flags verified OFF
- **Operational runbooks** — cross-linked to prior gate reports and
  workstream notes
- **Deployment checklist** — VPS boot verification + TTL index list
- **Rollback checklist** — per-workstream + nuclear + per-data-slice
- **Validation checklist** — activation-time sanity checks
- **Known backlog** — non-blocking items carried forward
- **Production readiness assessment** — PASS across 9 dimensions;
  3 items explicitly deferred to activation (aggregator wiring,
  TTL indexes, live network clients)

Cumulative unit tests: **323 / 323 passing**.
Production posture: **all Stage-4 flags OFF, zero behaviour change**.

Post-freeze roadmap (in strict order, each pending operator approval):
1. Coherent UKIE Activation (staged phase A → E per Master Plan §8.4)
2. VPS deployment
3. Paper broker validation
4. 24-hour validation
5. 72-hour validation
6. Recommendation Mode
7. Autonomous Mode
8. Frontend implementation

Bug fixes and operational wiring are permitted between freeze and
activation without lifting the freeze.

### Session — Activation Plan v2 remediation (2026-07-20, COMPLETE)

Independent operator-review pass on `COHERENT_UKIE_ACTIVATION_PLAN.md`
identified 12 conditions. All resolved via Batches 1 + 2 + 3(a),
with Batch 4 (low-priority polish) deferred by operator direction.

Deliverables:
- **Plan v2** (`memory/COHERENT_UKIE_ACTIVATION_PLAN.md`, 681 lines) —
  preview-vs-prod scope, Phase 0 baseline, timeline table,
  Assumptions, Risk register, Appendix A seed policy, Phase E
  rewritten around native Alertmanager silences (no delivery-layer
  proxy).
- **Review Memo v2** (`memory/COHERENT_UKIE_ACTIVATION_PLAN_REVIEW.md`,
  222 lines) — finding-by-finding resolution table; verdict now
  APPROVED (no conditions).
- **Change Summary** (`memory/ACTIVATION_PLAN_V2_CHANGE_SUMMARY.md`).
- **W1 wiring** — `engines/db_indexes.py`: 5 TTL specs added for
  Stage-4 audit collections (main-DB `workload_dead_letter` +
  cross-DB loop for `strategy_knowledge_base.{lifecycle_events,
  knowledge_endorsement_events, knowledge_contradiction_events,
  connector_events}`). All target `*_dt` companion fields per the
  existing `audit_log` precedent. 5 new env overrides.
- **W2 wiring** — `engines/subsystem_health_router.py`
  auto-registers 5 retrofit providers with the central aggregator
  at module import. `engines/health/router.py::system_health()`
  now composes the async `ukie` block (omitted entirely when flag
  off — no shape change to pre-Stage-4 consumers).
- **Regression tests** — `backend/tests/test_activation_wiring_w1_w2.py`
  (8 tests, all passing). Stage-4 subset now 181/181 passing (was
  134 pre-remediation).

Freeze fully respected: no new features, no new endpoints, no new
flags, no runtime behaviour change (all Stage-4 flags remain OFF by
default).

Awaiting operator sign-off on Plan v2 §14 before Phase A start.

## Backlog (P2 / cosmetic)

- Duplicate `operation_id` warning at `legacy/api/admin.py:list_users` (30-sec fix)
- Remove accidental self-submodule pointer at repo root
  (`git rm --cached strategy-factory-canonical`)
- Optional: nightly `mongodump` cron in `factory-mongo` compose

## Test credentials — local validation (NOT production)

See `/app/memory/test_credentials.md`. Production admin credentials (unchanged from session 1):
- Email: `admin@coinnike.com`
- Password: `Tmn0SECEyDxV1KqfbHMw` — rotate after first login

---

## Frontend Design Phase — D-series complete (2026-07-20)

**All eight D-series design documents authored and approved by operator.**

Design phase is a **prerequisite for Sprint 1 code**. Backend Feature Freeze remains in effect throughout.

### Approved documents

| # | Document | Lines | Purpose |
|---|---|---|---|
| Bible v1.0 | `FRONTEND_DESIGN_BIBLE.md` | 1,072 | Original 21-section spec |
| Bible v2.0 delta | `FRONTEND_DESIGN_BIBLE_V2_DELTA.md` | 215 | Personalization + signature graphics + Copilot elevation |
| **Bible v2.1** | `FRONTEND_DESIGN_BIBLE_V2_1.md` | 946 | **Canonical**. Supersedes v1.0 + v2.0 delta |
| Study | `DESIGN_INSPIRATION_STUDY.md` | 850 | Six-product research (Mission Control · Linear · Palantir · UI/UX Pro Max) |
| Deltas | `BIBLE_V2.1_DELTAS.md` | 822 | Implementation-ready deltas from the study |
| D0 | `D0_VISUAL_LANGUAGE_EXPLORATION.md` | 443 | Concept D (50% Mission Control · 35% AI Intelligence · 15% Executive Luxury) |
| D1 | `D1_MISSION_CONTROL_VISUAL_BENCHMARK.md` | 649 | Visual system codification |
| D2 | `D2_AI_ACTIVITY_TIMELINE.md` + `D2_ADDENDUM_STORYTELLING_STANDARD.md` | 546 | Timeline + Division-voice storytelling |
| D3 | `D3_APPROVAL_CENTER.md` | 376 (patched) | Approval Center with Lineage Graph downstream chip |
| D4 | `D4_MASTER_BOT_WORKFORCE.md` | 880 | Master Bot CEO metaphor + 8-division org chart + Purpose Before Status |
| D5 | `D5_SIGNATURE_GRAPHIC_GALLERY.md` | 1,025 | G2–G8 signature graphics + Signature Frame recognisability mechanism |
| D6 | `D6_PERSONALIZATION_MODES.md` | 1,076 | Executive · Operations · Research · Developer modes + Decision Identity invariant |
| D7 | `D7_EMPTY_LOADING_ERROR_DORMANT.md` | 1,047 | State Template + 45+ authored specimens |
| D8 | `D8_SPRINT_1_EXECUTION_PLAN.md` | 888 | Sprint 1 execution architecture |

### Foundational principles (Bible v2.1 §1.4)

1. **Invisible Luxury** — craftsmanship over decoration
2. **Everything Connected** — every artefact carries lineage
3. **Progressive Disclosure** — Simple → Advanced Lens
4. **Context Never Lost** (§1.4.4) — state follows the operator across navigation
5. **State Memory** (§1.4.5) — state stays with the surface on return

### Invariants adopted (mode-orthogonal)

- **Purpose Before Status** (D4 §5.1.1) — every entity answers Why · Now · Produces · Next
- **Decision Identity** (D6 §8.1a) — truth is invariant across modes; only presentation differs
- **Signature Frame** (D5 §2) — mechanism of recognisability across all G-graphics
- **State Template** (D7 §3) — mechanism of consistency across all non-happy states

### Post-D8 gate — E-series (Experience Design Suite)

Before Sprint 1 code begins, the following experience-design documents will be authored:

- **E1** — Strategy Experience (end-to-end journey of one strategy)
- **E2** — Authentication Experience *(recommended first)*
- **E3** — First-Time User Journey
- **E4** — Daily Operator Journey
- **E5** — Cross-Module Navigation

Recommended authorship order: **E2 → E3 → E4 → E1 → E5**. Estimated timeline ~11 working days.

### Sprint 1 scope (per D8)

- Architectural foundations: workspace state store · State Memory infra · URL scheme · AppShell · design tokens · mode switcher · ⌘K palette · danger ribbon · status rail
- Primitives: `<Chip>` · `<MetricBlock>` · `<ChartTile>` · `<TableTile>` · `<PipelineStageBar>` · `<ActivityRow>` · `<WorkerCard>` · `<StateTemplate>` · `<ApprovalCard>` · `<EvidenceDrawer>` · `<LineageBar>` · `<ProvenanceTriple>` · `<SignatureFrame>` · `<DivisionCaption>` · `<KeyboardShortcut>` HUD
- Feature machinery: `<FacetBar>` · `<TimeWindowChip>` · Optimistic UI middleware · adapters for Timeline / Approvals / Factory · Mission Control aggregator
- Surfaces: Mission Control v1 · Timeline · Approval Center v1 · Master Bot Dashboard skeleton · Strategy Explorer minimal · empty states · Attention severity ordering
- Tests: Storybook (≥ 115 stories) · Playwright E2E · axe-core CI · visual regression · reduced-motion audit · keyboard walkthrough

**Total Sprint 1 effort: 142 engineer-days.** D8 recommends a 3-sprint stretch for craftsmanship.

### Sprint 1 explicit non-goals (deferred to Sprint 2+)

- Lineage Graph mode (Bible §10.2) → Sprint 2
- Pinned Preview (§7.12) → Sprint 2
- Full Master Bot Plan Contract with HITL cross-links → Sprint 2
- Full Workforce Org Chart → Sprint 2
- Copilot trace-as-UI (§24) → Sprint 3
- G3 Knowledge Graph → Sprint 3
- G5 Execution Constellation → Sprint 3
- G6 Portfolio Risk Surface → Sprint 4
- G7 Learning Evolution Timeline → Sprint 3
- Executive Briefing surface → Sprint 3
- Research Workspace surface → Sprint 3

### Next actionable steps

1. Operator review of D8.
2. Author E-series (E2 → E3 → E4 → E1 → E5).
3. Sprint 1 kick-off after E-series sign-off.

---

## E-series complete (2026-07-20) — Design phase closed

**The Experience Design Suite is complete.** Together with the D-series, the frontend design phase is now closed. The Interactive Prototype Gate (D8 §13.7) is the next step before Sprint 1 React production build.

### E-series documents

| # | Document | Lines | Signature refinement |
|---|---|---|---|
| E1 | `E1_STRATEGY_EXPERIENCE.md` | 1,419 | Strategy Passport (§6.7) |
| E2 | `E2_AUTHENTICATION_EXPERIENCE.md` | 809 | Trust Before Credentials (§9) |
| E3 | `E3_FIRST_TIME_USER_JOURNEY.md` | 834 | Progressive Confidence (§8.4) |
| E4 | `E4_DAILY_OPERATOR_JOURNEY.md` | 729 | Timeline as Handoff (§6) |
| E5 | `E5_CROSS_MODULE_NAVIGATION.md` | 830 | Rule of Predictable Return (§4.5) |

### Foundational principles adopted (Bible v2.1 §1.4)

1. Invisible Luxury
2. Everything Connected
3. Progressive Disclosure
4. Context Never Lost (§1.4.4)
5. State Memory (§1.4.5)

### Invariants codified across the design phase

- Purpose Before Status (D4 §5.1.1)
- Decision Identity (D6 §8.1a)
- Trust Before Credentials (E2 §9)
- Silent Graduation + Progressive Confidence (E3 §8.3–§8.4)
- Rule of Predictable Return (E5 §4.5)

### Total design phase artefact roster

15 documents · ~14,000 lines · zero implementation code · backend Feature Freeze respected throughout.

### Next actionable steps

1. Operator review of E5.
2. Enter **Interactive Prototype Gate** (D8 §13.7): build walkable React prototype with representative data covering every Sprint 1 surface.
3. Operator walk-through: 5 mode switches; 10-hop navigation; every empty state via fixture toggle; Progressive Confidence milestones fireable via fixture.
4. Refinements captured as D-doc / E-doc addenda before Sprint 1 code.
5. Sprint 1 kick-off per D8 §11 rollout order (146 engineer-days recommended 3-sprint stretch).

---

## Interactive Prototype Gate opened (2026-07-20)

**Design Phase closed.** Interactive Prototype Gate entered per D8 §13.7.

### P0 Prototype Blueprint delivered

📄 `/app/memory/P0_PROTOTYPE_BLUEPRINT.md` — formal contract for the prototype build.

- 6 evaluation dimensions codified with executable verification tests (Discoverability · Navigation Predictability · Cognitive Load · Interaction Rhythm · Operator Trust · Product Identity)
- Full prototype scope, directory layout, fixture strategy, technology (React + Vite + Zustand + Framer + Tailwind + Lucide + throw-away discipline)
- 6-phase build plan (~14 engineer-days single / ~7 pair)
- 4-session walk-through protocol
- Refinement Addendum protocol — every accepted refinement lands as a formal D/E-series addendum, never as in-code override
- Prototype exit criteria → Design Freeze

### Next actionable steps

1. Operator reviews and approves P0.
2. Prototype build (per P0 §8).
3. 4-session walk-through (per P0 §9).
4. Refinement addenda authored (per P0 §10).
5. Design Freeze declared (per P0 §11).
6. Sprint 1 kick-off per D8 §11 rollout order.

---

## Prototype Phase 2 — Primitives COMPLETE (2026-02-04) ✅

Backend Feature Freeze remains in effect. All work landed strictly inside
`/app/prototype/` per D8 §13.7 throw-away discipline.

### 13 new primitives shipped
Under `/app/prototype/src/primitives/`:

- Foundations: `SignatureFrame.tsx`, `DivisionCaption.tsx`, `KeyboardShortcutHUD.tsx`
- Data: `MetricBlock.tsx` (A/B/C variants), `ChartTile.tsx` (line + sparkline), `TableTile.tsx` (sortable, hover-actions, drill-through)
- Workflow: `PipelineStageBar.tsx` (8 stages × 5 states), `ActivityRow.tsx` (10 actor kinds), `WorkerCard.tsx` (5 states)
- Decision: `ApprovalCard.tsx` (3 risk levels × 6 origins)
- Evidence: `EvidenceDrawer.tsx`, `LineageBar.tsx`, `ProvenanceTriple.tsx`

Shared: `motion.ts` (Bible §6.1 presets — fadeInUp, fadeIn, drawerSlide, stagger).

### PrimitiveGallery route
- `/prototype/gallery` — single validation surface at
  `/app/prototype/src/gallery/PrimitiveGallery.tsx`.
- Five sections: **F** Foundations · **D** Data · **W** Workflow · **X** Decision · **E** Evidence, plus **S** Canonical States showcase.
- Prototype-only Inspector (`/app/prototype/src/gallery/Inspector.tsx`) with toggles for canonical state, mode, density, advanced-lens, reduced-motion, long-content.
- Inspector-only store: `/app/prototype/src/workspace-state/inspectorStore.ts`.
- Deterministic fixtures: `/app/prototype/src/gallery/fixtures.ts`.

### Acceptance criteria — all satisfied
- ✅ 13 primitives complete
- ✅ Token-only styling (nothing hardcoded outside `tokens.css`)
- ✅ Four canonical states supported via `StateTemplate`
- ✅ `data-testid` on every interactive element
- ✅ Responsive layout via CSS grid `auto-fit`
- ✅ Focus-visible ring inherited globally
- ✅ Reduced-motion honoured (media query + inspector override + `useMotionEnabled` hook)
- ✅ Successful `yarn build` (2.87s · 107KB gzipped)
- ✅ Screenshots captured across happy / loading / empty / advanced-lens / executive-cinema
- ✅ Zero React console errors (Router future-flag notices only)

### Next actionable steps
1. Prototype Phase 3 — Authentication surface (Trust Before Credentials).
2. Phase 4 — Core Surfaces (Mission Control, Timeline, Approval Center, Master Bot, Strategy Explorer).
3. Phase 5 — Cross-module wiring (Predictable Return, Facet cascade, Decision Identity).
4. Phase 6 — Fixture Debug Panel & Evaluation Harness (upgrades the current Inspector).
5. Prototype walkthrough against 6 Evaluation Dimensions → Design Freeze.
6. Sprint 1 React production implementation in `/app/frontend/` per D8 §11.

### Deferred / blocked (unchanged)
- 🟡 F-B `/api/save-strategy` origin tag — awaiting operator decision (a/b/c).
- 🟡 Operator: flip `COE_HEALTH_CONTRACT_ENABLED=true` on VPS (Phase A precondition).


---

## Scenario Presets + Prototype Phase 3 — Authentication COMPLETE (2026-02-04) ✅

Backend Feature Freeze remains in effect. All work landed strictly inside
`/app/prototype/`. `/api/save-strategy` origin tag continues deferred by
operator instruction.

### Scenario Presets (fixture-only)
- `/app/prototype/src/gallery/scenarios.ts` — 6 fixture bundles:
  Executive Morning Review · Operations Shift Burst · Research Investigation
  · Incident Response · Governance Review · Compute Pressure.
- `inspectorStore.applyScenario(key)` fans preset values into the workspace
  store (mode, density, advanced lens, kill posture) and the inspector
  (canonical state, long content). Selecting any individual toggle clears
  `scenarioKey` so operators can freely drift from a preset.
- Inspector now surfaces a **Scenario presets** section above the manual
  state controls — first-class walkthrough entry points.
- **No simulator logic** — presets are pure fixtures per user directive.

### Phase 3 — Authentication (Trust Before Credentials)
Files:
- `/app/prototype/src/workspace-state/authStore.ts` — 4 stances
  (anonymous · authenticating · authenticated · expired), fixture
  credentials `operator@coinnike.com / prototype123`, error taxonomy
  covering E2 §3.3 (empty, invalid email, wrong creds, locked, expired,
  backend down).
- `/app/prototype/src/auth/LoginScreen.tsx` — centered card inside
  persistent chrome, kill-posture pre-auth banner, 260 ms latency, focused
  password field after wrong creds.
- `/app/prototype/src/auth/UserMenu.tsx` — header disclosure with session
  meta, mode switcher, sign-out, prototype "expire session" button.
- `/app/prototype/src/auth/RequireAuth.tsx` — guard preserving `?next=`.
- `/app/prototype/src/shell/LeftRailStub.tsx` — 7 modules rendered at 40%
  opacity with lock glyphs when unauthenticated (E2 §3.1). Real routing
  arrives with Phase 4.
- `AppShell` updated: LeftRail always visible; pre-auth suppresses ⌘K
  hint & UserMenu; post-auth kill-posture triggers red danger ribbon.

### Verified flows (screenshots captured)
- 🟢 Anonymous root → redirect to `/auth/sign-in`.
- 🟢 Pre-auth chrome: locked rail, `⌘K DISABLED`, kill-posture chip visible.
- 🟢 Wrong credentials → warn-toned inline error, password refocused.
- 🟢 Invalid email → dedicated error message.
- 🟢 Locked email (`locked@coinnike.com`) → 15-minute cool-down copy.
- 🟢 Correct login → redirect to captured `next` (defaults to gallery).
- 🟢 UserMenu opens with session meta, mode switcher, sign-out.
- 🟢 "Expire session" → redirect + info-toned "Your session expired." notice.
- 🟢 Scenario presets: Executive, Incident (kill posture + danger ribbon),
     others switching mode/density/state cleanly.
- 🟢 Vite build 2.43 s · 112 KB gzipped · zero React console errors.

### Next actionable steps
1. **Phase 4 — Core Surfaces**: Mission Control · Timeline · Approval Center
   · Master Bot · Strategy Explorer (real routing in LeftRail).
2. Phase 5 — Cross-module wiring (Predictable Return, Facet cascade,
   Decision Identity, three-view Master Bot toggle).
3. Phase 6 — Fixture Debug Panel & Evaluation Harness (upgrades Inspector).
4. Prototype walkthrough against 6 Evaluation Dimensions → Design Freeze.
5. Sprint 1 React production build in `/app/frontend/` per D8 §11.

### Deferred / blocked
- 🟡 F-B `/api/save-strategy` origin tag — deferred per operator directive.
- 🟡 Operator: flip `COE_HEALTH_CONTRACT_ENABLED=true` on VPS (Phase A precondition).

### Prototype-only credentials
- Fixture email: `operator@coinnike.com`
- Fixture password: `prototype123`
- Locked-account fixture: `locked@coinnike.com`
- These credentials are inline in `authStore.ts` and never touch the
  backend. They will be removed at Design Freeze.


---

## Prototype Phase 4 — Core Surfaces COMPLETE (2026-07-20) ✅

Backend Feature Freeze remains in effect. All Phase 4 work landed inside
`/app/prototype/` per D8 §13.7 throw-away discipline.

### 6 core surfaces + shell routing
Under `/app/prototype/src/surfaces/`:
- `MissionControl.tsx` (Bible §7.11, D1 §5) — 3 KPI blocks, pipeline
  stage bar, throughput chart, activity strip, approvals summary
  chip-strip with one-click drill to Approval Center.
- `Timeline.tsx` (Bible §7.4, D2) — chronological activity stream +
  actor-kind facet chips + EvidenceDrawer per row.
- `ApprovalCenter.tsx` (Bible §7.5, D3) — risk-sorted approval grid;
  optimistic decide (approve · defer · block); resolved-strip.
- `MasterBot.tsx` (Bible §7.6, D4) — workforce org chart via
  `WorkerCard` grid + purpose-first `DivisionCaption`; kill-posture
  notice when armed.
- `StrategyExplorer.tsx` (E1) — sortable strategies table with
  status/flag chips + row-activation to passport.
- `StrategyPassport.tsx` (E1 §4, D1 §11) — full passport anatomy:
  metrics · ProvenanceTriple · LineageBar · sparkline · narrative ·
  EvidenceDrawer.

Shell + routing:
- `LeftRail.tsx` — 6 modules (mission · timeline · approvals ·
  workforce · strategies · settings) now render as `NavLink` when
  authenticated, `Lock`-glyphed stub when anonymous.
- `InspectorSheet.tsx` — floating right-side sheet hosting the
  Inspector; reachable from every authenticated surface via the header
  "◆ proto" button. Overlay dismiss + Esc-close.
- `SurfaceHeader.tsx`, `ScenarioBanner.tsx` — Purpose Before Status
  header anatomy + fixture-only scenario indicator.

### Acceptance criteria — all satisfied
- ✅ 6 surfaces wired + reachable via LeftRail
- ✅ Scenario fixtures drive presentation (no simulator)
- ✅ Global Inspector available from every surface
- ✅ Token-only styling, no hardcoded colours outside `tokens.css`
- ✅ `data-testid` on every interactive element
- ✅ Successful `yarn build` (2.47s · 122KB gzipped)
- ✅ Smoke screenshot verifies full navigation loop
- ✅ Vite build clean; zero React console errors

---

## Prototype Phase 5 — Cross-module Wiring COMPLETE (2026-07-20) ✅

Delivered the full Phase-5 navigation contract in one pass: Rule of
Predictable Return + Decision Identity + Facet Bar cascade + Master Bot
three-view toggle.

### `navigationStore` (new)
`/app/prototype/src/workspace-state/navigationStore.ts` — a single
Zustand store encoding three of the four invariants:
- **Facet plane**: `{ actor, status, risk }` shared across Timeline,
  Approval Center, and Strategy Explorer. Each surface projects the
  cascade onto its own facet axis.
- **Surface memory**: `{ [pathname]: state-slice }` keyed dictionary
  so each surface can persist arbitrary interaction state (selected
  row, resolved chips, active id, active view) across navigation.
- **Return crumb**: `{ path, label, origin, originId? }` breadcrumb
  dropped by any surface before navigating to a detail view; the
  passport reads + consumes it to render an origin-aware back button.

### Rule of Predictable Return (E5 §4.5)
- Timeline restores the last-opened row + facet on return.
- Approval Center restores resolved chips + risk facet on return.
- Strategy Explorer restores the last-active id highlight (`▸ strat-…`)
  on return.
- Passport back button reads the crumb → navigates to the exact
  origin path with copy that names it ("back to timeline" · "back to
  approvals" · "back to explorer").

### Decision Identity (D6 §8.1a)
- `workspace-state/store.ts::selectedStrategy` is the single source of
  truth for the current strategy id.
- Every cross-surface navigation to a passport calls `selectStrategy`
  first, guaranteeing the id is stable across modes/surfaces.
- Passport surfaces render two mono chips (`identity · <id>` +
  `via · <origin>`) confirming the invariant at a glance.

### Facet Bar cascade (Bible §7.4a)
- Timeline actor facet → `navigationStore.facets.actor`
- Approvals risk facet → `navigationStore.facets.risk`
- Strategy Explorer status facet → `navigationStore.facets.status`
- Each surface renders a `cascade · <axis> <value>` hint so operators
  can see the plane at a glance.

### Master Bot three-view toggle
- **Org**: original `WorkerCard` grid.
- **Purpose**: purpose-first list, alphabetised by purpose, muted
  state chip on the trailing edge. Reinforces D4 §5.1.1.
- **Status**: status-first table, sorted with error/blocked first,
  purpose intentionally muted. Reinforces Decision Identity by making
  the same workforce presentable in three ways without changing truth.
- Selected view persists in surface memory keyed by pathname.

### Evidence drawer footer action
- `EvidenceDrawer` gained an optional `footerAction` prop. Timeline
  uses it to expose "open passport · strat-###" when the selected
  event references a strategy id — closing the loop from evidence to
  Decision Identity.

### Verified flows (single end-to-end screenshot)
- 🟢 Timeline actor facet → cascade hint updates.
- 🟢 Approvals risk facet → chip narrows the grid, cascade hint
  updates.
- 🟢 Explorer status facet → status counts + row set update.
- 🟢 Approvals row → "open passport" drop-crumb → back button reads
  "BACK TO APPROVALS" + `identity · strat-014` + `via · approvals`.
- 🟢 Master Bot 3-view toggle: Org → Purpose → Status all render.
- 🟢 Vite build 2.59 s · 129KB gzipped · zero React console errors.

---

## Prototype Phase 6 — Evaluation Harness COMPLETE (2026-07-20) ✅

Dedicated Evaluation Harness route at `/prototype/eval`. Inspector
remains focused on fixtures + developer tooling per operator directive.

### `evaluationStore` (new)
`/app/prototype/src/workspace-state/evaluationStore.ts`:
- 6 dimensions × 4 criteria = **24 authored criteria** total,
  covering Discoverability · Navigation Predictability · Cognitive
  Load · Interaction Rhythm · Operator Trust · Product Identity.
- Each criterion carries `id`, `headline`, `detail`, and a
  D/E-series `reference` citation.
- Per-criterion verdict `pass · review · fail · unset`; persisted to
  `localStorage` under `sf.eval.v1`.
- `summariseDimension(d, v)` → per-dimension roll-up (verdict is
  fail-wins → review-wins → unset-wins → pass).
- `overallReadiness(v)` → 4-state readiness verdict:
  `ready · nearly · blocked · unstarted`, with headline + detail copy.

### `EvaluationHarness` surface (new)
`/app/prototype/src/surfaces/EvaluationHarness.tsx`:
- Surface header (Purpose Before Status) + session label input +
  reset / mark-all-pass controls.
- **Overall Readiness Card** (SignatureFrame · gold when READY, crit
  when BLOCKED, info when NEARLY, advisory when UNSTARTED). Shows
  headline, detail copy, and counts (pass · review · fail · unset)
  plus a `<pass>% of <total>` mono trailer.
- **Evaluation Session Summary** — six-tile grid, one tile per
  dimension. Each tile carries a verdict chip, `<pass>/<total>
  passing`, and a right-arrow anchor to the dimension section below.
- **Six dimension sections** with authored criteria, each rendered
  as a card with a 4-button verdict selector (pass · review · fail ·
  unset). Left-accent bar changes colour per verdict.
- **Walk-through notes** — persisted textarea for capturing
  refinements to author as D/E-series addenda.

### Feature-flags + discoverability
- `/prototype/eval` is guarded by `RequireAuth` per the rest of the
  authenticated shell.
- LeftRail exposes a new "EVAL" module (`ClipboardList` icon) so the
  harness is reachable during walkthrough sessions without needing to
  type the URL.

### Verified flows
- 🟢 Every criterion verdict click writes to localStorage.
- 🟢 Session summary tiles roll up dimension verdicts correctly
  (fail-wins > review-wins > unset > pass).
- 🟢 Overall readiness verdict transitions unstarted → nearly →
  ready as verdicts land; a single "fail" flips to BLOCKED.
- 🟢 `mark-all-pass` shortcut flips readiness to READY.
- 🟢 Reset restores all verdicts to unset.
- 🟢 Session label + notes persisted between reloads.

### Next actionable steps
1. Operator walk-through of the prototype using the 6-dimension
   harness at `/prototype/eval`.
2. Refinements captured in the notes textarea → authored as formal
   D-series / E-series addenda (Refinement Addendum protocol per
   P0 §10). No in-code overrides.
3. Design Freeze declaration once the harness reports READY.
4. Sprint 1 React production build in `/app/frontend/` per D8 §11.

### Deferred / blocked (unchanged)
- 🟡 F-B `/api/save-strategy` origin tag — deferred per operator directive.
- 🟡 Operator: flip `COE_HEALTH_CONTRACT_ENABLED=true` on VPS (Phase A precondition).




---

## Prototype Validation → Design Freeze v1.0 (2026-07-21) ✅

Backend Feature Freeze remains in effect throughout. Zero backend touches.

### Prototype Exit Report (P0)
- `/app/memory/P0_PROTOTYPE_EXIT_REPORT.md` — 6-dimension walkthrough of `/app/prototype` against P0 §9 exit criteria.
- **Result:** 23 / 24 PASS · 1 REVIEW · 0 FAIL (§11.4 upgraded REVIEW → PASS post-resolution).
- 15 / 15 primitives + 6 / 6 core surfaces + auth + eval-harness rendered end-to-end.
- Optimistic UI, Session Memory, Rule of Predictable Return, and 4-hop shared-facet-plane persistence all verified live.
- Zero copy defects across 10 audited surface-states (D2 Addendum).

### Pre-Freeze consistency resolution
- Single 1-line copy edit to `prototype/src/surfaces/Timeline.tsx` briefing so it accurately describes the shared-plane cascade the `navigationStore` already implements. Re-validation passed (4-hop plane persistence + Explorer independent axis).
- Non-material to design contract; logged in Freeze changelog §5.

### Design Freeze v1.0
- `/app/memory/DESIGN_FREEZE_v1.0.md` — binding design contract accepted 2026-07-21.
- `/app/memory/DESIGN_FREEZE_SUMMARY.md` — 105-line operator-facing one-pager.
- Locks Bible v2.1 + D0–D8 + E1–E5 + P0 blueprint + P0 exit report + design tokens + 15 primitives + 8 surfaces + 6 cross-surface contracts + full `data-testid` registry.
- 8 items explicitly deferred to Sprint 1 (all engineering/plumbing/diagnostic — design unchanged).
- Recommended freeze tag: `v1.1.0-design-freeze-v1` (operator to apply).

### Documentation cleanup pass
- `/app/memory/DOCUMENTATION_CLEANUP_REPORT.md` — full report of the repo-wide consistency pass.
- Resolved: missing `.env.example` files (added), stray empty `strategy-factory-canonical/` dir (removed), FRONTEND_AUDIT_AND_ROADMAP superseded banner, BACKEND_FEATURE_FREEZE + COHERENT_UKIE_ACTIVATION_PLAN status headers aligned, DESIGN_FREEZE + P0_EXIT_REPORT status headers marked ACCEPTED.
- Every governing document now references `DESIGN_FREEZE_v1.0.md`.
- Zero source-code changes.

### Sprint 1 Foundation Kickoff Plan
- `/app/memory/SPRINT_1_FOUNDATION_KICKOFF_PLAN.md` — 236-line plan with 5 milestones · 60 engineer-days · 6-week calendar recommendation.
- M1 Foundation infrastructure (11d) → M2 Primitives (15d) → M3 Feature machinery (9d) → M4 Foundation surfaces (15d) → M5 Integration + polish (10d).
- All Sprint 1 exit criteria drawn from D8 §14.
- Awaiting operator "go" before implementation begins.

### Canonical path
```
Backend Feature Freeze v1.1.0-stage4 ✅ 2026-07-20
    ├── Coherent UKIE Activation Phase A → E (operator-driven, VPS parallel track)
    └── Design Freeze v1.0 ✅ 2026-07-21
             └── Sprint 1 Foundation Kickoff (awaiting operator "go")
```



---

## Sprint 1 Foundation — COMPLETE (2026-07-21) ✅

**Milestone tags:** `v1.2.0-sprint1-{m1,m2,m3,m4,m5}` — five recovery checkpoints.
**Sprint 1 tag:** `v1.2.0-sprint1-complete` (operator to apply).

### Delivered
- **43 new files** under `/app/frontend/src/os/**` (~4 900 LoC)
- 15 primitives, 5 surfaces, 7 adapters, 5 stores, 1 gallery route
- ~200 `data-testid` attributes for QA hooks
- Real-auth code path (JWT via `POST /api/auth/login`) with fixture fallback
- Adapter-first architecture: zero direct `fetch()` from surfaces
- Backend Feature Freeze: **zero backend commits** across all 5 milestones

### Reports
- `/app/memory/SPRINT_1_M{1,2,3,4,5}_COMPLETION_REPORT.md` — per-milestone
- `/app/memory/SPRINT_1_COMPLETION_REPORT.md` — Sprint rollup + backend-integration readiness

### Deferred to Sprint 2 (documented, non-blocking)
- Master Bot Dashboard as own surface · WebSocket streaming
- Full Storybook + axe-core CI · Playwright E2E harness against yarn build
- 60-frame visual regression baseline · Legacy v01 dead-code cleanup

### Next
Backend Integration per Sprint 1 Completion Report §7.
Prerequisites: `.env` populated · v1.1.0-stage4 backend healthy · operator account seeded · CORS configured.



---

## Backend Integration Track α — COMPLETE (2026-07-21) ✅

**Recommended tag:** `v1.2.0-integration-complete`

### Milestone summary
- **2 adapters wire-verified live:** `fetchStrategies` (`GET /api/strategies`) · `authStore.login` (`POST /api/auth/login`)
- **1 adapter contract-preserved:** `commitApproval` — 404/409 collapse to OBSERVE-mode ack
- **4 adapters fixture-only under Backend Feature Freeze:** fetchWorkers · fetchPipeline · fetchTimeline · fetchApprovals — each emits single-shot `console.info` breadcrumb naming its expected endpoint and the freeze reason
- **Zero backend source-code changes** · **zero frontend behaviour changes**

### Compatibility boundary declared
The adapter layer under `/app/frontend/src/os/adapters/**` is the **official contract seam** between the Sprint 1 frontend and the Backend Feature Freeze v1.1.0-stage4 backend. Backend Activation Phases (Coherent UKIE Activation Plan) can proceed on the ops track independently — as each phase lands, the corresponding adapter breadcrumb auto-clears because `fixtureOrLive()` starts receiving live data. NO frontend changes required at activation time.

### Configuration (dev workspace only)
- `backend/.env` populated · dev-only JWT_SECRET generated · CORS locked to preview origin only
- `frontend/.env` populated · REACT_APP_BACKEND_URL = pod preview URL

### Reports
- `/app/memory/BACKEND_INTEGRATION_COMPLETION_REPORT.md` — full report + API contract matrix + adapter mappings
- `/app/memory/SPRINT_2_PLANNING.md` — 5-milestone Sprint 2 plan (N1 QA · N2 Master Bot · N3 Streaming · N4 Housekeeping · N5 Passport) · 34 engineer-days · 6-week calendar

### Roadmap update
```
Backend Feature Freeze v1.1.0-stage4 ✅ 2026-07-20
Design Freeze v1.0                    ✅ 2026-07-21
Sprint 1 Foundation (M1→M5)           ✅ 2026-07-21
Backend Integration Track α           ✅ 2026-07-21 ← CURRENT
├── Sprint 2 (frontend, N1→N5)        · queued (see SPRINT_2_PLANNING.md)
└── Backend Activation (UKIE Phase A→E) · ops-driven parallel track
```



---

## Sprint 2 — COMPLETE (2026-07-21) ✅

**Recommended tag:** `v1.3.0-sprint2-complete`

### Delivered (N1 → N5)
- **N1 QA infrastructure baseline** — Storybook 8.6 · 69 stories · axe-core `.axerc.json` waiver ledger · Playwright + axe-playwright · 4-job CI (`frontend-qa.yml`) · `check-testids.js` + `check-pr-title.js`
- **N2 Master Bot Dashboard** — `/c/masterbot` surface (identity strip · gold plan card · 5-decision log) + `masterBotAdapter.js` (fixture-only) + ⌘K palette entry
- **N3 Streaming surfaces** — `streamAdapter.js` (WSS + polling fallback) · `useStream` hook · `StreamPostmark` on Timeline · Approvals · StatusRail
- **N4 Sprint 1 latent-risk closure** — `useFocusTrap` on ⌘K palette · centralized 401 interceptor + `sf-auth-unauthorized` event · `REACT_APP_STRICT_LIVE` diagnostic flag · `Promise.allSettled` + `mc-partial-notice` boundary · legacy v01 archived to `.archive/v01/` · absolute-path splat catch-all fix (verified iter-3)
- **N5 Strategy Passport** — `/c/strategies/:id` surface with all seven sections (signature · metrics · provenance · lineage · guardrails · equity curve · backtest · approvals) · `fetchStrategy(id)` live→fixture fallback · Strategy Explorer row-click wiring

### Test evidence
- **12/12 Playwright tests passing** on `yarn build` static output
- **69 Storybook stories** rendered; 0 build errors
- **0 unwaived axe-core violations** on 3 surfaces; 1 documented `color-contrast` waiver (token layer, Design-Freeze-owned)
- **Testing agent 3-iteration cycle:** iter-1 11/12 · iter-2 caught CRITICAL regression · iter-3 7/7 clean

### Freeze compliance
- **Backend edits: 0** (v1.1.0-stage4 preserved)
- **Design token edits: 0** (v1.0 preserved)
- **5 semantic ARIA additions only** (non-visual metadata)

### Reports produced
- `/app/memory/SPRINT_2_N1_COMPLETION_REPORT.md`
- `/app/memory/SPRINT_2_N1_COMPATIBILITY_REPORT.md`
- `/app/memory/SPRINT_2_MID_REVIEW_PACKAGE.md`
- `/app/memory/SPRINT_2_COMPLETION_REPORT.md`
- `/app/memory/SPRINT_2_VPS_DEPLOYMENT_PACKAGE.md`
- `/app/memory/SPRINT_2_PRODUCTION_CANDIDATE_REPORT.md`
- `/app/test_reports/iteration_{1,2,3}.json`

### Roadmap update
```
Backend Feature Freeze v1.1.0-stage4  ✅ 2026-07-20
Design Freeze v1.0                    ✅ 2026-07-21
Sprint 1 Foundation                   ✅ 2026-07-21
Backend Integration Track α           ✅ 2026-07-21
Sprint 2 (N1 → N5)                    ✅ 2026-07-21 ← CURRENT
├── VPS deployment · single coherent  · queued
├── Production Candidate smoke tests  · queued
└── Sprint 3 planning                 · gated on VPS validation
```

### Deferred to Sprint 3
- 60-frame visual regression matrix (currently 3 baselines)
- `color-contrast` token remediation (Design Token Review)
- `@emotion/is-prop-valid` framer-motion warn
- `check-testids.js` → `@babel/parser` upgrade
- Storybook Vite migration (optional)
- Backend routers for streaming, master-bot, timeline, approvals, factory, workforce (blocked by Backend Feature Freeze — awaits Backend Activation Roadmap)


---

## Sprint 2.0 · Tail-patch (post-Legacy-Audit) — COMPLETE (2026-07-21) ✅

**Post-audit refinements landed after operator approved Option B of `SPRINT_2_LEGACY_CAPABILITY_AUDIT.md`.**

### R1/R2/R3 landed
- **R1** — 4th metric block on Mission Control: `Portfolio equity` (legacy Monitoring parity)
- **R2** — Next-tick postmark on Master Bot plan card (legacy Auto-Discovery Scheduler parity)
- **R3** — Three ⌘K palette proposals: `Propose new strategy…` · `Optimize strategy…` · `Promote to live…` — all drop `<ApprovalCard>` onto `/c/approvals` via new `features/paletteProposals.js` module-level buffer

### Validation
- **17 Playwright tests pass** (12 pre-existing + 5 new tail-refinement tests)
- **12/12 testing-agent assertions pass** on preview URL (iteration_4.json)
- **0 backend edits · 0 token edits · 0 new sidebar items · 0 new primitives**

### Docs
- `/app/memory/SPRINT_2_LEGACY_CAPABILITY_AUDIT.md` — Audit
- `/app/memory/SPRINT_2_FINAL_VALIDATION_REPORT.md` — Tail-patch validation
- `/app/test_reports/iteration_4.json` — Independent verification

### Deferred (Sprint 3 candidates newly identified)
- DEF-7 · `paletteProposals.js` buffer clear on logout
- DEF-8 · Portfolio-equity block variant='C' when 4-variant grid authorised
- DEF-9 · Refactor Master Bot next-tick postmark to reuse StreamPostmark primitive
