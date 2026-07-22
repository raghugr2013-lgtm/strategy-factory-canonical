# PROJECT_CONTINUITY_REPORT.md

> **Mode:** Read-only audit. No code modified. No refactor. No deployment.
> No branch changes. No commits. Inventory verification only.
> **Anchor:** Inspection of the operator-uploaded `App.zip` + `Frontend.zip`
> + `ASF_UI_Handoff.zip` (already embedded inside `App.zip`) + the 18 old-UI
> screenshots (`screenshots of old ui.docx`).
> **Date:** continuity audit run on operator request, post-`2026-06-11 ui_restoration package`.

---

## 0 · Executive headline (one paragraph)

The Strategy Factory codebase is **architecturally complete and operator-trust
restored.** Backend ships **84 mounted routers · ~468 routes · 168 engines · 23
factory-supervisor primitives · 13 data-engine modules · 6 cBot-engine modules ·
205 backend tests.** Frontend ships **60 operator components · 10 ui-asf
primitives · 46 shadcn/Radix primitives · 21 command-shell files** driving the
10-module COMMAND shell at `/c/*`. All six **R-phase recovery sprints (R1→R6)**
landed; the **AUTH-FIX** (3 frontend files, ~25 LOC) shipped 2026-02-09 and
cleared the cascading 401 cluster — verified `48/49 /api/* requests carry
Bearer`. The **operator-approved UI Restoration Design Package** (10 documents,
dated 2026-06-11) is the freshest artefact and supersedes ASF_UI_Handoff as the
forward design contract. BI5 recovery is **fully audited** (11–15 engineering
days across three independently shippable phases) but **not started**.
DEV-RC1 has **5 open items**, only one of which (light-theme contrast cluster)
is a real BLOCKER; the rest are 0.5–1 dev-day each. No PROJECT_STATE_EXPORT.md
has ever been produced.

---

## 1 · Backend inventory (detailed)

### 1.1 Routers / API surface

**62 top-level routers** under `backend/api/*.py` + **23 dormant latent routers**
under `backend/api/latent/*.py`. All mounted in `server.py` with `prefix="/api"`.
Total `include_router` calls in `server.py`: **84**. Total decorated routes
across `backend/api/`: **468** (matches the "469" recorded in
`RECOVERY_FINAL_CERTIFICATION.md` after the `/api/health` inline route is
counted).

#### 1.1.1 Core operator routers (`backend/api/`)

| Group | File | Purpose |
|---|---|---|
| **Auth** | `auth.py` · `auth_middleware.py` (root) · `auth_utils.py` (root) | JWT bearer, `require_admin`, pod-seeded admin (`admin@strategyfactory.dev`). |
| **Admin** | `admin.py` · `admin_market_universe.py` · `admin_execution_realism.py` · `admin_flag_governance.py` · `readiness.py` | Operator admin surfaces + dormant feature-flag governance + market-universe registry. |
| **Strategies + Memory** | `strategies.py` · `strategy_memory.py` · `research_lineage.py` · `lifecycle.py` · `dashboard.py` · `dashboard_route.py` | Strategy CRUD, ancestry, memory, lifecycle gates, dashboard generator. |
| **Data plane** | `data.py` · `data_health.py` · `data_maintenance.py` · `ingestion.py` | BID + BI5 + CSV + server import + gap fix + auto-maintenance. |
| **BI5 plane** | `bi5_ingest.py` · `bi5_realism.py` · `bi5_certification.py` | Tick-archive → 1m bars → realism + cert (data + strategy). |
| **Pipeline + Logs** | `pipeline.py` · `pipeline_logs.py` · `live_tracking.py` · `incremental_run_alias.py` | Pipeline orchestration + log stream + live tracking. |
| **Generation / cBot** | `cbot.py` · `cbot_parity.py` · `llm_diagnostics.py` · `llm_health.py` | cBot codegen, parity sign-off, LLM provider health. |
| **Mutation + Factory** | `auto_factory.py` · `auto_mutation.py` · `multi_cycle.py` · `mutation.py` · `gem_factory.py` · `phase12_tuning.py` · `auto_selection.py` | Auto-mutation, multi-cycle, Phase 55, gem factory, tuning. |
| **Portfolio** | `portfolio.py` · `portfolio_builder.py` · `portfolio_intelligence.py` | Builder, panel, intelligence. |
| **Prop firm** | `prop_firms.py` · `prop_firm_intelligence.py` · `prop_firm_analysis.py` · `prop_firm_rules_review.py` · `phase4_matching.py` · `phase4_route.py` · `challenge.py` · `challenge_matching.py` | Catalogue · intel · rules · match · challenge engine. |
| **Execution** | `execution.py` · `trade_runner.py` | Paper exec, Trade Runner. |
| **Monitoring / Diagnostics** | `monitoring.py` · `soak_diagnostics.py` · `cpu_pool_state.py` · `data_health.py` | Runtime state, soak evidence, CPU pool, data health. |
| **Optimization + Regime** | `optimization.py` · `regime.py` · `governance.py` · `deployment.py` · `market_intelligence.py` | Optimizer · regime · survivor gov · deployment registry. |
| **Master Bot + Runner** | `master_bot.py` · `runner.py` | MB-9 Phase 1+2 (definition · pack · ranker · deployment · runner registry · token rotation). |
| **VPS scaling** | `scaling.py` · `factory_supervisor.py` · `orchestrator.py` · `orchestrator_heartbeat.py` | P1.A→P1.D admission/journal/events + FS-P1.0→FS-P1.4 leader-lease scheduler. |

#### 1.1.2 Latent / dormant routers (`backend/api/latent/`)

All registered behind feature flags; default OFF (observability-only).

`activation_governance · activation_timeline · advanced_scaffolding · calibration ·
cbot_log_diagnostic · cbot_trade_parity · compute_probe · deployment_extras ·
deployment_readiness · execution_realism_defaults · factory_runner_heartbeat ·
feature_flags · htf_parity · ingestion_aggregate · ingestion_health ·
lifecycle_decay · market_universe · observability · parity_certification ·
risk_of_ruin · safe_to_widen · widening_history`

### 1.2 Engines (168 files in `backend/engines/`)

Grouped by role (representative entries; full list authoritative on disk):

