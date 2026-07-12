# Stage 2 Activation Guide — Strategy Factory v1.0.0

**Purpose:** deterministic implementation roadmap for activating the preserved Strategy Factory capabilities. Every module in this guide is already on disk — activation is wiring, not writing. Follow this doc and Stage 2 completes without another architecture audit.

**Baseline assumption:** Strategy Factory v1.0.0 is deployed on the Contabo VPS at `https://strategy.coinnike.com`. `./infra/scripts/health.sh` passes green. From here, we activate one pillar at a time.

**Foundation flag:** every activation is gated by the env var `ENABLE_LEGACY_ROUTERS=true` (defaults to false in `.env.example`). Set it once in `.env`, then per-pillar router mounts are added incrementally to `app/main.py`. Rebuild + restart backend after each mount.

---

## 0. One-time Stage 2 foundation

Before activating any specific pillar, do the following one-time setup. **This is not module work — it is the substrate every pillar depends on.**

### 0.1 Install legacy Python deps in the backend image

Edit `backend/Dockerfile`, add after the existing `pip install -r requirements.txt`:

```dockerfile
COPY legacy/requirements.legacy.txt legacy/
RUN pip install -r legacy/requirements.legacy.txt
```

`backend/legacy/requirements.legacy.txt` includes: `pandas`, `numpy`, `apscheduler`, `dukascopy-python`, `pdfplumber`, `pypdf`, `reportlab`, `beautifulsoup4`, `lxml`, `psutil`.

### 0.2 Add the feature flag

In `.env` on the VPS:
```env
ENABLE_LEGACY_ROUTERS=true
```

Add to `docker-compose.prod.yml` → `factory-backend.environment`:
```yaml
ENABLE_LEGACY_ROUTERS: ${ENABLE_LEGACY_ROUTERS:-false}
```

In `backend/app/main.py::create_app`, add near the router mounts:
```python
import os
if os.getenv("ENABLE_LEGACY_ROUTERS", "").lower() == "true":
    _mount_legacy_routers(app)   # defined per-pillar below
```

### 0.3 Import v01 mongodump (optional — for the 14-strategy cohort)

```bash
docker cp mongodb-dump-20260614_151752.archive.gz factory-backend:/tmp/
docker exec factory-backend sh -c 'mongorestore --uri "$MONGO_URL" \
  --archive=/tmp/mongodb-dump-20260614_151752.archive.gz --gzip \
  --nsFrom="test_database.*" --nsTo="strategy_factory.*"'
```

### 0.4 LLM call-site migration (one-time, ~6 files)

Every legacy engine that reads `EMERGENT_LLM_KEY` directly must be swapped to call VIE. Pattern:

```python
# BEFORE (in legacy/engines/*.py)
import os
_KEY = os.getenv("EMERGENT_LLM_KEY")
response = some_provider_sdk.call(_KEY, prompt=...)

# AFTER
from app.vie.client import get_vie
result = await get_vie().generate(prompt=..., task="research")
```

Files that need this migration (grep-verified):
- `backend/legacy/engines/llm_config.py`
- `backend/legacy/engines/llm_runner.py`
- `backend/legacy/engines/ai_orchestrator.py`
- `backend/legacy/engines/agent_advisor.py`
- `backend/legacy/engines/strategy_description.py`
- `backend/legacy/engines/analysis_engine.py`

Effort: ~2 hours total (mechanical substitution, patterns are identical across files).

### 0.5 Sibling scheduler container (only needed for Improvement + Master Bot pillars)

Add to `infra/compose/docker-compose.prod.yml` (see `docs/STAGE2_PRESERVATION.md §3.2` for the exact YAML block).

---

## 1. Module activation matrix (at-a-glance)

Ordered by recommended activation sequence.

| # | Pillar | Status | Effort (dev-days) | Backend routers | Frontend pages | Deps beyond §0 |
|---|---|---|---:|---|---|---|
| 1 | Diagnostic Surfaces | Preserved | 0.5 | `data_health`, `llm_health`, `orchestrator_heartbeat`, `diag_bi5_health` | (dashboard tiles) | none |
| 2 | Research Engine | Preserved | 2 | `market_intelligence`, `research_lineage`, `admin_market_universe` | Research page (exists) + Universe explorer | VIE (already active) |
| 3 | Strategy Library | Preserved | 2 | `dashboard`, `dashboard_route`, `governance` | Library page + Governance suite | none |
| 4 | Strategy Generation | Preserved | 4 | `strategies` (legacy), `auto_factory`, `gem_factory` | Auto Factory + Strategy Explorer + Details | LLM migration §0.4 |
| 5 | Validation | Preserved | 2 | validation (embedded in `strategies.py`, extract to `validation.py`) | Validation Panel + Rules Review | numpy, pandas |
| 6 | Backtesting | Preserved | 5 | `data`, `data_health`, `data_maintenance`, `bi5_ingest`, `bi5_realism`, `bi5_certification`, `bi5_cert_sweep`, `ingestion`, `regime` | Backtest Panel + Data Availability + BI5 Health | numpy, pandas, dukascopy-python + `factory_bi5` volume |
| 7 | Optimization | Preserved | 3 | `optimization` | Optimization Panel | numpy, pandas |
| 8 | AI Explanation | Preserved | 2 | `llm_diagnostics`, `llm_health` | Analysis Panel + Description viewer | LLM migration §0.4 |
| 9 | Strategy Improvement | Preserved | 4 | `mutation`, `auto_mutation`, `phase12_tuning` | Auto-Mutation Runner + Mutation Compile | apscheduler + sibling scheduler §0.5 |
| 10 | Strategy Comparison | Preserved | 3 | `cbot`, `cbot_parity` | Comparison + Parity Cert + cBot Panel | cbot_engine package |
| 11 | Master Bot Builder | Preserved | 5 | `master_bot`, `deployment`, `portfolio`, `portfolio_builder`, `portfolio_intelligence`, `trade_runner` | Master Bot Dashboard + Portfolio Builder | apscheduler + sibling scheduler §0.5 |
| 12 | Strategy Dossier | Preserved | 3 | `strategy_memory`, `lifecycle` | Dossier page (compose from panels) | none |
| 13 | Automated Valuation | Preserved | 2 | `readiness` (expand from 24-LOC shim) | Readiness Panel + Deployment Readiness Card | numpy |
| 14 | Export Framework | Preserved | 2 | (via `master_bot` + `deployment`) | (via Master Bot Compile Panel) | cbot_engine, asf package |

