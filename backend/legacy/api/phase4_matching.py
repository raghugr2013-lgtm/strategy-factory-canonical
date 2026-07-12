"""
API routes for the Phase 4 Strategy ↔ Prop Firm Matcher.

Thin FastAPI surface over `engines.phase4_matcher`. Stateless — no
persistence. Additive — zero modifications to existing endpoints.

POST /api/phase4/match-firms
  Body (one of):
    { "strategy_id": "<mongo_id>" }
    { "strategy_trades": [ ... ], "initial_balance": 10000 }
    { "strategy_text": "...", "pair": "EURUSD", "timeframe": "H1" }
  Optional:
    "n_simulations": 30   (10–200, Monte Carlo runs per firm)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engines.db import get_db
from engines.phase4_matcher import match_strategy_phase4

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/phase4", tags=["phase4-matching"])


class MatchFirmsRequest(BaseModel):
    strategy_id: Optional[str] = None
    strategy_trades: Optional[List[Dict[str, Any]]] = None
    # On-the-fly backtest inputs (used when neither id nor trades are sent)
    strategy_text: Optional[str] = None
    pair: Optional[str] = "EURUSD"
    timeframe: Optional[str] = "H1"

    # Phase 19 — bounds relaxed; clear human errors come from the handler.
    initial_balance: float = 10000
    n_simulations: int = 30
    # Phase 19 — exploration mode for early-stage strategies.
    relaxed_mode: bool = False


async def _load_trades_from_db(strategy_id: str):
    db = get_db()
    try:
        doc = await db.strategies.find_one({"_id": ObjectId(strategy_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid strategy ID")
    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")

    bt = doc.get("backtest_results") or {}
    trades = bt.get("trades") or []
    if not trades:
        raise HTTPException(
            status_code=400,
            detail="Strategy has no backtest trades. Run a backtest first.",
        )
    validation_report = doc.get("validation") or None
    meta = {
        "id": str(doc["_id"]),
        "pair": doc.get("pair", ""),
        "timeframe": doc.get("timeframe", ""),
    }
    return trades, validation_report, meta


async def _trades_from_backtest(strategy_text: str, pair: str, timeframe: str):
    """Produce a trade list on the fly for dashboard strategies that
    don't carry `trades` in their payload."""
    from engines.backtest_engine import run_backtest_logic
    from api.strategies import _load_real_data  # reuse the shared loader

    prices, data_source, data_points, _, _ = await _load_real_data(pair, timeframe)
    bt = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=prices,
        data_source=data_source,
        data_points=data_points,
    )
    trades = bt.get("trades") or []
    if not trades:
        raise HTTPException(
            status_code=400,
            detail=f"Ad-hoc backtest produced 0 trades for {pair}/{timeframe}.",
        )
    return trades


@router.post("/match-firms")
async def match_firms_endpoint(req: MatchFirmsRequest):
    """
    Phase-4 matching endpoint — reshapes the existing matching engine
    output into the approved contract (firm, plan, score, pass_probability,
    expected_value, risk, verdict).

    Stateless: results are not persisted.

    Phase 19 additions: relaxed_mode flag + diagnostics envelope on every
    response. Pydantic bounds relaxed; clear human errors from the handler.
    """
    from engines.match_input_validator import (
        diagnostics_block,
        is_actionable_for_match,
        validate_match_inputs,
    )

    ok, why = validate_match_inputs(
        req.initial_balance, req.n_simulations,
        relaxed_mode=req.relaxed_mode,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=why)

    trades: Optional[List[dict]] = req.strategy_trades
    validation_report: Optional[Dict[str, Any]] = None
    strategy_meta: Optional[Dict[str, Any]] = None

    if req.strategy_id and trades is None:
        trades, validation_report, strategy_meta = await _load_trades_from_db(
            req.strategy_id
        )

    if trades is None and req.strategy_text and req.pair and req.timeframe:
        trades = await _trades_from_backtest(
            req.strategy_text, req.pair, req.timeframe
        )
        strategy_meta = {"pair": req.pair, "timeframe": req.timeframe}

    if not trades:
        diag = diagnostics_block(
            trades, initial_balance=req.initial_balance,
            n_simulations=req.n_simulations, relaxed_mode=req.relaxed_mode,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "Provide strategy_id, strategy_trades, or strategy_text+pair+timeframe.",
                "diagnostics": diag,
            },
        )

    actionable, why = is_actionable_for_match(trades, relaxed_mode=req.relaxed_mode)
    if not actionable:
        diag = diagnostics_block(
            trades, initial_balance=req.initial_balance,
            n_simulations=req.n_simulations, relaxed_mode=req.relaxed_mode,
        )
        raise HTTPException(
            status_code=400,
            detail={"reason": why, "diagnostics": diag},
        )

    try:
        result = await match_strategy_phase4(
            trades=trades,
            initial_balance=req.initial_balance,
            validation_report=validation_report,
            n_simulations=req.n_simulations,
        )
    except Exception as e:  # pragma: no cover
        logger.exception("Phase 4 matcher failed")
        raise HTTPException(status_code=500, detail=str(e))

    if strategy_meta:
        result["strategy"] = strategy_meta

    result["diagnostics"] = diagnostics_block(
        trades, initial_balance=req.initial_balance,
        n_simulations=req.n_simulations, relaxed_mode=req.relaxed_mode,
    )
    return {"matching": result}
