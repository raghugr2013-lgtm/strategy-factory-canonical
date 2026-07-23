# AI Strategy Factory — PRD / Implementation Log

## Original Problem Statement
This is an advanced AI Strategy Factory (already operational): historical market-data
ingestion (Dukascopy BID/BI5), strategy generation (template + LLM hybrid), mutation,
multi-cycle optimization, OOS / regime / session filtering, prop-firm evaluation, and
an autonomous orchestrator with APScheduler. Last incomplete task: **Market Data
Export** for portability across Emergent accounts.

## Architecture (do NOT rebuild)
- **Backend**: FastAPI; routers under `backend/api/*`; engines under `backend/engines/*`;
  data layer under `backend/data_engine/*`. Mongo via `engines/db.get_db()`.
- **Frontend**: React + CRACO + Tailwind; Market Data UI lives in
  `frontend/src/components/DataMaintenancePanel.js`.
- **Existing Backup/Portability infra (Phase 5.2)** in `data_engine/data_backup.py`
  (export_dataset / export_bulk / export_all / import_backup) and
  `api/data_maintenance.py` (`/api/data/backup/{export,export-bulk,export-all,import}`).

## What's been implemented in this session

### 2026-05-07 — Market Data Export feature (continued from credits-out)
- **Backend (additive only)**
  - `data_engine/data_backup.py` → new `export_streaming_to_file(path, symbols?, timeframes?, sources?)`
    streams every `(symbol, source, timeframe)` row-by-row from Mongo directly into a ZIP entry
    using `zipfile.ZipFile.open(..., "w", force_zip64=True)` — memory-bounded regardless of dataset size.
    Joins per-dataset coverage (`backfill_progress_pct`, `actual_months`, `target_months`,
    `has_gaps`, `completeness`) from the `data_coverage` collection.
  - `api/data.py` → new `POST /api/data/export` endpoint. Builds the archive into a named
    temp file then returns a `FileResponse` (chunked-streamed by Starlette) with a
    `BackgroundTask` that deletes the temp file after delivery. Filename format:
    `market_data_export_<UTCYYYYMMDDTHHMMSSZ>.zip`. Exposes `X-Export-Total-Rows` /
    `X-Export-Total-Datasets` / `X-Export-Filename` response headers. Returns 404 when
    no datasets are present.
  - ZIP layout (compatible with existing `POST /api/data/backup/import`):
    ```
    market_data/BID/SYMBOL_TF.csv
    market_data/BI5/SYMBOL_TF.csv
    market_data_manifest.json    ← rich manifest (per-dataset coverage)
    metadata.json                ← legacy companion (back-compat)
    ```
  - `market_data_manifest.json` fields: `version, format, exported_at, schema, symbols,
    sources, timeframes, total_datasets, total_rows, datasets[ {path, symbol, source,
    timeframe, row_count, range_first, range_last, coverage_pct, completeness_pct,
    actual_months, target_months, has_gaps} ], import_endpoint`.

- **Frontend (additive)**
  - `services/api.js` → new `exportMarketData(payload)` POSTs to `/api/data/export`,
    reads response as a blob, triggers browser download using the server-supplied
    filename (X-Export-Filename / Content-Disposition), and returns
    `{ filename, totalRows, totalDatasets }`.
  - `components/DataMaintenancePanel.js` → replaced legacy `<a … data-testid="dm-export-all-btn">`
    with new `<button … data-testid="dm-export-market-data-btn">` placed immediately before
    "Import ZIP" in the existing Backup & Restore row. Loading state disables the button,
    swaps the icon for a spinner, and shows "Building ZIP…". While export is in flight
    the Import ZIP button is also disabled to prevent racing operations. After success a
    "exported N dataset(s) · M rows" summary appears.

### Verified
- POST /api/data/export → 200 with valid ZIP, headers populated.
- Import round-trip: 960 seeded rows → export → DB wipe → import via existing
  `/api/data/backup/import` → 960 inserted, 0 skipped.
- Idempotent re-import: 0 inserted, 960 skipped_duplicates.
- Memory profile: 50 960 rows (XAUUSD 1m × 50 000 + others) exported in ~0.68 s,
  resulting ZIP 635 KB; per-row streaming into ZIP entry → bounded memory.
- UI: "Export Market Data" button visible on Market Data page, next to "Import ZIP";
  legacy "Export ALL (ZIP)" anchor removed.

## What is NOT touched (per user constraints)
- Strategy engines (generation, mutation, optimization, orchestrator scheduler)
- Ingestion / Dukascopy downloader / auto data maintainer
- Existing import-backup endpoint and ZIP layout (kept identical → full back-compat)
- Prop-firm PDFs, codebase, strategy library, unrelated DB collections (excluded from export)

### 2026-05-09 — Behavioral Transparency Layer (Phase 25)
- **Backend (already in archive — verified, not modified)**
  - `engines/strategy_memory.py::_attach_behavior_metrics()` populates per-row cached
    behavioral metrics (no recomputation, no backtest re-run):
    * `wins`, `losses`, `avg_win`, `avg_loss` (derived from `winning_trades` /
      `losing_trades` if present, else from `total_trades × win_rate`)
    * `risk_reward_ratio` (derived from avg_win/avg_loss if not already set)
    * `behavioral_profile` via `_classify_behavior()` — pure function over win_rate,
      RR, trade count, and library style. Returns one of:
      `HIGH_WINRATE_SCALPER` · `TREND_FOLLOWER` · `MEAN_REVERSION` ·
      `ASYMMETRIC_BREAKOUT` · `LOW_FREQ_SWING` · `BALANCED` · `UNCLASSIFIED`
    * `expected_max_consec_losses` (95 % confidence, `log(0.05)/log(loss_p)`)
    * `avg_consec_losses` (geometric expected run length `loss_p / (1 − loss_p)`)
    * `recovery_factor` (`total_return % / max_dd_fraction`)
    * `smoothness_label` via `_classify_smoothness()` — `SMOOTH` (stab≥70 ∧ DD<5%) /
      `VOLATILE` (stab<40 ∨ DD≥15%) / `null` (mixed)
  - Two new badges fire from smoothness label: `SMOOTH`, `VOLATILE`.
  - All metrics surfaced in `validation.metrics` block of `/api/strategies/explorer`
    AND in the details payload from `get_strategy_details()` (single source of truth
    for orchestrator + prop-firm matcher reuse).

