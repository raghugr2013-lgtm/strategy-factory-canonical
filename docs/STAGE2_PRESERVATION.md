# Stage 2 Preservation

**Purpose:** Every Stage 2 module from the v01 handoff bundle is preserved on disk in this repository. This document describes what is preserved, where it now resides, and what it takes to activate each subsystem — without any architectural restructuring.

**Location root:** `backend/legacy/`

**Guarantee:** re-enabling any preserved module is an **additive** action (install its dependencies, register its router in `app/main.py` behind a feature flag). **No refactor of the Phase 1 core is required.**

---

## 1. Directory summary

| Path | File count | Purpose |
|---|---:|---|
| `backend/legacy/engines/` | 175 | Domain engines (research, generation, validation, backtest, portfolio, master bot, etc.) |
| `backend/legacy/api/` | 66 | Legacy FastAPI routers (`/api/{strategies,portfolio,master_bot,…}`) |
| `backend/legacy/cbot_engine/` | 6 | cBot IR generator + parity simulator + transpiler |
| `backend/legacy/data_engine/` | 13 | BI5 tick ingest + archive + gap analyzer + market calendar |
| `backend/legacy/scripts/` | 12 | BI5 archive helpers, seed helpers, validation utilities |
| `backend/legacy/factory_runner.py` | 1 | APScheduler sibling entrypoint |
| `backend/legacy/requirements.legacy.txt` | 1 | pandas, numpy, dukascopy-python, APScheduler, pdfplumber, pypdf, reportlab, beautifulsoup4, lxml, psutil |
| `backend/legacy/README.md` | 1 | pointer back to this document |

**Total: 344 files preserved verbatim from v01 (`factory-source-20260614_151752.tar.gz`).**

---

## 2. Module map (Stage 2 → files that already exist)

Each row of the Stage 2 roadmap maps to preserved code that will become the seed of that feature. Nothing needs to be re-invented from scratch.

### Research Engine
- `legacy/engines/market_intelligence.py`, `market_universe*.py`, `research_lineage.py`
- `legacy/api/market_intelligence.py`, `research_lineage.py`
- **Integration point (Phase 1 core):** `app/api/research.py` already exposes `/api/research/query` and `/api/research/history` via VIE. The legacy engines add lineage tracking and market-universe wiring on top.

### Strategy Generation
- `legacy/engines/strategy_engine.py`, `strategy_ingestion/`, `strategy_ir*.py`, `strategy_description.py`, `strategy_ranking_engine.py`
- `legacy/api/strategies.py`, `api/auto_factory.py`, `api/gem_factory.py`
- **Integration point:** `app/api/strategies.py` provides CRUD on the `strategies` collection; generation adds population from IR + templates.

### Validation
- `legacy/engines/validation_engine.py`, `validation_report.py`, `signal_quality.py`, `spread_analyzer.py`
- **Integration point:** New endpoints `/api/validation/*` register into `app/main.py`.

### Optimization
- `legacy/engines/optimization_engine.py`, `ga_optimizer.py`, `random_search_optimizer.py`, `optimization_portfolio_bridge.py`
- `legacy/api/optimization.py`
- Requires: legacy dependencies `numpy`, `pandas`.

### Backtesting
- `legacy/engines/backtest_engine.py`, `backtest_pool.py`, `backtest_report.py`, `execution_simulator.py`, `execution_realism_defaults.py`, `slippage_model.py`, `walk_forward_engine.py`, `oos_holdout.py`, `monte_carlo_engine.py`
- Requires: BI5 tick data via `legacy/data_engine/`

### AI Explanation
- `legacy/engines/strategy_description.py`, `analysis_engine.py`, `agent_advisor.py`, `ai_orchestrator.py`, `llm_runner.py`
- **AI calls migrated:** replace `EMERGENT_LLM_KEY` sites in these files with `from app.vie.client import get_vie` calls before enabling. `docs/MIGRATION_NOTES.md` documents the substitution.

### Strategy Improvement
- `legacy/engines/refinement_engine.py`, `strategy_refinement_engine.py`, `mutation_engine.py`, `auto_mutation_runner.py`, `mutation_pool.py`, `evolution_engine.py`, `phase12_tuning.py`
- `legacy/api/mutation.py`, `auto_mutation.py`, `phase12_tuning.py`

### Strategy Comparison
- `legacy/engines/parity_certification.py`, `parity_drift_view.py`, `cbot_parity.py`, `cbot_trade_parity.py`, `htf_parity.py`, `r5_shadow_comparator.py`
- `legacy/api/cbot_parity.py`

### Master Bot framework
- `legacy/engines/master_bot_definition.py`, `master_bot_engine.py`, `master_bot_ranker.py`, `master_bot_pack.py`, `master_bot_export.py`, `master_bot_deployment.py`, `master_bot_diff.py`
- `legacy/api/master_bot.py`, `deployment.py`

### Strategy Dossier
- `legacy/engines/strategy_memory.py`, `strategy_profiler.py`, `strategy_lifecycle.py`
- `legacy/api/strategy_memory.py`, `lifecycle.py`

### Automated Valuation
- `legacy/engines/expected_value.py`, `risk_of_ruin.py`, `pass_probability.py`, `readiness_engine.py`, `history_prior.py`
- `legacy/api/readiness.py`

### Internal Strategy Library
- `legacy/engines/strategy_library.py`, `strategy_ranking_engine.py`, `ranking_engine.py`, `governance_universe.py`, `survivor_registry.py`
- `legacy/api/dashboard.py`, `phase4_matching.py`

### Scheduler / Automation
- `legacy/engines/auto_scheduler.py`, `orchestrator_scheduler.py`, `cadence_scheduler.py`, `rotational_orchestrator.py`
- `legacy/factory_runner.py` — the APScheduler sibling process
- Requires: `APScheduler==3.11.2`

