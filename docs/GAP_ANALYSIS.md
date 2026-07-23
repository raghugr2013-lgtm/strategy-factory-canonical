# Strategy Factory — Gap Analysis

**Companion to:** `docs/CAPABILITY_INVENTORY.md`.
**Method:** For each future module in the long-term vision, list the
existing capabilities that already satisfy the requirement and the
delta that is still open. **Recommendation column names EXACTLY ONE
action per row.**

Recommendation grammar (borrowed from the Capability Inventory):
Reuse · Refine · Extend · Replace · Build New.

---

## Global reuse principle

> Anything already implemented is preferred over anything that has to be
> written. Every gap in this document is a delta on top of a specific
> existing subsystem — never a greenfield build unless the "Existing
> support" column is literally empty.

Every "Missing" cell below has been double-checked against
`docs/CAPABILITY_INVENTORY.md` — items listed as Missing are the ones
we could not find under `backend/app/` or `backend/legacy/`.

---

## 1 · Historical Knowledge Base

**Vision:** A read-only, learning-only corpus of every historical
strategy, with sub-second similarity search, canonical family lookup,
and lifecycle-safe re-insertion of KB rows as fresh candidates.

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Read-only DB with row-level guardrails | ✅ `KnowledgeRepository` (B1) + `StrategyRepository` (B2) | — | **Reuse** |
| Isolated Mongo DB (physically separate from production) | ✅ `strategy_knowledge_base` (`KNOWLEDGE_DB_NAME`) | — | **Reuse** |
| Historical corpus (140 rows imported) | ✅ Phase 1.5 ingestion complete; `champions` collection populated | — | **Reuse** |
| Canonical hashing + family search | ✅ `app/knowledge/canonical.py` + `/families/<hash>` (B3, B6) | — | **Reuse** |
| Six-dimensional evaluation from legacy metrics | ✅ `app/knowledge/evaluation.py` (B4) | — | **Reuse** |
| Similarity search — rule-based | ✅ `RuleBasedSimilarity` (B5) | — | **Reuse** |
| Similarity search — embedding-backed | ⚠️ `EmbeddingSimilarityStub` present (B5) | Implement embedding backend (choose sentence-transformers or provider API); wire behind existing contract | **Extend** |
| New corpus ingestion (post-launch imports) | ⚠️ `docs/KB_MIGRATION_SPEC.md v0.1` (planning-only) | Execute Phases M0–M3 of the spec after user answers the 10 §11 questions | **Extend** |
| UKIE domain registry + connectors | ⚠️ `engines/knowledge/router` (B8) flag-gated | Register KB migration domains + connectors; enable via `UKIE_DOMAIN_REGISTRY_ENABLED` | **Extend** |
| Re-insertion as cold candidate through the full framework pipeline | ✅ Every match carries `eligible_for_deploy: False` + `readiness_ceiling: PENDING_VALIDATION`; the `POST /api/strategies` path is the canonical re-entry | — | **Reuse** |

**Net gap:** 3 extensions (embedding, migration execution, UKIE
domain wiring). Zero replacements. Zero greenfield builds.

---

## 2 · Autonomous Research Factory (24×7)

