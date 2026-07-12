"""
Phase 8 — Live Execution Manager.

Orchestration layer that takes a Phase-7 portfolio output and runs it as a
live trading session. Additive — sits ALONGSIDE the existing
`execution_engine.py` (backtest realism), not on top of it.

Responsibilities:
  1. cBot generation per strategy — reuses `engines.cbot_pipeline.build_reliable_cbot`
     (generate → safety-inject → compile → auto-fix loop).
  2. Capital + risk allocation — ingested from `portfolio.allocation`
     (per-strategy `capital_pct` + `risk_per_trade_pct`).
  3. Go/No-Go gate — evaluates current DD, recent performance, and the
     emergency-stop flag before every decision tick.
  4. Live tracking — wraps `engines.live_tracking_engine.process_strategy_live`
     so live equity, DD, and trades are derived from the SAME signal logic
     as the validated backtest — no parallel implementation.
  5. Session state — persisted to the new `execution_sessions` collection.
     Only one session may be `active` at a time; start() returns 409 if busy.

Execution modes:
  - "paper"  (default) — signals + simulated fills only. Zero broker IO.
  - "cbot"             — generates the cTrader cBot source code per
                         strategy and returns it in the response for the
                         operator to deploy via the cTrader IDE. No auto-
                         connection (broker API is P1 backlog).

No broker API integration is wired in this phase — the engine returns the
ready-to-deploy cBot source as the artefact.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

SESSIONS = "execution_sessions"
TRACKING = "execution_tracking"

# ─────────────────────────────────────────────────────────────────────
# Risk-control defaults (per-session; overridable at start())
# ─────────────────────────────────────────────────────────────────────
DEFAULT_RISK_LIMITS: Dict[str, float] = {
    "max_daily_drawdown_pct": 5.0,
    "max_total_drawdown_pct": 10.0,
    "max_per_trade_risk_pct": 2.0,
    "recent_loss_streak_limit": 5,   # stop if N losing trades in a row
    "min_recent_profit_factor": 0.5, # over last 20 trades
}

# Mode guard — "paper" never sends orders; "cbot" only emits cBot source.
ALLOWED_MODES = ("paper", "cbot")

_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────
# Session helpers
# ─────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_active_session(db) -> Optional[dict]:
    return await db[SESSIONS].find_one({"status": "active"}, {"_id": 0})


async def _load_portfolio(db, portfolio_run_id: str) -> Optional[dict]:
    return await db["portfolios"].find_one(
        {"run_id": portfolio_run_id}, {"_id": 0}
    )


# ─────────────────────────────────────────────────────────────────────
# cBot generation
# ─────────────────────────────────────────────────────────────────────

def _make_strategy_profile(strategy: dict, alloc: dict) -> dict:
    """Shape the portfolio row + allocation into the profile that
    `build_reliable_cbot` expects. Reuses pair/timeframe/style + risk
    budget; leaves indicator details to the downstream parameter
    extractor (which the existing pipeline already runs)."""
    return {
        "pair": strategy.get("pair"),
        "timeframe": strategy.get("timeframe"),
        "style": strategy.get("style") or "trend-following",
        "strategy_text": strategy.get("strategy_text") or "",
        "parameters": strategy.get("parameters") or {},
        "risk_per_trade_pct": alloc.get("risk_per_trade_pct", 1.0),
        "capital_pct": alloc.get("capital_pct", 0.25),
        # Basic indicator set — code generator will infer defaults when empty.
        "indicators": {},
    }


async def _generate_cbot_for_strategy(strategy: dict, alloc: dict) -> dict:
    """Returns a per-strategy compile record. The cBot source, compile
    status, warnings, and bot_name all come from `build_reliable_cbot`."""
    try:
        from engines.cbot_pipeline import build_reliable_cbot
    except Exception as e:
        return {"compile_status": "error", "errors": [{"message": str(e)}]}

    profile = _make_strategy_profile(strategy, alloc)
    # Safety rules come from the strategy's own DD / panel when available.
    safety_rules = {
        "max_drawdown_pct": strategy.get("max_drawdown_pct"),
        "max_per_trade_risk_pct": alloc.get("risk_per_trade_pct"),
    }
    result = build_reliable_cbot(profile, safety_rules)
    return {
        "bot_name": result.get("bot_name"),
        "compile_status": result.get("compile_status"),
        "attempts": result.get("attempts", 1),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
        "indicators_used": result.get("indicators_used"),
        "code_length": len(result.get("code", "")),
        "code": result.get("code"),  # surfaced so operator can deploy
    }


# ─────────────────────────────────────────────────────────────────────
# Go / No-Go decision gate
# ─────────────────────────────────────────────────────────────────────

def go_no_go(session: dict) -> Dict[str, Any]:
    """
    Evaluate whether the session may trade right now.

    Checks (in order — first BLOCK wins):
      • `emergency_stop` flag          → BLOCK "emergency_stop"
      • total_dd > max_total_dd_pct    → BLOCK "total_dd_breached"
      • daily_dd > max_daily_dd_pct    → BLOCK "daily_dd_breached"
      • recent loss streak ≥ limit     → BLOCK "loss_streak"
      • recent profit factor too low   → BLOCK "weak_recent_pf"

    Returns a verdict dict — `allow=False` with `reasons[]` on block,
    `allow=True` otherwise.
    """
    limits = {**DEFAULT_RISK_LIMITS, **(session.get("risk_limits") or {})}
    tracking = session.get("tracking") or {}
    reasons: List[str] = []

    if session.get("emergency_stop"):
        reasons.append("emergency_stop")

    total_dd = float(tracking.get("total_drawdown_pct") or 0.0)
    daily_dd = float(tracking.get("daily_drawdown_pct") or 0.0)
    loss_streak = int(tracking.get("loss_streak") or 0)
    recent_pf = float(tracking.get("recent_profit_factor") or 0.0)

    if total_dd >= float(limits["max_total_drawdown_pct"]):
        reasons.append(f"total_dd_breached ({total_dd}% ≥ {limits['max_total_drawdown_pct']}%)")
    if daily_dd >= float(limits["max_daily_drawdown_pct"]):
        reasons.append(f"daily_dd_breached ({daily_dd}% ≥ {limits['max_daily_drawdown_pct']}%)")
    if loss_streak >= int(limits["recent_loss_streak_limit"]):
        reasons.append(f"loss_streak ({loss_streak} ≥ {limits['recent_loss_streak_limit']})")
    if recent_pf > 0 and recent_pf < float(limits["min_recent_profit_factor"]):
        reasons.append(f"weak_recent_pf ({recent_pf} < {limits['min_recent_profit_factor']})")

    return {
        "allow": len(reasons) == 0,
        "verdict": "GO" if not reasons else "NO_GO",
        "reasons": reasons,
        "limits": limits,
        "observed": {
            "total_drawdown_pct": total_dd,
            "daily_drawdown_pct": daily_dd,
            "loss_streak": loss_streak,
            "recent_profit_factor": recent_pf,
            "emergency_stop": bool(session.get("emergency_stop")),
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Live tracking update — reuses live_tracking_engine
# ─────────────────────────────────────────────────────────────────────

def _aggregate_tracking(per_strategy: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll per-strategy live metrics into a session-wide tracking dict."""
    if not per_strategy:
        return {
            "equity": 0.0, "total_drawdown_pct": 0.0, "daily_drawdown_pct": 0.0,
            "total_trades": 0, "loss_streak": 0,
            "recent_profit_factor": 0.0, "win_rate": 0.0,
        }

    # Capital-weighted composite drawdown + weighted PF.
    total_w = sum(float(s.get("capital_pct") or 0.0) for s in per_strategy) or 1.0
    total_dd = sum(
        float(s.get("capital_pct") or 0.0) * float(s.get("live_dd_pct") or 0.0)
        for s in per_strategy
    ) / total_w
    daily_dd = sum(
        float(s.get("capital_pct") or 0.0) * float(s.get("live_daily_dd_pct") or 0.0)
        for s in per_strategy
    ) / total_w

    total_trades = sum(int(s.get("live_trades") or 0) for s in per_strategy)
    # Loss streak = min across strategies is too lenient; take the WORST (max).
    loss_streak = max((int(s.get("live_loss_streak") or 0) for s in per_strategy), default=0)

    weighted_pf = sum(
        float(s.get("capital_pct") or 0.0) * float(s.get("live_profit_factor") or 0.0)
        for s in per_strategy
    ) / total_w
    weighted_wr = sum(
        float(s.get("capital_pct") or 0.0) * float(s.get("live_win_rate") or 0.0)
        for s in per_strategy
    ) / total_w

    # Session equity = weighted return over starting capital (percentage form).
    ret_pct = sum(
        float(s.get("capital_pct") or 0.0) * float(s.get("live_return_pct") or 0.0)
        for s in per_strategy
    ) / total_w

    return {
        "equity_return_pct": round(ret_pct, 2),
        "total_drawdown_pct": round(total_dd, 2),
        "daily_drawdown_pct": round(daily_dd, 2),
        "total_trades": total_trades,
        "loss_streak": loss_streak,
        "recent_profit_factor": round(weighted_pf, 3),
        "win_rate": round(weighted_wr, 1),
        "updated_at": _now_iso(),
    }


