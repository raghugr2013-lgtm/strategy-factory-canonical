# CAPABILITY_CATALOG.md

**Audit type:** Full capability discovery — every feature that exists anywhere in the codebase, mounted or not.
**Status:** Read-only. No code modified. No surfaces mounted. No flags flipped.
**Generated:** 2026-06-12 (post-parity-trilogy)

**Source counts:**
- Backend routers (`/app/backend/api/`): **63** Python files
- Backend latent routers (`/app/backend/api/latent/`): **22** Python files
- Engines (`/app/backend/engines/*.py` flat): **168** Python files
- Factory-supervisor engines (`/app/backend/engines/factory_supervisor/`): **22** Python files
- Data engines (`/app/backend/data_engine/`): **12** Python files
- Cbot engines (`/app/backend/cbot_engine/`): **5** Python files
- Strategy-ingestion engines (`/app/backend/engines/strategy_ingestion/`): **7** Python files
- Persistence adapters (`/app/backend/engines/persistence_adapters/`): **3** Python files
- Seed engines (`/app/backend/engines/seed/`): **1** Python file
- Scripts (`/app/backend/scripts/`): **8** Python files
- Tests (`/app/backend/tests/test_*.py`): **211** Python files
- `server.py` `include_router(...)` calls: **85**
- `server.py` `@app.on_event("startup")` handlers: **17**
- Frontend components (`/app/frontend/src/components/**`): **125** files (top-level: 63)
- Frontend shell files (`/app/frontend/src/command/**`): **41** files
- `modulesRegistry.js` sections declared: **57** (49 with `Component:` slot)
- `TopTabBar.jsx` declared chips: **17** (11 CORE + 6 MORE)
- Feature flag entries (`engines/feature_flags.py::_FLAG_SPECS`): **89**
- `.env` flag overrides currently set: **1** (`ENABLE_DYNAMIC_MARKET_UNIVERSE=1`)

**Status taxonomy:**

| Status | Meaning |
|---|---|
| **Active** | Backend + Frontend + Mounted + Reachable + Default-ON (or flag-enabled) |
| **Hidden** | Backend + Frontend exist; frontend lazy-imported but no section mounts it (or mounted only via Power-User/raw API) |
| **Dormant** | Backend exists; gated by feature-flag default OFF; flag introspectable; activates on operator decree |
| **Placeholder** | Reservation card / rail label visible; no backend behaviour yet |
| **Orphan** | File exists in repo; zero importers; replacement mounted elsewhere |
| **Dead** | File exists in repo; zero importers; no replacement; superseded function |

---

## 1. Pipeline / strategy lifecycle capabilities

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | Auto Factory (Generate) | LLM-driven seed-strategy generator | Y (`engines/auto_factory_engine.py`, `engines/auto_factory.py`; `api/auto_factory.py`) | Y (`AutoFactory.js`, `AutoFactoryPhase55.js`) | Y (`mutate/factory`, `mutate/factory-55`) | Y | — | **Active** (correctly gated by readiness when LLM/BI5 missing) |
| 2 | Auto Mutation Runner | Single-cycle mutation runner | Y (`engines/auto_mutation_runner.py`, `engines/mutation_engine.py`; `api/auto_mutation.py`) | Y (`AutoMutationRunner.js`) | Y (`mutate/auto`) | Y | — | **Active** |
| 3 | Multi-Cycle Runner | Multi-generation mutation sweep | Y (`engines/multi_cycle_runner.py`; `api/multi_cycle.py`) | Y (`MultiCycleRunner.js`) | Y (`mutate/cycle`) | Y | — | **Active** |
| 4 | Validation (WF / OOS / MC) | Walk-Forward, OOS, Monte-Carlo validation | Y (`engines/validation_engine.py`, `engines/walk_forward_engine.py`, `engines/oos_holdout.py`, `engines/monte_carlo_engine.py`) | Y (`ValidationPanel.js`) | Y (`lab/validate`) | Y | — | **Active** |
| 5 | Auto Selection | Multi-criteria strategy selection | Y (`engines/auto_selection_engine.py`; `api/auto_selection.py`) | Y (`AutoSelection.js`) | Y (`mutate/auto-select`) | Y | — | **Active** |
| 6 | Strategy Library | Canonical strategy storage + fingerprint | Y (`engines/strategy_library.py`) | — | — | Y (consumed by Explorer) | — | **Active** |
| 7 | Strategy Lifecycle | Stage transitions + history | Y (`engines/strategy_lifecycle.py`; `api/lifecycle.py`) | — (read indirectly) | — | Y | — | **Active** (backend) |
| 8 | Strategy Mutation | Pure mutation primitive | Y (`engines/strategy_mutation.py`) | — | — | Y (engine) | — | **Active** |
| 9 | Strategy Profiler | Current-market-data signature | Y (`engines/strategy_profiler.py`) | — | — | Y (engine) | — | **Active** |
| 10 | Strategy Ranking | Cell-level + global ranking | Y (`engines/strategy_ranking_engine.py`, `engines/ranking_engine.py`) | — | — | Y (engine) | — | **Active** |
| 11 | Strategy Refinement | Iterative refinement engine | Y (`engines/strategy_refinement_engine.py`, `engines/refinement_engine.py`) | — | — | Y (engine) | — | **Active** |
| 12 | Strategy Memory | Pattern memory + recall | Y (`engines/strategy_memory.py`; `api/strategy_memory.py`) | — (via Explorer) | — | Y | — | **Active** |
| 13 | Survivor Registry | Canonical survivor tracking | Y (`engines/survivor_registry.py`) | — | — | Y | — | **Active** |
| 14 | Replacement Engine | Stale-survivor replacement | Y (`engines/replacement_engine.py`) | — | — | Y | — | **Active** |
| 15 | Decision Engine | Decision arbitration | Y (`engines/decision_engine.py`) | — | — | Y | — | **Active** |
| 16 | Evolution Engine | Strategy evolution primitive | Y (`engines/evolution_engine.py`) | — | — | Y | — | **Active** |
| 17 | IR (Intermediate Representation) | Strategy IR | Y (`engines/strategy_ir.py`, `strategy_ir_builders.py`, `strategy_ir_backfill.py`, `strategy_ir_renderer.py`, `ir_interpreter.py`, `ir_telemetry.py`) | — | — | Y | — | **Active** |
| 18 | Backtest Engine | Canonical backtester | Y (`engines/backtest_engine.py`, `backtest_pool.py`, `backtest_report.py`) | Y (`BacktestPanel.js`) | Y (`lab/backtest`) | Y | `ENABLE_PROCESS_POOL_BACKTEST` (default OFF — single thread) | **Active** (pool dormant) |
| 19 | Optimization Engine | Parameter search | Y (`engines/optimization_engine.py`, `random_search_optimizer.py`, `ga_optimizer.py`) | Y (`OptimizationPanel.js`) | Y (`lab/optim`) | Y | — | **Active** |
| 20 | Code Generator | cBot / IR code gen | Y (`engines/code_generator.py`, `compile_engine.py`) | — | — | Y | — | **Active** |
| 21 | Analysis Engine | Strategy analysis surface | Y (`engines/analysis_engine.py`) | Y (`StrategyAnalysis.js`) | Y (`lab/analysis`) | Y | — | **Active** |

