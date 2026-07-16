"""Phase C — /api/intelligence/* endpoints.

Read-only advisory endpoints (except `bundles/build` which mutates via the
existing `master_bot_engine.set_tier_metadata` if `persist=true`). Additive
over the existing master-bot / ranking / regime routers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines.intelligence import (
    build_tiered_bundles,
    classify_strategy,
    current_regime,
    emit_decision,
    portfolio_contribution_score,
    select_active_strategy,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class ClassifyIn(BaseModel):
    strategy_text: str = Field(default="")
    profit_factor: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    total_trades: Optional[int] = None
    win_rate: Optional[float] = None
    strategy_hash: Optional[str] = None


@router.post("/classify")
async def intelligence_classify(payload: ClassifyIn):
    doc = payload.model_dump()
    cls = classify_strategy(doc)
    await emit_decision(
        "strategy_classification",
        strategy_hash=cls.strategy_hash,
        reason=f"style={cls.style} conf={cls.confidence}",
        metrics={"style": cls.style, "confidence": cls.confidence},
        evidence=cls.evidence,
    )
    return cls.to_dict()


class ContribIn(BaseModel):
    candidate: Dict[str, Any]
    existing_bundle: List[Dict[str, Any]] = Field(default_factory=list)


@router.post("/portfolio-score")
async def intelligence_portfolio_score(payload: ContribIn):
    ps = portfolio_contribution_score(payload.candidate, payload.existing_bundle)
    return ps.to_dict()


class BuildBundleIn(BaseModel):
    strategies: List[Dict[str, Any]] = Field(default_factory=list)
    min_contribution: float = 0.05
    persist: bool = False
    master_bot_id: Optional[str] = None


@router.post("/bundles/build")
async def intelligence_build_bundles(
    payload: BuildBundleIn,
    _u=Depends(require_admin),
):
    if not payload.strategies:
        raise HTTPException(status_code=400, detail={"code": "no_strategies"})
    report = build_tiered_bundles(
        payload.strategies,
        min_contribution=payload.min_contribution,
    )
    await emit_decision(
        "master_bot_bundle_built",
        reason=f"accepted={report.accepted} rejected={report.rejected}",
        metrics={
            "pool_size":     report.pool_size,
            "accepted":      report.accepted,
            "tier_1_size":   len(report.tier_1),
            "tier_2_size":   len(report.tier_2),
            "tier_3_size":   len(report.tier_3),
        },
        evidence={"style_balance": report.style_balance},
    )
    persisted = None
    if payload.persist and payload.master_bot_id:
        try:
            from engines.master_bot_engine import set_tier_metadata
            persisted = {
                "tier_1": await set_tier_metadata(
                    payload.master_bot_id, "tier_1",
                    {"strategies": [s["strategy_hash"] for s in report.tier_1]},
                ),
                "tier_2": await set_tier_metadata(
                    payload.master_bot_id, "tier_2",
                    {"strategies": [s["strategy_hash"] for s in report.tier_2]},
                ),
                "tier_3": await set_tier_metadata(
                    payload.master_bot_id, "tier_3",
                    {"strategies": [s["strategy_hash"] for s in report.tier_3]},
                ),
            }
        except Exception as e:                                # noqa: BLE001
            persisted = {"error": str(e)[:200]}
    return {"report": report.to_dict(), "persisted": persisted}


@router.get("/regime")
async def intelligence_regime(
    pair: str = Query(default="EURUSD"),
    timeframe: str = Query(default="H1"),
):
    snap = await current_regime(pair=pair, timeframe=timeframe)
    await emit_decision(
        "market_regime_detected",
        reason=f"{pair}/{timeframe}: {snap.regime} conf={snap.confidence}",
        metrics={"regime": snap.regime, "confidence": snap.confidence,
                 "pair": pair, "timeframe": timeframe},
        evidence=snap.evidence,
    )
    return snap.to_dict()


class ActivateIn(BaseModel):
    bundle: List[Dict[str, Any]] = Field(default_factory=list)
    pair: str = "EURUSD"
    timeframe: str = "H1"
    regime_override: Optional[str] = None


@router.post("/activate")
async def intelligence_activate(payload: ActivateIn):
    """Given a Master Bot bundle, return the strategy the bot should
    activate right now for the current regime.

    Bundle elements should already be classified (as returned from
    `/intelligence/classify` or `/intelligence/bundles/build`).
    """
    if payload.regime_override:
        regime = payload.regime_override
    else:
        snap = await current_regime(pair=payload.pair, timeframe=payload.timeframe)
        regime = snap.regime
    decision = select_active_strategy(payload.bundle, regime)
    await emit_decision(
        "dynamic_activation",
        strategy_hash=decision.active_hash,
        reason=decision.reason,
        metrics={
            "regime":            decision.regime,
            "activation_score":  decision.activation_score,
            "active_style":      decision.active_style,
            "pair":              payload.pair,
            "timeframe":         payload.timeframe,
        },
        evidence={"candidates": decision.candidates},
    )
    return decision.to_dict()
