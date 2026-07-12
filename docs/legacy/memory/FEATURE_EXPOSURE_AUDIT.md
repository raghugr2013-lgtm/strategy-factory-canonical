# FEATURE_EXPOSURE_AUDIT.md

**Audit type:** Phase 1 — Full Feature Exposure Audit
**Scope:** Strictly read-only. No code modified.
**Canonical sources:** `App.zip/App/backend/` (backend), `Frontend.zip/src/` (frontend).
**Live pod (`/app`) status:** NOT yet hydrated — all evidence is drawn from the zips.

---

## Classification key

| Code | Meaning |
|---|---|
| **A — Mounted & reachable** | Backend router included; UI section in `modulesRegistry.js`; reachable from the rail or palette without flags. |
| **B — Mounted but hidden** | Backend router included; UI exists; only reachable via Command Palette (⌘K) or deep link — not in primary nav. |
| **C — Exists in code, not mounted** | Module/component file is in the repo but **not** imported by `server.py` or `modulesRegistry.js`. |
| **D — Backend only (no frontend)** | API works; no operator UI. Verdict-quality endpoint, advisory engine, or admin-CRUD. |
| **E — Frontend only (no backend)** | UI exists; backend endpoint does not (yet). |
| **F — Dormant behind feature flag(s)** | Code shipped; flag defaults preserve byte-identical pre-flag behaviour. |
| **G — Reservation only** | Placeholder card / stub doc. No engine, no real endpoint. |
| **H — Dead code** | Imports unused. No router, no UI consumer. |
| **I — Removed / deprecated** | Existed in backup, intentionally removed. |

---

## 1. Strategy Generation, AI & Research Lab

| Subsystem | Class | Backend file(s) | Frontend component(s) | Route / Endpoint | Flag(s) | Scheduler | Ready |
|---|---|---|---|---|---|---|---|
| **Strategy Generator (Strategy Panel)** | A | `api/strategies.py`, `engines/strategy_engine.py`, `engines/strategy_library.py`, `engines/random_search_optimizer.py` | `components/StrategyPanel.js` (`lab/panel`) | `/api/strategies/*` | none | n/a | Y |
| **Strategy Output / Description / Details** | A | `engines/strategy_description.py`, `engines/strategy_ir*.py` (renderer + builders + backfill) | `StrategyDescription.js`, `StrategyDetailsPanel.js`, `StrategyChartView.js`, `StrategyDeepDivePanel.js` | `/api/strategies/<id>`, `/api/strategies/<id>/description` | none | n/a | Y |
| **AI Analysis** | A | `engines/analysis_engine.py`, `api/dashboard.py` | `StrategyAnalysis.js` (`lab/analysis`) | `/api/strategies/<id>/analysis`, `/api/dashboard/generate` | none | n/a | Y |
| **Indicator Ideas / Strategy DNA** | D | `engines/strategy_engine.py`, `engines/strategy_ir_builders.py` (DNA hashing inside) | (no dedicated panel — surfaced inline in `StrategyDetailsPanel`) | — | none | n/a | Y |
| **Random Search Optimizer** | D | `engines/random_search_optimizer.py` (called via Optimization) | `OptimizationPanel.js` consumes the entrypoint | `/api/optimization/*` | none | n/a | Y |
| **AI Architecture (Copilot)** | F | `engines/factory_supervisor/copilot_operational.py`, `copilot_advanced.py` + `command/shell/CopilotPanel.jsx` | `CopilotPanel.jsx` (⌘J overlay) | `/api/orchestrator/heartbeat`, `/api/llm/call-log/recent` (consumed) | `FS_ENABLE_COPILOT` (OFF), `FS_ENABLE_COPILOT_ADVANCED` (OFF), `FS_COPILOT_PROVIDER=none` | n/a | Advisory-only, dormant |
| **LLM Generator / LLM Health / LLM Diagnostics** | A | `engines/llm_runner.py`, `llm_config.py`, `api/llm_diagnostics.py`, `api/llm_health.py` | `command/shell/ai/LlmCallRiver` (`ai/river`) | `/api/llm/*` | LLM provider env vars | n/a | Y |
| **Auto Learning Infrastructure** | F | `engines/factory_supervisor/auto_learning_*` (aggregator) | (no dedicated panel — read via Architect Dashboard) | exposed indirectly via Factory Supervisor surfaces | `FS_ENABLE_AUTO_LEARNING` (OFF), `FS_ENABLE_AUTO_LEARNING_LOOP` (strictly OFF — operator veto) | n/a | Dormant, no loop |

## 2. Mutation, Auto-Factory, Selection

