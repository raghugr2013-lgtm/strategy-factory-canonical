"""Phase 5 — Trade Runner Engine (paper execution).

Isolated paper-execution layer that consumes a saved Portfolio Builder
snapshot and simulates trade flow under prop-firm-style risk controls.

Design goals (per Phase 5 spec):
    • SL-based position sizing     (risk_usd = balance × risk_pct)
    • Daily DD + Total DD limits   (hard halt on breach)
    • Go/No-Go gating before every trade
    • Trade ledger with PnL / winrate / drawdown
    • Paper mode default (live mode deliberately out-of-scope)

Additive only. NOT modified:
    • Portfolio Builder engine
    • Auto Selection engine
    • Prop Firm rule / matching engines
    • Phase-7 `portfolio_engine` or Phase-8/9 `execution_manager`
      (they live in their own collections; we use dedicated
       `trade_runner_runs` / `trade_runner_trades` collections).

Future hooks (not built): cTrader bridge, live tracking stream-in,
Auto-Factory callback on halt.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

RUNS_COLL = "trade_runner_runs"
TRADES_COLL = "trade_runner_trades"
PORTFOLIO_COLL = "portfolio_builder_runs"   # read-only dependency

# ── Default risk limits (prop-firm style) ─────────────────────────────
DEFAULT_ACCOUNT_BALANCE = 10_000.0
DEFAULT_DAILY_LOSS_LIMIT_PCT = 5.0
DEFAULT_TOTAL_LOSS_LIMIT_PCT = 10.0
DEFAULT_REWARD_RATIO = 1.0           # 1R per trade
DEFAULT_MODE = "paper"               # "paper" only for now


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_date(ts_iso: Optional[str] = None) -> str:
    if ts_iso:
        return ts_iso[:10]
    return datetime.now(timezone.utc).date().isoformat()


# ── Portfolio loader ───────────────────────────────────────────────────
async def load_portfolio(portfolio_id: str) -> Dict[str, Any]:
    """Read a saved Portfolio Builder snapshot. Never mutates it."""
    db = get_db()
    doc = await db[PORTFOLIO_COLL].find_one(
        {"portfolio_id": portfolio_id}, {"_id": 0},
    )
    if not doc:
        raise ValueError(f"portfolio not found: {portfolio_id}")
    meta = doc.get("meta") or {}
    if not meta.get("strategies"):
        raise ValueError(f"portfolio has no strategies: {portfolio_id}")
    return doc


async def _latest_portfolio() -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[PORTFOLIO_COLL].find_one(
        {}, {"_id": 0}, sort=[("saved_at", -1)],
    )


# ── Position sizing (SL-based) ─────────────────────────────────────────
def compute_position(
    *,
    account_balance: float,
    risk_pct: float,
    sl_pips: float = 30.0,
    pip_value_per_lot: float = 10.0,
) -> Dict[str, float]:
    """SL-based sizing:
        risk_usd   = balance × risk_pct / 100
        lot_size   = risk_usd / (sl_pips × pip_value_per_lot)

    Returns both so the trade ledger can show the sizing math without the
    caller having to recompute."""
    risk_usd = max(0.0, account_balance * (risk_pct / 100.0))
    denom = max(0.0001, sl_pips * pip_value_per_lot)
    lot_size = round(risk_usd / denom, 3)
    return {
        "risk_usd": round(risk_usd, 2),
        "lot_size": lot_size,
        "sl_pips": sl_pips,
    }


# ── Win-rate proxy from PF ─────────────────────────────────────────────
def _win_rate_from_pf(pf: Optional[float], reward_ratio: float) -> float:
    """With 1R SL and `reward_ratio` R TP:
        PF = wr × R / ((1 - wr) × 1)
        ⇒ wr = PF / (PF + R)
    Falls back to 0.5 when PF missing."""
    try:
        p = float(pf or 0.0)
    except (TypeError, ValueError):
        p = 0.0
    if p <= 0:
        return 0.5
    return max(0.25, min(0.85, p / (p + reward_ratio)))


# ── Go / No-Go gate ────────────────────────────────────────────────────
def go_no_go(run: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate whether new trades are allowed on this run. Returns a
    structured verdict so the UI can surface the reason."""
    if run.get("status") != "running":
        return {"allow": False, "reason": f"run_{run.get('status')}"}
    limits = run.get("limits") or {}
    daily_limit = float(limits.get("daily_loss_limit_pct") or DEFAULT_DAILY_LOSS_LIMIT_PCT)
    total_limit = float(limits.get("total_loss_limit_pct") or DEFAULT_TOTAL_LOSS_LIMIT_PCT)
    daily_loss_pct = run.get("daily_loss_pct") or 0.0
    total_loss_pct = run.get("total_loss_pct") or 0.0
    if daily_loss_pct >= daily_limit:
        return {"allow": False, "reason": "daily_loss_limit"}
    if total_loss_pct >= total_limit:
        return {"allow": False, "reason": "total_loss_limit"}
    return {"allow": True, "reason": "ok"}


