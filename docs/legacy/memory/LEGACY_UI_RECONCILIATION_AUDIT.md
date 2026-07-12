# LEGACY_UI_RECONCILIATION_AUDIT.md

**Audit type:** Final pre-hydration reconciliation — legacy 1-vCPU UI vs canonical Frontend.zip/App.zip architecture.
**Sources:**
* `legacy_screenshots.docx` (operator-uploaded, 18 PNGs — identical MD5 to `_inventory/old_ui_screenshots.docx` and `old_ui_screenshots_v2.docx`)
* `_inventory/old1vcpu/src/App.js` — **authoritative** legacy navbar source (lines 167–187 with explicit `🔒 NAVBAR CONFIG — LOCKED 🔒` comment)
* `_inventory/old1vcpu/src/components/` (50 components)
* `memory/visual_approval_package/01_TAB_ROSTER.md` + `04_COMPONENT_REHOUSING_MATRIX.md` — locked restoration plan
* `Frontend.zip/src/command/shell/modulesRegistry.js` (canonical new shell)
* `App.zip/backend/` (canonical backend)

**Status:** Read-only. No code modified.

---

## 1. Classification key

| Code | Meaning |
|---|---|
| **MR — Mounted & reachable** | Legacy screen has a direct equivalent visible in the primary navigation of the new shell. |
| **MH — Mounted but hidden** | Legacy screen exists in the new codebase but reachable only via Command Palette (⌘K), Power-User sub-tab, or `/legacy` route. |
| **MV — Moved to another location** | Legacy screen is now reached at a different navigation path with no functional loss. |
| **MG — Merged into another screen** | Legacy screen is now a tab/section/accordion within a composite surface. |
| **BO — Backend exists but UI missing** | API live; no operator UI surface in the new shell. |
| **UO — UI exists but backend missing** | Operator surface renders; no backend behaviour. |
| **PL — Placeholder only** | Reservation card; layout-anchor, no behaviour. |
| **MX — Missing entirely** | Not present in new codebase. |

---

## 2. Legacy CORE_TABS — full audit

Legacy navbar (verbatim from `old1vcpu/src/App.js` LL 168–179):

```
CORE_TABS = [
  { id: 'dashboard',         label: 'Dashboard' },
  { id: 'execution',         label: 'Execution' },
  { id: 'auto-factory',      label: 'Auto Factory' },
  { id: 'monitoring',        label: 'Monitoring' },
  { id: 'paper-exec',        label: 'Paper Exec' },
  { id: 'trade-runner',      label: 'Trade Runner' },
  { id: 'portfolio-builder', label: 'Portfolio' },
  { id: 'explorer',          label: 'Explorer' },
  { id: 'data',              label: 'Market Data' },
  { id: 'auto-select',       label: 'Auto Select' },
];
// + admin-users appended for admin role
```

### CORE-1 · Dashboard

| Aspect | Detail |
|---|---|
| Legacy renders | `GovernanceCard` + `UniverseGovernancePanel` + `StrategyIngestionCard` + `AutoSchedulerControl` + `OrchestratorPanel` + `MultiCycleRunner` + `AutoMutationRunner` + `StrategyDashboard` (eight panels stacked) |
| New home | **`/c/dashboard/briefing`** (Mission Briefing) — calm synthesis; the eight legacy panels are reachable inline via deep-link buttons + LeftRail nav |
| Mapping (per `04_COMPONENT_REHOUSING_MATRIX.md`) | GovernanceCard → `governance/gov`; UniverseGovernance → `governance/universe`; StrategyIngestionCard → `diag/ingest-src`; AutoSchedulerControl → `ai/sched`; OrchestratorPanel → `ai/orch`; MultiCycleRunner → `mutate/cycle`; AutoMutationRunner → `mutate/auto`; StrategyDashboard → fallback inside `MissionBriefing` deep-link |
| Status | **MG — Merged** (Mission Briefing) + **MV — Moved** (each panel has its own canonical home) |
| Missing elements | The single-page "everything stacked" UX is gone. Operators who liked seeing 8 panels at once must now navigate or open multiple sections. |
| Recommended mount location | Already correct — Mission Briefing aggregates KPIs; full panels are one click away. |

### CORE-2 · Execution

| Aspect | Detail |
|---|---|
| Legacy renders | `phase9/ExecutionDashboard` (3-step strip: Generate → Allocate → Execute, composing `phase9/AutoFactoryCard` + `phase9/PortfolioBuilderCard` + `phase9/LiveExecutionCard`) |
| New home | **NOT bound in `modulesRegistry.js`.** `ExecutionDashboard`, `AutoFactoryCard`, `PortfolioBuilderCard`, `LiveExecutionCard` all exist under `frontend/src/components/phase9/` but **no `MODULES[*].sections` entry imports them.** |
| Status | **MH — Mounted but hidden** (component imported nowhere in the new shell) |
| Missing elements | The unified 3-step execution flow — Generate→Allocate→Execute is split across `mutate/factory` → `portfolio/builder` → `exec/*`. The single-screen workflow is gone. |
| Recommended mount location | Either: (a) add a new section `dashboard/exec-strip` mounting `ExecutionDashboard`, or (b) explicitly retire this composite per visual approval (Mission Briefing supersedes it). Currently the visual approval matrix recommends Option B — but the component is still in the repo, so it should be either wired or formally removed. |

