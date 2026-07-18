# R2_COMPLETION_REPORT

**Branch:** BI5 Recovery R2 — B-4 Auto Certification Sweep · B-5 Master Bot Ranker Integration · B-8 Lifecycle / UI Surfacing
**Authorisation:** operator-approved 2026-06-13
**Implemented by:** receiving agent
**Verified:** 2026-06-13
**Code revisions:**
* `bi5_cert_sweep@R2-v1` (new engine)
* `bi5_cert_sweep_scheduler@R2-v1` (new APScheduler cadence)
* `master_bot_ranker v1.0 → v1.1`
* `/api/diag/bi5/health` ingest_version `r1-v1 → r2-bi5-health-with-cert-v1`

**Scope adherence:** R2 only. Strategy Import not begun · Factory Supervisor not begun · Auto Learning not begun · Marketplace not begun · Phase 13/14/15 not begun · Step-0 calibration untouched after closure · `/app/_migration_inbox/` still absent · `strategy_library` still empty.

---

## 1 · What landed

### 1.1 B-4 — Auto Certification Sweep

| Artefact | Path | Role |
|---|---|---|
| Sweep engine (new) | `backend/engines/bi5_cert_sweep.py` | Walks `strategy_library`, builds `StrategyCertRequest` per strategy, calls existing `certify_strategy()` orchestrator, persists log rows + emits lifecycle events. |
| Weekly scheduler (new) | `backend/engines/bi5_cert_sweep_scheduler.py` | APScheduler `CronTrigger` job · Sunday 03:00 UTC · single-instance · misfire grace 600 s · coalesce. |
| API surface (new) | `backend/api/bi5_cert_sweep.py` | `POST /api/admin/bi5/sweep`, `GET /api/admin/bi5/sweep/{runs,results,status}` — all admin-gated. |
| Server wiring | `backend/server.py` | Router include + startup hook `_start_bi5_cert_sweep_scheduler` (idempotent). |
| Persistence | `bi5_cert_sweep_runs` + `bi5_cert_sweep_log` (auto-created) | Run-level summary + per-strategy result rows. |

Key design choices:

* **Idempotent on empty library.** First-call latency on a 0-row library = 12 ms; the runner exits cleanly with `processed=0` and writes one summary row to `bi5_cert_sweep_runs`. This is the verified pre-GATE-3 state.
* **Pair-cert cache.** `_precheck_pair_data_cert` is memoised per pair within a run so a 200-strategy sweep does at most 4 cert-store reads (one per supported FX/metal pair).
* **Honest early-fail audit.** Strategies whose pair has no PASS data cert are NOT routed into the orchestrator; they get a `DATA_CERT_NOT_PASS` / `DATA_CERT_MISSING` row in `bi5_cert_sweep_log` AND a `bi5_cert` event in `strategy_lifecycle_history` with `verdict=FAIL` + reason. This preserves the contract that the audit trail explains *why* a strategy is uncertified.
* **Budget-capped.** `max_strategies` (default 200) ceiling on every run prevents a runaway library from parking the sweep.
* **No I/O for live ticks.** B-4 deliberately does NOT pull ticks from the BI5 archive — that's R3's B-3 territory. The orchestrator already short-circuits when ticks aren't supplied; for now the sweep records `MISSING_FILLS` / `MISSING_SIGNALS` honestly when validation artefacts aren't present.

### 1.2 B-5 — Master Bot Ranker Integration

| Artefact | Path | Role |
|---|---|---|
| Weight table updated | `backend/engines/master_bot_ranker.py` | `DEFAULT_WEIGHTS` rebalanced per R2 spec. Two new active signals added. |
| New scoring path | same file, `_compute_candidate_score` | Reads `bi5_cert_verdict` (PASS=1.0 · WARN=0.5 · FAIL/absent=0.0) and `bi5_slippage_score` (0..1 clamp). |
| Verdict map | same file, `BI5_VERDICT_SCORE` + `_norm_bi5_verdict` | Three-tier mapping; unknown verdicts default to 0.0. |
| Auto re-seed | same file, `get_weights` | When the persisted config doc is on an older `ranker_version`, the weights are re-seeded to the new defaults idempotently. Operator overrides (`updated_by != system_default`) are preserved as additive overlays. |
| Test coverage | `backend/tests/test_master_bot_ranker_bi5_signals.py` (new) | 9 pure-function tests. |

