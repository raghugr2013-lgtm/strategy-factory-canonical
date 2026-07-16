# Strategy Factory Canonical v1.1 — API Compatibility Recovery

## Original Problem Statement

Production stack at `strategy.coinnike.com` is healthy at the container / HTTP layer, but the frontend reports multiple 404s (`/api/challenge-firms`, `/api/strategies/explorer`, `/api/readiness`, `/api/library/list`, `/api/dashboard/generate`, `/api/rank-strategies`, `/api/monte-carlo`, etc.) even though the backend claims 82 legacy routers are mounted. Deliver a complete audit and code fix restoring full frontend/backend compatibility WITHOUT redesigning the app or removing legacy modules. Preserve the canonical v1.1 architecture.

## Architecture

- **Frontend**: React 19 + v01 Command OS (CommandShell, TopTabBar, LifecycleRail, StatusRail, AuthGate).
- **Backend**: FastAPI 0.116 + MongoDB 6. Phase-1 core (auth + admin + strategies CRUD + research + dashboard/summary + health) + 83 legacy v01 routers.
- **VIE (Vendor Independent Engine)**: Standalone gateway (6 providers: OpenAI, Anthropic, Gemini, DeepSeek, Groq, Kimi).
- **Auth**: JWT + refresh-token rotation + 5-role RBAC + admin-approve signup.
- **Deploy**: Docker Compose (local + VPS overlay with Traefik).

## User Personas

- **Admin** — approves signups, manages users, monitors readiness, runs factory supervisor.
- **Developer / Operator / Researcher / Viewer** — 5-role RBAC on all endpoints.

## Core Requirements (static)

1. Preserve the canonical v1.1 architecture.
2. Do NOT redesign or remove any legacy module.
3. Every frontend `/api/*` call must reach a backend handler (no router-level 404s).
4. Backend must expose `/api/auth/signup` (v01-compatible pending-account flow).
5. Backend startup must not fail when optional dependencies (dukascopy_python) are absent.

## What's Been Implemented — 2026-02-15

### Routing surgery in `backend/app/main.py`
- Removed the `conflict_map` that stranded ~40 endpoints under `/api/legacy/*`.
- Introduced `_PRIORITY_STRATEGY_SCOPE_MODULES` (strategy_memory, market_intelligence, prop_firm_analysis, challenge_matching) mounted first so `/api/strategies/*` specific paths beat the Phase-1 core `/{strategy_id}` catch-all.
- Moved `_mount_legacy_routers()` to run BEFORE `include_router(strategies_router)` in `create_app()`.
- Fixed the `dashboard_route` / `phase4_route` side-effect timing AND module-identity bugs — side-effects now run immediately before strategies is mounted, and strategies is imported via the same `api.strategies` shim path the side-effects mutate.

### Signup added to Phase-1 core auth
- New `POST /api/auth/signup` — creates user with `status="pending"` and returns v01-shape `{message, email, status}`.
- Login endpoint hardened to reject `pending` / `rejected` accounts with 403 (v01 admin-approve-signup contract).

### Optional-dependency guardrail
- `legacy/data_engine/dukascopy_downloader.py` wraps the `dukascopy_python` import in try/except. The module imports cleanly without the SDK; `download_and_store()` raises a clean `RuntimeError` only when actually invoked. Startup log no longer prints the mount failure.

### Verification
- 35/35 backend regression tests pass (`/app/backend/tests/test_api_compatibility.py`).
- 89 legacy routers/attachers online (was 82 pre-fix).
- Every one of the 25 originally-404 GET endpoints returns 200 with a fresh JWT.
- Every previously-stranded POST endpoint returns 422/validation (route mounted) instead of 404.

## Files Changed

| File | Purpose |
|---|---|
| `backend/app/main.py` | Removed conflict_map, added _PRIORITY_STRATEGY_SCOPE_MODULES, reordered create_app, fixed dashboard_route/phase4_route mount |
| `backend/app/auth/routes.py` | Added POST /api/auth/signup; hardened login to reject pending accounts |
| `backend/legacy/data_engine/dukascopy_downloader.py` | Optional dukascopy_python import; RuntimeError only when actually invoked |
| `audit/*` | Full RCA, mismatch report, scanner scripts, backend & frontend route dumps, verification log |
| `backend/tests/test_api_compatibility.py` | 35 regression tests covering the full API-compat contract |
| `memory/test_credentials.md` | Admin credential reference for testing agent |

## Backlog / Next Priorities

