"""
Phase 10 — Challenge Management System (Control Layer).

Adaptive control loop that sits ABOVE the execution manager. It reads the
live session + portfolio state, classifies account health, decides an
action, and — when enabled — executes it through the existing execution
layer. No engines are modified; this module is a pure orchestrator.

State machine:
    HEALTHY  → total_dd ≤ 60% of max, daily_dd ≤ 60% of max, pf ≥ 1.0
    WARNING  → total_dd in (60%, 80%] of max, or daily_dd in (60%, 80%]
    DANGER   → total_dd in (80%, 100%) of max, or daily_dd > 80%
    BREACH   → any hard limit ≥ 100% of the configured cap

Decision matrix:
    HEALTHY              → CONTINUE
    WARNING              → REDUCE_RISK        (halve per-trade risk budget)
    DANGER               → PAUSE              (halt, keep session, replay later)
    BREACH               → STOP               (terminal, emergency stop)
    PF < 0.7 (any state) → REBUILD_PORTFOLIO  (rebuild from library)
    loss_streak ≥ 5      → PAUSE              (cool-down)
    daily_dd > 4%        → REDUCE_RISK        (hard rule per spec)
    daily_dd > 5%        → STOP               (hard rule per spec)

Action handler:
    CONTINUE           → no-op
    REDUCE_RISK        → session.risk_limits.max_per_trade_risk_pct *= 0.5
    PAUSE              → execution_manager.stop_execution(reason="paused:...")
    STOP               → execution_manager.emergency_stop(reason="...")
    REBUILD_PORTFOLIO  → stop session + schedule a portfolio rebuild (flag set;
                         rebuild is executed by the loop on the next tick so
                         the caller stays non-blocking).

Loop:
    `start_control_loop(interval_minutes=10)` installs an APScheduler
    interval job that runs `tick_and_act` each interval. `coalesce=True`,
    `max_instances=1` + a local `asyncio.Lock` double-guard against
    overlaps. Every decision is persisted to `challenge_decisions` for
    audit.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from engines.db import get_db

logger = logging.getLogger(__name__)

DECISIONS_COLL = "challenge_decisions"
RUN_STATE_COLL = "challenge_control"

# ─────────────────────────────────────────────────────────────────────
# State / decision enums
# ─────────────────────────────────────────────────────────────────────
STATES = ("HEALTHY", "WARNING", "DANGER", "BREACH", "IDLE")
ACTIONS = ("CONTINUE", "REDUCE_RISK", "PAUSE", "STOP", "REBUILD_PORTFOLIO")

DEFAULT_SAFETY_RULES: Dict[str, Any] = {
    "daily_dd_reduce_pct": 4.0,     # daily_dd > 4%   → REDUCE_RISK
    "daily_dd_stop_pct":   5.0,     # daily_dd > 5%   → STOP
    "loss_streak_pause":   5,       # streak ≥ 5      → PAUSE
    "pf_rebuild_floor":    0.7,     # pf < 0.7        → REBUILD_PORTFOLIO
    "risk_reduce_factor":  0.5,     # REDUCE_RISK multiplier on max_per_trade_risk_pct
    # ── Phase 10.5 extensions ──
    "cooldown_hours":              2.0,   # after STOP/PAUSE/REBUILD: block new trading
    "strategy_pf_disable":         0.5,   # per-strategy disable threshold
    "strategy_loss_streak_disable": 4,    # per-strategy disable threshold
    # Gradual risk-recovery ladder applied AFTER a REDUCE_RISK, when state
    # returns to HEALTHY. The manager walks up one rung per tick until the
    # session's original `max_per_trade_risk_pct` is reached.
    "risk_recovery_ladder":        [0.5, 0.75, 1.0, 1.25],
    # Blocked hours (UTC 24h clock). Default empty = always allowed.
    "blocked_hours_utc":           [],
}

_lock = asyncio.Lock()
_scheduler: Optional[AsyncIOScheduler] = None
_JOB_ID = "challenge_control_interval"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# State classification
# ─────────────────────────────────────────────────────────────────────

def classify_state(
    tracking: Dict[str, Any],
    risk_limits: Dict[str, float],
    emergency_stop: bool = False,
) -> Dict[str, Any]:
    """Pure fn — classify account state from tracking + limits.
    Returns { state, total_dd_ratio, daily_dd_ratio, observed }."""
    if emergency_stop:
        return {
            "state": "BREACH",
            "total_dd_ratio": 1.0, "daily_dd_ratio": 1.0,
            "observed": {"emergency_stop": True},
        }

    total_dd = float(tracking.get("total_drawdown_pct") or 0.0)
    daily_dd = float(tracking.get("daily_drawdown_pct") or 0.0)
    max_total = max(0.1, float(risk_limits.get("max_total_drawdown_pct") or 10.0))
    max_daily = max(0.1, float(risk_limits.get("max_daily_drawdown_pct") or 5.0))

    total_ratio = total_dd / max_total
    daily_ratio = daily_dd / max_daily
    worst = max(total_ratio, daily_ratio)

    if worst >= 1.0:
        state = "BREACH"
    elif worst > 0.8:
        state = "DANGER"
    elif worst > 0.6:
        state = "WARNING"
    else:
        state = "HEALTHY"

    return {
        "state": state,
        "total_dd_ratio": round(total_ratio, 3),
        "daily_dd_ratio": round(daily_ratio, 3),
        "observed": {
            "total_drawdown_pct": total_dd, "daily_drawdown_pct": daily_dd,
            "max_total_drawdown_pct": max_total, "max_daily_drawdown_pct": max_daily,
            "loss_streak": int(tracking.get("loss_streak") or 0),
            "recent_profit_factor": float(tracking.get("recent_profit_factor") or 0.0),
            "win_rate": float(tracking.get("win_rate") or 0.0),
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Decision engine
# ─────────────────────────────────────────────────────────────────────

def decide_action(
    classification: Dict[str, Any],
    tracking: Dict[str, Any],
    safety_rules: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Given a state classification, pick an action and a reason trail.

    Precedence (first match wins):
      1. BREACH                          → STOP
      2. daily_dd > daily_dd_stop_pct    → STOP      (hard rule)
      3. PF < pf_rebuild_floor (> 0)     → REBUILD_PORTFOLIO
      4. DANGER                          → PAUSE
      5. loss_streak ≥ loss_streak_pause → PAUSE
      6. daily_dd > daily_dd_reduce_pct  → REDUCE_RISK (hard rule)
      7. WARNING                         → REDUCE_RISK
      8. HEALTHY / IDLE                  → CONTINUE
    """
    rules = {**DEFAULT_SAFETY_RULES, **(safety_rules or {})}
    state = classification["state"]
    observed = classification["observed"]
    pf = float(observed.get("recent_profit_factor") or 0.0)
    daily_dd = float(observed.get("daily_drawdown_pct") or 0.0)
    loss_streak = int(observed.get("loss_streak") or 0)

    reasons: list[str] = []
    action = "CONTINUE"

    if state == "BREACH":
        action = "STOP"
        reasons.append("state=BREACH")
    elif daily_dd > float(rules["daily_dd_stop_pct"]):
        action = "STOP"
        reasons.append(f"daily_dd {daily_dd} > {rules['daily_dd_stop_pct']}%")
    elif pf > 0 and pf < float(rules["pf_rebuild_floor"]):
        action = "REBUILD_PORTFOLIO"
        reasons.append(f"pf {pf} < {rules['pf_rebuild_floor']}")
    elif state == "DANGER":
        action = "PAUSE"
        reasons.append("state=DANGER")
    elif loss_streak >= int(rules["loss_streak_pause"]):
        action = "PAUSE"
        reasons.append(f"loss_streak {loss_streak} ≥ {rules['loss_streak_pause']}")
    elif daily_dd > float(rules["daily_dd_reduce_pct"]):
        action = "REDUCE_RISK"
        reasons.append(f"daily_dd {daily_dd} > {rules['daily_dd_reduce_pct']}%")
    elif state == "WARNING":
        action = "REDUCE_RISK"
        reasons.append("state=WARNING")
    else:
        reasons.append(f"state={state}")

    return {
        "action": action, "reasons": reasons,
        "state": state, "rules_used": rules,
    }


