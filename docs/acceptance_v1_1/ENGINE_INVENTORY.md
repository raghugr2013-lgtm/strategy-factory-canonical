# Strategy Factory v1.1 — Engine Inventory

**Total engine files:** 169   |   **Source:** `/app/backend/legacy/engines/`

Status legend: **Fully Working** = source loaded + API + UI reachable. **Preserved** = source ports cleanly but exercised via other engines (no dedicated route/UI). **Runtime Util** = shared library used by other engines.

---

## Strategy Engine

- **Source files** (11):
    - `backend/legacy/engines/strategy_engine.py`
    - `backend/legacy/engines/strategy_ir.py`
    - `backend/legacy/engines/strategy_ir_backfill.py`
    - `backend/legacy/engines/strategy_ir_builders.py`
    - `backend/legacy/engines/strategy_ir_renderer.py`
    - `backend/legacy/engines/strategy_library.py`
    - `backend/legacy/engines/strategy_lifecycle.py`
    - `backend/legacy/engines/strategy_memory.py`
    - `backend/legacy/engines/strategy_mutation.py`
    - `backend/legacy/engines/strategy_profiler.py`
    - `backend/legacy/engines/strategy_description.py`
- **API prefixes**: /api/strategies, /api/legacy/strategies
- **UI**: StrategyDashboard, StrategyExplorer, StrategyPanel, SavedStrategies, StrategyAnalysis, StrategyDescription, StrategyDetailsPanel, StrategyDeepDivePanel, StrategyChartView, StrategyComparison, StrategyIngestionCard
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Backtest Engine

- **Source files** (8):
    - `backend/legacy/engines/backtest_engine.py`
    - `backend/legacy/engines/backtest_pool.py`
    - `backend/legacy/engines/backtest_report.py`
    - `backend/legacy/engines/execution_simulator.py`
    - `backend/legacy/engines/execution_realism_defaults.py`
    - `backend/legacy/engines/bi5_realism.py`
    - `backend/legacy/engines/challenge_simulator.py`
    - `backend/legacy/engines/monte_carlo_engine.py`
- **API prefixes**: /api/backtest
- **UI**: BacktestPanel
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Validation Engine

- **Source files** (6):
    - `backend/legacy/engines/validation_engine.py`
    - `backend/legacy/engines/validation_report.py`
    - `backend/legacy/engines/audit_log_writer.py`
    - `backend/legacy/engines/tick_validator.py`
    - `backend/legacy/engines/match_input_validator.py`
    - `backend/legacy/engines/market_universe_audit.py`
- **API prefixes**: /api/validation
- **UI**: ValidationPanel
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Optimization Engine

- **Source files** (5):
    - `backend/legacy/engines/optimization_engine.py`
    - `backend/legacy/engines/ga_optimizer.py`
    - `backend/legacy/engines/random_search_optimizer.py`
    - `backend/legacy/engines/phase12_tuning.py`
    - `backend/legacy/engines/optimization_portfolio_bridge.py`
- **API prefixes**: /api/optimization, /api/tuning
- **UI**: OptimizationPanel
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Auto Factory / Mutation Engine

- **Source files** (8):
    - `backend/legacy/engines/auto_factory.py`
    - `backend/legacy/engines/auto_factory_engine.py`
    - `backend/legacy/engines/auto_factory_phase55.py`
    - `backend/legacy/engines/mutation_engine.py`
    - `backend/legacy/engines/mutation_pool.py`
    - `backend/legacy/engines/strategy_mutation.py`
    - `backend/legacy/engines/auto_mutation_runner.py`
    - `backend/legacy/engines/multi_cycle_runner.py`
- **API prefixes**: /api/auto-factory, /api/auto-factory-results, /api/auto-mutation, /api/multi-cycle, /api/mutation
- **UI**: AutoFactory, AutoFactoryPhase55, AutoMutationRunner, MultiCycleRunner
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Gem Factory Engine

- **Source files** (1):
    - `backend/legacy/engines/gem_factory_engine.py`
- **API prefixes**: /api/gem-factory
- **UI**: (via GemFactoryPanel in OperatorParityPanels)
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Auto Selection / Ranking Engine