def _check_and_halt(run: Dict[str, Any]) -> None:
    """Mutate run in-place: flip to halted if any risk limit is breached."""
    verdict = go_no_go(run)
    if not verdict["allow"] and run.get("status") == "running":
        run["status"] = "halted"
        run["halted_reason"] = verdict["reason"]
        run["halted_at"] = _now_iso()


# ── Run lifecycle ──────────────────────────────────────────────────────
async def start_run(
    *,
    portfolio_id: Optional[str] = None,
    account_balance: float = DEFAULT_ACCOUNT_BALANCE,
    mode: str = DEFAULT_MODE,
    daily_loss_limit_pct: float = DEFAULT_DAILY_LOSS_LIMIT_PCT,
    total_loss_limit_pct: float = DEFAULT_TOTAL_LOSS_LIMIT_PCT,
    reward_ratio: float = DEFAULT_REWARD_RATIO,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Create an active run backed by a saved portfolio."""
    if mode not in ("paper", "live"):
        raise ValueError(f"unsupported mode: {mode}")
    if mode == "live":
        raise ValueError("live mode not implemented (paper only in Phase 5)")

    if portfolio_id:
        port = await load_portfolio(portfolio_id)
    else:
        port = await _latest_portfolio()
        if not port:
            raise ValueError("no saved portfolio available — build+save one first")
        portfolio_id = port.get("portfolio_id")

    meta = port.get("meta") or {}
    strategies = meta.get("strategies") or []
    allocation = meta.get("allocation") or {}

    per_strategy: List[Dict[str, Any]] = []
    for s in strategies:
        h = s.get("strategy_hash")
        alloc = allocation.get(h) or {}
        per_strategy.append({
            "strategy_hash": h,
            "strategy_name": s.get("strategy_name"),
            "pair": s.get("pair"),
            "timeframe": s.get("timeframe"),
            "firm_slug": s.get("firm_slug"),
            "challenge": s.get("challenge"),
            "status": "active",
            "risk_pct": float(alloc.get("risk_pct") or 0.0),
            "pf": s.get("strategy_best_pf"),
            "win_rate": round(_win_rate_from_pf(s.get("strategy_best_pf"), reward_ratio), 3),
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "pnl": 0.0,
        })

    run_id = f"tr_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    run: Dict[str, Any] = {
        "run_id": run_id,
        "portfolio_id": portfolio_id,
        "mode": mode,
        "status": "running",
        "started_at": now,
        "halted_at": None,
        "halted_reason": None,
        "seed": seed,
        "limits": {
            "daily_loss_limit_pct": daily_loss_limit_pct,
            "total_loss_limit_pct": total_loss_limit_pct,
            "reward_ratio": reward_ratio,
        },
        "account_balance_start": float(account_balance),
        "equity": float(account_balance),
        "peak_equity": float(account_balance),
        "daily_start_equity": float(account_balance),
        "daily_start_date": _utc_date(now),
        "daily_loss_pct": 0.0,
        "total_loss_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "trades_count": 0,
        "wins_count": 0,
        "losses_count": 0,
        "pnl": 0.0,
        "strategies": per_strategy,
    }

    db = get_db()
    # Insert a deep-copied doc so Mongo can't pollute the returned dict
    # with an _id. `run` stays projection-clean for the HTTP response.
    await db[RUNS_COLL].insert_one({**run})
    return run


async def _load_run(run_id: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db[RUNS_COLL].find_one({"run_id": run_id}, {"_id": 0})
    if not doc:
        raise ValueError(f"run not found: {run_id}")
    return doc


async def _save_run(run: Dict[str, Any]) -> None:
    db = get_db()
    # Snapshot (full replace of the run doc, excluding any Mongo _id).
    payload = {k: v for k, v in run.items() if k != "_id"}
    await db[RUNS_COLL].update_one(
        {"run_id": run["run_id"]},
        {"$set": payload},
        upsert=True,
    )


# ── Daily reset (auto on date rollover) ────────────────────────────────
def _maybe_reset_daily(run: Dict[str, Any]) -> None:
    today = _utc_date()
    if run.get("daily_start_date") != today:
        run["daily_start_date"] = today
        run["daily_start_equity"] = run.get("equity", run.get("account_balance_start"))
        run["daily_loss_pct"] = 0.0
        if run.get("status") == "halted" and run.get("halted_reason") == "daily_loss_limit":
            # Daily halt clears at the date boundary — total halt does not.
            run["status"] = "running"
            run["halted_reason"] = None
            run["halted_at"] = None


# ── Trade simulation (paper mode) ──────────────────────────────────────
def _simulate_trade(
    strategy: Dict[str, Any],
    *,
    equity: float,
    reward_ratio: float,
    rng: random.Random,
) -> Dict[str, Any]:
    risk_pct = float(strategy.get("risk_pct") or 0.0)
    win_rate = float(strategy.get("win_rate") or 0.5)
    sizing = compute_position(account_balance=equity, risk_pct=risk_pct)
    won = rng.random() < win_rate
    direction = "BUY" if rng.random() < 0.5 else "SELL"
    pnl = sizing["risk_usd"] * reward_ratio if won else -sizing["risk_usd"]
    return {
        "strategy_hash": strategy["strategy_hash"],
        "strategy_name": strategy.get("strategy_name"),
        "pair": strategy.get("pair"),
        "timeframe": strategy.get("timeframe"),
        "direction": direction,
        "lot_size": sizing["lot_size"],
        "sl_pips": sizing["sl_pips"],
        "risk_usd": sizing["risk_usd"],
        "pnl": round(pnl, 2),
        "result": "WIN" if won else "LOSS",
        "executed_at": _now_iso(),
    }


def _update_run_after_trade(run: Dict[str, Any], trade: Dict[str, Any]) -> None:
    run["equity"] = round(run["equity"] + trade["pnl"], 2)
    run["peak_equity"] = max(run["peak_equity"], run["equity"])
    run["trades_count"] += 1
    if trade["result"] == "WIN":
        run["wins_count"] += 1
    else:
        run["losses_count"] += 1
    run["pnl"] = round(run["equity"] - run["account_balance_start"], 2)

    start_bal = run["account_balance_start"] or 1.0
    daily_loss = max(0.0, run["daily_start_equity"] - run["equity"])
    total_loss = max(0.0, run["account_balance_start"] - run["equity"])
    dd = max(0.0, run["peak_equity"] - run["equity"])
    run["daily_loss_pct"] = round(daily_loss / start_bal * 100.0, 3)
    run["total_loss_pct"] = round(total_loss / start_bal * 100.0, 3)
    run["max_drawdown_pct"] = round(
        max(run["max_drawdown_pct"], dd / start_bal * 100.0), 3,
    )

    # Update per-strategy rollup
    for s in run["strategies"]:
        if s["strategy_hash"] == trade["strategy_hash"]:
            s["trades"] += 1
            if trade["result"] == "WIN":
                s["wins"] += 1
            else:
                s["losses"] += 1
            s["pnl"] = round(s["pnl"] + trade["pnl"], 2)
            break


async def step_run(run_id: str, steps: int = 1) -> Dict[str, Any]:
    """Advance the simulator by `steps` rounds. Each round fires one
    trade per active strategy subject to Go/No-Go. Early-exits on halt."""
    steps = max(1, min(int(steps), 200))
    run = await _load_run(run_id)
    _maybe_reset_daily(run)

    if run["status"] != "running":
        return {
            "run": run,
            "executed": [],
            "executed_count": 0,
            "skipped_reason": run.get("halted_reason") or run["status"],
        }

    rng = random.Random(run.get("seed"))
    # Deterministic bump so repeated /step calls don't repeat outcomes
    rng.seed((run.get("seed") or 0) + run["trades_count"] * 7919 + 17)

    reward_ratio = float((run.get("limits") or {}).get("reward_ratio") or DEFAULT_REWARD_RATIO)
    executed: List[Dict[str, Any]] = []
    db = get_db()

    for _ in range(steps):
        if run["status"] != "running":
            break
        for s in run["strategies"]:
            if run["status"] != "running":
                break
            if s.get("status") != "active":
                continue
            verdict = go_no_go(run)
            if not verdict["allow"]:
                _check_and_halt(run)
                break
            trade = _simulate_trade(
                s, equity=run["equity"],
                reward_ratio=reward_ratio, rng=rng,
            )
            trade["run_id"] = run_id
            _update_run_after_trade(run, trade)
            _check_and_halt(run)
            executed.append(trade)

    if executed:
        await db[TRADES_COLL].insert_many([{**t} for t in executed])
    await _save_run(run)

    return {
        "run": run,
        "executed": [{k: v for k, v in t.items() if k != "_id"} for t in executed],
        "executed_count": len(executed),
    }


async def stop_run(run_id: str) -> Dict[str, Any]:
    run = await _load_run(run_id)
    if run["status"] in ("stopped", "halted"):
        return run
    run["status"] = "stopped"
    run["halted_at"] = _now_iso()
    await _save_run(run)
    return run


async def get_run(run_id: str, *, trade_limit: int = 25) -> Dict[str, Any]:
    run = await _load_run(run_id)
    _maybe_reset_daily(run)
    db = get_db()
    trades_cursor = (
        db[TRADES_COLL]
        .find({"run_id": run_id}, {"_id": 0})
        .sort("executed_at", -1)
        .limit(max(1, min(trade_limit, 500)))
    )
    trades = [t async for t in trades_cursor]
    return {"run": run, "trades": trades}


async def list_runs(limit: int = 10) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = (
        db[RUNS_COLL]
        .find({}, {"_id": 0})
        .sort("started_at", -1)
        .limit(max(1, min(limit, 50)))
    )
    return [d async for d in cursor]