### CORE-3 · Auto Factory

| Aspect | Detail |
|---|---|
| Legacy renders | `AutoFactoryPhase55` (the modern Phase 55 implementation) |
| New home | **`/c/mutate/factory-55`** — same component, sub-section of Mutation Engine |
| Status | **MV — Moved** (was a top-level tab; now a section under `mutate`) |
| Visual approval restoration | Plans to restore as top-level tab `auto-factory` with `AutoFactoryPhase55` + `MasterBotCompilePanel` accordion |
| Missing elements | Operator muscle-memory: "Auto Factory" was a top-of-bar item. New shell buries it 2 clicks deep. |
| Recommended mount location | Honour the visual approval — promote to **its own top-tab/module** OR keep current `mutate/factory-55` and surface via Lifecycle Rail (M1) — the LifecycleRail already includes a Factory stage. Verify post-hydration. |

### CORE-4 · Monitoring

| Aspect | Detail |
|---|---|
| Legacy renders | `Monitoring.js` (Stop-all / Resume / Save Thresholds / Breach Log / Fleet) — the **Monitoring Center** |
| New home | **`/c/diag/monitoring`** — first sub-tab inside `MonitoringSuite` (Runtime · Soak · Compute · Cluster) |
| Status | **MG — Merged into MonitoringSuite** |
| Visual approval restoration | Top-level tab `monitoring` with 4-tab sub-bar (Runtime · Soak · Compute · Cluster) |
| Missing elements | None — every legacy control is preserved as the Runtime sub-tab. |
| Recommended mount location | Acceptable as-is OR promote to top-level per visual approval (Lifecycle Rail surfaces it; LeftRail Diag module surfaces it). |

### CORE-5 · Paper Exec

| Aspect | Detail |
|---|---|
| Legacy renders | `PaperExecution` (Safe Execution Layer — BID/BI5 replay) |
| New home | **`/c/exec/paper`** — first section of Execution Center |
| Status | **MV — Moved** (top-tab → section under Execution Center) |
| Visual approval restoration | Top-level tab `paper-exec` |
| Missing elements | None functionally; just demoted from top bar. |
| Recommended mount location | Acceptable as-is. |

### CORE-6 · Trade Runner

| Aspect | Detail |
|---|---|
| Legacy renders | `TradeRunner` (Phase 5 — paper execution) |
| New home | **`/c/exec/runner`** |
| Status | **MV — Moved** |
| Missing elements | None. |
| Recommended mount location | Acceptable as-is. |

### CORE-7 · Portfolio

| Aspect | Detail |
|---|---|
| Legacy renders | `PortfolioBuilder` |
| New home | **`/c/portfolio/builder`** |
| Status | **MV — Moved**; sister sections `/c/portfolio/panel` (PortfolioPanel) + `/c/portfolio/intel` (PortfolioIntelligence) added (was hidden `portfolio` route in legacy) |
| Missing elements | None. Actually richer: legacy buried `PortfolioPanel` at hidden `portfolio` route. |
| Recommended mount location | Acceptable as-is. |

### CORE-8 · Explorer

| Aspect | Detail |
|---|---|
| Legacy renders | `StrategyExplorer` (Phase 16 — Strategy Memory) |
| New home | **`/c/explorer/explorer`** + `/c/explorer/saved` + `/c/explorer/compare` (3 sections under Strategy Explorer module) |
| Status | **MV — Moved**; expanded into 3 sections + 3 reservation cards (M3 Score, Phase 13, Phase 15) |
| Missing elements | None functionally. `StrategyDeepDivePanel` + `StrategyDetailsPanel` legacy drilldowns now render as Inspector pane (⌘.) — verify behaviour post-hydration. |
| Recommended mount location | Acceptable as-is. |

### CORE-9 · Market Data

| Aspect | Detail |
|---|---|
| Legacy renders | `DataUpload` + `DataMaintenancePanel` (Manual + Automated stacked) |
| New home | **`/c/diag/market-data`** — `MarketDataWorkbench` composite (Manual · Automated · Archive sub-tabs) |
| Status | **MG — Merged into MarketDataWorkbench** + **MV — Moved** to Diagnostics |
| Visual approval restoration | Top-level tab `data` with 3 sub-tabs |
| Missing elements | None — `DataAvailability` + `DataBackupPanel` ADDED as new sub-content. |
| Recommended mount location | Acceptable in `diag/market-data` OR promote to top-level per visual approval. The visual approval `04_COMPONENT_REHOUSING_MATRIX.md` row 41 explicitly calls for `data` as a primary tab. |

### CORE-10 · Auto Select

