"""
Phase 10.5 — Control System Refinement tests.

Covers the five extensions layered on top of Phase 10:
  1. Cooldown system        (STOP/PAUSE/REBUILD arm cooldown; live ticks skip)
  2. Gradual risk recovery  (ladder step-up on CONTINUE in HEALTHY)
  3. Per-strategy disable   (pf<0.5 OR loss_streak≥4 → allocation[i].disabled=True)
  4. Auto rebuild flow      (flag + build_portfolio_from_library + start_execution)
  5. Time filter            (blocked_hours_utc override decision to PAUSE)
"""
from __future__ import annotations

import datetime as _dt
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from engines import challenge_manager as cm


LIMITS = {"max_total_drawdown_pct": 10.0, "max_daily_drawdown_pct": 5.0,
          "max_per_trade_risk_pct": 2.0}


@pytest_asyncio.fixture(autouse=True)
async def _fresh(monkeypatch):
    from engines import db as _db_module
    _db_module._client = None
    _db_module._db = None
    db = _db_module.get_db()
    for c in (cm.DECISIONS_COLL, cm.RUN_STATE_COLL, "execution_sessions",
              "portfolios", "strategy_library"):
        await db[c].delete_many({})
    yield
    cm.stop_control_loop()
    for c in (cm.DECISIONS_COLL, cm.RUN_STATE_COLL, "execution_sessions",
              "portfolios", "strategy_library"):
        await db[c].delete_many({})


def _tracking(total_dd=0.0, daily_dd=0.0, loss_streak=0, pf=1.5, wr=55.0):
    return {
        "total_drawdown_pct": total_dd, "daily_drawdown_pct": daily_dd,
        "loss_streak": loss_streak, "recent_profit_factor": pf,
        "win_rate": wr, "total_trades": 20,
    }


# ═════════════════════════════════════════════════════════════════════
# 1. Cooldown system
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cooldown_armed_by_stop(monkeypatch):
    async def fake_em(session_id=None, reason="emergency"):
        return {"session_id": session_id, "status": "stopped"}
    monkeypatch.setattr("engines.execution_manager.emergency_stop", fake_em)

    decision = {"action": "STOP", "reasons": ["state=BREACH"],
                "rules_used": {"cooldown_hours": 2.0}}
    res = await cm.execute_action(decision, {"session_id": "S1", "status": "active"})
    assert res["applied"] is True
    assert "cooldown_until" in res

    until = await cm._cooldown_until()  # noqa: SLF001
    assert until is not None
    # Should be roughly 2 hours in the future.
    delta_h = (until - datetime.now(timezone.utc)).total_seconds() / 3600.0
    assert 1.5 < delta_h <= 2.0


@pytest.mark.asyncio
async def test_cooldown_armed_by_pause(monkeypatch):
    async def fake_stop(session_id, reason="manual"):
        return {"session_id": session_id, "status": "stopped"}
    monkeypatch.setattr("engines.execution_manager.stop_execution", fake_stop)

    d = {"action": "PAUSE", "reasons": ["state=DANGER"],
         "rules_used": {"cooldown_hours": 1.0}}
    await cm.execute_action(d, {"session_id": "S1", "status": "active"})
    assert (await cm._cooldown_until()) is not None


@pytest.mark.asyncio
async def test_live_tick_short_circuits_during_cooldown(monkeypatch):
    # Arm cooldown directly
    await cm._set_cooldown(2.0, reason="test")  # noqa: SLF001

    async def fake_status(history_limit=1):
        return {"active": {
            "session_id": "S1", "status": "active", "emergency_stop": False,
            "risk_limits": LIMITS, "tracking": _tracking(total_dd=8.5, pf=1.5),
        }}
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)

    r = await cm.tick_and_act(dry_run=False)
    assert r["decision"]["action"] == "COOLDOWN"
    assert r["skipped_reason"] == "cooldown_active"
    assert r["action_result"]["applied"] is False


@pytest.mark.asyncio
async def test_dry_run_tick_bypasses_cooldown(monkeypatch):
    """Dry-run ticks MUST still classify + decide even under cooldown —
    otherwise the operator loses visibility of the pending state."""
    await cm._set_cooldown(2.0, reason="test")  # noqa: SLF001

    async def fake_status(history_limit=1):
        return {"active": {
            "session_id": "S1", "status": "active", "emergency_stop": False,
            "risk_limits": LIMITS, "tracking": _tracking(total_dd=7.0, pf=1.2),
        }}
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)

    r = await cm.tick_and_act(dry_run=True)
    # Dry-run produces a real decision (WARNING → REDUCE_RISK)
    assert r["decision"]["action"] == "REDUCE_RISK"
    assert r["cooldown_active"] is True