---

## 2. Market data & DSR capabilities

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 22 | DSR (Dynamic Symbol Registry) | Operator-managed symbol catalogue | Y (`engines/market_universe.py`, `market_universe_adapter.py`, `market_universe_audit.py`, `seed/market_universe_seed.py`; `api/admin_market_universe.py`, `api/latent/market_universe.py`) | Y (`SymbolRegistryPanel.jsx`, `UniverseGovernancePanel.jsx`) | Y (`governance/symbol-registry`, `governance/universe`) | Y | `ENABLE_DYNAMIC_MARKET_UNIVERSE=1` (ON) · `MARKET_UNIVERSE_DEFAULT_TIER` · `MARKET_UNIVERSE_AUTO_INGEST` · `MARKET_UNIVERSE_AUDIT_TTL_DAYS` | **Active** |
| 23 | BID Ingestion | Bid-data ingestion + scheduler | Y (`data_engine/auto_data_maintainer.py` + scheduler) | Y (Manual sub-tab in MarketDataWorkbench) | Y (`diag/market-data`) | Y | `BID_INTERVAL_MINUTES` (default 5) | **Active** |
| 24 | BI5 Ingestion (R1) | 30-day Dukascopy fetch every 60 min | Y (`engines/auto_data_maintainer._update_bi5_symbol`; `data_engine/bi5_ingest_runner.py`; `api/bi5_ingest.py`) | Y (BI5 source picker in MarketDataWorkbench Manual) | Y (`diag/market-data` + B-2 source param) | Y | `BI5_INTERVAL_MINUTES` (default 60) | **Active** |
| 25 | BI5 Health Panel | Per-symbol coverage / sync / status | Y (`api/diag_bi5_health.py`) | Y (`BI5HealthPanel.jsx`) | Y (`diag/bi5-health`) | Y | — | **Active** |
| 26 | BI5 Maturity | Maturity scorer | Y (`engines/bi5_maturity.py`) | — | — | Y (engine) | — | **Active** |
| 27 | BI5 Realism | Realism certification engine | Y (`engines/bi5_realism.py`; `api/bi5_realism.py`) | — (consumed by certification) | — | Y | — | **Active** |
| 28 | BI5 Certification | Strategy + Data certification flow | Y (`engines/bi5_certification.py`; `api/bi5_certification.py`) | — (panel pending) | — | Y (API only) | — | **Hidden** (API live; no UI panel exposes `/api/bi5-cert/*` endpoints yet) |
| 29 | BI5 R2 — Auto-cert sweep | B-4 + B-5 + B-8 — Sunday 03:00 UTC sweep + ranker weights + lifecycle surfacing | — (queued) | — | — | N | — | **Not yet built** (P0 roadmap per PRD §6) |
| 30 | BI5 R3 — Tick replay | B-3 + B-6 + B-7 — `simulate_fills` + Trade Runner consolidation | — (queued) | — | — | N | — | **Not yet built** (P0 roadmap) |
| 31 | One-shot BI5 backfill | `scripts/bi5_one_shot_backfill.py` | Y (CLI) | — | — | Y (`python -m scripts.bi5_one_shot_backfill`) | — | **Active** (CLI) |
| 32 | Tick Aggregator | OHLCV + higher-TF rebuild | Y (`data_engine/tick_aggregator.py`, `tick_archive.py`, `tick_validator.py`) | — | — | Y | — | **Active** |
| 33 | Dukascopy Downloader | Raw BI5 fetcher | Y (`data_engine/dukascopy_downloader.py`) | — | — | Y | — | **Active** |
| 34 | Gap Analyzer | Bar-gap detection | Y (`data_engine/gap_analyzer.py`) | — (consumed) | — | Y | — | **Active** |
| 35 | Incremental Updater | Last-stored cursor logic | Y (`data_engine/incremental_updater.py`) | — | — | Y | — | **Active** |
| 36 | Data Backup | Manual + scheduled backup | Y (`data_engine/data_backup.py`) | Y (DataBackupPanel via Archive sub-tab) | Y (`diag/market-data` Archive) | Y | — | **Active** |
| 37 | Data Maintenance | Automated maintenance loop | Y (`data_engine/data_maintenance.py`) | Y (DataMaintenancePanel via Automated sub-tab) | Y (`diag/market-data` Automated) | Y | — | **Active** |
| 38 | Market Calendar | Trading-hours calendar | Y (`data_engine/market_calendar.py`) | — | — | Y | — | **Active** |
| 39 | Spread Analyzer | Spread + microstructure | Y (`engines/spread_analyzer.py`; `persistence_adapters/market_spread_store.py`) | — | — | Y | — | **Active** |
| 40 | Regime Classifier | Market-regime detection | Y (`engines/regime_classifier.py`, `regime_performance.py`; `api/regime.py`) | — (consumed by validation) | — | Y | — | **Active** |
| 41 | Signal Quality | Signal-quality engine | Y (`engines/signal_quality.py`) | — | — | Y | — | **Active** |