| Subsystem | Class | Backend file(s) | Frontend component(s) | Endpoint | Flag(s) | Scheduler | Ready |
|---|---|---|---|---|---|---|---|
| **Mutation Engine** | A | `engines/mutation_engine.py`, `engines/strategy_mutation.py`, `engines/mutation_pool.py`, `api/mutation.py` | (consumed by Auto Factory + Auto Mutation Runner) | `/api/mutation/*` | `ENABLE_ANTI_CORRELATION_FILTER` (OFF), `ENABLE_PROCESS_POOL_MUTATION` (OFF) | n/a | Y |
| **Auto Mutation Runner** | A | `api/auto_mutation.py`, `engines/auto_mutation_runner.py` | `AutoMutationRunner.js` (`mutate/auto`) | `/api/auto-mutation/*` | none | APScheduler (`auto_scheduler.py`) | Y |
| **Multi-Cycle Runner** | A | `api/multi_cycle.py`, `engines/multi_cycle_runner.py` | `MultiCycleRunner.js` (`mutate/cycle`) | `/api/multi-cycle/*` | none | n/a | Y |
| **Auto Factory** | A | `api/auto_factory.py`, `engines/auto_factory.py`, `engines/auto_factory_engine.py`, `auto_factory_phase55.py` | `AutoFactory.js`, `AutoFactoryPhase55.js` (`mutate/factory*`) | `/api/auto-factory/*` | none | APScheduler | Y |
| **Auto Selection** | A | `api/auto_selection.py`, `engines/auto_selection_engine.py` | `AutoSelection.js` (`mutate/auto-select`) | `/api/auto-selection/*` | none | n/a | Y |
| **Validation Engine** | A | `engines/validation_engine.py`, `engines/validation_report.py` | `ValidationPanel.js` (`lab/validate`) | `/api/strategies/<id>/validate` | none | n/a | Y |
| **Walk Forward** | A | `engines/walk_forward_engine.py` | consumed by ValidationPanel | (sub-route of validate) | none | n/a | Y |
| **OOS Validation** | A | `engines/oos_holdout.py` | consumed by ValidationPanel | (sub-route of validate) | none | n/a | Y |
| **Monte Carlo** | A | `engines/monte_carlo_engine.py` | consumed by ValidationPanel | (sub-route of validate) | none | n/a | Y |
| **Pass Probability** | A | `engines/pass_probability.py` | rendered in `StrategyDashboard`, `StrategyComparison` | `/api/strategies/<id>` (embedded field) | `ENABLE_CALIBRATION` (OFF — identity transform applied) | n/a | Y, identity transform |
| **Backtest Engine + Pool** | A | `engines/backtest_engine.py`, `backtest_pool.py`, `backtest_report.py` | `BacktestPanel.js` (`lab/backtest`) | `/api/strategies/<id>/backtest` | `ENABLE_PROCESS_POOL_BACKTEST` (OFF) | n/a | Y |

## 3. Prop Firm, Challenge, Rules

| Subsystem | Class | Backend file(s) | Frontend | Endpoint | Flag(s) | Ready |
|---|---|---|---|---|---|---|
| **Prop Firm Registry / Admin** | A | `api/prop_firms.py`, `engines/prop_firm_config_engine.py`, `prop_firm_intelligence.py` | `PropFirmsAdmin.js`, `AddFirmModal.js` (`propfirm/admin`) | `/api/prop-firms/*` | none | Y |
| **Prop Firm Engine + Rule Engine** | A | `engines/prop_firm_rule_engine.py`, `rule_enforcement.py`, `rule_engine.py` | `RulesReviewPanel.js` (`governance/rules`) | `/api/prop-firm-rules-review/*` | none | Y |
| **Prop Firm Intelligence** | A | `api/prop_firm_intelligence.py`, `prop_firm_analysis.py` | (consumed inside Firm Match) | `/api/prop-firm-intelligence/*`, `/api/prop-firm-analysis/*` | none | Y |
| **Firm Match (Phase 4)** | A | `api/phase4_matching.py`, `engines/phase4_matcher.py`, `matching_engine.py` | `FirmMatchPanel.js` (`propfirm/match`) | `/api/match-firms-phase4`, `/api/phase4-matching/*` | none | Y |
| **Challenge Simulator + Matching** | B | `api/challenge.py`, `engines/challenge_simulator.py`, `challenge_manager.py`, `challenge_matching_engine.py`, `api/challenge_matching.py` | `OperatorParityPanels.jsx::ChallengeMatchingPanel` (Power-User sub-tab in Governance Admin) | `/api/challenge/*`, `/api/challenge-matching/*` | none | Y |

## 4. Portfolio & Master Bot

| Subsystem | Class | Backend file(s) | Frontend | Endpoint | Flag(s) | Ready |
|---|---|---|---|---|---|---|
| **Portfolio Builder** | A | `api/portfolio_builder.py`, `engines/portfolio_builder_engine.py` | `PortfolioBuilder.js` (`portfolio/builder`) | `/api/portfolio-builder/*` | none | Y |
| **Portfolio Panel** | A | `api/portfolio.py`, `engines/portfolio_engine.py`, `portfolio_combiner.py`, `portfolio_store.py`, `multi_asset_portfolio.py` | `PortfolioPanel.js` (`portfolio/panel`) | `/api/portfolio/*` | none | Y |
| **Portfolio Intelligence** | A | `api/portfolio_intelligence.py`, `engines/portfolio_intelligence_engine.py`, `optimization_portfolio_bridge.py` | `PortfolioIntelligence.js` (`portfolio/intel`) | `/api/portfolio-intelligence/*` | none | Y |
| **Master Bot V1 — definition, engine, ranker, export** | A | `engines/master_bot_*.py` (8 files), `api/master_bot.py` | `MasterBotDashboard.jsx`, `MutateMasterBotCompile.jsx`, `MasterBotCompilePanel.jsx` (`mutate/master-bot*`) | `/api/master-bot/*` | none for core; `RUNNER_AUTO_ROUTE_AT_REGISTER` (OFF), `RUNNER_MULTI_ACCOUNT_ENABLED` (OFF), `RUNNER_AUTO_ROTATE` (OFF) for multi-runner | Y for single-runner |

