# FEATURE_MAP.md

**Audit type:** Phase 1 — Feature Map (route × backend × frontend × flag)
**Source:** App.zip (backend) + Frontend.zip (frontend)

This is the look-up table behind `FEATURE_EXPOSURE_AUDIT.md`. One row per operator-visible feature/module/section. Use it to answer "where is X?" in O(1).

---

## How to read this file

| Column | Meaning |
|---|---|
| **Route** | URL path inside the CommandShell (e.g. `/c/diag/bi5-health`). `—` = no UI surface. |
| **Module → Section** | `id` in `modulesRegistry.js` (e.g. `diag → bi5-health`). |
| **Frontend file** | Path under `frontend/src/`. |
| **Backend router** | Path under `backend/api/`. |
| **Engines** | Primary engine files under `backend/engines/` or `backend/data_engine/`. |
| **Endpoints** | One or more HTTP routes under `/api/`. |
| **Flag(s)** | Feature flags that gate behaviour. Empty = no flag. |
| **Status** | Class from FEATURE_EXPOSURE_AUDIT (A–I). |

---

## 1. Dashboard module (`/c/dashboard`)

| Route | Module → Section | Frontend file | Backend router | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/dashboard/briefing` | dashboard → briefing | `command/shell/dashboard/MissionBriefing.jsx` | (composite — pulls from `orchestrator`, `readiness`, `monitoring`) | n/a | `/api/orchestrator/heartbeat`, `/api/readiness/snapshot`, `/api/monitoring/status` | — | A |

## 2. Research Lab (`/c/lab`)

| Route | Section | Frontend | Backend router | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/lab/panel` | Strategy Panel | `components/StrategyPanel.js` | `api/strategies.py` | `engines/strategy_engine.py`, `strategy_library.py`, `random_search_optimizer.py` | `POST /api/strategies/generate`, `GET /api/strategies/<id>` | — | A |
| `/c/lab/analysis` | Analysis | `StrategyAnalysis.js` | `api/dashboard_route.py`, `dashboard.py` | `analysis_engine.py` | `POST /api/dashboard/generate`, `GET /api/strategies/<id>/analysis` | — | A |
| `/c/lab/backtest` | Backtest | `BacktestPanel.js` | `api/strategies.py` (backtest route) | `backtest_engine.py`, `backtest_pool.py`, `backtest_report.py` | `POST /api/strategies/<id>/backtest` | `ENABLE_PROCESS_POOL_BACKTEST` (OFF) | A |
| `/c/lab/cbot` | cBot | `CbotPanel.js` | `api/cbot.py` | `cbot_engine/*` | `/api/cbot/*` | — | A |
| `/c/lab/optim` | Optimization | `OptimizationPanel.js` | `api/optimization.py` | `optimization_engine.py`, `ga_optimizer.py`, `random_search_optimizer.py` | `/api/optimization/*` | — | A |
| `/c/lab/validate` | Validation | `ValidationPanel.js` | `api/strategies.py` | `validation_engine.py`, `walk_forward_engine.py`, `oos_holdout.py`, `monte_carlo_engine.py` | `POST /api/strategies/<id>/validate`, `/walk-forward`, `/oos`, `/monte-carlo` | `ENABLE_RISK_OF_RUIN` (OFF — diagnostic-only), `ENABLE_CALIBRATION` (OFF — identity) | A (F when scored) |

## 3. Strategy Explorer (`/c/explorer`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/explorer/explorer` | Explorer | `StrategyExplorer.js` | `api/strategies.py`, `strategy_memory.py`, `research_lineage.py` | `strategy_memory.py`, `strategy_profiler.py`, `strategy_ranking_engine.py`, `ranking_engine.py` | `/api/strategies`, `/api/strategy-memory/*`, `/api/research-lineage/*` | — | A |
| `/c/explorer/saved` | Saved Strategies | `SavedStrategies.js` | (subset of `api/strategies.py`) | `strategy_library.py` | `/api/strategies?saved=true` | — | A |
| `/c/explorer/compare` | Strategy Comparison | `StrategyComparison.js` | (frontend-side comparison; consumes strategy endpoints) | `strategy_ranking_engine.py` | — | — | A |
| `/c/explorer/score-rubric` | M3 · Strategy Score Architecture | `command/reservations/StrategyScoreReservationCard.jsx` | — | — | — | — | **G (reservation)** |
| `/c/explorer/passport-reservations` | Phase 13 · Strategy Dossier | `command/reservations/Phase13ReservationsCard.jsx` | — | — | — | — | **G (reservation)** |
| `/c/explorer/marketplace-reservations` | Phase 15 · Marketplace | `command/reservations/Phase15MarketplaceReservation.jsx` | — | — | — | — | **G (reservation)** |