---

## 3. Portfolio + execution capabilities

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 42 | Portfolio Builder | Build portfolios from survivors | Y (`engines/portfolio_builder_engine.py`, `portfolio_combiner.py`; `api/portfolio_builder.py`) | Y (`PortfolioBuilder.js`) | Y (`portfolio/builder`) | Y | — | **Active** |
| 43 | Portfolio Panel | Live-portfolio operator view | Y (`engines/portfolio_engine.py`, `portfolio_store.py`; `api/portfolio.py`) | Y (`PortfolioPanel.js`) | Y (`portfolio/panel`) | Y | — | **Active** |
| 44 | Portfolio Intelligence | Anti-corr + intelligence layer | Y (`engines/portfolio_intelligence_engine.py`; `api/portfolio_intelligence.py`) | Y (`PortfolioIntelligence.js`) | Y (`portfolio/intel`) | Y | `ENABLE_ANTI_CORRELATION_FILTER` (default OFF) · `ANTI_CORRELATION_THRESHOLD` | **Active** (filter dormant) |
| 45 | Multi-Asset Portfolio | Cross-asset portfolio builder | Y (`engines/multi_asset_portfolio.py`) | — | — | Y (engine) | — | **Active** |
| 46 | Optimization × Portfolio Bridge | Cross-stage bridge | Y (`engines/optimization_portfolio_bridge.py`) | — | — | Y | — | **Active** |
| 47 | Phase 14 Dual Scorecard | Prop + Investor reservation card | — (Phase 14 engine pending) | Y (`Phase14DualScorecardCard.jsx`) | Y (`portfolio/scorecards-reservations`) | Y | — | **Placeholder** |
| 48 | Paper Execution | Paper trading engine | Y (`engines/paper_execution_engine.py`, `paper_execution_alert_bridge.py`; `api/execution.py`) | Y (`PaperExecution.js`) | Y (`exec/paper`) | Y | `source ∈ {bid_1m, bi5}` runtime param | **Active** |
| 49 | Trade Runner | Live-trade dispatcher | Y (`engines/trade_runner_engine.py`; `api/trade_runner.py`) | Y (`TradeRunner.js`) | Y (`exec/runner`) | Y | — | **Active** |
| 50 | Live Tracking | Live-position tracker | Y (`engines/live_tracking_engine.py`; `api/live_tracking.py`) | Y (`LiveTrackingPanel.js`) | Y (`exec/live`) | Y | — | **Active** |
| 51 | Execution Broker Chips | Track A/B + cTrader/VPS reservation | — (display only) | Y (`ExecutionBrokerChips.jsx`) | Y (`exec/brokers`) | Y | — | **Placeholder** (cTrader Demo · cTrader Live · Windows VPS · Broker Telemetry slots reserved) |
| 52 | Execution Engine | Order-execution primitive | Y (`engines/execution_engine.py`, `execution_manager.py`, `execution_simulator.py`) | — | — | Y | — | **Active** |
| 53 | Execution Realism Defaults | Slippage / spread defaults | Y (`engines/execution_realism_defaults.py`; `api/admin_execution_realism.py`, `api/latent/execution_realism_defaults.py`) | Y (`AdminExecutionRealismPanel` in `GovernanceAdminSuite`) | Y (`governance/admin` → Realism sub-tab) | Y | `ENABLE_EXECUTION_REALISM_DEFAULTS` | **Active** |
| 54 | Slippage Model | Slippage engine | Y (`engines/slippage_model.py`) | — | — | Y | — | **Active** |
| 55 | Multi-Account Envelope | Multi-account routing | Y (`engines/multi_account_envelope.py`) | — | — | Y | `RUNNER_MULTI_ACCOUNT_ENABLED` | **Dormant** |
| 56 | Runner Registry | Live-runner roster | Y (`engines/runner_registry.py`, `runner_router.py`, `runner_token_rotator.py`, `runner_account_migration.py`; `api/runner.py`) | — | — | Y (API) | `RUNNER_AFFINITY_POLICY` · `RUNNER_AUTO_ROUTE_AT_REGISTER` · `RUNNER_AUTO_ROTATE` · `RUNNER_ROTATE_INTERVAL_SEC` · `RUNNER_TOKEN_GRACE_SEC` · `RUNNER_PARITY_DRIFT_WINDOW_DAYS` | **Hidden** (API exposed, no operator panel) |
| 57 | Factory Runner Heartbeat | Heartbeat surface | Y (`engines/factory_runner_heartbeat.py`; `api/latent/factory_runner_heartbeat.py`) | — | — | Y (API) | — | **Hidden** |
| 58 | Cbot Pipeline | cBot compile pipeline | Y (`engines/cbot_pipeline.py`, `cbot_autofix.py`, `cbot_log_diagnostic.py`, `cbot_parity.py`, `cbot_trade_parity.py`; `api/cbot.py`, `api/cbot_parity.py`; `cbot_engine/*`) | Y (`CbotPanel.js`) | Y (`lab/cbot`) | Y | `ENABLE_CBOT_TRADE_PARITY` · `CBOT_TRADE_PARITY_FIRST_N` · `ENABLE_TRADE_PARITY_HARD_GATE` (OFF) | **Active** |
| 59 | R5 Shadow Comparator | Cbot vs strategy shadow comparison | Y (`engines/r5_shadow_comparator.py`) | — | — | Y | — | **Active** |
| 60 | HTF Parity | Higher-TF parity validation | Y (`engines/htf_parity.py`; `api/latent/htf_parity.py`) | — | — | Y (API) | `ENABLE_HTF_PARITY_VALIDATION` · `HTF_PARITY_MAX_DIVERGENCE_PCT` · `ENABLE_HTF_PARITY_HARD_GATE` (OFF) | **Active** (hard gate dormant) |
| 61 | Parity Certification | Cross-source certification | Y (`engines/parity_certification.py`, `parity_drift_view.py`; `api/latent/parity_certification.py`) | Y (`ParityCertificationCard.jsx`) | Y (`diag/parity`) | Y | `PARITY_CERTIFICATION_MIN_SAMPLES` · `PARITY_CERTIFICATION_MIN_PASS_RATE` | **Active** |