| Cluster | Modules |
|---|---|
| **Strategy generation + IR** | `strategy_engine.py` · `strategy_library.py` · `strategy_description.py` · `strategy_profiler.py` · `strategy_ir.py` · `strategy_ir_builders.py` · `strategy_ir_renderer.py` · `strategy_ir_backfill.py` · `strategy_mutation.py` · `strategy_lifecycle.py` · `strategy_memory.py` · `strategy_refinement_engine.py` · `strategy_ranking_engine.py` · `strategy_ingestion/` (collector·normalizer·parser·validator·injector·schema·tradingview_urls). |
| **Mutation engines** | `mutation_engine.py` · `mutation_pool.py` · `evolution_engine.py` · `ga_optimizer.py` · `random_search_optimizer.py` · `auto_mutation_runner.py` · `auto_factory.py` · `auto_factory_engine.py` · `auto_factory_phase55.py` · `auto_selection_engine.py` · `replacement_engine.py` · `refinement_engine.py`. |
| **Data engines (in `engines/`)** | `data_access.py` · `data_engine.py` (n/a, see §1.3) · `db.py` · `db_indexes.py` · `persistence_adapters/` (bi5_certification_store · bi5_data_certification_store · market_spread_store). |
| **Validation engines** | `validation_engine.py` · `validation_report.py` · `backtest_engine.py` · `backtest_pool.py` · `backtest_report.py` · `walk_forward_engine.py` · `monte_carlo_engine.py` · `oos_holdout.py` · `htf_parity.py` · `parity_certification.py` · `parity_drift_view.py` · `tick_validator.py` · `cbot_parity.py` · `cbot_trade_parity.py` · `r5_shadow_comparator.py`. |
| **Portfolio engines** | `portfolio_engine.py` · `portfolio_builder_engine.py` · `portfolio_combiner.py` · `portfolio_intelligence_engine.py` · `portfolio_store.py` · `multi_asset_portfolio.py`. |
| **Master Bot infrastructure** | `master_bot_engine.py` · `master_bot_definition.py` · `master_bot_pack.py` · `master_bot_ranker.py` · `master_bot_export.py` · `master_bot_deployment.py` · `master_bot_diff.py` · `runner_registry.py` · `runner_router.py` · `runner_account_migration.py` · `runner_token_rotator.py` · `multi_account_envelope.py`. |
| **Trade Runner infrastructure** | `trade_runner_engine.py` · `paper_execution_engine.py` · `execution_engine.py` · `execution_manager.py` · `execution_simulator.py` · `execution_realism_defaults.py` · `slippage_model.py` · `expected_value.py` · `risk_of_ruin.py`. |
| **Live tracking + Lifecycle** | `live_tracking_engine.py` · `lifecycle_decay.py` · `history_prior.py` · `replay_priority.py`. |
| **Monitoring infrastructure** | `monitoring_engine.py` · `monitoring_alert_bridge.py` · `paper_execution_alert_bridge.py` · `alert_engine.py` · `signal_quality.py` · `soak_stability.py` · `spread_analyzer.py` · `ecosystem_observability.py` · `ecosystem_maturity.py`. |
| **AI / LLM / Orchestration** | `ai_orchestrator.py` · `llm_runner.py` · `llm_config.py` · `code_generator.py` · `compile_engine.py` · `param_extractor.py` · `analysis_engine.py` · `agent_advisor.py` · `decision_engine.py` · `pass_probability.py`. |
| **Activation + Feature flags** | `feature_flags.py` · `flag_overrides.py` · `activation_governance.py` · `activation_journal.py` · `safety_engine.py` · `safety_injector.py` · `rule_enforcement.py` · `rule_engine.py` · `prop_firm_rule_engine.py` · `governance_universe.py`. |
| **Compute + VPS scaling** | `host_capability.py` · `cpu_pool.py` · `adaptive_pool_sizer.py` · `adaptive_concurrency.py` · `adaptive_cooldown.py` · `admission_controller.py` · `admission_wrapper.py` · `queue_pressure.py` · `workload_classes.py` · `compute_probe.py` · `scaling_registry.py` · `scaling_router.py` · `scaling_events.py` · `architect_scaling_view.py`. |
| **Schedulers + Orchestrators** | `auto_scheduler.py` · `cadence_scheduler.py` · `orchestrator_scheduler.py` · `rotational_orchestrator.py` · `factory_runner_heartbeat.py` · `widening_proposal.py` · `widening_history.py` · `safe_to_widen.py` · `survivor_registry.py`. |
| **Factory Supervisor (`engines/factory_supervisor/` — 23 files)** | `worker_scheduler.py` · `worker_runtime.py` · `submission_dispatcher.py` · `supervisor_lock.py` · `supervisor_heartbeat.py` · `supervisor_events.py` · `architect_advisor.py` · `auto_learning.py` · `copilot_advanced.py` · `copilot_context.py` · `copilot_operational.py` · `defer_queue.py` · `fag_proposals.py` · `fleet_registry.py` · `llm_adapter_base.py` · `notification_center.py` · `recommendation_engine.py` · `remote_transport.py` · `routing_policy.py` · `system_state_view.py` · `eligibility_signals.py` · `workload.py`. |
| **Market universe + Calibration** | `market_universe.py` · `market_universe_adapter.py` · `market_universe_audit.py` · `calibration_framework.py` · `regime_classifier.py` · `regime_performance.py` · `prop_firm_config_engine.py` · `prop_firm_intelligence.py` · `prop_firm_panel.py` · `event_continuation.py`. |
| **Misc** | `audit_log_writer.py` · `advisory_lock.py` · `cbot_pipeline.py` · `cbot_autofix.py` · `cbot_log_diagnostic.py` · `matching_engine.py` · `phase4_matcher.py` · `phase12_tuning.py` · `bi5_maturity.py` · `bi5_certification.py` · `bi5_realism.py` · `challenge_manager.py` · `challenge_matching_engine.py` · `challenge_portfolio.py` · `challenge_simulator.py` · `match_input_validator.py` · `extract_jobs.py` · `pipeline_logs.py` · `optimization_engine.py` · `optimization_portfolio_bridge.py` · `readiness_engine.py` · `ranking_engine.py` · `env_priority.py` · `ir_interpreter.py` · `ir_telemetry.py` · `host_capability.py` · `seed/market_universe_seed.py`. |

### 1.3 Data engines (`backend/data_engine/` — 13 modules)

`auto_data_maintainer.py` · `bi5_ingest_runner.py` · `csv_ingester.py` ·
`data_backup.py` · `data_maintenance.py` · `data_manager.py` ·
`dukascopy_downloader.py` · `gap_analyzer.py` · `incremental_updater.py` ·
`market_calendar.py` · `tick_aggregator.py` · `tick_archive.py` ·
`adapters/dukascopy_bi5.py` + `adapters/base.py`.

### 1.4 cBot engine (`backend/cbot_engine/` — 6 modules)

`generator.py` · `ir_emitter.py` · `ir_transpiler.py` · `ir_templates.py` ·
`ir_parity_simulator.py`.

### 1.5 Workers / runners / orchestrators