**Active default weight set (Σ = 1.00 exactly):**

| Signal | Old | New | Δ |
|---|---:|---:|---:|
| `deploy_score`        | 0.60 | **0.50** | −0.10 |
| `pass_probability`    | 0.40 | **0.40** |  0   |
| `bi5_cert_verdict`    | —    | **0.07** | new |
| `bi5_slippage_score`  | —    | **0.03** | new |
| `risk_of_ruin`        | 0.00 | 0.00 | hook |
| `calibration`         | 0.00 | 0.00 | hook |
| `regime_fitness`      | 0.00 | 0.00 | hook |

The reservation pattern for future-phase signals (`risk_of_ruin`, `calibration`, `regime_fitness`) is preserved verbatim — those hooks remain 0-weighted until R6 / Phase 13 activates them.

### 1.3 B-8 — Lifecycle / UI Surfacing

| Artefact | Path | Role |
|---|---|---|
| Lifecycle events | written by `bi5_cert_sweep._emit_lifecycle_event` | Additive `event_type="bi5_cert"` rows appended to `strategy_lifecycle_history`. No `from_stage`/`to_stage` fields — these are NOT stage transitions, so the cohort-distribution aggregate (filtered by stage fields) ignores them. Pure audit additivity. |
| New diag panel (new) | `frontend/src/components/Bi5CertPanel.jsx` + `Bi5CertPanel.css` | Mounted at `diag/bi5-cert`. Reads cert distribution, sweep history, cadence status; offers an admin-gated "Run sweep now" button. |
| Module registry | `frontend/src/command/shell/modulesRegistry.js` | One new section line registered under `diag` (Diagnostics module). Available on `workstation` + `tablet` posture. |
| BI5 Health panel extended | `frontend/src/components/BI5HealthPanel.jsx` + `.css` | One new column **Data Cert** with PASS/WARN/FAIL/— chips; backed by the new `data_cert_verdict` field on `/api/diag/bi5/health` rows. |
| BI5 Health endpoint extended | `backend/api/diag_bi5_health.py` | Per-symbol latest data-cert join (single point lookup per symbol — cheap). Summary now also publishes `cert_pass`, `cert_warn`, `cert_fail`, `cert_absent` roll-up counters. `ingest_version` bumped to `r2-bi5-health-with-cert-v1`. |

---

## 2 · Architecture summary of what changed

```
+──────────────────────────── R2 SCOPE (closed) ───────────────────────────+
|                                                                          |
|  ┌─────────────────────┐                                                 |
|  │ APScheduler (cron)  │  Sun 03:00 UTC                                  |
|  │ bi5_cert_sweep_     │ ───────────────┐                                |
|  │   scheduler@R2-v1   │                │                                |
|  └─────────────────────┘                ▼                                |
|                                ┌──────────────────────────────┐          |
|     POST /api/admin/bi5/sweep ▶│      run_sweep()             │          |
|     (manual operator trigger)  │  bi5_cert_sweep@R2-v1        │          |
|                                │  - per-pair cert cache       │          |
|                                │  - budget-capped (max_str)   │          |
|                                │  - idempotent persistence    │          |
|                                └─────────┬────────────────────┘          |
|                                          │                               |
|                                          ▼                               |
|              ┌─────────────────────────────────────────────────┐         |
|              │  certify_strategy()  (UNCHANGED — P0B Phase 3) │         |
|              │   • DATA_CERT_MISSING / NOT_PASS short-circuit │         |
|              │   • MISSING_FILLS / MISSING_SIGNALS short-cir.│         |
|              │   • spread + slippage + execution + stability │         |
|              │   • weighted geomean (P0B-v2 thresholds)      │         |
|              └────────────┬───────────────────────┬───────────┘         |
|                           │                       │                     |
|                           ▼                       ▼                     |
|             bi5_cert_sweep_log         bi5_strategy_certifications      |
|             (per-strategy result)      (verdict store, unchanged)       |
|                           │                       │                     |
|                           │                       │                     |
|                           ▼                       │                     |
|             strategy_lifecycle_history            │                     |
|             (additive event_type="bi5_cert" rows) │                     |
|                                                   │                     |
|  ┌──────────────────────────────────────────┐    │                     |
|  │   fetch_candidate_pool()  (B-5 wiring)   │ ◀──┘                     |
|  │   master_bot_ranker v1.1                 │                          |
|  │   reads lib_doc.bi5_cert.{verdict,slip}  │                          |
|  │   contribution = w*norm per signal       │                          |
|  └──────────────────────┬───────────────────┘                          |
|                         │                                              |
|                         ▼                                              |
|  ┌────────────────────────────────────────────────┐                    |
|  │  GET /api/master-bot/candidates                │                    |
|  │   (now exposes bi5_cert_verdict +              │                    |
|  │    bi5_slippage_score on every candidate)      │                    |
|  └────────────────────────────────────────────────┘                    |
|                                                                          |
|  ┌────────────────────────────────────────────────────┐                  |
|  │  UI · diag/bi5-cert  (B-8 new panel)               │                  |
|  │    + diag/bi5-health (B-8 cert column extension)   │                  |
|  └────────────────────────────────────────────────────┘                  |
+──────────────────────────────────────────────────────────────────────────+
```