---

## 4. Prop firm capabilities

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 62 | Prop Firms Admin | Firm catalogue CRUD | Y (`api/prop_firms.py`) | Y (`PropFirmsAdmin.js`, `AddFirmModal.js`) | Y (`propfirm/admin`) | Y | — | **Active** |
| 63 | Firm Match (Phase 4) | Strategy ↔ firm matcher | Y (`engines/phase4_matcher.py`, `matching_engine.py`, `match_input_validator.py`; `api/phase4_matching.py`, `api/phase4_route.py`) | Y (`FirmMatchPanel.js`) | Y (`propfirm/match`) | Y | — | **Active** |
| 64 | Prop Firm Intelligence | Firm risk analytics | Y (`engines/prop_firm_intelligence.py`; `api/prop_firm_intelligence.py`) | — (consumed by FirmMatchPanel) | — | Y (API) | — | **Active** |
| 65 | Prop Firm Analysis | Firm vs strategy analysis | Y (`engines/prop_firm_panel.py`; `api/prop_firm_analysis.py`) | — | — | Y (API) | — | **Active** |
| 66 | Prop Firm Rules Engine | Rule enforcement primitive | Y (`engines/prop_firm_rule_engine.py`, `rule_engine.py`, `rule_enforcement.py`, `safety_engine.py`, `safety_injector.py`) | Y (`RulesReviewPanel.js`) | Y (`governance/rules`) | Y | — | **Active** |
| 67 | Prop Firm Rules Review | Rules-review API | Y (`api/prop_firm_rules_review.py`) | Y (consumed by RulesReviewPanel) | Y | Y | — | **Active** |
| 68 | Prop Firm Config Engine | Firm config + PDFs | Y (`engines/prop_firm_config_engine.py`; `prop_firm_configs_example.json`; `prop_firm_pdfs/`) | — | — | Y | — | **Active** |
| 69 | Challenge Manager | Challenge-template registry | Y (`engines/challenge_manager.py`) | — | — | Y | — | **Active** |
| 70 | Challenge Matching | Strategy ↔ challenge-template scoring | Y (`engines/challenge_matching_engine.py`; `api/challenge.py`, `api/challenge_matching.py`) | Y (`ChallengeMatchingPanel` in `OperatorParityPanels.jsx`) | **N** (lazy-imported `modulesRegistry.js` L131; no section references) | Y (API only) | — | **Hidden** |
| 71 | Challenge Simulator | Challenge run simulator | Y (`engines/challenge_simulator.py`) | — | — | Y | — | **Active** |
| 72 | Challenge Portfolio | Per-challenge portfolio shim | Y (`engines/challenge_portfolio.py`) | — | — | Y | — | **Active** |

---

## 5. Master Bot capabilities

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 73 | Master Bot Engine | Composer/runtime/compiler | Y (`engines/master_bot_engine.py`, `master_bot_composer.py`, `master_bot_definition.py`, `master_bot_compiler.py`, `master_bot_runtime.py`, `master_bot_signer.py`, `master_bot_export.py`, `master_bot_pack.py`, `master_bot_deployment.py`, `master_bot_diff.py`; `api/master_bot.py`) | Y (`MasterBotDashboard.jsx`, `MasterBotCompilePanel.jsx`, `MutateMasterBotCompile.jsx`) | Y (`mutate/master-bot`, `mutate/master-bot-compile`) | Y | — | **Active** |
| 74 | Master Bot Ranker | Composite deploy_score formula | Y (`engines/master_bot_ranker.py`) | — | — | Y | — | **Active** |

---