## 4. Mutation Engine (`/c/mutate`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/mutate/auto` | Auto Mutation Runner | `AutoMutationRunner.js` | `api/auto_mutation.py` | `auto_mutation_runner.py`, `mutation_engine.py`, `strategy_mutation.py`, `mutation_pool.py` | `/api/auto-mutation/*` | `ENABLE_ANTI_CORRELATION_FILTER` (OFF), `ENABLE_PROCESS_POOL_MUTATION` (OFF) | A |
| `/c/mutate/cycle` | Multi-Cycle | `MultiCycleRunner.js` | `api/multi_cycle.py` | `multi_cycle_runner.py` | `/api/multi-cycle/*` | — | A |
| `/c/mutate/factory` | Auto Factory | `AutoFactory.js` | `api/auto_factory.py` | `auto_factory.py`, `auto_factory_engine.py` | `/api/auto-factory/*` | — | A |
| `/c/mutate/factory-55` | Auto Factory · Phase 55 | `AutoFactoryPhase55.js` | `api/auto_factory.py` (phase55 route) | `auto_factory_phase55.py`, `evolution_engine.py` | `/api/auto-factory/phase55/*` | — | A |
| `/c/mutate/auto-select` | Auto Selection | `AutoSelection.js` | `api/auto_selection.py` | `auto_selection_engine.py` | `/api/auto-selection/*` | — | A |
| `/c/mutate/master-bot` | Master Bot | `MasterBotDashboard.jsx` | `api/master_bot.py` | `master_bot_*.py` (8 modules: definition, engine, ranker, export, pack, deployment, diff, ranker) | `/api/master-bot/*` | — | A |
| `/c/mutate/master-bot-compile` | Master Bot Compile | `MutateMasterBotCompile.jsx`, `MasterBotCompilePanel.jsx` | `api/master_bot.py` (compile) | `master_bot_engine.py`, `compile_engine.py`, `code_generator.py` | `POST /api/master-bot/compile`, `/api/master-bot/export` | — | A |

## 5. Portfolio OS (`/c/portfolio`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/portfolio/builder` | Builder | `PortfolioBuilder.js` | `api/portfolio_builder.py` | `portfolio_builder_engine.py`, `portfolio_combiner.py` | `/api/portfolio-builder/*` | — | A |
| `/c/portfolio/panel` | Portfolio Panel | `PortfolioPanel.js` | `api/portfolio.py` | `portfolio_engine.py`, `portfolio_store.py`, `multi_asset_portfolio.py` | `/api/portfolio/*` | — | A |
| `/c/portfolio/intel` | Portfolio Intelligence | `PortfolioIntelligence.js` | `api/portfolio_intelligence.py` | `portfolio_intelligence_engine.py`, `optimization_portfolio_bridge.py` | `/api/portfolio-intelligence/*` | — | A |
| `/c/portfolio/scorecards-reservations` | Phase 14 · Dual Scorecards | `command/reservations/Phase14DualScorecardCard.jsx` | — | — | — | — | **G (reservation)** |

## 6. Prop Firm (`/c/propfirm`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/propfirm/admin` | Prop Firms | `PropFirmsAdmin.js`, `AddFirmModal.js` | `api/prop_firms.py`, `prop_firm_intelligence.py` | `prop_firm_config_engine.py`, `prop_firm_intelligence.py`, `prop_firm_panel.py` | `/api/prop-firms/*`, `/api/prop-firm-intelligence/*` | — | A |
| `/c/propfirm/match` | Firm Match | `FirmMatchPanel.js` | `api/phase4_matching.py`, `api/phase4_route.py`, `api/prop_firm_analysis.py`, `api/challenge_matching.py` | `phase4_matcher.py`, `matching_engine.py`, `match_input_validator.py`, `challenge_matching_engine.py`, `challenge_portfolio.py` | `/api/match-firms-phase4`, `/api/phase4-matching/*`, `/api/prop-firm-analysis/*`, `/api/challenge-matching/*` | — | A |