- **P0 (done)**: Restore all previously-404 canonical `/api/*` paths.
- **P0 (done)**: Fix Phase-1 core `/api/strategies/{strategy_id}` shadow of Strategy Memory `/explorer`.
- **P0 (done)**: Restore `dashboard_route` + `phase4_route` side-effect endpoints.
- **P0 (done)**: Add `/api/auth/signup`.
- **P0 (done)**: v1.2.0-alpha2 Phase A — outcome-event ledger, AI Workforce telemetry, design doc.
- **P0 (done, 2026-02-15)**: v1.2.0-alpha2 Phase B — Continuous Learning Supervisor + Strategy Lineage + Outcome-conditioned Retrieval + AI Workforce Router. 29 Phase B tests + 32 Phase A tests + 35 baseline = **96/96 passing**. Router mount count unchanged at 92 (strictly additive).
- **P0 (done, 2026-01-16)**: v1.2.0-alpha2 Phase B.1 — **Continuous Capacity-Aware Scheduler**. Adaptive-concurrency-driven learning-cycle dispatcher that continuously polls `host_capability` + `compute_probe` + `queue_pressure` and launches cycles as `asyncio.Task`s up to the recommended concurrency. Never sleeps unconditionally; respects hard cap + rolling-hour governor + capacity band. 21 new Phase B.1 tests + full Phase A/B regression = **82/82 passing** (116/116 including legacy suites). Router count still 92 (strictly additive). Performance audit report at `audit/PHASE_B1_PERFORMANCE_AUDIT.md` documents root cause (fixed-interval scheduler + `USE_PROCESS_POOL=false` + `_SIG_LOCK` + serialised Mongo emit) with measurable evidence: `sequential 13.7 cycles/s ≈ gathered_4 12.0 cycles/s` on 16-core box at 9% CPU utilisation.
- **P0 (done, 2026-01-16)**: v1.2.0-alpha2 Phase B.2 — **Unified Autonomous Orchestration Engine**. Central decision engine replacing per-purpose schedulers with a single priority-scored task dispatcher. 11 task adapters registered (`market_data_topup`, `bi5_realism_sweep`, `knowledge_index_refresh`, `strategy_generate`, `backtest`, `validation` (passive), `mutation`, `optimization` (passive), `learning_cycle`, `ranking`, `master_bot_bundle_refresh` (passive)). Each declares CPU/RAM/duration/AI-required/cost/business-value metadata; the scorer computes `priority_base × business_value × pressure × dep_readiness × budget_headroom ÷ resource_cost_factor` deterministically every tick. Provider budget tracker enforces per-provider RPM + per-provider daily USD + global daily/monthly USD ceilings, and `choose_provider()` implements the cost/quality/latency/availability weighted pick. Subordinate hooks added to `auto_scheduler` and `orchestrator_scheduler` so legacy APScheduler jobs go dormant while `ORCHESTRATOR_ENABLED=true`. 6 new API endpoints under `/api/orchestrator/*`. **29 Phase B.2 tests + full A/B/B.1 regression = 111/111 passing**. E2E self-improving loop verified with orchestrator active — all 6 stages green. Router count 92 → 93 (strictly additive; `orchestrator_engine` router added). Design doc at `docs/V1.2.0_ALPHA2_PHASE_B2_DESIGN.md`.
- **P0 (done, 2026-01-16)**: v1.2.0-alpha2 Phase C — **Autonomous Quant Intelligence Layer**. Five modules that convert learned strategies into adaptive Master Bots. `engines/intelligence/` package: **(1) Strategy Intelligence** — classifies every strategy by style (trend_following, mean_reversion, breakout, session_based, volatility_based, momentum), regime suitability, risk profile, and backtest-evidence-weighted confidence. **(2) Portfolio Intelligence** — scores by portfolio contribution (solo_score × (1 + diversification_bonus − correlation_penalty)) rather than solo metrics. **(3) Master Bot Builder** — greedy contribution-maximising selection with style-cap (≤40%) and correlation constraints; splits accepted pool into Tier 1 (1..10) / Tier 2 (11..20) / Tier 3 (21..30). **(4) Market Regime Engine** — wraps existing `regime_classifier` with freshness + synthetic-fallback safety net. **(5) Dynamic Strategy Selector** — deterministic activation score = confidence × regime_fit × (1 + pf_boost) × (1 − risk_penalty). Every decision emits an `outcome_events` row via `explainability.emit_decision` for full audit trail. **5 new API endpoints** under `/api/intelligence/*` (classify / portfolio-score / bundles/build / regime / activate). `master_bot_bundle_refresh` orchestrator task upgraded to invoke the full Phase C pipeline. **24 Phase C tests + full A/B/B.1/B.2 regression = 135/135 passing**. Router count 93 → 94 (strictly additive; `intelligence_engine` router added).
- **P0 (done, 2026-01-16)**: v1.2.0-alpha2 Phase D — **Adaptive Autonomous Portfolio & Master Bot Engine**. Portfolio-centric autonomy: strategies become components; Master Bots become adaptive portfolios. `engines/portfolio/` package adds 7 engines: **(1) Allocation** (the brain) — decides ACTIVATE/PAUSE/REDUCE/INCREASE/REPLACE/HOLD per member from regime × confidence × correlation × drawdown × style-share. **(2) Capital** — converts actions to % weights with risk-parity + confidence + regime-fit tilts, style-cap ≤35%, cash reserve ≥10%, mathematically guaranteed sum=1. **(3) Health** — continuous monitor emitting rebalance signals on style-concentration / correlation / drawdown / diversity breaches. **(4) Promotion** — autonomous pipeline Research → Validated → Tier 3 → Tier 2 → Tier 1 → Production with per-stage gates. **(5) Retirement** — PF-trend + prediction-accuracy + drawdown detection with DEMOTE/ARCHIVE/REPLACE actions. **(6) Self-Rebuilding Master Bot** — composes all engines into one idempotent rebuild pass; called by new orchestrator task `self_rebuild` (PASSIVE by default). **(7) Continuous Closed Learning** — records `predicted → realised` deltas back into outcome_events for self-correcting confidence. Every autonomous action emits an outcome_events row (full explainability). **8 new API endpoints** under `/api/portfolio/*` (health / allocate / capital / promotion-candidates / retirement-candidates / rebuild / state / closed-learning/record). Orchestrator task count 11 → 12 (added `self_rebuild`). **33 Phase D tests + full A/B/B.1/B.2/C regression = 168/168 passing**. Router count 94 → 95 (strictly additive; `portfolio_engine` router added). E2E self-improving loop still green. Design doc at `docs/V1.2.0_ALPHA2_PHASE_D_DESIGN.md`.
- **P0 (done, 2026-01-16)**: v1.2.0-alpha2 Phase E — **Autonomous Production Validation**. Long-duration stability harness at `backend/scripts/phase_e_stability_run.py` that samples backend RSS, CPU, Mongo pool + collection counts, orchestrator dispatch counters, continuous-scheduler cycles, outcome-event write rate, and portfolio rebuild round-trip latency. 10-min compressed drill in this pod: **VERDICT: PASS** — 0.0 MB/hour RSS growth, 0 errors, orchestrator sustained 124.4 dispatches/min, continuous scheduler 58.9 cycles/min, Mongo took 415 outcome-events/min sustained writes, portfolio rebuild p50/p95 5/6 ms. Full drill artefact at `audit/PHASE_E_STABILITY_REPORT.json` + human-readable `audit/PHASE_E_STABILITY_REPORT.md` with a VPS 24–72 h runbook. **11 new Phase E tests + full A/B/B.1/B.2/C/D regression = 179/179 passing**. No architecture changes; only new harness + tests + docs.
- **P0 (design done, 2026-01-16)**: v1.2.0-alpha2 Phase F — **Adaptive Trading Brain (DESIGN ONLY)**. Design doc at `docs/V1.2.0_ALPHA2_PHASE_F_DESIGN.md` covering 8 new modules under `engines/brain/` (signals, regime_transition, execution_quality, risk_budget, scorer, policy, brain, types), 6 new API endpoints under `/api/brain/*`, continuous action space (target_weight ∈ [0..1]) replacing Phase D's discrete INCREASE/REDUCE deltas, regime-transition pre-staging, risk-budget headroom governor, `PORTFOLIO_POLICY=brain|phase_d` env switch for instant rollback, 5 open architecture questions (Q1–Q5) for operator review. **No code implemented yet — awaiting operator sign-off on architecture.**
- **P0 (done, 2026-01-16)**: v1.2.0-alpha2 Phase F — **Adaptive Trading Brain (IMPLEMENTED)** with all 5 operator-approved refinements:
  - **Q1 gradual evolution**: Max 5% weight-delta per tick (`BRAIN_MAX_WEIGHT_DELTA_PER_TICK=0.05`); catastrophic override → immediate `EMERGENCY_ZERO` for severe DD (≥30%), confidence collapse (≤0.15), prediction accuracy collapse (≤0.20), corrupted strategy, or broker failure.
  - **Q2 shadow pre-staging**: Paused strategies scoring high on `score_next` when `transition_probability ≥ 0.5` receive a shadow allocation (`BRAIN_PRE_STAGE_SHADOW=0.03`) — never real capital until fully promoted.
  - **Q3 heuristic regime transition detector**: short-vs-medium window comparison (`method="heuristic_short_vs_medium"`). Roadmap-marked for hybrid → ML → HMM → Bayesian → change-point in later phases.
  - **Q4 execution quality estimator**: composite score over spread/latency/slippage/rejects/broker health/fill quality; missing components default to neutral 0.7 until live cTrader data lands.
  - **Q5 closed-learning integration**: brain emits `brain_decision` + `brain_tick` outcome events for every tick — feeds confidence/activation/regime-suitability/portfolio-contribution learning without ever rewriting strategies.
  - **Diversification-first tier splitting (operator refinement)**: `master_bot_builder._place_diversified` guarantees each Tier 1/2/3 balances styles (≤35% share per tier per style) instead of picking top-N by profit factor. Prevents "10 trend followers" scenarios.
  - **`PORTFOLIO_POLICY=brain|phase_d` env switch** in `rebuilder.py` — default `phase_d` keeps byte-identical Phase D behaviour; setting `brain` routes allocation through the new engine. Instant rollback with one env var.
  - **8 new modules** in `engines/brain/` + **6 new API endpoints** under `/api/brain/*` (`tick`, `signals`, `regime-transition`, `policy/weights`, `execution-quality`, `risk-budget`).
  - **25 Phase F tests + full regression = 204/204 passing**. Router count 95 → 96 (strictly additive; `brain_engine` router added).