## 6. Monitoring + scaling + diagnostics capabilities

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 75 | Monitoring Suite (Runtime · Soak · Compute · Cluster) | 4-pane diag composite | Y (`engines/monitoring_engine.py`, `monitoring_alert_bridge.py`; `api/monitoring.py`) | Y (`MonitoringSuite.jsx`, `Monitoring.js`) | Y (`diag/monitoring`) | Y | — | **Active** |
| 76 | Soak Diagnostics | Long-soak metric collector | Y (`engines/soak_stability.py`, `ecosystem_observability.py`; `api/soak_diagnostics.py`, `api/latent/advanced_scaffolding.py`) | Y (`SoakDiagnosticsPanel` via Monitoring) | Y (via Soak sub-tab) | Y | `ENABLE_SOAK_STABILITY_EMITTER` | **Active** |
| 77 | CPU Pool State | Pool-utilisation surface | Y (`engines/cpu_pool.py`, `host_capability.py`; `api/cpu_pool_state.py`) | Y (`CpuPoolStatePanel` via Monitoring Compute) | Y (Compute sub-tab) | Y | — | **Active** |
| 78 | Scaling Engine | Adaptive scaling policy | Y (`engines/scaling_router.py`, `scaling_events.py`, `scaling_registry.py`; `api/scaling.py`) | Y (`ScalingPanel` in `OperatorParityPanels.jsx`) | Y (`MonitoringSuite` Cluster sub-tab mounts ScalingPanel) | Y | `ENABLE_BAND_BASED_ROUTING` · `ENABLE_ADAPTIVE_POOL_SIZING` · `WORKLOAD_PROFILE` | **Active** |
| 79 | Adaptive Concurrency | Concurrency tuner | Y (`engines/adaptive_concurrency.py`, `adaptive_pool_sizer.py`, `adaptive_cooldown.py`) | — | — | Y | `ENABLE_ADAPTIVE_COOLDOWN` · `ADAPTIVE_COOLDOWN_MAX_MULT` | **Dormant** |
| 80 | Admission Controller | Queue-pressure based admission | Y (`engines/admission_controller.py`, `admission_wrapper.py`, `queue_pressure.py`) | — | — | Y | `ENABLE_ADMISSION_CONTROL` · `QUEUE_PRESSURE_WINDOW_SEC` | **Dormant** |
| 81 | Alert Engine | System alert generator | Y (`engines/alert_engine.py`) | — | — | Y | — | **Active** |
| 82 | Ingestion Health Aggregate | Cross-source ingestion KPI | Y (`engines/ingestion_health_aggregate.py`; `api/latent/ingestion_aggregate.py`, `api/latent/ingestion_health.py`; `api/ingestion.py`) | Y (`IngestionHealthCard.jsx`) | Y (`diag/ingestion`) | Y | — | **Active** |
| 83 | Compute Probe | Compute capability probe | Y (`engines/compute_probe.py`; `api/latent/compute_probe.py`) | — | — | Y (API) | `COMPUTE_AWARE_ORCHESTRATION` | **Dormant** |
| 84 | Deployment Readiness | Readiness gate engine | Y (`engines/readiness_engine.py`, `deployment_extras.py`; `api/readiness.py`, `api/deployment.py`, `api/latent/deployment_readiness.py`, `api/latent/deployment_extras.py`) | Y (`ReadinessPanel.js`, `DeploymentReadinessCard.jsx`) | Y (`governance/readiness`, `diag/readiness`) | Y | — | **Active** |
| 85 | Calibration Framework | Decile calibration | Y (`engines/calibration_framework.py`; `api/latent/calibration.py`) | — | — | Y (API) | `ENABLE_CALIBRATION` · `CALIBRATION_MIN_OUTCOMES` · `CALIBRATION_DECILE_COUNT` | **Dormant** |
| 86 | Risk of Ruin | RoR Monte-Carlo | Y (`engines/risk_of_ruin.py`; `api/latent/risk_of_ruin.py`) | — | — | Y (API) | `ENABLE_RISK_OF_RUIN` · `RISK_OF_RUIN_WEIGHT=0.0` · `RISK_OF_RUIN_DEFAULT_SIMS` | **Dormant** (weight pinned 0.0) |
| 87 | Lifecycle Decay | Aging-penalty engine | Y (`engines/lifecycle_decay.py`; `api/latent/lifecycle_decay.py`) | — | — | Y (API) | `ENABLE_AGING_PENALTY` · `AGING_TAU_DAYS` · `AGING_AUTO_DEMOTION_THRESHOLD` · `ENABLE_AGING_AUTO_DEMOTION` | **Dormant** |
| 88 | Safe to Widen | Safety widening gate | Y (`engines/safe_to_widen.py`; `api/latent/safe_to_widen.py`) | — | — | Y (API) | — | **Active** (engine; no panel) |
| 89 | Widening History | Widening audit | Y (`engines/widening_history.py`; `api/latent/widening_history.py`) | — | — | Y (API) | — | **Active** (no panel) |
| 90 | Widening Proposal | Widening proposal workflow | Y (`engines/widening_proposal.py`; consumed by `api/admin_flag_governance.py`) | Y (consumed by `AdminFlagGovernancePanel`) | Y (Flags sub-tab in Governance · Admin) | Y | — | **Active** |
| 91 | Flag Governance | Operator flag overrides | Y (`engines/flag_overrides.py`; `api/admin_flag_governance.py`) | Y (`AdminFlagGovernancePanel`) | Y (`governance/admin` → Flags) | Y | — | **Active** |
| 92 | Env Priority | Env-var introspection panel | Y (consumed by `EnvPriorityPanel`) | Y (`EnvPriorityPanel.js`) | Y (`governance/env`) | Y | — | **Active** |
| 93 | Audit Log Writer | Cross-engine audit logger | Y (`engines/audit_log_writer.py`) | — | — | Y | `AUDIT_LOG_RETENTION_DAYS` | **Active** |
| 94 | Activation Governance | Activation-gate orchestrator | Y (`engines/activation_governance.py`, `activation_journal.py`; `api/latent/activation_governance.py`, `api/latent/activation_timeline.py`) | — | — | Y (API) | — | **Active** (no panel; activation timeline in PRD) |
| 95 | Adaptive Rotation | Cell-rotation policy | Y (`engines/rotational_orchestrator.py`; consumed by `api/latent/advanced_scaffolding.py`) | — | — | Y (API) | `ENABLE_ROTATIONAL_ORCHESTRATION` · `ROTATIONAL_MAX_CELLS_PER_TICK` · `ROTATIONAL_EXPLORATION_FLOOR_PCT` · `ENABLE_ADAPTIVE_ROTATION` | **Dormant** |
| 96 | Event Continuation | Event-stream continuation | Y (`engines/event_continuation.py`) | — | — | Y | `ENABLE_EVENT_CONTINUATION` | **Dormant** |
| 97 | Replay Priority | Replay-event priority | Y (`engines/replay_priority.py`) | — | — | Y | `ENABLE_REPLAY_PRIORITY` | **Dormant** |
| 98 | Cadence Scheduler | Inter-cell pacing | Y (`engines/cadence_scheduler.py`) | — | — | Y | `ENABLE_CADENCE_SCHEDULER` · `CADENCE_MIN_GAP_MIN` | **Dormant** |
| 99 | Auto Scheduler | Master scheduler | Y (`engines/auto_scheduler.py`, `orchestrator_scheduler.py`) | Y (`AutoSchedulerControl.js`) | Y (`ai/sched`) | Y | — | **Active** |
| 100 | Orchestrator | LLM orchestrator | Y (`engines/ai_orchestrator.py`; `api/orchestrator.py`, `api/orchestrator_heartbeat.py`) | Y (`OrchestratorPanel.js`) | Y (`ai/orch`) | Y | — | **Active** (degrades to `readiness_blocked` when LLM key missing) |
| 101 | LLM Workforce River | Live LLM call river | Y (`engines/llm_runner.py`, `llm_config.py`; `api/llm_diagnostics.py`, `api/llm_health.py`) | Y (`LlmCallRiver` — inline in shell) | Y (`ai/river`) | Y | — | **Active** |
| 102 | Mission Briefing | Synthesised dashboard | — (composite of `/api/orchestrator/heartbeat` + `/api/monitoring/status` + `/api/readiness/snapshot`) | Y (`shell/dashboard/MissionBriefing.jsx`) | Y (`dashboard/briefing`) | Y | — | **Active** |
| 103 | Briefing Print | Print-friendly briefing | — | Y (`shell/dashboard/BriefingPrint.jsx`) | Y (print mode) | Y | — | **Active** |

