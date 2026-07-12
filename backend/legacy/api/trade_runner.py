"""Phase 5 — Trade Runner API.

Endpoints mounted at `/api/trade-runner`:

    POST /start           — create a run from a saved portfolio
    POST /step/{run_id}   — advance N simulated trading rounds
    POST /stop/{run_id}   — stop an active run
    GET  /status/{run_id} — run state + last N trades
    GET  /runs            — list recent runs (history)
    GET  /config          — default limits + constants

Isolated additive layer. Does NOT touch Portfolio Builder, Auto
Selection, Prop Firm engines, or the existing Phase-8/9 `/api/execution`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import trade_runner_engine as tre

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trade-runner", tags=["trade-runner"])


class StartRequest(BaseModel):
    portfolio_id: Optional[str] = None          # falls back to latest saved
    account_balance: float = Field(tre.DEFAULT_ACCOUNT_BALANCE, gt=0, le=10_000_000)
    mode: str = Field(tre.DEFAULT_MODE, pattern="^(paper|live)$")
    daily_loss_limit_pct: float = Field(tre.DEFAULT_DAILY_LOSS_LIMIT_PCT, gt=0, le=100)
    total_loss_limit_pct: float = Field(tre.DEFAULT_TOTAL_LOSS_LIMIT_PCT, gt=0, le=100)
    reward_ratio: float = Field(tre.DEFAULT_REWARD_RATIO, gt=0, le=10)
    seed: Optional[int] = None


class StepRequest(BaseModel):
    steps: int = Field(1, ge=1, le=200)


@router.post("/start")
async def start(req: StartRequest):
    try:
        run = await tre.start_run(
            portfolio_id=req.portfolio_id,
            account_balance=req.account_balance,
            mode=req.mode,
            daily_loss_limit_pct=req.daily_loss_limit_pct,
            total_loss_limit_pct=req.total_loss_limit_pct,
            reward_ratio=req.reward_ratio,
            seed=req.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("trade-runner: start failed")
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "started", "run": run}


@router.post("/step/{run_id}")
async def step(run_id: str, req: StepRequest):
    try:
        return await tre.step_run(run_id, steps=req.steps)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("trade-runner: step failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop/{run_id}")
async def stop(run_id: str):
    try:
        run = await tre.stop_run(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "stopped", "run": run}


@router.get("/status/{run_id}")
async def status(
    run_id: str,
    trade_limit: int = Query(25, ge=1, le=500),
):
    try:
        return await tre.get_run(run_id, trade_limit=trade_limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/runs")
async def runs(limit: int = Query(10, ge=1, le=50)):
    rows = await tre.list_runs(limit=limit)
    return {"count": len(rows), "runs": rows}


@router.get("/config")
async def config():
    return {
        "defaults": {
            "account_balance": tre.DEFAULT_ACCOUNT_BALANCE,
            "daily_loss_limit_pct": tre.DEFAULT_DAILY_LOSS_LIMIT_PCT,
            "total_loss_limit_pct": tre.DEFAULT_TOTAL_LOSS_LIMIT_PCT,
            "reward_ratio": tre.DEFAULT_REWARD_RATIO,
            "mode": tre.DEFAULT_MODE,
        },
        "modes": ["paper"],       # live deliberately disabled in Phase 5
    }