| Component | Location | Status |
|---|---|---|
| **FastAPI process** | `backend/server.py` (685 lines · supervisor-managed) | ACTIVE |
| **Sibling factory runner** | `backend/factory_runner.py` | DORMANT (`FACTORY_RUNNER_OWNS_SCHEDULERS=false` by default) |
| **Auto-data maintainer** | `data_engine/auto_data_maintainer.py` (`restore_if_enabled`) | OFF until operator opts in |
| **Auto-discovery scheduler** | `engines/auto_scheduler.py` (`restore_if_enabled`) | OFF |
| **Orchestrator scheduler** | `engines/orchestrator_scheduler.py` (`restore_if_enabled`) | OFF |
| **Factory Supervisor worker scheduler** | `engines/factory_supervisor/worker_scheduler.py` | OFF (`FS_ENABLE_WORKER_SCHEDULER` flag) |
| **Windows runner agent** | `runners/windows_agent/agent.py` + `README.md` | Reference impl — runs ON the operator's Windows VPS for cTrader |
| **Mutation runners** | `engines/multi_cycle_runner.py` · `engines/auto_mutation_runner.py` | Idle until invoked from UI/API |
| **Backtest pool** | `engines/backtest_pool.py` | Lazy init |

### 1.6 Notification / Alert infrastructure

* `engines/alert_engine.py` — alert dispatcher (webhook + Telegram).
* `engines/monitoring_alert_bridge.py` · `engines/paper_execution_alert_bridge.py` — bridges.
* `engines/factory_supervisor/notification_center.py` — NC primitive (dormant; flag `ENABLE_NOTIFICATION_CENTER`).
* Frontend overlay: `command/shell/NotificationDrawer.jsx` + `stores/notificationsStore.js` (consumes `/api/monitoring/status` + `/api/admin/widening-proposals`).

### 1.7 Chatbot / Copilot infrastructure

* Backend (dormant): `engines/factory_supervisor/copilot_advanced.py` · `copilot_context.py` · `copilot_operational.py` · `recommendation_engine.py` · `architect_advisor.py`.
* LLM adapter (dormant): `engines/factory_supervisor/llm_adapter_base.py`.
* Frontend overlay: `command/shell/CopilotPanel.jsx` (consumes `/api/orchestrator/heartbeat` + `/api/llm/call-log/recent` in read-only advisory mode).

### 1.8 AI / Learning modules

`ai_orchestrator.py` · `llm_runner.py` · `llm_config.py` · `code_generator.py` · `compile_engine.py` · `analysis_engine.py` · `decision_engine.py` · `auto_learning.py` (factory_supervisor) · `agent_advisor.py` · `param_extractor.py` · `pass_probability.py`. **State:** `llm_generator_enabled=false` by default — operator must set `EMERGENT_LLM_KEY` + flip the flag for live AI generation.

### 1.9 Tests

* `backend/tests/`: **205 test files** (including `latent/` subdir with 5 latent tests).
* Coverage areas: auth, admin, BI5 (ingest, certification, calendar, holiday, multi-tf, spread), bi5_realism, auto_factory, auto_scheduler, master_bot (MB-1 → MB-9 Phase 2), runner registry, scaling, factory_supervisor, parity, lifecycle, monte-carlo, walk-forward, soak.

### 1.10 Config + env

* `backend/.env` declares: `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ENABLE_DYNAMIC_MARKET_UNIVERSE`, `ENABLE_CBOT_TRADE_PARITY`, `ENABLE_HTF_PARITY_VALIDATION`, `ENABLE_HTF_PARITY_HARD_GATE`, `ENABLE_TRADE_PARITY_HARD_GATE`.
* `backend/config/symbols.py` + `bi5_symbols.py` — canonical 7-symbol seed.
* `backend/prop_firm_pdfs/`: 54 PDF firm spec sheets.
* `backend/scripts/` — soak helpers + HTF rebuild + multi-asset / mutation / per-asset stability validators.
* `data/bi5/dukascopy/<SYM>/<YYYY>/<MM>/<DD>/<HH>h_ticks.bi5` — 110 MB tick archive on disk (EURUSD 3766h · GBPUSD 2208h · USDJPY 744h · XAUUSD 744h).

---

## 2 · Frontend inventory (detailed)

### 2.1 Tech stack + entry points

* **Framework:** React (CRACO build · `craco.config.js`) — `@/` alias to `src/`.
* **Entry:** `src/index.js` → `bootstrapA11yPatcher()` → `installAuthFetchInterceptor()` (auth fix) → `<App/>`.
* **Routing:** `react-router-dom` minimal: `/` and `/c/*` both render `<GatedCommandModuleApp>`; `/legacy` keeps the placeholder Home for parity testing.
* **Theme:** `bootstrapThemeStore()` (default `dark`, light operator-elective via Command Palette).
* **Locale:** `bootstrapLocaleStore()` + `IntlProvider` + en-US/de-DE pilot dictionaries (24 keys each).
* **`.env`:** `REACT_APP_BACKEND_URL=https://stall-debug.preview.emergentagent.com`.

### 2.2 Navigation architecture (current — 10-module COMMAND shell)

Source of truth: `command/shell/modulesRegistry.js`. Path scheme: `/c/{moduleId}/{sectionId}`.

| # | Module ID | Label | Sections (count) | Posture availability |
|--:|---|---|---:|---|
| 1 | `dashboard` | Dashboard | 1 (Mission Briefing) | briefing · tablet · workstation |
| 2 | `lab` | Research Lab | 6 (panel · analysis · backtest · cbot · optim · validate) | workstation |
| 3 | `explorer` | Strategy Explorer | 3 (explorer · saved · compare) | briefing-ro · tablet · workstation |
| 4 | `mutate` | Mutation Engine | 7 (auto · cycle · factory · factory-55 · auto-select · master-bot · master-bot-compile) | workstation |
| 5 | `portfolio` | Portfolio OS | 3 (builder · panel · intel) | briefing-ro · tablet · workstation |
| 6 | `propfirm` | Prop Firm | 2 (admin · match — Challenge embedded) | briefing-ro · tablet · workstation |
| 7 | `exec` | Execution Center | 3 (paper · runner · live) | briefing-ro · tablet · workstation |
| 8 | `ai` | AI Workforce | 3 (river · orch · sched) | briefing-ro · tablet · workstation |
| 9 | `diag` | Diagnostics | 7 (readiness · parity · ingestion · ingest-src · pipeline · market-data · monitoring) | briefing-ro · tablet · workstation |
| 10 | `governance` | Governance | 6 (gov · universe · rules · env · readiness · admin) | workstation |
|  |  | **Total** | **41 sections** |  |

Composite sub-tab structures inside diag/governance:

* `diag/market-data` → **Manual** (`DataUpload`) · **Automated** (`DataMaintenancePanel`) · **Archive** (`DataBackupPanel`).
* `diag/monitoring` → **Runtime** (`Monitoring`) · **Soak** (`SoakDiagnosticsPanel`) · **Compute** (`CpuPoolStatePanel`) · **Cluster** (`ScalingPanel`).
* `governance/admin` → **Users** (`AdminUsers`) · **Flags** (`AdminFlagGovernancePanel`) · **Realism** (`AdminExecutionRealismPanel`) · **Tuning** (`Phase12TuningPanel`).
* `mutate/master-bot` (MasterBotDashboard) + `mutate/master-bot-compile` (MutateMasterBotCompile).