---

## 7. Governance + admin capabilities

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 104 | Governance Card | Promotion / governance dashboard | Y (`engines/governance_universe.py`; `api/governance.py`) | Y (`GovernanceCard.jsx`) | Y (`governance/gov`) | Y | — | **Active** |
| 105 | Universe Governance | Symbol-governance ops | Y | Y (`UniverseGovernancePanel.jsx`) | Y (`governance/universe`) | Y | — | **Active** |
| 106 | Phase 12 Tuning | Tunable knob editor | Y (`engines/phase12_tuning.py`; `api/phase12_tuning.py`) | Y (`Phase12TuningPanel` via `GovernanceAdminSuite`) | Y (`governance/admin` → Tuning) | Y | — | **Active** |
| 107 | Auth + Admin Users | JWT auth + admin seeding | Y (`auth_utils.py`, `auth_middleware.py`; `api/auth.py`, `api/admin.py`) | Y (`AuthGate.js`, `AdminUsers.js`) | Y (`governance/admin` → Users) | Y | — | **Active** |
| 108 | Strategy Ingestion | External strategy ingest | Y (`engines/strategy_ingestion/*` — collector · injector · normalizer · parser · validator · schema · ingestion_runner) | Y (`StrategyIngestionCard.js`) | Y (`diag/ingest-src`) | Y | — | **Active** |

---

## 8. Phase 13 / 14 / 15 reservations

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 109 | Strategy Score Architecture | 4-metric reservation card (Quality · Evidence · Market · Trust) | — (engine pending) | Y (`StrategyScoreReservationCard.jsx`) | Y (`explorer/score-rubric`) | Y | — | **Placeholder** |
| 110 | Phase 13 Strategy Dossier | 12 report-slot reservations | — (engine pending) | Y (`Phase13ReservationsCard.jsx`) | Y (`explorer/passport-reservations`) | Y | — | **Placeholder** |
| 111 | Phase 14 Auto Valuation | Dual scorecard + auto-pricing | — (engine pending) | Y (`Phase14DualScorecardCard.jsx`) | Y (`portfolio/scorecards-reservations`) | Y | — | **Placeholder** |
| 112 | Phase 15 Marketplace | 3 product types · 6 metadata reservations | — (separate codebase) | Y (`Phase15MarketplaceReservation.jsx`) | Y (`explorer/marketplace-reservations`) | Y | — | **Placeholder** |
| 113 | Deployment (LifecycleRail stage 10) | Rail label only | — | Y (`LifecycleRail.jsx` L31) | Y (label; routes to Monitoring) | Y (as label) | — | **Placeholder** |

---

## 9. Factory Supervisor stack (dormant by hard veto)