@pytest.mark.asyncio
async def test_clear_cooldown():
    await cm._set_cooldown(2.0, reason="test")  # noqa: SLF001
    assert (await cm._cooldown_until()) is not None
    await cm.clear_cooldown()
    assert (await cm._cooldown_until()) is None


# ═════════════════════════════════════════════════════════════════════
# 2. Gradual risk recovery
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_recovery_walks_ladder_on_healthy_continue(monkeypatch):
    from engines import db as _db
    db = _db.get_db()
    # Original limit was 2%, reduced to 0.3% (below ladder floor)
    await db["execution_sessions"].insert_one({
        "session_id": "S1", "status": "active",
        "risk_limits": {"max_per_trade_risk_pct": 0.3},
        "original_max_per_trade_risk_pct": 2.0,
        "allocation": [], "strategies": [], "cbots": [],
        "per_strategy_tracking": [],
        "tracking": _tracking(total_dd=1.0, pf=1.5),
        "emergency_stop": False,
    })

    async def fake_status(history_limit=1):
        d = await db["execution_sessions"].find_one({"session_id": "S1"}, {"_id": 0})
        return {"active": d}
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)

    # Tick 1: should step to 0.5
    r1 = await cm.tick_and_act(dry_run=False)
    assert r1["decision"]["action"] == "CONTINUE"
    assert r1["recovery"]["new_risk_pct"] == 0.5

    # Tick 2: 0.5 → 0.75
    r2 = await cm.tick_and_act(dry_run=False)
    assert r2["recovery"]["new_risk_pct"] == 0.75

    # Tick 3: 0.75 → 1.0
    r3 = await cm.tick_and_act(dry_run=False)
    assert r3["recovery"]["new_risk_pct"] == 1.0

    # Tick 4: 1.0 → 1.25
    r4 = await cm.tick_and_act(dry_run=False)
    assert r4["recovery"]["new_risk_pct"] == 1.25

    # Tick 5: 1.25 → ceiling (2.0)
    r5 = await cm.tick_and_act(dry_run=False)
    assert r5["recovery"]["new_risk_pct"] == 2.0

    # Tick 6: already at ceiling → no recovery
    r6 = await cm.tick_and_act(dry_run=False)
    assert r6["recovery"] is None


@pytest.mark.asyncio
async def test_recovery_blocked_when_state_not_healthy(monkeypatch):
    from engines import db as _db
    db = _db.get_db()
    await db["execution_sessions"].insert_one({
        "session_id": "S1", "status": "active",
        "risk_limits": {"max_per_trade_risk_pct": 0.5,
                        "max_total_drawdown_pct": 10, "max_daily_drawdown_pct": 5},
        "original_max_per_trade_risk_pct": 2.0,
        "allocation": [], "strategies": [], "cbots": [], "per_strategy_tracking": [],
        "tracking": _tracking(total_dd=7.0, pf=1.2),  # WARNING
        "emergency_stop": False,
    })
    async def fake_status(history_limit=1):
        d = await db["execution_sessions"].find_one({"session_id": "S1"}, {"_id": 0})
        return {"active": d}
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)

    r = await cm.tick_and_act(dry_run=True)  # dry so REDUCE_RISK doesn't clobber
    assert r["recovery"] is None  # HEALTHY check fails


@pytest.mark.asyncio
async def test_reduce_risk_seeds_original_ceiling(monkeypatch):
    from engines import db as _db
    db = _db.get_db()
    await db["execution_sessions"].insert_one({
        "session_id": "S1", "status": "active",
        "risk_limits": {"max_per_trade_risk_pct": 2.0},
        "allocation": [], "strategies": [], "cbots": [], "per_strategy_tracking": [],
    })
    d = {"action": "REDUCE_RISK", "reasons": ["state=WARNING"],
         "rules_used": cm.DEFAULT_SAFETY_RULES}
    res = await cm.execute_action(d, await db["execution_sessions"].find_one({"session_id": "S1"}))
    assert res["new_risk_pct"] == 1.0
    assert res["original_max_per_trade_risk_pct"] == 2.0
    stored = await db["execution_sessions"].find_one({"session_id": "S1"})
    assert stored["original_max_per_trade_risk_pct"] == 2.0


