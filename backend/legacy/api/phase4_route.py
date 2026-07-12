"""
Phase 4 route mounting — mirrors the Phase 10 pattern.

The preview ingress allow-list lags behind new sub-routers, so instead
of exposing the Phase 4 matcher under its own prefix we mount it
directly on `strategies_router` (already allow-listed via /api).

`from api import phase4_route` in server.py is all that's needed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import HTTPException
from pydantic import BaseModel

from api.strategies import router as strategies_router
from engines.db import get_db
from engines.phase4_matcher import match_strategy_phase4

logger = logging.getLogger(__name__)


class MatchFirmsPhase4Request(BaseModel):
    strategy_id: Optional[str] = None
    strategy_trades: Optional[List[Dict[str, Any]]] = None
    strategy_text: Optional[str] = None
    pair: Optional[str] = "EURUSD"
    timeframe: Optional[str] = "H1"
    # Phase 19 — bounds relaxed (only obviously-invalid is rejected here;
    # human-readable validation runs in the handler via match_input_validator).
    initial_balance: float = 10000
    n_simulations: int = 30
    # Phase 19 — relaxed/exploration mode for early-stage strategies.
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
    return (
        trades,
        doc.get("validation") or None,
        {
            "id": str(doc["_id"]),
            "pair": doc.get("pair", ""),
            "timeframe": doc.get("timeframe", ""),
        },
    )


async def _trades_from_backtest(strategy_text: str, pair: str, timeframe: str):
    from engines.backtest_engine import run_backtest_logic
    from api.strategies import _load_real_data

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


@strategies_router.post("/match-firms-phase4")
async def match_firms_phase4_route(req: MatchFirmsPhase4Request):
    """
    Phase-4 matcher — returns firm×plan ranked matches with pass probability,
    expected value, risk (LOW/MEDIUM/HIGH) and verdict (BEST/SAFE/RISKY).
    Stateless, additive, reuses the existing matching engine.

    Phase 19 additions:
      • Pydantic bounds relaxed; human-readable validation done in handler.
      • `relaxed_mode=true` → allow exploration matches with low trade
        counts (matcher's own variance / sharpe haircuts still apply).
      • Every response carries a `diagnostics` envelope describing
        what the matcher saw (trade count, equity curve, daily DD,
        consistency metrics, missing fields).
    """
    from engines.match_input_validator import (
        diagnostics_block,
        is_actionable_for_match,
        validate_match_inputs,
    )

    # Pre-flight numeric validation (clear 400 instead of Pydantic 422).
    ok, why = validate_match_inputs(
        req.initial_balance, req.n_simulations,
        relaxed_mode=req.relaxed_mode,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=why)

    trades = req.strategy_trades
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
    # Phase 19 — diagnostics envelope on success.
    result["diagnostics"] = diagnostics_block(
        trades, initial_balance=req.initial_balance,
        n_simulations=req.n_simulations, relaxed_mode=req.relaxed_mode,
    )
    return {"matching": result}
