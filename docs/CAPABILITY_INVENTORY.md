# Strategy Factory — Capability Inventory

**Scope:** Every significant backend subsystem present in the canonical
repo (`strategy-factory-canonical` @ `main` · v1.1.0-stage4).
**Method:** Repo-only static survey — no runtime probing. Sources: mount
block in `backend/app/main.py`, module layout under `backend/app/*` and
`backend/legacy/*`, test tree under `backend/tests/` and
`backend/legacy/tests/`, contents of `docs/RELEASE_NOTES.md`,
`memory/PHASE_*` reports, and `memory/BACKEND_FEATURE_FREEZE.md`.
**Purpose:** Maximum-reuse baseline for Historical Knowledge Base,
Autonomous Research Factory, Strategy Explorer, Strategy Registry,
Master Bot, Paper Trading, Export Engine, and Human Workspace.

> Legend for classification:
> **PR** Production Ready · **MC** Mostly Complete ·
> **NR** Needs Refinement · **NE** Needs Extension ·
> **LR** Legacy but Reusable · **MG** Missing.
> Recommendation: exactly one of Reuse / Refine / Extend / Replace / Build New.

---

## Section A · Phase-1 Core (`backend/app/`)

Small, hand-audited, freeze-locked at v1.1.0-stage4. Owns the canonical
`/api/auth`, `/api/admin`, `/api/health`, `/api/research`,
`/api/dashboard/summary`, `/api/strategies/*`, `/api/knowledge/*` paths.

| # | Subsystem | Files | Status | APIs | Storage | Tests | Recommendation |
|---|-----------|-------|--------|------|---------|-------|----------------|
| A1 | Auth (JWT + refresh rotation + 5-role RBAC + admin-approve signup) | `auth/{routes,security,seed,deps}.py` | **PR** | `/api/auth/login`, `/refresh`, `/me`, `/logout`, `/register`, admin approve/list | Mongo: `users`, `refresh_tokens` | `test_auth_admin_system.py` + `test_api_endpoints.py` | **Reuse** |
| A2 | Admin (user CRUD, role change, approve pending) | `api/admin.py` | **PR** | `/api/admin/users*`, `/api/admin/pending`, `/api/admin/readiness` | `users` | `test_auth_admin_system.py` | **Reuse** |
| A3 | Health + Universal Health Contract | `api/health.py` + `engines/health/router.py` + CTS | **PR** | `/api/health`, `/api/readiness`, `/api/health/{system,subsystems,<name>}` | none | `test_health_contract.py`, `test_cts.py` | **Reuse** |
| A4 | Research surface | `api/research.py` | **PR** | `/api/research/*` (Explorer-driven read-outs, lineage) | KB DB via `KnowledgeRepository` | `test_research_lineage_g1.py` | **Reuse** |
| A5 | Dashboard summary | `api/dashboard.py` | **PR** | `/api/dashboard/summary` | multiple engines | in-suite | **Reuse** |
| A6 | Strategies CRUD | `api/strategies.py` | **PR** | `/api/strategies` (POST/GET), `/{id}` | `strategies` (`eligible_for_deploy` guard) | `test_strategy_route_split.py`, `test_api_compatibility.py` | **Reuse** |
| A7 | Knowledge subsystem router | `knowledge/{router,repository,canonical,evaluation,similarity}.py` | **PR** | `/api/knowledge/{nearest, families/<h>, champions, statistics, strategy/<id>, health}` | `strategy_knowledge_base` (isolated DB) via `KnowledgeRepository` | `test_knowledge_layer.py`, `test_knowledge_pipeline.py`, `test_knowledge_router.py` | **Reuse** |
| A8 | VIE client wrapper | `vie/client.py` | **PR** | consumed via LLM engines | none | `test_provider_hint.py`, `test_llm_config.py`, `test_llm_routing_migration.py` | **Reuse** |
| A9 | Config + versioning + Mongo bootstrap | `core/{config,versioning}.py`, `db/{mongo,models}.py` | **PR** | `/api/version` | index bootstrap on boot | `test_migration.py`, `test_dedup_and_repository.py` | **Reuse** |
| A10 | factory-runner Phase-0 stub | `runner.py` | **MC** — heartbeat only | none | `/tmp/factory_runner.hb` | `test_factory_runner_heartbeat.py` | **Extend** (Phase 5 wiring below) |