## 5. Trade Runner & Execution

| Subsystem | Class | Backend file(s) | Frontend | Endpoint | Flag(s) | Ready |
|---|---|---|---|---|---|---|
| **Paper Execution** | A | `api/execution.py`, `engines/paper_execution_engine.py`, `execution_engine.py`, `execution_manager.py`, `execution_simulator.py` | `PaperExecution.js` (`exec/paper`) | `/api/execution/*` | none | Y |
| **Trade Runner** | A | `api/trade_runner.py`, `engines/trade_runner_engine.py` | `TradeRunner.js` (`exec/runner`) | `/api/trade-runner/*` | none | Y |
| **Live Tracking** | A | `api/live_tracking.py`, `engines/live_tracking_engine.py` | `LiveTrackingPanel.js` (`exec/live`) | `/api/live-tracking/*` | none | Y |
| **Execution Realism Defaults** | F | `engines/execution_realism_defaults.py`, `api/latent/execution_realism_defaults.py`, `api/admin_execution_realism.py` | `OperatorParityPanels.jsx::AdminExecutionRealismPanel` | `/api/latent/execution-realism-defaults`, `/api/admin/execution-realism/*` | `ENABLE_EXECUTION_REALISM_DEFAULTS` (OFF) | Dormant — registry-only |
| **Runner Registry / Token Rotator / Router** | F | `engines/runner_*.py`, `multi_account_envelope.py`, `parity_drift_view.py`, `api/runner.py` | (none — admin CRUD only) | `/api/master-bot/runners/*` | `RUNNER_AFFINITY_POLICY`, `RUNNER_AUTO_ROTATE`, `RUNNER_MULTI_ACCOUNT_ENABLED`, `RUNNER_AUTO_ROUTE_AT_REGISTER` | Single-runner mode active |
| **Broker Accounts Chip Row** (Track A/B + cTrader Live/Demo + VPS) | G | (nothing) | `reservations/ExecutionBrokerChips.jsx` (top of `exec`) | — | — | Placeholder only |
| **cBot Generator + Transpiler** | A | `cbot_engine/` (5 files), `api/cbot.py` | `CbotPanel.js` (`lab/cbot`) | `/api/cbot/*` | none | Y |
| **cBot Parity (Signal)** | A | `engines/cbot_parity.py`, `api/cbot_parity.py` | `ParityCertificationCard.jsx` (`diag/parity`) | `/api/cbot-parity/*` | none | Y |
| **cBot Trade Parity (Lifecycle)** | F | `engines/cbot_trade_parity.py`, `api/latent/cbot_trade_parity.py` | (none) | `/api/latent/cbot-trade-parity` | `ENABLE_CBOT_TRADE_PARITY` (OFF) | Dormant simulator |
| **HTF Parity Validation** | F | `engines/htf_parity.py`, `api/latent/htf_parity.py` | (none) | `/api/latent/htf-parity` | `ENABLE_HTF_PARITY_VALIDATION` (OFF) | Dormant |
| **Parity Hard-Gate Certification** | F | `engines/parity_certification.py`, `api/latent/parity_certification.py` | embedded in `ParityCertificationCard` | `/api/latent/parity-certification` | `ENABLE_TRADE_PARITY_HARD_GATE`, `ENABLE_HTF_PARITY_HARD_GATE` (both OFF) | Dormant aggregator |
| **cBot Log Diagnostic** | A | `api/latent/cbot_log_diagnostic.py`, `engines/cbot_log_diagnostic.py` | (operator script — paste-blob endpoint) | `/api/latent/cbot-log-diagnostic` | none | Y, operator-driven |
| **cTrader Integration / Windows Agent** | E/G | (none in backend) | — | — | — | **Not built** — only "Broker Accounts" chip placeholder |

## 6. Market Data, BI5, DSR