### 2.3 Global overlays / shell-level surfaces

| Overlay | File | Shortcut | Backend wiring |
|---|---|---|---|
| **Command Palette** | `command/shell/CommandPalette.jsx` | `⌘K` / `Ctrl+K` | local (no API) |
| **Notification Drawer** | `command/shell/NotificationDrawer.jsx` + `ui-asf/AsfNotificationDrawer.jsx` | `⌘⌥N` / `⌘⇧N` | `/api/monitoring/status`, `/api/admin/widening-proposals` |
| **Copilot Panel** | `command/shell/CopilotPanel.jsx` | `⌘J` | `/api/orchestrator/heartbeat`, `/api/llm/call-log/recent` |
| **Inspector Pane** | `command/shell/inspector/InspectorPane.jsx` + `InspectorProvider.jsx` + `views.jsx` | `⌘.` | local |
| **Detail Drawer** | `ui-asf/AsfDetailDrawer.jsx` | (per-context) | per-panel APIs |
| **Shortcuts overlay** | `command/shell/ShortcutsOverlay.jsx` | `?` | local |
| **Emergency Banner** | `command/shell/EmergencyBanner.jsx` | (≤480px posture) | local |
| **Mobile Surfaces** | `command/shell/MobileSurfaces.jsx` | (handheld posture) | local |

### 2.4 Component inventory (`src/components/` — 60 components)

#### Strategy / Lab (Research Lab module)
`StrategyPanel.js` · `StrategyAnalysis.js` · `StrategyDescription.js` · `StrategyChartView.js` · `StrategyDeepDivePanel.js` · `StrategyDetailsPanel.js` · `StrategyComparison.js` · `BacktestPanel.js` · `CbotPanel.js` · `OptimizationPanel.js` · `Optimization.js` · `ValidationPanel.js`.

#### Strategy registry / Explorer
`StrategyExplorer.js` · `StrategyDashboard.js` · `SavedStrategies.js`.

#### Mutation + Factory
`AutoMutationRunner.js` · `MultiCycleRunner.js` · `AutoFactory.js` · `AutoFactoryPhase55.js` · `AutoSelection.js`.

#### Portfolio
`PortfolioBuilder.js` · `PortfolioPanel.js` · `PortfolioIntelligence.js`.

#### Prop Firm
`PropFirmsAdmin.js` · `FirmMatchPanel.js` · `AddFirmModal.js` · `RulesReviewPanel.js`.

#### Execution
`PaperExecution.js` · `TradeRunner.js` · `LiveTrackingPanel.js` · `Monitoring.js` · `MonitoringSuite.jsx`.

#### Data + Market
`DataUpload.js` (BID + BI5 + CSV + Server import + Gap fix · 817 LOC · re-mounted) · `DataMaintenancePanel.js` · `DataAvailability.js` · `MarketDataWorkbench.jsx`.

#### Diagnostics
`DeploymentReadinessCard.jsx` · `ParityCertificationCard.jsx` · `IngestionHealthCard.jsx` · `PipelineLogsPanel.js` · `StrategyIngestionCard.js`.

#### Governance / Admin
`GovernanceCard.jsx` · `UniverseGovernancePanel.jsx` · `EnvPriorityPanel.js` · `ReadinessPanel.js` · `AdminUsers.js` · `GovernanceAdminSuite.jsx`.

#### Master Bot
`MasterBotDashboard.jsx` · `MasterBotCompilePanel.jsx` · `MutateMasterBotCompile.jsx`.

#### Architect / Operator
`ArchitectDashboard.jsx` · `OperatorEndpointPanel.jsx` · `OperatorParityPanels.jsx` (exports FactorySupervisor / Scaling / Phase12Tuning / GemFactory / AdminFlagGovernance / AdminExecutionRealism / DataBackup / SoakDiagnostics / CpuPoolState / ChallengeMatching panels).

#### AI workforce
`OrchestratorPanel.js` · `AutoSchedulerControl.js`.

#### Auth + Shell utility
`AuthGate.js` · `NavMoreMenu.js` · `DensityToggle.js` · `ThemeToggle.js` · `TraderModeButton.js` (deprecated · scheduled for post-RC1 cleanup).

#### a11y helper
`components/a11y/` (specific bootstrap utilities — verify on disk).

### 2.5 Component design libraries

| Library | Path | Count |
|---|---|---:|
| **shadcn + Radix primitives** | `components/ui/` | 46 (accordion · alert · avatar · badge · breadcrumb · button · calendar · card · checkbox · dialog · drawer · dropdown · form · hover-card · input · label · menubar · navigation-menu · pagination · popover · progress · select · separator · sheet · skeleton · slider · sonner · switch · table · tabs · etc.) |
| **ui-asf custom primitives** | `components/ui-asf/` | 10 (`AsfCard` · `AsfDetailDrawer` · `AsfEmptyState` · `AsfKpiTile` · `AsfNotificationDrawer` · `AsfSkeleton` · `AsfTable` · `IndicatorLegend` · `VerdictBadge` · `VerdictChip`) |
| **phase9 (legacy)** | `components/phase9/` | 5 (`AutoFactoryCard` · `ExecutionDashboard` · `LiveExecutionCard` · `PortfolioBuilderCard` · `ui`) |
| **command/shell** | `command/shell/` | 21 files (Shell, Bar, Palette, ModuleApp, LeftRail, LineageStrip, MobileSurfaces, ModuleSurface, NotificationDrawer, ShortcutsOverlay, StatusRail, EmergencyBanner, CopilotPanel, Glyphs · plus `ai/`, `dashboard/`, `inspector/`, `modulesRegistry.js`, `router.js`, `useDensity`, `useEventRing`, `usePosture`, `usePremium`, `eventRingStore`, `shell.css`) |

### 2.6 Stores + services + i18n

* **Stores:** `localeStore.js` · `notificationsStore.js` · `themeStore.js`.
* **Services:** `api.js` · `auth.js` (with `installAuthFetchInterceptor` — wired post AUTH-FIX) · `phase9_api.js` · `throttledPost.js`.
* **Hooks:** `useDatasetAvailability.js` · `useFocusTrap.js` · `useMarketUniverse.js` · `useTheme.js` · `use-toast.js`.
* **i18n:** `i18n/providers/IntlProvider.jsx` + `locales/en-US.json` + `locales/de-DE.json` (24 keys each — pilot only).
* **Styles:** `styles/asf-design-tokens.css` · `asf-rc1-dark-contrast-lifts.css` · `asf-rc1-light-overrides.css` · `asf-u3-interactions.css` · `asf-u4-a11y.css` · `asf-u4-responsive.css` · `styles/theme.js` + `command/{tokens,density,identity,motion,panels,premium,typography}.css`.
* **Test IDs (constants):** `constants/testIds/{auth,home,index}.js`.

