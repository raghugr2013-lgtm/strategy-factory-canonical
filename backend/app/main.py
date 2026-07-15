"""FastAPI application factory.

Phase 0 mounts only the lean Phase-1 core (auth + admin + strategies CRUD +
research + dashboard + health). Legacy routers are gated behind
ENABLE_LEGACY_ROUTERS. When true, legacy routers are mounted MODULE-BY-MODULE
by the phase that owns them (Strategy Generation in Phase 1, Backtesting in
Phase 2, etc.).

──────────────────────────────────────────────────────────────────────
v1.1.1 API-Compatibility Recovery — routing fixes (Feb 2026)
──────────────────────────────────────────────────────────────────────
Legacy full-recovery mounts every preserved v01 router at its canonical
`/api/*` path. The previous `conflict_map` that relocated the four
"colliding" modules to `/api/legacy/*` broke the entire frontend, which
was written against `/api/challenge-firms`, `/api/dashboard/generate`,
`/api/rank-strategies`, `/api/admin/readiness`, `/api/library/*`, etc.
The relocation was unnecessary because Phase-1 core routes register
first and win on identical paths — every other legacy route lives at a
path Phase-1 core never claims.

`/strategies`-scoped legacy routers (`strategy_memory`,
`market_intelligence`, `prop_firm_analysis`, `challenge_matching`) MUST
mount before the legacy `strategies.py` router and Phase-1 core
`strategies_router`, otherwise Phase-1 core's
`GET /api/strategies/{strategy_id}` catch-all shadows every specific
subpath (`/explorer`, `/{hash}/history`, `/{hash}/market-scan`, etc.).
FastAPI matches routes in registration order.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.research import router as research_router
from app.api.strategies import router as strategies_router
from app.auth.routes import router as auth_router
from app.auth.seed import seed_admin
from app.core.config import get_settings
from app.core.versioning import version_info
from app.db.mongo import ensure_indexes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("strategy_factory")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("boot %s", version_info())
    try:
        await ensure_indexes()
    except Exception:  # noqa: BLE001
        logger.exception("ensure_indexes failed")
    try:
        await seed_admin()
    except Exception:  # noqa: BLE001
        logger.exception("seed_admin failed")

    # v1.1.1 — Automatic market-data maintenance resume-on-boot.
    # If the persisted config in `auto_maintenance_config.enabled == True`
    # (operator toggled it on before restart), transparently restart the
    # APScheduler so BID/BI5 top-ups resume without a manual toggle.
    # Never crashes boot — best-effort only. Requires ENABLE_LEGACY_ROUTERS.
    if get_settings().enable_legacy_routers:
        # v1.1.1a — one-shot cleanup of stale `bi5_runner_error` rows that
        # were emitted before commit 976e04e (BI5SymbolSpec dataclass fix,
        # 2026-07-14T15:24Z). Their error text is "'dict' object has no
        # attribute 'symbol'" and they leak into the operator UI. Any row
        # with that string is safe to drop — the next scheduled BI5 tick
        # rewrites the correct state for every symbol. Non-fatal; runs
        # once per boot; matches by error substring so re-run is a no-op.
        try:
            from app.db.mongo import get_db as _get_db
            _db = _get_db()
            _res = await _db.auto_maintenance_status.delete_many({
                "bi5_runner_error": {"$regex": "'dict' object has no attribute 'symbol'"}
            })
            if _res.deleted_count:
                logger.info(
                    "auto-maintenance: purged %d stale pre-fix BI5 error rows",
                    _res.deleted_count,
                )
        except Exception:  # noqa: BLE001
            logger.exception("auto-maintenance stale BI5 cleanup failed (non-fatal)")
        try:
            import sys as _sys, os as _os
            _lp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "legacy")
            if _lp not in _sys.path:
                _sys.path.insert(0, _lp)
            from data_engine import auto_data_maintainer as _adm  # type: ignore
            _cfg = await _adm._load_config()
            if _cfg.get("enabled"):
                await _adm.start_scheduler()
                logger.info("auto-maintenance scheduler resumed on boot (config.enabled=True)")
            else:
                logger.info("auto-maintenance scheduler dormant on boot (config.enabled=False — toggle via /api/data/maintenance/toggle)")
        except Exception:  # noqa: BLE001
            logger.exception("auto-maintenance resume-on-boot failed (non-fatal)")

    # v1.2.0-alpha2 — bootstrap outcome_events indexes so the ledger
    # is ready to accept writes from the pipeline decorators.
    if get_settings().enable_legacy_routers:
        try:
            import sys as _sys, os as _os
            _lp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "legacy")
            if _lp not in _sys.path:
                _sys.path.insert(0, _lp)
            from engines.learning import ensure_indexes as _learning_ensure_indexes
            await _learning_ensure_indexes()
        except Exception:  # noqa: BLE001
            logger.exception("learning.ensure_indexes failed (non-fatal)")

        # v1.2.0-alpha2 Phase B — auto-start the continuous learning
        # scheduler when `LEARNING_SCHEDULER_ENABLED=true`. Any failure
        # here is non-fatal: manual /api/learning/scheduler/start is
        # always available as a recovery path.
        try:
            from engines.learning import config as _lcfg, start_scheduler as _learning_start_scheduler
            if _lcfg.scheduler_enabled():
                _sched_info = await _learning_start_scheduler()
                logger.info("learning scheduler auto-started on boot: %s", _sched_info)
            else:
                logger.info("learning scheduler dormant on boot (LEARNING_SCHEDULER_ENABLED=false)")
        except Exception:  # noqa: BLE001
            logger.exception("learning scheduler auto-start failed (non-fatal)")

    yield
    logger.info("shutdown")


# ──────────────────────────────────────────────────────────────────
# Legacy /strategies-scoped routers — MUST mount before Phase-1 core
# so specific subpaths beat `/api/strategies/{strategy_id}` catch-all.
# ──────────────────────────────────────────────────────────────────
_PRIORITY_STRATEGY_SCOPE_MODULES = (
    "strategy_memory",      # /strategies/explorer, /strategies/library/{id}/details, /strategies/{hash}/*
    "market_intelligence",  # /strategies/{hash}/market-scan|profile
    "prop_firm_analysis",   # /strategies/{hash}/prop-analysis
    "challenge_matching",   # /strategies/{hash}/match-challenges|challenge-match
)


def _mount_legacy_routers(app: FastAPI) -> None:
    """Full-recovery mount block. All ~85 preserved legacy routers under
    a single ENABLE_LEGACY_ROUTERS gate. Every legacy router mounts at
    `/api` — the previous `conflict_map` relocation to `/api/legacy` has
    been removed because it stranded ~40 frontend-consumed endpoints.
    Route collisions with Phase-1 core (only 3 identical paths exist)
    are naturally resolved by FastAPI: Phase-1 core routes register
    first in `create_app()` and win.
    """
    s = get_settings()
    if not s.enable_legacy_routers:
        logger.info("legacy routers dormant (ENABLE_LEGACY_ROUTERS=false)")
        return

    from app.auth.deps import get_current_user  # noqa: WPS433
    from fastapi import APIRouter  # noqa: WPS433

    auth_dep = [Depends(get_current_user)]

    # ── Primary routers ─────────────────────────────────────────
    # (`strategy_memory`, `market_intelligence`, `prop_firm_analysis`,
    #  `challenge_matching` are lifted to _PRIORITY_STRATEGY_SCOPE_MODULES
    #  and mounted FIRST; do not repeat them here.)
    primary_names = [
        "admin", "admin_execution_realism", "admin_flag_governance", "admin_market_universe",
        "asf", "auto_mutation", "auto_selection",
        "bi5_cert_sweep", "bi5_certification", "bi5_ingest", "bi5_realism",
        "cbot", "cbot_parity",
        "challenge",
        "cpu_pool_state", "dashboard",
        "data", "data_health", "data_maintenance",
        "deployment", "diag_bi5_health",
        "execution", "factory_supervisor", "gem_factory", "governance",
        "incremental_run_alias", "ingestion",
        "knowledge",     # v1.1.1 AI Learning Layer — /api/knowledge/*
        "learning",      # v1.2.0-alpha2 outcome-event ledger — /api/learning/*
        "ai_workforce",  # v1.2.0-alpha2 provider health + telemetry — /api/ai-workforce/*
        "lifecycle", "live_tracking", "llm_diagnostics", "llm_health",
        "master_bot", "monitoring", "multi_cycle", "mutation",
        "optimization", "orchestrator", "orchestrator_heartbeat",
        "phase12_tuning", "phase4_matching",
        "pipeline", "pipeline_logs",
        "portfolio", "portfolio_builder", "portfolio_intelligence",
        "prop_firm_intelligence", "prop_firm_rules_review", "prop_firms",
        "readiness", "regime", "research_lineage",
        "runner", "scaling", "soak_diagnostics",
        "strategies", "trade_runner",
    ]

    mounted = 0

    # ── PHASE A ── /strategies-scope legacy routers FIRST ──────────
    for name in _PRIORITY_STRATEGY_SCOPE_MODULES:
        try:
            mod = __import__(f"legacy.api.{name}", fromlist=["*"])
            for _n, _v in vars(mod).items():
                if isinstance(_v, APIRouter):
                    app.include_router(_v, prefix="/api", dependencies=auth_dep)
                    mounted += 1
        except Exception:  # noqa: BLE001
            logger.exception("legacy priority mount failed for api.%s", name)

    # ── PHASE B ── everything else ────────────────────────────────
    for name in primary_names:
        # Before mounting `strategies`, run the side-effect imports that
        # ATTACH additional endpoints to the strategies router
        # (dashboard_route: /library/*, /dashboard/*, /strategy/describe,
        #  /cbot/build-reliable, /dashboard/portfolios/*, /pipeline/dashboard;
        #  phase4_route: /match-firms-phase4). These must be imported before
        # `include_router(strategies.router)` because FastAPI snapshots a
        # router's routes at include-time — later mutations don't propagate.
        #
        # IMPORTANT: dashboard_route and phase4_route import via the shim
        # path `from api.strategies import router` — under the sys.path
        # shim installed by server.py this becomes a *different* Python
        # module object than `legacy.api.strategies`, so we mount the same
        # `api.strategies` module the side-effects decorated. Otherwise
        # the ~16 side-effect endpoints are attached to an orphan router.
        if name == "strategies":
            for side_effect in ("dashboard_route", "phase4_route"):
                try:
                    __import__(f"legacy.api.{side_effect}", fromlist=["*"])
                    mounted += 1  # counted as attached
                except Exception:  # noqa: BLE001
                    logger.exception("legacy side-effect import failed: %s", side_effect)
            try:
                # Use the shim path so we grab the SAME router object the
                # side-effects mutated.
                mod = __import__("api.strategies", fromlist=["*"])
                for _n, _v in vars(mod).items():
                    if isinstance(_v, APIRouter):
                        app.include_router(_v, prefix="/api", dependencies=auth_dep)
                        mounted += 1
            except Exception:  # noqa: BLE001
                logger.exception("legacy mount failed for api.strategies (shim path)")
            continue
        try:
            mod = __import__(f"legacy.api.{name}", fromlist=["*"])
            for _n, _v in vars(mod).items():
                if isinstance(_v, APIRouter):
                    app.include_router(_v, prefix="/api", dependencies=auth_dep)
                    mounted += 1
        except Exception:  # noqa: BLE001
            logger.exception("legacy mount failed for api.%s", name)

    # ── Latent routers (v01 Phase 29+ additions) ────────────────
    latent_names = [
        "activation_governance", "activation_timeline",
        "advanced_scaffolding", "calibration",
        "cbot_log_diagnostic", "cbot_trade_parity",
        "compute_probe",
        "deployment_extras", "deployment_readiness",
        "execution_realism_defaults", "factory_runner_heartbeat",
        "feature_flags", "htf_parity",
        "ingestion_aggregate", "ingestion_health", "lifecycle_decay",
        "market_universe", "observability",
        "parity_certification", "risk_of_ruin",
        "safe_to_widen", "widening_history",
    ]
    for name in latent_names:
        try:
            mod = __import__(f"legacy.api.latent.{name}", fromlist=["*"])
            for _n, _v in vars(mod).items():
                if isinstance(_v, APIRouter):
                    app.include_router(_v, prefix="/api", dependencies=auth_dep)
                    mounted += 1
        except Exception:  # noqa: BLE001
            logger.exception("legacy mount failed for api.latent.%s", name)

    # ── Phase 1B — Auto Factory (kept in its own block) ────────
    try:
        from legacy.api.auto_factory import router as auto_factory_router
        app.include_router(auto_factory_router, prefix="/api", dependencies=auth_dep)
        mounted += 1
        logger.info("mounted legacy router: /api/auto-factory")
    except Exception:  # noqa: BLE001
        logger.exception("auto_factory mount failed")

    logger.info("legacy full-recovery mount: %d routers/attachers online", mounted)


def _mount_future_modules(app: FastAPI) -> None:
    """Auto-mount plug-in modules under /app/modules/<slug>/backend/api/.

    Each module directory becomes a namespaced API prefix `/api/<slug>/*`.
    The frozen v01 core is never touched — this loader only adds new routers
    that live entirely outside `backend/legacy/` and `backend/app/`.
    """
    import pathlib
    import importlib.util
    import sys as _sys
    from fastapi import APIRouter

    modules_root = pathlib.Path("/app/modules")
    if not modules_root.exists():
        return
    try:
        from app.auth.deps import get_current_user
        auth_dep = [Depends(get_current_user)]
    except Exception:  # noqa: BLE001
        auth_dep = []

    mounted = 0
    for slug_dir in sorted(modules_root.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name.startswith(("_", ".")):
            continue
        api_dir = slug_dir / "backend" / "api"
        if not api_dir.exists():
            continue
        for py in sorted(api_dir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            mod_name = f"modules.{slug_dir.name}.backend.api.{py.stem}"
            try:
                spec = importlib.util.spec_from_file_location(mod_name, py)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                _sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                for _n, _v in vars(mod).items():
                    if isinstance(_v, APIRouter):
                        app.include_router(_v, dependencies=auth_dep)
                        mounted += 1
            except Exception:  # noqa: BLE001
                logger.exception("future-module mount failed: %s", mod_name)
    if mounted:
        logger.info("future modules mount: %d routers online", mounted)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Strategy Factory",
        version=s.build_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # ── Phase-1 core (always on) — register first ────────────────
    # These are the small, hand-audited routes that own the canonical
    # `/api/auth`, `/api/admin`, `/api/health`, `/api/research`, and
    # `/api/dashboard/summary` paths. They must be first so their exact
    # paths win any collision with legacy modules.
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(research_router)
    app.include_router(dashboard_router)

    # ── Legacy full-recovery mount ───────────────────────────────
    # Mounts every preserved v01 router at `/api/*`. Runs BEFORE the
    # Phase-1 core `strategies_router` so `/api/strategies/explorer`,
    # `/api/strategies/{hash}/history`, `/api/strategies/{hash}/re-run`,
    # `/api/strategies/{hash}/market-scan`, `/api/strategies/{hash}/prop-analysis`,
    # `/api/strategies/{hash}/match-challenges`, and
    # `/api/strategies/library/{id}/details` register ahead of Phase-1's
    # `GET/DELETE /api/strategies/{strategy_id}` catch-all.
    _mount_legacy_routers(app)

    # ── Phase-1 core strategies (catch-all LAST) ─────────────────
    # `/api/strategies/{strategy_id}` is a catch-all that must come
    # after every specific `/api/strategies/<static>` route.
    app.include_router(strategies_router)

    # Future modules — mounted from /app/modules/<slug>/backend/api/ (never modifies frozen core)
    _mount_future_modules(app)
    return app


app = create_app()