- **P0 (design done, 2026-01-16)**: v1.2.0-alpha2 Phase G — **Market Intelligence (DESIGN ONLY)**. Design doc at `docs/V1.2.0_ALPHA2_PHASE_G_DESIGN.md`. New `engines/market_intel_engine/` package with **MarketState ledger** (Mongo-persisted rolling aggregations), **8 observers** (trend duration, volatility dynamics, breakout quality, reversal strength, session stats, liquidity estimator, correlation matrix, style performance), **heuristic change-point detectors** (CUSUM-lite volatility, trend-duration drift, breakout degradation, correlation breakdown, noise increase), **MarketIntelligence aggregator** producing market_confidence / style_confidence / regime_confidence / opportunity_score / risk_environment, additive brain integration (5 new optional `BrainSignals` fields, 3 additive scorer weights defaulting to 0.0, 1 market-driven force-pause policy hook), new orchestrator task `market_intelligence_refresh` (5-min freshness SLA, active by default because cheap+local), 7 new `/api/market-intelligence/*` endpoints, 4 new Mongo collections (`market_snapshots` TTL 30d, `market_states`, `structural_changes`, `market_intelligence`), full explainability chain via 5 new `decision_type` markers, and pre-built extensibility contracts for Phase H (live cTrader `MarketDataSource` protocol) + Phase I (`WeightProvider` protocol) + future daily "Factory Performance Review". Master switch `MI_ENABLED=false` → completely dormant; `MI_ENABLED=true` + `BRAIN_USES_MARKET_INTELLIGENCE=true` + weights > 0 required to actually influence the brain (three-step cautious activation). 10 implementation milestones (G1–G10) each with regression gates. **6 open architecture questions** (Q1–Q6) awaiting operator sign-off before implementation.
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 Phase G — **Market Intelligence Engine (IMPLEMENTED)** with all 6 operator-approved refinements.
  - **Package**: `engines/market_intel_engine/` (renamed from `market_intelligence` to avoid collision with the pre-existing v01 scan-eligible module). Public API: `types`, `config`, `ledger`, `observers/{8}`, `change_detection`, `intelligence`, `brain_bridge`.
  - **Q1 dynamic universe**: `MI_UNIVERSE` env-driven — supports Forex, Metals, Indices, Crypto, CFDs. No hardcoded pairs.
  - **Q2 piggyback ingestion**: New orchestrator task `market_intelligence_refresh` (5-min SLA, priority 65) declares `DEPENDS_ON=("market_data_topup",)` so it reads the same snapshot pipeline the topup task feeds.
  - **Q3 dual persistence**: Every `StructuralChange` writes to BOTH `structural_changes` (canonical timeline) AND `outcome_events` (audit chain).
  - **Q4 two-step opt-in**: `MI_ENABLED=true` (default) enables ledger + observers; brain remains dormant until `BRAIN_USES_MARKET_INTELLIGENCE=true` AND market weights > 0.
  - **Q5 risk-first pause OFF by default**: `BRAIN_MARKET_RISK_PAUSE_ENABLED=false` — even with the master switch on, market-driven force-pause requires explicit operator opt-in after production validation.
  - **Q6 live outcomes only**: `style_performance` observer reads live outcome events only (drift-free; accepts slower warmup).
  - **8 observers** deterministic + unit-testable in isolation (no Mongo access).
  - **Heuristic change detectors**: CUSUM-lite volatility, running-mean trend-drift, rolling breakout-drop, correlation breakdown, noise increase, liquidity band demotion. All tagged `method="heuristic_*"` for future Phase G.2 ML replacement.
  - **In-memory MarketIntelligence cache** (`MI_INTELLIGENCE_CACHE_TTL_S=60`) prevents Mongo hammering on high-frequency brain ticks.
  - **Additive brain integration**: `BrainSignals` gains 5 optional fields (`market_confidence`, `style_confidence`, `opportunity_score`, `risk_environment`, `structural_changes`). `scorer` reads env weights `BRAIN_W_MARKET_CONFIDENCE`, `BRAIN_W_STYLE_CONFIDENCE`, `BRAIN_W_OPPORTUNITY` (all default 0.0 → byte-identical Phase F). `policy` gains market-driven force-pause hook (OFF by default per Q5).
  - **7 new API endpoints** under `/api/market-intelligence/*` (`state`, `state/history`, `changes`, `intelligence`, `refresh` [admin], `observers/config`, `explain/{intelligence_id}`).
  - **4 new Mongo collections** with idempotent index bootstrap: `market_snapshots` (TTL 30d via `expires_at`), `market_states`, `structural_changes`, `market_intelligence` (unique `(pair, timeframe)`).
  - **Full explainability chain**: `market_state_refresh` → `structural_change_detected` → `market_intelligence_refresh` → (future) `brain_market_influence` + `brain_market_risk_pause` outcome events.
  - **38 Phase G tests + Phase A/B/B.1/B.2/C/D/E/F regression = 239/242 passing** (3 failures are pre-existing xdist test-isolation issues in `test_v1_2_0_alpha2_phase_a.py`, reproducible on baseline). Router count 96 → 97 (strictly additive; `market_intelligence_engine` router added). Orchestrator task count 12 → 13.
