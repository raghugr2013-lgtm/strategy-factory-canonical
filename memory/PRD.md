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
