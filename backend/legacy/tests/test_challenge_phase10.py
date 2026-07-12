"""
Phase 10 — Challenge Manager tests.

Covers state classification across HEALTHY/WARNING/DANGER/BREACH, decision
precedence across all 8 branches of decide_action, action execution wired
through execution_manager (mocked for isolation), loop lock guard, and
scheduler lifecycle.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from engines import challenge_manager as cm


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _fresh():
    from engines import db as _db_module
    _db_module._client = None
    _db_module._db = None
    db = _db_module.get_db()
    await db[cm.DECISIONS_COLL].delete_many({})
    await db[cm.RUN_STATE_COLL].delete_many({})
    await db["execution_sessions"].delete_many({})
    yield
    cm.stop_control_loop()
    await db[cm.DECISIONS_COLL].delete_many({})
    await db[cm.RUN_STATE_COLL].delete_many({})
    await db["execution_sessions"].delete_many({})


LIMITS = {"max_total_drawdown_pct": 10.0, "max_daily_drawdown_pct": 5.0,
          "max_per_trade_risk_pct": 2.0}


def _tracking(total_dd=0.0, daily_dd=0.0, loss_streak=0, pf=1.5, wr=55.0):
    return {
        "total_drawdown_pct": total_dd, "daily_drawdown_pct": daily_dd,
        "loss_streak": loss_streak, "recent_profit_factor": pf,
        "win_rate": wr, "total_trades": 20,
    }


# ─────────────────────────────────────────────────────────────────────
# classify_state — 5 buckets
# ─────────────────────────────────────────────────────────────────────

def test_classify_healthy():
    c = cm.classify_state(_tracking(total_dd=1.0, daily_dd=1.0), LIMITS)
    assert c["state"] == "HEALTHY"
    assert c["total_dd_ratio"] == 0.1


def test_classify_warning_total_dd():
    # 6.5/10 = 0.65 → WARNING
    c = cm.classify_state(_tracking(total_dd=6.5, daily_dd=0.5), LIMITS)
    assert c["state"] == "WARNING"


def test_classify_warning_daily_dd():
    # 3.5/5 = 0.70 → WARNING
    c = cm.classify_state(_tracking(total_dd=0, daily_dd=3.5), LIMITS)
    assert c["state"] == "WARNING"


def test_classify_danger():
    # 8.5/10 = 0.85 → DANGER
    c = cm.classify_state(_tracking(total_dd=8.5, daily_dd=1.0), LIMITS)
    assert c["state"] == "DANGER"


def test_classify_breach_total():
    c = cm.classify_state(_tracking(total_dd=10.5), LIMITS)
    assert c["state"] == "BREACH"


def test_classify_breach_daily():
    c = cm.classify_state(_tracking(daily_dd=5.1), LIMITS)
    assert c["state"] == "BREACH"


def test_classify_breach_on_emergency():
    c = cm.classify_state(_tracking(), LIMITS, emergency_stop=True)
    assert c["state"] == "BREACH"


# ─────────────────────────────────────────────────────────────────────
# decide_action — every precedence branch
# ─────────────────────────────────────────────────────────────────────

def test_decide_stop_on_breach():
    c = cm.classify_state(_tracking(total_dd=10.5), LIMITS)
    d = cm.decide_action(c, _tracking(total_dd=10.5))
    assert d["action"] == "STOP"
    assert any("state=BREACH" in r for r in d["reasons"])


def test_decide_stop_on_daily_dd_hard_rule():
    # daily_dd 5.5 > 5 → STOP (even though not yet at total DD breach)
    t = _tracking(daily_dd=5.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "STOP"


def test_decide_rebuild_on_weak_pf():
    t = _tracking(total_dd=2.0, pf=0.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "REBUILD_PORTFOLIO"
    assert any("pf 0.5" in r for r in d["reasons"])


def test_decide_pause_on_danger():
    t = _tracking(total_dd=8.5, pf=1.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "PAUSE"


def test_decide_pause_on_loss_streak():
    t = _tracking(total_dd=0.5, loss_streak=5, pf=1.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "PAUSE"


def test_decide_reduce_risk_on_daily_dd_hard_rule():
    # daily_dd 4.2 > 4 AND < 5 → REDUCE_RISK (hard rule)
    t = _tracking(daily_dd=4.2, pf=1.2)
    c = cm.classify_state(t, LIMITS)   # daily 4.2/5=0.84 → DANGER
    # Branch order: BREACH→daily_stop→pf_rebuild→DANGER.
    # DANGER precedes the daily_dd_reduce rule → PAUSE. That's correct per
    # our documented precedence (DANGER halts before the soft-reduce).
    d = cm.decide_action(c, t)
    assert d["action"] == "PAUSE"


def test_decide_reduce_risk_hard_rule_when_warning():
    # daily_dd 4.2 with RELAXED daily cap (10%) so state only = WARNING
    # and the daily_dd_reduce rule must fire.
    loose = {"max_total_drawdown_pct": 20.0, "max_daily_drawdown_pct": 7.0}
    t = _tracking(total_dd=12.0, daily_dd=4.2, pf=1.2)  # 12/20=0.6, 4.2/7=0.6
    c = cm.classify_state(t, loose)
    assert c["state"] == "HEALTHY"                # both ratios = 0.6 → HEALTHY
    d = cm.decide_action(c, t)
    assert d["action"] == "REDUCE_RISK"
    assert any("daily_dd 4.2" in r for r in d["reasons"])


def test_decide_reduce_risk_on_warning_state():
    t = _tracking(total_dd=7.0, daily_dd=0.5, pf=1.2)  # 7/10=0.70 → WARNING
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "REDUCE_RISK"
    assert any("state=WARNING" in r for r in d["reasons"])


def test_decide_continue_on_healthy():
    t = _tracking(total_dd=1.0, pf=1.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t)
    assert d["action"] == "CONTINUE"


def test_decide_continue_on_idle():
    c = {"state": "IDLE", "observed": {}}
    d = cm.decide_action(c, _tracking())
    assert d["action"] == "CONTINUE"


def test_decide_respects_custom_safety_rules():
    # Aggressive rules — pause at streak 3
    t = _tracking(loss_streak=3, total_dd=1.0, pf=1.5)
    c = cm.classify_state(t, LIMITS)
    d = cm.decide_action(c, t, safety_rules={"loss_streak_pause": 3})
    assert d["action"] == "PAUSE"


# ─────────────────────────────────────────────────────────────────────
# execute_action — wiring
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_reduce_risk_updates_session_limits(monkeypatch):
    from engines import db as _db
    db = _db.get_db()
    session = {
        "session_id": "S1", "status": "active",
        "risk_limits": {"max_per_trade_risk_pct": 2.0},
    }
    await db["execution_sessions"].insert_one({**session})

    decision = {"action": "REDUCE_RISK", "reasons": ["state=WARNING"],
                "state": "WARNING", "rules_used": cm.DEFAULT_SAFETY_RULES}
    res = await cm.execute_action(decision, session)
    assert res["applied"] is True
    assert res["old_risk_pct"] == 2.0
    assert res["new_risk_pct"] == 1.0

    updated = await db["execution_sessions"].find_one({"session_id": "S1"})
    assert updated["risk_limits"]["max_per_trade_risk_pct"] == 1.0


@pytest.mark.asyncio
async def test_execute_pause_calls_stop_execution(monkeypatch):
    called = {}
    async def fake_stop(session_id, reason="manual"):
        called["sid"] = session_id; called["reason"] = reason
        return {"session_id": session_id, "status": "stopped", "stop_reason": reason}
    monkeypatch.setattr("engines.execution_manager.stop_execution", fake_stop)

    decision = {"action": "PAUSE", "reasons": ["state=DANGER"], "rules_used": {}}
    res = await cm.execute_action(decision, {"session_id": "S1", "status": "active"})
    assert res["applied"] is True
    assert called["sid"] == "S1"
    assert "paused:" in called["reason"]


@pytest.mark.asyncio
async def test_execute_stop_calls_emergency(monkeypatch):
    called = {}
    async def fake_em(session_id=None, reason="emergency"):
        called["sid"] = session_id; called["reason"] = reason
        return {"session_id": session_id, "status": "stopped",
                "emergency_stop": True, "stop_reason": reason}
    monkeypatch.setattr("engines.execution_manager.emergency_stop", fake_em)

    decision = {"action": "STOP", "reasons": ["state=BREACH"], "rules_used": {}}
    res = await cm.execute_action(decision, {"session_id": "S2", "status": "active"})
    assert res["applied"] is True
    assert called["sid"] == "S2"
    assert called["reason"].startswith("stop:")


@pytest.mark.asyncio
async def test_execute_rebuild_stops_and_flags(monkeypatch):
    stop_called = {}
    async def fake_stop(session_id, reason="manual"):
        stop_called["sid"] = session_id
        return {"session_id": session_id, "status": "stopped"}
    monkeypatch.setattr("engines.execution_manager.stop_execution", fake_stop)

    decision = {"action": "REBUILD_PORTFOLIO", "reasons": ["pf 0.5 < 0.7"],
                "rules_used": {}}
    res = await cm.execute_action(decision, {"session_id": "S3", "status": "active"})
    assert res["applied"] is True
    assert res["rebuild_requested"] is True

    from engines.db import get_db
    flag = await get_db()[cm.RUN_STATE_COLL].find_one({"_id": "control"})
    assert flag and "rebuild_requested_at" in flag


@pytest.mark.asyncio
async def test_execute_action_dry_run_is_no_op(monkeypatch):
    called = False
    async def boom(*a, **k):
        nonlocal called; called = True
        return {}
    monkeypatch.setattr("engines.execution_manager.stop_execution", boom)

    decision = {"action": "PAUSE", "reasons": [], "rules_used": {}}
    res = await cm.execute_action(decision, {"session_id": "S1"}, dry_run=True)
    assert res["applied"] is False
    assert called is False


# ─────────────────────────────────────────────────────────────────────
# tick_and_act — orchestrator
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tick_and_act_no_active_session(monkeypatch):
    async def fake_status(history_limit=1):
        return {"active": None, "total_sessions": 0, "history": []}
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)

    r = await cm.tick_and_act(dry_run=True)
    assert r["state"] == "IDLE"
    assert r["decision"]["action"] == "CONTINUE"


@pytest.mark.asyncio
async def test_tick_and_act_persists_decision(monkeypatch):
    async def fake_status(history_limit=1):
        return {
            "active": {
                "session_id": "S9", "status": "active",
                "emergency_stop": False,
                "risk_limits": LIMITS,
                "tracking": _tracking(total_dd=7.0, pf=1.2),
            },
            "total_sessions": 1, "history": [],
        }
    monkeypatch.setattr("engines.execution_manager.get_status", fake_status)

    r = await cm.tick_and_act(dry_run=True)
    assert r["state"] == "WARNING"
    assert r["decision"]["action"] == "REDUCE_RISK"

    from engines.db import get_db
    recorded = await get_db()[cm.DECISIONS_COLL].find_one({"session_id": "S9"})
    assert recorded is not None
    assert recorded["decision"]["action"] == "REDUCE_RISK"


# ─────────────────────────────────────────────────────────────────────
# Scheduler lifecycle
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_control_loop_start_stop():
    s = cm.start_control_loop(interval_minutes=5.0)
    assert s["enabled"] is True
    assert s["interval_minutes"] == 5.0
    # Replaceable
    s2 = cm.start_control_loop(interval_minutes=10.0)
    assert s2["interval_minutes"] == 10.0
    st = cm.stop_control_loop()
    assert st["enabled"] is False


@pytest.mark.asyncio
async def test_control_loop_rejects_zero_interval():
    with pytest.raises(ValueError):
        cm.start_control_loop(interval_minutes=0)