### Files touched (complete list)

```
NEW
  backend/engines/bi5_cert_sweep.py                       sweep engine
  backend/engines/bi5_cert_sweep_scheduler.py             Sunday cadence
  backend/api/bi5_cert_sweep.py                           4 sweep endpoints
  backend/tests/test_master_bot_ranker_bi5_signals.py     B-5 unit suite (9 tests)
  frontend/src/components/Bi5CertPanel.jsx                B-8 diag panel
  frontend/src/components/Bi5CertPanel.css                B-8 panel styles

MODIFIED
  backend/engines/master_bot_ranker.py                    B-5 weight + scoring
  backend/api/diag_bi5_health.py                          B-8 cert join + roll-up
  backend/server.py                                       router + startup hook
  frontend/src/components/BI5HealthPanel.jsx              B-8 cert chip column
  frontend/src/components/BI5HealthPanel.css              cert chip styles
  frontend/src/command/shell/modulesRegistry.js           bi5-cert section register

UNCHANGED (verified not modified)
  All other backend engines · all routers outside the four above ·
  strategy_library · prop_firm_rules · market_data · market_spread ·
  bi5_data_certification (cert verdict values from R2 Step-0 preserved) ·
  market_universe_symbols / governance_universe ·
  every non-bi5_cert lifecycle event writer.
```

---

## 3 · Evidence that B-4 is functioning

### 3.1 Cadence armed

`GET /api/admin/bi5/sweep/status` (admin Bearer):

```json
{
  "running": true,
  "job": {
    "id": "bi5_cert_sweep_weekly",
    "next_run_utc": "2026-06-14T03:00:00+00:00",
    "trigger_type": "cron",
    "cron": "Sun 03:00 UTC"
  },
  "next_run_utc": "2026-06-14T03:00:00+00:00",
  "schedule": "Sunday 03:00 UTC",
  "version": "bi5_cert_sweep_scheduler@R2-v1"
}
```

* Job registered, scheduler running, next run = next Sunday 03:00 UTC. ✓
* `misfire_grace_time=600` so a server restart in a 10-minute window around the cron edge still fires the sweep. ✓
* `max_instances=1` + `coalesce=True` so a long-running sweep never overlaps with itself. ✓

### 3.2 Manual trigger works end-to-end

`POST /api/admin/bi5/sweep` (admin Bearer) → response:

```json
{
  "run_id": "f5ea37ecc8de47f8a45222be05f4235b",
  "started_at": "2026-06-13T08:45:14.025535+00:00",
  "finished_at": "2026-06-13T08:45:14.037927+00:00",
  "duration_seconds": 0.012,
  "discovered": 0, "processed": 0,
  "pass_count": 0, "warn_count": 0, "fail_count": 0,
  "early_fails": {}, "skipped": 0, "skip_reasons": {},
  "errors": 0,
  "max_strategies": 200, "dry_run": false, "trigger": "manual",
  "sweep_version": "bi5_cert_sweep@R2-v1"
}
```

* Run completes in 12 ms on the empty library — the verified pre-GATE-3 state. ✓
* Result persisted to `bi5_cert_sweep_runs` (now contains 2 runs · both manual). ✓
* `bi5_cert_sweep_log` empty (no strategies = no per-strategy rows — as designed). ✓
* `strategy_lifecycle_history` untouched by these runs (no eligible strategies means no events to emit). ✓