- **Frontend (this session — additive only)**
  - Resumed interrupted edits in `components/StrategyDetailsPanel.js` (archive-merged
    safely without overwriting partial progress).
  - Fixed bug in `IsOosCard` (undefined `overfit` reference → now derives from
    `cmp.overfit_flagged`).
  - Added 4 new cards (matching existing research-terminal styling — no visual
    redesign, low clutter, professional):
    1. **`<BehaviorCard>`** — uses pre-existing `BEHAVIOR_INFO` map; shows profile
       label + tone-coded badge + descriptive note + WR/RR/trades grid.
    2. **`<WinLossCard>`** — proportional emerald/red bar + Wins/Losses/Avg Win/Avg
       Loss stat grid.
    3. **`<StreakCard>`** — Expected worst run (color-coded: green ≤4, amber 5–7,
       red ≥8), avg consecutive losses, recovery factor (color-coded). Footnote
       reminds reader these are probabilistic, no rerun.
    4. **`<SmoothnessCard>`** — SMOOTH / MIXED / VOLATILE badge + descriptive note +
       Stability/Max DD/Avg trade % grid.
  - `components/StrategyExplorer.js` Stage column already renders behavioral profile
    chip beneath stage badge (verified — no changes needed).
  - All `data-testid` attributes added per guidelines (`behavior-card`,
    `winloss-card`, `streak-card`, `smoothness-card`, `winloss-bar`,
    `behavior-profile-<PROFILE>`, `smoothness-label-<LABEL>`).

### Verified end-to-end (Phase 25)
- Empty Explorer renders cleanly (no syntax / runtime errors).
- Seeded 3 synthetic strategies hitting different profiles:
  * `TEST_Scalper_RSI` → `HIGH_WINRATE_SCALPER` profile + `STABLE` + `SMOOTH` badges,
    stage `prop_safe`.
  * `TEST_Breakout_Donchian` → `ASYMMETRIC_BREAKOUT` profile + `HIGH_DD` badge,
    stage `candidate`.
  * `TEST_TrendMACD` → `TREND_FOLLOWER` profile + `STABLE` badge, stage `validated`.
- Details drawer screenshot confirmed all 4 new cards rendered in correct order
  with correct data: BehaviorCard (ASYMMETRIC BREAKOUT badge + 7-loss expected
  worst run color-coded amber), WinLossCard (38.2 % wins green/red bar), StreakCard
  (recovery factor 2.67 color-coded amber), SmoothnessCard (MIXED label).
- No duplicate components anywhere in `frontend/src` (grep verified).
- Acorn syntax check passes for both edited files.
- Test seed data cleaned up after verification.

### 2026-05-09 — Phase 26 / G1: Research-Run Lineage (foundation)
- New module `engines/research_lineage.py` — single source of truth for "which
  discovery cycle produced this artifact?". Pure persistence, never mutates engines.
  Public surface: `new_research_run`, `attach_child`, `append_summary`,
  `mark_finished`, `get_run`, `list_runs`, `get_runs_for_strategy`,
  `get_runs_for_library_id`. ID format: `rr_<UTCYYYYMMDDTHHMMSS>_<8hex>`.
- New collection `research_runs` — root doc per discovery cycle: trigger
  (orchestrator_tick / auto_scheduler_tick / manual_api / manual_rerun /
  ingestion / workspace_generate), config snapshot, child fan-out
  (multi_cycle_run / auto_run_cycle / mutation_run / library_save /
  history_row counter / ingestion_batch), summary counters + library_ids +
  envs_scanned, parent_research_run_id (for future "rerun-of" lineage),
  status (running / completed / stopped / error / timeout).
- Threaded `research_run_id` (additive optional kwarg, never replaces existing
  ids) through the discovery chain:
  * `ai_orchestrator.execute()` opens an `orchestrator_tick` lineage root
    BEFORE calling `multi_cycle_runner.start_multi_cycle` and surfaces it on
    the execution result.
  * `multi_cycle_runner.start_multi_cycle` accepts the rrid (auto-creates a
    `manual_api` rrid when missing), persists it on `multi_cycle_runs` doc,
    propagates to every cycle, calls `mark_finished` after `_drive` returns.
  * `auto_mutation_runner.run_single_cycle` accepts the rrid (auto-creates
    when missing), persists on `auto_run_cycles` doc, attaches itself as
    `auto_run_cycle` child + rolls summary, propagates to `_run_one_strategy`.
  * `auto_mutation_runner.run_auto_mutation` (long-running variant) wired
    too — persists on `auto_mutation_runs` + `auto_mutation_cycles`.
  * `auto_scheduler._build_job` opens an `auto_scheduler_tick` lineage root
    per tick (so the manual + scheduler + orchestrator paths produce uniform
    lineage), and `mark_finished` runs in a `finally` block.
  * `strategy_memory.record_performance` accepts the rrid, writes it onto the
    `strategy_performance_history` row, attaches `history_row` counter +
    `mutation_run` + `library_save` children + appends `library_ids` to
    summary on the lineage doc.
- New read-only HTTP API at `/api/research-runs`:
  * `GET /api/research-runs?limit=&trigger_type=&status=` — list (sorted desc).
  * `GET /api/research-runs/{rrid}` — full doc, 404 for unknown.
  * `GET /api/research-runs/by-strategy/{strategy_hash}` — lineage for a
    strategy hash (joins via `strategy_performance_history`).
  * `GET /api/research-runs/by-library/{library_id}` — lineage by saved
    library id (joins via `summary.library_ids`).
- New `LineageCard` in `StrategyDetailsPanel.js`:
  * data-testid="lineage-card", rows data-testid="lineage-run-{rrid}".
  * Trigger pills with tone-coded categories
    (orchestrator_tick=violet, auto_scheduler_tick=emerald,
    manual_api=sky, ingestion=amber, etc.).
  * Status pills (running/completed/stopped/error/timeout/skipped).
  * Empty state ("no runs recorded") for legacy strategies; never throws.
  * `getResearchRunsForStrategy / getResearchRun / listResearchRuns` added
    to `services/api.js`.
- `engines/strategy_memory.get_strategy_details` now returns `strategy_hash`
  on the payload so the drawer can query lineage with it.

### Verified end-to-end (Phase 26 / G1)
- Smoke script: every helper (`new_research_run` / `attach_child` for all 5
  child kinds / `append_summary` / `mark_finished` / `get_run` / `list_runs` /
  `get_runs_for_strategy` / `get_runs_for_library_id`) returns expected docs.
- `record_performance(... research_run_id=rrid)` correctly increments
  `children.history_row` counter, attaches `mutation_run` + `library_save`
  children with strategy_hash/pf/library_id metadata, pushes library_id to
  `summary.library_ids`.