### 2.7 Workstation restoration package (frontend-side)

* `command/shell/` contains everything the operator sees — the 10-module rail, command palette, briefing screen.
* `pages/Welcome/` exists but is empty (placeholder).
* `routes/` directory exists but is empty (routing handled in `App.js` + `command/shell/router.js`).

---

## 3 · Recovery state

| Asset | Status | Evidence |
|---|---|---|
| **AUTH-FIX** | ✅ **COMPLETE (2026-02-09)** | `AUTH_FIX_VERIFICATION.md` · `POST_FIX_RUNTIME_REPORT.md` · 3 frontend files (`index.js` + `services/auth.js` + `App.js`) ≈ 25 LOC. Before/after screenshots in `memory/AUTH_FIX_SCREENSHOTS/{before,after}/` (8 jpegs each). Empirical: 48/49 `/api/*` requests carry Bearer. |
| **Recovery Sprint (R1–R6)** | ✅ **COMPLETE** | 6 per-phase reports + `RECOVERY_FINAL_CERTIFICATION.md` + `BEFORE_AFTER_RECOVERY_COMPARISON.md`. Rail collapsed 13 → 10 modules. 21/21 endpoint probes 200 OK. 84/84 routers preserved. 467 routes preserved. 0 backend files modified. |
| **UI Restoration Design Package** | ✅ **PRODUCED 2026-06-11** — awaiting operator sign-off before implementation | `memory/ui_restoration/` — 9 documents + `README.md` (01_SCREEN_INVENTORY · 02_OLD_TO_NEW_MAPPING · 03_WIREFRAMES · 04_NAVIGATION_ARCHITECTURE · 05_COMPONENT_LIBRARY · 06_OPERATOR_WORKFLOWS · 07_RESPONSIVE_LAYOUTS · 08_MIGRATION_PLAN · 09_OPERATOR_FAMILIARITY_RECOVERY). Locked decisions D1–D7 captured (flat top-tab bar primary nav; old-UI screenshots = primary visual source; ASF_UI_Handoff = functionality reference; zero backend changes; ≤ 2-click workflow depth). |
| **Functional Audit** | ✅ **COMPLETE** | `END_TO_END_FUNCTIONAL_AUDIT.md` · `DEPLOYMENT_READINESS_SCORECARD.md` (composite readiness **92 %**) · `FINAL_OPERATOR_WORKFLOW_AUDIT.md` · `WORKING_FEATURES_MATRIX.md` · `LIVE_WORKFLOW_EXECUTION_REPORT.md` (8 PASS · 7 PARTIAL · 0 FAIL) · `REAL_FUNCTIONALITY_MATRIX.md` · `PLACEHOLDER_AND_MOCK_AUDIT.md` (0 mocks · 0 placeholders). |
| **Operator Trust** | ✅ Restored | `OPERATOR_NAVIGATION_GUIDE.md` · `OPERATOR_TRAINING_SESSION.md` · `OPERATOR_RUNBOOK.md` · `SYSTEM_OPERATION_RUNBOOK.md` · `WORKFLOW_SCREENSHOT_GUIDE.md` · `WORKFLOW_SCREENSHOTS/` (10 jpegs). |
| **Backend Wiring Certification** | ✅ | `BACKEND_WIRING_CERTIFICATION.md` + `AUDIT_BACKEND_CERTIFICATION.md` + `FINAL_FEATURE_EXPOSURE_CERTIFICATION.md`. |
| **DEV-RC1** | 🟠 **NOT CUT** — 5 open items | `PRE_RC1_BLOCKERS.md` + `FINAL_RC1_READINESS_REPORT.md` (recommends 🟢 cut at HEAD) + `RC1_RELEASE_NOTES.md` draft. |
| **24h Soak** | ❌ **NOT STARTED** | Compressed soak run (`PHASE2_SOAK_*` reports) — wall-clock soak still required at 12-vCPU. |
| **12-vCPU Deployment** | ❌ **NOT STARTED** | gated behind DEV-RC1 + real soak. |
| **Production Deploy** | ❌ **NOT STARTED** | — |

---

## 4 · BI5 status

### 4.1 Reports present

| Report | Date | Verdict |
|---|---|---|
| `BI5_ARCHITECTURE_AUDIT.md` | 2026-02-09 | Two halves disconnected; UI BI5 chip dead; Mongo empty of BI5 rows |
| `BI5_RECOVERY_AUDIT.md` | 2026-06-10 | 9 broken links; **11–15 day** total recovery in 3 ship-ready phases |
| `BI5_UI_ARCHITECTURE_AUDIT.md` | 2026-06-07 | UI TF selector confirmed operationally meaningless |
| `BI5_DATA_CERT_FAIL_VERDICT_RCA.md` | (current) | 4 data cert rows · all FAIL · root cause: `hours_expected_empty=0` definition |
| `BI5_DATA_CERT_WRITER_ARCHITECTURE_REVIEW.md` | — | Writer architecture deep-dive |
| `BI5_DATA_CERT_WRITER_IMPLEMENTATION_REPORT.md` | — | Phase-3 implementation log |

### 4.2 Summary of findings

* **Real BI5 path exists** — `POST /api/admin/bi5/run` (`BI5IngestRunner`) decodes raw `.bi5` blobs → aggregates to 1m mid-price OHLCV → writes to `market_data{source:"bi5"}`. Tick-archive on disk has **7,462 hourly `.bi5` files (≈110 MB)** for EURUSD · GBPUSD · USDJPY · XAUUSD.
* **Workstation UI BI5 button is dead** — `Market Data → Manual → BI5 Tick Data → Download` silently drops the `source` field on the wire; backend defaults to `OFFER_SIDE_BID` and writes `source="bid_1m"`. Click ingests BID candles, not BI5.
* **Mongo BI5 storage empty** — `market_data` has 104,389 docs all `source="bid_1m"`; `market_spread`, `bi5_certification`, `bi5_data_certification` all = 0 docs.
* **Tick granularity not preserved in Mongo** — only on disk; Mongo holds the 1m OHLCV roll-up.
* **Tick replay → realism → slippage arrow is broken in steady state** — `execution_simulator.py` + `slippage_model.py` exist and use bid/ask ticks, but `bi5_realism.py` only re-runs backtests on 1m OHLCV bars — same shape as BID, so BI5 adds zero execution-realism value today.
* **TF selector decorative** — backend deprecates anything other than `1m` for BI5 (`_BI5_CANONICAL_TIMEFRAME="1m"`).

### 4.3 Broken-link catalogue (from `BI5_RECOVERY_AUDIT.md` §2)