**Total effort estimate:** ~40 dev-days for full activation of all 13 pillars in the order above. The critical path is Research → Library → Generation → Validation → Backtesting because they unlock every other pillar.

---

## 2. Per-module deep-dive

For each module: **exact paths · status · deps · routers · UI · effort · activation order · user-visible outcome · step-by-step activation**.

### 2.1 Research Engine

- **Repository path:**
  - Engines: `backend/legacy/engines/{market_universe,market_universe_adapter,market_universe_audit,market_intelligence,research_lineage}.py` + `backend/legacy/engines/seed/market_universe_seed.py`
  - Routers: `backend/legacy/api/{market_intelligence,research_lineage,admin_market_universe}.py`
  - Frontend components: `frontend/legacy/src/components/{StrategyIngestionCard,MarketDataWorkbench}.jsx`
- **Current status:** Preserved but inactive (engines Fully implemented — 413 + 939 + 343 LOC)
- **Runtime dependencies:** VIE (already active); no new libs
- **API routers required (to mount):**
  - `POST /api/legacy/research/query` (already active in Phase 1 as `/api/research/query`)
  - `POST /api/legacy/market-intelligence/*`
  - `POST /api/legacy/research-lineage/*`
  - `GET /api/legacy/admin/market-universe/*`
- **Frontend pages required:**
  - Existing Phase 1 `pages/ResearchPage.jsx` — extend to show lineage timeline
  - Port `MarketDataWorkbench.jsx` from `frontend/legacy/`
- **Estimated wiring effort:** **2 dev-days**
- **Activation order:** **#2** (after diagnostic surfaces)
- **Expected user-visible functionality after activation:**
  - Researchers can query the Research Engine with lineage tracking (who asked what when, and what conclusions were drawn)
  - Admins can inspect and curate the market universe (symbols, timeframes, prop-firm rulesets)
  - Every research query persists with the exact VIE provider + model that served it
- **Activation steps:**
  1. Complete §0.4 LLM migration for `market_intelligence.py`, `research_lineage.py`
  2. Add to `app/main.py::_mount_legacy_routers`:
     ```python
     from legacy.api import market_intelligence, research_lineage, admin_market_universe
     app.include_router(market_intelligence.router, prefix="/api/legacy")
     app.include_router(research_lineage.router, prefix="/api/legacy")
     app.include_router(admin_market_universe.router, prefix="/api/legacy")
     ```
  3. Port `MarketDataWorkbench.jsx` into `frontend/src/pages/UniversePage.jsx`; add nav item
  4. Extend `pages/ResearchPage.jsx` to fetch `/api/legacy/research-lineage/{query_id}` after each query
  5. Verify: `curl -H "Auth: Bearer $TOK" $URL/api/legacy/market-intelligence/health` → 200

### 2.2 Strategy Generation

- **Repository path:**
  - Engines: `backend/legacy/engines/{strategy_engine,strategy_ir,strategy_ir_backfill,strategy_ir_builders,strategy_ir_renderer,auto_factory,auto_factory_engine,auto_factory_phase55,gem_factory_engine,code_generator,compile_engine}.py`
  - Ingestion subsystem: `backend/legacy/engines/strategy_ingestion/` (8 files: parser, normalizer, validator, injector, collector, ingestion_runner, tradingview_urls, __init__)
  - Routers: `backend/legacy/api/{strategies,auto_factory,gem_factory}.py`
  - Frontend components: `frontend/legacy/src/components/{AutoFactory,AutoFactoryPhase55,StrategyPanel,StrategyExplorer,SavedStrategies,StrategyDetailsPanel,StrategyDeepDivePanel,StrategyChartView}.js/.jsx`
- **Current status:** Preserved but inactive (engines Fully implemented — `strategy_engine.py` 882 LOC, `strategy_ir.py` 453 LOC, largest generation pipeline in the bundle)
- **Runtime dependencies:** LLM migration §0.4 for `strategy_engine.py` if it calls LLMs; no new external libs
- **API routers required:** `strategies` (legacy), `auto_factory`, `gem_factory`
- **Frontend pages required:**
  - Port `AutoFactory.js` → new `pages/AutoFactoryPage.jsx`
  - Port `StrategyExplorer.js` → new `pages/StrategyExplorerPage.jsx`
  - Extend existing `pages/StrategiesPage.jsx` with `StrategyDetailsPanel` + `StrategyDeepDivePanel` (right-drawer pattern)
- **Estimated wiring effort:** **4 dev-days**
- **Activation order:** **#4**
- **Expected user-visible functionality after activation:**
  - "Auto Factory" — one-click generation of candidate strategies from a prompt or market universe subset
  - "Gem Factory" — targeted mining of high-conviction strategies against specific asset/timeframe combos
  - Strategy Explorer — deep-drill into any candidate: IR tree, chart preview, description, backtest metrics
  - Ingestion pipeline (TradingView URL → normalized IR)