| Aspect | Detail |
|---|---|
| Legacy renders | `AutoSelection` (Phase 3 — deployment picker) |
| New home | **`/c/mutate/auto-select`** |
| Status | **MV — Moved** (top-tab → section under Mutation Engine) |
| Missing elements | None. |
| Recommended mount location | Acceptable as-is. |

### CORE-11 · Admin (admin-only)

| Aspect | Detail |
|---|---|
| Legacy renders | `ReadinessPanel` + `AdminUsers` (stacked) |
| New home | **`/c/governance/admin`** — `GovernanceAdminSuite` composite (Users · Flags · Realism · Tuning · Rules sub-tabs) |
| Status | **MG — Merged into GovernanceAdminSuite** |
| Visual approval restoration | Top-level tab `admin-users` with 5-tab sub-bar |
| Missing elements | `ReadinessPanel` is now at `governance/readiness` AND inside Admin top-pinned strip (per visual approval) — verify it actually renders top-pinned post-hydration. |
| Recommended mount location | Acceptable as-is. |

---

## 3. Legacy MORE_TABS — full audit

```
MORE_TABS = [
  { id: 'workspace',    label: 'Workspace' },           # the strategy lab
  { id: 'pipeline',     label: 'Auto Factory (Legacy)' },
  { id: 'prop-firms',   label: 'Prop Firms' },
  { id: 'live',         label: 'Live Tracking' },
  { id: 'optimization', label: 'Optimization' },        # standalone optimizer
  { id: 'saved',        label: 'Library (N)' },         # SavedStrategies
];
```

### MORE-1 · Workspace ⭐ (THE strategy lab — most operator-critical legacy screen)

| Aspect | Detail |
|---|---|
| Legacy renders | A 12-col grid combining: **`StrategyPanel`** (generator), **`StrategyAnalysis`**, **`BacktestPanel`**, **`StrategyDescription`**, **`CbotPanel`**, **`OptimizationPanel`**, **`ValidationPanel`**, **`StrategyComparison`** — eight components in a single workspace |
| New home | **6 separate sections under `/c/lab/*`**: `panel`, `analysis`, `backtest`, `cbot`, `optim`, `validate`. Comparison is at `/c/explorer/compare`. |
| Status | **MG — Merged but inverted** — was 1 page with 8 panels; now 6 pages with 1–2 panels each. Operationally: more clicks. |
| Visual approval restoration | Plans to restore as MORE-tab `workspace` rendering the full 3-col 9-col grid (per `04_COMPONENT_REHOUSING_MATRIX.md`) |
| Missing elements | The unified workspace UX. Operators who used the Workspace as a single power-user surface now need to jump between 6 lab sections. |
| Recommended mount location | Strong recommendation: **add a `lab/workspace` composite section** that re-mounts the 8-component grid. The components are all imported in `modulesRegistry.js`; only the composite host is missing. ETA to implement: ~2 hours. |

### MORE-2 · Auto Factory (Legacy)

| Aspect | Detail |
|---|---|
| Legacy renders | `AutoFactory` (the pre-Phase-55 implementation) |
| New home | **`/c/mutate/factory`** |
| Status | **MV — Moved** |
| Missing elements | None. |
| Recommended mount location | Acceptable as-is. |

### MORE-3 · Prop Firms

| Aspect | Detail |
|---|---|
| Legacy renders | `PropFirmsAdmin` (Phase 20 — Review & Approval) |
| New home | **`/c/propfirm/admin`** + sister `/c/propfirm/match` (FirmMatchPanel) |
| Status | **MV — Moved**; sister surface added |
| Missing elements | `AddFirmModal` should be invoked as a modal from PropFirmsAdmin — verify post-hydration. `ChallengeMatchingPanel` is reachable via Governance Admin Power-User sub-tab; legacy had it embedded in Firm Match. |
| Recommended mount location | Per visual approval, Challenge Matching should appear as a third sub-tab of `prop-firms` (Admin · Match · Challenge). Currently only Admin + Match are mounted under `propfirm`; Challenge is parked in Governance Admin. **Recommend moving ChallengeMatchingPanel to `propfirm/challenge`** post-hydration. |

### MORE-4 · Live Tracking

| Aspect | Detail |
|---|---|
| Legacy renders | `LiveTrackingPanel` |
| New home | **`/c/exec/live`** |
| Status | **MV — Moved** |
| Missing elements | None. |
| Recommended mount location | Acceptable as-is. |

### MORE-5 · Optimization (standalone)

| Aspect | Detail |
|---|---|
| Legacy renders | `Optimization` (standalone — Phase 8 Strategy Refinement) |
| New home | **NOT bound in `modulesRegistry.js`** (only the workspace-scoped `OptimizationPanel.js` is mounted at `lab/optim`) |
| Status | **MH — Mounted but hidden** (component file `Optimization.js` exists in `frontend/src/components/` but no MODULES section imports it) |
| Missing elements | The standalone optimizer that wasn't tied to a single strategy is gone from primary nav. |
| Recommended mount location | Either: (a) add a `lab/optim-standalone` section, or (b) confirm the per-strategy `OptimizationPanel` covers the standalone use case. Verify with operator post-hydration. |