| # | Capability | Description | Backend | Frontend | Mounted | Reachable | Feature flag | Status |
|---|---|---|---|---|---|---|---|---|
| 114 | Factory Supervisor (master) | FS orchestrator | Y (`api/factory_supervisor.py` + 22 engines under `engines/factory_supervisor/`) | Y (`FactorySupervisorPanel` in `OperatorParityPanels.jsx`) | **N** (lazy-imported `modulesRegistry.js` L122; no section references; Monitoring Cluster mounts `ScalingPanel` instead) | Partial (API live) | `ENABLE_FACTORY_SUPERVISOR` (default OFF) | **Hidden** + **Dormant** |
| 115 | FS Worker Runtime | Per-worker runtime | Y (`engines/factory_supervisor/worker_runtime.py`, `worker_scheduler.py`, `workload.py`) | — | — | Y (API: `/api/factory-supervisor/workers`, `/workers/tick`) | `FS_ENABLE_WORKER_SCHEDULER` · `FS_WORKER_POLL_INTERVAL_SEC` | **Dormant** |
| 116 | FS Defer Queue | Retry queue for deferred work | Y (`engines/factory_supervisor/defer_queue.py`) | — | — | Y (API: `/api/factory-supervisor/defer-queue*` × 5) | `FS_ENABLE_DEFER_QUEUE` · `FS_ENABLE_DEFER_WORKER` · `FS_DEFER_RETRY_BASE_SEC` · `FS_DEFER_RETRY_MAX_SEC` · `FS_DEFER_MAX_RETRIES` · `FS_DEFER_TTL_SEC` | **Dormant** |
| 117 | FS Routing Policy | Submission routing | Y (`engines/factory_supervisor/routing_policy.py`, `submission_dispatcher.py`) | — | — | Y (API: `/api/factory-supervisor/submit`, `/submissions`, `/routing-policy`) | `FS_ROUTING_POLICY` | **Dormant** |
| 118 | FS Heartbeat & Lock | Leader election + heartbeat | Y (`engines/factory_supervisor/supervisor_heartbeat.py`, `supervisor_lock.py`, `supervisor_events.py`, `advisory_lock.py`) | — | — | Y (API: `/api/factory-supervisor/heartbeats`, `/lock`, `/events`) | `FS_LEADER_LEASE_TTL_SEC` · `FS_HEARTBEAT_CADENCE_SEC` | **Dormant** |
| 119 | FS Fleet Registry | Worker-fleet registry | Y (`engines/factory_supervisor/fleet_registry.py`) | — | — | Y (API: `/api/factory-supervisor/fleet`) | — | **Dormant** |
| 120 | FS Remote Transport | Remote worker transport | Y (`engines/factory_supervisor/remote_transport.py`) | — | — | Y (API: `/api/factory-supervisor/remote-transport`) | `FS_REMOTE_TRANSPORT` | **Dormant** |
| 121 | FS System State View | Cross-system snapshot | Y (`engines/factory_supervisor/system_state_view.py`) | — | — | Y (API: `/api/factory-supervisor/system-state-view`) | `FS_ENABLE_SYSTEM_STATE_VIEW` | **Dormant** |
| 122 | **AI Architect (Advisor Stream)** | Operator-facing advisor dashboard | Y (`engines/factory_supervisor/architect_advisor.py`) | Y (`ArchitectDashboard.jsx::NextRecommendedActionCard`, `FleetHealthCard`, `QueuePressureCard`, `DeferQueueCard`, `RoutingCard`, `WorkerStatusCard`, `AdmissionScalingEventsCard`, `DeploymentReadinessSection`, `GovernancePanel`) | **N** (`ArchitectDashboard.jsx` has zero importers) | Partial (API: `/api/factory-supervisor/architect/dashboard`, `/architect/recommended-action`) | `FS_ENABLE_ARCHITECT_DASHBOARD` | **Hidden** + **Dormant** |
| 123 | **Recommendation Engine** | Multi-recommendation scorer | Y (`engines/factory_supervisor/recommendation_engine.py`) | Y (`ArchitectDashboard.jsx::NextRecommendedActionCard`) | **N** (parent unmounted) | Partial (API: `/api/factory-supervisor/recommendations`, `/recommendations/top`) | `FS_ENABLE_RECOMMENDATION_ENGINE` | **Hidden** + **Dormant** |
| 124 | **Notification Center (FS-backed)** | Persistent notification ledger | Y (`engines/factory_supervisor/notification_center.py`) | Y (`NotificationsCard` inside `ArchitectDashboard.jsx`) | **N** (parent unmounted; UI-only `inboxEvents.js` store mounted instead) | Partial (API: `/api/factory-supervisor/notifications` × 6 — get/unread-count/stats/acknowledge/archive/{id}) | `ENABLE_NOTIFICATION_CENTER` · `FS_ENABLE_NOTIFICATION_API` · `FS_ENABLE_NOTIFICATION_WORKER` | **Hidden** + **Dormant** |
| 125 | **Operator Inbox (UI-only)** | UI event-store drawer | — (event bus only; `inboxEvents.js`) | Y (`OperatorInboxDrawer.jsx` + `DangerRibbon.jsx`) | Y (mounted in `CommandShell.jsx`) | Y | — | **Active** (UI; backend NC dormant pending `ENABLE_NOTIFICATION_CENTER`) |
| 126 | **Copilot (basic)** | Live-data assist panel | Y (`engines/factory_supervisor/copilot_context.py`, `copilot_operational.py`) | Y (`shell/CopilotPanel.jsx`) | Y (mounted in `CommandShell.jsx`; toggled by command palette) | Y | `FS_ENABLE_COPILOT` · `FS_ENABLE_COPILOT_REFRESH` | **Active** (UI; FS backend gated dormant — UI panel reads `/api/orchestrator/heartbeat` + `/api/llm/call-log/recent` directly, no copilot backend dependency) |
| 127 | **Copilot (advanced)** | Multi-provider Copilot | Y (`engines/factory_supervisor/copilot_advanced.py`, `llm_adapter_base.py`) | — | — | Y (API: `/api/factory-supervisor/copilot/advanced/*` × 4) | `FS_ENABLE_COPILOT_ADVANCED` · `FS_COPILOT_PROVIDER` | **Dormant** |
| 128 | **Notification Drawer (live-data overlay)** | M5 live overlay reading 3 endpoints | — (`/api/monitoring/status` + `/api/admin/widening-proposals` + `/api/orchestrator/heartbeat`) | Y (`shell/NotificationDrawer.jsx`) | Y (mounted in `CommandShell.jsx`) | Y | — | **Active** |
| 129 | **AsfNotificationDrawer (Phase U-3)** | Read-only daily-digest drawer | — | Y (`components/ui-asf/AsfNotificationDrawer.jsx`) | Y (mounted in `CommandShell.jsx`) | Y | — | **Active** |
| 130 | **Eligibility Engine** | FS feature-gate evaluator | Y (`engines/factory_supervisor/eligibility_signals.py`) | — | — | Y (API: `/api/factory-supervisor/eligibility`, `/eligibility/{feature_name}`) | `FS_ENABLE_ELIGIBILITY_ENGINE` | **Dormant** |
| 131 | **Flag Auto-Governance (FAG) Proposals** | Auto proposal/approve/reject flag changes | Y (`engines/factory_supervisor/fag_proposals.py`) | — | — | Y (API: `/api/factory-supervisor/fag/*` × 8) | `FS_ENABLE_FAG_ENGINE` · `FS_FAG_PROPOSAL_TTL_SEC` | **Dormant** |
| 132 | **Auto Learning** | Continuous-learning feedback loop | Y (`engines/factory_supervisor/auto_learning.py`) | Y (`AutoLearningPanel` inline at `ArchitectDashboard.jsx::689`) | **N** (parent unmounted) | Partial (API: `/api/factory-supervisor/auto-learning/*` × 5 — status/aggregate/insights/eligibility/notify) | `FS_ENABLE_AUTO_LEARNING` · `FS_ENABLE_AUTO_LEARNING_LOOP` · `FS_ENABLE_AUTO_LEARNING_WORKER` · `FS_AUTO_LEARNING_ROR_THRESHOLD` · `FS_AUTO_LEARNING_AGING_THRESHOLD` · `FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES` | **Hidden** + **Dormant** |
| 133 | **FS Telemetry Worker** | Background telemetry emitter | Y (`engines/factory_supervisor/*`) | — | — | Y | `FS_ENABLE_TELEMETRY_WORKER` | **Dormant** |
| 134 | **FS Scheduler control** | Start/stop scheduler endpoints | Y (`api/factory_supervisor.py` `/scheduler/*`) | — | — | Y (API) | — | **Hidden** (API live; no UI control panel) |

---

## 10. Shell + UI overlays (active)