| Subsystem | Class | Backend file(s) | Frontend | Endpoint | Flag(s) | Scheduler | Ready |
|---|---|---|---|---|---|---|---|
| **Market Data Manual (CSV/BID/BI5 upload)** | A | `api/data.py`, `data_engine/csv_ingester.py`, `tick_archive.py`, `tick_aggregator.py` | `DataUpload.js` (under `MarketDataWorkbench`, `diag/market-data`) | `/api/data/*` | none | n/a | Y |
| **Auto Data Maintenance** | A | `api/data_maintenance.py`, `data_engine/auto_data_maintainer.py`, `incremental_updater.py`, `gap_analyzer.py` | `DataMaintenancePanel.js` (under `MarketDataWorkbench`) | `/api/data-maintenance/*` | none | APScheduler (BID 15 min, BI5 60 min) | Y |
| **Data Backup** | A | `api/data_maintenance.py::backup_router`, `data_engine/data_backup.py` | `OperatorParityPanels.jsx::DataBackupPanel` (under `MarketDataWorkbench`) | `/api/data-backup/*` | none | n/a | Y |
| **Data Health** | A | `api/data_health.py` | (consumed by `IngestionHealthCard`) | `/api/data-health/*` | none | n/a | Y |
| **Ingestion Health Aggregate** | A | `api/latent/ingestion_aggregate.py`, `engines/ingestion_health_aggregate.py` | `IngestionHealthCard.jsx` (`diag/ingestion`) | `/api/latent/ingestion-aggregate` | none | n/a | Y |
| **Strategy Ingestion** | A | `engines/strategy_ingestion/`, `api/ingestion.py` | `StrategyIngestionCard.js` (`diag/ingest-src`) | `/api/ingestion/*` | none | n/a | Y |
| **BI5 Realism + Certification** | A | `api/bi5_realism.py`, `bi5_certification.py`, `engines/bi5_realism.py`, `bi5_maturity.py`, `bi5_certification.py` | (consumed within strategy outputs) | `/api/bi5-realism/*`, `/api/bi5-cert/*` | none | n/a | Y |
| **BI5 Ingest (manual + scheduled)** | A | `api/bi5_ingest.py`, `data_engine/bi5_ingest_runner.py`, `dukascopy_downloader.py`, `adapters/dukascopy_bi5.py` | exposed via `DataUpload` (BI5 source select), `DataMaintenance` | `POST /api/admin/bi5/run`, `GET /api/admin/bi5/symbols` | none | called by `auto_data_maintainer._update_bi5_symbol` (B-1 ✓) | Y |
| **BI5 R1 — Per-symbol Health (Coverage % · Last Sync · Last Gap Repair · Ticks · Status)** | A | `api/diag_bi5_health.py` (`GET /api/diag/bi5/health`) | `BI5HealthPanel.jsx` (`diag/bi5-health`) | `/api/diag/bi5/health` | none | n/a | Y |
| **BI5 R1 — One-shot historical backfill (B-9)** | D | `scripts/bi5_one_shot_backfill.py` | (CLI only) | n/a | none | n/a | Y |
| **DSR · Engine (market_universe)** | A (read) / F (consumption) | `engines/market_universe.py`, `market_universe_adapter.py`, `market_universe_audit.py`, `api/latent/market_universe.py`, `api/admin_market_universe.py` | `SymbolRegistryPanel.jsx` (`governance/symbol-registry`) ← **DSR-1 UI** | `GET /api/latent/market-universe`, `POST /api/admin/market-universe`, `…/{sym}/tier`, `…/{sym}/enable`, `DELETE` | `ENABLE_DYNAMIC_MARKET_UNIVERSE` (OFF), `MARKET_UNIVERSE_DEFAULT_TIER=candidate`, `MARKET_UNIVERSE_AUTO_INGEST` (OFF), `MARKET_UNIVERSE_AUDIT_TTL_DAYS=90` | (seeded at startup; consumption gated by flag) | DSR-1 UI Y, DSR-2 ingestion Y, **DSR-3 dynamic universe still flag-gated OFF** |
| **DSR-2 · Scheduler consumes registry** | F | `data_engine/auto_data_maintainer.py::_ingestion_symbols` reads registry when flag ON | (auto) | (auto) | gated by `ENABLE_DYNAMIC_MARKET_UNIVERSE` | YES (consults registry); flag OFF → legacy `SYMBOL_CONFIG` fallback | Y (shadow audit ready) |
| **Dukascopy Downloader** | A | `data_engine/dukascopy_downloader.py`, `adapters/dukascopy_bi5.py` | consumed by BI5 ingest + DataUpload | (no direct route) | none | n/a | Y |
| **Tick Validator** | A | `engines/tick_validator.py` | (used inside ingestion) | n/a | none | n/a | Y |
| **Market Calendar / Session** | A | `data_engine/market_calendar.py` | (used inside ingestion) | n/a | none | n/a | Y |
| **Governance Universe (allowed pair × TF × style)** | A | `engines/governance_universe.py` | `UniverseGovernancePanel.jsx` (`governance/universe`) | `/api/governance/*` | none | n/a | Y |
| **Spread Analyzer / Slippage** | D | `engines/spread_analyzer.py`, `slippage_model.py` | (used inside execution; no panel) | n/a | none | n/a | Y |

## 7. Diagnostics, Monitoring, Soak