# ═════════════════════════════════════════════════════════════════════
# 3. Per-strategy disable
# ═════════════════════════════════════════════════════════════════════

def test_find_strategies_to_disable_identifies_weak():
    session = {
        "per_strategy_tracking": [
            {"strategy_id": "s1", "live_profit_factor": 1.5, "live_loss_streak": 1},
            {"strategy_id": "s2", "live_profit_factor": 0.3, "live_loss_streak": 0},  # pf<0.5
            {"strategy_id": "s3", "live_profit_factor": 1.0, "live_loss_streak": 5},  # streak≥4
            {"strategy_id": "s4", "live_profit_factor": 0.4, "live_loss_streak": 6},  # both
        ],
    }
    victims = cm._find_strategies_to_disable(session, cm.DEFAULT_SAFETY_RULES)  # noqa: SLF001
    ids = {v["strategy_id"] for v in victims}
    assert ids == {"s2", "s3", "s4"}
    # s4 has both reasons
    s4 = next(v for v in victims if v["strategy_id"] == "s4")
    assert len(s4["reasons"]) == 2


@pytest.mark.asyncio
async def test_disable_strategies_flips_allocation_flag():
    from engines import db as _db
    db = _db.get_db()
    await db["execution_sessions"].insert_one({
        "session_id": "S1", "status": "active",
        "allocation": [
            {"strategy_id": "s1", "capital_pct": 0.5, "risk_per_trade_pct": 2.0},
            {"strategy_id": "s2", "capital_pct": 0.5, "risk_per_trade_pct": 2.0},
        ],
        "strategies": [], "cbots": [], "per_strategy_tracking": [],
        "risk_limits": {},
    })
    changed = await cm.disable_strategies_in_session(
        "S1", [{"strategy_id": "s2", "reasons": ["pf 0.3 < 0.5"]}],
    )
    assert changed == 1
    stored = await db["execution_sessions"].find_one({"session_id": "S1"})
    allocs = {a["strategy_id"]: a for a in stored["allocation"]}
    assert allocs["s1"].get("disabled") is not True
    assert allocs["s2"]["disabled"] is True
    assert allocs["s2"]["disable_reasons"] == ["pf 0.3 < 0.5"]
    # Re-running is idempotent (no double-disable)
    again = await cm.disable_strategies_in_session(
        "S1", [{"strategy_id": "s2", "reasons": ["..."]}],
    )
    assert again == 0


@pytest.mark.asyncio
async def test_tick_disables_weak_strategies(monkeypatch):
    from engines import db as _db
    db = _db.get_db()
    await db["execution_sessions"].insert_one({
        "session_id": "S1", "status": "active",
        "risk_limits": LIMITS,
        "allocation": [
            {"strategy_id": "s1", "capital_pct": 0.5, "risk_per_trade_pct": 2.0},
            {"strategy_id": "s2", "capital_pct": 0.5, "risk_per_trade_pct": 2.0},
        ],
        "strategies": [], "cbots": [],
        "per_strategy_tracking": [
            {"strategy_id": "s1", "live_profit_factor": 1.5, "live_loss_streak": 1},
            {"strategy_id": "s2", "live_profit_factor": 0.3, "live_loss_streak": 0},
        ],
        "tracking": _tracking(total_dd=1.0, pf=1.4),
        "emergency_stop": False,
    })
    async def fake_status(history_limit=1):
        d = await db["execution_sessions"].find_one({"session_id": "S1"}, {"_id": 0})
        return {"active": d}
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)

    r = await cm.tick_and_act(dry_run=False)
    assert r["strategies_disabled"] == 1
    victim_ids = {v["strategy_id"] for v in r["victims"]}
    assert victim_ids == {"s2"}