### MORE-6 · Library (Saved Strategies)

| Aspect | Detail |
|---|---|
| Legacy renders | `SavedStrategies` |
| New home | **`/c/explorer/saved`** |
| Status | **MV — Moved**; count badge logic (`Library (${savedStrategies.length})`) — verify the new shell carries this in `TopTabBar` post-hydration. |
| Missing elements | The count badge in the tab label may not yet render in `TopTabBar.jsx`. Easy follow-up. |
| Recommended mount location | Acceptable as-is; verify count badge. |

---

## 4. Hidden legacy route (`portfolio`)

| Aspect | Detail |
|---|---|
| Legacy renders | `PortfolioPanel` (reachable only via direct `setActiveTab('portfolio')` — not in either nav set) |
| New home | **`/c/portfolio/panel`** — now visible in primary nav |
| Status | **MV — Moved**, and **upgraded** (was hidden, now visible) |
| Missing elements | None. |
| Recommended mount location | Acceptable as-is. |

---

## 5. Operator-named subsystems — explicit audit

### 5.1 AI Architecture

| Item | Status |
|---|---|
| Legacy presence | The label "AI Architecture" does not appear as a tab. The closest legacy concept was the Dashboard's stacked panels (Orchestrator + Scheduler + AutoMutationRunner). |
| New presence | **MR** via `CopilotPanel` (⌘J) + `ArchitectDashboard` (palette-only) + `/c/ai/*` module (Live River · Orchestrator · Auto-Scheduler) |
| Backend | `engines/ai_orchestrator.py`, `decision_engine.py`, `factory_supervisor/architect_advisor.py`, `copilot_*` |
| Missing | Architecture surface (the operator-facing "this is how the AI is reasoning right now" view) is dormant behind `FS_ENABLE_ARCHITECT_DASHBOARD=false`. |
| Recommendation | Acceptable dormancy. Activate after FS-P1.0 soak. |

### 5.2 Strategy Generator

| Item | Status |
|---|---|
| Legacy presence | `StrategyPanel` (Workspace tab — top left) |
| New presence | **MR** at `/c/lab/panel` |
| Backend | `api/strategies.py::generate`, `engines/strategy_engine.py` |
| Missing | None functionally. Workspace single-page composite is the UX gap (see MORE-1). |
| Recommendation | Acceptable. Restore Workspace composite if operator misses single-page lab. |

### 5.3 Strategy Output

| Item | Status |
|---|---|
| Legacy presence | `BacktestPanel` + `StrategyDescription` + `StrategyDetailsPanel` (Workspace tab — main column) |
| New presence | **MR** at `/c/lab/backtest`; `StrategyDescription` rendered inside `lab/backtest` (per matrix row 54); `StrategyDetailsPanel` → `AsfDetailDrawer` global drawer |
| Backend | `api/strategies.py::backtest`, `api/dashboard_route.py` |
| Missing | Verify `StrategyDescription` actually renders inside `BacktestPanel` — the rehousing matrix says it does, but `BacktestPanel.js` from old1vcpu must inline render it. Confirm post-hydration. |
| Recommendation | Acceptable; verify rendering. |

### 5.4 AI Analysis

| Item | Status |
|---|---|
| Legacy presence | `StrategyAnalysis` (Workspace tab — left col) |
| New presence | **MR** at `/c/lab/analysis` |
| Backend | `api/dashboard.py::generate-analysis`, `engines/analysis_engine.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.5 Indicator Ideas

| Item | Status |
|---|---|
| Legacy presence | Inside `StrategyPanel` (no dedicated tab) — operator-input indicator suggestions feed into strategy generation |
| New presence | **MR** — same place: inside `StrategyPanel` at `/c/lab/panel` |
| Backend | Part of `engines/strategy_engine.py` IR builders + `strategy_ir_builders.py` |
| Missing | If the legacy had a standalone "Indicator Ideas" generator surface, it isn't separately mounted. The functionality lives inline. |
| Recommendation | Confirm with operator whether an explicit Indicator Ideas panel is desired. If yes, add `lab/indicators` section. |

### 5.6 Random Search Optimizer

| Item | Status |
|---|---|
| Legacy presence | Driven by `OptimizationPanel` (Workspace) + standalone `Optimization` (MORE-5 tab) |
| New presence | **MR** at `/c/lab/optim` (per-strategy) — standalone `Optimization.js` is **MH** (hidden) |
| Backend | `engines/random_search_optimizer.py`, `optimization_engine.py`, `ga_optimizer.py`, `api/optimization.py` |
| Missing | Standalone optimizer surface. See MORE-5 — `Optimization.js` exists in repo, not wired. |
| Recommendation | Decide: keep standalone optimizer hidden (operator uses per-strategy view) or mount it. |

### 5.7 Validator

| Item | Status |
|---|---|
| Legacy presence | `ValidationPanel` (Workspace) — combined Walk Forward + OOS + Monte Carlo |
| New presence | **MR** at `/c/lab/validate` |
| Backend | `api/strategies.py::validate`, `engines/validation_engine.py`, `walk_forward_engine.py`, `oos_holdout.py`, `monte_carlo_engine.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.8 Monitoring Center

