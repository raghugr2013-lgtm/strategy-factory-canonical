# Pre-Deployment State — Cold Boot Verified

**Date:** 2026-05-13
**Status:** ✅ Ready for native production deploy. Schedulers OFF and persisted.

## Final pre-deploy state

| Layer | State | Persistence |
|---|---|---|
| Orchestrator scheduler | `enabled: false`, `next_run_at: null`, `tick_count: 0` | ✅ `orchestrator_scheduler_config._id="default"` → `{enabled:false, interval_minutes:15}` |
| Auto-scheduler | `enabled: false`, `subordinate_to_orchestrator: true` (preserved for warm-start) | ✅ `auto_scheduler_config` doc |
| Backend health | `{status:"ok"}` post-restart | — |
| `restore_if_enabled` hooks | Both honoured `enabled=false` on restart | ✅ verified |

## Phase 27.4 BI5 Single-Source Realism Stream — Shipping with this Deploy

| Component | Status |
|---|---|
| `engines/bi5_realism._resample_1m_to_tf` (pandas, left-closed, left-labelled) | ✅ in main |
| `engines/bi5_realism._load_and_resample_bi5` | ✅ in main |
| `engines/data_access.load_bi5_1m_bars` (canonical 1m loader) | ✅ in main |
| `api/data.py` soft-warn on (bi5, non-1m) | ✅ in main |
| `tests/test_bi5_resample_alignment.py` | ✅ 8 tests pass |
| `tests/test_bi5_realism_multi_tf_consistency.py` | ✅ 4 tests pass |
| Existing `tests/test_bi5_realism_27_3.py` | ✅ 16 tests pass (zero regression) |

## Production Boot Guarantee

On first production boot:

```
1. Backend startup hooks fire in order:
   - seed_admin()                                          → seed admin@local.test if not present
   - auto_data_maintainer.restore_if_enabled()             → reads auto_data_maintainer_config
   - auto_scheduler.restore_if_enabled()                   → reads enabled=false → no-op
   - orchestrator_scheduler.restore_if_enabled()           → reads enabled=false → no-op
2. APScheduler initialises but holds no scheduled jobs.
3. Application accepts HTTP requests immediately.
4. Zero autonomous ticking until operator explicitly POSTs /scheduler/start.
```

## Cohort State Traveling to Production

| Collection | Rows | Notes |
|---|---|---|
| `market_data` | ~200k | EURUSD/H1 18.7k, XAUUSD/H1 17.7k, GBPUSD/H1 18.7k, EURUSD/15m 74.8k, XAUUSD/15m 70.9k |
| `strategy_lifecycle` | 167 | All in `exploratory`, all `from_stage: null → to_stage: exploratory` first-touch from 2026-05-10T10:21Z |
| `strategy_lifecycle_history` | ~167+ | One row per first-touch transition |
| `strategies_library` (or equivalent) | 167 shells | `runs=1` but `pf=None, trades=None, behavioral=None` — populated when warm-start ticks fire |
| `research_runs` | 2 | Both from 2026-05-10, both `status: completed` (lineage proof) |
| `bi5_ingest_log` | 0 | No BI5 staged yet (Step 5 territory) |
| `orchestrator_scheduler_config` | 1 (`enabled:false`) | Will boot disabled |
| `auto_scheduler_config` | 1 (`enabled:false, subordinate:true`) | Will boot disabled |

## Phase 1 — Cold Deploy Verification Checklist

| # | Endpoint / action | Expected |
|---|---|---|
| 1 | `GET /api/health` | `200 {"status":"ok"}` |
| 2 | `POST /api/auth/login {admin@local.test, admin123}` | 200 + JWT |
| 3 | `GET /api/orchestrator/scheduler/status` | `enabled: false, next_run_at: null` |
| 4 | `GET /api/auto/scheduler/status` | `enabled: false, subordinate: true` |
| 5 | `GET /api/lifecycle/cohort/stage-counts` | 8 stages, `total: 167`, all in `exploratory` |
| 6 | `GET /api/lifecycle/transitions/recent?limit=5` | 5 first-touch transitions from 2026-05-10 |
| 7 | `GET /api/research-runs?limit=10` | 2 completed runs from 2026-05-10 |
| 8 | `GET /api/bi5-realism/cohort/stale-count` | `stale_count: 0, eligible_stages: [portfolio_worthy, deployment_ready]` |
| 9 | `POST /api/incremental/bi5 {symbol:EURUSD, timeframe:1h}` | 200 + `deprecation_warning` populated (27.4 soft-warn live) |
| 10 | `GET /` | Sign-in card renders |
| 11 | UI sign-in flow | Reaches dashboard |
| 12 | Market data spot-check | EURUSD/1h returns 18.7k bars via `data_access.load_ohlc_bars` |
| 13 | `realism_sweep.schedule` field present even with scheduler disabled | `"SUN 03:00 UTC"` |

If any check fails → halt and investigate before Phase 2.

## Phase 2 — Controlled Warm Start (post-cold-verification)

```bash
# (A) Authority first
POST /api/orchestrator/scheduler/start    # default 15 min
# Expected: {enabled: true, interval_minutes: 15}

# (B) Subordinate immediately after
POST /api/auto/scheduler/start
  body: {"subordinate_to_orchestrator": true}
# Expected: {enabled: true, subordinate_to_orchestrator: true}

# (C) Verify G2 contract is live in production
GET /api/auto/scheduler/status
# runtime.is_subordinated_now MUST be true
```

Then monitor cadence; preserve all locked discipline:

- No threshold tweaks
- No env_priority widening
- No crypto expansion
- No forced promotions
- No manual `/api/orchestrator/tick` invocations
- Observation cadence: lifecycle transitions, orchestrator tick continuity, subordinate coordination, research_runs growth

## Discipline Preservation Summary

- ✅ BID/BI5 separation philosophy intact
- ✅ G2 orchestration authority contract preserved
- ✅ G6 lifecycle progression engine wired
- ✅ G1 research lineage active
- ✅ Phase 27.4 single-source realism stream shipping
- ✅ Lifecycle gates untouched
- ✅ Discovery engines untouched
- ✅ Backtest engine untouched
- ✅ Frontend untouched
- ✅ No threshold drift
- ✅ No env widening
- ✅ Schedulers will NOT autonomously tick on production boot

🟢 **Ready for native production deploy.**