| Subsystem | Class | Backend file(s) | Frontend | Endpoint | Flag(s) | Ready |
|---|---|---|---|---|---|---|
| **Deployment Readiness** | A | `engines/readiness_engine.py`, `api/readiness.py`, `api/latent/deployment_readiness.py`, `latent/deployment_extras.py` | `DeploymentReadinessCard.jsx` (`diag/readiness`) | `/api/readiness/*`, `/api/latent/deployment-readiness`, `/api/latent/deployment-extras` | none | Y |
| **Pipeline Logs** | A | `api/pipeline_logs.py`, `engines/pipeline_logs.py`, `api/pipeline.py` | `PipelineLogsPanel.js` (`diag/pipeline`) | `/api/pipeline-logs/*` | none | Y |
| **Monitoring (Runtime)** | A | `api/monitoring.py`, `engines/monitoring_engine.py`, `monitoring_alert_bridge.py`, `alert_engine.py` | `Monitoring.js` (under `MonitoringSuite`, `diag/monitoring`) | `/api/monitoring/*` | none | Y |
| **Soak Diagnostics** | A | `api/soak_diagnostics.py`, `engines/soak_stability.py` | `OperatorParityPanels.jsx::SoakDiagnosticsPanel` (under `MonitoringSuite`) | `/api/soak-diagnostics/*` | `ENABLE_SOAK_STABILITY_EMITTER` (OFF — emitter no-op until ON) | Y (read), F (emit) |
| **CPU Pool State** | A | `engines/cpu_pool.py`, `api/cpu_pool_state.py` | `OperatorParityPanels.jsx::CpuPoolStatePanel` (under `MonitoringSuite`) | `/api/cpu-pool/state` | `USE_PROCESS_POOL`, `ENABLE_PROCESS_POOL_*`, `ENABLE_ADAPTIVE_POOL_SIZING` (all OFF) | Y |
| **Scaling Engine / VPS Allocation** | F | `engines/scaling_*.py`, `host_capability.py`, `adaptive_pool_sizer.py`, `queue_pressure.py`, `admission_controller.py`, `api/scaling.py` | `OperatorParityPanels.jsx::ScalingPanel` (under `MonitoringSuite`) | `/api/scaling/*` | `ENABLE_BAND_BASED_ROUTING`, `ENABLE_ADMISSION_CONTROL`, `ENABLE_ADAPTIVE_POOL_SIZING` (all OFF) | Dormant — observability live |
| **Compute Probe** | A | `engines/compute_probe.py`, `api/latent/compute_probe.py` | (consumed by Scaling + Architect) | `/api/latent/compute-probe` | none | Y |
| **Orchestrator Heartbeat** | A | `api/orchestrator_heartbeat.py` | StatusRail polls this | `/api/orchestrator/heartbeat` | none | Y |
| **Factory Runner Heartbeat** | A | `engines/factory_runner_heartbeat.py`, `api/latent/factory_runner_heartbeat.py` | embedded in `DeploymentReadinessCard` | `/api/latent/factory-runner-heartbeat` | none | Y |

## 8. Governance, Admin, Activation

| Subsystem | Class | Backend file(s) | Frontend | Endpoint | Flag(s) | Ready |
|---|---|---|---|---|---|---|
| **Governance Card (Promotion)** | A | `api/governance.py`, `engines/governance_universe.py`, `survivor_registry.py`, `replacement_engine.py`, `safe_to_widen.py`, `widening_history.py`, `widening_proposal.py` | `GovernanceCard.jsx` (`governance/gov`) | `/api/governance/*`, `/api/latent/safe-to-widen`, `/api/latent/widening-history` | none | Y |
| **Universe Governance** | A | `engines/governance_universe.py` | `UniverseGovernancePanel.jsx` (`governance/universe`) | `/api/governance/universe/*` | none | Y |
| **Rules Review** | A | `api/prop_firm_rules_review.py` | `RulesReviewPanel.js` (`governance/rules`) | `/api/prop-firm-rules-review/*` | none | Y |
| **Env Priority** | A | `engines/env_priority.py` | `EnvPriorityPanel.js` (`governance/env`) | `/api/env-priority/*` | `ENABLE_ADAPTIVE_ROTATION` (OFF) | Y |
| **Admin · Users** | A | `api/admin.py`, `api/auth.py`, `auth_utils.py`, `auth_middleware.py` | `AdminUsers.js` (Power-User sub-tab in `GovernanceAdminSuite`) | `/api/admin/*`, `/api/auth/*` | none | Y |
| **Admin · Flag Governance** | A | `api/admin_flag_governance.py`, `engines/activation_governance.py`, `flag_overrides.py`, `engines/feature_flags.py`, `api/latent/feature_flags.py`, `latent/activation_governance.py`, `latent/activation_timeline.py` | `OperatorParityPanels.jsx::AdminFlagGovernancePanel` (sub-tab) | `/api/admin/flag-governance/*`, `/api/latent/feature-flags`, `/api/latent/activation-governance`, `/api/latent/activation-timeline` | self-aware (this IS the registry) | Y |
| **Admin · Execution Realism Defaults** | A | `api/admin_execution_realism.py` | `OperatorParityPanels.jsx::AdminExecutionRealismPanel` | `/api/admin/execution-realism/*` | gated by `ENABLE_EXECUTION_REALISM_DEFAULTS` (OFF) | Y, registry-only |
| **Admin · Market Universe (DSR)** | A | `api/admin_market_universe.py` | `SymbolRegistryPanel.jsx` (now), older `OperatorParityPanels` access | `/api/admin/market-universe/*` | gated by `ENABLE_DYNAMIC_MARKET_UNIVERSE` (OFF) for runtime consumption | Y |
| **Phase 12 Tuning** | A | `api/phase12_tuning.py`, `engines/phase12_tuning.py` | `OperatorParityPanels.jsx::Phase12TuningPanel` (sub-tab) | `/api/phase12-tuning/*` | none | Y |
| **Readiness Panel** | A | `engines/readiness_engine.py` (already listed) | `ReadinessPanel.js` (`governance/readiness`) | `/api/readiness/*` | none | Y |
| **Activation Governance / Activation Timeline** | A (read-only) | `engines/activation_governance.py`, `audit_log_writer.py`, `engines/feature_flags.emit_boot_audit_event/emit_override_diff_event` | (read via Admin Flag Gov + Activation Timeline endpoints) | `/api/latent/activation-governance`, `/api/latent/activation-timeline` | none (advisory only) | Y |