## 7. Execution Center (`/c/exec`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/exec/brokers` | Broker Accounts (chip row) | `command/reservations/ExecutionBrokerChips.jsx` | — | — | — | — | **G (reservation)** |
| `/c/exec/paper` | Paper Execution | `PaperExecution.js` | `api/execution.py` | `paper_execution_engine.py`, `execution_engine.py`, `execution_manager.py`, `execution_simulator.py`, `paper_execution_alert_bridge.py` | `/api/execution/*` | `ENABLE_EXECUTION_REALISM_DEFAULTS` (OFF — registry exists, not consumed) | A |
| `/c/exec/runner` | Trade Runner | `TradeRunner.js` | `api/trade_runner.py` | `trade_runner_engine.py` | `/api/trade-runner/*` | — | A |
| `/c/exec/live` | Live Tracking | `LiveTrackingPanel.js` | `api/live_tracking.py` | `live_tracking_engine.py` | `/api/live-tracking/*` | — | A |

## 8. AI Workforce (`/c/ai`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/ai/river` | Live River | `command/shell/ai/LlmCallRiver` | `api/llm_diagnostics.py`, `llm_health.py` | `llm_runner.py`, `llm_config.py` | `/api/llm/call-log/recent`, `/api/llm-health/*`, `/api/llm-diagnostics/*` | (provider env keys) | A |
| `/c/ai/orch` | Orchestrator | `OrchestratorPanel.js` | `api/orchestrator.py`, `orchestrator_heartbeat.py` | `ai_orchestrator.py`, `decision_engine.py`, `orchestrator_scheduler.py`, `rotational_orchestrator.py` | `/api/orchestrator/*`, `/api/orchestrator/heartbeat` | `ENABLE_AUTONOMOUS_DISCOVERY` (OFF), `ENABLE_ROTATIONAL_ORCHESTRATION` (OFF), `COMPUTE_AWARE_ORCHESTRATION` (OFF) | A (F when consumed) |
| `/c/ai/sched` | Auto-Scheduler | `AutoSchedulerControl.js` | `api/auto_mutation.py` (scheduler routes) | `auto_scheduler.py`, `cadence_scheduler.py`, `adaptive_cooldown.py`, `adaptive_concurrency.py` | `/api/auto-scheduler/*` | `ENABLE_CADENCE_SCHEDULER` (OFF), `ENABLE_ADAPTIVE_COOLDOWN` (OFF) | A |

