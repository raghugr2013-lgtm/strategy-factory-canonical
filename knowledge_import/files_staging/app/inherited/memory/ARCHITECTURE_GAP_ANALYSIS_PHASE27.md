# Phase 27 — Autonomous Lifecycle Consolidation
## Architecture Inspection · Maturity Map · Remaining Gaps

> **Read-only deliverable.** No code changed. No new systems added.
> Goal: confirm what is in place after Phases 25 / 26 / 26.5 / G1, identify
> the *exact* remaining surface for **G2 · G6 · BI5 realism gate · G7**, and
> flag the few residual fragmentations / cleanup items the previous run
> stopped short of.
>
> Read after `ARCHITECTURE_ANALYSIS_PHASE26.md` and
> `STRATEGY_LIFECYCLE_DESIGN_PHASE26_5.md`.

---

## 0. Executive snapshot

| Area | Status | Tested | Confidence |
|---|---|---|---|
| **Phase 25** Behavioral transparency | ✅ implemented (cards + chips + badges) | manual + screenshots | HIGH |
| **Phase 26 / G1** Research-run lineage | ✅ implemented end-to-end | 13/13 pytest pass (`test_research_lineage_g1.py`) | HIGH |
| **Phase 26.5** 8-stage lifecycle MODEL | ✅ implemented as pure module + Explorer rollup wiring | gate logic + persistence tested (`test_strategy_lifecycle_phase26_5*.py`, ~1 030 LOC) | HIGH |
| **G2** Scheduler unification | ❌ **NOT done** — both `auto_scheduler` and `orchestrator_scheduler` still independent | — | n/a |
| **G6** Promotion ladder rules in `ai_orchestrator.decide()` | ❌ **NOT done** — no `LIFECYCLE_PROMOTE_TO_*` rules; no `auto_build_portfolio` execution; no `lifecycle_evaluator` job | — | n/a |
| **BI5 realism gate** (`engines/bi5_realism.py`) | ❌ **NOT done** — module absent; `paper_execution_engine` *can* run with `source="bi5"` but no realism-PF calculator, no Sunday sweep, no library-doc realism block, no UI surface | — | n/a |
| **G7** Deployment report (`engines/deployment_report.py`) | ❌ **NOT done** — module absent; no signed JSON+Markdown artifact; no "Ready to Deploy" widget | — | n/a |
| **Lifecycle UI surface** (8-stage chips on Explorer) | ⚠️ **partial** — backend already returns `validation.lifecycle_stage / lifecycle_stage_rank / lifecycle_flags / lifecycle_cool_down_until`, but `StrategyExplorer.js` still renders only the legacy 4-stage `<StageBadge stage={v.stage} />` (line 1239). | — | LOW |
| **Test cleanup pass** (the credits-out item) | ⚠️ **partial** — tests are present and self-cleaning; `__pycache__/` carries stale compiled tests; nothing currently rotting in Mongo | inspected directory | MEDIUM |

The skeleton designed in Phase 26.5 §8 is implemented up to the **module + cached-view** layer. Everything past that — the orchestrator rules, the deployment artifact, BI5 closure, scheduler unification — is still pending.

---

## 1. Phase-by-phase maturity verification

### 1.1 Phase 25 — Behavioral transparency
- `engines/strategy_memory.py::_attach_behavior_metrics()` mutates the metrics block in-place, classifies via `_classify_behavior` and `_classify_smoothness` (pure heuristics over WR / RR / trades / DD / stability).
- Adds: `wins`, `losses`, `avg_win`, `avg_loss`, `risk_reward_ratio` derivation, `behavioral_profile`, `expected_max_consec_losses`, `avg_consec_losses`, `recovery_factor`, `smoothness_label`.
- Surfaced through `_attach_validation_view` → Explorer rollup AND `get_strategy_details()` (single source for orchestrator + matcher reuse).
- Frontend cards verified in PRD: `BehaviorCard`, `WinLossCard`, `StreakCard`, `SmoothnessCard` all rendered in `StrategyDetailsPanel.js` with `data-testid` attributes.