### 3.3 Live DB state

```
bi5_cert_sweep_runs:           2 (both manual, 0 errors)
bi5_cert_sweep_log:            0 (empty library — by design)
strategy_lifecycle_history:    0 (no transitions because library is empty)
bi5_data_certification:        15  (PRESERVED — R2 Step-0 verdicts untouched)
```

---

## 4 · Evidence that B-5 ranker weights are active

### 4.1 Persisted config doc (live)

`GET /api/master-bot/ranker/config` (admin Bearer):

```json
{
  "weights": {
    "deploy_score":       0.50,
    "pass_probability":   0.40,
    "bi5_cert_verdict":   0.07,
    "bi5_slippage_score": 0.03,
    "risk_of_ruin":       0.00,
    "calibration":        0.00,
    "regime_fitness":     0.00
  },
  "ranker_version": "v1.1",
  "updated_at": "2026-06-13T08:51:54.056967+00:00",
  "updated_by": "system_default"
}
```

* Σ active weights = 1.00 exactly (asserted in `test_default_weights_sum_to_one_for_active_signals`). ✓
* `ranker_version` flipped from `v1.0` → `v1.1` via the on-boot auto re-seed; future operator overrides will land verbatim on top. ✓

### 4.2 Candidate pool surface

`GET /api/master-bot/candidates` returns:

```json
{
  "candidates": [],
  "active_signals": [
    "deploy_score", "pass_probability",
    "bi5_cert_verdict", "bi5_slippage_score"
  ],
  "future_signals": ["risk_of_ruin", "calibration", "regime_fitness"],
  "ranker_version": "v1.1",
  "weights": { …same as §4.1… },
  "advisory_only": true
}
```

* The 4 active signals now include both BI5 signals. ✓
* `candidates` empty because `strategy_library` is empty (GATE 3 prerequisite). ✓
* Every enriched candidate row will expose `bi5_cert_verdict`, `bi5_slippage_score`, and the full `bi5_cert` block — proven by code review (`fetch_candidate_pool` lines under "BI5 R2 / B-5" comments).

### 4.3 Pure-function proof suite

```
backend/tests/test_master_bot_ranker_bi5_signals.py  ── 9 passed in 0.03s

  test_pass_cert_outranks_no_cert                          PASSED
  test_warn_cert_outranks_no_cert_but_below_pass           PASSED
  test_fail_cert_scores_as_no_cert                         PASSED
  test_unknown_verdict_treated_as_zero                     PASSED
  test_zero_weight_backwards_compat                        PASSED   ← backwards-compat proof
  test_slippage_value_clamped                              PASSED
  test_norm_bi5_verdict_table                              PASSED
  test_default_weights_sum_to_one_for_active_signals       PASSED
  test_bi5_weight_split_matches_plan                       PASSED
```

The full BI5-side test stack (50 tests across `test_tick_validator.py` + `test_master_bot_ranker_bi5_signals.py` + `test_p0b_phase4_index_explain.py` + `test_bi5_adapter_interface.py`) passes cleanly. The R2 Step-0 P0B-v2 calibration tests remain unchanged and continue to pass.

### 4.4 Backwards-compatibility guarantee

`test_zero_weight_backwards_compat`: with both `bi5_cert_verdict` and `bi5_slippage_score` weights set to 0.0, a PASS-cert candidate scores **identically** to an absent-cert candidate. Operators can disable the new signals at any time by zeroing the weights via `POST /api/master-bot/ranker/config` — no code revert required.

---

## 5 · Evidence that B-8 lifecycle surfacing is visible in the UI

### 5.1 Live screenshot (workstation posture)

UI was loaded at `https://strategy-prod-main.preview.emergentagent.com/c/diag` with the admin account, then scrolled to the new section. **Both panels rendered cleanly, dark theme intact, Binance gold `#F0B90B` accent preserved.**

### 5.2 BI5 R2 · Strategy & Data Certification panel — captured rendering