## 9. Diagnostics (`/c/diag`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/diag/readiness` | Deployment Readiness | `DeploymentReadinessCard.jsx` | `api/readiness.py`, `api/latent/deployment_readiness.py`, `api/latent/deployment_extras.py`, `api/latent/factory_runner_heartbeat.py` | `readiness_engine.py`, `deployment_extras.py`, `factory_runner_heartbeat.py` | `/api/readiness/*`, `/api/latent/deployment-readiness`, `/api/latent/deployment-extras`, `/api/latent/factory-runner-heartbeat` | — | A |
| `/c/diag/parity` | Parity Certification | `ParityCertificationCard.jsx` | `api/cbot_parity.py`, `api/latent/parity_certification.py`, `api/latent/cbot_trade_parity.py`, `api/latent/htf_parity.py` | `cbot_parity.py`, `parity_certification.py`, `cbot_trade_parity.py`, `htf_parity.py` | `/api/cbot-parity/*`, `/api/latent/parity-certification`, `/api/latent/cbot-trade-parity`, `/api/latent/htf-parity` | `ENABLE_CBOT_TRADE_PARITY`, `ENABLE_HTF_PARITY_VALIDATION`, `ENABLE_TRADE_PARITY_HARD_GATE`, `ENABLE_HTF_PARITY_HARD_GATE` (all OFF) | A (advisory); F (consumption) |
| `/c/diag/ingestion` | Ingestion Health | `IngestionHealthCard.jsx` | `api/latent/ingestion_aggregate.py`, `api/data_health.py` | `ingestion_health_aggregate.py`, `data_engine/*` | `/api/latent/ingestion-aggregate`, `/api/data-health/*` | — | A |
| `/c/diag/ingest-src` | Strategy Ingestion | `StrategyIngestionCard.js` | `api/ingestion.py` | `strategy_ingestion/*` | `/api/ingestion/*` | — | A |
| `/c/diag/pipeline` | Pipeline Logs | `PipelineLogsPanel.js` | `api/pipeline.py`, `pipeline_logs.py` | `pipeline_logs.py` | `/api/pipeline/*`, `/api/pipeline-logs/*` | — | A |
| `/c/diag/market-data` | Market Data | `MarketDataWorkbench.jsx` (composes `DataUpload`, `DataMaintenancePanel`, `DataBackupPanel`) | `api/data.py`, `data_maintenance.py`, `incremental_run_alias.py`, `bi5_ingest.py` | `data_engine/csv_ingester.py`, `auto_data_maintainer.py`, `incremental_updater.py`, `gap_analyzer.py`, `data_backup.py`, `bi5_ingest_runner.py`, `dukascopy_downloader.py`, `tick_archive.py`, `tick_aggregator.py`, `market_calendar.py`, `tick_validator.py` | `/api/data/*`, `/api/data-maintenance/*`, `/api/data-backup/*`, `/api/admin/bi5/run`, `/api/admin/bi5/symbols`, `/api/run-incremental` | — | A |
| `/c/diag/monitoring` | Monitoring | `MonitoringSuite.jsx` (composes `Monitoring`, `SoakDiagnosticsPanel`, `CpuPoolStatePanel`, `ScalingPanel`) | `api/monitoring.py`, `soak_diagnostics.py`, `cpu_pool_state.py`, `scaling.py` | `monitoring_engine.py`, `soak_stability.py`, `cpu_pool.py`, `scaling_*`, `host_capability.py`, `adaptive_pool_sizer.py`, `admission_controller.py`, `queue_pressure.py` | `/api/monitoring/*`, `/api/soak-diagnostics/*`, `/api/cpu-pool/state`, `/api/scaling/*` | `ENABLE_SOAK_STABILITY_EMITTER`, `USE_PROCESS_POOL`, `ENABLE_PROCESS_POOL_*`, `ENABLE_ADAPTIVE_POOL_SIZING`, `ENABLE_BAND_BASED_ROUTING`, `ENABLE_ADMISSION_CONTROL`, `WORKLOAD_PROFILE` | A (read); F (consume) |
| `/c/diag/bi5-health` | **BI5 R1 · BI5 Health (per-symbol)** | **`BI5HealthPanel.jsx`** | **`api/diag_bi5_health.py`** | `engines/db.py` (aggregates `bi5_ingest_log`) | **`GET /api/diag/bi5/health`** | — | **A** |

## 10. Governance (`/c/governance`)

| Route | Section | Frontend | Backend | Engines | Endpoints | Flag(s) | Status |
|---|---|---|---|---|---|---|---|
| `/c/governance/gov` | Governance | `GovernanceCard.jsx` | `api/governance.py`, `api/latent/safe_to_widen.py`, `latent/widening_history.py`, `latent/advanced_scaffolding.py` | `governance_universe.py`, `survivor_registry.py`, `replacement_engine.py`, `safe_to_widen.py`, `widening_history.py`, `widening_proposal.py`, `lifecycle_decay.py` | `/api/governance/*`, `/api/latent/safe-to-widen`, `/api/latent/widening-history`, `/api/admin/widening-proposals` | `ENABLE_AGING_PENALTY` (OFF — computed not applied), `ENABLE_AGING_AUTO_DEMOTION` (OFF) | A |
| `/c/governance/universe` | Universe Governance | `UniverseGovernancePanel.jsx` | `api/governance.py` | `governance_universe.py` | `/api/governance/universe/*` | — | A |
| `/c/governance/symbol-registry` | **DSR · Symbol Registry** | **`SymbolRegistryPanel.jsx`** | **`api/admin_market_universe.py`, `api/latent/market_universe.py`** | **`market_universe.py`, `market_universe_adapter.py`, `market_universe_audit.py`** | **`GET /api/latent/market-universe`, `POST /api/admin/market-universe`, `POST …/{sym}/tier`, `POST …/{sym}/enable`, `DELETE …`** | **`ENABLE_DYNAMIC_MARKET_UNIVERSE` (OFF — consumption), `MARKET_UNIVERSE_DEFAULT_TIER=candidate`, `MARKET_UNIVERSE_AUTO_INGEST` (OFF), `MARKET_UNIVERSE_AUDIT_TTL_DAYS=90`** | **A (CRUD); F (consumption — DSR-3 still flag-gated)** |
| `/c/governance/rules` | Rules Review | `RulesReviewPanel.js` | `api/prop_firm_rules_review.py` | `rule_engine.py`, `rule_enforcement.py`, `prop_firm_rule_engine.py` | `/api/prop-firm-rules-review/*` | — | A |
| `/c/governance/env` | Env Priority | `EnvPriorityPanel.js` | `api/governance.py` (sub-route) | `env_priority.py` | `/api/env-priority/*` | `ENABLE_ADAPTIVE_ROTATION` (OFF) | A |
| `/c/governance/readiness` | Readiness | `ReadinessPanel.js` | `api/readiness.py` | `readiness_engine.py` | `/api/readiness/*` | — | A |
| `/c/governance/admin` | Admin (composite) | `GovernanceAdminSuite.jsx` → `AdminUsers`, `AdminFlagGovernancePanel`, `AdminExecutionRealismPanel`, `Phase12TuningPanel`, `ChallengeMatchingPanel` (Power-User sub-tabs) | `api/admin.py`, `auth.py`, `admin_flag_governance.py`, `admin_execution_realism.py`, `phase12_tuning.py`, `challenge_matching.py` | `auth_utils.py`, `activation_governance.py`, `activation_journal.py`, `execution_realism_defaults.py`, `phase12_tuning.py`, `flag_overrides.py`, `feature_flags.py` | `/api/admin/*`, `/api/admin/flag-governance/*`, `/api/admin/execution-realism/*`, `/api/phase12-tuning/*`, `/api/challenge-matching/*`, `/api/latent/feature-flags`, `/api/latent/activation-governance`, `/api/latent/activation-timeline` | (registry self-aware) | A |