- **Activation steps:**
  1. Complete §0.4 for `strategy_engine.py`, `agent_advisor.py`, `strategy_description.py`
  2. Mount three legacy routers under `/api/legacy/*`
  3. Port `AutoFactory.js` + `StrategyExplorer.js`; wire to the new endpoints
  4. Add "Auto Factory" and "Strategy Explorer" to the sidebar nav (role: admin/developer/researcher)
  5. Smoke test: generate 5 candidate strategies via `POST /api/legacy/auto-factory/run`, verify they appear in the Library

### 2.3 Validation Engine

- **Repository path:**
  - Engines: `backend/legacy/engines/{validation_engine,validation_report,signal_quality,spread_analyzer,match_input_validator,rule_engine,rule_enforcement,tick_validator,calibration_framework}.py`
  - Routers: currently embedded in `legacy/api/strategies.py` — recommend extracting to a new `legacy/api/validation.py` for clarity
  - Frontend components: `frontend/legacy/src/components/{ValidationPanel,RulesReviewPanel}.js`
- **Current status:** Preserved but inactive (engines Fully implemented — `validation_engine.py` 351 LOC)
- **Runtime dependencies:** `numpy`, `pandas`
- **API routers required:** create `/api/legacy/validation/{run,report}` (extracted from `strategies.py`)
- **Frontend pages required:** Port `ValidationPanel.js` and `RulesReviewPanel.js` as a two-tab **Validation** section inside `pages/StrategiesPage.jsx` (drawer or dedicated route)
- **Estimated wiring effort:** **2 dev-days**
- **Activation order:** **#5**
- **Expected user-visible functionality after activation:**
  - Every strategy in the Library has a "Validate" action → runs `validation_engine` on it → produces a report with signal quality, spread analysis, rule enforcement violations
  - Batch validation for the whole library or a selected cohort
  - Rule Review panel where admins can add/edit validation rules
- **Activation steps:**
  1. Extract validation endpoints from `legacy/api/strategies.py` into `legacy/api/validation.py`
  2. Mount under `/api/legacy`
  3. Port UI panels
  4. Smoke test: pick a strategy → click Validate → report renders

### 2.4 Optimization Engine

- **Repository path:**
  - Engines: `backend/legacy/engines/{optimization_engine,optimization_portfolio_bridge,ga_optimizer,random_search_optimizer}.py`
  - Router: `backend/legacy/api/optimization.py`
  - Frontend components: `frontend/legacy/src/components/OptimizationPanel.js`
- **Current status:** Preserved but inactive (engines Fully implemented — 373 LOC)
- **Runtime dependencies:** `numpy`, `pandas`
- **API routers required:** `optimization`
- **Frontend pages required:** Port `OptimizationPanel.js` as a new tab in Strategy Details drawer OR standalone `pages/OptimizationPage.jsx`
- **Estimated wiring effort:** **3 dev-days**
- **Activation order:** **#7**
- **Expected user-visible functionality after activation:**
  - GA and random-search optimization of any strategy's parameter space
  - Progress streaming (see best-so-far metric over generations)
  - Optimization ↔ Portfolio bridge auto-populates the portfolio builder with the optimized survivors
- **Activation steps:**
  1. Mount `optimization` router
  2. Port `OptimizationPanel.js`
  3. Wire progress polling (or SSE if the router supports it)
  4. Smoke test: optimize a small strategy over 10 generations, confirm survivors appear

### 2.5 Backtesting Engine

- **Repository path:**
  - Engines: `backend/legacy/engines/{backtest_engine,backtest_pool,backtest_report,execution_simulator,execution_realism_defaults,slippage_model,walk_forward_engine,oos_holdout,monte_carlo_engine,regime_classifier,regime_performance}.py`
  - Data subsystem: `backend/legacy/data_engine/` (13 files) + BI5 certification suite: `bi5_certification.py`, `bi5_cert_sweep.py`, `bi5_cert_sweep_scheduler.py`, `bi5_maturity.py`, `bi5_realism.py`
  - BI5 scripts: `backend/legacy/scripts/bi5_*.py` (12 files)
  - Routers: `backend/legacy/api/{data,data_health,data_maintenance,bi5_ingest,bi5_realism,bi5_certification,bi5_cert_sweep,diag_bi5_health,ingestion,regime}.py`
  - Frontend components: `frontend/legacy/src/components/{BacktestPanel,DataAvailability,DataUpload,DataMaintenancePanel,Bi5CertPanel,BI5HealthPanel,IngestionHealthCard}.js/.jsx`
- **Current status:** Preserved but inactive (engines Fully implemented — `backtest_engine.py` at **1,748 LOC** is the largest engine in the bundle)
- **Runtime dependencies:** `pandas`, `numpy`, `dukascopy-python`, `psutil`, `apscheduler` (for cert sweep). Plus a persistent Docker volume `factory_bi5` for the tick archive.
- **API routers required:** all 10 listed above
- **Frontend pages required:**
  - New `pages/BacktestPage.jsx` composed from `BacktestPanel.js` + result viewer
  - New `pages/DataPage.jsx` composed from `DataAvailability.js` + `DataUpload.js` + `DataMaintenancePanel.js` + `IngestionHealthCard.jsx`
  - New `pages/DataHealthPage.jsx` for operators — `Bi5CertPanel.jsx` + `BI5HealthPanel.jsx`