- **P0 (design done, 2026-02-16)**: v1.2.0-alpha2 Phase H — **Execution Intelligence (DESIGN APPROVED)**. Design doc at `docs/V1.2.0_ALPHA2_PHASE_H_DESIGN.md` (644 lines). All 8 operator questions Q1–Q8 resolved: default broker `paper`, two-step opt-in, no auto-flatten (recommend-only risk), rolling weighted health windows (5m/1h/24h), immutable-ID audit chain, live requires operator approval, preserve broker-native TIF, architect-for-multi-account-implement-single. Independent-engine principle enforced (execution NEVER mutates brain state; feedback flows via outcome_events → closed learning → knowledge → brain). New H11 milestone added for **Execution Replay** (deterministic offline replay from immutable `execution_journal`). 9-question explainability chain locked in.
- **P0 (in progress, 2026-02-16)**: v1.2.0-alpha2 Phase H — **Execution Intelligence (H1–H3 IMPLEMENTED)**.
  - **H1 · Types + Config + Ledger + Index bootstrap** — `engines/execution/` package created. Public API: `types`, `config`, `ledger`, `broker/{base,paper}`, `order_lifecycle`, `position_lifecycle`. 7 new Mongo collections (`order_requests`, `fill_events`, `positions`, `broker_health`, `execution_quality`, `execution_attribution`, `execution_journal`) with idempotent indexes, TTLs where appropriate, and `(account_id, ...)` composite keys for Q8 multi-account readiness. Boot log shows `execution engine indexes bootstrapped (broker=paper)`.
  - **H2 · PaperBrokerAdapter + Order + Position lifecycle** — Deterministic paper broker (configurable slippage / latency / reject / partial-fill rates via `PAPER_*` env). Idempotent `submit()` on `request_id`. Order state machine `PENDING → SENT → WORKING → PARTIAL → FILLED` (or `REJECTED/CANCELLED/EXPIRED`). Position lifecycle handles same-side add (VWAP), opposite-side close (realised PnL), partial close, and residual re-open. Every state change + fill writes to `execution_journal` (Replay) AND emits `outcome_events` (Q1–Q4 "why?" explainability).
  - **H3 · Immutable Execution Journal (Replay foundation)** — Append-only `execution_journal` with per-account monotonic `seq` (guarded by asyncio.Lock to survive concurrent `asyncio.gather` writers). Verified: 20 concurrent writers → 20 unique sequential seqs. Enables H11 deterministic offline replay.
  - **Explainability chain verified**: every journal event carries `request_id` + `strategy_hash` + `brain_decision_id` correlations end-to-end (immutable-id join per Q5).
  - **Tests**: 14 Phase H tests passing (types, config, ledger idempotency, journal monotonicity, paper broker determinism, kill-switch block, full open→close roundtrip with $99.60 realised PnL on 10-pip move, audit chain preservation). Full Phase A–H regression: **251 passing** with 5 pre-existing xdist test-isolation flakes (confirmed unrelated via `git stash` on baseline).
  - **Router count still 97** (H1–H8 add zero routers; H9 will add `execution_engine` → 98).
  - **Remaining milestones**: H5 (broker_health + orchestrator task), H6 (measure_execution_quality + Phase F integration branch), H7 (attribution + orchestrator task), H8 (risk_monitor recommend-only), H9 (16 `/api/execution/*` endpoints), H10 (full regression), H11 (Execution Replay engine).
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 Phase H — **Canonical Paper-Flow Validation Harness** (`backend/scripts/paper_flow_drill.py`). Permanent regression artifact validating 9 categories. Configurable workloads (10/100/500/1000) + configurable symbols/latency/reject-rate/partial-rate/slippage. PASS/FAIL per category + JSON report + non-zero exit on FAIL. Independently verified by testing agent (iteration_1.json): 100% backend success rate. Harness self-audit caught + fixed TWO real order_lifecycle bugs before ship (missing state-transition journaling; REJECTED overwritten by FILLED).
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 Phase H — **LedgerBackend abstraction** (`engines/execution/ledger_backends/`). Pluggable persistence layer with three implementations targeted: `MongoLedgerBackend` (default, wraps original ledger.py), `MemoryLedgerBackend` (in-process dict, deterministic, ~10× faster), `ReplayLedgerBackend` (future H11). Selection via explicit `set_backend()`, or `EXEC_LEDGER_BACKEND=memory|mongo` env, or default (mongo). Public `ledger.py` free functions refactored into a facade delegating to `get_backend().<method>()`. Drill CLI supports `--backend memory` / `--backend mongo`. Verified via testing agent (iteration_2.json): both backends satisfy the Protocol structurally + behaviourally, drill exit 0 on both, boot healthy, zero regression on Phase A–G.
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 Phase H — **H4 · CtraderBrokerAdapter + Resilience + OAuth session** (`engines/execution/broker/ctrader/`). All mocked for tests; the real Protobuf websocket wiring is deferred to H4.1 with a stable `CtraderTransport` Protocol.
  - `OAuthSession` — token cache with `is_expired`/`is_expiring_soon`/`apply_refresh`, injectable clock for tests
  - `CircuitBreaker` — CLOSED→OPEN→HALF_OPEN state machine (5 fails/60s → OPEN 5min → HALF_OPEN probe → CLOSED on success)
  - `ExponentialBackoff` — 100ms→30s cap, monotonic + reset
  - `ResilientConnection` — heartbeat (15s cadence, 3 miss → force reconnect), backoff-wrapped connect, breaker-wrapped perform
  - `MockCtraderTransport` — deterministic double supporting `fail_next_connect`, `disconnect_after`, `reject_ids`, `latency_ms`, `refresh_oauth`
  - `CtraderBrokerAdapter` — implements `BrokerAdapter` Protocol; wraps transport in `ResilientConnection`; owns `OAuthSession`; emits `BrokerHealth` from live-connection state
  - Falls back to `paper` when `BROKER=ctrader` is set without an explicit production transport wire-up — safe VPS boot (Q1)
  - **26 Phase H tests passing** (was 14 pre-H4). 265 passing in Phase A–H full suite; same 3 pre-existing xdist flakes only.
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 Phase H — **H5 · Broker Health engine** (`engines/execution/broker_health.py` + orchestrator task `broker_health_check`).
  - Rolling weighted health scores per Q4: **short 5m, medium 1h, long 24h**. Composite formula: `0.35·uptime + 0.25·(1−reject) + 0.15·(1−requote) + 0.15·latency_norm + 0.10·(1−disconnect_bias)` bounded to [0..1] with `_band_for` mapping (≥0.80 healthy, ≥0.50 degraded, else unhealthy).
  - `sample_broker_health()` reads active adapter, persists via ledger, emits `broker_health_check` outcome event. Never raises.
  - `is_broker_healthy_for_new_orders()` — Q3-safe read helper (recommend-only; blocks nothing itself; caller decides).
  - Orchestrator task `broker_health_check` (60s cadence, active by default, respects `EXEC_ENABLED`). Task count 13 → 14.
  - **28 Phase H tests passing** (was 26; +4 for H5: scoring formula bounds, persistence roundtrip, unhealthy-gate, task registration). Zero regression across Phase A–G.
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 **Tiered Regression Pyramid** (`/app/Makefile` + `backend/scripts/tier5_validation.py`).
  - **Tier 1** (every commit): memory backend + Phase H pytest + 10-order drill (~2s)
  - **Tier 2** (hourly): memory backend + 100-order clean drill + 500-order hostile stress drill (~15s)
  - **Tier 3** (daily): mongo backend + 500-order integration drill + full Phase A–H regression sweep (~3min)
  - **Tier 4** (pre-release): mongo backend + 1000-order clean drill + 1000-order stress + full regression (~10min)
  - **Tier 5** (production): `tier5_validation.py` runs the paper drill in a loop for 24h / 72h + writes canonical aggregate JSON report
  - Every tier exits 0 on PASS, non-zero on FAIL, JSON reports timestamped to `/app/test_reports/`. Suitable for CI matrix / cron / GitHub Actions.