| Item | Status |
|---|---|
| Legacy presence | `Monitoring.js` at top-level tab `monitoring` |
| New presence | **MG** — first sub-tab of `MonitoringSuite` at `/c/diag/monitoring` |
| Backend | `api/monitoring.py`, `engines/monitoring_engine.py`, alert bridge |
| Missing | None functionally — all legacy controls preserved (Stop-all / Resume / Thresholds / Breach Log / Fleet). |
| Recommendation | Acceptable. |

### 5.9 Market Data Maintenance

| Item | Status |
|---|---|
| Legacy presence | `DataUpload` at `data` tab top of page |
| New presence | **MR** as Manual sub-tab of `MarketDataWorkbench` at `/c/diag/market-data` |
| Backend | `api/data.py`, `data_engine/csv_ingester.py`, `tick_archive.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.10 Auto Data Maintenance

| Item | Status |
|---|---|
| Legacy presence | `DataMaintenancePanel` at `data` tab (bottom of page) |
| New presence | **MR** as Automated sub-tab of `MarketDataWorkbench` |
| Backend | `api/data_maintenance.py`, `data_engine/auto_data_maintainer.py`, `incremental_updater.py`, `gap_analyzer.py` |
| Missing | None. The B-1 BI5 dispatch (60-min cadence) and DSR-2 registry consumption are MORE capability than legacy. |
| Recommendation | Acceptable; verify the BI5 source picker is visible in Manual sub-tab. |

### 5.11 Auto Factory Controls

| Item | Status |
|---|---|
| Legacy presence | `AutoFactoryPhase55` at `auto-factory` top-tab; `AutoFactory` (legacy) at `pipeline` MORE-tab |
| New presence | **MR** — both at `/c/mutate/factory-55` and `/c/mutate/factory` |
| Backend | `api/auto_factory.py`, `engines/auto_factory.py`, `auto_factory_phase55.py`, `evolution_engine.py` |
| Missing | None. The legacy operator may expect Auto Factory to be top-level (it was); now it's a section. |
| Recommendation | Per visual approval, promote `auto-factory` to top-level OR rely on LifecycleRail to surface it. Verify post-hydration. |

### 5.12 Explorer

| Item | Status |
|---|---|
| Legacy presence | `StrategyExplorer` at `explorer` top-tab |
| New presence | **MR** at `/c/explorer/explorer` (+ Saved + Compare + 3 reservation cards) |
| Backend | `api/strategies.py`, `strategy_memory.py`, `research_lineage.py` |
| Missing | None — actually enhanced with 3 reservation surfaces (M3 Score, Phase 13 Dossier, Phase 15 Marketplace). |
| Recommendation | Acceptable. |

### 5.13 Portfolio Builder

| Item | Status |
|---|---|
| Legacy presence | `PortfolioBuilder` at `portfolio-builder` top-tab |
| New presence | **MR** at `/c/portfolio/builder` + sister sections |
| Backend | `api/portfolio_builder.py`, `engines/portfolio_builder_engine.py`, `portfolio_combiner.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.14 Execution Simulator

| Item | Status |
|---|---|
| Legacy presence | `PaperExecution` (Safe Execution Layer — BID/BI5 replay) |
| New presence | **MR** at `/c/exec/paper` |
| Backend | `api/execution.py`, `engines/paper_execution_engine.py`, `execution_engine.py`, `execution_simulator.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.15 Auto Selection

| Item | Status |
|---|---|
| Legacy presence | `AutoSelection` at `auto-select` top-tab |
| New presence | **MR** at `/c/mutate/auto-select` |
| Backend | `api/auto_selection.py`, `engines/auto_selection_engine.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.16 Prop Firm Manager

| Item | Status |
|---|---|
| Legacy presence | `PropFirmsAdmin` at `prop-firms` MORE-tab |
| New presence | **MR** at `/c/propfirm/admin` |
| Backend | `api/prop_firms.py`, `engines/prop_firm_config_engine.py`, `prop_firm_intelligence.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.17 Challenge Profiles

| Item | Status |
|---|---|
| Legacy presence | Embedded in `PropFirmsAdmin` (no separate tab) |
| New presence | **MH** — `ChallengeMatchingPanel` reachable via Governance Admin Power-User sub-tab (`OperatorParityPanels.jsx`) |
| Backend | `api/challenge.py`, `engines/challenge_simulator.py`, `challenge_manager.py`, `challenge_matching_engine.py`, `api/challenge_matching.py` |
| Missing | Challenge Profiles surface is hard to find. |
| Recommendation | **Promote to `propfirm/challenge` sub-tab** (per visual approval `01_TAB_ROSTER.md` row 3 of MORE) so it sits next to Firm Match. |

### 5.18 Live Tracking

| Item | Status |
|---|---|
| Legacy presence | `LiveTrackingPanel` at `live` MORE-tab |
| New presence | **MR** at `/c/exec/live` |
| Backend | `api/live_tracking.py`, `engines/live_tracking_engine.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.19 Optimization