```
BI5 R2  Strategy & Data Certification     schema · bi5_cert_sweep_scheduler@R2-v1
                                                                [Refresh]  [Run sweep now]

DATA-CERT TOTAL    PASS         WARN         FAIL    LAST SWEEP    LAST SWEEP AT   NEXT AUTO-SWEEP
     15             9            6            0       0/0           2m ago           2026-06-14 03:00 UTC

Data Certifications · per (symbol × window) — 15 windows
SYMBOL    WINDOW                    SUB-SCORES                                  COMPOSITE  VERDICT
EURUSD    2026-05-31 → 2026-06-06   cov 1.00 · integ 1.00 · price 1.00 · dens 0.49 · cont 0.41   0.8254   WARN
EURUSD    2026-05-01 → 2026-05-30   cov 1.00 · integ 1.00 · price 1.00 · dens 0.57 · cont 0.41   0.8436   WARN
EURUSD    2026-04-01 → 2026-04-30   cov 1.00 · integ 1.00 · price 1.00 · dens 0.61 · cont 0.43   0.8578   PASS
EURUSD    2026-03-02 → 2026-03-31   cov 1.00 · integ 1.00 · price 1.00 · dens 0.69 · cont 0.47   0.8831   PASS
EURUSD    2026-01-31 → 2026-03-01   cov 1.00 · integ 1.00 · price 1.00 · dens 0.54 · cont 0.43   0.8416   WARN
EURUSD    2026-01-01 → 2026-01-30   cov 1.00 · integ 1.00 · price 1.00 · dens 0.52 · cont 0.36   0.8255   WARN
GBPUSD    2026-05-31 → 2026-05-31   cov 1.00 · integ 1.00 · price 1.00 · dens 1.00 · cont 0.50   0.9434   PASS
GBPUSD    2026-05-01 → 2026-05-30   cov 1.00 · integ 1.00 · price 1.00 · dens 0.69 · cont 0.40   0.8704   PASS
GBPUSD    2026-03-02 → 2026-03-03   cov 1.00 · integ 1.00 · price 1.00 · dens 0.88 · cont 0.46   0.9175   PASS
GBPUSD    2026-01-31 → 2026-03-01   cov 1.00 · integ 1.00 · price 1.00 · dens 0.68 · cont 0.41   0.8702   PASS
GBPUSD    2026-01-01 → 2026-01-30   cov 1.00 · integ 1.00 · price 1.00 · dens 0.66 · cont 0.33   0.8511   PASS
USDJPY    2026-05-31 → 2026-05-31   cov 1.00 · integ 1.00 · price 1.00 · dens 0.50 · cont 0.43   0.8301   WARN
USDJPY    2026-05-01 → 2026-05-30   cov 1.00 · integ 1.00 · price 1.00 · dens 0.52 · cont 0.42   0.8324   WARN
XAUUSD    2026-05-31 → 2026-05-31   cov 1.00 · integ 1.00 · price 1.00 · dens 1.00 · cont 0.66   0.9655   PASS
XAUUSD    2026-05-01 → 2026-05-30   cov 1.00 · integ 1.00 · price 1.00 · dens 0.85 · cont 0.64   0.9384   PASS

Strategy Certification · sweep history — 2 recent runs
RUN STARTED              TRIGGER   DISCOVERED   PASS   WARN   FAIL   SKIPPED   DURATION
2026-06-13 08:54 UTC     manual         0         0      0      0       0        0.00s
2026-06-13 08:45 UTC     manual         0         0      0      0       0        0.01s

Auto-sweep cadence: Sunday 03:00 UTC · ranker weights: bi5_cert_verdict 0.07 · bi5_slippage_score 0.03 ·
manual trigger available to admins.
```

* Verdict chips: PASS in Binance gold, WARN in amber, FAIL in danger red.
* "Run sweep now" button fires synchronously and surfaces a toast: *"Sweep complete · run_id 90c53f72… · discovered=0 · processed=0 · …"*
* Auto-refresh every 30 s.
* All `data-testid` attributes present: `bi5-cert-panel`, `bi5c-run-sweep`, `bi5c-refresh`, `bi5c-stats`, `bi5c-data-section`, `bi5c-sweep-section`, `bi5c-data-row-{SYMBOL}`, `bi5c-sweep-row-{run_id}`, `bi5c-empty-{data,sweep}`.

### 5.3 BI5 Health panel — new Data Cert column