- **Estimated wiring effort:** **5 dev-days** (biggest single activation; volume provisioning + backfill + UI work)
- **Activation order:** **#6**
- **Expected user-visible functionality after activation:**
  - Full backtesting: single run, walk-forward, out-of-sample holdout, Monte Carlo, regime-conditioned performance
  - BI5 tick archive management: view coverage, upload gaps, run backfill, certify quality
  - Ingestion health dashboard for operators
  - Regime classifier report per strategy
- **Activation steps:**
  1. Add `factory_bi5` named volume to `docker-compose.prod.yml`, mount at `/data/bi5` in the backend service, set `BI5_ARCHIVE_PATH=/data/bi5` env
  2. Run one-time BI5 backfill: `docker exec factory-backend python legacy/scripts/bi5_one_shot_backfill.py`
  3. Mount all 10 routers under `/api/legacy`
  4. Port all 3 new pages
  5. Enable BI5 cert sweep on the sibling scheduler (see §0.5)
  6. Smoke test: run a 1-year backtest on EURUSD H1 for one of the seeded strategies

### 2.6 AI Explanation Engine

- **Repository path:**
  - Engines: `backend/legacy/engines/{analysis_engine,agent_advisor,ai_orchestrator,llm_runner,llm_config,strategy_description}.py`
  - Routers: `backend/legacy/api/{llm_diagnostics,llm_health}.py`
  - Frontend components: `frontend/legacy/src/components/{StrategyAnalysis,StrategyDescription}.js`
- **Current status:** Preserved but inactive (engines Fully implemented — `ai_orchestrator.py` at 1,010 LOC is the second-largest engine after backtest)
- **Runtime dependencies:** VIE (§0.4 migration mandatory)
- **API routers required:** `llm_diagnostics`, `llm_health`
- **Frontend pages required:** Port both components as tabs inside Strategy Details drawer
- **Estimated wiring effort:** **2 dev-days** (mostly the §0.4 migration work already done)
- **Activation order:** **#8** (depends on Generation being live so there's something to explain)
- **Expected user-visible functionality after activation:**
  - Every strategy card shows an "Explain" action → returns a human-readable rationale (via VIE `task="explanation"`)
  - "Analyze" — deep pattern analysis on a strategy's live/backtest performance
  - Per-strategy Description auto-populates on ingestion or generation
- **Activation steps:**
  1. Verify §0.4 migration is complete for the 6 files listed there
  2. Mount `llm_diagnostics` + `llm_health`
  3. Port UI panels; wire them to `/api/legacy/llm-*` and the existing `/api/research/query`
  4. Smoke test: click Explain on a seeded strategy, verify VIE routes the call

### 2.7 Strategy Improvement Engine

- **Repository path:**
  - Engines: `backend/legacy/engines/{refinement_engine,strategy_refinement_engine,mutation_engine,auto_mutation_runner,mutation_pool,strategy_mutation,evolution_engine,phase12_tuning}.py`
  - Routers: `backend/legacy/api/{mutation,auto_mutation,phase12_tuning}.py`
  - Frontend components: `frontend/legacy/src/components/{AutoMutationRunner,MutateMasterBotCompile}.jsx`
- **Current status:** Preserved but inactive (engines Fully implemented — `mutation_engine.py` at **1,595 LOC** and 33 defs is the third-largest engine)
- **Runtime dependencies:** `apscheduler` (for `auto_mutation_runner`), sibling scheduler container §0.5
- **API routers required:** `mutation`, `auto_mutation`, `phase12_tuning`
- **Frontend pages required:** Port `AutoMutationRunner.js` as `pages/ImprovementPage.jsx`; embed `MutateMasterBotCompile.jsx` in Master Bot flow
- **Estimated wiring effort:** **4 dev-days**
- **Activation order:** **#9** (depends on Backtesting to score mutations)
- **Expected user-visible functionality after activation:**
  - "Improve" action on any strategy → runs mutation loop → returns ranked successors
  - Auto-Mutation Runner — scheduled continuous improvement of a strategy cohort
  - Phase 12 tuning — parameter-space refinement using historical priors
- **Activation steps:**
  1. Ensure sibling `factory-runner` container is up (§0.5)
  2. Mount 3 routers
  3. Port UI
  4. Configure APScheduler jobs (defaults are in `auto_mutation_runner.py`)
  5. Smoke test: launch mutation on a seed strategy, verify offspring appear ranked

### 2.8 Strategy Comparison Engine

- **Repository path:**
  - Engines: `backend/legacy/engines/{parity_certification,parity_drift_view,cbot_parity,cbot_trade_parity,htf_parity,r5_shadow_comparator}.py`
  - cBot IR subsystem: `backend/legacy/cbot_engine/` (6 files: generator, ir_emitter, ir_templates, ir_transpiler, ir_parity_simulator, __init__)
  - Autofix + diagnostics: `backend/legacy/engines/{cbot_autofix,cbot_log_diagnostic,cbot_pipeline}.py`
  - Routers: `backend/legacy/api/{cbot,cbot_parity}.py`
  - Frontend components: `frontend/legacy/src/components/{StrategyComparison,ParityCertificationCard,OperatorParityPanels,CbotPanel}.js/.jsx`
- **Current status:** Preserved but inactive (engines Fully implemented — `parity_certification.py` 618 LOC, `r5_shadow_comparator.py` 509 LOC)
- **Runtime dependencies:** cbot_engine package (imports internally); no external new deps
- **API routers required:** `cbot`, `cbot_parity`
- **Frontend pages required:** New `pages/ComparisonPage.jsx` composed from `StrategyComparison.js` + `ParityCertificationCard.jsx`; separate `pages/CbotPage.jsx` for the cBot IR viewer
- **Estimated wiring effort:** **3 dev-days**
- **Activation order:** **#10**
- **Expected user-visible functionality after activation:**
  - Side-by-side comparison of any two strategies (or a strategy vs. its cBot-transpiled version)
  - Parity certification report — confirms Python IR and cBot output produce identical trades on the same tick stream
  - R5 shadow comparator — regression harness for strategy changes
  - Operator parity view for live trading (paper vs live drift)