**Verdict:** ✅ closed.

### 1.2 Phase 26 / G1 — Research-run lineage
- New module `engines/research_lineage.py`.
- New collection `research_runs` (root-doc-per-tick).
- Threaded `research_run_id` through:
  - `ai_orchestrator.execute()` → opens `orchestrator_tick` lineage doc before triggering multi-cycle (lines 478–489).
  - `multi_cycle_runner.start_multi_cycle` accepts the rrid; auto-creates `manual_api` rrid when missing.
  - `auto_mutation_runner.run_single_cycle` + `run_auto_mutation` (long-running) accept the rrid.
  - `auto_scheduler._build_job` opens an `auto_scheduler_tick` lineage root per tick (line 118).
  - `strategy_memory.record_performance` writes the rrid onto `strategy_performance_history`, attaches `history_row` / `mutation_run` / `library_save` children (lines 122–143).
- HTTP API: `GET /api/research-runs` (list/filter), `GET /api/research-runs/{rrid}`, `GET /api/research-runs/by-strategy/{hash}`, `GET /api/research-runs/by-library/{id}`.
- UI: `LineageCard` in `StrategyDetailsPanel.js` (lines 381–460).

**Tested:** 13/13 in `test_research_lineage_g1.py` (covers HTTP, engine, history-row attach, 404, by-strategy, by-library). Test report `iteration_1.json` is clean.

**Verdict:** ✅ closed.

### 1.3 Phase 26.5 — Strategy Lifecycle Model
File `engines/strategy_lifecycle.py` (678 LOC) implements:

- **Closed taxonomy** `LIFECYCLE_STAGES = (exploratory, candidate, validated, stable, prop_safe, elite, portfolio_worthy, deployment_ready)` and `LIFECYCLE_FLAGS = {PARTIAL_REALISM, BI5_FAIL, STALE, MANUALLY_OVERRIDDEN}`.
- **Pure gate functions**: `_gate_candidate`, `_gate_validated`, `_gate_stable`, `_gate_prop_safe`, `_gate_elite`, `_gate_portfolio_worthy`, `_gate_deployment_ready`. Hysteresis buffers per gate (validated 0.10 OOS, stable 0.10 CoV, prop_safe 0.02 DD, deployment_ready 0.10 BI5).
- **Cohort percentile** helper (`compute_cohort_p90_deploy_score`) + linear-interp `_percentile`. `min_cohort_size=10` — returns `None` below threshold (gate fails closed).
- **Inline deploy-score estimator** (`estimate_deploy_score`) mirrors `auto_selection_engine._compute_deploy_score` with weights pp:0.25, stability:0.20, pf_capped:0.15, oos:0.15, dd_inv:0.10, score_field:0.10, trades_adequacy:0.05.
- **Cool-down model**: BI5_FAIL caps stage at `stable` for 30 days; STALE flag fires when `last_run_at` >30 days old AND stage ≥ stable.
- **Persistence**: `upsert_lifecycle()` writes to `strategy_lifecycle` (current snapshot) and appends transitions to `strategy_lifecycle_history` (audit log) — opt-in; never called from Explorer rollup.
- **Wired into rollup**: `strategy_memory._attach_lifecycle_view()` runs on every Explorer fetch using `compute_lifecycle_state_from_rollup` and the per-fetch cohort p90; writes 4 fields under `validation.*` (`lifecycle_stage`, `lifecycle_stage_rank`, `lifecycle_flags`, `lifecycle_cool_down_until`).
- **Old 4-stage `validation.stage`** is **untouched** (additive — exactly as the design promised).

**Tested**: `tests/test_strategy_lifecycle_phase26_5.py` (550 LOC, gate-by-gate + persistence) + `tests/test_strategy_lifecycle_phase26_5_edge_cases.py` (483 LOC). Both self-clean with `TEST_LF_` prefix.