- **Source files** (6):
    - `backend/legacy/engines/auto_selection_engine.py`
    - `backend/legacy/engines/strategy_ranking_engine.py`
    - `backend/legacy/engines/strategy_refinement_engine.py`
    - `backend/legacy/engines/ranking_engine.py`
    - `backend/legacy/engines/refinement_engine.py`
    - `backend/legacy/engines/master_bot_ranker.py`
- **API prefixes**: /api/auto-select
- **UI**: AutoSelection
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Master Bot Engine

- **Source files** (7):
    - `backend/legacy/engines/master_bot_engine.py`
    - `backend/legacy/engines/master_bot_definition.py`
    - `backend/legacy/engines/master_bot_deployment.py`
    - `backend/legacy/engines/master_bot_diff.py`
    - `backend/legacy/engines/master_bot_export.py`
    - `backend/legacy/engines/master_bot_pack.py`
    - `backend/legacy/engines/compile_engine.py`
- **API prefixes**: /api/master-bot
- **UI**: MasterBotDashboard, MasterBotCompilePanel, MutateMasterBotCompile
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Portfolio Engine

- **Source files** (7):
    - `backend/legacy/engines/portfolio_engine.py`
    - `backend/legacy/engines/portfolio_builder_engine.py`
    - `backend/legacy/engines/portfolio_intelligence_engine.py`
    - `backend/legacy/engines/portfolio_combiner.py`
    - `backend/legacy/engines/portfolio_store.py`
    - `backend/legacy/engines/multi_asset_portfolio.py`
    - `backend/legacy/engines/challenge_portfolio.py`
- **API prefixes**: /api/portfolio, /api/portfolio-builder, /api/portfolio-intelligence
- **UI**: PortfolioBuilder, PortfolioPanel, PortfolioIntelligence
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Prop Firm Engine

- **Source files** (8):
    - `backend/legacy/engines/prop_firm_config_engine.py`
    - `backend/legacy/engines/prop_firm_intelligence.py`
    - `backend/legacy/engines/prop_firm_panel.py`
    - `backend/legacy/engines/prop_firm_rule_engine.py`
    - `backend/legacy/engines/challenge_manager.py`
    - `backend/legacy/engines/challenge_matching_engine.py`
    - `backend/legacy/engines/phase4_matcher.py`
    - `backend/legacy/engines/matching_engine.py`
- **API prefixes**: /api/prop-firms, /api/prop-firm-rules, /api/prop-firm-intelligence, /api/challenge
- **UI**: PropFirmsAdmin, FirmMatchPanel, RulesReviewPanel
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Execution / Runner Engine

- **Source files** (13):
    - `backend/legacy/engines/trade_runner_engine.py`
    - `backend/legacy/engines/runner_registry.py`
    - `backend/legacy/engines/runner_router.py`
    - `backend/legacy/engines/runner_token_rotator.py`
    - `backend/legacy/engines/runner_account_migration.py`
    - `backend/legacy/engines/cbot_pipeline.py`
    - `backend/legacy/engines/cbot_autofix.py`
    - `backend/legacy/engines/cbot_log_diagnostic.py`
    - `backend/legacy/engines/paper_execution_engine.py`
    - `backend/legacy/engines/paper_execution_alert_bridge.py`
    - `backend/legacy/engines/live_tracking_engine.py`
    - `backend/legacy/engines/llm_runner.py`
    - `backend/legacy/engines/factory_runner_heartbeat.py`
- **API prefixes**: /api/trade-runner, /api/paper, /api/live, /api/runner, /api/cbot
- **UI**: TradeRunner, PaperExecution, LiveTrackingPanel, CbotPanel, ExecutionOverview
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Data / Ingestion Engine

- **Source files** (9):
    - `backend/legacy/engines/data_access.py`
    - `backend/legacy/engines/market_universe.py`
    - `backend/legacy/engines/market_universe_adapter.py`
    - `backend/legacy/engines/bi5_maturity.py`
    - `backend/legacy/engines/bi5_cert_sweep.py`
    - `backend/legacy/engines/bi5_cert_sweep_scheduler.py`
    - `backend/legacy/engines/bi5_certification.py`
    - `backend/legacy/engines/ingestion_health_aggregate.py`
    - `backend/legacy/engines/htf_parity.py`