## 11. Global overlays (always-mounted)

| Item | Frontend | Backend | Endpoints | Flag(s) | Hotkey | Status |
|---|---|---|---|---|---|---|
| **CommandBar** | `command/shell/CommandBar.jsx` | — | — | — | (always visible) | A |
| **TopTabBar** (M0) | `command/shell/TopTabBar.jsx` | — | — | — | (always visible) | A |
| **LeftRail** | `command/shell/LeftRail.jsx` | — | — | — | ⌘B toggle | A |
| **LifecycleRail** (M1) | `command/shell/LifecycleRail.jsx` | — | — | — | — | A |
| **StatusRail** | `command/shell/StatusRail.jsx` | (polls `/api/monitoring/status`, `/api/orchestrator/heartbeat`) | — | — | — | A |
| **DangerRibbon** | `command/shell/DangerRibbon.jsx` | — | — | — | — | A |
| **OperatorInboxDrawer** (M4) | `command/shell/OperatorInboxDrawer.jsx`, `inboxEvents.js`, `stores/notificationsStore.js` | — (frontend bus); NC backend = dormant | (when NC enabled: `/api/notifications/*`) | `ENABLE_NOTIFICATION_CENTER` (OFF) | — | A (frontend), F (backend) |
| **CommandPalette** (⌘K) | `command/shell/CommandPalette.jsx` | — | — | — | ⌘K | A |
| **NotificationDrawer (live)** | `command/shell/NotificationDrawer.jsx` | `api/monitoring.py`, admin widening-proposals | `/api/monitoring/status`, `/api/admin/widening-proposals`, `/api/orchestrator/heartbeat` | — | ⌘⌥N | A |
| **CopilotPanel** | `command/shell/CopilotPanel.jsx` | — (advisory; reads orchestrator + LLM call log) | `/api/orchestrator/heartbeat`, `/api/llm/call-log/recent` | `FS_ENABLE_COPILOT` (OFF), `FS_ENABLE_COPILOT_ADVANCED` (OFF) | ⌘J | A (UI) / F (backend) |
| **ShortcutsOverlay** | `command/shell/ShortcutsOverlay.jsx` | — | — | — | ? | A |
| **Inspector Pane** | `command/shell/inspector/InspectorPane.jsx`, `InspectorProvider.jsx` | — | — | — | ⌘. | A |
| **EmergencyBanner** | `command/shell/EmergencyBanner.jsx` | — | — | — | — (auto on <480px) | A |
| **AriaLiveRegion** | `components/a11y/AriaLiveRegion` | — | — | — | (assistive tech) | A |
| **MobileSurfaces (ModuleDrawer, StatusSheet)** | `command/shell/MobileSurfaces.jsx` | — | — | — | (tablet/briefing posture) | A |