**Verdict:** ✅ MODEL is closed. **But the model is currently isolated** — no orchestrator rule reads `lifecycle_stage`, no UI chip renders the new stage, no promotion advances on transitions. The model was built; nothing yet *acts* on it. (This is the natural seam G6 is supposed to fill.)

---

## 2. The two schedulers (G2 surface)

Confirmed by reading `engines/auto_scheduler.py` and `engines/orchestrator_scheduler.py`:

- Two **independent** APScheduler instances, two persisted config docs (`auto_scheduler_config`, `orchestrator_scheduler_config`), two restore-at-startup hooks in `server.py` (lines 158, 168).
- `auto_scheduler` ticks call `auto_mutation_runner.run_single_cycle(...)` directly with a hard-coded rotating EURUSD↔XAUUSD H1.
- `orchestrator_scheduler` ticks call `ai_orchestrator.run_tick(execute=True)` which may emit `trigger_multi_cycle` (uses `env_priority` adaptive scan).
- **Both can fire every 15 min in parallel** — no coordination, no cost-aware throttle, no shared lineage parent.
- Each path independently opens its own `research_run_id` (lineage is consistent, but the work is duplicated when both schedulers are on).

**Why G2 is the right next move:** the lifecycle ladder will produce promotion rules that should fire **once per tick**, not twice — and the `lifecycle_evaluator` job (G6.3 below) belongs in a **single** scheduler authority.

**Sub-gap unique to G2:**
1. `_build_job` in `auto_scheduler` opens lineage AND drives a cycle, but doesn't expose itself to the orchestrator's decision step. Two reasonable paths:
   - **Option A — Subordinate**: `auto_scheduler` becomes a *no-op when `orchestrator_scheduler.is_enabled()` returns true*. Auto-discovery still possible standalone for users who don't run the orchestrator.
   - **Option B — Merge**: Orchestrator job's APScheduler instance also schedules the auto-discovery cron with a different cadence + rule_id (`AUTO_DISCOVERY_TICK`). Both share the same `_lock` so they never overlap.
2. The two restore hooks must collapse into one to keep restart semantics simple.

Either option preserves config schemas + endpoints (no breaking change for the UI).

---

## 3. G6 surface (the promotion ladder)

`engines/ai_orchestrator.py::decide()` currently has **7 rules** (lines 240–415):
`RUN_ACTIVE`, `NO_SAVES_BOOST_DIVERSITY`, `NO_SAVES_WAIT`, `HIGH_INSUFFICIENT_TRADES`, `LOW_PF_DIVERSITY`, `PROP_STATUS_FAIL_DOMINANT`, `OOS_GATE_DOMINANT`, `PROMOTE_BEST` (advisory, score≥60), `HEALTHY_TRAJECTORY`.

**No rule reads `lifecycle_stage`.** **No rule emits `auto_build_portfolio`, `export_cbot_for_portfolio`, `generate_deployment_report`, or `trigger_bi5_realism_check`.** `PROMOTE_BEST` exists but only logs a recommendation — it never causes the strategy to advance.

### 3.1 What G6 needs to wire in (using already-existing modules)

| Hook | Calls | Already exists? |
|---|---|---|
| `lifecycle_evaluator` job (every tick) | `compute_lifecycle_state_from_rollup` + `upsert_lifecycle` over the eligible cohort | ✅ functions in `strategy_lifecycle.py`; just needs to be invoked |
| `LIFECYCLE_PROMOTE_TO_PORTFOLIO_WORTHY` rule | when transition `elite → portfolio_worthy` is observed in history audit | ✅ history collection populated by `upsert_lifecycle` |
| `auto_build_portfolio` action | `portfolio_builder_engine.build_portfolio(persist=True)` | ✅ engine + endpoint already exist |
| `LIFECYCLE_TRIGGER_BI5_CHECK` rule (Sunday 03:00 UTC) | `bi5_realism.evaluate(strategy_hash)` | ❌ **bi5_realism module missing** (see § 4) |
| `LIFECYCLE_PROMOTE_TO_DEPLOYMENT_READY` rule | calls `cbot_pipeline.build_reliable_cbot` + `compile_engine.validate` + `deployment_report.generate(...)` | ⚠️ cbot_pipeline + compile_engine exist; **deployment_report module missing** (G7) |
| `LIFECYCLE_DEMOTE` rule | logs cause, surfaces on dashboard | ✅ `strategy_lifecycle_history` is populated on every transition |