| # | Capability | Description | Frontend | Mounted | Status |
|---|---|---|---|---|---|
| 135 | TopTabBar (11 CORE + 6 MORE) | Primary nav | Y (`shell/TopTabBar.jsx`) | Y | **Active** |
| 136 | LifecycleRail (10-step) | Operator GPS | Y (`shell/LifecycleRail.jsx`) | Y | **Active** |
| 137 | StatusRail (6 chips) | Live posture chips | Y (`shell/StatusRail.jsx`) | Y | **Active** |
| 138 | LeftRail (legacy) | Module rail (hidden in shell mode) | Y (`shell/LeftRail.jsx`) | Y (collapsed) | **Active** |
| 139 | DangerRibbon | Top critical-alert bar | Y (`shell/DangerRibbon.jsx`) | Y | **Active** |
| 140 | EmergencyBanner | Emergency banner | Y (`shell/EmergencyBanner.jsx`) | Y | **Active** |
| 141 | CommandPalette | ⌘K palette | Y (`shell/CommandPalette.jsx`) | Y | **Active** |
| 142 | CommandBar | Top icon bar | Y (`shell/CommandBar.jsx`) | Y | **Active** |
| 143 | ShortcutsOverlay | Keyboard shortcut help | Y (`shell/ShortcutsOverlay.jsx`) | Y | **Active** |
| 144 | Lineage Strip | Per-strategy lineage indicator | Y (`shell/LineageStrip.jsx`) | Y (per-row) | **Active** |
| 145 | Mobile Surfaces | Mobile fallback surfaces | Y (`shell/MobileSurfaces.jsx`) | Y (posture-gated) | **Active** |
| 146 | Module Surface | Section host | Y (`shell/ModuleSurface.jsx`) | Y | **Active** |
| 147 | A11y AriaLiveRegion | Screen-reader announcer | Y (`components/a11y/AriaLiveRegion.jsx`) | Y | **Active** |
| 148 | UI-ASF design-system kit | 11 ASF tokens (KpiTile · Card · Drawer · EmptyState · Skeleton · Table · IndicatorLegend · VerdictBadge · VerdictChip · etc.) | Y (`components/ui-asf/*`) | Y | **Active** |
| 149 | shadcn-ui kit | shadcn components | Y (`components/ui/*`) | Y | **Active** |

---

## 11. Orphans + dead code (zero importers)

| # | Item | Path | LOC | Replacement | Status |
|---|---|---|---|---|---|
| 150 | `Optimization.js` (legacy) | `components/Optimization.js` | 506 | `OptimizationPanel.js` mounted at `lab/optim` ✅ | **Orphan** (Retire) |
| 151 | `ArchitectDashboard.jsx` (parent shell) | `components/ArchitectDashboard.jsx` | 940 | Partial — `GovernanceAdminSuite` + `MonitoringSuite` absorbed 3 children. Advisor Stream + Recommendation Feed + AutoLearningPanel + NotificationsCard NOT rehoused | **Orphan** (Rehouse children, then retire) |
| 152 | `NavMoreMenu.js` | `components/NavMoreMenu.js` | — | Superseded by `TopTabBar.jsx` MORE-menu chips | **Orphan** (Retire) |
| 153 | `DensityToggle.js` | `components/DensityToggle.js` | — | Density toggled internally by `usePosture.js` / `useDensity.js` | **Orphan** (Retire) |
| 154 | `TraderModeButton.js` | `components/TraderModeButton.js` | — | Trader/Operator mode absorbed by posture model | **Orphan** (Retire) |
| 155 | `phase9/AutoFactoryCard.js` | `components/phase9/AutoFactoryCard.js` | — | Superseded by `AutoFactoryPhase55.js` | **Orphan** (Retire) |
| 156 | `phase9/ExecutionDashboard.js` | `components/phase9/ExecutionDashboard.js` | 74 | Superseded by `exec/*` sections | **Orphan** (Retire) |
| 157 | `phase9/LiveExecutionCard.js` | `components/phase9/LiveExecutionCard.js` | — | Superseded by `LiveTrackingPanel.js` | **Orphan** (Retire) |
| 158 | `phase9/PortfolioBuilderCard.js` | `components/phase9/PortfolioBuilderCard.js` | — | Superseded by `PortfolioBuilder.js` | **Orphan** (Retire) |
| 159 | `phase9/ui.js` | `components/phase9/ui.js` | — | Superseded by `components/ui/*` + `components/ui-asf/*` | **Orphan** (Retire) |

---

## 12. Roll-up by status

| Status | Count | Notes |
|---|---|---|
| Active | **~100** | Core pipeline, market data, governance, monitoring, master bot, prop firm, shell overlays |
| Hidden | **6** | Challenge Matching · Factory Supervisor master · Architect Dashboard · Recommendation Engine · Auto Learning · Notification Center · BI5 Certification (no UI panel) · Runner Registry (no panel) · Factory Runner Heartbeat (no panel) · FS Scheduler control (no panel) — total varies depending on whether you count "engine-only with no UI" as Hidden or Active-backend; conservative count = **6** UI-class hidden surfaces |
| Dormant | **~22** | Mostly feature-flag-gated engines: FS workers/queues/policy/copilot-advanced/eligibility/FAG/auto-learning, calibration, RoR, lifecycle decay, cadence, rotational, anti-correlation, admission control, compute-aware, multi-account, replay/event continuation |
| Placeholder | **5** | Phase 13 Dossier, Phase 14 Valuation, Phase 15 Marketplace, Strategy Score (4 metric scaffold), Execution Broker Chips (cTrader/VPS slots), LifecycleRail Deployment label |
| Orphan | **10** | `Optimization.js`, `ArchitectDashboard.jsx`, `NavMoreMenu.js`, `DensityToggle.js`, `TraderModeButton.js`, 5× `phase9/*` |
| Dead | **0** | All orphans have a clear replacement story — no truly "dead" code |

---

## 13. State of this document

* Read-only audit.
* Companion to `MISSING_FROM_UI.md` (operator-visibility view) and `ROADMAP_RECONCILIATION.md` (roadmap-status view).
* No code modified. No imports run. No flags flipped.

**End of report.**