---

## Section B · Historical Knowledge Base

Isolated Mongo DB `strategy_knowledge_base`, populated from Phase 1.5 /
Phase 1.6 ingestion. Every row carries `learning_only=True` and every
read is guarded by `KnowledgeRepository`.

| # | Subsystem | Files | Status | Key contract | Recommendation |
|---|-----------|-------|--------|--------------|----------------|
| B1 | `KnowledgeRepository` (read-only, write-refusing) | `app/knowledge/repository.py` | **PR** | `find/find_one/count/aggregate` inject `learning_only=True`; every write raises `_ImmutableError` | **Reuse** |
| B2 | `StrategyRepository` (production reads) | same file | **PR** | injects `eligible_for_deploy != False` → KB rows structurally invisible to production reads | **Reuse** |
| B3 | Canonical hashing (structural family detection) | `app/knowledge/canonical.py` | **PR** | family-level dedup + regression detection | **Reuse** |
| B4 | Six-dimensional evaluation | `app/knowledge/evaluation.py` (`DeploymentReadiness`) | **PR** | `evaluate_from_legacy_metrics()` returns a Pydantic model; readiness ceiling is `PENDING_VALIDATION` for every KB row | **Reuse** |
| B5 | Similarity backends | `similarity.py` — `RuleBasedSimilarity`, `EmbeddingSimilarityStub` | **MC** (embedding is a stub) | Stable request/response contract; backend swap is one env var (`SIMILARITY_BACKEND`) | **Extend** (implement the embedding backend behind the existing stub) |
| B6 | Champions + families + statistics endpoints | `app/knowledge/router.py` | **PR** | `/api/knowledge/champions`, `/families/<hash>`, `/statistics` | **Reuse** |
| B7 | Knowledge ingestion pipeline | `legacy/engines/knowledge/*` + `legacy/api/knowledge.py` + `app/knowledge/*` | **NE** — historical import complete; migration path for new corpora is drafted only (`docs/KB_MIGRATION_SPEC.md v0.1`) | ingestion connectors, dedup policy, guardrails | **Extend** (execute drafted KB Migration Spec) |
| B8 | UKIE foundation (Universal Knowledge Ingestion Engine) | `legacy/engines/knowledge/router.py` (`/api/knowledge/domains,connectors`) | **MC** — flag-gated, self-503 when off (`UKIE_DOMAIN_REGISTRY_ENABLED`) | domain registry + connector scaffolding | **Extend** (register the KB migration domains + connectors) |

---

## Section C · Autonomous Orchestration (v1.2.0-alpha2 Phase B / B.1 / B.2)

Three concentric schedulers. Phase B.2 (orchestrator) supersedes B.1
(continuous) which supersedes B (fixed-interval learning scheduler).
All three coexist; production picks one via env.