**Vision:** A self-directed factory that runs without human input,
generates strategies, backtests, mutates, validates, promotes, and
retires — while an operator only reviews approvals.

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Multi-tier scheduler | ✅ Learning · Continuous · Orchestrator (C1–C3); orchestrator supersedes both | — | **Reuse** |
| Task registry (backtest, mutation, optimization, ranking, validation, strategy_generate, learning_cycle, market_data_topup, knowledge_index_refresh, market_intelligence_refresh, master_bot_bundle_refresh, meta_learning_evaluation, factory_evaluation, self_rebuild, bi5_realism_sweep, broker_health_check, execution_attribution) | ✅ 17 tasks registered (C4) | — | **Reuse** |
| USD budget guardrail across restarts | ✅ Budget tracker + boot rehydration (C5) | — | **Reuse** |
| Outcome-event ledger | ✅ Learning ledger (C1) | — | **Reuse** |
| Restart-preserved schedulers subordinated to orchestrator | ✅ auto-scheduler, orchestrator-scheduler, auto-data-maintainer (C6) | — | **Reuse** |
| Sibling process for CPU-heavy work | ⚠️ Container runs Phase-0 stub (A10); recovered impl exists (`legacy/factory_runner.py`) | Wire the recovered runner behind `FACTORY_RUNNER_OWNS_SCHEDULERS=true` — swap the entrypoint from `app.runner` to `legacy.factory_runner` | **Refine** |
| Factory Supervisor (fleet registry, worker runtime, copilot, notification center, submission dispatcher, defer queue) | ⚠️ Full recovery under `legacy/engines/factory_supervisor/*` (J1–J6) | Activate through the wired sibling runner; connect to orchestrator's task queue | **Extend** |
| Recommendation engine + architect advisor + auto-learning | ✅ `factory_supervisor/{recommendation_engine,architect_advisor,auto_learning}.py` (J3) | Same activation as above | **Extend** |
| Flag governance (FAG proposals) | ✅ `factory_supervisor/fag_proposals.py` (J6) | Same activation as above | **Extend** |
| Governance approvals surface | ✅ Approvals Modal + Timeline shim (M2); executor swaps in post-freeze | Wire `executor` argument to real endpoints as freeze lifts (per Slice γ handover §4) | **Extend** |
| OBSERVE mode default for all mutating decisions | ✅ Meta-Learning defaults to OBSERVE (I4); Factory Eval defaults to OBSERVE (I5) | — | **Reuse** |

**Net gap:** wire Factory Supervisor (J1–J6) into the sibling
factory-runner (C7), then flip `ORCHESTRATOR_ENABLED=true` in
production. No new engines.

---

## 3 · Strategy Explorer

**Vision:** A live-updating browser over every strategy in the
Factory — champions, drafts, backtested, deployed, retired — with
lineage, timeline, and re-insert-as-cold action.

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Strategy read API (production-safe) | ✅ `/api/strategies` (A6) + `StrategyRepository` (B2) | — | **Reuse** |
| Champion / family listings | ✅ `/api/knowledge/champions`, `/families/<hash>`, `/statistics` (B6) | — | **Reuse** |
| Explorer surface — legacy `/strategies/explorer` | ✅ `strategy_memory` router (mounted at priority) | — | **Reuse** |
| Strategy Passport (per-strategy detail) | ✅ Frontend Slice β + backing routers (M1) | — | **Reuse** |
| Lineage timeline | ✅ Research Lineage (K10) + Timeline shim (M2) | wire real Timeline endpoint post-freeze | **Extend** |
| Filters by regime / prop-firm / pair / timeframe | ✅ market universe + prop-firm engines expose the tags | — | **Reuse** |
| Similarity-driven discovery from a KB row | ✅ `/api/knowledge/nearest` (B6) | — | **Reuse** |
| Re-insert-as-cold action from Explorer | ✅ Path is `POST /api/strategies` (per KB guardrails contract) | Add the UI action; backend already correct | **Extend** |

**Net gap:** frontend wiring on top of an already-complete backend.

---

## 4 · Strategy Registry

**Vision:** Single canonical index of every strategy the Factory has
ever known — with hash-based identity, lifecycle state, deployment
eligibility, and audit trail.

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Canonical hash identity | ✅ `app/knowledge/canonical.py` (B3) | — | **Reuse** |
| Lifecycle state machine | ✅ `engines/strategy_lifecycle.py` + `phase26_5` tests | — | **Reuse** |
| Deployment eligibility guardrails | ✅ `eligible_for_deploy` row-level flag + `StrategyRepository` (B2) | — | **Reuse** |
| Audit trail | ✅ Activation journal (K1) + audit log writer (K2) | — | **Reuse** |
| Library API | ✅ `engines/strategy_library.py` + `/api/library/*` via `dashboard_route` side-effect | — | **Reuse** |
| Cross-DB registry (production ∪ KB view) | ✅ `strategies` + `strategy_kb_view` collections | — | **Reuse** |
| Registry dashboard surface | ✅ Strategy Pipeline surface (M4) + Strategy Passport (M1) | — | **Reuse** |