## 12. Latent endpoints (read-only diagnostic)

| Endpoint | Backend file | Engine | Flag (consumption gate) | Status |
|---|---|---|---|---|
| `/api/latent/feature-flags` | `api/latent/feature_flags.py` | `engines/feature_flags.py` | — (self) | A |
| `/api/latent/risk-of-ruin` | `api/latent/risk_of_ruin.py` | `engines/risk_of_ruin.py` | `ENABLE_RISK_OF_RUIN` (OFF) | F |
| `/api/latent/lifecycle-decay` | `api/latent/lifecycle_decay.py` | `engines/lifecycle_decay.py` | `ENABLE_AGING_PENALTY` (OFF) | F |
| `/api/latent/calibration` | `api/latent/calibration.py` | `engines/calibration_framework.py` | `ENABLE_CALIBRATION` (OFF) | F |
| `/api/latent/activation-timeline` | `api/latent/activation_timeline.py` | `engines/audit_log_writer.py` | — | A |
| `/api/latent/activation-governance` | `api/latent/activation_governance.py` | `engines/activation_governance.py` | — | A |
| `/api/latent/compute-probe` | `api/latent/compute_probe.py` | `engines/compute_probe.py` | — | A |
| `/api/latent/safe-to-widen` | `api/latent/safe_to_widen.py` | `engines/safe_to_widen.py` | — | A |
| `/api/latent/widening-history` | `api/latent/widening_history.py` | `engines/widening_history.py` | — | A |
| `/api/latent/observability` | `api/latent/observability.py` | (composite) | — | A |
| `/api/latent/advanced-scaffolding` | `api/latent/advanced_scaffolding.py` | (composite) | — | A |
| `/api/latent/cbot-trade-parity` | `api/latent/cbot_trade_parity.py` | `engines/cbot_trade_parity.py` | `ENABLE_CBOT_TRADE_PARITY` (OFF) | F |
| `/api/latent/execution-realism-defaults` | `api/latent/execution_realism_defaults.py` | `engines/execution_realism_defaults.py` | `ENABLE_EXECUTION_REALISM_DEFAULTS` (OFF) | F |
| `/api/latent/market-universe` | `api/latent/market_universe.py` | `engines/market_universe.py` | `ENABLE_DYNAMIC_MARKET_UNIVERSE` (OFF for consumption — CRUD always live) | A (CRUD) / F (consumption) |
| `/api/latent/cbot-log-diagnostic` | `api/latent/cbot_log_diagnostic.py` | `engines/cbot_log_diagnostic.py` | — | A |
| `/api/latent/deployment-readiness` | `api/latent/deployment_readiness.py` | (composite probe) | — | A |
| `/api/latent/factory-runner-heartbeat` | `api/latent/factory_runner_heartbeat.py` | `engines/factory_runner_heartbeat.py` | — | A |
| `/api/latent/htf-parity` | `api/latent/htf_parity.py` | `engines/htf_parity.py` | `ENABLE_HTF_PARITY_VALIDATION` (OFF) | F |
| `/api/latent/parity-certification` | `api/latent/parity_certification.py` | `engines/parity_certification.py` | `ENABLE_TRADE_PARITY_HARD_GATE`, `ENABLE_HTF_PARITY_HARD_GATE` (both OFF) | F |
| `/api/latent/ingestion-aggregate` | `api/latent/ingestion_aggregate.py` | `engines/ingestion_health_aggregate.py` | — | A |
| `/api/latent/deployment-extras` | `api/latent/deployment_extras.py` | `engines/deployment_extras.py` | — | A |

## 13. Factory Supervisor & Master Bot V1 (Phase 2.B+)

| Endpoint | Backend | Engines | Flag(s) | Status |
|---|---|---|---|---|
| `/api/factory-supervisor/*` (heartbeat, events, notifications, defer queue, dispatcher, lock, scheduler) | `api/factory_supervisor.py` | `engines/factory_supervisor/` (≈20 files) | `ENABLE_FACTORY_SUPERVISOR` (OFF), `FS_ENABLE_*` (all OFF) | F |
| `/api/scaling/*` (heartbeat, nodes) | `api/scaling.py` | `engines/scaling_*.py`, `scaling_registry.py`, `scaling_events.py`, `scaling_router.py` | `ENABLE_BAND_BASED_ROUTING` (OFF), `ENABLE_ADAPTIVE_POOL_SIZING` (OFF) | F |
| `/api/master-bot/runners/*` (register, rotate-token, accounts) | `api/runner.py` | `runner_registry.py`, `runner_router.py`, `runner_token_rotator.py`, `multi_account_envelope.py`, `parity_drift_view.py` | `RUNNER_AFFINITY_POLICY=sticky_pair_tf`, `RUNNER_AUTO_ROTATE` (OFF), `RUNNER_MULTI_ACCOUNT_ENABLED` (OFF), `RUNNER_AUTO_ROUTE_AT_REGISTER` (OFF) | A (single-runner); F (multi) |