| # | Subsystem | Files | Status | Storage | Recommendation |
|---|-----------|-------|--------|---------|----------------|
| C1 | Outcome-event ledger (emitter + lineage + supervisor) | `legacy/engines/learning/{emitter,lineage,supervisor,config}.py` + `/api/learning/*` | **PR** | `outcome_events` + indexes bootstrapped on boot | **Reuse** |
| C2 | Continuous capacity-aware scheduler | `legacy/engines/learning/continuous_scheduler.py` | **PR** | scheduler state row | **Reuse** |
| C3 | Unified Autonomous Orchestration Engine (Phase B.2) | `legacy/engines/orchestrator/{core,registry,budget_tracker,types}.py` + `/api/orchestrator/*` | **PR** — auto-starts on boot when `ORCHESTRATOR_ENABLED=true`; every subordinate scheduler dorms in favor of it | Mongo state + budget rehydration (BUDGET_PERSIST) | **Reuse** |
| C4 | Task registry (17 registered tasks) | `orchestrator/tasks/*` — backtest, mutation, optimization, ranking, validation, strategy_generate, learning_cycle, market_data_topup, knowledge_index_refresh, market_intelligence_refresh, master_bot_bundle_refresh, meta_learning_evaluation, factory_evaluation, self_rebuild, bi5_realism_sweep, broker_health_check, execution_attribution | **PR** | task ledger | **Reuse** |
| C5 | Budget tracker (daily USD accounting, restart-preserved) | `orchestrator/budget_tracker.py` | **PR** | Mongo state + boot rehydration | **Reuse** |
| C6 | Auto-scheduler + orchestrator scheduler + auto data maintainer (legacy) | `engines/auto_scheduler.py`, `engines/orchestrator_scheduler.py`, `data_engine/auto_data_maintainer.py` | **LR** (subordinated to C3 when Phase B.2 flag is on) | persisted enable-flags | **Reuse** (as subordinate services) |
| C7 | Runner container process | `app/runner.py` (Phase 0 stub) + `legacy/factory_runner.py` (Phase 5 recovered) | **NE** — stub in production; recovered impl exists but not yet wired | heartbeat file | **Extend** (swap stub for recovered `legacy.factory_runner:_main`) |

---

## Section D · Strategy Generation Stack