### 3.2 Specific code-level seams identified
- The execute layer (line 451) already supports new action names — just extend `ACTION_TYPES` + add elif branches.
- The state observed by `observe_state()` already pulls everything needed (live status, recent runs, env_priority, library count, best_candidate). The only missing observation field is the **lifecycle transition stream** — easy: read the last N rows of `strategy_lifecycle_history` per tick.
- The orchestrator can reuse the existing `trigger_consumed = True` guard so promotion rules never fire while a cycle is mid-run (avoids racing the writer of `strategy_library`).

### 3.3 Convergence math (carrying over from §6 of the design)
The model in `STRATEGY_LIFECYCLE_DESIGN_PHASE26_5.md` predicts ~0.3 deployment-ready strategies / 100 generated. At the current cadence (15-min × 8 envs × ~3 strategies = ~24 strategies/tick × 96 ticks/day ≈ 2 300 candidates/day) the ladder should produce **5–7 DEPLOYMENT_READY/day** in steady state — comfortably more than the 3–5 needed for a portfolio. **G6 is therefore the highest-ROI step:** it uncorks the throughput that the rest of the pipeline already supports.

---

## 4. BI5 realism gate (the only architecturally-acceptable BI5 consumer)

### 4.1 Confirmed BID vs BI5 separation
Source-of-truth = `data_engine/data_manager.py`:
```
ALLOWED_SOURCES = ("bid_1m", "bi5")
DEFAULT_SOURCE  = "bid_1m"
```
Validated at every read/write (lines 212, 319). Indexes route `(symbol, source, timeframe)` independently. Legacy rows missing `source` are stamped `bid_1m` (line 464).

### 4.2 Where BI5 is currently consumed
| Module | How it touches BI5 | Expected? |
|---|---|---|
| `engines/paper_execution_engine.start_run(source=...)` | accepts `"bid_1m"` or `"bi5"`; defaults to `bid_1m` (line 67) — only consumed when caller explicitly passes `bi5` | ✅ this is the future BI5 consumer; nothing automatic yet |
| `engines/gem_factory_engine.py` | only documents the BI5 retention policy in a docstring — **does not read BI5** | ✅ no surprise consumer |
| `data_engine/auto_data_maintainer.py` | runs a 60-min BI5 maintenance track (gap detection only — no Dukascopy `.bi5` fetcher; manual chunk-import only); validates BID↔BI5 alignment | ✅ pure data-plane |
| `data_engine/data_backup.py` / `data_manager.py` | exports/imports BI5 separately under `market_data/BI5/<SYMBOL>_<TF>.csv` | ✅ portability only |
| `data_engine/incremental_updater.py` | `incremental_update_bi5()` + `validate_bid_bi5_alignment()` | ✅ ingestion-side only |

### 4.3 Where BI5 is NOT consumed (and rightly so)
- `engines/mutation_engine.py` — defaults to BID via `data_access.load_with_recovery(source="bid_1m")`. Confirmed by reading lines 667 + 1062 (only persists `source="mutation_engine"` for tagging, not data source).
- `engines/auto_mutation_runner.py` — uses `mutation_engine` defaults.
- `engines/backtest_engine.py` — accepts external prices; never asks the DB for source.
- `engines/multi_cycle_runner.py` — no source param.
- `engines/auto_factory*.py` — all variants drive the same chain.

**Conclusion: discovery / mutation / OOS / validation are 100 % on BID.** BI5 is currently a fallow data-plane — exactly the precondition the architecture wants for a *certification-only* realism layer.