- **Activation steps:**
  1. Mount `cbot` + `cbot_parity`
  2. Port UI
  3. Add a "Compare" button on strategy cards that pushes both onto Comparison page
  4. Smoke test: transpile a Python IR to cBot, run parity cert → PASS expected

### 2.9 Master Bot Builder

- **Repository path:**
  - Master bot engines: `backend/legacy/engines/{master_bot_definition,master_bot_engine,master_bot_ranker,master_bot_pack,master_bot_export,master_bot_deployment,master_bot_diff}.py`
  - Portfolio engines: `backend/legacy/engines/{portfolio_engine,portfolio_builder_engine,portfolio_combiner,portfolio_intelligence_engine,portfolio_store,multi_asset_portfolio,multi_account_envelope}.py`
  - Runner infra: `backend/legacy/engines/{runner_registry,runner_router,runner_token_rotator,runner_account_migration,factory_runner_heartbeat,trade_runner_engine,live_tracking_engine}.py`
  - Routers: `backend/legacy/api/{master_bot,deployment,portfolio,portfolio_builder,portfolio_intelligence,trade_runner}.py`
  - Frontend components: `frontend/legacy/src/components/{MasterBotDashboard,MasterBotCompilePanel,PortfolioBuilder,PortfolioPanel,PortfolioIntelligence,MultiCycleRunner}.jsx/.js`
- **Current status:** Preserved but inactive (engines Fully implemented — `master_bot_engine.py` 662 LOC, `master_bot_ranker.py` 460 LOC, `master_bot_definition.py` 324 LOC; ~3,500 LOC across master_bot_* + ~3,000 LOC across portfolio_*)
- **Runtime dependencies:** `apscheduler`, sibling scheduler §0.5, ASF package (already preserved in `engines/asf/`)
- **API routers required:** all 6 listed above
- **Frontend pages required:** New `pages/MasterBotsPage.jsx` (dashboard + compile flow), new `pages/PortfolioPage.jsx` (builder + intelligence + panel)
- **Estimated wiring effort:** **5 dev-days**
- **Activation order:** **#11**
- **Expected user-visible functionality after activation:**
  - Build a Master Bot from a curated cohort of strategies (weight by rank, prop-firm rule set, asset mix)
  - Compile → produces an ASF package + optional cBot artefact
  - Deploy → assign to a trade runner (paper first, live later)
  - Multi-cycle runner: schedule automatic recompilation cadences
  - Portfolio Intelligence: correlation matrix, risk-of-ruin, expected value across the constituent bots
- **Activation steps:**
  1. Ensure sibling `factory-runner` is up
  2. Mount all 6 routers
  3. Port UI (~5 panels)
  4. Provision a paper trade runner (defaults exist in `runner_registry.py`)
  5. Smoke test: build a 3-strategy Master Bot, compile, deploy to paper, verify heartbeat

### 2.10 Strategy Dossier

- **Repository path:**
  - Engines: `backend/legacy/engines/{strategy_memory,strategy_profiler,strategy_lifecycle,lifecycle_decay}.py`
  - Routers: `backend/legacy/api/{strategy_memory,lifecycle}.py`
  - Frontend: no dedicated Dossier component in v01 — will be composed from `StrategyDetailsPanel.js` + `StrategyDeepDivePanel.js` + `StrategyChartView.js` + new memory viewer
- **Current status:** Preserved but inactive (engines Fully implemented — `strategy_memory.py` 1,146 LOC, `strategy_lifecycle.py` 963 LOC, `strategy_profiler.py` 499 LOC)
- **Runtime dependencies:** none beyond §0
- **API routers required:** `strategy_memory`, `lifecycle`
- **Frontend pages required:** New composite `pages/DossierPage.jsx` — full-page report on a single strategy pulling from memory + profiler + lifecycle + backtest + validation history
- **Estimated wiring effort:** **3 dev-days** (composition work; no new engine logic)
- **Activation order:** **#12**
- **Expected user-visible functionality after activation:**
  - Every strategy has a full-page Dossier: profile, lifecycle stage (candidate → certified → deployed → retired), decay analysis, memory timeline of every mutation/validation/backtest event, and export as PDF/JSON
- **Activation steps:**
  1. Mount 2 routers
  2. Compose the Dossier page from preserved sub-panels
  3. Add "Open Dossier" from every strategy card
  4. Smoke test: open Dossier on a certified strategy → sections populate

### 2.11 Automated Valuation

- **Repository path:**
  - Engines: `backend/legacy/engines/{expected_value,risk_of_ruin,pass_probability,readiness_engine,history_prior,safe_to_widen,widening_history,widening_proposal}.py`
  - Router: `backend/legacy/api/readiness.py` (current 24-LOC shim — expand to expose `expected_value`, `risk_of_ruin`, `pass_probability`)
  - Frontend components: `frontend/legacy/src/components/{ReadinessPanel,DeploymentReadinessCard}.js/.jsx`