## 9. AI Workforce, Copilot, Factory Supervisor

| Subsystem | Class | Backend file(s) | Frontend | Endpoint | Flag(s) | Ready |
|---|---|---|---|---|---|---|
| **AI Workforce Live River** | A | `engines/llm_runner.py`, `api/llm_diagnostics.py` | `command/shell/ai/LlmCallRiver` (`ai/river`) | `/api/llm/call-log/recent` | none | Y |
| **Orchestrator** | A | `api/orchestrator.py`, `engines/ai_orchestrator.py`, `decision_engine.py`, `orchestrator_scheduler.py`, `rotational_orchestrator.py` | `OrchestratorPanel.js` (`ai/orch`) | `/api/orchestrator/*` | `ENABLE_AUTONOMOUS_DISCOVERY` (OFF), `ENABLE_ROTATIONAL_ORCHESTRATION` (OFF), `COMPUTE_AWARE_ORCHESTRATION` (OFF) | Y, schedulers static |
| **Auto-Scheduler Control** | A | `engines/auto_scheduler.py` | `AutoSchedulerControl.js` (`ai/sched`) | `/api/auto-scheduler/*` (within auto-mutation/orchestrator) | `ENABLE_CADENCE_SCHEDULER` (OFF), `ENABLE_ADAPTIVE_COOLDOWN` (OFF) | Y |
| **Factory Supervisor (FS-P1.0..1.4)** | F | `engines/factory_supervisor/` (subdir, ≈20 modules: supervisor_lock, supervisor_heartbeat, supervisor_events, defer_queue, submission_dispatcher, worker_scheduler, recommendation_engine, eligibility_signals, fag_proposals, copilot_*, auto_learning_*, system_state_view) + `api/factory_supervisor.py` | `OperatorParityPanels.jsx::FactorySupervisorPanel`, `ArchitectDashboard.jsx` (reachable via ⌘K only) | `/api/factory-supervisor/*` | `ENABLE_FACTORY_SUPERVISOR` (OFF), `FS_ENABLE_*` (all OFF) | Dormant. Worker scheduler boot hook present (gated). |
| **Notification Center** | F (consumption) / A (write) | `engines/factory_supervisor/supervisor_events.py`, NC API endpoints inside factory_supervisor | `command/shell/NotificationDrawer.jsx`, `AsfNotificationDrawer.jsx`, `command/shell/EmergencyBanner.jsx`, `command/shell/DangerRibbon.jsx` | `/api/notifications/*`, `/api/factory-supervisor/notifications/*` | `ENABLE_NOTIFICATION_CENTER` (OFF), `FS_ENABLE_NOTIFICATION_API` (OFF) | Live UI; backend persists when ON |
| **Operator Inbox** | A | uses `notifications` store + `inboxEvents.js` (frontend bus) | `command/shell/OperatorInboxDrawer.jsx`, `inboxEvents.js` (M4) | (frontend-only event bus today) | none | Y, frontend-only event store |
| **Architect Dashboard** | F | `engines/factory_supervisor/architect_advisor.py`, `architect_scaling_view.py` | `ArchitectDashboard.jsx` (palette-only) | `/api/factory-supervisor/architect/*` | `FS_ENABLE_ARCHITECT_DASHBOARD` (OFF) | Dormant — advisor only |

## 10. M0–M5 UI Restoration Program (Visual chrome)

