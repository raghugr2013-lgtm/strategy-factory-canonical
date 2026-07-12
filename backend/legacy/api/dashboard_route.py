"""
Phase 10 — Dashboard route binding.

Registers /dashboard/generate directly on the strategies_router because
the preview ingress only forwards requests whose first-segment router is
already known. This file is import-only — it has no side effects beyond
attaching the endpoint to the existing router.
"""
from pydantic import BaseModel
from typing import Optional

from api.strategies import router as strategies_router
from api.dashboard import (
    dashboard_generate, DashboardGenerateRequest,
    dashboard_quality_profile, QualityProfileRequest,
    dashboard_datasets,
    dashboard_generate_portfolio, MultiAssetGenerateRequest,
)
from engines.portfolio_store import (
    save_portfolio as _save_portfolio,
    list_portfolios as _list_portfolios,
    load_portfolio as _load_portfolio,
    delete_portfolio as _delete_portfolio,
)
from engines.strategy_library import (
    save_strategy as _save_strategy,
    auto_save_top as _auto_save_top,
    list_saved as _list_saved,
    delete_saved as _delete_saved,
)
from engines.cbot_pipeline import build_reliable_cbot as _build_cbot


@strategies_router.post("/dashboard/generate")
async def _dashboard_generate_proxy(req: DashboardGenerateRequest):
    return await dashboard_generate(req)


# Alias under a path prefix known to the ingress (the external preview
# proxy only forwards `/api/<prefix>` paths that already existed in the
# registered app — adding it here as a second mount avoids the 404).
@strategies_router.post("/pipeline/dashboard")
async def _dashboard_generate_alias(req: DashboardGenerateRequest):
    return await dashboard_generate(req)


# P2 — quality threshold calibration (registered on strategies_router
# so the preview ingress forwards it).
@strategies_router.post("/dashboard/quality-profile")
async def _dashboard_quality_profile_proxy(req: QualityProfileRequest):
    return await dashboard_quality_profile(req)


# P2 — dataset inventory (dynamic pair/timeframe discovery).
@strategies_router.get("/dashboard/datasets")
async def _dashboard_datasets_proxy():
    return await dashboard_datasets()


# P4 — multi-asset portfolio rollout.
@strategies_router.post("/dashboard/generate-portfolio")
async def _dashboard_generate_portfolio_proxy(req: MultiAssetGenerateRequest):
    return await dashboard_generate_portfolio(req)


# ── P1 — Multi-Asset Portfolio persistence (save / list / load / delete) ──

class PortfolioSaveRequest(BaseModel):
    name: str
    portfolio_result: dict          # the full response from `/dashboard/generate-portfolio`
    request_echo: Optional[dict] = None


@strategies_router.post("/dashboard/portfolios/save")
async def _portfolio_save(req: PortfolioSaveRequest):
    return await _save_portfolio(
        name=req.name,
        portfolio_result=req.portfolio_result or {},
        request_echo=req.request_echo or {},
    )


@strategies_router.get("/dashboard/portfolios/list")
async def _portfolio_list(limit: int = 100):
    return await _list_portfolios(limit=limit)


@strategies_router.get("/dashboard/portfolios/{portfolio_id}")
async def _portfolio_load(portfolio_id: str):
    return await _load_portfolio(portfolio_id)


@strategies_router.delete("/dashboard/portfolios/{portfolio_id}")
async def _portfolio_delete(portfolio_id: str):
    return await _delete_portfolio(portfolio_id)


# ── Phase 11 — Strategy Library endpoints ─────────────────────────────

class LibrarySaveRequest(BaseModel):
    strategy: dict
    source: Optional[str] = "dashboard"
    force: Optional[bool] = False


class LibraryAutoSaveRequest(BaseModel):
    top_strategies: list
    source: Optional[str] = "auto_save"