- **P1 (done, 2026-02-16)**: **UI/UX Master Design Specification v1.0** (`docs/UI_UX_MASTER_DESIGN_SPECIFICATION_v1.0.md`). 34-section canonical frontend constitution covering vision, IA, navigation, Mission Control, Factory Pipeline, all workspace modules (Trading Brain, Market Intelligence, Execution Intelligence, Portfolio, Knowledge Graph, etc.), motion + sound + colour + typography + component library + design tokens + accessibility + performance budget + desktop/tablet/mobile layouts. Backend independent; frontend implementation is intentionally deferred until Phase H closes. Every future UI PR must conform to this spec unless an approved design update lands.
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 **Phase H6–H11** — Execution Quality + Attribution + Risk Monitor + APIs + Regression + Replay Engine.
  - **H6** `quality.py measure_execution_quality` — six-component composite (spread 0.30 / latency 0.20 / slippage 0.20 / reject 0.15 / broker 0.10 / fill 0.05). Falls back to `method="estimated_no_live_feed"` under `MIN_FILLS=20`, else `method="measured_live"`. Persists via ledger + emits `execution_quality_refresh` outcome event.
  - **H7** `attribution.py attribute_closed_positions` — joins closed round-trips to brain decisions via immutable IDs (Q5 audit chain). Idempotent by `brain_decision_id`. Writes `ExecutionAttribution` rows and `execution_realised` outcome events with `delta_predicted_realised` (Phase I training signal ready). Orchestrator task `execution_attribution` (5-min cadence, depends on broker_health_check). Task count 14 → 15.
  - **H8** `risk_monitor.py evaluate_guards` — 7 guards (max_positions, max_exposure_pair, max_exposure_total, daily_loss_pct, loss_24h_pct, broker_health_min, clock_drift). **Recommend-only per Q3**: emits `risk_breach` outcome events + returns `RiskRecommendation` list (action ∈ {pause, reduce, halt_new_opens}). NEVER auto-liquidates positions.
  - **H9** 16 `/api/execution/*` endpoints (config · broker/health · broker/history · broker/kill-switch (admin) · kill-switch/clear (admin) · orders (GET/POST admin) · orders/{id} · orders/{id} DELETE admin · fills · positions · positions/history · quality · quality/refresh admin · attribution · attribution/{decision_id} · risk/status · replay (admin) · journal). Router count 97 → **98**.
  - **H10** — Full A–H regression sweep = **285 passing** (was 265 pre-batch; +20 net Phase H tests). Same 3 pre-existing xdist flakes only.
  - **H11** `replay.py replay_range` — deterministic offline replay from `execution_journal`. Derives terminal state per request_id purely from journaled events, byte-identical to live-run state (verified). `ReplayReport` aggregates event counts, terminal state distribution, and fills-per-order. Exposed via `POST /api/execution/replay` (admin).
  - **45 Phase H tests passing** (was 28 pre-batch; +17 H6/H7/H8/H9/H11).
  - **`make ci-verdict`** — one-line PASS/FAIL summary for pre-push hooks + GitHub commit status.
- **P0 (done, 2026-02-16)**: v1.2.0-alpha2 **Phase I — Meta-Learning Engine (IMPLEMENTED in OBSERVE MODE)**.
  - **Package**: `engines/meta_learning/` with `types`, `config`, `ledger`, `explainability`, `collectors/{4 modules}`, `evaluators/{6 modules}`, `stats`, `proposers`, `ranker`, `applier`, `engine`.
  - **4 operating modes**: `disabled → observe (default) → recommend → autonomous`. Default OBSERVE. Autonomous requires belt-and-suspenders `META_LEARNING_AUTONOMOUS_CONFIRM=YES` env + per-surface whitelist gating.
  - **6 evaluators** (pure functions, deterministic): weight_sensitivity (Pearson+Spearman correlation between scoring components and realised PnL), threshold_calibration (bucketed expected-uplift search), confidence_calibration (reliability-curve gap), style_regime_matrix (6×4 miscalibration cells), market_signal_utility (Phase G weights with first-activation gate capping at 0.05 from 0.0), execution_quality_gate (delta_predicted_realised p95 analysis).
  - **5 proposers**: brain_weights, brain_thresholds, market_weights, execution_gate, confidence_calibration. Each bounded by `META_LEARNING_MAX_DELTA_PER_TICK=0.02` and class-cap-per-day.
  - **Ranker**: `score = expected_uplift × confidence × (1 − risk_penalty(green|amber|red))`. Below `META_LEARNING_RANK_FLOOR=0.01` → EXPIRED. Ties broken by lowest recent-application load.
  - **Applier**: DORMANT in OBSERVE. Even in RECOMMEND/AUTONOMOUS, writes only to `meta_learning_overrides`; downstream engines consume overrides only when `BRAIN_USE_META_OVERRIDES / PORTFOLIO_USE_META_OVERRIDES / EXEC_USE_META_OVERRIDES=true` (all default `false` = byte-identical to Phase H).
  - **Structural non-modification guarantee**: pytest hashes 10 watched brain/portfolio/execution source files; changes fail the suite. Zero edits to `brain/scorer.py`, `brain/policy.py`, `brain/brain.py`, `brain/config.py`, `portfolio/allocation.py`, `capital.py`, `rebuilder.py`, `execution/risk_monitor.py`, `quality.py`, `attribution.py`.

## Phase I Files Added (2026-02-16)