| Item | Class | Frontend file | Mount | Notes |
|---|---|---|---|---|
| **M0 · Top Tab Bar** | A | `command/shell/TopTabBar.jsx` (160 LOC) | `CommandShell.jsx` line 275 | Operator nav above CommandBar. |
| **M1 · Lifecycle Rail** | A | `command/shell/LifecycleRail.jsx` (166 LOC) | `CommandShell.jsx` line 277 | Stage timeline (Generate → Mutate → Validate → Score → Master Bot → Deploy). |
| **Status Rail** | A | `command/shell/StatusRail.jsx` | mounted unconditionally | Bottom-strip chips (orchestrator, LLM, ingestion). |
| **M2 · Mission Control shell + Phase 13/14/15 reservation cards** | A | `command/shell/dashboard/MissionBriefing.jsx`; `command/reservations/Phase13ReservationsCard.jsx`, `Phase14DualScorecardCard.jsx`, `Phase15MarketplaceReservation.jsx`, `ExecutionBrokerChips.jsx`, `StrategyScoreReservationCard.jsx` (M3) | dashboard module + explorer + portfolio + exec | Placeholders. |
| **M3 · Strategy Score Architecture (Quality · Evidence · Market · Trust)** | G | `reservations/StrategyScoreReservationCard.jsx` | `explorer/score-rubric` | Reservation only — no backend scoring. |
| **M4 · Operator Inbox + Notification framework** | A | `OperatorInboxDrawer.jsx` (255 LOC) + `inboxEvents.js` (129 LOC) + `DangerRibbon.jsx` + `NotificationDrawer.jsx` + `AsfNotificationDrawer.jsx` + `stores/notificationsStore.js` | `CommandShell.jsx` | UI-complete; backend NC dormant. |
| **M5 · Phase 13/14/15 reservations + visual approval package locked in `memory/visual_approval_package/`** | G | (same as M2) | (same) | Confirmed via `/memory/visual_approval_package/10_…_DOSSIER_VALUATION_MARKETPLACE.md`. |
| **Strategy Dossier Engine** | G | — | `Phase13ReservationsCard.jsx` only | **Not yet built.** |
| **Automated Valuation Engine** | G | — | `Phase14DualScorecardCard.jsx` only | **Not yet built.** |
| **Marketplace Layer** | G | — | `Phase15MarketplaceReservation.jsx` only | **Not yet built.** |

## 11. Auth, Theme, i18n, Inspector

| Item | Class | Backend/Frontend | Notes |
|---|---|---|---|
| **JWT Auth + AuthGate + Admin Seed** | A | `api/auth.py`, `auth_utils.py`, `auth_middleware.py`, `api/admin.py`; `components/AuthGate.js` | Email/password login, hashed creds. Admin auto-seeded at startup. |
| **Theme (dark default, light optional)** | A | `stores/themeStore.js` + Command Palette (`cmd:theme-toggle`) | `ThemeToggle.js` removed (intentional). |
| **i18n (en-US, de-DE)** | A | `stores/localeStore.js` + `i18n/providers/IntlProvider.js` + Command Palette (`cmd:lang-cycle`) | Locales discoverable. |
| **Inspector Pane** | A | `command/shell/inspector/InspectorProvider.jsx`, `InspectorPane.jsx` (⌘.) | Posture-aware. |
| **Command Palette / Shortcuts Overlay** | A | `command/shell/CommandPalette.jsx`, `ShortcutsOverlay.jsx` | ⌘K / ? |
| **Mobile Surfaces (Drawer / Status Sheet)** | A | `command/shell/MobileSurfaces.jsx` | Posture: tablet / briefing. |

## 12. Reserved / Dead / Removed

| Item | Class | Notes |
|---|---|---|
| **Marketplace Layer (Phase 15)** | G | UI placeholder only. No engine, no endpoint. |
| **Strategy Dossier Engine (Phase 13)** | G | UI placeholder only. |
| **Automated Valuation Engine (Phase 14)** | G | UI placeholder only. |
| **cTrader Live Integration** | G | UI chip only (`ExecutionBrokerChips`). No SDK / connector. |
| **Windows Agent / VPS Allocation runtime** | F/G | `engines/scaling_*` + `host_capability.py` are dormant primitives. No agent shipped. |
| **`pages/Welcome/`** | I | Directory exists, empty. Welcome screen was scaffolded then removed in favour of CommandShell landing. |
| **`LegacyHome` route at `/legacy`** | B | Placeholder kept for U-1 parity testing. Not in nav. |
| **`old1vcpu/`** | I | Inventory snapshot for migration reference, do not run. |
| **`asf_ui_handoff/` package** | I | Reference docs only (12 screens + design system). |
| **`ThemeToggle.js`** | I | Removed per visual approval. Replaced by Command Palette toggle. |

---

## 13. Cross-cutting summary by class

| Class | Count of subsystems | Examples |
|---|---|---|
| A — Mounted & reachable | **≈70** | Strategy Panel, Auto Factory, Validation, BI5 R1 Health, DSR-1 Symbol Registry UI, Master Bot Dashboard, … |
| B — Mounted but hidden (palette only) | **3** | Challenge Matching Panel, Architect Dashboard, Legacy Home |
| C — Exists but not mounted | **0** | — (all imports trace back to a mount) |
| D — Backend only (no UI) | **6** | BI5 one-shot backfill (CLI), Random Search Optimizer (consumed by Optim), Spread Analyzer, cBot Log Diagnostic (paste-endpoint), Runner Registry CRUD, Dukascopy Downloader |
| E — Frontend only (no backend) | **2** | Broker Account Chips, Operator Inbox (frontend event bus only — backend NC dormant) |
| F — Dormant behind feature flag(s) | **30+** | Factory Supervisor (FS-P1.0..1.4), Auto-Learning, Scaling/Admission/Adaptive Pool, Aging/RoR/Calibration, DSR consumption (ENABLE_DYNAMIC_MARKET_UNIVERSE), Execution Realism Defaults, HTF Parity, Trade Parity Hard Gate, Cadence Scheduler, Adaptive Cooldown, Anti-Correlation Filter, AI Advisory, Replay Priority, Process Pool, etc. |
| G — Reservation / placeholder | **6** | Phase 13/14/15, Strategy Score, Broker Chips, Welcome page (empty) |
| H — Dead code | **0** | (none detected — repository is well-pruned) |
| I — Removed/deprecated | **3** | `ThemeToggle.js`, `pages/Welcome/` (empty), `old1vcpu/` (inventory) |