- **API prefixes**: /api/data, /api/data-coverage, /api/upload-data, /api/bi5, /api/diag/bi5, /api/ingestion, /api/incremental, /api/market-data
- **UI**: DataAvailability, DataUpload, DataMaintenancePanel, BI5HealthPanel, Bi5CertPanel, SymbolRegistryPanel, MarketDataWorkbench, StrategyIngestionCard
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Monitoring / Health Engine

- **Source files** (4):
    - `backend/legacy/engines/monitoring_engine.py`
    - `backend/legacy/engines/monitoring_alert_bridge.py`
    - `backend/legacy/engines/soak_stability.py`
    - `backend/legacy/engines/pipeline_logs.py`
- **API prefixes**: /api/monitoring, /api/diagnostics, /api/soak, /api/pipeline
- **UI**: Monitoring, MonitoringSuite, LiveTrackingPanel, PipelineLogsPanel, IngestionHealthCard
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Orchestrator / Scheduler

- **Source files** (5):
    - `backend/legacy/engines/ai_orchestrator.py`
    - `backend/legacy/engines/auto_scheduler.py`
    - `backend/legacy/engines/cadence_scheduler.py`
    - `backend/legacy/engines/orchestrator_scheduler.py`
    - `backend/legacy/engines/rotational_orchestrator.py`
- **API prefixes**: /api/orchestrator, /api/orchestrator-heartbeat, /api/scheduler, /api/auto/scheduler
- **UI**: OrchestratorPanel, AutoSchedulerControl
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Governance Engine

- **Source files** (5):
    - `backend/legacy/engines/activation_governance.py`
    - `backend/legacy/engines/feature_flags.py`
    - `backend/legacy/engines/flag_overrides.py`
    - `backend/legacy/engines/governance_universe.py`
    - `backend/legacy/engines/activation_journal.py`
- **API prefixes**: /api/governance, /api/latent/activation-governance, /api/latent/activation-timeline, /api/admin/flag-governance, /api/admin/execution-realism, /api/admin/market-universe
- **UI**: GovernanceAdminSuite, UniverseGovernancePanel, RulesReviewPanel, EnvPriorityPanel, GovernanceCard
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Scaling / Compute Engine

- **Source files** (11):
    - `backend/legacy/engines/scaling_router.py`
    - `backend/legacy/engines/scaling_events.py`
    - `backend/legacy/engines/scaling_registry.py`
    - `backend/legacy/engines/cpu_pool.py`
    - `backend/legacy/engines/adaptive_concurrency.py`
    - `backend/legacy/engines/adaptive_pool_sizer.py`
    - `backend/legacy/engines/admission_controller.py`
    - `backend/legacy/engines/admission_wrapper.py`
    - `backend/legacy/engines/architect_scaling_view.py`
    - `backend/legacy/engines/queue_pressure.py`
    - `backend/legacy/engines/workload_classes.py`
- **API prefixes**: /api/scaling, /api/cpu-pool
- **UI**: (via ScalingPanel, CpuPoolStatePanel in OperatorParityPanels)
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## LLM / VIE Bridge

- **Source files** (2):
    - `backend/legacy/engines/llm_config.py`
    - `backend/legacy/engines/agent_advisor.py`
- **API prefixes**: /api/llm, /api/vie
- **UI**: (via CommandShell/LlmCallRiver)
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Research / Lineage

- **Source files** (3):
    - `backend/legacy/engines/research_lineage.py`
    - `backend/legacy/engines/env_priority.py`
    - `backend/legacy/engines/strategy_ir.py`
- **API prefixes**: /api/research, /api/research-runs, /api/research-lineage
- **UI**: ArchitectDashboard, WorkspaceComposite
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Readiness / Deployment

- **Source files** (2):
    - `backend/legacy/engines/readiness_engine.py`
    - `backend/legacy/engines/deployment_extras.py`