- **Current status:** Preserved but inactive (engines Fully implemented — `expected_value.py` 447 LOC, `pass_probability.py` 380 LOC, `readiness_engine.py` 361 LOC, `risk_of_ruin.py` 315 LOC; router is Placeholder shim)
- **Runtime dependencies:** `numpy`
- **API routers required:** expand `readiness.py` (or add a new `valuation.py`)
- **Frontend pages required:** Port `ReadinessPanel.js` as a tab in Master Bot dashboard AND as a standalone `pages/ValuationPage.jsx`
- **Estimated wiring effort:** **2 dev-days**
- **Activation order:** **#13**
- **Expected user-visible functionality after activation:**
  - Every strategy/Master Bot gets an automated valuation report: expected value, risk of ruin, pass-probability against prop firm rules, deployment readiness score
  - Traffic-light gate on Master Bot deployment: green (safe to deploy) / amber (widen params) / red (block)
- **Activation steps:**
  1. Expand `legacy/api/readiness.py` from 24 LOC to a full CRUD surface over the 8 preserved engines
  2. Mount under `/api/legacy/valuation`
  3. Port UI
  4. Wire the traffic-light into Master Bot deployment flow

### 2.12 Strategy Library

- **Repository path:**
  - Engines: `backend/legacy/engines/{strategy_library,strategy_ranking_engine,ranking_engine,governance_universe,survivor_registry,live_tracking_engine,trade_runner_engine}.py`
  - Routers: `backend/legacy/api/{dashboard,dashboard_route,governance,phase4_matching}.py`
  - Frontend components: `frontend/legacy/src/components/{StrategyDashboard,SavedStrategies,LiveTrackingPanel,UniverseGovernancePanel,GovernanceAdminSuite,GovernanceCard,SymbolRegistryPanel}.js/.jsx`
- **Current status:** Preserved but inactive (engines Fully implemented — `strategy_library.py` 442 LOC, `governance_universe.py` 371 LOC, `strategy_ranking_engine.py` 248 LOC)
- **Runtime dependencies:** none beyond §0
- **API routers required:** `dashboard`, `dashboard_route`, `governance`, `phase4_matching`
- **Frontend pages required:** Extend existing `pages/StrategiesPage.jsx` into a full Library — add `SavedStrategies`, `LiveTrackingPanel`, `UniverseGovernancePanel`, `GovernanceAdminSuite` as tabs; separate `pages/GovernancePage.jsx` for admins
- **Estimated wiring effort:** **2 dev-days**
- **Activation order:** **#3**
- **Expected user-visible functionality after activation:**
  - Full-featured strategy library replacing the current basic list: rank-ordered, filterable by symbol/timeframe/status, live-tracking sub-view for deployed strategies
  - Governance suite: symbol registry, universe rulesets, survivor cohort management
- **Activation steps:**
  1. Import v01 mongodump cohort if desired (§0.3)
  2. Mount 4 routers
  3. Port UI tabs into `StrategiesPage.jsx`
  4. Add Governance page to admin sidebar
  5. Smoke test: seed cohort visible; rank change reflects in UI

### 2.13 Export Framework

- **Repository path:**
  - Engines: `backend/legacy/engines/{master_bot_export,code_generator,compile_engine,cbot_autofix,cbot_log_diagnostic,cbot_pipeline}.py`
  - cBot IR subsystem: `backend/legacy/cbot_engine/` (6 files)
  - ASF package: `backend/legacy/engines/asf/` (6 files: schema, package_reader, dedup_policy, calibration_snapshot, importer, __init__)
  - Deployment router: `backend/legacy/api/deployment.py`
  - Frontend: `frontend/legacy/src/components/MasterBotCompilePanel.jsx` handles the compile → export flow