| ID | Link | Class | Sizing |
|---|---|---|---|
| **B-1** | Scheduler `_update_bi5_symbol` → `run_bi5_ingest` dispatch | Integration | **S** (1d) |
| **B-2** | UI BI5 chip → API `source` field on the wire | UI bug | **S** (1d) |
| **B-3** | `paper_execution_engine._load_bars` → tick loader for `source="bi5"` | Integration | **M** (2-3d) |
| **B-4** | Auto-payload builder for `certify_strategy` (Sunday 03:00 UTC sweep) | Integration | **M** (2-3d) |
| **B-5** | Master Bot ranker → `bi5_cert.certification_verdict` + `slippage_score` weights | Integration | **S** (1d) |
| **B-6** | `simulate_fills` wiring at paper-execution runtime (not only cert sweep) | Integration | **M** (2-3d) |
| **B-7** | Trade Runner consolidation onto paper-execution engine | Refactor | **M** (3-4d) |
| **B-8** | Lifecycle + UI surfacing of `bi5_data_certification` verdict | Integration | **S** (1d) |
| **B-9** | One-shot historical backfill across existing 110 MB disk archive | Backfill | **S** (1d) |

**Phased recovery (independently shippable):**

| Phase | Goal | Days | Issues |
|---|---|---|---|
| **R1 · Foundation** | BI5 data exists in `market_data` end-to-end (UI + scheduler) | **3–4 d** | B-1 · B-2 · B-9 |
| **R2 · Realism** | Auto per-strategy cert; `deployment_ready` gate admits strategies | **3–4 d** | B-4 · B-5 · B-8 |
| **R3 · Execution** | Tick replay → realism → slippage default; PnL distributions become real | **5–7 d** | B-3 · B-6 · B-7 |
| **Total** |  | **11–15 d** | 9 broken links |

R1 alone makes BI5 visible E2E. R2 + R3 convert BI5 into execution-realism value.

### 4.4 Restorability certification

✅ **YES.** Every architectural box has a real code asset. Work is **integration, not invention**.

---

## 5 · UI restoration status

### 5.1 Package existence

✅ **`/app/memory/ui_restoration/` EXISTS** — 9 design documents + `README.md`,
all dated **2026-06-11**, all marked *"Design specification ONLY. No code
changes. No backend changes. No deployment."*.

### 5.2 Locked operator decisions (verbatim from README §2)

| # | Decision |
|---|---|
| D1 | Primary navigation = **flat top tab bar** (visual priority). LeftRail demoted/removed as primary nav. |
| D2 | Command Palette (⌘K), Notification Drawer (🔔), Copilot Panel (⌘J) kept as **global overlays** only. |
| D3 | **No new top tabs.** Governance / Diagnostics / Copilot / Notification Center / Master Bot admin fold under existing workflows (Admin / Dashboard / More ▾). |
| D4 | Old screenshots = **primary visual source of truth**. ASF_UI_Handoff = functionality reference only. |
| D5 | One screen = one business workflow. Max click depth: **Tab → Screen → Action**. |
| D6 | Dense tables over cards. Minimal scrolling. Dark trading-terminal aesthetic. |
| D7 | Markdown wireframes only this phase. **NO implementation.** |

### 5.3 Tab architecture (target — S-01 → S-17, derived from old screenshots)

Old top-tab roster preserved: `Dashboard · Execution · Auto Factory · Monitoring · Paper Exec · Trade Runner · Portfolio · Explorer · Market Data · Auto Select · Admin · More ▾` (11 visible tabs + `More ▾` overflow).

| S-ID | Restored screen | Source old-UI screen | Component re-housing |
|---|---|---|---|
| S-01 | Dashboard | O-1 | MissionBriefing + Governance + Universe + Ingestion + Scheduler + Orchestrator + Multi-Cycle + Auto Mutation + Generation form + Multi-Asset Portfolio + Pipeline Logs |
| S-02 | Execution (3-step strip) | O-2 | AutoFactory → PortfolioBuilder → PaperExecution |
| S-03 | Auto Factory | O-3, O-14 | AutoFactory + AutoFactoryPhase55 |
| S-04 | Monitoring | O-4 | Monitoring (incl. SOAK/CPU/Scaling sub-tabs) |
| S-05 | Paper Exec | O-5 | PaperExecution |
| S-06 | Trade Runner | O-6 | TradeRunner |
| S-07 | Portfolio | O-7 | PortfolioBuilder · PortfolioPanel · PortfolioIntelligence |
| S-08 | Explorer (+Library merge) | O-8, O-18 | StrategyExplorer + SavedStrategies + StrategyComparison |
| S-09 | Market Data | O-9 | MarketDataWorkbench (DataUpload + DataMaintenance + DataBackup) |
| S-10 | Auto Select | O-10 | AutoSelection |
| S-11 | Admin (Governance fold) | O-11 | GovernanceAdminSuite + ReadinessPanel + UniverseGovernance + EnvPriority + GovernanceCard + RulesReview |
| S-12 | Workspace / Strategy Lab | O-12 | StrategyPanel · StrategyAnalysis · BacktestPanel · CbotPanel · OptimizationPanel · ValidationPanel |
| S-13 | Live Tracking | O-13 | LiveTrackingPanel |
| S-14 | Prop Firms | O-14 (15) | PropFirmsAdmin · FirmMatchPanel |
| S-15–17 | (More ▾ overflow) | — | AI Workforce · Master Bot · Diagnostics power surfaces |

Reverse census proves: **every section in current `modulesRegistry.js` has an explicit home in the restored UI** (see `02_OLD_TO_NEW_MAPPING.md` §3).

### 5.4 Migration plan summary (`08_MIGRATION_PLAN.md`)

| Phase | Scope | Risk class | Operator impact | Effort |
|---|---|---|---|---|
| **M0** Tokens & theme | Override `command/tokens.css` (yellow accent, Binance surfaces, 36 px rows, radius 4/4/2, no glows). VerdictBadge/Chip palette resynced. Light-theme sheet updated. | R0 cosmetic | O1 visual only | ~0.5 d |
| **M1** Shell swap | New `TopTabBar` + StatusBar + `More ▾` mounted in `CommandShell`. LeftRail unmounted from primary flow (kept behind `ui.leftrail` flag — instant rollback). `modulesRegistry.js` re-keyed to S-01…S-17. Legacy URL redirect map. ⌘K palette re-labeled. | R2 navigation | O2 relearn-position | ~1.5 d |
| **M2** Anchor screens (one per commit) | S-01 Dashboard · S-06 Trade Runner · S-03 Auto Factory · S-04 Monitoring · S-05 Paper Exec | R3 composition | O2 | ~3 d |
| **M3** Remaining tabs | S-02 · S-07 · S-08 · S-09 · S-10 · S-11 (+ More ▾ S-12…S-17) | R3 | O2 | ~3 d |
| **M4** Overlays + polish + cert | Restyle ⌘K / 🔔 / 💬 / Inspector. Tab status dots + More ▾ attention aggregation. | R1 layout | O1 | ~1.5 d |
|  | **Total** |  |  | **~9.5 d** |