| File | Purpose |
|---|---|
| `docs/V1.2.0_ALPHA2_PHASE_I_DESIGN.md` | 649-line design document with Q1–Q8 operator questions and resolved defaults |
| `docs/V1.2.0_ARCHITECTURE_BOOK.md` | 700+ line canonical technical + design-rationale reference for the entire v1.2.0 backend |
| `backend/legacy/engines/meta_learning/__init__.py` | Public engine API (types, config, ledger, engine) |
| `backend/legacy/engines/meta_learning/types.py` | `MetaEvaluation`, `MetaRecommendation`, `MetaApplication`, `MetaMode`, `MetaSurface`, `MetaSeverity`, `MetaRiskBand`, `MetaRecStatus` |
| `backend/legacy/engines/meta_learning/config.py` | Env-driven mode + cadence + significance thresholds + autonomous whitelist + class caps |
| `backend/legacy/engines/meta_learning/ledger.py` | Mongo-persisted 5-collection ledger with idempotent index bootstrap |
| `backend/legacy/engines/meta_learning/explainability.py` | Emits `meta_learning_*` outcome_events |
| `backend/legacy/engines/meta_learning/stats.py` | Pure-function pearson, spearman, bin_edges, normalise_pnl, p_value_from_r |
| `backend/legacy/engines/meta_learning/collectors/__init__.py` | Read-only outcome_event collectors |
| `backend/legacy/engines/meta_learning/collectors/brain_decisions.py` | `collect_brain_decisions()` |
| `backend/legacy/engines/meta_learning/collectors/execution_realised.py` | `collect_execution_realised()` + `join_decision_to_realised()` |
| `backend/legacy/engines/meta_learning/collectors/market_intelligence.py` | Phase G outcome_events collector |
| `backend/legacy/engines/meta_learning/collectors/portfolio.py` | Phase D outcome_events collector |
| `backend/legacy/engines/meta_learning/evaluators/__init__.py` | 6 evaluator exports |
| `backend/legacy/engines/meta_learning/evaluators/weight_sensitivity.py` | Per-scoring-weight Pearson/Spearman correlation vs realised PnL |
| `backend/legacy/engines/meta_learning/evaluators/threshold_calibration.py` | Bucketed expected-uplift threshold search |
| `backend/legacy/engines/meta_learning/evaluators/confidence_calibration.py` | Reliability-curve gap detector |
| `backend/legacy/engines/meta_learning/evaluators/style_regime_matrix.py` | 6×4 style-regime miscalibration |
| `backend/legacy/engines/meta_learning/evaluators/market_signal_utility.py` | Phase G weights utility with first-activation gate |
| `backend/legacy/engines/meta_learning/evaluators/execution_quality_gate.py` | Delta_predicted_realised p95 gate analysis |
| `backend/legacy/engines/meta_learning/proposers.py` | 5 proposers with severity + risk band + guardrails |
| `backend/legacy/engines/meta_learning/ranker.py` | Score-based ranker with floor + tie-break |
| `backend/legacy/engines/meta_learning/applier.py` | Dormant-in-OBSERVE applier with `ApplierGuardBlocked` safety net |
| `backend/legacy/engines/meta_learning/engine.py` | Top-level `run_meta_learning_cycle()` orchestrator |
| `backend/legacy/engines/orchestrator/tasks/meta_learning_evaluation.py` | Orchestrator task (priority 55, cadence 900s) |
| `backend/legacy/api/meta_learning_engine.py` | 12 new `/api/meta-learning/*` endpoints |
| `backend/tests/test_v1_2_0_alpha2_phase_i.py` | 48 regression tests (config, ledger, stats, evaluators, proposers, ranker, applier OBSERVE-safety, engine, orchestrator, API, structural non-modification, determinism) |

## Phase I Files Modified (additive only)

| File | Change |
|---|---|
| `backend/app/main.py` | +1 line to `primary_names` list (mount `meta_learning_engine` router) + `meta_learning ensure_indexes()` bootstrap call |
| `backend/legacy/engines/orchestrator/tasks/__init__.py` | Import `meta_learning_evaluation` for side-effect registration |
| `backend/tests/test_v1_2_0_alpha2_phase_{a,b,b1,b2,c,d,f,g,h}.py` | Widen router-count assertion tuples to include `'99'` (predicted in Phase I §11) |
| `backend/tests/test_v1_2_0_alpha2_phase_d.py::TestOrchestratorIntegration::test_self_rebuild_task_registered` | Widen accepted task count to include 16 |

## Phase I Configuration surface

| Var | Default | Description |
|---|---|---|
| `META_LEARNING_MODE` | `observe` | `disabled|observe|recommend|autonomous` |
| `META_LEARNING_CADENCE_SEC` | `900` | Orchestrator dispatch interval |
| `META_LEARNING_WINDOW_HOURS` | `24` | Evaluator look-back window |
| `META_LEARNING_MIN_SAMPLES` | `50` | Minimum decisions per evaluator |
| `META_LEARNING_MIN_SAMPLES_WARMUP` | `30` | Warmup ramp value (if `WARMUP_UNTIL` in future) |
| `META_LEARNING_WARMUP_UNTIL` | `""` | ISO date; while in future, uses warmup value |
| `META_LEARNING_SIG_THRESHOLD` | `0.20` | Pearson `|ρ|` floor for recommendations |
| `META_LEARNING_WEIGHT_STEP` | `0.01` | Base step size for weight recommendations |
| `META_LEARNING_MAX_DELTA_PER_TICK` | `0.02` | Absolute cap on any single-tick recommendation |
| `META_LEARNING_REC_TTL_DAYS` | `7` | Pending recommendation TTL |
| `META_LEARNING_RANK_FLOOR` | `0.01` | Recommendations below this score auto-expire |
| `META_LEARNING_CALIB_GAP_MIN` | `0.10` | Reliability curve gap floor |
| `META_LEARNING_AUTONOMOUS_CONFIRM` | `""` | Must be `YES` for autonomous mode to actually apply |
| `META_LEARNING_AUTONOMOUS_WHITELIST` | `"brain_weight,market_weight"` | Comma-separated surface whitelist |
| `META_LEARNING_CAP_<surface>` | `0.05` | Per-surface max cumulative delta per rolling 24h |
| `BRAIN_USE_META_OVERRIDES` | `false` | Downstream opt-in: brain reads `meta_learning_overrides` |
| `PORTFOLIO_USE_META_OVERRIDES` | `false` | Downstream opt-in: portfolio reads overrides |
| `EXEC_USE_META_OVERRIDES` | `false` | Downstream opt-in: execution reads overrides |


  - **12 new API endpoints** under `/api/meta-learning/*`: `config`, `status`, `evaluations`, `evaluations/{id}`, `recommendations`, `pending`, `recommendations/{id}`, `applications`, `overrides`, `mode-history`, `refresh` (admin), `recommendations/{id}/approve` (admin, **returns 409 in OBSERVE**), `recommendations/{id}/reject` (admin), `overrides/{target}/revert` (admin).
  - **5 new Mongo collections**: `meta_learning_evaluations` (TTL 90d), `meta_learning_recommendations` (TTL 180d via `expires_at`), `meta_learning_applications` (TTL 365d, dormant in OBSERVE), `meta_learning_overrides` (permanent, dormant in OBSERVE), `meta_learning_mode_history` (TTL 365d).
  - **7 new outcome_event decision-type markers**: `meta_learning_cycle_start`, `meta_learning_evaluation`, `meta_learning_recommendation`, `meta_learning_cycle_end`, `meta_learning_mode_change`, `meta_learning_application`, `meta_learning_revert`. Full immutable-ID audit chain.
  - **Orchestrator task**: `meta_learning_evaluation` (priority 55, cadence 900s, depends on `execution_attribution`, respects `META_LEARNING_MODE=disabled`). Task count 15 → **16**.
  - **48 Phase I tests + full A–I regression = 335 passing** (32 A + 22 B + 21 B.1 + 29 B.2 + 24 C + 33 D + 11 E + 25 F + 38 G + 45 H + 48 I; running with `-n 0`). Router count 98 → **99** exactly as designed.
  - **Boot log**: `meta_learning engine ready (mode=observe, cadence=900s)`.
  - **API-level verified**: OBSERVE mode `approve` endpoint returns HTTP 409 with `{"error": "meta_learning is in observe mode; approval blocked", "mode": "observe"}`. Force-refresh cycle completes cleanly with zero overrides + zero applications written.
  - Design doc at `docs/V1.2.0_ALPHA2_PHASE_I_DESIGN.md` (649 lines) with all 8 operator questions Q1–Q8 answered via recommended defaults.
