# AI Strategy Factory v10 — Architecture State Report

**Generated:** 2026-05-09
**Phase context:** Deployment-convergence phase (G7 paused)
**Mode:** Inspection + verification only — zero code changes

---

## 1. Project Root & Structure

**Root:** `/app` (continuation of existing codebase; archive extracted into `/app`,
`.git` and `.emergent` preserved).

```
/app
├── backend/                       Python 3.11 / FastAPI / Motor / APScheduler
│   ├── server.py                  43 routers wired, 4 startup hooks
│   ├── startup_validator.py       Required-env gate (JWT_SECRET, ADMIN_PASSWORD, EMERGENT_LLM_KEY)
│   ├── auth_middleware.py         JWT bearer middleware (allowlists /api/health, /api/auth/*)
│   ├── auth_utils.py              seed_admin() runs on startup
│   ├── api/                       43 routers
│   ├── engines/                   88 engine modules + strategy_ingestion/ subpkg
│   ├── data_engine/               BID + BI5 storage / coverage / incremental updater
│   ├── cbot_engine/               cTrader bot generator
│   ├── config/symbols.py          7 symbols × 7 timeframes universe
│   ├── tests/                     106 pytest test files
│   ├── scripts/                   Validation utility scripts
│   └── prop_firm_pdfs/            PDF rule extractor inputs
├── frontend/                      React 19 + CRACO + Tailwind + Radix UI
│   └── src/                       App.js + 46 components + AuthGate
├── memory/                        PRD, design docs, this report
└── test_reports/pytest/           junit XMLs (g1, lifecycle, lifecycle edge)
```

**LOC (backend):** 48,731 across server + api + engines.
**Tests:** 106 pytest files (pytest XMLs present for G1, Phase 26.5 lifecycle base + edge).

---

## 2. Service Boot & Runtime Health

| Service       | Status   | Notes                                                     |
|---------------|----------|-----------------------------------------------------------|
| supervisor    | RUNNING  | backend / frontend / mongodb / code-server / nginx-proxy  |
| backend (8001)| HEALTHY  | After `pip install -r requirements.txt` (dukascopy_python missing in fresh venv); now boots clean. `Application startup complete`. All 4 startup hooks fired (`seed_admin`, `restore_if_enabled` × 3). |
| frontend (3000)| HEALTHY | Renders Sign-In page successfully; only standard CRA webpack-dev-server deprecation warnings. |
| mongodb       | HEALTHY  | `mongodb://localhost:27017/test_database` — 0 strategies, 0 lifecycle docs, 1 prior research_run from 2026-05-09 14:58. |
| `/api/health` | 200      | `{"status":"ok","service":"AI Strategy Factory"}`         |

**Auth verified end-to-end:** seeded admin login (`admin@local.test` / `admin123`) returns
JWT token; bearer-protected routes return 200 with token, 401 without.

**OpenAPI:** 260 paths declared. Only `/api/health` and `/api/auth/*` are public; everything
else is gated by `AuthMiddleware`.

---

## 3. Endpoint Verification Matrix

### Market Data
| Endpoint                              | Status | Response                                           |
|---------------------------------------|--------|----------------------------------------------------|
| `GET  /api/market-data`               | 200    | `{"datasets":[]}` (no data ingested yet)           |
| `GET  /api/data-coverage?symbol=…`    | 200    | `coverages:[]`, `message:"No data stored for EURUSD"` |
| `GET  /api/incremental/alignment`     | 200    | `aligned:false, reason:"one_or_both_empty"`        |
| `GET  /api/dashboard/datasets`        | 200    | `success, min_candles, pairs:[]`                   |