| Item | Status |
|---|---|
| Legacy presence | Standalone `Optimization` at `optimization` MORE-tab |
| New presence | **MH** — component exists; no module section mounts it |
| Backend | `api/optimization.py`, `engines/optimization_engine.py` |
| Missing | Standalone optimizer surface. |
| Recommendation | Per visual approval row 58: mount under MORE-tab `optimization`. Currently absent in `modulesRegistry.js`. |

### 5.20 Strategy Library

| Item | Status |
|---|---|
| Legacy presence | `SavedStrategies` at `saved` MORE-tab with `Library (N)` badge |
| New presence | **MR** at `/c/explorer/saved` |
| Backend | `api/strategies.py?saved=true`, `engines/strategy_library.py` |
| Missing | Count badge in tab label — verify TopTabBar carries it post-hydration. |
| Recommendation | Acceptable; verify badge. |

### 5.21 Trade Runner

| Item | Status |
|---|---|
| Legacy presence | `TradeRunner` at `trade-runner` top-tab |
| New presence | **MR** at `/c/exec/runner` |
| Backend | `api/trade_runner.py`, `engines/trade_runner_engine.py` |
| Missing | None. |
| Recommendation | Acceptable. |

### 5.22 Master Bot

| Item | Status |
|---|---|
| Legacy presence | **Not present in 1-vCPU UI.** This subsystem post-dates the legacy. |
| New presence | **MR** at `/c/mutate/master-bot` (Dashboard) + `/c/mutate/master-bot-compile` (Compile) |
| Backend | `api/master_bot.py`, `engines/master_bot_*.py` (8 modules), `api/runner.py` |
| Missing | Master Bot **administration** (per visual approval row 19) should also live under Monitoring → Cluster sub-tab. Currently only under Mutation Engine. |
| Recommendation | Add `MasterBotDashboard` as additional sub-content under `diag/monitoring` Cluster sub-tab OR confirm operator is happy with single home under Mutation. |

### 5.23 Factory Supervisor

| Item | Status |
|---|---|
| Legacy presence | **Not present in 1-vCPU UI.** Post-dates legacy. |
| New presence | **MH** — `FactorySupervisorPanel` reachable via Command Palette (⌘K → search "Factory Supervisor") + Cluster sub-tab in MonitoringSuite (per visual approval). `ArchitectDashboard.jsx` reachable via palette. |
| Backend | `api/factory_supervisor.py`, `engines/factory_supervisor/*` (≈20 modules) |
| Backend status | Dormant — `ENABLE_FACTORY_SUPERVISOR=false`, all `FS_ENABLE_*` OFF |
| Missing | Primary-nav discoverability. Currently a power-user palette surface only. |
| Recommendation | Acceptable while dormant. Promote to LeftRail status dot + Cluster sub-tab when activated. |

### 5.24 Auto Learning Infrastructure

| Item | Status |
|---|---|
| Legacy presence | **Not present in 1-vCPU UI.** Post-dates legacy. |
| New presence | **BO — Backend exists but UI missing.** `engines/factory_supervisor/auto_learning_*` runs; no dedicated panel. Insights would surface via Recommendation Engine + Architect Dashboard (both dormant). |
| Backend | `engines/factory_supervisor/auto_learning_aggregator.py` + readiness probe |
| Backend status | Dormant — `FS_ENABLE_AUTO_LEARNING=false`, `FS_ENABLE_AUTO_LEARNING_LOOP=false` (operator hard veto) |
| Missing | Operator-visible "what is the system learning?" panel. |
| Recommendation | Acceptable while dormant. When activated, surface as `ai/learning` section. |

### 5.25 Dynamic Symbol Registry (DSR)

| Item | Status |
|---|---|
| Legacy presence | **Not present in 1-vCPU UI.** Post-dates legacy. |
| New presence | **MR** at `/c/governance/symbol-registry` (DSR-1 SymbolRegistryPanel) |
| Backend | `engines/market_universe.py`, `api/admin_market_universe.py`, `api/latent/market_universe.py` |
| Backend status | DSR-3 ACTIVE post-hydration (`ENABLE_DYNAMIC_MARKET_UNIVERSE=1`) |
| Missing | None — full CRUD UI + engine consumption + adapter cache + shadow audit. |
| Recommendation | Acceptable. Verify mount post-hydration. |

### 5.26 BI5 Systems