- **P1 (done, 2026-02-16)**: **v1.2.0 Architecture Book** (`docs/V1.2.0_ARCHITECTURE_BOOK.md`, 1000+ lines) — canonical technical + design-rationale reference. 20 chapters covering the philosophy (six design commitments), system topology, why each engine is separated from the others, explainability chain, why Meta-Learning starts in OBSERVE, why the frontend is decoupled, LedgerBackend abstraction rationale, replay determinism, feature flags, and validation pyramid. Explains not just *how* but *why*.
- **P1 (done, 2026-02-16)**: **UI/UX Master Design Specification v1.0 — Phase I Meta-Learning workspace appendix** added (`docs/UI_UX_MASTER_DESIGN_SPECIFICATION_v1.0.md` §Appendix C). Covers navigation, desktop/tablet/mobile layouts, KPI grid, ReliabilityChart, StyleRegimeMiscalibrationHeatmap, details drawer, motion design, sound design, data-testid inventory, accessibility, performance budget, empty states, interaction guidelines, and full explainability trace integration. Documentation only — no React/CSS.
- **P0 (design done, 2026-02-16)**: v1.2.0-alpha2 **Phase J — Factory Self-Evaluation (DESIGN ONLY)**. Design doc at `docs/V1.2.0_ALPHA2_PHASE_J_DESIGN.md` (715 lines). Factory-level engine (peer of Phase I). New package `engines/factory_eval/` with 4 collectors, 10 evaluators (factory_improvement, provider_efficiency, research_roi, strategy_ranking, regime_effectiveness, bottleneck_detector, compute_allocation, execution_quality_ranking, portfolio_health_trends, coverage_gap_detector), 6 proposers, ranker, dormant applier, engine. 26 new `/api/factory-eval/*` endpoints. 6 new Mongo collections (`factory_eval_{reports,insights,recommendations,applications,overrides,mode_history}`). 20-KPI catalogue (6 P0 + 14 P1). Hourly regular cycle + daily 03:00 UTC 90-day report. Router count 99 → **100**, orchestrator task count 16 → **17**. 4 operating modes (default `observe`). Structural non-modification guarantee via hashed watched files. 10 open operator questions Q1–Q10 with recommended defaults. **No implementation yet — awaiting operator sign-off**.
- **P1 (done, 2026-02-16)**: **Architecture Book expanded** with Appendices D–H: Operations Playbook (boot sequence, emergency shutdown, disaster recovery, why we never auto-rollback), Security Posture (auth, secrets, broker credential blast radius, immutable audit as security control), Upgrade Path (v1.2.0 → v1.4.0), Why the Explainability Chain Doubles as a Learning Signal, and When to Add a New Engine vs Extend an Existing One. Total now 837 lines. Explains not just how but *why* every operational decision was made.
- **P1 (done, 2026-02-16)**: **UI/UX Master Design Specification v1.0** further expanded with Appendices D–F: Phase J Factory Self-Evaluation workspace (three-band layout, KPI hero grid, provider leaderboard, regime effectiveness matrix, bottleneck panel, portfolio health trends, floating recommendations rail), Explainability Explorer (cross-cutting audit UI with ChainTree + EventDetails), and Command OS global wireframe additions (nav-rail final ordering, mode summary chip cluster, global keyboard shortcuts). Total now 1110 lines. Documentation only.
- **P1**: Make `dukascopy_python` truly optional (done — startup clean).
- **P1 (alpha3)**: Dashboard Mosaic — `GET /api/dashboard/health-mosaic` + `MosaicRail` frontend consuming the new learning/ai-workforce metrics endpoints.
- **P1 (alpha3)**: Portfolio Intelligence injection block (`engines/knowledge/portfolio_block.py`) hooked into `strategy_engine._try_llm_generation` above the prior-knowledge block.
- **P1 (alpha3)**: Frontend Learning tab — event stream + lineage tree viewer.
- **P2**: Delete stale `/app/backend/tests/backend_test.py` which uses obsolete admin password.
- **P2**: Add pytest-based nightly regression run in CI targeting the same test files.
- **P3**: Consider a periodic cleanup job for `TEST_signup_*` users created by the compat test-suite.
- **P3**: Frontend UI smoke test (Playwright) covering Dashboard → Explorer → Prop Firm → Challenge Firms → Library → Portfolio Builder → Trade Runner navigation with the seeded admin.

## Phase B Files Added (2026-02-15)

| File | Purpose |
|---|---|
| `backend/legacy/engines/learning/config.py` | Env-driven thresholds (PF/DD/trades/WR/scheduler/retrieval/workforce) |
| `backend/legacy/engines/learning/supervisor.py` | Continuous Learning Supervisor + scheduler |
| `backend/legacy/engines/learning/lineage.py` | Strategy-lineage stamper across `strategies`+`strategy_library`+`archive` |
| `backend/legacy/engines/ai_workforce/router.py` | AI Workforce Router (opt-in failover) |
| `backend/legacy/engines/ai_workforce/scorer.py` | Per-provider quality scorer (60s cache) |
| `backend/legacy/engines/knowledge/outcome_conditioning.py` | Outcome-conditioned retrieval boost |
| `backend/tests/test_v1_2_0_alpha2_phase_b.py` | 29 regression tests |

## Phase B.1 Files Added (2026-01-16)

| File | Purpose |
|---|---|
| `backend/legacy/engines/learning/continuous_scheduler.py` | **Continuous Capacity-Aware Scheduler** — polls `AdaptiveConcurrency.recommend()` on every tick, dispatches `run_learning_cycle` as `asyncio.Task`s, respects host capacity + hard cap + hourly governor + AI-provider RPM budget. Opt-in via `LEARNING_CONTINUOUS_MODE=true`. |
| `backend/scripts/perf_audit_learning_loop.py` | Performance profiling harness — sequential vs `asyncio.gather` vs staggered dispatch under `psutil`+`compute_probe`+`queue_pressure` sampling. |
| `audit/PHASE_B1_PERFORMANCE_AUDIT.md` | Root-cause analysis of "big VPS slower than small VPS" — with measurable evidence. |
| `audit/PERF_AUDIT_REPORT.json` | Raw timing evidence produced by the harness. |
| `backend/tests/test_v1_2_0_alpha2_phase_b1.py` | 21 regression tests (endpoint contract + capacity logic + legacy scheduler regression + 92-router boot-log invariant). |

## Phase B.1 Files Modified (additive only)