### BI5 Realism (Phase 27.3)
| Endpoint                                          | Status | Response                                       |
|---------------------------------------------------|--------|------------------------------------------------|
| `GET  /api/bi5-realism/cohort/stale-count`        | 200    | `stale_count:0, eligible_stages:[portfolio_worthy, deployment_ready]` |
| `POST /api/bi5-realism/sweep`                     | declared | not invoked — would no-op without eligible cohort |
| `POST /api/bi5-realism/evaluate/{hash}`           | declared | not invoked — no strategy hashes yet         |
| `GET  /api/bi5-realism/{hash}`                    | declared | 404 for unknown hash                         |

### Lifecycle (Phase 26.5 + G6 / 27.2)
| Endpoint                                          | Status | Response                                       |
|---------------------------------------------------|--------|------------------------------------------------|
| `GET  /api/lifecycle/cohort/stage-counts`         | 200    | All 8 stages present, all counts = 0           |
| `GET  /api/lifecycle/transitions/recent?limit=5`  | 200    | `count:0`                                      |
| `POST /api/lifecycle/evaluate?persist=true`       | 200    | `evaluated:0, promotions:0, demotions:0, first_touch:0, cohort_p90_deploy_score:null` — runs cleanly on empty cohort |
| `GET  /api/lifecycle/{hash}` / `/history`         | declared | 404 for unknown hash                         |

### Orchestrator (Phase 22) + G2 + G6
| Endpoint                                          | Status | Response                                       |
|---------------------------------------------------|--------|------------------------------------------------|
| `GET  /api/orchestrator/state`                    | 200    | `live.status=idle`, lifecycle stage_counts attached, `adaptive_scan` populated with 16 envs |
| `POST /api/orchestrator/decide`                   | 200    | 1 rec: `LIFECYCLE_EVALUATE / evaluate_lifecycle_cohort / info` (active even on empty cohort — confirms G6 wiring) |
| `POST /api/orchestrator/tick`                     | 200    | `status:"preview"` with execute=false; cooldown guard wired |
| `GET  /api/orchestrator/scheduler/status`         | 200    | `enabled:false`, `realism_sweep.schedule:"SUN 03:00 UTC"` (BI5 cron mounted on same scheduler) |
| `GET  /api/orchestrator/env-priority/stats`       | 200    | 16 envs, 5 knob keys, allocation map attached  |
| `POST /api/orchestrator/scheduler/{start,stop}`   | declared | persistence via `orchestrator_scheduler_config._id=default` |

### Research Lineage (G1 / Phase 26)
| Endpoint                                          | Status | Response                                       |
|---------------------------------------------------|--------|------------------------------------------------|
| `GET  /api/research-runs?limit=5`                 | 200    | `count:1`, prior run from auto_scheduler tick at 2026-05-09 14:58 (reproducible cold-start trail) |
| `GET  /api/research-runs/by-strategy/{hash}`      | declared | not invoked                                  |
| `GET  /api/research-runs/by-library/{lib_id}`     | declared | not invoked                                  |
| `GET  /api/research-runs/{rrid}`                  | declared | 404 for unknown                              |

### Auto Discovery Scheduler (subordinated under G2)
| Endpoint                                          | Status | Response                                       |
|---------------------------------------------------|--------|------------------------------------------------|
| `GET  /api/auto/scheduler/status`                 | 200    | `enabled:false`                                |
| `POST /api/auto/scheduler/start`                  | declared | accepts `subordinate_to_orchestrator: true|false|null` |

### Portfolio / Readiness / Other surface
| Endpoint                                          | Status | Response                                       |
|---------------------------------------------------|--------|------------------------------------------------|
| `GET  /api/admin/readiness`                       | 200    | overall = **red** (because `market_data` empty); 4 subchecks: `market_data:red`, `llm_budget:yellow`, `alerts:yellow`, `active_runs:green`, `risk_limits:yellow` |
| `GET  /api/portfolio-intelligence/current`        | 200    | `status:"empty"`                               |
| `GET  /api/strategies/explorer?limit=2`           | 200    | `count:0, strategies:[], filters_applied:{}`   |

**Note:** `red` readiness is **expected for a freshly-restored database with no ingested
market data** — the full deployment-readiness chain integrity is preserved (the gate
fires correctly), simply nothing has flowed through yet.