# ═════════════════════════════════════════════════════════════════════
# 4. Auto rebuild flow
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_auto_rebuild_runs_only_when_flag_set(monkeypatch):
    # Mock portfolio + execution — we just verify wiring.
    build_called = {"n": 0}
    async def fake_build(**kwargs):
        build_called["n"] += 1
        return {"success": True, "run_id": "auto123", "portfolio_score": 77}
    async def fake_start(**kwargs):
        return {"session_id": "NEW_S", "status": "active"}
    monkeypatch.setattr("engines.portfolio_engine.build_portfolio_from_library", fake_build)
    monkeypatch.setattr("engines.execution_manager.start_execution", fake_start)

    session = {"session_id": "S1", "account_balance": 10000,
               "mode": "paper", "risk_limits": LIMITS}

    # No flag → no rebuild
    r = await cm._auto_rebuild_if_requested(session, cm.DEFAULT_SAFETY_RULES, auto_rebuild=True)
    assert r is None
    assert build_called["n"] == 0

    # Set flag
    from engines import db as _db
    await _db.get_db()[cm.RUN_STATE_COLL].update_one(
        {"_id": "control"},
        {"$set": {"rebuild_requested_at": "2026-04-19T12:00:00+00:00"}},
        upsert=True,
    )
    r = await cm._auto_rebuild_if_requested(session, cm.DEFAULT_SAFETY_RULES, auto_rebuild=True)
    assert r["rebuilt"] is True
    assert r["new_session_id"] == "NEW_S"
    assert build_called["n"] == 1

    # Flag cleared after successful rebuild
    ctrl = await _db.get_db()[cm.RUN_STATE_COLL].find_one({"_id": "control"})
    assert "rebuild_requested_at" not in ctrl


@pytest.mark.asyncio
async def test_auto_rebuild_blocked_by_cooldown(monkeypatch):
    # Flag set but cooldown active → skipped
    from engines import db as _db
    await _db.get_db()[cm.RUN_STATE_COLL].update_one(
        {"_id": "control"},
        {"$set": {"rebuild_requested_at": "2026-04-19T12:00:00+00:00"}},
        upsert=True,
    )
    await cm._set_cooldown(2.0, reason="test")  # noqa: SLF001

    build_called = {"n": 0}
    async def fake_build(**kwargs):
        build_called["n"] += 1
        return {"success": True}
    monkeypatch.setattr("engines.portfolio_engine.build_portfolio_from_library", fake_build)

    r = await cm._auto_rebuild_if_requested({"session_id": "S1"}, {}, auto_rebuild=True)
    assert r["skipped"] == "cooldown_active"
    assert build_called["n"] == 0


# ═════════════════════════════════════════════════════════════════════
# 5. Time filter
# ═════════════════════════════════════════════════════════════════════

def test_is_blocked_hour_detects_membership():
    t = _dt.datetime(2026, 4, 19, 23, 30, tzinfo=_dt.timezone.utc)
    assert cm._is_blocked_hour([22, 23, 0], now=t) is True    # noqa: SLF001
    assert cm._is_blocked_hour([10, 11], now=t) is False      # noqa: SLF001
    assert cm._is_blocked_hour([], now=t) is False            # noqa: SLF001


@pytest.mark.asyncio
async def test_time_filter_overrides_continue_to_pause(monkeypatch):
    async def fake_status(history_limit=1):
        return {"active": {
            "session_id": "S1", "status": "active", "emergency_stop": False,
            "risk_limits": LIMITS, "tracking": _tracking(total_dd=0.5, pf=1.5),
            "allocation": [], "strategies": [], "cbots": [],
            "per_strategy_tracking": [],
        }}
    async def fake_stop(session_id, reason="manual"):
        return {"session_id": session_id, "status": "stopped"}
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)
    monkeypatch.setattr("engines.execution_manager.stop_execution", fake_stop)

    # Force current hour into blocked range
    current_hour = datetime.now(timezone.utc).hour
    r = await cm.tick_and_act(
        dry_run=True,
        safety_rules={"blocked_hours_utc": [current_hour]},
    )
    assert r["decision"]["action"] == "PAUSE"
    assert any("blocked_hour_utc" in rr for rr in r["decision"]["reasons"])


# ═════════════════════════════════════════════════════════════════════
# Regression sanity — Phase 10 behavior unchanged
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_phase10_decide_matrix_still_passes_under_phase10_5(monkeypatch):
    """Smoke: the core decision matrix must still produce the same
    actions when no Phase 10.5 overrides are provided."""
    t = _tracking(total_dd=8.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "PAUSE"       # DANGER → PAUSE (unchanged)

    t = _tracking(total_dd=1.0, pf=0.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "REBUILD_PORTFOLIO"
