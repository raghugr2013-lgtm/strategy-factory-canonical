"""
Phase 8 — Live Execution API.

Thin FastAPI surface over `engines.execution_manager`. No broker IO in this
phase — paper mode only (or cBot-source emission for manual deploy).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines import execution_manager as em
from engines import paper_execution_engine as pex

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/execution", tags=["execution"])


class ExecutionStartRequest(BaseModel):
    portfolio_run_id: Optional[str] = None
    portfolio: Optional[Dict[str, Any]] = None
    account_balance: float = Field(10000.0, gt=0)
    mode: str = Field("paper", pattern="^(paper|cbot)$")
    risk_limits: Optional[Dict[str, float]] = None


class ExecutionStopRequest(BaseModel):
    session_id: str
    reason: str = "manual"


@router.post("/start")
async def execution_start(req: ExecutionStartRequest):
    """Start a live-execution session bound to a Phase-7 portfolio.
    Generates compile-checked cBots per strategy and seeds the Go/No-Go gate."""
    try:
        session = await em.start_execution(
            portfolio_run_id=req.portfolio_run_id,
            portfolio=req.portfolio,
            account_balance=req.account_balance,
            mode=req.mode,
            risk_limits=req.risk_limits,
        )
    except RuntimeError as e:
        if str(e).startswith("already_active"):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("execution_start failed")
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "session": session}


@router.post("/stop")
async def execution_stop(req: ExecutionStopRequest):
    """Graceful stop — session persists in Mongo for audit."""
    try:
        session = await em.stop_execution(req.session_id, reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "session": session}


@router.post("/emergency-stop")
async def execution_emergency_stop():
    """Hard stop — force-halts the currently active session (if any)."""
    try:
        return {"success": True, **await em.emergency_stop()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def execution_status(history_limit: int = 10):
    """Active session (with fresh Go/No-Go) + recent history."""
    try:
        return await em.get_status(history_limit=history_limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cbot/{session_id}/{strategy_id}")
async def execution_cbot(session_id: str, strategy_id: str):
    """Return the generated cBot source for a strategy inside a session."""
    from engines.db import get_db
    db = get_db()
    session = await db["execution_sessions"].find_one(
        {"session_id": session_id}, {"_id": 0, "cbots": 1}
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    for c in session.get("cbots", []):
        if c.get("strategy_id") == strategy_id:
            return c
    raise HTTPException(status_code=404, detail="strategy not found in session")


# ═════════════════════════════════════════════════════════════════════
# Paper Execution (Safe historical-replay simulation)
# ═════════════════════════════════════════════════════════════════════

class PaperStartRequest(BaseModel):
    portfolio_id: Optional[str] = None
    account_balance: float = Field(pex.DEFAULT_ACCOUNT_BALANCE, gt=0, le=10_000_000)
    risk_pct: Optional[float] = Field(None, gt=0, le=10)
    daily_loss_limit_pct: float = Field(pex.DEFAULT_DAILY_LOSS_LIMIT_PCT, gt=0, le=100)
    total_loss_limit_pct: float = Field(pex.DEFAULT_TOTAL_LOSS_LIMIT_PCT, gt=0, le=100)
    tick_ms: int = Field(pex.DEFAULT_TICK_MS, ge=5, le=10_000)
    bars_limit: int = Field(pex.DEFAULT_BARS_LIMIT, ge=100, le=20_000)
    source: str = Field(pex.DEFAULT_SOURCE, pattern="^(bid_1m|bi5)$")
    slippage_pips: float = Field(0.5, ge=0, le=20)
    seed: Optional[int] = None


@router.post("/paper/start")
async def paper_start(req: PaperStartRequest):
    """Start a SAFE paper-trading run. Replays historical BID/BI5 bars
    through the portfolio-approved strategies and simulates trades.
    Tracks expected-vs-actual entry deviation and running PF vs backtest PF."""
    try:
        run = await pex.start_run(
            portfolio_id=req.portfolio_id,
            account_balance=req.account_balance,
            risk_pct=req.risk_pct,
            daily_loss_limit_pct=req.daily_loss_limit_pct,
            total_loss_limit_pct=req.total_loss_limit_pct,
            tick_ms=req.tick_ms,
            bars_limit=req.bars_limit,
            source=req.source,
            slippage_pips=req.slippage_pips,
            seed=req.seed,
        )
    except RuntimeError as e:
        if str(e).startswith("already_active"):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("paper-exec start failed")
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "started", "run": run}


class PaperStopRequest(BaseModel):
    run_id: str


@router.post("/paper/stop")
async def paper_stop(req: PaperStopRequest):
    try:
        run = await pex.stop_run(req.run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "stopped", "run": run}


@router.get("/paper/status")
async def paper_status(
    run_id: Optional[str] = None,
    trade_limit: int = 25,
):
    """Snapshot of the active (or most recent) paper run with its latest
    trades and equity curve."""
    try:
        return await pex.get_status(run_id=run_id, trade_limit=trade_limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("paper-exec status failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper/trades")
async def paper_trades(run_id: Optional[str] = None, limit: int = 100):
    try:
        trades = await pex.list_trades(run_id=run_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"count": len(trades), "trades": trades}


@router.get("/paper/equity")
async def paper_equity(run_id: str, limit: int = 1000):
    try:
        curve = await pex.list_equity(run_id=run_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"count": len(curve), "equity_curve": curve}


@router.get("/paper/runs")
async def paper_runs(limit: int = 10):
    runs = await pex.list_runs(limit=limit)
    return {"count": len(runs), "runs": runs}


@router.get("/paper/deviation/{strategy_hash}")
async def paper_deviation(strategy_hash: str, limit: int = 100):
    history = await pex.deviation_history(strategy_hash=strategy_hash, limit=limit)
    return {"count": len(history), "history": history}


@router.get("/paper/deviation-alerts")
async def paper_deviation_alerts(limit: int = 25):
    """Recent deviation alert log (one entry per (run,strategy) that fired)."""
    from engines import paper_execution_alert_bridge as pdb
    rows = await pdb.recent_log(limit=limit)
    return {"count": len(rows), "alerts": rows}


@router.get("/paper/config")
async def paper_config():
    return {
        "defaults": {
            "account_balance": pex.DEFAULT_ACCOUNT_BALANCE,
            "risk_pct": pex.DEFAULT_RISK_PCT,
            "daily_loss_limit_pct": pex.DEFAULT_DAILY_LOSS_LIMIT_PCT,
            "total_loss_limit_pct": pex.DEFAULT_TOTAL_LOSS_LIMIT_PCT,
            "tick_ms": pex.DEFAULT_TICK_MS,
            "bars_limit": pex.DEFAULT_BARS_LIMIT,
            "source": pex.DEFAULT_SOURCE,
            "slippage_pips": 0.5,
        },
        "sources": ["bid_1m", "bi5"],
    }
