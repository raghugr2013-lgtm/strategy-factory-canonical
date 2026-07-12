"""Phase 14 — Strategy Mutation API."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import mutation_engine as me

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mutation", tags=["mutation"])


class MutationRequest(BaseModel):
    strategy_text: str = Field(..., min_length=1)
    pair: str = Field(..., min_length=3)
    timeframe: str = Field(..., min_length=2)
    style: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    max_variants: int = Field(me.MAX_VARIANTS, ge=me.MIN_VARIANTS, le=me.MAX_VARIANTS)
    prices: Optional[List[float]] = None


@router.post("/mutate")
async def mutation_mutate(req: MutationRequest):
    """Produce forex-specific variants and backtest each one.

    - If `prices` is omitted, reuses `dashboard._load_real_prices` (same
      data path the dashboard itself uses).
    - If `prices` is supplied, overrides the loader and runs all variants
      against the caller-provided series.
    - Output shape is identical for both paths.
    """
    base = {
        "strategy_text": req.strategy_text,
        "pair": req.pair,
        "timeframe": req.timeframe,
        "style": req.style,
        "parameters": req.parameters or {},
    }
    try:
        return await me.run_mutation_pipeline(
            base,
            max_variants=req.max_variants,
            prices=req.prices,
            triggered_by="api",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("mutation pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
async def mutation_preview(req: MutationRequest):
    """Return the structured variants WITHOUT backtesting. Useful for a
    fast UI preview."""
    base = {
        "strategy_text": req.strategy_text,
        "pair": req.pair,
        "timeframe": req.timeframe,
        "style": req.style,
        "parameters": req.parameters or {},
    }
    variants = me.mutate_strategy(base, max_variants=req.max_variants)
    return {
        "pair": req.pair.upper(), "timeframe": req.timeframe.upper(),
        "total_variants": len(variants),
        "variants": [
            {
                "mutation_type": v["mutation_type"],
                "variant_fingerprint": v["variant_fingerprint"],
                "strategy_text": v["strategy_text"],
                "parameters": v["parameters"],
            }
            for v in variants
        ],
    }


@router.get("/events")
async def mutation_events(
    mutation_type: Optional[str] = Query(None, alias="type"),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        return {"events": await me.list_events(mutation_type=mutation_type, limit=limit)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def mutation_stats():
    return await me.get_stats()


@router.get("/catalogue")
async def mutation_catalogue():
    return {
        "mutation_types": list(me.MUTATION_TYPES),
        "min_variants": me.MIN_VARIANTS,
        "max_variants": me.MAX_VARIANTS,
    }


# ── Phase 28 telemetry — IR coverage (read-only, scheduler-independent)
@router.get("/ir-telemetry")
async def mutation_ir_telemetry(
    since: Optional[str] = Query(
        None,
        description="ISO-8601 lower bound on `ts` (inclusive). "
                    "Omit for full-history aggregation.",
    ),
    limit: int = Query(
        5000, ge=1, le=50000,
        description="Hard cap on rows scanned. Default 5000, max 50000.",
    ),
):
    """Operator-facing IR coverage telemetry.

    Aggregates the existing ``mutation_events`` collection into a
    single payload exposing:
      * ir_native vs legacy share (% and absolute)
      * chain-depth distribution + mean
      * legacy-reason breakdown (momentum_base, composer_legacy_base, …)
      * per-mutation-type ir_native rate

    Pure read-only. No scheduler interaction. Historical events lacking
    the Phase 28 telemetry fields bucket as ``unknown`` so the curve is
    honest, not retrofitted.
    """
    from engines.ir_telemetry import fetch_ir_telemetry
    from engines.db import get_db
    db = get_db()
    return await fetch_ir_telemetry(db, since=since, limit=limit)


# ── Phase 14.3 — Stability Monitoring endpoints ──────────────────────

@router.get("/stability/logs")
async def mutation_stability_logs(
    mutation_type: Optional[str] = Query(None, alias="type"),
    auto_save_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
):
    """Newest-first stability log entries. Filterable by mutation_type and/or
    auto_save_status (saved|rejected|duplicate|skipped|error)."""
    try:
        logs = await me.list_stability_logs(
            mutation_type=mutation_type,
            auto_save_status=auto_save_status,
            limit=limit,
        )
        return {"count": len(logs), "logs": logs}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stability/stats")
async def mutation_stability_stats():
    """Rollup of stability logs: success_rate, avg_pf, avg_trades, avg_drawdown,
    and rejection_reasons distribution (per-type and global)."""
    return await me.get_stability_stats()


# ── Phase 15 — Evolution Loop endpoint ───────────────────────────────

@router.get("/evolution/stats")
async def mutation_evolution_stats(
    regime: Optional[str] = Query(None, description="Filter by regime_type (Phase 16)"),
):
    """Evolution Loop diagnostics: per-mutation_type weights + scores.

    `active=true` means weights are already driving variant selection in
    `run_mutation_pipeline`. When `active=false`, selection falls back to
    the legacy deterministic path and weights shown here are what *would*
    apply once enough stability logs accumulate.

    Phase 16 — pass `?regime=trending|ranging|high_volatility|low_volatility`
    to see regime-specific weights (activation threshold: 20 logs per regime)."""
    from engines.evolution_engine import get_evolution_stats
    return await get_evolution_stats(regime_type=regime)


# ── Phase 16 — Regime classification endpoint ────────────────────────

@router.get("/regime/classify")
async def mutation_regime_classify(
    pair: str = Query(..., description="e.g. EURUSD"),
    timeframe: str = Query(..., description="e.g. H1"),
    window: int = Query(100, ge=30, le=500),
):
    """Classify the current regime for `pair/timeframe` using the most
    recent BID candles stored in MongoDB (same data path the dashboard
    and mutation pipeline use). Returns regime + the raw metrics."""
    from api.dashboard import _load_real_prices
    from engines.regime_classifier import describe_regime
    # `_load_real_prices` returns a 3-tuple `(prices, highs, lows)` —
    # regime classification is close-only so we keep just the prices.
    prices, _highs, _lows = await _load_real_prices(pair.upper(), timeframe.upper())
    if not prices:
        raise HTTPException(
            status_code=400,
            detail=f"No BID candles for {pair.upper()}/{timeframe.upper()}. "
                   f"Download via Market Data tab first.",
        )
    info = describe_regime(prices, window=window)
    info["pair"] = pair.upper()
    info["timeframe"] = timeframe.upper()
    info["data_points"] = len(prices)
    return info