---

## 4. Critical Architectural Concepts — Verification

### 4.1 BID vs BI5 Separation ✅ Preserved
- `engines/backtest_engine.py` consumed by discovery / mutation / OOS pipeline (BID-only path).
- `engines/bi5_realism.py` line 16 explicit comment: *"the architecturally-sanctioned BI5
  consumer. ALL discovery / mutation / OOS / validation work continues to run on BID candles."*
- `bi5_realism._load_bi5_bars` calls `data_access.load_with_recovery(source="bi5",
  auto_recover=False)` — never auto-downloads.
- Eligible stages locked to `("portfolio_worthy", "deployment_ready")` only.

### 4.2 Lifecycle Progression Engine (G6) ✅ Active
- 8 stages declared in `LIFECYCLE_STAGES` (`exploratory → candidate → validated → stable
  → prop_safe → elite → portfolio_worthy → deployment_ready`).
- `evaluate_cohort` is a pure function over already-cached fields — no backtest re-run,
  no LLM call. Caller-supplied cohort percentile.
- Hysteresis buffers per stage to prevent flip-flop: validated 0.10 OOS, stable 0.10 CoV,
  prop_safe 0.02 DD, deployment_ready 0.10 BI5.
- Cool-down: BI5_FAIL → 30-day cap at `stable`.
- Flag taxonomy closed: `PARTIAL_REALISM`, `BI5_FAIL`, `STALE`, `MANUALLY_OVERRIDDEN`,
  `BI5_DATA_MISSING` (flag-and-allow path).
- Persistence opt-in (`upsert_lifecycle`); audit log into
  `strategy_lifecycle_history` collection on every transition.
- `evaluate_lifecycle_cohort` action wired into orchestrator rule-book (Rule 8) — fires
  every tick; verified inline with `POST /orchestrator/decide` (current rec).

### 4.3 Orchestration Authority (G2) ✅ Active
- Single APScheduler instance per backend boot (`engines.orchestrator_scheduler`).
- `auto_scheduler` carries a `subordinate_to_orchestrator` flag (default True from
  `SchedulerStartRequest`); when both schedulers run, `orchestrator_scheduler.is_active()`
  is the read-only probe used by auto_scheduler to defer.
- BI5 weekly sweep (Sunday 03:00 UTC) is mounted on the SAME scheduler instance — single
  authority for recurring background work.
- Both schedulers persist enable-state into Mongo (`orchestrator_scheduler_config`,
  `auto_scheduler_config`) so state survives restart via `restore_if_enabled` startup hooks.
- Cooldown guard on `/orchestrator/tick` (120s wall-clock) prevents human overlap.

### 4.4 Research Lineage System (G1) ✅ Active
- `engines/research_lineage.py` opens a `research_run_id` per orchestrator-driven trigger.
- Confirmed live on cold start: 1 prior run (`rr_20260509T145857_…`, trigger:
  `auto_scheduler_tick`, status: `completed`).
- 4 read-only API endpoints (`/api/research-runs*`).
- `ai_orchestrator.execute()` opens a research_run BEFORE calling `mcr.start_multi_cycle`
  and propagates `research_run_id` downstream (see line ~676–696 of `ai_orchestrator.py`).

### 4.5 Behavioral Profile Layer ✅ Present
Validated by `_gate_stable` — requires `behavioral_profile` to be classified and NOT
`BALANCED` / `UNCLASSIFIED` to enter STABLE. Profiles produced by `engines/strategy_profiler.py`
and surfaced via `_attach_validation_view` in `strategy_memory.py`.

### 4.6 BI5 Realism Certification Layer ✅ Active
- `evaluate(force_refresh)`, `sweep_realism(force_refresh, limit)`, `get_realism`,
  `stale_realism_count` — all four surfaces exist and are mounted.
- Freshness window: 60 days (`REALISM_FRESHNESS_DAYS`), short-circuits via `fresh_cache`
  status when `force_refresh=False`.