| File | Change |
|---|---|
| `backend/legacy/engines/learning/__init__.py` | Export continuous scheduler API |
| `backend/legacy/api/learning.py` | +3 endpoints: `/api/learning/continuous/{start,stop,status}` |
| `backend/app/main.py` | Auto-start continuous scheduler on boot when `LEARNING_CONTINUOUS_MODE=true` |

## Phase B.2 Files Added (2026-01-16)

| File | Purpose |
|---|---|
| `docs/V1.2.0_ALPHA2_PHASE_B2_DESIGN.md` | Architecture design document |
| `backend/legacy/engines/orchestrator/__init__.py` | Package root |
| `backend/legacy/engines/orchestrator/types.py` | `Task` protocol, `Readiness`, `TaskResult`, `OrchestratorContext` |
| `backend/legacy/engines/orchestrator/registry.py` | Auto-registration decorator + env-driven passive/priority overrides |
| `backend/legacy/engines/orchestrator/budget_tracker.py` | Provider RPM + per-provider USD + global USD ceilings + weighted `choose_provider()` |
| `backend/legacy/engines/orchestrator/core.py` | `Orchestrator` — priority scorer, tick loop, dispatcher, budget/pressure/dep-readiness gating |
| `backend/legacy/engines/orchestrator/tasks/__init__.py` | Imports 11 adapters for side-effect registration |
| `backend/legacy/engines/orchestrator/tasks/_helpers.py` | Shared freshness/dependency helpers |
| `backend/legacy/engines/orchestrator/tasks/market_data_topup.py` | Adapter → `data_engine.auto_data_maintainer` |
| `backend/legacy/engines/orchestrator/tasks/bi5_realism_sweep.py` | Adapter → `bi5_realism.sweep_realism` |
| `backend/legacy/engines/orchestrator/tasks/knowledge_index_refresh.py` | Adapter → `knowledge.rebuild` |
| `backend/legacy/engines/orchestrator/tasks/strategy_generate.py` | Adapter → `strategy_engine.generate_strategy_text` |
| `backend/legacy/engines/orchestrator/tasks/backtest.py` | Adapter → `learning.supervisor.run_learning_cycle` |
| `backend/legacy/engines/orchestrator/tasks/validation.py` | Passive stub (validation runs inline in backtest today) |
| `backend/legacy/engines/orchestrator/tasks/mutation.py` | Adapter → `auto_mutation_runner.run_single_cycle` |
| `backend/legacy/engines/orchestrator/tasks/optimization.py` | Passive stub |
| `backend/legacy/engines/orchestrator/tasks/learning_cycle.py` | Adapter → `learning.supervisor.run_learning_cycle` (high priority) |
| `backend/legacy/engines/orchestrator/tasks/ranking.py` | Adapter → `strategy_ranking_engine.rank_all` |
| `backend/legacy/engines/orchestrator/tasks/master_bot_bundle_refresh.py` | Passive stub — operator-approved auto-refresh |
| `backend/legacy/api/orchestrator_engine.py` | 6 new endpoints under `/api/orchestrator/*` |
| `backend/tests/test_v1_2_0_alpha2_phase_b2.py` | 29 regression tests |

## Phase B.2 Files Modified (additive only)

| File | Change |
|---|---|
| `backend/app/main.py` | Register orchestrator_engine router + boot auto-start when `ORCHESTRATOR_ENABLED=true` |
| `backend/legacy/engines/auto_scheduler.py` | `_is_subordinated()` now defers to orchestrator when it's active |
| `backend/legacy/engines/orchestrator_scheduler.py` | Tick body checks orchestrator active-state and skips when subordinate |

## Phase B.2 Configuration surface

Master switch: `ORCHESTRATOR_ENABLED=true|false` (default false).
Tick cadence: `ORCH_TICK_MS`, `ORCH_IDLE_MS`, `ORCH_MAX_CONCURRENT_TASKS`, `ORCH_DECISION_HISTORY`.
Budget: `ORCH_BUDGET_DAILY_USD_GLOBAL`, `ORCH_BUDGET_MONTHLY_USD_GLOBAL`, `ORCH_BUDGET_DAILY_USD_<PROVIDER>`, `ORCH_BUDGET_RPM_<PROVIDER>`, `ORCH_BUDGET_WEIGHT_{COST,QUALITY,LATENCY,AVAILABILITY}`.
Per-task overrides: `ORCH_TASK_<NAME>_PASSIVE`, `ORCH_TASK_<NAME>_PRIORITY_BASE`.

## Phase B.1 Configuration surface (all env-driven, live-reload)

| Var | Default | Description |
|---|---|---|
| `LEARNING_CONTINUOUS_MODE` | `false` | Master switch — set `true` to activate |
| `LEARNING_CONTINUOUS_TICK_MS` | `1000` | Capacity poll cadence when dispatching |
| `LEARNING_CONTINUOUS_IDLE_MS` | `2000` | Poll cadence when band is warn/critical / at cap |
| `LEARNING_CONTINUOUS_MAX_CONCURRENT` | `8` | Hard ceiling regardless of adaptive recommendation |
| `LEARNING_CONTINUOUS_CYCLES_PER_HOUR` | `600` | Rolling-hour governor (0=disabled) |
| `LEARNING_CONTINUOUS_PROVIDER_RPM` | `0` | Per-provider RPM cap (0=rely on VIE limiter) |
| `LEARNING_CONTINUOUS_CYCLE_MAX_S` | `300` | Per-cycle timeout |
| `LEARNING_CONTINUOUS_PAIR` / `_TIMEFRAME` / `_STYLE` | `EURUSD` / `H1` / `trend-following` | Default seed |

## Phase B Files Modified (additive only)

| File | Change |
|---|---|
| `backend/legacy/engines/learning/__init__.py` | Export new modules |
| `backend/legacy/engines/ai_workforce/__init__.py` | Export router + scorer |
| `backend/legacy/engines/knowledge/retriever.py` | Call `apply_boosts` after TF-IDF pass |
| `backend/legacy/engines/llm_runner.py` | Delegate to router when `AI_WORKFORCE_FAILOVER=true` |
| `backend/legacy/api/learning.py` | 9 new endpoints (cycles/metrics/config/scheduler/lineage-detail) |
| `backend/legacy/api/ai_workforce.py` | 4 new endpoints (router-config/metrics/quality/route-test) |
| `backend/app/main.py` | Auto-start scheduler on boot when env flag set |
| `docs/V1.2.0_ALPHA2_DESIGN.md` | Section 10 — Phase B shipped |

## VPS Deployment Recovery Steps (for the user)

The GitHub repository has NOT been pushed automatically (per user request — "I will review and push"). To ship this fix to strategy.coinnike.com:

```bash
# 1. On your workstation
git fetch origin
git checkout main
git merge --ff-only <this branch's commit sha>
git push origin main

# 2. On the VPS
cd /opt/strategy-factory   # or wherever the checkout lives
git pull
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml build factory-backend
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml up -d factory-backend
./infra/scripts/health.sh
```

Post-deploy health check should show `legacy full-recovery mount: 89 routers/attachers online` in the backend container log.