### 4.4 What is missing for the realism gate
1. **`engines/bi5_realism.py` module** (does not exist):
   - `evaluate(strategy_hash) -> {pf_ratio, last_checked_at, sample_days, status}` — calls `paper_execution_engine.start_run(portfolio_id=None, source="bi5", bars_limit=…, …)` for the strategy's `(pair, timeframe)`, computes the realism PF ratio against the cached `strategy_library.profit_factor`.
   - Persists to a new `bi5_realism` block on `strategy_library` doc (or to the `strategy_lifecycle` doc — design suggests the lifecycle doc; either is fine).
   - Hooks the `BI5_FAIL` cool-down + `PARTIAL_REALISM` flag computation already encoded in `_gate_deployment_ready` and the flag-emission block in `compute_lifecycle_state` (lines 438–447).
2. **Sunday 03:00 UTC sweep** — a single APScheduler cron on the unified scheduler (post-G2) that loops `PORTFOLIO_WORTHY ∪ DEPLOYMENT_READY` and re-checks any strategy whose `bi5_realism.last_checked_at` is older than 60 days (or absent).
3. **UI pill** in `StrategyDetailsPanel.js` next to `LineageCard`: "BI5 0.82 ✓" / "BI5 0.62 ⚠ partial" / "BI5 cool-down 14d". **Field already plumbed** through lifecycle doc — front-end just hasn't been written.
4. **Test file** `test_bi5_realism.py` — does not exist.

**Crucial constraint preserved:** the realism gate must run **only** on strategies that have already cleared 7 cheap gates (entry to `portfolio_worthy`). The current `paper_execution_engine` already supports `source="bi5"` — there is no engine work, only the wrapper + invocation discipline.

### 4.5 BI5 data availability prerequisite
The auto-maintainer track for BI5 is in place but **`bi5 tick fetcher not wired`** (line 213 of `auto_data_maintainer.py`). If a user has not uploaded BI5 chunks, `paper_execution_engine` will return `insufficient_bars`. The realism gate must therefore:
- **Skip gracefully** (no demotion) when BI5 data is missing — strategies stay at `portfolio_worthy` with a `BI5_DATA_MISSING` flag (would extend `LIFECYCLE_FLAGS`).
- Surface a one-line UI warning so the operator knows to upload BI5 data.

This is the ONLY remaining design ambiguity that needs your sign-off before BI5 work begins.

---

## 5. G7 surface (deployment report)

Module `engines/deployment_report.py` does **not exist**. The constituent inputs **all exist**:
| Input | Source | Status |
|---|---|---|
| Lifecycle snapshot | `strategy_lifecycle.get_lifecycle()` | ✅ |
| Lifecycle history (audit trail) | `strategy_lifecycle.get_lifecycle_history()` | ✅ |
| Library doc (params, metrics) | `strategy_library` collection | ✅ |
| Behavioral profile + win/loss + streak + smoothness | `_attach_behavior_metrics` | ✅ |
| Pass-probability narrative + violations | `get_strategy_details().pass_probability_reasoning` | ✅ |
| Portfolio context | `multi_asset_portfolios` / `portfolio_builder_runs` | ✅ |
| Firm match | `strategy_challenge_match` collection | ✅ |
| Risk allocation | `prop_firm_panel.safe_risk_per_trade` | ✅ |
| BI5 realism block | (pending § 4) | ❌ |
| cBot artifact id + compile status | `cbot_pipeline` + `compile_engine` | ✅ |
| Research-run lineage | `research_lineage.get_runs_for_strategy(hash)` | ✅ |

So G7 is purely **a join + signing module**: read the inputs above, produce a stable JSON, render a Markdown twin, hash-sign both, save to `deployment_reports` collection, return a `report_id`. A new endpoint `GET /api/strategies/{id}/deployment-report` streams the JSON; `?format=md` returns the Markdown.