- **Current status:** Preserved but inactive (engines Fully implemented)
- **Runtime dependencies:** cbot_engine package + ASF package (both preserved)
- **API routers required:** already covered by `master_bot` + `deployment` (Master Bot pillar). No new mount needed here — Export is activated as a side-effect of Master Bot.
- **Frontend pages required:** `MasterBotCompilePanel.jsx` exposes Export controls
- **Estimated wiring effort:** **2 dev-days** (incremental on top of Master Bot activation)
- **Activation order:** **#14 (concurrent with Master Bot)**
- **Expected user-visible functionality after activation:**
  - "Export" button on any Master Bot → produces:
    - ASF package (`.asf` archive with calibration snapshot, IR, metadata)
    - cBot source (auto-generated C# for cTrader)
    - JSON manifest for downstream deployment tooling
  - Download from browser; also stored in Mongo `master_bot_exports` collection
- **Activation steps:**
  1. No separate mount — comes with Master Bot (§2.9)
  2. Verify the Export tab in `MasterBotCompilePanel.jsx` calls `/api/legacy/master-bot/{id}/export?format=asf|cbot|json`
  3. Smoke test: compile a Master Bot, export as ASF, download, verify contents

### 2.14 Diagnostic Surfaces (foundation-level)

Not a full pillar but a smart first activation — safe read-only endpoints that Stage 2 depends on.

- **Repository path:**
  - Routers: `backend/legacy/api/{data_health,llm_health,orchestrator_heartbeat,diag_bi5_health,pipeline_logs,architect_view,ops_data_engine,operator_endpoint,queue_pressure}.py`
  - Frontend components: existing preview `pages/DashboardPage.jsx` extended
- **Current status:** Preserved but inactive
- **Runtime dependencies:** none beyond §0
- **Estimated wiring effort:** **0.5 dev-day**
- **Activation order:** **#1** (first, safest)
- **Expected user-visible functionality after activation:**
  - Dashboard tiles for every diagnostic surface: LLM health, data engine heartbeat, orchestrator state, pipeline logs

---

## 3. Full activation dependency graph

```
                          ┌──────────────────────────────────────────┐
                          │             SHARED PLATFORM              │
                          │  ┌────────┐ ┌────────┐ ┌────────────┐    │
                          │  │  VIE   │ │  Auth  │ │  Traefik   │    │
                          │  │ :8100  │ │ + RBAC │ │ (external) │    │
                          │  └────────┘ └────────┘ └────────────┘    │
                          │  ┌────────┐ ┌────────┐ ┌────────────┐    │
                          │  │ Mongo  │ │ Redis  │ │ Prometheus │    │
                          │  │(shared)│ │(shared)│ │Grafana/Loki│    │
                          │  └────────┘ └────────┘ └────────────┘    │
                          └────────┬─────────────────────────────────┘
                                   │
                     ┌─────────────┼───────────────┐
                     │             │               │
                ┌────▼────┐   ┌────▼──────┐   ┌────▼──────────┐
                │ Backend │   │ Frontend  │   │ factory-runner│
                │  :8001  │   │  nginx    │   │ (sibling)     │
                │ FastAPI │   │  React    │   │ APScheduler   │
                │         │   │           │   │ (from §0.5)   │
                └────┬────┘   └────┬──────┘   └────┬──────────┘
                     │             │               │
                     ▼             ▼               ▼
        ═══════════════════════════════════════════════════════════
        ═════════════ PILLAR ACTIVATION ORDER ═════════════════════
        ═══════════════════════════════════════════════════════════

  Step 1 (0.5d): ┌─────────────────────────────────────┐
  DIAGNOSTIC     │ data_health · llm_health            │
  SURFACES       │ orchestrator_heartbeat · pipeline   │
                 └──────────────┬──────────────────────┘
                                │
  Step 2 (2d):   ┌──────────────▼──────────────────────┐
  RESEARCH ◀─────┤ VIE ◀── market_intelligence         │
  ENGINE         │        research_lineage             │
                 │        market_universe (939 LOC)    │
                 └──────────────┬──────────────────────┘
                                │
  Step 3 (2d):   ┌──────────────▼──────────────────────┐
  STRATEGY   ◀───┤ Mongo:strategies + strategy_library │
  LIBRARY        │ ranking · governance · survivors    │
                 └──────────────┬──────────────────────┘
                                │
  Step 4 (4d):   ┌──────────────▼──────────────────────┐
  STRATEGY   ◀───┤ VIE ◀── strategy_engine (882 LOC)   │
  GENERATION     │         auto_factory · gem_factory  │
                 │         strategy_ingestion/*        │
                 └──────────────┬──────────────────────┘
                                │
  Step 5 (2d):   ┌──────────────▼──────────────────────┐
  VALIDATION ◀───┤ numpy/pandas ◀── validation_engine  │
                 │ signal_quality · spread_analyzer    │
                 │ rule_engine · calibration_framework │
                 └──────────────┬──────────────────────┘
                                │
  Step 6 (5d):   ┌──────────────▼──────────────────────┐
  BACKTESTING◀───┤ pandas/numpy/dukascopy              │
                 │ Docker volume: factory_bi5          │
                 │ backtest_engine (1,748 LOC)         │
                 │ walk_forward · monte_carlo · regime │
                 │ data_engine/* · bi5_certification   │
                 └──────────────┬──────────────────────┘
                                │
  Step 7 (3d):   ┌──────────────▼──────────────────────┐
  OPTIMIZATION◀──┤ numpy/pandas                        │
                 │ ga_optimizer · random_search        │
                 │ optimization_portfolio_bridge       │
                 └──────────────┬──────────────────────┘
                                │
  Step 8 (2d):   ┌──────────────▼──────────────────────┐
  AI         ◀───┤ VIE ◀── ai_orchestrator (1,010 LOC) │
  EXPLANATION    │         agent_advisor               │
                 │         strategy_description        │
                 └──────────────┬──────────────────────┘
                                │
  Step 9 (4d):   ┌──────────────▼──────────────────────┐
  STRATEGY   ◀───┤ APScheduler (in factory-runner)     │
  IMPROVEMENT    │ mutation_engine (1,595 LOC)         │
                 │ auto_mutation_runner · evolution    │
                 │ refinement · phase12_tuning         │
                 └──────────────┬──────────────────────┘
                                │
  Step 10 (3d):  ┌──────────────▼──────────────────────┐
  STRATEGY   ◀───┤ cbot_engine/* (IR + transpiler)     │
  COMPARISON     │ parity_certification (618 LOC)      │
                 │ r5_shadow_comparator · htf_parity   │
                 └──────────────┬──────────────────────┘
                                │
  Step 11 (5d):  ┌──────────────▼──────────────────────┐
  MASTER BOT ◀───┤ factory-runner + trade_runner       │
  BUILDER        │ master_bot_engine (662 LOC)         │
                 │ master_bot_ranker · portfolio_*     │
                 │ multi_asset_portfolio · envelope    │
                 └──────────────┬──────────────────────┘
                                │
  Step 12 (3d):  ┌──────────────▼──────────────────────┐
  STRATEGY   ◀───┤ strategy_memory (1,146 LOC)         │
  DOSSIER        │ strategy_profiler · lifecycle       │
                 │ lifecycle_decay                     │
                 └──────────────┬──────────────────────┘
                                │
  Step 13 (2d):  ┌──────────────▼──────────────────────┐
  AUTOMATED  ◀───┤ numpy ◀── expected_value            │
  VALUATION      │           risk_of_ruin              │
                 │           pass_probability          │
                 │           readiness_engine          │
                 └──────────────┬──────────────────────┘
                                │
  Step 14 (2d):  ┌──────────────▼──────────────────────┐
  EXPORT     ◀───┤ cbot_engine/* + asf/* package       │
  FRAMEWORK      │ master_bot_export · code_generator  │
                 │ compile_engine · deployment         │
                 └──────────────┬──────────────────────┘
                                │
                                ▼
                    Downloadable .asf / .cbot / .json artefact
                    → deployed to trade_runner (paper first)
                    → live via runner_router + heartbeat


  ═══════════════════════════════════════════════════════════
  Cross-cutting subsystems reused across ALL pillars:
  ═══════════════════════════════════════════════════════════
     · factory_supervisor/* (24 files) — copilot + fleet registry
     · adaptive_concurrency, adaptive_pool_sizer, admission_controller
     · scaling_events, scaling_registry, scaling_router, soak_stability
     · feature_flags, flag_overrides
     · persistence_adapters/* (BI5 + market_spread Mongo stores)
     · monitoring_engine, alert_engine, monitoring_alert_bridge
     · auth/deps.require_roles(...) on every mutating endpoint
     · Prometheus scrape + Promtail logging labels on every container
```

**How each pillar touches each shared component:**

| Pillar | Backend | Frontend | VIE | MongoDB | Redis | Docker | Monitoring |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Diagnostic Surfaces | ✓ | ✓ | — | ✓ read | — | — | ✓ scrape |
| Research | ✓ | ✓ | ✓ | ✓ RW | — | — | ✓ scrape |
| Library | ✓ | ✓ | — | ✓ RW | — | — | ✓ scrape |
| Generation | ✓ | ✓ | ✓ | ✓ RW | — | — | ✓ scrape |
| Validation | ✓ | ✓ | — | ✓ RW | — | — | ✓ scrape |
| Backtesting | ✓ | ✓ | — | ✓ RW | opt cache | ✓ volume `factory_bi5` | ✓ scrape |
| Optimization | ✓ | ✓ | — | ✓ RW | opt cache | — | ✓ scrape |
| AI Explanation | ✓ | ✓ | ✓ | ✓ RW | — | — | ✓ scrape |
| Improvement | ✓ | ✓ | ✓ | ✓ RW | — | ✓ sibling `factory-runner` | ✓ scrape |
| Comparison | ✓ | ✓ | — | ✓ RW | — | — | ✓ scrape |
| Master Bot | ✓ | ✓ | opt | ✓ RW | opt cache | ✓ sibling `factory-runner` + trade_runner | ✓ scrape |
| Dossier | ✓ | ✓ | opt | ✓ RW | — | — | ✓ scrape |
| Valuation | ✓ | ✓ | — | ✓ RW | — | — | ✓ scrape |
| Export | ✓ | ✓ | — | ✓ RW | — | — | ✓ scrape |

Legend: `✓` required · `opt` optional/enhancement · `—` unused

---

## 4. Global sequencing rules (do not violate)

1. **Never mount a Stage 2 router without `ENABLE_LEGACY_ROUTERS=true`.** Prefix every mount with `/api/legacy/` so it can't collide with Phase 1 routes.
2. **Never edit a preserved engine to fit the new core.** If the engine expects a Mongo collection that doesn't exist yet, let it create it — Phase 1 already ensures indexes idempotently.
3. **Never call an LLM SDK directly from a legacy engine.** Every LLM path must go through `app.vie.client.get_vie()`. §0.4 lists the exact files to migrate.
4. **Run `./infra/scripts/health.sh` after every mount.** Overall status must return to green before proceeding to the next pillar.
5. **Never activate two pillars in the same deploy cycle.** One-per-deploy discipline lets `health.sh` blame the right pillar if something fails.
6. **`factory-runner` is required only from Step 9 onward.** Steps 1–8 do not need the sibling scheduler; keep the compose file minimal until then.
7. **The BI5 volume (Step 6) must survive redeploys.** Use a named Docker volume, never a bind-mount to a repo path.
8. **Never re-run the v01 mongodump `--drop`** after the first import — subsequent Stage 2 pillars write into the same DB and will lose data.
9. **The React shell stays lean.** Every new page from Stage 2 goes into `frontend/src/pages/` following the Phase 1 patterns (`Layout` + `ProtectedRoute roles=[...]`). Do NOT re-introduce the v01 CommandShell as a wholesale replacement — cherry-pick components from `frontend/legacy/src/` and adapt.
10. **Ship the sidebar nav update in the same PR as the router mount.** Otherwise operators discover unnavigable routes.

---

## 5. Definition of "Stage 2 complete"

All 13 pillars mounted, all UI pages ported, `./infra/scripts/health.sh` green, and the following acceptance flows pass end-to-end on `https://strategy.coinnike.com`:

- [ ] Researcher submits a Research query → lineage recorded → strategy candidate ingested into Library
- [ ] Developer opens Auto Factory → generates 20 candidates → 3 pass Validation
- [ ] Developer opens one candidate → runs 1-year Backtest → Walk-forward + Monte Carlo reports render
- [ ] Optimization run → 50 offspring → GA selects top 5
- [ ] Improvement run → mutation loop produces ranked successors
- [ ] AI Explanation → generates rationale for the top candidate (via VIE)
- [ ] Comparison → parity check between Python IR and cBot output → PASS
- [ ] Master Bot Builder → assembles 5 winning strategies → compiles → deploys to paper runner
- [ ] Automated Valuation → traffic-light green on the deployed Master Bot
- [ ] Dossier → full-page report renders every section
- [ ] Export → downloads a valid `.asf` package

**When these 11 boxes are checked, Strategy Factory Stage 2 is complete and the platform is ready for the customer-facing product work that comes after.**

---

*End of Stage 2 Activation Guide.*