**Net gap:** none at the subsystem level.

---

## 5 · Master Bot

**Vision:** Executable multi-strategy bundle that runs on paper or
live broker, packaged with a definition/diff/export contract.

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Master bot engine | ✅ `engines/master_bot_engine.py` (G4) | — | **Reuse** |
| Definition + diff + export | ✅ `master_bot_{definition,diff,export,pack}.py` (G4) | — | **Reuse** |
| Bundle refresh scheduler task | ✅ `orchestrator/tasks/master_bot_bundle_refresh.py` (C4) | — | **Reuse** |
| Ranker (BI5-signal aware) | ✅ `master_bot_ranker.py` (G4) + `test_master_bot_ranker_bi5_signals.py` | — | **Reuse** |
| Deployment surface | ✅ `master_bot_deployment.py` + `/api/master-bot/*` | — | **Reuse** |
| Intelligence integration | ✅ `intelligence/master_bot_builder.py` (I1) | — | **Reuse** |

**Net gap:** none.

---

## 6 · Paper Trading

**Vision:** Full-fidelity broker parity, immutable journal, replayable
outcomes, deviation alerts vs backtest.

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Paper execution engine | ✅ `paper_execution_engine.py` (H1) | — | **Reuse** |
| Deviation alerts vs backtest | ✅ `paper_execution_alert_bridge.py` (H1) + `test_paper_backtest_alignment.py` + `test_paper_deviation_alerts.py` | — | **Reuse** |
| Immutable journal + replay | ✅ Execution engine journal + replay (H2) | — | **Reuse** |
| Broker adapter — paper | ✅ `execution/broker/paper.py` (H3) | — | **Reuse** |
| Broker adapter — live | ⚠️ `execution/broker/ctrader/` scaffolded (H3) | Finish cTrader adapter (or add another) | **Extend** |
| Broker health monitor | ✅ `execution/broker_health.py` (H2) + `broker_health_check` task (C4) | — | **Reuse** |
| Slippage + realism defaults | ✅ `slippage_model.py`, `execution_realism_defaults.py` (H5) | — | **Reuse** |
| Ledger backend abstraction (memory + mongo) | ✅ H4 | — | **Reuse** |
| Quality + attribution + risk monitor | ✅ H2 | — | **Reuse** |
| Live tracking dashboard | ✅ `live_tracking_engine.py` (H6) + `/api/live-tracking/*` | — | **Reuse** |
| Paper broker validation (24h/72h drills) | ✅ `scripts/tier5_validation.py`, `paper_flow_drill.py` | — | **Reuse** |

**Net gap:** one broker adapter to finish.

---

## 7 · Export Engine