The Strategy Lab and Auto Factory both draw from this stack.

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| D1 | LLM-backed generator + refinement | `engines/strategy_engine.py`, `strategy_refinement_engine.py`, `refinement_engine.py`, `strategy_description.py`, `code_generator.py`, `compile_engine.py` | **PR** | **Reuse** |
| D2 | Strategy IR (Intermediate Representation) | `engines/strategy_ir*.py` (`ir`, `ir_builders`, `ir_renderer`, `ir_backfill`, `ir_interpreter`, `ir_telemetry`) | **PR** — v1.2 canonical shape | **Reuse** |
| D3 | cBot pipeline (IR → C# → parity) | `cbot_engine/{generator,ir_emitter,ir_transpiler,ir_parity_simulator,ir_templates}.py`, `engines/{cbot_pipeline,cbot_parity,cbot_trade_parity,cbot_autofix,cbot_log_diagnostic}.py` | **PR** | **Reuse** |
| D4 | Strategy mutation | `engines/mutation_engine.py`, `strategy_mutation.py`, `mutation_pool.py`, `auto_mutation_runner.py` | **PR** | **Reuse** |
| D5 | Auto selection / replacement | `engines/auto_selection_engine.py`, `replacement_engine.py`, `evolution_engine.py` | **PR** | **Reuse** |
| D6 | Ranking + profiling | `engines/strategy_ranking_engine.py`, `ranking_engine.py`, `strategy_profiler.py`, `strategy_library.py` | **PR** | **Reuse** |
| D7 | Auto Factory (Phase 1B) | `engines/auto_factory.py`, `auto_factory_engine.py`, `auto_factory_phase55.py` + `/api/auto-factory/*` | **MC** — Phase 55 present; hooked via orchestrator task | **Reuse** |
| D8 | Decision engine | `engines/decision_engine.py` | **PR** | **Reuse** |
| D9 | Strategy Lab surface | `frontend/src/os/surfaces/StrategyLab.jsx` (live) | **PR** | **Reuse** |

---

## Section E · Backtest, Optimization, Validation

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| E1 | Backtest engine + pool + reports | `engines/backtest_{engine,pool,report}.py` | **PR** | **Reuse** |
| E2 | Walk-forward + Monte-Carlo + OOS holdout | `engines/walk_forward_engine.py`, `monte_carlo_engine.py`, `oos_holdout.py` | **PR** | **Reuse** |
| E3 | Regime classifier + performance | `engines/regime_classifier.py`, `regime_performance.py` + `intelligence/market_regime.py` | **PR** | **Reuse** |
| E4 | Optimization engines | `engines/optimization_engine.py`, `random_search_optimizer.py`, `ga_optimizer.py`, `phase12_tuning.py` | **PR** | **Reuse** |
| E5 | Optimization ↔ Portfolio bridge | `engines/optimization_portfolio_bridge.py` | **PR** | **Reuse** |
| E6 | Validation engine + report | `engines/validation_engine.py`, `validation_report.py` | **PR** | **Reuse** |
| E7 | Signal quality + expected-value + pass-probability + risk-of-ruin + calibration | `engines/{signal_quality,expected_value,pass_probability,risk_of_ruin,calibration_framework}.py` | **PR** | **Reuse** |
| E8 | Structural robustness / safe-to-widen / widening history + proposal | `engines/{soak_stability,safe_to_widen,widening_history,widening_proposal}.py` | **PR** | **Reuse** |

---

## Section F · Data + Market Universe

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| F1 | Data manager + Dukascopy downloader | `data_engine/{data_manager,dukascopy_downloader}.py` | **PR** | **Reuse** |
| F2 | BI5 ingest runner (weekly sweep) | `data_engine/bi5_ingest_runner.py` + `engines/bi5_ingest_runner.*` | **PR** | **Reuse** |
| F3 | BI5 certification + realism + maturity + cert-sweep | `engines/{bi5_certification,bi5_realism,bi5_maturity,bi5_cert_sweep,bi5_cert_sweep_scheduler,bi5_bid_diff,bi5_bid_diff_router}.py` | **PR** | **Reuse** |
| F4 | Tick aggregator / archive / validator | `data_engine/{tick_aggregator,tick_archive,tick_validator}.py` | **PR** | **Reuse** |
| F5 | Auto data maintainer (resume-on-boot APScheduler) | `data_engine/auto_data_maintainer.py` | **PR** | **Reuse** |
| F6 | CSV ingester + gap analyzer + incremental updater + backup | `data_engine/{csv_ingester,gap_analyzer,incremental_updater,data_backup,data_maintenance}.py` | **PR** | **Reuse** |
| F7 | Market calendar (incl. metal-holiday) | `data_engine/market_calendar.py` | **PR** | **Reuse** |
| F8 | Market universe (config + adapter + audit + seed + eligibility) | `engines/market_universe*.py`, `governance_universe.py` | **PR** | **Reuse** |
| F9 | Spread analyzer + store | `engines/spread_analyzer.py`, `market_spread_store` (via BI5 ingest wiring) | **PR** | **Reuse** |
| F10 | Coverage router | `engines/coverage_router.py` (`/api/data/coverage`) | **PR** | **Reuse** |

---

## Section G · Portfolio + Master Bot + Prop Firms

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| G1 | Portfolio engine (v1.2.0-alpha2 Phase D) | `engines/portfolio/{allocation,capital,promotion,retirement,rebuilder,closed_learning,health,config}.py` + `/api/portfolio/*` | **PR** | **Reuse** |
| G2 | Legacy portfolio (builder, combiner, intelligence, store) | `engines/{portfolio_engine,portfolio_builder_engine,portfolio_combiner,portfolio_intelligence_engine,portfolio_store}.py` | **PR** | **Reuse** |
| G3 | Multi-asset + multi-account envelope | `engines/{multi_asset_portfolio,multi_account_envelope}.py` | **PR** | **Reuse** |
| G4 | Master Bot | `engines/master_bot_{engine,definition,deployment,diff,export,pack,ranker}.py` + `/api/master-bot/*` | **PR** | **Reuse** |
| G5 | Prop firms (config, panel, rule engine, intelligence) | `engines/prop_firm_{config_engine,panel,rule_engine,intelligence}.py` + `/api/prop-firms*` | **PR** | **Reuse** |
| G6 | Challenge simulator + matcher + portfolio + manager | `engines/challenge_{simulator,matching_engine,portfolio,manager}.py`, `phase4_matcher.py`, `match_input_validator.py` | **PR** | **Reuse** |
| G7 | Gem Factory (Phase 11) | `engines/gem_factory_engine.py` + `/api/gem-factory/*` | **PR** | **Reuse** |

---

## Section H · Paper Trading + Execution + Broker

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| H1 | Paper execution engine + alert bridge | `engines/paper_execution_engine.py`, `paper_execution_alert_bridge.py` | **PR** | **Reuse** |
| H2 | Execution engine v1.2 (Phase H) | `engines/execution/{order_lifecycle,position_lifecycle,quality,attribution,replay,risk_monitor,ledger,broker_health,config,types}.py` + `/api/execution/*` (17 endpoints incl. immutable journal) | **PR** — indexes bootstrap on boot; dormant when `EXEC_ENABLED=false` | **Reuse** |
| H3 | Broker adapters | `execution/broker/{paper,ctrader}` + `broker/base.py` | **MC** — paper live, cTrader adapter scaffolded | **Extend** (finish cTrader; add more if needed) |
| H4 | Ledger backends | `execution/ledger_backends/{memory,mongo,registry}.py` | **PR** | **Reuse** |
| H5 | Execution simulator + realism defaults + slippage | `engines/{execution_simulator,execution_realism_defaults,slippage_model}.py` | **PR** | **Reuse** |
| H6 | Live tracking | `engines/live_tracking_engine.py` + `/api/live-tracking/*` | **PR** | **Reuse** |
| H7 | Trade runner + engine | `engines/trade_runner_engine.py` + `/api/trade-runner/*` | **PR** | **Reuse** |

---

## Section I · Intelligence + Meta-Learning + Factory Eval + Brain

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| I1 | Intelligence engine (Phase C) | `engines/intelligence/{dynamic_selector,market_regime,master_bot_builder,strategy_intelligence,portfolio_intelligence,explainability}.py` + `/api/intelligence/*` | **PR** | **Reuse** |
| I2 | Brain engine (Phase F) | `engines/brain/{brain,policy,scorer,signals,risk_budget,regime_transition,execution_quality,config,types}.py` + `/api/brain/*` | **PR** | **Reuse** |
| I3 | Market Intelligence (Phase G) | `engines/market_intel_engine/{intelligence,change_detection,brain_bridge,ledger,observers/}.py` — 8 observers | **PR** — indexes bootstrap when `MI_ENABLED=true` | **Reuse** |
| I4 | Meta-Learning (Phase I) | `engines/meta_learning/{engine,collectors/,evaluators/,applier,proposers,ranker,ledger,explainability,stats,types,config}.py` + `/api/meta-learning/*` | **PR — OBSERVE mode default** | **Reuse** |
| I5 | Factory Evaluation (Phase J) | `engines/factory_eval/{engine,collectors,evaluators,ledger,explainability,config,types}.py` + `/api/factory-eval/*` | **PR** | **Reuse** |
| I6 | AI Workforce (provider health + router + telemetry + circuit breaker + scorer) | `engines/ai_workforce/*` + `/api/ai-workforce/*` | **PR** | **Reuse** |
| I7 | Meta-Learning ↔ pipeline collectors | `meta_learning/collectors/{brain_decisions,execution_realised,market_intelligence,portfolio}.py` | **PR** | **Reuse** |

---

## Section J · Factory Supervisor (Phase 5 — recovered, dormant)

Recovered fully but not yet wired into the running factory-runner.

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| J1 | Fleet registry + worker runtime/scheduler | `factory_supervisor/{fleet_registry,worker_runtime,worker_scheduler,workload}.py` | **MC** | **Extend** (wire via factory-runner activation) |
| J2 | Copilot (context / operational / advanced) | `factory_supervisor/copilot_{context,operational,advanced}.py` | **MC** | **Extend** |
| J3 | Architect advisor + recommendation engine + auto-learning | `factory_supervisor/{architect_advisor,recommendation_engine,auto_learning,eligibility_signals}.py` | **MC** | **Extend** |
| J4 | Notification center + defer queue + submission dispatcher + remote transport | `factory_supervisor/{notification_center,defer_queue,submission_dispatcher,remote_transport}.py` | **MC** | **Extend** |
| J5 | Supervisor lock + heartbeat + events + system state view | `factory_supervisor/{supervisor_lock,supervisor_heartbeat,supervisor_events,system_state_view}.py` | **MC** | **Extend** |
| J6 | FAG proposals (flag governance) + routing policy + LLM adapter base | `factory_supervisor/{fag_proposals,routing_policy,llm_adapter_base}.py` | **MC** | **Extend** |

Once wired, J1–J6 activate the sibling factory-runner as the
CPU-heavy orchestrator.

---

## Section K · Governance, Safety, Observability

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| K1 | Activation governance + journal | `engines/{activation_governance,activation_journal}.py` | **PR** | **Reuse** |
| K2 | Audit log writer + boot audit emitter | `engines/audit_log_writer.py`, `tests/test_boot_audit_emitter.py` | **PR** | **Reuse** |
| K3 | Feature flags + overrides | `engines/{feature_flags,flag_overrides}.py` + `/api/admin/flag-governance` | **PR** | **Reuse** |
| K4 | Safety engine + injector + rule enforcement/engine | `engines/{safety_engine,safety_injector,rule_enforcement,rule_engine}.py` | **PR** | **Reuse** |
| K5 | Admission controller + adaptive concurrency / cooldown / pool sizer | `engines/{admission_controller,admission_wrapper,adaptive_concurrency,adaptive_cooldown,adaptive_pool_sizer}.py` | **PR** | **Reuse** |
| K6 | COE (Coordinated Ops Engine) + COE-γ + pressure middleware + metrics router | `engines/coe/`, `coe_gamma/`, `coe_metrics_router.py`, `coe_pressure_middleware.py` | **PR** | **Reuse** |
| K7 | CTS (Universal Health Contract subsystem) | `engines/cts/` | **PR** | **Reuse** |
| K8 | Monitoring + alert bridges + engine + subsystem health router | `engines/{monitoring_engine,monitoring_alert_bridge,alert_engine,subsystem_health_router}.py` | **PR** | **Reuse** |
| K9 | Ecosystem maturity + observability | `engines/{ecosystem_maturity,ecosystem_observability}.py` | **PR** | **Reuse** |
| K10 | Research lineage | `engines/research_lineage.py` + `/api/research-lineage/*` | **PR** | **Reuse** |

---

## Section L · Infrastructure Primitives

| # | Subsystem | Files | Status | Recommendation |
|---|-----------|-------|--------|----------------|
| L1 | CPU pool + IO pool + queue pressure | `engines/{cpu_pool,io_pool,queue_pressure}.py` | **PR** | **Reuse** |
| L2 | Host capability + compute probe | `engines/{host_capability,compute_probe}.py` | **PR** | **Reuse** |
| L3 | Readiness engine | `engines/readiness_engine.py` + `/api/admin/readiness` | **PR** | **Reuse** |
| L4 | Deployment extras + factory-runner heartbeat | `engines/{deployment_extras,factory_runner_heartbeat}.py` | **PR** | **Reuse** |
| L5 | LLM config + runner | `engines/{llm_config,llm_runner}.py` + `/api/llm-diagnostics`, `/api/llm-health` | **PR** | **Reuse** |
| L6 | DB indexes + advisory lock + event continuation | `engines/{db,db_indexes,advisory_lock,event_continuation}.py` | **PR** | **Reuse** |
| L7 | Env priority + persistence adapters + runner registry/router/token rotator | `engines/{env_priority,persistence_adapters,runner_registry,runner_router,runner_token_rotator,runner_account_migration}.py` | **PR** | **Reuse** |

---

## Section M · Frontend Consumption Surfaces (`frontend/src/os/`)

Non-exhaustive — captured to lock the read-side contract:

| # | Surface | Backs onto |
|---|---------|-----------|
| M1 | **Strategy Passport** (detail) | `strategy_memory`, `strategy_lifecycle`, `research_lineage`, `pipeline_logs`, `learning`, `factory_eval` |
| M2 | **Approvals Modal + Timeline Shim** (§12/§13) | client-side session store today; wired to swap into `POST /api/timeline/events` post-freeze |
| M3 | **Strategy Lab** | strategy generation stack + `POST /api/knowledge/nearest` |
| M4 | **Strategy Pipeline** | `/api/strategies`, `/api/knowledge/champions`, `/api/knowledge/statistics` |
| M5 | **Coverage · Market Data** | `/api/data/coverage`, market universe + BI5 |
| M6 | **Datasets · Optimization · Validation** | data engine, optimization engines, validation report |
| M7 | Mission Control shell (`CommandShell`, `TopTabBar`, `LifecycleRail`, `StatusRail`, `AuthGate`, `CmdKPalette`, `FactoryWalkthrough`) | dashboard summary + readiness |

Auth stack `E2_AUTHENTICATION_EXPERIENCE.md` and the design bible
(`FRONTEND_DESIGN_BIBLE_V2_1.md`) are the frozen consumer contracts.

---

## Section N · Tests already available

| Group | Count | Coverage |
|-------|-------|----------|
| `backend/tests/*` (Phase-1 core + v1.2.0-alpha2 phases A–J) | 50 files | Auth · knowledge · CTS · learning · dedup · migration · workload · queue · budget · reservations · trust scorer · retro score · promote bridge · connectors · compose image tags · route split · phase-a…j suites |
| `backend/legacy/tests/*` | 190+ files | Every module — auto-factory, cbot, challenge sim, execution, portfolio, master-bot, mutation, optimization, prop-firm, walk-forward, BI5, GA integration, phase 4–30, portfolio, monitoring |
| `backend/scripts/paper_flow_drill.py` + `tier5_validation.py` | 2 scripts | Live-broker validation (24h/72h paper drills), 100/500/1000-order flows |
| `Makefile tiered pyramid` | 5 tiers | commit / hourly / daily / pre-release / prod validation |

**Bottom line:** the automated regression pyramid already exceeds what
most greenfield builds ever produce. Every subsystem below has at
least one associated test; several have dozens.

---

## Section O · Roll-up counts

- **Public API endpoints:** 497 (docs: `docs/acceptance_v1_1/API_INVENTORY.md`).
- **Engines:** 169 modules under `legacy/engines/` + 5 under `app/`.
- **Legacy routers:** 83 preserved v01 routers.
- **DB collections in active use (approx.):** 60+ across `strategy_factory_v1` and the isolated `strategy_knowledge_base`.
- **Schedulers:** 3 tiers (learning → continuous → orchestrator) + auto-scheduler + BI5 weekly + auto-data-maintainer.
- **Broker adapters:** paper (live) + cTrader (scaffolded).
- **Providers via VIE:** 6 (OpenAI, Anthropic, Gemini, DeepSeek, Groq, Kimi).

---

## Section P · Global recommendation summary

- **Reuse:** almost everything under `app/` and `legacy/engines/` — the
  factory is a decade-scale asset base.
- **Extend (short list):** embedding similarity backend (B5), KB
  migration spec execution (B7), UKIE domain/connector wiring (B8),
  Factory Supervisor activation via factory-runner (C7 + J1–J6),
  cTrader broker adapter (H3).
- **Refine:** Phase-0 runner stub (A10 → swap for recovered impl).
- **Replace:** nothing.
- **Build New:** nothing at the subsystem level. Only new
  compositions of existing capabilities.

Full mapping of each recommendation onto the eight future modules is
in `docs/GAP_ANALYSIS.md`; module wiring is in
`docs/DEPENDENCY_MAP.md`; production sequencing is in
`docs/IMPLEMENTATION_ROADMAP.md`; the 24×7 factory readiness view is
in `docs/AUTONOMOUS_FACTORY_READINESS.md`.