---

## 14. Recommendations

### What is actually active today (with default env)
1. The full operator UI shell (CommandShell, TopTabBar, LifecycleRail, StatusRail, NotificationDrawer, Inbox, Inspector, Palette).
2. All Research Lab + Mutation + Validation + Portfolio + Master Bot V1 + Prop Firm + Firm Match + Paper Execution + Trade Runner + Live Tracking surfaces.
3. Auto schedulers — Auto Discovery (`engines/auto_scheduler.py`), Orchestrator (`engines/orchestrator_scheduler.py`), Auto Maintenance (`data_engine/auto_data_maintainer.py`), Worker Scheduler (`factory_supervisor/worker_scheduler.py` — gated OFF).
4. BI5 ingest (manual + scheduled 60-min cadence) with BI5 R1 per-symbol health panel + endpoint.
5. DSR registry — **CRUD via UI / API live; engine consumption flag OFF** (legacy `SYMBOL_CONFIG` is still the runtime universe).
6. ≈60 latent diagnostic endpoints under `/api/latent/*`, all advisory.

### What is hidden (reachable via Command Palette only)
* `ChallengeMatchingPanel` (inside Governance Admin sub-tab)
* `ArchitectDashboard` (Power-User palette entry — Factory Supervisor advisor)
* Various Power-User sub-tabs in `OperatorParityPanels` (Soak, CPU Pool, Data Backup, Phase 12 Tuning, Flag Governance, Execution Realism)
* `/legacy` placeholder home

### What is dormant (default-OFF flags)
* DSR-3 dynamic market universe consumption (registry seeded, UI live, engines still legacy)
* All Factory Supervisor capabilities (FS-P1.0..1.4 — Recommendation, Eligibility, FAG, Copilot, Auto-Learning aggregator)
* All Scaling/Admission/Adaptive Pool/Band-Routing
* All Aging/Calibration/RoR weighting (computed but identity-applied)
* Anti-correlation filter, Adaptive cooldown, Cadence scheduler
* Multi-runner routing, token rotation, multi-account fan-out
* Trade-parity + HTF-parity hard gates
* Execution realism defaults registry consumption

### What is missing (not yet built)
1. **Strategy Dossier Engine** (Phase 13) — backend engines, persistence, render pipeline. Today: 1 reservation card.
2. **Automated Valuation Engine** (Phase 14) — dual-scorecard inputs, pricing model, marketplace pricing API.
3. **Marketplace Layer** (Phase 15) — signed-product distribution, customer surface, payment, telemetry isolation.
4. **cTrader runtime integration** (broker connector, order-routing, broker telemetry).
5. **Windows Agent / VPS allocation runtime** (primitives exist; no agent shipped).
6. **Master Bot V2** — current shipped is V1 (MB-1..3 + MB-9 P1/P2). Capacity-aware auto-orchestration loop is still flag-OFF.

### What should be prioritized next (mapped to operator's locked roadmap §3)

| Priority | Item | What remains |
|---|---|---|
| **A — DSR** | DSR-3 flip-flag readiness | Shadow audit + 7-day soak with `ENABLE_DYNAMIC_MARKET_UNIVERSE=true` against a small registry slice; verify zero drift vs legacy. |
| **B — BI5 Recovery** | BI5 R1 closure | Run `scripts/bi5_one_shot_backfill.py` (B-9) once; verify `GET /api/diag/bi5/health` populates coverage % for all 7 seeded symbols; extend bi5_ingest_log with the 4 new fields (Evidence Score · Trust Score · Dossier · Marketplace) — schema-only, no consumers yet. |
| **C — Strategy Dossier Engine** | Phase 13 | Begin with persistence schema + dossier renderer. UI reservation already in place. |
| **D — Automated Valuation Engine** | Phase 14 | Build Prop-Firm + Investor scorecards from existing Pass Probability + Risk-of-Ruin + Aging signals (already computed, just not consumed). |
| **E — Marketplace Layer** | Phase 15 | Signed-product packager + isolated public read-API + customer surface. ASF private/factory stays internal. |
| **F — Deployment readiness** | Continuous | Hydrate `/app`, run `/api/health` + `/api/latent/deployment-readiness` + `/api/latent/deployment-extras` until all-green; soak BI5 + DSR. |

---

## 15. Stability of this audit

This document is **fact-based and tied to specific files** in the canonical sources. Re-running the audit after hydration is expected to produce identical class assignments unless code is mutated.