@strategies_router.post("/library/save")
async def library_save(req: LibrarySaveRequest):
    res = await _save_strategy(req.strategy, source=req.source or "dashboard",
                                force=bool(req.force))
    # Phase 14.4 — pipeline log (additive, best-effort)
    try:
        from engines.pipeline_logs import log_event as _plog
        status = res.get("status")
        level = "success" if status == "saved" else (
            "warn" if status in ("duplicate", "rejected") else "error"
        )
        s = req.strategy or {}
        m = (s.get("backtest") or {})
        pf = m.get("profit_factor")
        msg = {
            "saved":     f"Strategy saved (PF {pf})" if pf is not None else "Strategy saved",
            "duplicate": "Duplicate fingerprint — already in library",
            "rejected":  f"Rejected: {res.get('reason')}",
        }.get(status, f"Save {status}")
        await _plog(
            "save", msg, level=level,
            strategy_id=res.get("strategy_id"),
            pair=s.get("pair"), timeframe=s.get("timeframe"),
            meta={"source": req.source or "dashboard",
                  "verdict": s.get("verdict"), "score": s.get("score")},
        )
    except Exception:
        pass
    return res


@strategies_router.post("/library/auto-save")
async def library_auto_save(req: LibraryAutoSaveRequest):
    res = await _auto_save_top(req.top_strategies,
                                source=req.source or "auto_save")
    # Phase 14.4 — pipeline log (additive, best-effort)
    try:
        from engines.pipeline_logs import log_event as _plog
        counts = res.get("counts") or {}
        saved = counts.get("saved", 0)
        dup   = counts.get("duplicates", 0)
        rej   = counts.get("rejected", 0)
        level = "success" if saved > 0 else ("warn" if (dup or rej) else "info")
        await _plog(
            "save",
            f"Save Top → saved {saved} · duplicates {dup} · rejected {rej}",
            level=level, meta={"source": req.source or "auto_save"},
        )
    except Exception:
        pass
    return res


@strategies_router.get("/library/list")
async def library_list(pair: str = None, timeframe: str = None,
                       verdict: str = None, limit: int = 100):
    items = await _list_saved(pair=pair, timeframe=timeframe,
                              verdict=verdict, limit=limit)
    return {"count": len(items), "items": items}


@strategies_router.delete("/library/{strategy_id}")
async def library_delete(strategy_id: str):
    ok = await _delete_saved(strategy_id)
    return {"success": ok}


# ── Phase 12 — Reliability-layer cBot generator ──────────────────────

class CbotBuildRequest(BaseModel):
    strategy_profile: dict
    safety_rules: Optional[dict] = None


@strategies_router.post("/cbot/build-reliable")
async def cbot_build_reliable(req: CbotBuildRequest):
    return _build_cbot(req.strategy_profile, req.safety_rules)


# ── Strategy Description Layer (additive, read-only enrichment) ──────

class DescribeRequest(BaseModel):
    strategy_text: str
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    style: Optional[str] = None
    backtest: Optional[dict] = None
    force: Optional[bool] = False


@strategies_router.post("/strategy/describe")
async def strategy_describe(req: DescribeRequest):
    """Return `{fingerprint, description, cached, created_at, ...}`.
    Uses cache by `fingerprint` unless `force=True`. Never raises — on
    LLM failure the `description` field carries an `error` key and the
    overall response still carries the stable `fingerprint`."""
    from engines.strategy_description import get_or_create_description
    return await get_or_create_description(
        req.strategy_text,
        pair=req.pair, timeframe=req.timeframe, style=req.style,
        backtest=req.backtest, force=bool(req.force),
    )


@strategies_router.get("/strategy/description/{fingerprint}")
async def strategy_description_by_fp(fingerprint: str):
    """Look up a previously-generated description by fingerprint. Returns
    404 when nothing is cached."""
    from fastapi import HTTPException
    from engines.strategy_description import get_cached_description
    doc = await get_cached_description(fingerprint)
    if not doc:
        raise HTTPException(status_code=404, detail="description not found")
    return {
        "fingerprint": doc.get("fingerprint"),
        "description": doc.get("description"),
        "cached": True,
        "created_at": doc.get("created_at"),
        "pair": doc.get("pair"),
        "timeframe": doc.get("timeframe"),
    }