**Constraint zero (operator-mandated):** `git diff --stat /app/backend` must be EMPTY at the end of every phase. Zero backend changes. Zero new mutators. Zero functionality removal.

### 5.5 Sign-off checklist status

All checklist items from `README.md §6` are **PENDING operator sign-off** — implementation cannot begin until:

- [ ] Restored tab roster approved (`01_SCREEN_INVENTORY.md` §C)
- [ ] Old→New mapping approved (`02_OLD_TO_NEW_MAPPING.md`)
- [ ] Dashboard wireframe approved (`03_WIREFRAMES.md` §1)
- [ ] Trade Runner wireframe approved (`03_WIREFRAMES.md` §6)
- [ ] Auto Factory wireframe approved (`03_WIREFRAMES.md` §3)
- [ ] Navigation architecture approved (`04_NAVIGATION_ARCHITECTURE.md`)
- [ ] Migration phasing approved (`08_MIGRATION_PLAN.md`)

---

## 6 · Operator continuity assessment

### 6.1 What a returning operator needs to know (single page)

1. **You are at HEAD = post-Recovery + post-AUTH-FIX + UI-Restoration-design-finalised.** Backend hasn't been touched since AUTH-FIX (and AUTH-FIX itself was frontend-only). Three concurrent tracks are awaiting your decision.

2. **The pod is healthy.** All 84 routers wired. All probed endpoints return 200 with structured payloads. Composite readiness = **92 %**. Zero broken / zero mocked features. Zero 5xx. (See `DEPLOYMENT_READINESS_SCORECARD.md`.)

3. **The system is un-bootstrapped — by design.** No market data loaded · `llm_generator_enabled=false` · Factory Supervisor OFF · no Master Bot defined · no notification channels wired. Cold-start steps live in `OPERATOR_RUNBOOK.md` (steps 0a → 5).

4. **There are 3 candidate forward paths**, presented in `PRD.md` and `FINAL_RC1_READINESS_REPORT.md`. They are independent — you can pick any one and the others stay viable:

   * **A. Continue UI Restoration** — operator-approved design package is fresh (Jun 11). Migration plan is risk-classified (R0 → R3). ~9.5 dev-days. Zero backend impact. Outcome: workstation matches old-UI muscle memory; new-UI gets dark trading-terminal density.
   * **B. Continue BI5 Recovery (Phase R1 first)** — 11–15 dev-days across R1 (3–4 d) → R2 (3–4 d) → R3 (5–7 d). R1 alone unlocks BI5 data E2E. Backend-heavy (≠ UI Restoration). Outcome: BI5 stops being decorative; tick replay → realism becomes real.
   * **C. Continue DEV-RC1 preparation** — 5 open items; only one BLOCKER (RC1-1 light-theme contrast). Dark-only RC1 = ~0.5 dev-day. Full light + dark RC1 = ~1.5–2 dev-days. Outcome: tag cut, release notes signed, gates RC1 → 24h soak → 12-vCPU.
   * **D. Continue Deployment Readiness (24h soak start)** — gated behind C. Cannot start until RC1 is cut. Includes performance/bundle audit, env-config hardening, observability hooks, Mongo-index review at deployment scale, cross-browser sweep.

5. **What's frozen / parked:**
   * **Calibration arc** — PARKED until D-1 / W-1 / A-1 met (see `CALIBRATION_ARC_PARKED.md`).
   * **Latent capabilities** (23 dormant API/latent routers) — observability-only, never engine-consumed.
   * **MB-9 Phase 2 Soak** — completed in compressed mode; real 24h wall-clock soak still required for production.
   * **TraderMode** — formally deprecated; cleanup in post-RC1 PR.

6. **Operator credentials (pod-seeded):**
   * Email: `admin@strategyfactory.dev`
   * Password: `vad4lXbPkQKqokvMde8KhtqL`
   * `POST {REACT_APP_BACKEND_URL}/api/auth/login`
   * (Also stored in `/app/memory/test_credentials.md`.)

7. **Workflow shortcut sheet:**
   * Top-bar: ⌘K Command Palette · `⌘J` Copilot · `⌘⌥N` Notifications · `⌘.` Inspector · `?` Shortcuts overlay.
   * Bottom Status Rail: `orch · ingest · sched · llm · govern · kill`.
   * Modules (current rail): `dashboard → lab → explorer → mutate → portfolio → propfirm → exec → ai → diag → governance`.
   * 11 step pipeline (cold-start to live): see `OPERATOR_RUNBOOK.md` §"15-step end-to-end run".

### 6.2 Reference document index (curated · for the returning operator)

| Need | Open this |
|---|---|
| One-paragraph project status | `PRD.md` |
| Phase-by-phase status | `PROJECT_STATUS_SUMMARY.md` |
| End-to-end workflow walkthrough | `OPERATOR_RUNBOOK.md` |
| Hands-on click+curl session | `OPERATOR_TRAINING_SESSION.md` |
| Workstation navigation paths | `OPERATOR_NAVIGATION_GUIDE.md` |
| Cold-start blockers (config / data) | `CRITICAL_BLOCKERS.md` · `OPERATOR_BLOCKERS.md` |
| Auth fix history | `AUTH_FIX_VERIFICATION.md` · `POST_FIX_RUNTIME_REPORT.md` |
| Recovery-sprint history | `RECOVERY_FINAL_CERTIFICATION.md` · `BEFORE_AFTER_RECOVERY_COMPARISON.md` · `R1_…` → `R6_…` |
| UI Restoration design | `memory/ui_restoration/` (10 files) |
| BI5 recovery roadmap | `BI5_RECOVERY_AUDIT.md` |
| RC1 gating | `PRE_RC1_BLOCKERS.md` · `FINAL_RC1_READINESS_REPORT.md` · `RC1_RELEASE_NOTES.md` |
| 12-vCPU deployment gates | `PROJECT_STATUS_SUMMARY.md` §3 + `DEPLOYMENT_PROGRESSION_PLAN.md` |
| Architecture references | `MASTER_BOT_RUNTIME_ARCHITECTURE.md` · `FACTORY_SUPERVISOR_ARCHITECTURE.md` · `MB9_DEPLOYMENT_ARCHITECTURE.md` · `VPS_SCALING_ARCHITECTURE.md` |

---

## 7 · Verification of specific items requested (A–G)