# ─────────────────────────────────────────────────────────────────────
# Action handler — wires into execution_manager
# ─────────────────────────────────────────────────────────────────────

async def execute_action(
    decision: Dict[str, Any], session: Dict[str, Any], dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply a decision. Reuses the existing execution_manager — no new
    broker IO, no new state machine on the execution side."""
    from engines import execution_manager as em
    action = decision["action"]
    session_id = session.get("session_id") if session else None
    result: Dict[str, Any] = {"action": action, "applied": False, "dry_run": dry_run}

    if dry_run or not session_id:
        result["note"] = "dry_run" if dry_run else "no_active_session"
        return result

    try:
        if action == "CONTINUE":
            result["applied"] = True
            result["note"] = "no-op"

        elif action == "REDUCE_RISK":
            rules = {**DEFAULT_SAFETY_RULES, **(decision.get("rules_used") or {})}
            factor = float(rules.get("risk_reduce_factor") or 0.5)
            current = float(
                (session.get("risk_limits") or {}).get("max_per_trade_risk_pct") or 2.0
            )
            new_limit = max(0.1, round(current * factor, 3))
            db = get_db()
            # Remember the ORIGINAL limit once so gradual recovery has a ceiling.
            original = session.get("original_max_per_trade_risk_pct") or current
            await db["execution_sessions"].update_one(
                {"session_id": session_id},
                {"$set": {
                    "risk_limits.max_per_trade_risk_pct": new_limit,
                    "original_max_per_trade_risk_pct": float(original),
                }},
            )
            result.update({"applied": True, "old_risk_pct": current,
                           "new_risk_pct": new_limit,
                           "original_max_per_trade_risk_pct": float(original)})

        elif action == "PAUSE":
            await em.stop_execution(
                session_id, reason=f"paused:{','.join(decision['reasons'])}"
            )
            rules = {**DEFAULT_SAFETY_RULES, **(decision.get("rules_used") or {})}
            until = await _set_cooldown(
                float(rules.get("cooldown_hours") or 2.0),
                reason=f"PAUSE:{','.join(decision['reasons'])}",
            )
            result.update({"applied": True, "cooldown_until": until.isoformat()})

        elif action == "STOP":
            await em.emergency_stop(
                session_id, reason=f"stop:{','.join(decision['reasons'])}"
            )
            rules = {**DEFAULT_SAFETY_RULES, **(decision.get("rules_used") or {})}
            until = await _set_cooldown(
                float(rules.get("cooldown_hours") or 2.0),
                reason=f"STOP:{','.join(decision['reasons'])}",
            )
            result.update({"applied": True, "cooldown_until": until.isoformat()})

        elif action == "REBUILD_PORTFOLIO":
            # Stop first (PAUSE semantics) + set a flag the loop can pick up.
            await em.stop_execution(
                session_id, reason=f"rebuild:{','.join(decision['reasons'])}"
            )
            db = get_db()
            rules = {**DEFAULT_SAFETY_RULES, **(decision.get("rules_used") or {})}
            until = await _set_cooldown(
                float(rules.get("cooldown_hours") or 2.0),
                reason=f"REBUILD:{','.join(decision['reasons'])}",
            )
            await db[RUN_STATE_COLL].update_one(
                {"_id": "control"},
                {"$set": {"rebuild_requested_at": _now_iso(),
                          "rebuild_source_session": session_id}},
                upsert=True,
            )
            result.update({"applied": True, "stopped": True,
                           "rebuild_requested": True,
                           "cooldown_until": until.isoformat()})
    except Exception as e:
        logger.exception("execute_action failed")
        result["error"] = str(e)

    return result


# ═════════════════════════════════════════════════════════════════════
# Phase 10.5 — Refinements
# ═════════════════════════════════════════════════════════════════════

# ─── 1. Cooldown ──────────────────────────────────────────────────────

async def _cooldown_until() -> Optional[datetime]:
    """Return the UTC timestamp at which the current cooldown expires,
    or None if no cooldown is active."""
    db = get_db()
    ctrl = await db[RUN_STATE_COLL].find_one({"_id": "control"}, {"_id": 0})
    if not ctrl or not ctrl.get("cooldown_until"):
        return None
    try:
        ts = datetime.fromisoformat(ctrl["cooldown_until"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts if ts > datetime.now(timezone.utc) else None
    except Exception:
        return None


async def _set_cooldown(hours: float, reason: str) -> datetime:
    db = get_db()
    until = datetime.now(timezone.utc) + timedelta(hours=max(0.0, float(hours)))
    await db[RUN_STATE_COLL].update_one(
        {"_id": "control"},
        {"$set": {
            "cooldown_until": until.isoformat(),
            "cooldown_reason": reason,
            "cooldown_started_at": _now_iso(),
        }},
        upsert=True,
    )
    return until


async def clear_cooldown() -> None:
    db = get_db()
    await db[RUN_STATE_COLL].update_one(
        {"_id": "control"},
        {"$unset": {"cooldown_until": "", "cooldown_reason": "",
                    "cooldown_started_at": ""}},
        upsert=True,
    )


# ─── 2. Time filter ──────────────────────────────────────────────────

def _is_blocked_hour(blocked_hours: List[int], now: Optional[datetime] = None) -> bool:
    if not blocked_hours:
        return False
    now = now or datetime.now(timezone.utc)
    return int(now.hour) in {int(h) for h in blocked_hours}


# ─── 3. Per-strategy control ─────────────────────────────────────────

def _find_strategies_to_disable(
    session: Dict[str, Any], rules: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Inspect per_strategy_tracking inside a live session; return the
    strategies that should be disabled based on pf / loss_streak thresholds."""
    pf_floor = float(rules.get("strategy_pf_disable") or 0.5)
    ls_limit = int(rules.get("strategy_loss_streak_disable") or 4)
    per = session.get("per_strategy_tracking") or []
    victims: List[Dict[str, Any]] = []
    for s in per:
        pf = float(s.get("live_profit_factor") or 0.0)
        ls = int(s.get("live_loss_streak") or 0)
        reasons: List[str] = []
        if pf > 0 and pf < pf_floor:
            reasons.append(f"pf {pf} < {pf_floor}")
        if ls >= ls_limit:
            reasons.append(f"loss_streak {ls} ≥ {ls_limit}")
        if reasons:
            victims.append({
                "strategy_id": s.get("strategy_id"),
                "pf": pf, "loss_streak": ls, "reasons": reasons,
            })
    return victims


async def disable_strategies_in_session(
    session_id: str, victims: List[Dict[str, Any]],
) -> int:
    """Flip `allocation[i].disabled=True` for any strategy matching a
    victim id. Non-destructive — the row stays in allocation for audit."""
    if not victims:
        return 0
    db = get_db()
    sess = await db["execution_sessions"].find_one({"session_id": session_id})
    if not sess:
        return 0
    victim_ids = {v["strategy_id"] for v in victims}
    alloc = sess.get("allocation") or []
    changed = 0
    for a in alloc:
        if a.get("strategy_id") in victim_ids and not a.get("disabled"):
            a["disabled"] = True
            a["disabled_at"] = _now_iso()
            a["disable_reasons"] = next(
                (v["reasons"] for v in victims if v["strategy_id"] == a.get("strategy_id")),
                [],
            )
            changed += 1
    if changed:
        await db["execution_sessions"].update_one(
            {"session_id": session_id}, {"$set": {"allocation": alloc}},
        )
    return changed


# ─── 4. Gradual risk recovery ────────────────────────────────────────

async def _apply_recovery_step(
    session: Dict[str, Any], rules: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """When state is HEALTHY but the session is carrying a reduced risk
    budget, step the limit back up via the recovery ladder. Called only
    during CONTINUE decisions — never overrides a safety-triggered cut."""
    ladder = list(rules.get("risk_recovery_ladder") or [])
    if not ladder:
        return None
    rl = session.get("risk_limits") or {}
    current = float(rl.get("max_per_trade_risk_pct") or 0.0)
    original = float(session.get("original_max_per_trade_risk_pct") or 0.0)
    if original <= 0:
        # Seed original once so recovery has a ceiling.
        original = current
    if current >= original:
        return None  # already at or above baseline

    # Find next rung strictly greater than current.
    next_rung = None
    for step in sorted(float(s) for s in ladder):
        if step > current:
            next_rung = step
            break
    if next_rung is None:
        next_rung = original
    next_rung = min(next_rung, original)
    if next_rung <= current:
        return None

    db = get_db()
    await db["execution_sessions"].update_one(
        {"session_id": session["session_id"]},
        {"$set": {
            "risk_limits.max_per_trade_risk_pct": next_rung,
            "original_max_per_trade_risk_pct": original,
        }},
    )
    return {"old_risk_pct": current, "new_risk_pct": next_rung,
            "ladder_ceiling": original}


# ─── 5. Auto rebuild ─────────────────────────────────────────────────

async def _auto_rebuild_if_requested(
    original_session: Dict[str, Any], rules: Dict[str, Any],
    auto_rebuild: bool,
) -> Optional[Dict[str, Any]]:
    """If a REBUILD flag is pending AND auto_rebuild=True, build a fresh
    portfolio and start a new session. Fully opt-in — default is off
    so the control loop never restarts trading silently."""
    if not auto_rebuild:
        return None
    db = get_db()
    ctrl = await db[RUN_STATE_COLL].find_one({"_id": "control"}, {"_id": 0}) or {}
    if not ctrl.get("rebuild_requested_at"):
        return None
    # Don't rebuild while cooldown is still active.
    if await _cooldown_until():
        return {"skipped": "cooldown_active"}

    try:
        from engines.portfolio_engine import build_portfolio_from_library
        from engines import execution_manager as em

        built = await build_portfolio_from_library(
            top_n_pool=25, target_size=4, max_pair_corr=0.6,
            max_same_pair=2, max_same_style=2,
        )
        if not built.get("success"):
            return {"skipped": f"rebuild_failed:{built.get('error')}"}

        # Clear the flag BEFORE starting the session to avoid retrigger loops.
        await db[RUN_STATE_COLL].update_one(
            {"_id": "control"}, {"$unset": {"rebuild_requested_at": ""}},
        )
        new_sess = await em.start_execution(
            portfolio_run_id=built["run_id"],
            account_balance=float(original_session.get("account_balance") or 10000),
            mode=original_session.get("mode") or "paper",
            risk_limits=original_session.get("risk_limits"),
        )
        return {
            "rebuilt": True,
            "new_session_id": new_sess.get("session_id"),
            "portfolio_run_id": built["run_id"],
            "portfolio_score": built.get("portfolio_score"),
        }
    except Exception as e:
        logger.exception("auto_rebuild failed")
        return {"skipped": f"error:{e}"}




async def get_current_snapshot() -> Dict[str, Any]:
    """Build the inputs needed by classify_state + decide_action. When no
    active session exists, returns an IDLE classification."""
    from engines import execution_manager as em
    status = await em.get_status(history_limit=1)
    active = status.get("active")
    if not active:
        return {
            "has_active_session": False,
            "session": None,
            "classification": {
                "state": "IDLE", "total_dd_ratio": 0.0, "daily_dd_ratio": 0.0,
                "observed": {},
            },
        }

    tracking = active.get("tracking") or {}
    risk_limits = active.get("risk_limits") or {}
    classification = classify_state(
        tracking, risk_limits, emergency_stop=bool(active.get("emergency_stop"))
    )
    return {
        "has_active_session": True,
        "session": active,
        "classification": classification,
        "tracking": tracking,
        "risk_limits": risk_limits,
    }


async def tick_and_act(
    dry_run: bool = False,
    safety_rules: Optional[Dict[str, Any]] = None,
    auto_rebuild: bool = False,
) -> Dict[str, Any]:
    """One pass of the adaptive loop. Safe to call from HTTP or scheduler.
    Serialized by a single `asyncio.Lock` — overlapping calls short-circuit.

    Phase 10.5 extensions:
      • cooldown    — after STOP/PAUSE/REBUILD, subsequent ticks short-circuit
                      until the cooldown expires (unless dry_run=True).
      • time filter — if current UTC hour is in `blocked_hours_utc`, the
                      decision is overridden to PAUSE.
      • per-strategy disable — strategies with pf < strategy_pf_disable or
                               loss_streak ≥ strategy_loss_streak_disable are
                               flagged `disabled=True` in the session.
      • gradual recovery — on CONTINUE with a session carrying a reduced risk
                           budget, step the per-trade limit up one rung along
                           `risk_recovery_ladder`.
      • auto_rebuild=True — when a REBUILD flag is outstanding AND cooldown
                            has expired, rebuild the portfolio + restart.
    """
    if _lock.locked():
        return {"skipped": True, "reason": "already_ticking"}

    async with _lock:
        rules = {**DEFAULT_SAFETY_RULES, **(safety_rules or {})}
        snapshot = await get_current_snapshot()
        classification = snapshot["classification"]
        tracking = snapshot.get("tracking") or {}
        session = snapshot.get("session")

        # ── cooldown short-circuit (live ticks only) ──
        cooldown = await _cooldown_until()
        cooldown_active = cooldown is not None
        if cooldown_active and not dry_run:
            record = {
                "ts": _now_iso(), "state": classification["state"],
                "cooldown_until": cooldown.isoformat(),
                "decision": {"action": "COOLDOWN", "reasons": ["cooldown_active"]},
                "action_result": {"applied": False, "note": "cooldown_active"},
                "session_id": (session or {}).get("session_id"),
                "dry_run": dry_run, "skipped_reason": "cooldown_active",
            }
            try:
                await get_db()[DECISIONS_COLL].insert_one({**record})
            except Exception:
                pass
            return record

        decision = decide_action(classification, tracking, safety_rules=rules)

        # ── time filter override (blocks trading during defined hours) ──
        if _is_blocked_hour(rules.get("blocked_hours_utc") or []):
            if decision["action"] in ("CONTINUE", "REDUCE_RISK"):
                hour = datetime.now(timezone.utc).hour
                decision = {
                    "action": "PAUSE",
                    "reasons": decision["reasons"] + [f"blocked_hour_utc={hour}"],
                    "state": decision["state"], "rules_used": rules,
                }

        # ── per-strategy disable ──
        victims = _find_strategies_to_disable(session or {}, rules) if session else []
        strategies_disabled = 0
        if victims and not dry_run and session:
            strategies_disabled = await disable_strategies_in_session(
                session["session_id"], victims,
            )

        action_result = await execute_action(decision, session or {}, dry_run=dry_run)

        # ── gradual risk recovery (only on CONTINUE for an active session) ──
        recovery = None
        if (not dry_run and session and decision["action"] == "CONTINUE"
                and classification["state"] == "HEALTHY"):
            recovery = await _apply_recovery_step(session, rules)

        # ── auto rebuild (opt-in) ──
        rebuild = None
        if auto_rebuild and session:
            rebuild = await _auto_rebuild_if_requested(session, rules, auto_rebuild)

        record = {
            "ts": _now_iso(),
            "state": classification["state"],
            "total_dd_ratio": classification.get("total_dd_ratio"),
            "daily_dd_ratio": classification.get("daily_dd_ratio"),
            "observed": classification.get("observed"),
            "decision": decision,
            "action_result": action_result,
            "session_id": (session or {}).get("session_id"),
            "dry_run": dry_run,
            # Phase 10.5 telemetry
            "cooldown_active": cooldown_active,
            "cooldown_until": cooldown.isoformat() if cooldown else None,
            "strategies_disabled": strategies_disabled,
            "victims": victims,
            "recovery": recovery,
            "auto_rebuild": rebuild,
        }
        try:
            db = get_db()
            await db[DECISIONS_COLL].insert_one({**record})
        except Exception as e:
            logger.warning("Failed to persist challenge decision: %s", e)

        logger.info("Challenge tick: state=%s action=%s session=%s disabled=%d",
                    classification["state"], decision["action"],
                    (session or {}).get("session_id"), strategies_disabled)
        return record


async def get_status(history_limit: int = 20) -> Dict[str, Any]:
    """Current snapshot + last N decisions for the audit pane."""
    snapshot = await get_current_snapshot()
    db = get_db()
    cursor = db[DECISIONS_COLL].find(
        {}, {"_id": 0}
    ).sort("ts", -1).limit(max(1, min(history_limit, 200)))
    history = [d async for d in cursor]
    control = await db[RUN_STATE_COLL].find_one({"_id": "control"}, {"_id": 0}) or {}
    scheduler_state = {
        "enabled": bool(_scheduler and _scheduler.running),
        "interval_minutes": control.get("interval_minutes"),
    }
    if _scheduler and scheduler_state["enabled"]:
        try:
            job = _scheduler.get_job(_JOB_ID)
            if job and job.next_run_time:
                scheduler_state["next_run_at"] = job.next_run_time.isoformat()
        except Exception:
            pass
    active_cd = await _cooldown_until()
    return {
        "snapshot": snapshot,
        "history": history,
        "scheduler": scheduler_state,
        "rebuild_requested_at": control.get("rebuild_requested_at"),
        # Phase 10.5 — cooldown visibility
        "cooldown": {
            "active": active_cd is not None,
            "until": active_cd.isoformat() if active_cd else None,
            "reason": control.get("cooldown_reason") if active_cd else None,
            "started_at": control.get("cooldown_started_at") if active_cd else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────

def _scheduled_wrapper():
    async def _runner():
        try:
            await tick_and_act()
        except Exception:
            logger.exception("Scheduled challenge tick failed")
    loop = asyncio.get_event_loop()
    loop.create_task(_runner())


def start_control_loop(interval_minutes: float = 10.0) -> Dict[str, Any]:
    """Install the adaptive loop as an APScheduler interval job."""
    global _scheduler
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if interval_minutes < 1 or interval_minutes > 60:
        # Spec says 5–10 min. Allow 1–60 for operator flexibility.
        logger.warning("challenge interval %smin is outside the 1–60 range", interval_minutes)

    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")

    try:
        _scheduler.remove_job(_JOB_ID)
    except Exception:
        pass

    _scheduler.add_job(
        _scheduled_wrapper,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=_JOB_ID, name="challenge_control_loop",
        coalesce=True, max_instances=1, replace_existing=True,
    )
    if not _scheduler.running:
        _scheduler.start()

    import asyncio as _a
    async def _persist():
        db = get_db()
        await db[RUN_STATE_COLL].update_one(
            {"_id": "control"},
            {"$set": {"interval_minutes": float(interval_minutes),
                      "enabled_at": _now_iso()}},
            upsert=True,
        )
    try:
        _a.get_event_loop().create_task(_persist())
    except Exception:
        pass

    job = _scheduler.get_job(_JOB_ID)
    return {
        "enabled": True,
        "interval_minutes": float(interval_minutes),
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }


def stop_control_loop() -> Dict[str, Any]:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.remove_job(_JOB_ID)
        except Exception:
            pass
        if _scheduler.running:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
        _scheduler = None
    return {"enabled": False, "interval_minutes": None, "next_run_at": None}