async def _compute_live_state(strategies: List[dict], allocation: List[dict]) -> List[Dict[str, Any]]:
    """Fetch live-tracking rows previously computed by `live_tracking_engine`
    for each strategy, or fall back to the strategy's backtest metrics if no
    live track yet. Returns a per-strategy summary used by the aggregator."""
    db = get_db()
    alloc_by_id = {a["strategy_id"]: a for a in allocation}
    per: List[Dict[str, Any]] = []
    for s in strategies:
        sid = s.get("strategy_id")
        alloc = alloc_by_id.get(sid) or {}
        track = await db["live_tracking"].find_one({"strategy_id": sid})
        if track and isinstance(track.get("live_metrics"), dict):
            lm = track["live_metrics"]
            per.append({
                "strategy_id": sid,
                "capital_pct": alloc.get("capital_pct", 0.25),
                "risk_per_trade_pct": alloc.get("risk_per_trade_pct", 1.0),
                "live_dd_pct": lm.get("max_drawdown_pct", 0.0),
                "live_daily_dd_pct": lm.get("max_daily_drawdown_pct", 0.0),
                "live_trades": lm.get("total_trades", 0),
                "live_loss_streak": lm.get("current_loss_streak", 0),
                "live_profit_factor": lm.get("profit_factor", 0.0),
                "live_win_rate": lm.get("win_rate", 0.0),
                "live_return_pct": lm.get("total_return_pct", 0.0),
                "tracking_status": track.get("status", "STABLE"),
            })
        else:
            # No live track yet → carry backtest metrics as a baseline so the
            # Go/No-Go gate has something to evaluate before the first trade.
            per.append({
                "strategy_id": sid,
                "capital_pct": alloc.get("capital_pct", 0.25),
                "risk_per_trade_pct": alloc.get("risk_per_trade_pct", 1.0),
                "live_dd_pct": s.get("max_drawdown_pct", 0.0),
                "live_daily_dd_pct": 0.0,
                "live_trades": 0,
                "live_loss_streak": 0,
                "live_profit_factor": s.get("profit_factor", 0.0),
                "live_win_rate": s.get("win_rate", 0.0),
                "live_return_pct": 0.0,
                "tracking_status": "NEW",
            })
    return per


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