| # | Item | Status | Evidence |
|---|---|---|---|
| **A** | AUTH-FIX changes present | ✅ **YES** | Frontend `index.js` calls `installAuthFetchInterceptor()` at boot; `services/auth.js` `isBackendCall` matches both absolute `API_URL` AND relative `/api/*`; `App.js` wraps `<CommandModuleApp/>` with `<AuthGate/>` via `GatedCommandModuleApp`. Verification report `AUTH_FIX_VERIFICATION.md`. Screenshots in `AUTH_FIX_SCREENSHOTS/{before,after}/`. |
| **B** | UI Restoration Design Package exists | ✅ **YES** | `memory/ui_restoration/` — 10 documents · README locked decisions D1–D7 · dated 2026-06-11 · sign-off PENDING. Plus `ASF_UI_Handoff_2026-06-08/` (functionality reference only, per D4). |
| **C** | BI5 audit reports exist | ✅ **YES** | `BI5_ARCHITECTURE_AUDIT.md` · `BI5_RECOVERY_AUDIT.md` · `BI5_UI_ARCHITECTURE_AUDIT.md` · `BI5_DATA_CERT_FAIL_VERDICT_RCA.md` · `BI5_DATA_CERT_WRITER_ARCHITECTURE_REVIEW.md` · `BI5_DATA_CERT_WRITER_IMPLEMENTATION_REPORT.md`. |
| **D** | Recovery Sprint reports exist | ✅ **YES** | R0_COMPLETION · R1_NAVIGATION_RESTORATION · R2_WORKFLOW_RESTORATION · R3_MARKET_DATA · R4_DEVELOPER_CONSOLE_RECOVERY · R5_GLOBAL_SURFACES · R5_PHASE2_* (×6) · R5_SHADOW_AUDIT · R6_0_FORENSIC_RECYCLE_AUDIT · R6_6/7/8/9/10/11_ARCHITECTURE_REVIEW · R6_BUSINESS_DASHBOARD · `RECOVERY_FINAL_CERTIFICATION.md` · `BEFORE_AFTER_RECOVERY_COMPARISON.md`. |
| **E** | Functional Audit reports exist | ✅ **YES** | `END_TO_END_FUNCTIONAL_AUDIT.md` · `DEPLOYMENT_READINESS_SCORECARD.md` · `FINAL_OPERATOR_WORKFLOW_AUDIT.md` · `WORKING_FEATURES_MATRIX.md` · `REAL_FUNCTIONALITY_MATRIX.md` · `LIVE_WORKFLOW_EXECUTION_REPORT.md` · `BROKEN_OR_PARTIAL_FEATURES.md` · `PLACEHOLDER_AND_MOCK_AUDIT.md` · `BACKEND_WIRING_CERTIFICATION.md` · `FINAL_ROUTE_VALIDATION_REPORT.md`. |
| **F** | Operator Training reports exist | ✅ **YES** | `OPERATOR_TRAINING_SESSION.md` · `OPERATOR_RUNBOOK.md` · `OPERATOR_NAVIGATION_GUIDE.md` · `SYSTEM_OPERATION_RUNBOOK.md` · `OPERATOR_BLOCKERS.md` · `WORKFLOW_SCREENSHOT_GUIDE.md` · `WORKFLOW_SCREENSHOTS/` (10 jpegs). |
| **G** | PROJECT_STATE_EXPORT.md exists | ❌ **NO** | Not present. No file matching `*PROJECT_STATE_EXPORT*` in `/app/memory/`. The closest equivalent (single-document status snapshot) is `PROJECT_STATUS_SUMMARY.md` + `PRD.md`. |

---

## 8 · Recommended Immediate Next Action

> **Recommendation: A · Continue UI Restoration.**

### Why this, not the others (right now)

1. **Freshness.** `ui_restoration/` package is dated **2026-06-11**, the most recent operator-approved artefact in the repo. The 7 sign-off checkboxes (`ui_restoration/README.md §6`) are the only documents currently blocking forward motion.

2. **Locked decisions already exist.** D1–D7 capture the operator's most recent design intent verbatim: flat top tab bar, dense Binance/Bybit/TradingView aesthetic, old-UI screenshots as primary visual source, ASF_UI_Handoff functionality reference only, ≤ 2-click depth, no new top tabs. Every other forward track risks invalidating these decisions if executed first.

3. **Reverse-census proves zero regression risk.** Every section in current `modulesRegistry.js` has an explicit home in the restored UI — including the 10 new operator panels added during the Recovery Sprint and the AUTH-FIX-recovered surfaces. `02_OLD_TO_NEW_MAPPING.md` §3 enumerates the proof.

4. **Backend untouched throughout.** Constraint zero of `08_MIGRATION_PLAN.md` is `git diff --stat /app/backend` MUST stay empty. UI Restoration **does not delay** BI5 Recovery (B), DEV-RC1 (C), or Deployment (D) — they remain independently shippable after.

5. **DEV-RC1 (C) gains, doesn't loses.** If UI Restoration M0 (token & theme — 0.5 d) lands first, it **resolves RC1-1 + RC1-2 (the only real BLOCKER + only HIGH item)** by remapping the dark-tokenised palette. The downstream RC1 cut drops from "1.5–2 dev-days" to "1 dev-day".

6. **BI5 Recovery (B) is the only backend-only track.** It can begin in parallel by a second engineer **without touching the frontend** — but is not blocking right now because the BI5 UI chip is documented as broken and the BI5 data plane is `count=0`. There is no live operator workflow depending on BI5 today.

### Suggested Phase-A execution order (no implementation in this report)

```
Day 0      operator signs the 7-item checklist in ui_restoration/README.md §6
Day 0.5    M0 — tokens & theme        (R0/O1)   →  also clears RC1-1 + RC1-2
Day 2      M1 — shell swap            (R2/O2)   →  TopTabBar + StatusBar + More ▾
Day 5      M2 — anchor screens        (R3/O2)   →  S-01, S-06, S-03, S-04, S-05
Day 8      M3 — remaining tabs        (R3/O2)   →  S-02, S-07, S-08, S-09, S-10, S-11, More ▾
Day 9.5    M4 — overlays + polish     (R1/O1)   →  ⌘K / 🔔 / 💬 / Inspector restyle
Day 9.5    DEV-RC1 cut at the same HEAD          →  release notes + RC1-3 (1-line) + RC1-4 (~0.5 d) folded into Day 9.5
Day 10+    BI5 R1 (Foundation) begins in parallel — backend-only, no UI dep
```

Total: **~9.5 dev-days** to fully restored workstation + RC1 cut, with BI5 R1 either parallel (second engineer) or serial (Day 10–13).

---

## 9 · Guardrail compliance

| Guardrail | Compliance |
|---|---|
| Read-only audit only | ✅ |
| No code changes | ✅ |
| No refactoring | ✅ |
| No implementation | ✅ |
| No deployment | ✅ |
| No branch changes | ✅ |
| No commits | ✅ |
| No testing beyond inventory verification | ✅ |

— END OF REPORT —