---

## 3. Runtime activation (per module)

### 3.1 Enabling one legacy router

1. Install the legacy Python deps into the backend image:
   ```dockerfile
   # backend/Dockerfile
   RUN pip install -r legacy/requirements.legacy.txt
   ```

2. Register the router in `app/main.py` behind an env flag:
   ```python
   import os
   if os.getenv("ENABLE_LEGACY_ROUTERS", "").lower() == "true":
       # Optionally scope-mount under /api/legacy/… to avoid collisions.
       from legacy.api.master_bot import router as legacy_mb_router
       app.include_router(legacy_mb_router, prefix="/api/legacy")
   ```

3. If a legacy engine calls `EMERGENT_LLM_KEY` directly, replace with VIE:
   ```python
   # BEFORE (v01)
   key = os.getenv("EMERGENT_LLM_KEY")
   ...

   # AFTER
   from app.vie.client import get_vie
   result = await get_vie().generate(prompt=..., task="generation")
   ```
   The substitution table is in `docs/MIGRATION_NOTES.md §1`.

4. Rebuild the image and redeploy:
   ```bash
   ./infra/scripts/deploy.sh
   ```

### 3.2 Enabling the sibling scheduler

1. Add a `factory-runner` service to `infra/compose/docker-compose.prod.yml` that reuses the backend image and overrides the command:
   ```yaml
   factory-runner:
     image: ${FACTORY_IMAGE_REPO}/backend:${FACTORY_IMAGE_TAG}
     container_name: factory-runner
     restart: unless-stopped
     depends_on:
       factory-backend:
         condition: service_healthy
     working_dir: /app
     command: ["python", "-u", "legacy/factory_runner.py"]
     environment:
       MONGO_URL: ${SHARED_MONGO_URL}
       DB_NAME: ${FACTORY_DB_NAME}
       FACTORY_RUNNER_OWNS_SCHEDULERS: "true"
       FACTORY_RUNNER_HEARTBEAT_SEC: "60"
       PYTHONUNBUFFERED: "1"
     networks:
       - vqb-network
     healthcheck:
       test: ["CMD-SHELL", "python -c \"import os,pymongo; pymongo.MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000).admin.command('ping')\" || exit 1"]
       interval: 60s
       timeout: 10s
       retries: 3
       start_period: 45s
   ```

2. Ensure `ENABLE_LEGACY_ROUTERS=true` on the backend so that scheduler-dependent APIs are mounted.

3. `./infra/scripts/deploy.sh`

### 3.3 Enabling BI5 tick data

1. Install `dukascopy-python==4.0.1` from `legacy/requirements.legacy.txt`.
2. Add a named volume `factory_bi5` to Compose and mount it at `/data/bi5`.
3. Set `BI5_ARCHIVE_PATH=/data/bi5` in the backend env.
4. Run the initial backfill via the preserved script:
   ```bash
   docker exec factory-backend python legacy/scripts/bi5_one_shot_backfill.py
   ```

---

## 4. Architectural guarantee

**Enabling Stage 2 later will NOT require restructuring the Phase 1 core because:**

1. **Interface stability.** The Phase 1 core communicates with everything through:
   - MongoDB collections (`users`, `strategies`, `research_queries`, plus any collection legacy engines want to create)
   - VIE HTTP (`http://factory-vie:8100`) for LLM calls — one entrypoint, no direct SDK usage
   - FastAPI dependency injection (`get_current_user`, `require_roles(...)`) — role guards are additive on any new router

2. **Additive routers.** `app/main.py::create_app` uses `app.include_router(...)`. Adding a legacy router does not touch the existing routes. Prefix them with `/api/legacy/…` if you want to avoid namespace collisions.

3. **Dependency isolation.** Phase 1 requirements (`backend/requirements.txt`) do NOT overlap with legacy requirements (`backend/legacy/requirements.legacy.txt`). Installing legacy deps is a pure superset — no version pins conflict.

4. **Data compatibility.** Every collection the legacy engines used still exists (Mongo doesn't care whether a collection is currently accessed). Migrating the v01 mongodump into the new DB is one `mongorestore` command — documented in `docs/MIGRATION_NOTES.md §1`.

5. **No hidden globals.** The Phase 1 core has zero mutable module-level state. Legacy engines that used the same pattern will co-exist without race conditions.

6. **Preserved test suite.** v01's pytest tests are archived under `backend/legacy/` (see `factory-source-20260614/backend/tests/` in the source tarball) — they can be enabled with the same feature flag and used to validate Stage 2 re-enablement.

**Bottom line:** Stage 2 development can continue on this repository. No further consolidation session is required.

---

## 5. Recommended re-enablement order

If you want to bring Stage 2 back incrementally rather than in one big-bang:

1. **Foundations** — install legacy deps, mount legacy `data_engine`, restore v01 mongodump. No new routers yet.
2. **Read-only surfaces** — mount `legacy/api/{data_health, llm_health, orchestrator_heartbeat, readiness}` behind `ENABLE_LEGACY_ROUTERS=true`. These are diagnostic; they can't corrupt anything.
3. **Strategy library + research** — mount `legacy/api/{strategies, research_lineage, market_intelligence}` and migrate their LLM calls to VIE.
4. **Validation + backtest** — mount `legacy/api/{optimization, monitoring, pipeline}` with dependent engines.
5. **Master bot + deployment** — mount `legacy/api/{master_bot, deployment, mutation, auto_factory}`.
6. **Scheduler** — bring up the `factory-runner` sibling container.

Each step is verifiable with `./infra/scripts/health.sh` + Grafana panels. Roll forward feature by feature.