async def start_execution(
    *,
    portfolio_run_id: Optional[str] = None,
    portfolio: Optional[Dict[str, Any]] = None,
    account_balance: float = 10000.0,
    mode: str = "paper",
    risk_limits: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Start a new live-execution session bound to a portfolio.

    Exactly one session may be `active` at a time. Pass EITHER
    `portfolio_run_id` (loads the persisted Phase-7 snapshot) OR an
    inline `portfolio` dict.

    Generates compile-checked cBots for each portfolio strategy and
    persists the full session state to `execution_sessions`.
    """
    if mode not in ALLOWED_MODES:
        raise ValueError(f"mode must be one of {ALLOWED_MODES}")
    if account_balance <= 0:
        raise ValueError("account_balance must be positive")

    async with _lock:
        db = get_db()
        active = await _get_active_session(db)
        if active:
            raise RuntimeError(f"already_active:{active.get('session_id')}")

        if portfolio_run_id and not portfolio:
            portfolio = await _load_portfolio(db, portfolio_run_id)
            if not portfolio:
                raise ValueError(f"portfolio run_id not found: {portfolio_run_id}")
        if not portfolio:
            raise ValueError("portfolio_run_id or portfolio is required")

        strategies = portfolio.get("strategies") or []
        allocation = portfolio.get("allocation") or []
        if not strategies or not allocation:
            raise ValueError("portfolio must contain strategies and allocation")

        # ── Generate cBots (compile-safe via the reused pipeline) ──
        alloc_by_id = {a.get("strategy_id"): a for a in allocation}
        cbots: List[Dict[str, Any]] = []
        compile_failures = 0
        for s in strategies:
            a = alloc_by_id.get(s.get("strategy_id")) or {}
            rec = await _generate_cbot_for_strategy(s, a)
            rec["strategy_id"] = s.get("strategy_id")
            rec["pair"] = s.get("pair")
            rec["timeframe"] = s.get("timeframe")
            if rec.get("compile_status") == "error":
                compile_failures += 1
            cbots.append(rec)

        # ── Seed live tracking snapshot ──
        per = await _compute_live_state(strategies, allocation)
        tracking = _aggregate_tracking(per)

        session_id = uuid.uuid4().hex[:12]
        session = {
            "session_id": session_id,
            "status": "active",
            "mode": mode,
            "started_at": _now_iso(),
            "stopped_at": None,
            "account_balance": float(account_balance),
            "portfolio_run_id": portfolio.get("run_id"),
            "portfolio_score": portfolio.get("portfolio_score"),
            "strategies": strategies,
            "allocation": allocation,
            "cbots": cbots,
            "compile_failures": compile_failures,
            "risk_limits": {**DEFAULT_RISK_LIMITS, **(risk_limits or {})},
            "emergency_stop": False,
            "tracking": tracking,
            "per_strategy_tracking": per,
        }

        # Pre-trade go/no-go on session seed
        session["go_no_go"] = go_no_go(session)

        await db[SESSIONS].insert_one({**session})
        logger.info("Execution session %s started — mode=%s, strategies=%d, compile_fail=%d",
                    session_id, mode, len(strategies), compile_failures)
        return session


async def stop_execution(session_id: str, reason: str = "manual") -> Dict[str, Any]:
    """Gracefully stop a session. The record moves to `status=stopped` and
    is kept in Mongo for audit / subsequent `/status` replies."""
    async with _lock:
        db = get_db()
        session = await db[SESSIONS].find_one({"session_id": session_id})
        if not session:
            raise ValueError(f"session not found: {session_id}")
        if session.get("status") != "active":
            return {"session_id": session_id, "status": session.get("status"),
                    "message": "already stopped"}

        await db[SESSIONS].update_one(
            {"session_id": session_id},
            {"$set": {"status": "stopped", "stopped_at": _now_iso(),
                      "stop_reason": reason}},
        )
        updated = await db[SESSIONS].find_one({"session_id": session_id}, {"_id": 0})
        logger.info("Execution session %s stopped — reason=%s", session_id, reason)
        return updated


async def emergency_stop(session_id: Optional[str] = None,
                         reason: str = "emergency") -> Dict[str, Any]:
    """Hard stop — sets the emergency flag and halts the session."""
    db = get_db()
    if session_id is None:
        active = await _get_active_session(db)
        if not active:
            return {"status": "no_active_session"}
        session_id = active["session_id"]
    await db[SESSIONS].update_one(
        {"session_id": session_id}, {"$set": {"emergency_stop": True}}
    )
    return await stop_execution(session_id, reason=reason)


async def refresh_tracking(session_id: str) -> Dict[str, Any]:
    """Recompute live tracking for an active session and re-run the
    Go/No-Go gate. Called by /status and can be invoked on demand."""
    db = get_db()
    session = await db[SESSIONS].find_one({"session_id": session_id})
    if not session:
        raise ValueError(f"session not found: {session_id}")
    if session.get("status") != "active":
        return {k: v for k, v in session.items() if k != "_id"}

    per = await _compute_live_state(session["strategies"], session["allocation"])
    tracking = _aggregate_tracking(per)
    session["tracking"] = tracking
    session["per_strategy_tracking"] = per
    gate = go_no_go(session)
    session["go_no_go"] = gate

    # Auto-halt if a breach was detected.
    if not gate["allow"]:
        session["status"] = "stopped"
        session["stopped_at"] = _now_iso()
        session["stop_reason"] = f"auto_halt: {','.join(gate['reasons'])}"
        logger.warning("Auto-halt session %s — %s", session_id, gate["reasons"])

    await db[SESSIONS].update_one(
        {"session_id": session_id},
        {"$set": {
            "tracking": tracking,
            "per_strategy_tracking": per,
            "go_no_go": gate,
            "status": session["status"],
            "stopped_at": session.get("stopped_at"),
            "stop_reason": session.get("stop_reason"),
        }},
    )
    session.pop("_id", None)
    return session


async def get_status(history_limit: int = 10) -> Dict[str, Any]:
    """Snapshot of the current active session + recent history.
    If there is an active session, its tracking is re-evaluated first
    so callers always see the freshest Go/No-Go decision."""
    db = get_db()
    active = await _get_active_session(db)
    if active:
        active = await refresh_tracking(active["session_id"])

    cursor = db[SESSIONS].find(
        {"status": {"$in": ["active", "stopped"]}},
        {"_id": 0, "strategies": 0, "allocation": 0,
         "cbots": 0, "per_strategy_tracking": 0},
    ).sort("started_at", -1).limit(max(1, min(history_limit, 50)))
    history = [d async for d in cursor]

    return {
        "active": active,
        "total_sessions": await db[SESSIONS].count_documents({}),
        "history": history,
    }