| Item | Status |
|---|---|
| Legacy presence | BI5 ingest was scheduled via `auto_data_maintainer` and surfaced as a status field inside DataMaintenancePanel — no dedicated per-symbol health panel. |
| New presence | **MR** at `/c/diag/bi5-health` (BI5 R1 BI5HealthPanel) + B-1 scheduler dispatch (60 min, lookback_days=30) + B-9 one-shot backfill script |
| Backend | `api/diag_bi5_health.py`, `data_engine/bi5_ingest_runner.py`, `dukascopy_downloader.py`, `scripts/bi5_one_shot_backfill.py` |
| Missing | The 4 BI5 R2 extended log fields (Evidence Score · Trust Score · Strategy Dossier · Marketplace Quality) — schema-ready but no producer. |
| Recommendation | Acceptable for hydration. Extend log fields when Phase 13/14/15 engines land. |

---

## 6. Net findings — what gets lost / hidden / partially mounted

### 6.1 Real losses (require operator decision)

| # | Item | Severity | Recommended action |
|---|---|---|---|
| L-1 | **Unified Workspace lab** (`MORE-1 / Workspace`) — single-page combining Generator + Analysis + Backtest + Description + cBot + Optim + Validate + Comparison | **HIGH** (operator-critical surface for daily strategy work) | Add `lab/workspace` composite section post-hydration (1–2 h work). Components already imported. |
| L-2 | **Execution composite** (`CORE-2 / Execution`) — `ExecutionDashboard` 3-step strip Generate→Allocate→Execute | **MEDIUM** | Either wire `dashboard/exec-strip` section OR formally retire per visual approval. |
| L-3 | **Standalone Optimization** (`MORE-5 / Optimization`) — `Optimization.js` | **LOW–MEDIUM** | Decide: per-strategy `lab/optim` suffices, OR wire `optimization` MORE-tab. |
| L-4 | **Challenge Profiles** as a sibling of Firm Match | **MEDIUM** | Mount `ChallengeMatchingPanel` at `propfirm/challenge`. |
| L-5 | **Library count badge** in tab label | **LOW** | Add `Library (${savedStrategies.length})` to TopTabBar entry for `saved`. |

### 6.2 Hidden but reachable (acceptable as power-user surfaces)

* `ArchitectDashboard` — palette-only.
* `FactorySupervisorPanel` — Cluster sub-tab + palette.
* `GemFactoryPanel` — Auto Factory bottom debug strip (admin-only) per visual approval.
* `LegacyHome` — `/legacy` route.

### 6.3 Moved (acceptable — no functional loss)

Every legacy CORE_TAB and most MORE_TABS were moved into the new 10-module structure. Mappings are 1:1 or 1:N enriched. See `LEGACY_TO_NEW_MAPPING.md` for the per-screen table.

### 6.4 Merged (acceptable — composites)

* `MonitoringSuite` (Runtime · Soak · Compute · Cluster) absorbed legacy `Monitoring`.
* `MarketDataWorkbench` (Manual · Automated · Archive) absorbed legacy `DataUpload + DataMaintenancePanel`.
* `GovernanceAdminSuite` (Users · Flags · Realism · Tuning · Rules) absorbed legacy `ReadinessPanel + AdminUsers`.
* `MissionBriefing` synthesises the legacy 8-panel Dashboard.

### 6.5 New surfaces (no legacy counterpart — additive)

| Surface | Status |
|---|---|
| TopTabBar (M0) | MR — always visible |
| LifecycleRail (M1) | MR — visible above every module |
| StatusRail | MR — bottom strip |
| OperatorInboxDrawer (M4) | MR — bell button |
| Live NotificationDrawer | MR — ⌘⌥N |
| CopilotPanel | MR — ⌘J (advisory only) |
| Inspector pane | MR — ⌘. |
| CommandPalette | MR — ⌘K |
| ShortcutsOverlay | MR — `?` |
| EmergencyBanner / DangerRibbon | MR — auto-render |
| AsfNotificationDrawer + AriaLiveRegion | MR |
| Mission Briefing | MR — Dashboard module sole section |
| BI5HealthPanel | MR — `/c/diag/bi5-health` |
| SymbolRegistryPanel | MR — `/c/governance/symbol-registry` |
| Phase 13/14/15 reservation cards | PL — placeholders |
| StrategyScoreReservationCard (M3) | PL — placeholder |
| ExecutionBrokerChips | PL — placeholder |
| Architect Dashboard | MH — palette |

---

## 7. Features developed AFTER 1-vCPU — visible workflow audit

The operator-named items below post-date the legacy UI. Each row classifies how visible it is to the operator today.

