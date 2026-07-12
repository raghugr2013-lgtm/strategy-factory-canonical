"""
Phase 8 — Live Execution Manager tests.

Covers session lifecycle (start / stop / emergency_stop), single-active-session
guard, portfolio validation, Go/No-Go gate under every breach condition,
auto-halt on tracking refresh, and cBot generation wiring (mocked so tests
don't touch the compile pipeline directly).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from engines import execution_manager as em


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

def _portfolio(run_id: str = "test_run_1") -> dict:
    """Minimal Phase-7 shaped portfolio."""
    return {
        "run_id": run_id,
        "portfolio_score": 74.2,
        "strategies": [
            {"strategy_id": "s1", "pair": "EURUSD", "timeframe": "H1",
             "style": "trend-following", "strategy_text": "entry long ema",
             "max_drawdown_pct": 4.0, "profit_factor": 1.8,
             "win_rate": 55, "total_return_pct": 12.0,
             "pass_probability": 72, "stability_score": 65},
            {"strategy_id": "s2", "pair": "GBPUSD", "timeframe": "H4",
             "style": "breakout", "strategy_text": "breakout",
             "max_drawdown_pct": 5.0, "profit_factor": 1.5,
             "win_rate": 52, "total_return_pct": 10.0,
             "pass_probability": 68, "stability_score": 60},
        ],
        "allocation": [
            {"strategy_id": "s1", "capital_pct": 0.55, "risk_per_trade_pct": 1.25,
             "pair": "EURUSD", "timeframe": "H1", "style": "trend-following"},
            {"strategy_id": "s2", "capital_pct": 0.45, "risk_per_trade_pct": 1.0,
             "pair": "GBPUSD", "timeframe": "H4", "style": "breakout"},
        ],
    }


@pytest_asyncio.fixture(autouse=True)
async def _fresh(monkeypatch):
    """Reset motor + test collections AND mock the cBot compile pipeline."""
    from engines import db as _db_module
    _db_module._client = None
    _db_module._db = None
    db = _db_module.get_db()
    await db["execution_sessions"].delete_many({})
    await db["portfolios"].delete_many({})
    await db["live_tracking"].delete_many({})

    # Mock build_reliable_cbot — we just verify the WIRING, not the
    # compile pipeline (which has its own 50+ tests).
    def _fake_build(profile, safety_rules=None):
        return {
            "code": f"// cBot for {profile.get('pair')}/{profile.get('timeframe')}\nclass Bot{{}}",
            "compile_status": "success",
            "attempts": 1,
            "errors": [], "warnings": [],
            "bot_name": f"Bot_{profile.get('pair')}_{profile.get('timeframe')}",
            "indicators_used": ["EMA"],
            "safety": {"applied": True},
            "fix_log": [], "placeholders_filled": [],
        }
    monkeypatch.setattr("engines.cbot_pipeline.build_reliable_cbot", _fake_build)

    yield
    await db["execution_sessions"].delete_many({})
    await db["portfolios"].delete_many({})
    await db["live_tracking"].delete_many({})


# ─────────────────────────────────────────────────────────────────────
# Go/No-Go gate — pure logic
# ─────────────────────────────────────────────────────────────────────

def test_go_no_go_allows_when_all_clean():
    session = {"risk_limits": {}, "emergency_stop": False,
               "tracking": {"total_drawdown_pct": 1.0, "daily_drawdown_pct": 0.5,
                            "loss_streak": 0, "recent_profit_factor": 1.5}}
    g = em.go_no_go(session)
    assert g["allow"] is True
    assert g["verdict"] == "GO"
    assert g["reasons"] == []


def test_go_no_go_blocks_on_emergency():
    g = em.go_no_go({"emergency_stop": True, "tracking": {}})
    assert g["allow"] is False
    assert "emergency_stop" in g["reasons"]


def test_go_no_go_blocks_on_total_dd():
    g = em.go_no_go({"emergency_stop": False,
                     "tracking": {"total_drawdown_pct": 10.0}})
    assert g["allow"] is False
    assert any("total_dd_breached" in r for r in g["reasons"])


def test_go_no_go_blocks_on_daily_dd():
    g = em.go_no_go({"tracking": {"daily_drawdown_pct": 5.0}})
    assert not g["allow"]
    assert any("daily_dd_breached" in r for r in g["reasons"])


def test_go_no_go_blocks_on_loss_streak():
    g = em.go_no_go({"tracking": {"loss_streak": 6}})
    assert not g["allow"]
    assert any("loss_streak" in r for r in g["reasons"])


def test_go_no_go_blocks_on_weak_pf():
    g = em.go_no_go({"tracking": {"recent_profit_factor": 0.3}})
    assert not g["allow"]
    assert any("weak_recent_pf" in r for r in g["reasons"])


def test_go_no_go_honors_custom_limits():
    # Custom stricter limit: total DD ≥ 2% blocks
    g = em.go_no_go({
        "risk_limits": {"max_total_drawdown_pct": 2.0},
        "tracking": {"total_drawdown_pct": 3.0},
    })
    assert not g["allow"]
    assert any("total_dd_breached" in r for r in g["reasons"])


# ─────────────────────────────────────────────────────────────────────
# start_execution
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_execution_happy_path():
    s = await em.start_execution(portfolio=_portfolio(), account_balance=10000, mode="paper")
    assert s["status"] == "active"
    assert s["mode"] == "paper"
    assert len(s["cbots"]) == 2
    assert all(c["compile_status"] == "success" for c in s["cbots"])
    assert s["go_no_go"]["allow"] is True
    assert s["tracking"]["total_trades"] == 0


@pytest.mark.asyncio
async def test_start_execution_rejects_when_active():
    await em.start_execution(portfolio=_portfolio(), account_balance=10000)
    with pytest.raises(RuntimeError, match="already_active"):
        await em.start_execution(portfolio=_portfolio("test_run_2"), account_balance=10000)


@pytest.mark.asyncio
async def test_start_execution_requires_portfolio():
    with pytest.raises(ValueError, match="required"):
        await em.start_execution(account_balance=10000)


@pytest.mark.asyncio
async def test_start_execution_rejects_bad_mode():
    with pytest.raises(ValueError, match="mode"):
        await em.start_execution(portfolio=_portfolio(), mode="live_real_money")


@pytest.mark.asyncio
async def test_start_execution_loads_by_run_id():
    from engines import db as _db
    db = _db.get_db()
    p = _portfolio("persisted_42")
    await db["portfolios"].insert_one({**p, "created_at": "2026-04-19"})

    s = await em.start_execution(portfolio_run_id="persisted_42", account_balance=5000)
    assert s["portfolio_run_id"] == "persisted_42"
    assert len(s["strategies"]) == 2


@pytest.mark.asyncio
async def test_start_execution_unknown_portfolio_id_raises():
    with pytest.raises(ValueError, match="not found"):
        await em.start_execution(portfolio_run_id="does_not_exist")


# ─────────────────────────────────────────────────────────────────────
# stop / emergency_stop / refresh_tracking
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_execution_marks_session_stopped():
    s = await em.start_execution(portfolio=_portfolio(), account_balance=10000)
    stopped = await em.stop_execution(s["session_id"], reason="test")
    assert stopped["status"] == "stopped"
    assert stopped["stop_reason"] == "test"
    # Can now start another session
    s2 = await em.start_execution(portfolio=_portfolio("r2"), account_balance=10000)
    assert s2["status"] == "active"


@pytest.mark.asyncio
async def test_stop_execution_unknown_session_raises():
    with pytest.raises(ValueError, match="not found"):
        await em.stop_execution("nope")


@pytest.mark.asyncio
async def test_emergency_stop_sets_flag_and_halts():
    s = await em.start_execution(portfolio=_portfolio(), account_balance=10000)
    stopped = await em.emergency_stop()
    assert stopped["status"] == "stopped"
    assert stopped["emergency_stop"] is True
    assert stopped["stop_reason"] == "emergency"


@pytest.mark.asyncio
async def test_emergency_stop_no_active_session():
    result = await em.emergency_stop()
    assert result["status"] == "no_active_session"


@pytest.mark.asyncio
async def test_refresh_tracking_auto_halts_on_breach():
    """Seed a live_tracking row with DD > limit → refresh must auto-halt."""
    from engines import db as _db
    db = _db.get_db()

    s = await em.start_execution(
        portfolio=_portfolio(), account_balance=10000,
        risk_limits={"max_total_drawdown_pct": 3.0},
    )
    # Inject a breach via live_tracking on strategy s1 (55% weight)
    await db["live_tracking"].insert_one({
        "strategy_id": "s1",
        "status": "FAILING",
        "live_metrics": {
            "max_drawdown_pct": 10.0,            # way above the 3% limit
            "max_daily_drawdown_pct": 1.0,
            "total_trades": 25,
            "current_loss_streak": 2,
            "profit_factor": 0.8,
            "win_rate": 40, "total_return_pct": -5.0,
        },
    })

    refreshed = await em.refresh_tracking(s["session_id"])
    assert refreshed["status"] == "stopped"
    assert refreshed["go_no_go"]["allow"] is False
    assert any("total_dd_breached" in r for r in refreshed["go_no_go"]["reasons"])
    assert refreshed.get("stop_reason", "").startswith("auto_halt")


@pytest.mark.asyncio
async def test_get_status_returns_active_plus_history():
    s1 = await em.start_execution(portfolio=_portfolio(), account_balance=10000)
    await em.stop_execution(s1["session_id"], reason="done")
    s2 = await em.start_execution(portfolio=_portfolio("r2"), account_balance=10000)

    status = await em.get_status()
    assert status["active"] is not None
    assert status["active"]["session_id"] == s2["session_id"]
    assert status["total_sessions"] == 2
    assert len(status["history"]) == 2
    # history items must NOT include heavy fields
    for h in status["history"]:
        assert "strategies" not in h
        assert "cbots" not in h