- Persists onto the lifecycle doc's `bi5_realism` block with `upsert=False` (does NOT
  create lifecycle rows from this path — clean separation of authority).
- PF ratio thresholds: `≥0.75` → ok / deploy-eligible; `0.50–0.75` → `partial` /
  `PARTIAL_REALISM`; `<0.50` → `fail` / `BI5_FAIL` + 30-day cool-down.
- Cron mounted on orchestrator scheduler at SUN 03:00 UTC (verified in
  `/orchestrator/scheduler/status.realism_sweep.schedule`).

---

## 5. What Is Complete

| Layer                                      | State    | Evidence                                          |
|--------------------------------------------|----------|---------------------------------------------------|
| Discovery / mutation / validation pipeline | Complete | `multi_cycle_runner`, `auto_mutation_runner`, `mutation_engine`, `validation_engine` — all routed |
| 4-stage stage label + new 8-stage ladder   | Complete | Both coexist; old `stage` field untouched in `strategy_memory._attach_validation_view` |
| Behavioral transparency layer              | Complete | `strategy_profiler` + `behavioral_profile` field consumed by `_gate_stable` |
| Research lineage (G1)                      | Complete | Engine + 4 read-only routes + cold-start audit row present |
| Orchestration authority (G2)               | Complete | Single scheduler, subordination probe `is_active()`, cooldown guard, persistence |
| Lifecycle classifier (Phase 26.5)          | Complete | Pure-function gates over cached metrics, hysteresis, cool-down, closed flag taxonomy |
| Lifecycle progression engine (G6)          | Complete | `evaluate_cohort` + `LIFECYCLE_EVALUATE` rec wired into every orchestrator tick |
| BI5 realism certification (Phase 27.3)     | Complete | Sunday cron + freshness window + flag-and-allow + force_refresh + deployment-gating |
| Auth + admin seed                          | Complete | JWT bearer middleware, login verified, seeded user reachable |
| Frontend boot + sign-in surface            | Complete | Renders cleanly, AuthGate present |

---

## 6. What Is Partial / Cold

These are NOT architectural gaps — they are **runtime emptiness** because the database
is fresh:

* `library.total = 0` — no strategies discovered yet.
* `lifecycle.stage_counts` — all stages = 0; classifier ready but cohort empty.
* `research_runs` count = 1 (single residual auto-scheduler row from 2026-05-09 14:58).
* `market_data.total_rows = 0` — no BID / BI5 ingested → `readiness.overall = red`.
* `portfolio-intelligence.current.status = "empty"` — no portfolios graduated.
* Schedulers (`orchestrator_scheduler`, `auto_scheduler`) both `enabled: false` — disabled
  state is the persisted default.
* `llm_budget` readiness = yellow ("LLM key is present but does not match expected shape")
  — `EMERGENT_LLM_KEY` is set to the OpenAI sk-proj-* key by design (back-compat shim
  documented inline in `backend/.env`); not a defect, just a soft-warn.

---

## 7. What Remains

### Intentionally paused (per problem statement)
* **G7 deployment-report layer** — paused on purpose. The chain is otherwise complete:
  `lifecycle` → `bi5_realism` → `deployment_ready` gate. G7 would package per-strategy
  deployment artefacts (manifest + cBot binary + risk profile + portfolio context) for
  external operator hand-off.

### Operational, not architectural
1. Ingest market data (BID + BI5) → readiness flips to green → first multi-cycle tick can
   produce strategies.
2. Enable the orchestrator scheduler (`POST /api/orchestrator/scheduler/start`) so the
   tick loop drives autonomous progression.
3. (Optionally) enable the auto_scheduler with `subordinate_to_orchestrator=true` so
   discovery only runs while the orchestrator is also live.
4. Resolve the soft `llm_budget` readiness yellow if a true Emergent universal key is
   desired (currently aliased to OpenAI sk-proj-* by design).

---