**UI**: a "Ready to Deploy" widget on the dashboard listing the latest 5 `deployment_ready` strategies + a download-report link (uses the same `data-testid` patterns already in use).

**Implementation order is intentionally last:** G7 cannot produce a clean artifact until BI5 realism is decided AND G6 has populated the lifecycle docs.

---

## 6. Residual fragmentation / cleanup items

These were called out in `ARCHITECTURE_ANALYSIS_PHASE26.md` §1.5 and **none have been addressed yet**. They are **not blocking** for G2 / G6 / BI5 / G7, but they will keep accumulating cost until consolidated:

| Item | Current state | Recommended deferral |
|---|---|---|
| **Auto-factory triplet** — `auto_factory.py` (473 L) + `auto_factory_engine.py` (437 L) + `auto_factory_phase55.py` (659 L) | All three present; UI exposes both `Auto Factory` and `Auto Factory (Legacy)` tabs | Defer to **post-G7**; rename two as `legacy/`; fold style into env_priority later |
| **Three matching engines** — `matching_engine.py` (330) + `challenge_matching_engine.py` (432) + `phase4_matcher.py` (576) | All three; callers spread across api/* | Defer; document call-site map first |
| **Two ranking engines** — `ranking_engine.py` (96) + `strategy_ranking_engine.py` (248) | Both present | Defer; thin re-export |
| **UI button clutter** | Explorer header + numerous tabs (`Auto Factory`, `Auto Factory (Legacy)`, `Pipeline`, `Workspace`, `Optimization`, `Multi-Cycle`) | Defer until G6 closes the autonomous loop; then collapse into "Manual Tools" sub-menu |
| **Stale `__pycache__`** in `tests/__pycache__/` | Includes `.cpython-311-pytest-9.0.3.pyc` for `test_strategy_lifecycle_phase26_5*` and `test_research_lineage_g1` | Cosmetic — auto-regenerated on next run |

The previous "credits exhausted during cleanup" item refers to these — **the actual project artifacts (Mongo, lineage docs, lifecycle docs) are clean**; only the .pyc residue is stale.

---

## 7. Lifecycle UI delta (the one frontend gap that *does* block G6)

`StrategyExplorer.js` line 1239:
```jsx
<StageBadge stage={v.stage} />
```
This still renders the **legacy 4-stage** label that comes from `validation.stage` (set by `_attach_validation_view`, lines 528–555 of `strategy_memory.py`).

The 8-stage value is already on the row at `validation.lifecycle_stage` / `validation.lifecycle_stage_rank` / `validation.lifecycle_flags` / `validation.lifecycle_cool_down_until`.

**Required minimal change**: add a second badge alongside the existing one (or extend `<StageBadge>` to honour `lifecycle_stage` when present, falling back to legacy `stage`). This is the cosmetic surface the design called for in §7. It is **non-blocking** for backend G6 work but **must land before** the deployment-report widget so the operator can see graduations.

---

## 8. Convergence + finishing condition

The design (§6 of the lifecycle doc) already specifies the convergence target. Reading it against current code:

- **Throughput limit** is set by `env_priority.max_env_share = 0.80` (no env >80 % of allocation), `exploratory_floor = 0.05`, and `BATCH_SIZE_CAP = 8` in `ai_orchestrator`. With these constants ~2 300 candidates/day flow through the gates.
- **Finishing condition** as designed: when 5 `portfolio_worthy` strategies are `deployment_ready`, the orchestrator throttles discovery to a 1-hour cadence. **This logic is not yet present in the orchestrator**; it is part of the G6 deliverable. Without it, the system will keep generating after the portfolio is full — the loop is bounded only by cost, not by goal completion.

---

## 9. Recommended roadmap (no scope expansion)

```
                 (sequence preserves architectural correctness)

   Phase 27.1  G2   scheduler unification               (S — 1 session)
        │
        ▼
   Phase 27.2  G6   lifecycle_evaluator job             (S — 1 session)
                    + LIFECYCLE_PROMOTE_TO_*  rules     (M — 1 session)
                    + auto_build_portfolio action
                    + Explorer 8-stage chip surface     (S — 0.5 sessions)
        │
        ▼
   Phase 27.3  BI5  engines/bi5_realism.py              (M — 1 session)
                    + Sunday 03:00 UTC sweep            (S — 0.5 sessions)
                    + StrategyDetailsPanel BI5 pill     (S — 0.5 sessions)
                    + LIFECYCLE_DATA_MISSING flag       (S — 0.5 sessions)
                    + test_bi5_realism.py
        │
        ▼
   Phase 27.4  G7   engines/deployment_report.py        (M — 1 session)
                    + GET /api/strategies/{id}/deployment-report
                    + Dashboard "Ready to Deploy" widget
                    + Finishing-condition throttle      (S — 0.5 sessions)

                          Total ≈ 5–6 sessions of additive,
                          no-engine-rewrite work.
```

Estimated lines of new code total < ~1 800 across all four phases (gate-rule glue, sweep cron, report joiner, frontend chip + pill + widget). No engine rewrites. No duplicate pipelines. Each phase is independently revertible behind a feature flag (`orchestrator_scheduler_config.lifecycle_rules_enabled`, `bi5_realism_enabled`, `deployment_reports_enabled`).

---

## 10. Open questions (need user sign-off before Phase 27.1 begins)

1. **G2 option A vs B** — should `auto_scheduler` become a **subordinate no-op while orchestrator is on** (option A — simpler, same UX), or should it be **merged into the orchestrator's APScheduler instance with its own rule_id** (option B — single scheduler, more refactor)? My recommendation: **A** for this cycle; revisit B in a later cleanup phase.
2. **BI5 data-missing strategy** — when BI5 tick data isn't available, should affected strategies (a) **stay at `portfolio_worthy` with `BI5_DATA_MISSING` flag** (advisory; preserves discovery throughput) or (b) **block at `portfolio_worthy` until data arrives** (stricter; halts deployment until operator uploads BI5)? My recommendation: **(a)** with a UI banner.
3. **Deployment-report delivery mode** — auto-email/auto-webhook on graduation, or operator-pull only (download link)? My recommendation: **operator-pull only** for v1; auto-delivery as a configurable add-on later.
4. **Cohort window for ELITE percentile** — current code passes the current Explorer-fetch's library docs as the cohort. That's the **correct behaviour** (rolling). Confirming OK; no change needed unless you want a 30-day filter applied at cohort selection.
5. **Lifecycle UI** — show **only** the new 8-stage chip, or **both** the legacy 4-stage and new 8-stage? Recommendation: **only 8-stage on Explorer**, with a tooltip explaining the bridge ("STABLE = VALIDATED + cross-run consistency", etc.). Legacy `validation.stage` field stays in the API response for any downstream consumer.

---

## 11. Summary

- **Skeleton complete.** Phases 25 / 26 / 26.5 / G1 are all closed and tested; the lifecycle module computes all 8 stages over cached fields with hysteresis, cohort-aware ELITE gate, BI5 cool-down, STALE flag, and audit-log persistence.
- **Glue is the bottleneck.** The orchestrator does not yet read `lifecycle_stage`; nothing automatically advances a strategy past `prop_safe`; BI5 realism exists as a runnable code path but no system invokes it; deployment reports are not generated.
- **Four discrete, additive moves remain**: G2 (scheduler unification), G6 (lifecycle rules + executor), BI5 realism gate, G7 (deployment report). Each is a small, independently-reversible delta — together they convert the factory from "good research engine that loops forever" into "autonomous research factory with a finishing condition".
- **No engine rewrites required**, no duplicate pipelines introduced, no UI proliferation. The remaining UI surface is a single chip change on Explorer + one pill in Details + one widget on Dashboard.

This document is the architectural baseline for Phase 27. Recommended next step: confirm the answers to §10 and proceed with **G2 (Phase 27.1)** as the next implementation slice.
