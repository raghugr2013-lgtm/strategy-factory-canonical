"""
Phase 11 — Gem Factory tests.

Covers the strict quality filter, refinement band, M1 strict gate,
library eligibility rule, competition cap, lifecycle fields, degradation
sweep state machine (active → degrading → retired), and the M1 timeframe
guard (M1 blocked when m1_mode='off', allowed when m1_mode='strict').
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from engines import gem_factory_engine as gf


LIB = "strategy_library"


@pytest_asyncio.fixture(autouse=True)
async def _fresh():
    from engines import db as _db_module
    _db_module._client = None
    _db_module._db = None
    db = _db_module.get_db()
    for c in (LIB, "live_tracking", gf.RUN_STATE_COLL):
        await db[c].delete_many({})
    yield
    for c in (LIB, "live_tracking", gf.RUN_STATE_COLL):
        await db[c].delete_many({})


def _card(**over):
    c = {
        "pair": "EURUSD", "timeframe": "H1", "style": "trend-following",
        "strategy_text": "ema cross", "score": 75, "verdict": "TRADE",
        "pass_probability": 65, "stability_score": 60,
        "backtest": {"profit_factor": 1.5, "max_drawdown_pct": 5.0,
                     "total_trades": 80, "win_rate": 54, "total_return_pct": 10},
    }
    c.update(over)
    return c


# ─────────────────────────────────────────────────────────────────────
# Strict quality filter (Step 3)
# ─────────────────────────────────────────────────────────────────────

def test_strict_floor_passes_strong_card():
    ok, reasons = gf._passes_strict_floor(_card())
    assert ok and reasons == []


def test_strict_floor_rejects_low_pf():
    ok, reasons = gf._passes_strict_floor(_card(backtest={"profit_factor": 1.0,
                                                           "max_drawdown_pct": 5,
                                                           "total_trades": 80}))
    assert not ok and any("pf" in r for r in reasons)


def test_strict_floor_rejects_low_stability():
    ok, reasons = gf._passes_strict_floor(_card(stability_score=40))
    assert not ok and any("stability" in r for r in reasons)


def test_strict_floor_rejects_high_dd():
    ok, _ = gf._passes_strict_floor(_card(
        backtest={"profit_factor": 1.5, "max_drawdown_pct": 12, "total_trades": 80}))
    assert not ok


def test_strict_floor_rejects_low_trades():
    ok, _ = gf._passes_strict_floor(_card(
        backtest={"profit_factor": 1.5, "max_drawdown_pct": 5, "total_trades": 20}))
    assert not ok


def test_strict_floor_rejects_low_pass_prob():
    ok, _ = gf._passes_strict_floor(_card(pass_probability=40))
    assert not ok


# ─────────────────────────────────────────────────────────────────────
# Refinement band (Step 4)
# ─────────────────────────────────────────────────────────────────────

def test_borderline_pf():
    assert gf._is_borderline(_card(backtest={"profit_factor": 1.0,
                                              "max_drawdown_pct": 5, "total_trades": 80})) is True


def test_borderline_stability():
    assert gf._is_borderline(_card(stability_score=45)) is True


def test_not_borderline_when_deeply_bad():
    # pf=0.5 is BELOW the refine band → not borderline (reject straight out).
    assert gf._is_borderline(_card(backtest={"profit_factor": 0.5,
                                              "max_drawdown_pct": 5, "total_trades": 80})) is False


def test_not_borderline_when_already_strong():
    assert gf._is_borderline(_card()) is False


# ─────────────────────────────────────────────────────────────────────
# Library eligibility (Step 6)
# ─────────────────────────────────────────────────────────────────────

def test_eligible_trade_always_saves():
    assert gf._eligible_for_library(_card(verdict="TRADE", score=40)) is True


def test_eligible_safe_prop_saves():
    assert gf._eligible_for_library(
        _card(verdict="RISKY", prop_status="SAFE", score=40)) is True


def test_eligible_strong_risky_saves():
    assert gf._eligible_for_library(
        _card(verdict="RISKY", prop_status="WARN", score=60)) is True


def test_not_eligible_weak_risky():
    assert gf._eligible_for_library(
        _card(verdict="RISKY", prop_status="WARN", score=50)) is False


def test_not_eligible_reject():
    assert gf._eligible_for_library(
        _card(verdict="REJECT", prop_status="FAIL", score=80)) is False


# ─────────────────────────────────────────────────────────────────────
# M1 strict gate (Step 11)
# ─────────────────────────────────────────────────────────────────────

def test_m1_strict_rejects_insufficient_trades():
    ok, _ = gf._passes_m1_strict(_card(backtest={"profit_factor": 1.5,
                                                  "max_drawdown_pct": 5,
                                                  "total_trades": 80}))
    assert not ok


def test_m1_strict_passes_highbar():
    ok, _ = gf._passes_m1_strict(_card(
        stability_score=65,
        backtest={"profit_factor": 1.5, "max_drawdown_pct": 5,
                  "total_trades": 250, "win_rate": 55}))
    assert ok


# ─────────────────────────────────────────────────────────────────────
# Competition cap (Step 5)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_competition_cap_keeps_top_n():
    cards = [
        _card(strategy_id=f"s{i}", score=90 - i,
              pair="EURUSD", timeframe="H1", style="trend-following")
        for i in range(5)
    ]
    winners = await gf._competition_cap(cards, "EURUSD", "H1", "trend-following", keep=3)
    assert len(winners) == 3
    assert [w["strategy_id"] for w in winners] == ["s0", "s1", "s2"]


# ─────────────────────────────────────────────────────────────────────
# M1 timeframe guard (Step 10)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_m1_blocked_when_mode_off(monkeypatch):
    async def fake_combo(*a, **k):
        return {"status": "complete", "generated": 0, "top_returned": 0,
                "saved": 0, "saved_ids": [], "runtime_sec": 0.0}
    monkeypatch.setattr("engines.auto_factory_engine._run_one_combo", fake_combo)

    r = await gf.run_gem_factory(
        pairs=["EURUSD"], timeframes=["M1"], styles=["trend-following"],
        per_combo=30, m1_mode="off",
    )
    assert r["config"]["timeframes_blocked"] == ["M1"]
    assert r["config"]["timeframes"] == []        # all approved dropped
    assert r["totals"]["slots_processed"] == 0


@pytest.mark.asyncio
async def test_m1_allowed_only_in_strict_mode(monkeypatch):
    async def fake_combo(*a, **k):
        return {"status": "complete", "generated": 0, "top_returned": 0,
                "saved": 0, "saved_ids": [], "runtime_sec": 0.0}
    monkeypatch.setattr("engines.auto_factory_engine._run_one_combo", fake_combo)

    r = await gf.run_gem_factory(
        pairs=["EURUSD"], timeframes=["M1"], styles=["trend-following"],
        per_combo=30, m1_mode="strict",
    )
    assert r["config"]["timeframes"] == ["M1"]
    assert r["config"]["timeframes_blocked"] == []


# ─────────────────────────────────────────────────────────────────────
# Degradation sweep (Steps 7 + 8)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sweep_flips_active_to_degrading_then_retired():
    from engines import db as _db
    db = _db.get_db()
    # Seed an active library row + a failing live_tracking row.
    await db[LIB].insert_one({
        "strategy_id": "sg1", "fingerprint": "fp_sg1",
        "pair": "EURUSD", "timeframe": "H1", "style": "trend-following",
        "status": "active", "rolling_dd": 3.0,
        "source": "gem_factory",
    })
    await db["live_tracking"].insert_one({
        "strategy_id": "sg1", "status": "WEAK",
        "live_metrics": {"profit_factor": 0.5, "current_loss_streak": 1,
                         "max_drawdown_pct": 4.0, "win_rate": 45},
    })

    # First sweep → active → degrading
    r1 = await gf.sweep_degradation()
    assert any(x["strategy_id"] == "sg1" for x in r1["degrading"])
    assert r1["retired"] == []
    updated = await db[LIB].find_one({"strategy_id": "sg1"})
    assert updated["status"] == "degrading"
    assert updated["rolling_pf"] == 0.5

    # Second consecutive sweep with the same failure → degrading → retired
    r2 = await gf.sweep_degradation()
    assert any(x["strategy_id"] == "sg1" for x in r2["retired"])
    final = await db[LIB].find_one({"strategy_id": "sg1"})
    assert final["status"] == "retired"


@pytest.mark.asyncio
async def test_sweep_recovers_to_active_when_metrics_clean():
    from engines import db as _db
    db = _db.get_db()
    await db[LIB].insert_one({
        "strategy_id": "sg_ok", "fingerprint": "fp_sg_ok", "status": "degrading",
        "pair": "EURUSD", "timeframe": "H1", "style": "trend",
    })
    await db["live_tracking"].insert_one({
        "strategy_id": "sg_ok",
        "live_metrics": {"profit_factor": 1.5, "current_loss_streak": 0,
                         "max_drawdown_pct": 3.0, "win_rate": 56},
    })

    await gf.sweep_degradation()
    final = await db[LIB].find_one({"strategy_id": "sg_ok"})
    assert final["status"] == "active"
    assert final["degrade_reasons"] == []


@pytest.mark.asyncio
async def test_sweep_leaves_rows_without_live_tracking_untouched():
    from engines import db as _db
    db = _db.get_db()
    await db[LIB].insert_one({
        "strategy_id": "sg_new", "fingerprint": "fp_sg_new", "status": "active",
        "pair": "EURUSD", "timeframe": "H1", "style": "trend",
    })
    await gf.sweep_degradation()
    row = await db[LIB].find_one({"strategy_id": "sg_new"})
    # Still active, no rolling metrics touched since no live data
    assert row["status"] == "active"
    assert row.get("rolling_pf") is None


# ─────────────────────────────────────────────────────────────────────
# Concurrency guard
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_run_rejected(monkeypatch):
    import asyncio as _a

    blocker = _a.Event()
    async def slow_combo(*a, **k):
        await blocker.wait()
        return {"status": "complete", "generated": 0, "top_returned": 0,
                "saved": 0, "saved_ids": [], "runtime_sec": 0.0}
    monkeypatch.setattr("engines.auto_factory_engine._run_one_combo", slow_combo)

    first = _a.create_task(gf.run_gem_factory(
        pairs=["EURUSD"], timeframes=["H1"], styles=["trend-following"],
        per_combo=30, m1_mode="off"))
    await _a.sleep(0.05)
    with pytest.raises(RuntimeError, match="already_running"):
        await gf.run_gem_factory(
            pairs=["EURUSD"], timeframes=["H1"], styles=["trend-following"],
            per_combo=30, m1_mode="off")
    blocker.set()
    await first


@pytest.mark.asyncio
async def test_rejects_invalid_m1_mode():
    with pytest.raises(ValueError):
        await gf.run_gem_factory(m1_mode="yolo")


# ─────────────────────────────────────────────────────────────────────
# Status shape
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_returns_library_counts():
    from engines import db as _db
    db = _db.get_db()
    await db[LIB].insert_many([
        {"strategy_id": "a1", "fingerprint": "fp_a1", "status": "active"},
        {"strategy_id": "a2", "fingerprint": "fp_a2", "status": "active"},
        {"strategy_id": "d1", "fingerprint": "fp_d1", "status": "degrading"},
        {"strategy_id": "r1", "fingerprint": "fp_r1", "status": "retired"},
        {"strategy_id": "m1", "fingerprint": "fp_m1", "status": "active", "m1_generation": True},
    ])
    s = await gf.get_status()
    assert s["library_counts"]["active"] == 3
    assert s["library_counts"]["degrading"] == 1
    assert s["library_counts"]["retired"] == 1
    assert s["library_counts"]["m1_generated"] == 1
    assert s["rules"]["quality_floor"]["min_profit_factor"] == 1.2
    assert s["data_window_policy"]["BID"].startswith("2022")