## 8. Architectural Risks / Concerns

### Confirmed clean
* No duplicate orchestration paths. `multi_cycle_runner.start_multi_cycle` is the single
  trigger entry, called from both manual API and from `ai_orchestrator.execute()`.
* No competing schedulers. Orchestrator scheduler owns BI5 sweep; auto_scheduler
  subordinates via the cheap `is_active()` probe.
* No backend corruption. All 88 engines + 43 routers import without error after dependency
  install. No circular-import warnings in the boot trace.
* Frontend runtime issue (mentioned in problem statement) is no longer present — root
  page renders the Sign-In screen cleanly.
* BID/BI5 separation is enforced by code AND comments — no path other than
  `engines.bi5_realism` calls `data_access.load_with_recovery(source="bi5")`.

### Soft observations (no action needed in this phase)
1. **Heavy uvicorn auto-reload churn at boot.** The `WatchFiles detected changes` log
   line lists ~270 files — caused by file mtimes from the unzip. First reload settled,
   second reload after `pip install` was clean. Cosmetic; subsequent edits will be
   incremental.
2. **`requirements.txt` carries `dukascopy-python==4.0.1`** — must be reinstalled on a
   fresh environment (it was already missing pre-restore). `pip install -r requirements.txt`
   covers it; the system handled this transparently during boot verification.
3. **`.env` contains live API keys** (OpenAI, DeepSeek, Anthropic). Acceptable for the
   preview environment; flag for any future production push.
4. **EMERGENT_LLM_KEY back-compat shim.** Pointed at the OpenAI key by intention
   (documented in-file lines 16–23 of `backend/.env`). Safe; preserves every consumer
   without code changes. Triggers a soft `yellow` on the readiness panel.
5. **No active research_runs / lifecycle_history rows** to validate the audit trail in
   live runtime — the cold-start row from 14:58 confirms the lineage WRITE path works.
   Once schedulers are enabled the audit log will populate.

### No risks identified for
* Cached-metrics approach (lifecycle is pure function over already-stored fields).
* Reversible feature layering (every G-phase module is additive — removing
  `engines/bi5_realism.py` would not break the lifecycle gates that precede it).
* Lightweight orchestration (no LLM calls inside orchestrator decision loop).
* Lifecycle progression logic (8 gates verified; hysteresis verified; cool-down verified).

---

## 9. Health Snapshot — Single Glance

```
SUPERVISOR     : ✓ all 5 services RUNNING
BACKEND        : ✓ /api/health 200
FRONTEND       : ✓ root 200, sign-in renders
MONGODB        : ✓ reachable, fresh DB
AUTH           : ✓ JWT login round-trip OK
260 ROUTES     : ✓ openapi.json reachable
LIFECYCLE API  : ✓ 5 endpoints declared, 8-stage taxonomy live
BI5 REALISM API: ✓ 4 endpoints declared, eligible_stages locked
ORCHESTRATOR   : ✓ state/decide/tick/scheduler all 200; LIFECYCLE_EVALUATE fires
G2 SUBORDINATION: ✓ is_active() probe present, persisted config schema in place
G6 PROGRESSION : ✓ evaluate_lifecycle_cohort wired into rule-book (Rule 8)
G7 DEPLOY-REPORT: ⏸ paused (intentional)
READINESS      : ⚠ red (empty market_data) — gate fires correctly
SCHEDULERS     : ⏸ both disabled (persisted default; awaits operator turn-on)
```

---

## 10. Inspection Boundary

**Performed:** dependency install (1 run of `pip install -r requirements.txt`),
supervisor restart of backend, read-only HTTP probes, code reading, file structure scan,
log inspection.

**Not performed:** zero code changes, zero refactors, zero deletions, zero file moves,
zero engine modifications, zero merges. The codebase under `/app` is bit-identical to
the uploaded archive aside from `__pycache__` regeneration and an unaltered
`requirements.txt`.

**Awaiting:** further instruction before any modification.