**Vision:** Emit any strategy or master-bot bundle as executable code
for external platforms (cTrader C# today; extensible to MT4/MT5).

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Strategy IR → cBot C# transpiler | ✅ `cbot_engine/ir_transpiler.py` + `ir_templates.py` (D3) | — | **Reuse** |
| Parity simulator + trade parity | ✅ `cbot_engine/ir_parity_simulator.py`, `engines/cbot_trade_parity.py` (D3) | — | **Reuse** |
| Auto-fix + log diagnostic | ✅ `engines/{cbot_autofix,cbot_log_diagnostic}.py` (D3) | — | **Reuse** |
| Master-bot pack + diff + export | ✅ `master_bot_{pack,diff,export}.py` (G4) | — | **Reuse** |
| Export surface | ✅ `/api/cbot/*`, `/api/cbot-parity/*`, `/api/master-bot/export`, and (via dashboard_route side-effect) `/cbot/build-reliable` | — | **Reuse** |
| Additional platform emitters (MT4/MT5/other) | ⚠️ None | Only if a business need materialises — architecturally an IR emitter alongside `ir_transpiler.py` | **Build New** (only when required) |

**Net gap:** MT4/MT5 emitters (business-driven, not architecture-driven).

---

## 8 · Human Workspace

**Vision:** The operator-facing OS — Command Shell, Approvals inbox,
Timeline, Passport, Palette, and a role-aware navigation frame.

| Requirement | Existing support | Delta | Recommendation |
|-------------|-------------------|-------|----------------|
| Command Shell + TopTabBar + LifecycleRail + StatusRail | ✅ `src/os/shell/*` + `src/os/rails/*` (M7) | — | **Reuse** |
| AuthGate + role-aware routing | ✅ `src/os/shell/AuthGate.jsx` + `/api/auth/me` role integration (Slice 1 M6) | — | **Reuse** |
| Command Palette (⌘K) + Walkthrough | ✅ `CmdKPalette`, `FactoryWalkthrough` (M7) | Add Strategy Pipeline to jump list (PRD backlog P1) | **Extend** |
| Approvals modal (§12) | ✅ `ApprovalsModal.jsx` (M2, Slice γ) | Wire real executor when freeze lifts | **Extend** |
| Timeline shim (§13) | ✅ `adapters/timelineShim.js` (M2) | Swap persistence for `POST /api/timeline/events` post-freeze | **Extend** |
| Strategy Passport detail view | ✅ Slice β (M1) | — | **Reuse** |
| Approvals inbox on Command surface | ⚠️ Consumer not yet built; producer live | Read from `useTimelineEvents({eventPrefix:'operator_'})` — zero backend work (PRD backlog P1, Slice δ) | **Extend** |
| Notification center | ✅ `factory_supervisor/notification_center.py` (J4) | Wire once supervisor activates | **Extend** |
| Design token system + interactive-element `data-testid` invariant | ✅ Frozen at `memory/FRONTEND_DESIGN_BIBLE_V2_1.md` + `scripts/check-testids.js` | — | **Reuse** |
| Personalization modes (D6) + role-aware nav (E5) | ✅ Design freeze documents (`memory/D6_*`, `memory/E5_*`) | Ship remaining modes progressively | **Extend** |

**Net gap:** frontend-only extensions; no new backend services.

---

## Consolidated gap ledger

| Delta | Source | Kind | Recommendation |
|-------|--------|------|----------------|
| Embedding-backed similarity | KB (§1) | backend | **Extend** — implement behind existing stub |
| KB migration spec execution (M0 → M3) | KB (§1) | backend + ops | **Extend** — after `KB_MIGRATION_SPEC.md v0.1` sign-off |
| UKIE domain / connector registration | KB (§1) | backend | **Extend** — flag-gated router already mounted |
| Wire recovered `legacy.factory_runner` into container | Autonomous Factory (§2) | ops | **Refine** — one entrypoint swap |
| Activate Factory Supervisor (J1–J6) | Autonomous Factory (§2) | backend | **Extend** — code exists, needs runtime hook-up |
| Frontend re-insert-as-cold action | Strategy Explorer (§3) | frontend | **Extend** |
| Real Timeline endpoint consumption swap | Explorer + Workspace (§3, §8) | frontend | **Extend** — one-line shim swap |
| cTrader / additional broker adapter | Paper Trading (§6) | backend | **Extend** |
| MT4/MT5 emitters | Export Engine (§7) | backend | **Build New** — only when demand appears |
| Approvals inbox on Command surface | Human Workspace (§8) | frontend | **Extend** |
| Command Palette · Strategy Pipeline entry | Human Workspace (§8) | frontend | **Extend** — trivial |

**Total:** 10 Extend · 1 Refine · 1 Build New (deferred).
Zero Replace. Zero Missing critical subsystems.

The rest of the roadmap is composition of existing capabilities.
