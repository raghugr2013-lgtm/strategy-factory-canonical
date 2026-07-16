"""Phase F — /api/brain/* endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines.brain import (
    brain_tick, compute_risk_budget, detect_transition,
    estimate_execution_quality,
)
from engines.brain import config as bcfg

router = APIRouter(prefix="/brain", tags=["brain"])


class TickIn(BaseModel):
    portfolio_members: List[Dict[str, Any]] = Field(default_factory=list)
    prices:             Optional[List[float]] = None
    open_positions:     int = 0
    execution_metadata: Optional[Dict[str, Any]] = None
    pair:               str = "EURUSD"
    timeframe:          str = "H1"


@router.post("/tick")
async def brain_tick_endpoint(payload: TickIn):
    """Run one brain tick on supplied portfolio + market inputs. Returns
    the full BrainReport with signals, decisions, pre_staged, emergency
    zeroes, risk budget, policy weights, and outcome-event ids."""
    r = await brain_tick(
        payload.portfolio_members, prices=payload.prices,
        open_positions=payload.open_positions,
        execution_metadata=payload.execution_metadata,
        pair=payload.pair, timeframe=payload.timeframe,
    )
    return r.to_dict()


@router.get("/signals")
async def brain_signals(pair: str = Query("EURUSD"),
                         timeframe: str = Query("H1")):
    """Read-only snapshot of the current signal set."""
    from engines.brain.signals import collect_signals
    s = await collect_signals(pair=pair, timeframe=timeframe)
    return s.to_dict()


@router.get("/regime-transition")
async def brain_regime_transition(pair: str = Query("EURUSD"),
                                    timeframe: str = Query("H1")):
    import math
    prices = [round(1.08 + 0.001 * math.sin(i / 12.0), 5) for i in range(200)]
    return detect_transition(prices).to_dict()


@router.get("/policy/weights")
async def brain_policy_weights():
    return {
        "weights": bcfg.scoring_weights(),
        "thresholds": {
            "trade_now": bcfg.trade_now_threshold(),
            "pause":     bcfg.pause_threshold(),
            "retire":    bcfg.retire_threshold(),
            "transition_min": bcfg.transition_prob_min(),
        },
        "gradual_evolution": {
            "max_weight_delta_per_tick": bcfg.max_weight_delta_per_tick(),
            "pre_stage_shadow_weight":   bcfg.pre_stage_shadow_weight(),
            "emergency_dd_pct":          bcfg.emergency_dd_pct(),
            "emergency_confidence":      bcfg.emergency_confidence(),
            "emergency_prediction_accuracy": bcfg.emergency_prediction_accuracy(),
        },
        "risk_budget": {
            "max_concurrent_trades": bcfg.risk_max_concurrent_trades(),
            "headroom_hard_block":   bcfg.risk_headroom_hard_block(),
        },
    }


class ExecQualityIn(BaseModel):
    spread_pips:   Optional[float] = None
    latency_ms:    Optional[float] = None
    slippage_pips: Optional[float] = None
    reject_rate:   Optional[float] = None
    broker_health: Optional[str]   = None
    fill_quality:  Optional[str]   = None


@router.post("/execution-quality")
async def brain_execution_quality(payload: ExecQualityIn):
    eq = estimate_execution_quality(**payload.model_dump())
    return eq.to_dict()


@router.get("/risk-budget")
async def brain_risk_budget(open_positions: int = 0,
                              avg_correlation: Optional[float] = None):
    return compute_risk_budget(
        open_positions=open_positions, avg_correlation=avg_correlation).to_dict()