| Symbol  | Coverage | Status   | **Data Cert** | Health Score |
|---|---:|---|---|---|
| BTCUSD  | 0.0%    | unknown  | —    | reserved |
| ETHUSD  | 0.0%    | unknown  | —    | reserved |
| EURUSD  | 71.4%   | ok       | **WARN** | reserved |
| GBPUSD  | 42.5%   | ok       | **PASS** | reserved |
| US100   | 0.0%    | unknown  | —    | reserved |
| USDJPY  | 67.3%   | ok       | **WARN** | reserved |
| XAUUSD  | 64.6%   | ok       | **PASS** | reserved |

Schema note rendered at the bottom of the panel:
> "R2 / B-8 adds per-symbol data_cert_verdict + data_cert_score join."

### 5.4 Lifecycle event surface

`strategy_lifecycle_history` currently contains 0 BI5 cert events (because no strategies are eligible — the library is empty). The emitter is wired and proven by code review (`_emit_lifecycle_event` is called on every per-strategy outcome path: pair-pre-check-fail, dry-run, build-fail, orchestrator return). The first strategy admitted to `strategy_library` after GATE 3 will produce its first cert event on the very next sweep tick.

Event schema (additive):

```json
{
  "event_type": "bi5_cert",
  "strategy_hash": "...",
  "library_id": "...",
  "transition_at": "<UTC ISO>",
  "bi5_cert_verdict": "PASS|WARN|FAIL",
  "bi5_cert_reason": "DATA_CERT_NOT_PASS|MISSING_FILLS|LOW_COMPOSITE|null",
  "pair": "EURUSD",
  "composite_score": 0.0..1.0,
  "subscores": { "integrity": …, "spread": …, "slippage": …, "execution": …, "stability": … },
  "sweep_run_id": "...",
  "sweep_version": "bi5_cert_sweep@R2-v1"
}
```

No `from_stage` / `to_stage` / `to_stage_rank` fields → cohort distribution queries (which filter on those) ignore these rows; existing lifecycle consumers see zero behaviour change. Existing transition writers in `strategy_lifecycle.py` / `replacement_engine.py` are not touched.

---

## 6 · Updated roadmap position

```
P0  ████████████  UI Restoration M0→M5                  DONE
P0  ████████████  Strategy Score reservation            DONE
P0  ████████████  DSR-1/2/3 activation                  DONE
P0  ████████████  BI5 R1                                DONE
P0  ████████████  GATE 0 PILOT (Steps 1-3)              DONE
P0  ████████████  Restoration Steps 4-5                 DONE
P0  ████████████  Restoration Steps 6-7                 DONE
P0  ████████████  BI5 archive Pass-1 + Pass-2           DONE
P0  ████████████  BI5 R2 Step-0 audit                   DONE
P0  ████████████  BI5 R2 Step-0 fix (Option A)          DONE  2026-06-13
P0  ████████████  BI5 R2 · B-4 Auto Cert Sweep          DONE  2026-06-13  ← R2 batch
P0  ████████████  BI5 R2 · B-5 Ranker Integration       DONE  2026-06-13     closed
P0  ████████████  BI5 R2 · B-8 Lifecycle/UI Surfacing   DONE  2026-06-13
P1  ░░░░░░░░░░░░  GATE 3 strategy import                BLOCKED (operator package)   ← we are here
P1  ░░░░░░░░░░░░  BI5 R3 (B-3 / B-6 / B-7)              NOT STARTED
P2  ░░░░░░░░░░░░  Phase 13 Dossier Engine               RESERVED
P2  ░░░░░░░░░░░░  Phase 14 Valuation Engine             RESERVED
P2  ░░░░░░░░░░░░  Pre-deploy hardening + soak           NOT STARTED
P2  ░░░░░░░░░░░░  12-vCPU deployment                    NOT STARTED
P3  ░░░░░░░░░░░░  Phase 15 Marketplace                  SEPARATE CODEBASE
```

**R2 is closed.** The Sunday-cadence sweep is armed and will fire on 2026-06-14 03:00 UTC; until then operators can trigger it manually from the new diag panel. Every B-4/B-5/B-8 acceptance criterion in `BI5_R2_IMPLEMENTATION_PLAN.md §1-§3` is met.

---

## 7 · Exact remaining work before GATE 3

GATE 3 is the strategy-import gate that re-populates `strategy_library` from the 1-vCPU codebase export. The remaining preconditions before it can begin:

| # | Item | Owner | State | Effort |
|---|---|---|---|---|
| 1 | **Operator drops the 1-vCPU strategy-export zip into `/app/_migration_inbox/`** | Operator | ⛔ AWAITING — directory currently absent. Per `PROJECT_EXECUTIVE_HANDOFF.md §11`, this is the single operator action that unlocks GATE 3. | n/a (operator action) |
| 2 | Inbox unpack + manifest verification | Receiving agent | NOT STARTED. The unpack walker, manifest schema, and fingerprint pre-check are already documented and partially implemented per `memory/IMPORT_READINESS_REPORT.md`. | ~0.5 d |
| 3 | Importer dry-run mode (zero writes) | Receiving agent | NOT STARTED. Walk the inbox, build `StrategyLibraryRecord` candidates, compute fingerprints, hit the dedupe primitive — produce a per-strategy report WITHOUT inserting. | ~0.5 d |
| 4 | Operator review of dry-run report | Operator | n/a | n/a (operator gate) |
| 5 | Importer wet-run + idempotency proof | Receiving agent | NOT STARTED. Same walker, persistence enabled, with the unique-fingerprint index lazy-on-first-write contract honoured. Side-effect bound exclusively to `strategy_library` + `ingested_strategies` + (NEW) BI5 cert sweep entries that fire on the post-import library. | ~0.5 d |
| 6 | First post-import sweep validation | Receiving agent + operator | NOT STARTED. Confirm cert distribution, sweep log shape, lifecycle audit trail integrity, ranker recompute. | ~0.5 d |

**Total estimated GATE 3 effort (assuming operator delivers the import package today): ~2 days of clean implementation + 1 day of operator-review wall-clock.**

GATE 3 has no software dependencies still pending. R2's closure removes the last technical blocker that was queued behind the import.

---

## 8 · Estimated effort remaining to 12-vCPU deployment readiness

Per `PROJECT_EXECUTIVE_HANDOFF.md §6-§7` and `memory/SYSTEM_READINESS_REPORT.md`, the deployment-readiness milestone is downstream of GATE 3 + R3 + Phase 13 + Phase 14 + pre-deploy hardening + soak. Each item below assumes the previous one has closed.

| Stage | Items | Wall-clock | Notes |
|---|---|---|---|
| **GATE 3** | Operator delivers import zip · dry-run · wet-run · post-import sweep | **2–3 d** | See §7. Hard-gated on operator package. |
| **BI5 R3** | B-3 tick-replay loader · B-6 simulate_fills at paper runtime · B-7 Trade Runner consolidation | **5–7 d** | All three depend on a populated `strategy_library`; B-3 also wants real ticks loaded into the cert workflow (today's B-4 carries `ticks=[]`). Implementation plan is sketched but not yet committed. |
| **Phase 13 — Dossier Engine** | Evidence Score · per-strategy dossier composition · UI dossier card · BI5 Health `health_score_reserved` activation | **5–7 d** | The reservation cards exist; the engine is gated behind R3. |
| **Phase 14 — Valuation Engine** | Trust Score · automated valuation · dual scorecard activation | **4–6 d** | Phase 14's persistence is shipped; only the engine and the scorecard card need wiring. |
| **Pre-deploy hardening + soak** | 72-hour soak with the orchestrator scheduler driving auto-cert sweeps + ranker reads · runtime degradation tracking · parity sign-off pass-rate ≥ 95 % · operator review of all GATE-1/2/3/4 ledgers | **5 d** | Per `memory/SYSTEM_READINESS_REPORT.md` §5 ("Definition of Done"). Wall-clock dominated by the soak window; engineering work is ~1 d of dashboards + 4 d of monitoring. |
| **12-vCPU pod migration** | Provision pod · re-run migration validation report on the new pod · DSR-3 governance ledger seal · `kill_switch=disarmed` operator vote | **2 d** | The migration playbook is the same one used in this restore — already proven byte-faithful. |

**Aggregate: 23–30 wall-clock days from this report's timestamp to 12-vCPU production readiness, with ~3 of those being operator-gated wait time.** The first 2–3 days are the GATE 3 unlock; everything else queues behind it.

The current pod itself (1-vCPU `handoff-check.preview.emergentagent.com`) is suitable for development and operator-side validation; it is not the production target. The migration validation report (`/app/MIGRATION_VALIDATION_REPORT.md`) is the template for the 12-vCPU cut-over.

---

— End of R2 completion report. Standing by for further authorisation. —