| Feature | UI Status | Backend Status | Operator-visible workflow? |
|---|---|---|---|
| **Master Bot** | MR | Live | YES — `/c/mutate/master-bot` (Dashboard) + `/c/mutate/master-bot-compile` (Compile). Single home today; visual approval recommends ALSO surfacing under Monitoring → Cluster. |
| **Factory Supervisor** | MH | Dormant (flag OFF) | PARTIAL — palette + Cluster sub-tab. No primary-nav presence. Acceptable while dormant. |
| **DSR (Dynamic Symbol Registry)** | MR | Active post-hydration | YES — `/c/governance/symbol-registry` with full CRUD. |
| **BI5 Health** | MR | Live | YES — `/c/diag/bi5-health`. |
| **Operator Inbox** | MR | UI-only event bus today; backend NC dormant | YES — bell icon → drawer. |
| **Danger Ribbon (EmergencyBanner)** | MR | UI-only (auto-render on small viewports) | YES — auto-visible. |
| **Marketplace** | PL | NOT BUILT | NO — only reservation card at `/c/explorer/marketplace-reservations`. |
| **Strategy Dossier** (Phase 13) | PL | NOT BUILT | NO — only reservation card at `/c/explorer/passport-reservations`. |
| **Auto Valuation** (Phase 14) | PL | NOT BUILT | NO — only reservation card at `/c/portfolio/scorecards-reservations`. |
| **Trust Score architecture** | PL | NOT BUILT | NO — surfaced only in `StrategyScoreReservationCard` (M3) at `/c/explorer/score-rubric`. |
| **Evidence Score architecture** | PL | NOT BUILT | NO — same card. |
| **Pass Probability architecture** | **BO** | Live (computed per strategy) | PARTIAL — value renders inline in `StrategyDashboard`, `StrategyComparison`, `StrategyDetailsPanel`. **No dedicated architecture/lineage view.** Calibration is dormant (`ENABLE_CALIBRATION=false` — identity transform). |

### 7.1 What this means

* **Today's visible operator value**: Master Bot, DSR, BI5 Health, Inbox, Danger Ribbon — all reachable in primary nav.
* **Today's invisible operator value (BO/PL)**: Pass Probability has no dedicated explanation surface; Trust/Evidence/Auto Valuation/Dossier/Marketplace are reservation-only.
* **The post-hydration import pipeline** (re-profile → re-score → re-rank → re-match → re-portfolio → re-masterbot) consumes the existing Pass Probability + RoR + Aging values but does NOT yet produce a Trust/Evidence/Dossier output. That gap is Phase 13/14 work.

---

## 8. Final reconciliation verdict

### 8.1 Hydration safety

**No legacy operator workflow is irretrievably lost.** Every legacy screen has either:
* a 1:1 home in the new shell, OR
* a composite home (MonitoringSuite / MarketDataWorkbench / GovernanceAdminSuite / MissionBriefing), OR
* a power-user palette home (FactorySupervisor / Architect / Gem Factory), OR
* a still-unwired component that exists in the repo and can be mounted in < 2 h (Workspace composite, ExecutionDashboard, standalone Optimization).

The 4–5 missing-mount items are CONFIGURATION oversights, not code losses. They are tracked in §6.1 and fixable post-hydration without backend changes.

### 8.2 What hydration should NOT change

* The 5 audit + 3 plan/report documents already in `/app/memory/`.
* The current `frontend/.env` (preserve pod URL per Option §5.2).
* The `node_modules/` (yarn install reuses).
* The Phase 13/14/15 reservation cards (they exist for layout stability — do not remove).

### 8.3 What hydration SHOULD change

* Replace stub backend (88 LOC) with canonical (687 LOC, 56 routers).
* Replace stub frontend `src/` with canonical (215 new files + M0–M5 chrome).
* Merge `.env` to add JWT_SECRET + ADMIN_* + DSR-3 flag.
* Add `_inventory` slice (`asf_ui_handoff` + `old1vcpu/src`).

### 8.4 Recommended post-hydration follow-up items (do AFTER validation)

| Priority | Item | Effort | Source of truth |
|---|---|---|---|
| **P1** | Mount **Workspace composite** at `lab/workspace` (lab single-page UX) | ~2 h | `04_COMPONENT_REHOUSING_MATRIX.md` row 51–57 |
| **P1** | Verify **Library count badge** in TopTabBar | < 30 min | `01_TAB_ROSTER.md` row MORE-6 |
| **P2** | Mount **ChallengeMatchingPanel** at `propfirm/challenge` | ~30 min | `01_TAB_ROSTER.md` row MORE-3 footnote |
| **P2** | Decide on **ExecutionDashboard** (wire vs retire) | operator decision | matrix rows 13–16 |
| **P2** | Decide on **standalone Optimization** (wire vs leave hidden) | operator decision | matrix row 58 |
| **P3** | Add **MasterBotDashboard** to Cluster sub-tab | ~30 min | matrix row 19 footnote |
| **P3** | Wire **Pass Probability lineage** surface | ~2 h | new — no legacy counterpart |

### 8.5 Authorization signal

This audit confirms hydration can proceed safely. The 4–5 mount-gap items (§6.1) do **not** block hydration — they are post-hydration polish items that can be addressed once the operator has the live shell in front of them to validate.

**Standing by for `EXECUTE HYDRATION` authorization.** Companion document `LEGACY_TO_NEW_MAPPING.md` provides the per-screen lookup table.