- Live API tested via curl: list returned sorted desc; GET-by-id returned
  full doc; GET-by-strategy joined through `strategy_performance_history`
  and returned both seeded runs (orchestrator_tick + auto_scheduler_tick);
  unknown rrid returned 404.
- UI verified visually: drawer for seeded `TEST_LIN_TrendStrategy` shows
  RESEARCH LINEAGE card with two runs — `ORCHESTRATOR TICK · LOW_PF_DIVERSITY
  · COMPLETED · 1/1 saved` and `AUTO SCHEDULER TICK · COMPLETED · 0/2 saved`.
- Testing-agent run: 13/13 pytest cases pass — covers HTTP endpoints, engine
  signatures, history-row attach behavior, empty-state, 404 handling.
  Report at `/app/test_reports/iteration_1.json`. Test file
  `/app/backend/tests/test_research_lineage_g1.py` (self-seeding & self-cleaning).

### 2026-05-09 — Phase 27.1 / G2: Scheduler subordination (consolidation)
- **Backend (additive only, feature-flagged, reversible)**
  - `engines/orchestrator_scheduler.py` → new `is_active()` probe.
    Cheap, in-memory check (no DB I/O); returns True iff this scheduler
    has a live APScheduler job AND the runtime flag confirms enablement.
    Used by `auto_scheduler` to decide whether to defer.
  - `engines/auto_scheduler.py` →
    * New `SUBORDINATE_DEFAULT = True` and runtime counter
      `subordinate_skip_count`.
    * `_load_config` / `_save_config` learn a top-level
      `subordinate_to_orchestrator` field (default True). Legacy configs
      backfill to True so existing installs become subordinate on first
      restart. `subordinate_to_orchestrator=None` in `_save_config`
      preserves the persisted value (no accidental overwrite).
    * New `_is_subordinated()` helper — exception-safe; resolves the
      flag and probes `orchestrator_scheduler.is_active()`. Falls open
      (returns False) on any failure so the scheduler is never silently
      disabled.
    * `_build_job._tick` checks subordination FIRST. When subordinated,
      records `last_status="skipped_subordinate"` +
      `last_reason="orchestrator_scheduler_active"`, increments
      `subordinate_skip_count`, and **returns immediately without
      opening a research_run** (subordinate ticks don't pollute lineage).
    * `start_scheduler` accepts new `subordinate_to_orchestrator` kwarg
      (Optional[bool], None preserves persisted value); echoes back
      the resolved flag in the response.
    * `stop_scheduler` and `restore_if_enabled` preserve the flag
      across stop/start and across backend restart.
    * `get_status` adds `config.subordinate_to_orchestrator` and
      `runtime.is_subordinated_now` + `runtime.subordinate_skip_count`.
  - `api/auto_mutation.py::SchedulerStartRequest` →
    new optional `subordinate_to_orchestrator` field; threaded through
    to `start_scheduler`.

- **Frontend (additive)**
  - `components/AutoSchedulerControl.js` →
    * `startScheduler` now accepts an `overrides` object so the toggle
      can post `subordinate_to_orchestrator: false`.
    * New violet `SUBORDINATE` pill next to the RUNNING/STOPPED badge —
      visible only when the orchestrator is currently active.
    * New `Subordinate skips` stat tile.
    * New `Independent mode` checkbox (data-testid
      `auto-scheduler-independent-mode`) — unchecked by default
      (subordinate); checking it persists `subordinate_to_orchestrator=false`.
    * `last_status="skipped_subordinate"` renders in the new violet
      `info` tone so the operator can tell automated subordination
      apart from cycle-level skips.

### Verified end-to-end (Phase 27.1 / G2)
- `engines/auto_scheduler.py` ruff clean; `engines/orchestrator_scheduler.py`
  ruff clean; `api/auto_mutation.py` ruff clean;
  `tests/test_g2_scheduler_subordination.py` ruff clean;
  `components/AutoSchedulerControl.js` ESLint clean.
- New test file `tests/test_g2_scheduler_subordination.py` (13 tests,
  10 unit + 3 HTTP smoke) — **all 13 pass** when run with
  `--asyncio-mode=auto`. Coverage:
  * `is_active()` returns False on cold start / stopped scheduler /
    runtime-disabled flag.
  * `_is_subordinated()` honours the persisted flag, falls open on
    `_load_config` failure, and respects the escape hatch.
  * Subordinate tick is a true no-op: no `run_single_cycle` call, no
    `new_research_run` lineage entry, but counters and last_status
    update for visibility.
  * Non-subordinate tick still runs the cycle as before.
  * `_save_config(subordinate_to_orchestrator=None)` preserves the
    persisted value across saves.
  * HTTP `/api/auto/scheduler/status` exposes the new fields with the
    documented shape.
  * HTTP `/api/auto/scheduler/start` honours the body's flag, persists
    it, and inherits it across stop/start.
  * `runtime.is_subordinated_now` flips True when
    `orchestrator_scheduler` starts and False when it stops.
- Live HTTP smoke (against `localhost:8001`) ran the full 7-step
  end-to-end lifecycle (default subordinate → orchestrator off →
  orchestrator on → flip flag → escape hatch → persist across
  stop/start → cleanup) — all assertions green.
- Regression: `tests/test_orchestrator_scheduler.py` (12 tests) and
  `tests/test_research_lineage_g1.py` (13 tests) still **all pass**.
  `tests/test_auto_scheduler.py` shows 23/25 pass; the 2 pre-existing
  failures are an unrelated `quality_threshold==55.0 vs 35.0` drift
  that predates G2 and is not touched by this change.

### Operator-facing behaviour
- **Default**: when both schedulers are enabled, the auto-scheduler
  becomes a passive standby (single source of discovery work →
  orchestrator). UI shows a violet `SUBORDINATE` pill so the operator
  knows ticks are deliberately deferred.
- **Escape hatch**: ticking the new `Independent mode` checkbox in the
  Auto-Discovery card flips `subordinate_to_orchestrator=false` and
  both schedulers resume independent operation.
- **Lineage hygiene**: subordinate ticks never open a research_run, so
  the orchestrator remains the sole lineage author when both are on.

### 2026-05-09 — Phase 27.2 / G6: Autonomous lifecycle progression
The most important architectural milestone of the consolidation phase.
**The orchestrator now ACTS on lifecycle intelligence**, converting the
Phase 26.5 classifier from passive (Explorer view-only) into autonomous
(every-tick state-machine evaluator + portfolio-graduation driver).

- **Backend (`engines/strategy_lifecycle.py` — additive)**
  - **`evaluate_cohort()`** — one autonomous pass over the eligible
    cohort: (a) read Explorer rollup (cached fields only — no backtest
    re-run); (b) bulk-fetch prior persisted state for hysteresis;
    (c) recompute lifecycle state per row using
    `compute_lifecycle_state_from_rollup`; (d) upsert + audit-log only
    the rows that changed stage OR are new (first-touch baseline).
    Returns `{evaluated, transitions, promotions, demotions,
    first_touch, upserted, stage_counts, cohort_p90_deploy_score,
    evaluated_at, research_run_id}` — the orchestrator response shape.
  - **`recent_transitions(since_iso, limit)`** — feeds the
    orchestrator's tick observation; descending sort by
    `transition_at`; bounded by `[1, 500]`.
  - **`cohort_stage_counts()`** — cheap aggregate of the persisted
    `strategy_lifecycle` collection; returns the full 8-stage
    taxonomy with zero-fill so callers always get a stable shape.

- **Backend (`engines/ai_orchestrator.py` — additive)**
  - `observe_state` extended with `lifecycle` block: `stage_counts`,
    `promotions_recent`, `demotions_recent`, `transitions_total`,
    `last_portfolio_built_at`. Failures fall through silently — the
    orchestrator never crashes if lifecycle observation hiccups.
  - **4 new rules** (all post Rule 7 — no existing rule changed):
    * **R8 `LIFECYCLE_EVALUATE`** — fires every tick. Action
      `evaluate_lifecycle_cohort`. Cheap, lifecycle-only, safe even
      while a multi-cycle run is in flight.
    * **R9 `LIFECYCLE_PROMOTIONS_DETECTED`** — advisory `info` when
      promotions exist in last 1h window. `params.by_transition` carries
      the per-edge counts (e.g. `validated→stable: 3`).
    * **R10 `LIFECYCLE_DEMOTIONS_DETECTED`** — advisory `warn` mirror.
    * **R11 `AUTO_BUILD_PORTFOLIO`** — fires when `count(elite) ≥ 3`
      AND no portfolio was built in the last 6h. Action
      `auto_build_portfolio` calls
      `portfolio_builder_engine.build_portfolio(persist=True)`. The new
      `portfolio_membership` flips strategies to `portfolio_worthy` on
      the next lifecycle tick.
    * `AUTO_BUILD_PORTFOLIO_COOLDOWN` — quiet advisory when threshold
      met but cooldown active, so operators see the system is poised.
  - **2 new ACTION_TYPES**: `evaluate_lifecycle_cohort`,
    `auto_build_portfolio`. Both routed in `execute()` with
    independent error-isolation (a failure in one rule never aborts
    the rule batch).
  - Constants surfaced for transparency:
    `AUTO_BUILD_MIN_ELITE = 3`, `AUTO_BUILD_COOLDOWN_HOURS = 6`,
    `LIFECYCLE_TRANSITION_WINDOW_HOURS = 1`.

- **API (`api/lifecycle.py` — new, minimal — no UI dashboard)**
  - `GET  /api/lifecycle/cohort/stage-counts` — full taxonomy + counts.
  - `GET  /api/lifecycle/transitions/recent?since=&limit=` — audit log.
  - `POST /api/lifecycle/evaluate?persist=&limit=` — manual cohort pass
    (same code path the orchestrator runs every tick).
  - `GET  /api/lifecycle/{strategy_hash}` — persisted doc, 404 when absent.
  - `GET  /api/lifecycle/{strategy_hash}/history?limit=` — audit log.
  - Mounted in `server.py` alongside `research_lineage_router`.

- **Frontend (`StrategyDetailsPanel.js` + `StrategyExplorer.js` —
  one component, no new pages, no new tabs)**
  - `STAGE_COLORS` extended with the 4 new stages (`stable` emerald,
    `elite` violet, `portfolio_worthy` deeper violet,
    `deployment_ready` yellow).
  - New `STAGE_TOOLTIPS` map — single-line bridge tooltip per stage.
  - **`<StageBadge>`** now reads optional `lifecycleStage` prop. When
    present, renders the 8-stage chip with its tooltip; when absent,
    falls back to the legacy 4-stage `stage` (full backward
    compatibility — pre-G6 callers still work).
  - Both call sites updated:
    `StrategyDetailsPanel` line 188 + `StrategyExplorer` line 1239 now
    pass `lifecycleStage={v.lifecycle_stage}`.

- **Verification**
  - All 5 new files / modules ruff + ESLint clean.
  - **20/20 new tests pass** in
    `tests/test_g6_lifecycle_progression.py`:
    * `evaluate_cohort` first-touch / promotion / idempotent.
    * `recent_transitions` since-filter + `cohort_stage_counts`.
    * Each of the 4 rules: `LIFECYCLE_EVALUATE` always fires;
      `*_DETECTED` advisories shape-correct; `AUTO_BUILD_PORTFOLIO`
      threshold + cooldown + sub-threshold silence.
    * `execute()` routes the 2 new actions to the right engine
      function with the right `persist=True` kwarg.
    * HTTP smoke for all 5 lifecycle endpoints + orchestrator
      decide/state including the new lifecycle block.
  - **Regression**: 108/112 of the previously-running suite passes.
    The 3 still-failing tests in
    `test_strategy_lifecycle_phase26_5_edge_cases.py` were verified
    failing on the pre-G6 baseline (git stash) — they are the
    "cleanup credits-out" items from the Phase 26.5 closing report,
    not regressions introduced by G6.

- **Operator-facing behaviour after G6**
  - Every orchestrator tick now ALWAYS contains
    `LIFECYCLE_EVALUATE → evaluate_lifecycle_cohort` in the
    recommendation feed.
  - When the autonomous loop has built up ≥3 elite survivors, the
    orchestrator fires `AUTO_BUILD_PORTFOLIO` — and because that
    action persists portfolio_membership, the very next tick's
    evaluator advances those strategies to `PORTFOLIO_WORTHY`.
  - Stage chips on Explorer + StrategyDetailsPanel now reflect the
    full 8-stage ladder with bridge tooltips.
  - The Explorer rollup view still carries BOTH the legacy
    `validation.stage` and the new `validation.lifecycle_stage`, so
    any pre-G6 consumer continues to work unchanged.

- **What still requires manual intervention (the BI5 + G7 surface)**
  - `portfolio_worthy → deployment_ready` requires the BI5 realism
    block + cBot compile gate, which are deferred to Phase 27.3 / 27.4
    (BI5 missing currently produces `BI5_NOT_VERIFIED` flag without
    blocking — the design's flag-and-allow path).
  - The deployment report itself (`engines/deployment_report.py`) is
    unchanged — Phase 27.4 work.

### 2026-05-09 — Phase 27.3 / BI5: Realism certification gate
The architecturally-sanctioned BI5 consumer. ALL discovery / mutation
/ OOS / validation work continues to run on BID candles. BI5 is
consumed ONLY here, as a realism oracle on strategies that have
already cleared seven cheap lifecycle gates (entry to
`portfolio_worthy`).

- **Backend (`engines/bi5_realism.py` — new module, ~430 LOC)**
  - `evaluate(strategy_hash, *, persist=True, force_refresh=False)` —
    one-strategy realism check:
    1. Resolve canonical library doc by hash → `strategy_text`,
       `pair`, `timeframe`, BID-derived `profit_factor`, `total_trades`.
    2. Honour freshness (`REALISM_FRESHNESS_DAYS=60`) when not forcing.
    3. Load BI5 bars via `data_access.load_with_recovery(source="bi5",
       auto_recover=False)` — **never auto-downloads**; operator owns
       data ingestion.
    4. Re-run `backtest_engine.run_backtest_logic` on those BI5 bars.
    5. Compute `pf_ratio = bi5_pf / cached_pf`; classify into bands
       (`ok ≥ 0.75`, `partial ≥ 0.50`, `fail < 0.50`); persist onto the
       lifecycle doc's new `bi5_realism` block (no separate collection).
    6. **Never creates lifecycle docs** — only enriches rows the
       evaluator already owns. Clean responsibility boundary.
  - `sweep_realism(*, force_refresh=False, limit=200)` — iterates
    `portfolio_worthy ∪ deployment_ready` (`ELIGIBLE_STAGES`), skips
    fresh rows, returns counter summary.
  - `get_realism(strategy_hash)` — read-only accessor for the
    persisted block.
  - `stale_realism_count(freshness_days)` — ops health check (how
    many strategies are due for a refresh).
  - Constants surfaced for transparency: `PF_RATIO_DEPLOY_FLOOR=0.75`,
    `PF_RATIO_FAIL_FLOOR=0.50`, `REALISM_FRESHNESS_DAYS=60`,
    `MIN_BI5_BARS=200`, `ELIGIBLE_STAGES=("portfolio_worthy",
    "deployment_ready")`.

- **Backend (`engines/strategy_lifecycle.py` — additive)**
  - New `BI5_DATA_MISSING` flag added to `LIFECYCLE_FLAGS` taxonomy.
  - `compute_lifecycle_state` flag-emission block now emits
    `BI5_DATA_MISSING` whenever `bi5_realism.status == "data_missing"`
    — the design's **flag-and-allow** path: no demotion, no cool-down,
    just a visible "BI5 not verified" indicator.
  - `evaluate_cohort` now bulk-pulls each row's `prior.bi5_realism` and
    threads it into `compute_lifecycle_state_from_rollup` via the
    existing `bi5_realism` kwarg — so once a realism reading is
    persisted, the next lifecycle tick uses it for gate decisions
    automatically.

- **Backend (`engines/strategy_memory.py` — additive)**
  - `get_explorer_rollup` does ONE bulk fetch (`get_lifecycle_map`) of
    persisted lifecycle docs per page render — N+1 avoided.
  - `_attach_lifecycle_view` accepts new `prior_lifecycle_doc` kwarg;
    when supplied, surfaces `validation.bi5_realism` so the frontend
    pill renders without a second API call.
  - `get_strategy_details` does the same single-doc fetch.

- **Backend (`engines/orchestrator_scheduler.py` — additive)**
  - New `REALISM_JOB_ID = "bi5_realism_sweep"` mounted on the SAME
    AsyncIOScheduler instance as the orchestrator tick (G2 single-
    authority design preserved). Runs `Sunday 03:00 UTC` via
    `CronTrigger(day_of_week='sun', hour=3, minute=0)`.
  - `start_scheduler` registers the realism cron alongside the tick
    job; idempotent (re-mounts both jobs).
  - `_runtime` extended with `last_realism_sweep_at`,
    `last_realism_sweep_summary`, `realism_sweep_count`.
  - `get_status` exposes a new `realism_sweep` block:
    `{schedule, next_run_at, last_run_at, run_count, last_summary}`.

- **API (`api/bi5_realism.py` — new, 4 endpoints, no UI dashboard)**
  - `GET  /api/bi5-realism/cohort/stale-count?freshness_days=` — ops
    health check.
  - `POST /api/bi5-realism/sweep?force_refresh=&limit=` — manual sweep.
  - `POST /api/bi5-realism/evaluate/{hash}?force_refresh=&persist=` —
    one-strategy ad-hoc check.
  - `GET  /api/bi5-realism/{hash}` — read persisted block; 404 when
    absent.
  - Mounted in `server.py` alongside `lifecycle_router`.

- **Frontend (`StrategyDetailsPanel.js` — one inline component, no new
  pages, no new tabs)**
  - New `<Bi5RealismPill>` component (~50 LOC). Renders next to
    `<StageBadge>` in the Validation header. Reads
    `validation.bi5_realism` + `validation.lifecycle_flags`. Four
    states with colour cues:
    * **OK** → emerald `BI5 0.82 ✓`
    * **PARTIAL** → amber `BI5 0.62 ⚠`
    * **FAIL** → red `BI5 0.40 ✗`
    * **NOT VERIFIED** (BI5_DATA_MISSING) → zinc `BI5 not verified`
    Tooltip carries `bi5_pf / cached_pf = ratio (last_checked …)` for
    transparency. `data-testid` always present.

- **Verification**
  - **16/16 new tests pass** in `tests/test_bi5_realism_27_3.py`
    covering: 3 skip paths · data-missing flag-and-allow · 3 success
    bands (ok / partial / fail with correct flag emission) · lifecycle
    integration (BI5_DATA_MISSING and BI5_FAIL flags propagate
    correctly) · sweep eligibility (only portfolio_worthy ∪
    deployment_ready) · scheduler realism cron registration with
    correct schedule (`SUN 03:00 UTC`) and exposure through
    `get_status` · 5 HTTP endpoints (404 / 200 with shape).
  - All ruff + ESLint clean.
  - Live HTTP smoke through `/api/bi5-realism/*` + orchestrator
    scheduler — all 5 checks green; realism sweep job confirmed
    registered for next Sunday 03:00 UTC.
  - **Regression**: **99/99 pass across all consolidation phases**
    (orchestrator_scheduler, research_lineage_g1, g2 subordination,
    strategy_lifecycle_phase26_5, g6_lifecycle_progression,
    bi5_realism_27_3). Zero collateral damage.

- **Architectural separation preserved**
  - **Discovery / mutation / OOS / validation** — 100% on BID candles
    (verified: `mutation_engine`, `auto_mutation_runner`,
    `multi_cycle_runner`, `auto_factory*`, `backtest_engine` all
    default to `bid_1m`).
  - **BI5 is consumed ONLY by `bi5_realism.evaluate`** — never by
    discovery or mutation. Realism remains a certification layer, not
    a discovery engine.
  - **Operator-pull only** — the system never auto-deploys; realism
    feeds the lifecycle's `deployment_ready` gate, which produces a
    visible chip + (Phase 27.4) a deployment report. Final hand-off
    is always operator-initiated.

- **Operator-facing behaviour after Phase 27.3**
  - Once the operator pre-stages BI5 chunks (e.g. EURUSD/H1 +
    XAUUSD/H1), the Sunday 03:00 UTC sweep runs autonomously and
    persists `pf_ratio` per eligible strategy.
  - Strategies whose ratio ≥ 0.75 become eligible for
    `DEPLOYMENT_READY` on the next lifecycle tick (assuming cBot
    compile + risk gate also pass).
  - Strategies with ratio in [0.50, 0.75) carry the `PARTIAL_REALISM`
    flag visibly without demotion.
  - Strategies with ratio < 0.50 are demoted to `STABLE` with a 30-day
    `BI5_FAIL` cool-down (existing lifecycle behaviour, now actually
    fed real evidence).
  - Strategies with no BI5 data carry the `BI5_DATA_MISSING` flag and
    a "BI5 not verified" pill — they STAY at `PORTFOLIO_WORTHY`.


- **Backend (additive only)**
  - New module `engines/env_priority.py` (515 lines): 3-tier config (CORE / SECONDARY /
    EXPLORATORY) with default weights 0.7 / 0.2 / 0.1, per-env adaptive multiplier
    bounded `[0.5, 2.0]`, EMA-smoothed feature scores
    (PF / pass_prob / survivors / OOS_PF / drawdown), per-tick decay toward neutral
    for idle envs, hard safety cap (no env > 80 %), exploratory floor (default 5 %),
    canonical timeframe normalisation (`H1` ↔ `1h`).
  - Persisted to Mongo collection `orchestrator_env_priority` (`_id="config"` and
    `_id="state"`) → survives restart.
  - Hooked into `engines/ai_orchestrator.observe_state()`:
    * each tick first calls `consume_recent_cycles()` (reads new `auto_run_cycles`
      docs since the persisted cursor, updates per-env multipliers, decays idle envs)
    * then samples N envs via `pick_environments()` and stores them on
      `state["adaptive_scan"]`.
  - `decide()` now uses `state["adaptive_scan"]` for the
    `NO_SAVES_BOOST_DIVERSITY` / `LOW_PF_DIVERSITY` autonomous trigger payloads,
    falling back to the legacy `DIVERSITY_SCAN` if env_priority is unconfigured
    (no breaking change). Manual `start_multi_cycle(scan=…)` calls bypass entirely.
  - 5 new endpoints in `api/orchestrator.py`:
    * `GET /api/orchestrator/env-priority/config`
    * `POST /api/orchestrator/env-priority/config`   — patch tiers / knobs
    * `GET /api/orchestrator/env-priority/stats`     — per-env metrics + allocation %
    * `POST /api/orchestrator/env-priority/sample`   — preview N picks (`n`, `seed`, `allow_noisy`)
    * `POST /api/orchestrator/env-priority/reset`    — clear adaptive multipliers

- **Frontend (additive)**
  - New component `components/EnvPriorityPanel.js` (~430 lines) embedded inside
    `OrchestratorPanel.js` as a collapsible "Environment Priority" section.
  - 3 tier editors (CORE/SECONDARY/EXPLORATORY) with editable pair/timeframe lists
    and weight inputs; live "% base" indicator.
  - 4 knob inputs (exploratory floor, max env share, EMA α, decay rate),
    Allow-noisy-scans toggle, Pause Adaptation, Reset Multipliers controls.
  - Stats table sorted by allocation showing per-env: tier badge, allocation bar,
    multiplier (×0.50–×2.00), score, PF EMA, survivor EMA, OOS PF, DD %, last-used.
  - Auto-refresh every 7 s while open. Revert + Save Config buttons (disabled until dirty).

### Verified (10 backend assertions)
1. Cold start uses base tier weights (0.7 / 0.2 / 0.1) ✓
2. Strong (EURUSD H1, PF=1.7, full saves) → mult 1.46 ; weak (BTCUSD 15m, PF=0.85, no saves) → 0.57 ✓
3. Idempotent — re-running consume after no new cycles is a no-op ✓
4. Hard cap respected — max env share ≤ 0.80 ✓
5. Exploratory floor enforced (≥ 5 %) ✓
6. Pause Adaptation skips updates ✓
7. Reset Multipliers restores all to neutral 1.0 ✓
8. Noisy gate excludes 1m unless `allow_noisy_scans=true` ✓
9. Zero-weight config rejected with 400 ✓
10. Decay over time pulls 1.8 → 1.53 over 20 idle ticks ✓

End-to-end: orchestrator decide path now emits `trigger_multi_cycle` with the
adaptive 8-env scan instead of the static 8-env DIVERSITY_SCAN.

### Defaults at a glance
| Knob | Default | Range |
|------|---------|-------|
| ema_alpha | 0.20 | 0.01 – 0.90 |
| decay_rate | 0.02 | 0.00 – 0.50 |
| exploratory_floor | 0.05 | 0.00 – 0.50 |
| max_env_share | 0.80 | 0.10 – 1.00 |
| allow_noisy_scans | false | bool |
| adaptation_enabled | true | bool |
| score_weights | pf 0.30 / pp 0.25 / surv 0.20 / oos 0.15 / dd 0.10 | normalized to 1.0 |

### 2026-05-09 — Strategy Explorer transparency / validation visibility (Phase 24)
- **Backend (additive)**
  - `engines/strategy_memory.py`: extended `get_explorer_rollup()` to enrich every
    library-saved row with cached `oos_holdout`, `expected_value`, `total_trades`,
    `win_rate`, `max_drawdown_pct`, `total_return_pct`, `profit_factor`,
    `pass_probability`, `stability_score` via a single bulk lookup keyed by `library_id`.
  - New `_attach_validation_view()` helper computes per-row:
    * **metrics block** — total_trades, IS_PF, OOS_PF, OOS_ratio, max_drawdown_pct,
      expectancy, avg_trade_pct, win_rate, stability_score, pass_probability_pct,
      R:R, breakeven_probability, total_return_pct
    * **badges array** — `LOW_SAMPLE` (trades<30), `OOS_WEAK` (ratio<0.7),
      `OVERFIT_RISK` (PF>5 ∧ trades<20), `HIGH_DD` (DD≥10%),
      `PROP_SAFE` (DD<5% ∧ ratio>0.7 ∧ pp>60%), `STABLE` (stability≥60)
    * **validation stage** — `exploratory` / `candidate` / `validated` / `prop_safe`
    * **confidence_summary** — one-liner ("86 trades · OOS 0.83 · DD 3.2% · stable")
  - New endpoint `GET /api/strategies/library/{strategy_id}/details` (cached only,
    NEVER re-runs a backtest): validation block, IS-vs-OOS comparison (with overfit
    flag), expectancy breakdown, prop-firm panel, validation-report notes,
    pass-probability narrative reasoning, run-level PF history + bucket distribution,
    plus `click_to_compute` stubs for equity / drawdown / monthly / trade dist.

- **Frontend (additive)**
  - New `components/StrategyDetailsPanel.js` (~330 lines) — research-grade drawer with
    6 cards (Validation, IS vs OOS, Expectancy, Pass-Prob Reasoning + violations,
    PF history + trade-count dist, Expensive-Visuals click-to-compute stubs).
    Exports reusable `<StageBadge>` + `<ValidationBadges>` for the table.
  - `components/StrategyExplorer.js` updated:
    * 5 new sortable columns (Best PF, OOS ratio, Trades, Max DD, Pass Prob) via a
      new `<SortableHeader>` helper — sort is **purely client-side** over already-
      loaded rows (no extra API hits, scrolling/filtering doesn't trigger backtests).
    * `Stage` column + `Badges` column.
    * Inline `confidence_summary` under each strategy name.
    * `MagnifyingGlassPlus` per-row button → opens `StrategyDetailsPanel` drawer
      (disabled when no `library_id`).
    * Removed three duplicate columns (Avg PF / Last PF / Best Firm / Match Score /
      Safe Risk) — surfaced inside the drawer instead.

### Stage threshold ladder (cached fields only)
| Stage | Requires |
|-------|----------|
| exploratory | no library entry OR runs<3 |
| candidate   | + IS_PF ≥ 1.2 ∧ trades ≥ 30 |
| validated   | + OOS_ratio ≥ 0.7 ∧ stability ≥ 60 |
| prop_safe   | + DD < 5 % ∧ pass_probability ≥ 60 % |

### Verified
- `GET /api/strategies/explorer` returns full `validation` block per row ✓
- `GET /api/strategies/library/{id}/details` returns deep cached payload ✓
- 170-row Explorer renders new columns; stage chips & badges visible; confidence summaries inline ✓
- Details drawer opens, shows 12-stat metrics grid, IS vs OOS with overfit flag, expectancy, reasoning, mini PF-history chart, click-to-compute stubs ✓
- ESLint + ruff clean ✓

## Phase 28-C — Deterministic IR → cAlgo C# Transpiler (2026-05-14)

Closes the executable bridge: trust-gated Strategy-IR now renders to deterministic, executable cTrader cAlgo C# cBots — no LLM, no placeholders, no semantic invention. The IR interpreter remains the canonical truth surface; the transpiler is a pure rendering layer.

### What landed
- NEW `cbot_engine/ir_templates.py` (~199 LoC): C# scaffolds + per-operator expression templates. Timing-semantic convention documented (Last(1)↔i, Last(2)↔i-1, never Last(0) in signal logic).
- NEW `cbot_engine/ir_emitter.py` (~376 LoC): per-operator typed C# emitters + IR walker. Honest refusal via `UnsupportedIROperatorError` on anything outside v1.
- NEW `cbot_engine/ir_transpiler.py` (~184 LoC): orchestration entry point — schema validate → v1 coverage check → walk → assemble → stamp lineage metadata.
- NEW `cbot_engine/ir_parity_simulator.py` (~90 LoC): execution-semantic infrastructure mirroring C# semantics in Python.
- NEW `tests/test_cbot_ir_transpiler.py` (~333 LoC, 40 tests, 7 trust-gate tiers + vocabulary completeness).
- `api/cbot.py` (+38 LoC): when `strategy_ir` present → ALWAYS transpile (operator decision #4). Legacy LLM/stub path preserved as unchanged fallback. Uniform 422 refusal contract.

### TRANSPILER_VERSION 1.0.0 — stable vocabulary
- Operators: AND/OR/NOT, GT/LT/GE/LE/EQ/NEQ, CROSS_UP/DOWN, RANGE_BREAK_UP/DOWN, AT_TIME/IN_GMT_WINDOW, BAND_TOUCH/BREAK_UPPER/LOWER, ATR_RATIO_ABOVE, HTF_SLOPE_UP/DOWN, BB_SQUEEZE_PERCENTILE
- Indicators: EMA, RSI, ATR, BOLLINGER, HTF_EMA
- SL kinds: pips, atr_mult, range_fraction, band_mid
- TP kinds: pips, atr_mult, range_fraction, band_mid, indicator_cross
- Refused (operator-locked): MACD/momentum (deferred to IR v1.1)

### Execution lineage metadata (operator directive #6 — every cBot carries)
- IR_VERSION · TRANSPILER_VERSION · STRATEGY_HASH (SHA-1 of canonical IR JSON) · GENERATED_AT · HTF_PARITY_MODE (APPROXIMATE | N/A) · PARITY_STATUS (PENDING | PASSED) · PARITY_FIXTURES_PASSED

### Trust gate — 40 / 40 PASS across 7 tiers
1. Determinism (byte-identical output, hash stable against dict ordering) — 3/3
2. Token validity (balanced braces/parens, required C# tokens) — 9/9
3. Declaration completeness (every indicator → field + init, HTF cross-feed) — 6/6
4. Semantic parity (simulator signals ≡ interpreter signals across 4 fixture families) — 6/6
5. Execution lineage metadata (all 7 header lines) — 2/2
6. Honest refusal on unsupported IR (operator / exit kind / parity simulator) — 3/3
7. Timing semantics (no Last(0) in signal logic, force-flat before entry, session/spread before entry) — 8/8
Vocabulary completeness (MACD explicit refusal) — 3/3

### Regression
- Phase 28 trust gate now: **147 / 147 PASS** (prior 107 + 40 new transpiler).
- Full regression: **242 / 242 PASS, 0 failed** across BI5 27.3+27.4, backtest correctness, G2/G6/G1, orchestrator scheduler, all Phase 28 layers.

### Live endpoint
- `POST /api/generate-cbot` with `strategy_ir` → 200, `source: ir_transpiler`, full executable C# with embedded lineage header.
- Without `strategy_ir` → 200, `source: legacy_generator` (legacy stub preserved).
- Schema-invalid IR → 422 `error: invalid_strategy_ir` (Pydantic enum refusal).
- Transpiler v1 gap → 422 `error: unsupported_ir_operator` (transpiler refusal).

### Stabilization posture
Phase 28-C lands the executable bridge but does NOT alter the operator-declared observation posture: no scheduler started, no autonomous emergence triggered, no library backfill, no live deployment automation, no Phase 28-D. Each generated cBot defaults to `PARITY_STATUS = PENDING` so a raw transpile is never mistaken for a parity-cleared artefact.

## Phase 28 Telemetry — IR Coverage Observability (2026-05-13)

Adds the minimum-viable observability surface so the operator can watch IR-contract health continuously during autonomous emergence — before Phase 28-C ships.

### What landed
- NEW `engines/ir_telemetry.py` (~275 LoC): pure helpers `compute_ir_chain_depth`, `classify_legacy_reason`, `summarize_events` + async `fetch_ir_telemetry` (read-only DB aggregate over `mutation_events`).
- `engines/mutation_engine.py::run_mutation_pipeline` event_doc enrichment (+20 LoC): every persisted event now carries `ir_status`, `ir_chain_depth`, `legacy_reason`.
- `api/mutation.py` (+34 LoC): `GET /api/mutation/ir-telemetry?since=&limit=` — read-only, scheduler-independent, query-string driven, capped at 50_000 rows.
- NEW `tests/test_ir_telemetry.py` (~335 LoC, 27 tests across 6 invariant groups).

### Four operator-facing signals
- `% IR-native vs legacy` (overall + per mutation_type)
- `chain_depth_distribution` + `chain_depth_mean`
- `legacy_reasons.*` (momentum_base, composer_legacy_base, ir_v1_unsupported, …)
- `legacy_reasons.momentum_base` — direct count of the IR v1 gap

### Trust gate
- Phase 28 trust gate now: **107 / 107 PASS** (prior 80 + 27 new telemetry).
- Regression sweep: **202 / 202 PASS, 0 failed** across full Phase 28 + BI5 + backtest correctness + G2/G6/G1 + orchestrator scheduler.
- Endpoint live: `GET /api/mutation/ir-telemetry` returns stable JSON shape with zero events on a fresh DB.

### Operator gate
Phase 28-C (IR → cAlgo C# transpiler) is **parked** until the operator declares a stabilization window closed. Recommended observation signals to watch:
1. `ir_native_pct` trend stays ≥ 95% for non-momentum bases
2. `chain_depth_distribution` shows a non-trivial population at depth ≥ 1 (composers actively selected by Evolution Loop)
3. `legacy_reasons.momentum_base` is dominant; any other bucket overtaking it warrants investigation
4. Per-type `ir_native_pct` stays ~100% for every root + composer type except momentum derivatives

## Phase 28-B++ — Cross-cycle composer-chain continuity (2026-05-13)

Closes a higher-order continuity sub-gap surfaced during the Phase 28-B+ inspection: `_derive_base_ir` only consulted `base["strategy_text"]`, never the `base["strategy_ir"]` that a re-mutated variant already carries. Across iterative autonomous mutation cycles this would silently drop overlays accumulated on prior cycles, breaking lineage continuity, evolutionary inheritance, and Phase 28-C export trustworthiness.

### What landed
- `engines/mutation_engine.py::_derive_base_ir`: short-circuit returns `base["strategy_ir"]` verbatim when it's a valid `StrategyIR` (instance or schema-validating dict). Falls back to text derivation for legacy bases — bit-identical to Phase 28-B+ behaviour.
- `mutate_strategy` and `mutate_strategy_by_types`: thread `base_strategy.get("strategy_ir")` into the internal `base` dict so the short-circuit can see it.
- NEW `tests/test_composer_chain_preserves_prior_overlay.py` — 14 tests across 5 invariant groups (carried-IR semantics, end-to-end carry-through, multi-cycle overlay accumulation, interpreter monotonicity, chain-aware special composers).

### Trust gate
- Phase 28 trust gate now: **80 / 80 PASS** (prior 66 + 14 new cross-cycle).
- Regression sweep: **148 / 148 PASS, 0 failed** across BI5 27.3+27.4, backtest correctness, G2 / G6 / G1, orchestrator scheduler.
- Single change-block to revert: drop the 9-line short-circuit + revert three +3-line carry-throughs → behaviour reverts to Phase 28-B+.

### What this enables
- Iterative composer chains (`filter_add_rsi → mtf_htf_confirmation → filter_add_volatility → risk_reward_1_2`) deterministically accumulate every overlay in the final IR with bit-stable JSON.
- `filter_remove_rsi` applied at any chain depth strips the prior overlay (not just text-derived RSI gates).
- `risk_reward_*` at chain tip replaces SL/TP only — prior entry predicates from N cycles survive verbatim.
- Cross-cycle interpreter signal counts are strictly monotone non-increasing for restrictive chains — direct semantic proof of zero overlay loss.

### Phase 28-C posture
Re-affirmed safe to begin: mutation pipeline is now semantically lossless across N autonomous cycles. cBot transpiler can faithfully render the accumulated rules without divergence.

## Backlog / Future Enhancements (P2)
- Add a "scope picker" UI in the Backup & Restore row to let the user select a subset
  of pairs / timeframes / sources before clicking Export Market Data (the backend
  endpoint already accepts those filters in the JSON body).
- Add SHA-256 of each CSV in the manifest so the receiving Emergent account can verify
  integrity post-import.
- Optional resumable upload for very large imports (>500 MB) — current Import ZIP
  endpoint reads the full body in memory; out of scope for this ticket.
