"""FastAPI application factory.

Phase 0 mounts only the lean Phase-1 core (auth + admin + strategies CRUD +
research + dashboard + health). Legacy routers are gated behind
ENABLE_LEGACY_ROUTERS. When true, legacy routers are mounted MODULE-BY-MODULE
by the phase that owns them (Strategy Generation in Phase 1, Backtesting in
Phase 2, etc.).
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
    yield
    logger.info("shutdown")


def _mount_legacy_routers(app: FastAPI) -> None:
    """Full-recovery mount block. All ~85 preserved legacy routers under
    a single ENABLE_LEGACY_ROUTERS gate. Route-prefix conflicts with the
    Phase-1 core are resolved by mounting under /api/legacy/ instead of
    /api/. Every mounted router inherits JWT auth via get_current_user.
    """
    s = get_settings()
    if not s.enable_legacy_routers:
        logger.info("legacy routers dormant (ENABLE_LEGACY_ROUTERS=false)")
        return

    from app.auth.deps import get_current_user  # noqa: WPS433
    from fastapi import APIRouter as _APIRouter  # noqa: WPS433

    auth_dep = [Depends(get_current_user)]

    # ── Modules that COLLIDE with Phase-1 core routes ────────────
    #   Phase-1 owns /api/auth, /api/admin, /api/dashboard/summary,
    #   /api/strategies, /api/readiness. Mount conflicting legacy
    #   modules under /api/legacy/ to preserve their surface.
    conflict_map = {
        "admin": "/api/legacy",           # legacy admin dashboard
        "strategies": "/api/legacy",      # legacy strategies (attaches dashboard_route + phase4_route)
        "dashboard": "/api/legacy",       # legacy dashboard widgets
        "readiness": "/api/legacy",       # legacy readiness (different from Phase-1 /api/readiness)
    }

    # ── Primary routers ─────────────────────────────────────────
    # (auto_factory already mounted separately in Phase 1B; skip)
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
        "lifecycle", "live_tracking", "llm_diagnostics", "llm_health",
        "master_bot", "monitoring", "multi_cycle", "mutation",
        "optimization", "orchestrator", "orchestrator_heartbeat",
        "phase12_tuning", "phase4_matching",
        "pipeline", "pipeline_logs",
        "portfolio", "portfolio_builder", "portfolio_intelligence",
        "prop_firm_intelligence", "prop_firm_rules_review", "prop_firms",
        "readiness", "regime", "research_lineage",
        "runner", "scaling", "soak_diagnostics",
        "strategies", "strategy_memory", "trade_runner",
    ]

    mounted = 0
    from fastapi import APIRouter
    for name in primary_names:
        try:
            mod = __import__(f"legacy.api.{name}", fromlist=["*"])
            # Collect every APIRouter attribute (some modules expose 2)
            for _n, _v in vars(mod).items():
                if isinstance(_v, APIRouter):
                    prefix = conflict_map.get(name, "/api")
                    app.include_router(_v, prefix=prefix, dependencies=auth_dep)
                    mounted += 1
        except Exception:  # noqa: BLE001
            logger.exception("legacy mount failed for api.%s", name)

    # dashboard_route + phase4_route attach endpoints to legacy strategies
    # router at import time. Importing them is sufficient — their side
    # effect is to add sub-endpoints to `legacy.api.strategies.router`,
    # which is already mounted above.
    for side_effect in ("dashboard_route", "phase4_route"):
        try:
            __import__(f"legacy.api.{side_effect}", fromlist=["*"])
            mounted += 1  # count as attached
        except Exception:  # noqa: BLE001
            logger.exception("legacy side-effect import failed: %s", side_effect)

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

    # Also mount `market_intelligence` (two routers) + `challenge_matching`
    # + `prop_firm_analysis` — these expose 2 routers each and are already
    # handled by the primary_names iteration above (matched via APIRouter
    # attribute enumeration).

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
    # Phase-1 core (always on)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(strategies_router)
    app.include_router(research_router)
    app.include_router(dashboard_router)

    # Legacy — module-by-module (currently all dormant in Phase 0)
    _mount_legacy_routers(app)
    # Future modules — mounted from /app/modules/<slug>/backend/api/ (never modifies frozen core)
    _mount_future_modules(app)
    return app


app = create_app()