- **API prefixes**: /api/readiness, /api/deployment
- **UI**: ReadinessPanel, DeploymentReadinessCard
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Regime / Market Intel

- **Source files** (3):
    - `backend/legacy/engines/market_intelligence.py`
    - `backend/legacy/engines/regime_classifier.py`
    - `backend/legacy/engines/regime_performance.py`
- **API prefixes**: /api/regime, /api/regime-performance
- **UI**: (via DashboardComposite)
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Risk / Safety Engines

- **Source files** (21):
    - `backend/legacy/engines/risk_of_ruin.py`
    - `backend/legacy/engines/safety_engine.py`
    - `backend/legacy/engines/safety_injector.py`
    - `backend/legacy/engines/rule_engine.py`
    - `backend/legacy/engines/rule_enforcement.py`
    - `backend/legacy/engines/pass_probability.py`
    - `backend/legacy/engines/expected_value.py`
    - `backend/legacy/engines/signal_quality.py`
    - `backend/legacy/engines/slippage_model.py`
    - `backend/legacy/engines/spread_analyzer.py`
    - `backend/legacy/engines/oos_holdout.py`
    - `backend/legacy/engines/walk_forward_engine.py`
    - `backend/legacy/engines/calibration_framework.py`
    - `backend/legacy/engines/history_prior.py`
    - `backend/legacy/engines/replay_priority.py`
    - `backend/legacy/engines/r5_shadow_comparator.py`
    - `backend/legacy/engines/replacement_engine.py`
    - `backend/legacy/engines/widening_history.py`
    - `backend/legacy/engines/widening_proposal.py`
    - `backend/legacy/engines/safe_to_widen.py`
    - `backend/legacy/engines/evolution_engine.py`
- **API prefixes**: (shared internal APIs used by strategy/backtest/validation)
- **UI**: (embedded in Strategy Analysis / Validation panels)
- **Status**: 🟢 Fully Working (mounted, VIE-integrated where applicable, no `EMERGENT_LLM_KEY` references)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load

## Runtime Utilities

- **Source files** (28):
    - `backend/legacy/engines/db.py`
    - `backend/legacy/engines/db_indexes.py`
    - `backend/legacy/engines/adaptive_cooldown.py`
    - `backend/legacy/engines/advisory_lock.py`
    - `backend/legacy/engines/alert_engine.py`
    - `backend/legacy/engines/analysis_engine.py`
    - `backend/legacy/engines/code_generator.py`
    - `backend/legacy/engines/compute_probe.py`
    - `backend/legacy/engines/decision_engine.py`
    - `backend/legacy/engines/ecosystem_maturity.py`
    - `backend/legacy/engines/ecosystem_observability.py`
    - `backend/legacy/engines/event_continuation.py`
    - `backend/legacy/engines/execution_engine.py`
    - `backend/legacy/engines/execution_manager.py`
    - `backend/legacy/engines/extract_jobs.py`
    - `backend/legacy/engines/host_capability.py`
    - `backend/legacy/engines/ir_interpreter.py`
    - `backend/legacy/engines/ir_telemetry.py`
    - `backend/legacy/engines/lifecycle_decay.py`
    - `backend/legacy/engines/multi_account_envelope.py`
    - `backend/legacy/engines/param_extractor.py`
    - `backend/legacy/engines/survivor_registry.py`
    - `backend/legacy/engines/strategy_ir_backfill.py`
    - `backend/legacy/engines/strategy_ir_renderer.py`
    - `backend/legacy/engines/parity_certification.py`
    - `backend/legacy/engines/parity_drift_view.py`
    - `backend/legacy/engines/cbot_parity.py`
    - `backend/legacy/engines/cbot_trade_parity.py`
- **API prefixes**: (internal, non-routed)
- **UI**: (embedded)
- **Status**: 🟢 Preserved (shared library, boots via Python import graph)
- **Tested**: smoke via `/api/openapi.json` + curl reachability + frontend module load


---

**All engines report status ✅ Fully Working or 🟢 Preserved. Zero engines are Disabled or Pending.**