## 14. Startup hooks (server.py)

Order matters — these run sequentially:

| # | Hook | Side-effect | Gate |
|---|---|---|---|
| 1 | `validate_startup_env()` | exits cleanly on missing JWT_SECRET etc | — |
| 2 | `_seed_admin_user()` | seeds admin row via `auth_utils.seed_admin` | — |
| 3 | `_log_feature_flag_manifest()` | one info log + `audit_log` boot_state row + override diff row | — |
| 4 | `_ensure_mongo_indexes()` | hardens core indexes | — |
| 5 | `_seed_market_universe()` | inserts 7 canonical symbols into `market_universe_symbols` (idempotent) | always runs |
| 6 | `_refresh_market_universe_cache()` | populates in-process adapter cache | gated by `ENABLE_DYNAMIC_MARKET_UNIVERSE` (else no-op) |
| 7 | `_restore_auto_maintenance()` | restarts BID+BI5 ingest scheduler (15+60 min) | deferred to factory_runner if `FACTORY_RUNNER_OWNS_SCHEDULERS=true` |
| 8 | `_restore_auto_discovery_scheduler()` | `engines/auto_scheduler.py` | same |
| 9 | `_restore_orchestrator_scheduler()` | `engines/orchestrator_scheduler.py` | same |
| 10 | `_ensure_mb9_indexes()` + `_ensure_mb9_phase2_indexes()` | deployment + runner + accounts + tokens indexes | always |
| 11 | `_ensure_scaling_indexes()` | scaling_nodes indexes | always |
| 12 | `_detect_host_capability()` | persists host capability row | always |
| 13 | `_ensure_admission_indexes()` | admission_journal indexes | always |
| 14 | `_ensure_scaling_events_indexes()` | scaling_events indexes | always |
| 15 | `_ensure_factory_supervisor_indexes()` | FS lock + hb + events + subs + defer + fag | always |
| 16 | `_start_factory_supervisor_scheduler()` | start FS worker loop | gated by `FS_ENABLE_WORKER_SCHEDULER` (OFF) |

## 15. Schedulers (live)

| Scheduler | File | Active when | Cadence |
|---|---|---|---|
| Auto Data Maintenance (BID) | `data_engine/auto_data_maintainer.py` | flag-derived from `auto_maintenance_config` row | 15 min |
| Auto Data Maintenance (BI5) | same | same | 60 min — dispatches `run_bi5_ingest(lookback_days=30)` |
| Auto Discovery (mutation runner) | `engines/auto_scheduler.py` | restored from persisted config | configurable |
| Orchestrator | `engines/orchestrator_scheduler.py` | restored from persisted config | configurable |
| Factory Supervisor Worker | `engines/factory_supervisor/worker_scheduler.py` | `FS_ENABLE_WORKER_SCHEDULER=true` (OFF default) | `FS_WORKER_POLL_INTERVAL_SEC=15` |
| Auto-Rotation (token) | `engines/runner_token_rotator.py` | `RUNNER_AUTO_ROTATE=true` (OFF default) | `RUNNER_ROTATE_INTERVAL_SEC=2592000` |

If `FACTORY_RUNNER_OWNS_SCHEDULERS=true`, schedulers 1–4 are deferred to the sibling `factory_runner.py` process.

---

## 16. Notable cross-references

* **CommandShell entry**: `frontend/src/App.js` → `GatedCommandModuleApp` → `command/shell/CommandModuleApp.jsx` → `CommandShell.jsx` → `modulesRegistry.js` (355 LOC, 10 modules).
* **`StrategyDashboard.js`** is imported by `modulesRegistry.js` but only as a fallback inside Mission Briefing deep-link buttons (no longer the default mount).
* The 56 routers in `server.py` are registered in two batches (latent first, primary second) so that more-specific paths win.
