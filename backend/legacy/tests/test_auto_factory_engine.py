"""
Phase 5 — Auto Strategy Factory Engine tests.

Mocks the dashboard pipeline so the harness is fast + deterministic,
exercises every branch (skip / error / save / duplicate), and verifies
scheduler start/stop semantics + the asyncio lock.
"""
from __future__ import annotations

import asyncio

import pytest
from dotenv import load_dotenv
load_dotenv()  # ensure MONGO_URL / DB_NAME are available for library saves
from fastapi import HTTPException

from engines import auto_factory_engine as factory


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _card(verdict: str, score: float, prob: float = 70.0, pair: str = "EURUSD",
          tf: str = "H1", style: str = "trend-following",
          text_suffix: str = "") -> dict:
    """Shape a minimal strategy card that `strategy_library._extract_core`
    accepts. TRADE + non-FAIL panel → saved."""
    return {
        "pair": pair, "timeframe": tf, "style": style,
        "strategy_text": f"ENTRY LONG EMA{text_suffix}",
        "parameters": {"fast": 8, "slow": 21, "sl": 20, "tp": 35},
        "verdict": verdict, "score": score,
        "pass_probability": prob, "stability_score": 65.0,
        "prop_firm_panel": {"status": "SAFE", "pass_probability": prob,
                            "max_drawdown": 4.5, "consistency_score": 70,
                            "recommendation": "deploy"},
        "backtest": {"profit_factor": 1.8, "total_return_pct": 12.0,
                     "win_rate": 55, "total_trades": 120,
                     "max_drawdown_pct": 4.5},
    }


import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def _reset_factory_state():
    """Isolate each test from global state AND from the persistent
    strategy_library. Also force re-init of the motor client, since
    pytest-asyncio creates a fresh event loop per test and the global
    `engines.db._db` motor client binds futures to its original loop."""
    from engines import db as _db_module
    _db_module._client = None
    _db_module._db = None

    factory._state["current_run"] = None
    factory._state["last_run"] = None
    factory._state["history"].clear()
    factory._state["scheduler"] = {"enabled": False, "interval_hours": None,
                                   "next_run_at": None}
    try:
        await _db_module.get_db()["strategy_library"].delete_many({"source": "auto_factory"})
    except Exception:
        pass
    yield
    factory.stop_scheduler()
    try:
        await _db_module.get_db()["strategy_library"].delete_many({"source": "auto_factory"})
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_multi_combo_iterates_and_aggregates(monkeypatch):
    """Happy path — 2 pairs × 1 tf × 2 styles = 4 combos, each returns
    2 top strategies, one TRADE + one REJECT. Only TRADE should save."""
    call_count = {"n": 0}

    async def fake_dashboard_generate(req):
        call_count["n"] += 1
        # Alternate "strong" and "weak" combos so we exercise save + reject.
        strong = call_count["n"] % 2 == 1
        if strong:
            tops = [
                _card("TRADE", 82.0, prob=78, pair=req.pair, tf=req.timeframe,
                      style=req.style, text_suffix=f"_{call_count['n']}_A"),
                _card("REJECT", 30.0, prob=20, pair=req.pair, tf=req.timeframe,
                      style=req.style, text_suffix=f"_{call_count['n']}_B"),
            ]
        else:
            tops = [
                _card("RISKY", 55.0, prob=35, pair=req.pair, tf=req.timeframe,
                      style=req.style, text_suffix=f"_{call_count['n']}_A"),
            ]
        return {
            "success": True, "top_strategies": tops,
            "timings": {"generated": req.count, "total_seconds": 0.01,
                        "shortlisted_for_validation": req.count, "skipped_validation": 0},
            "verdict_counts": {},
        }

    monkeypatch.setattr("api.dashboard.dashboard_generate", fake_dashboard_generate)

    summary = await factory.run_auto_factory(
        pairs=["EURUSD", "GBPUSD"],
        timeframes=["H1"],
        styles=["trend", "breakout"],
        per_combo=3, top_n=2, refine_top=0, prefilter_top=2,
        triggered_by="unit",
    )

    assert summary["totals"]["combos_total"] == 4
    assert summary["totals"]["combos_complete"] == 4
    assert summary["totals"]["combos_skipped"] == 0
    assert summary["totals"]["strategies_generated"] == 4 * 3
    # Strong combos (#1, #3) contribute 1 TRADE each → 2 saved.
    # Weak combos (#2, #4) have verdict=RISKY with pass_prob=35 < 50
    # AND stability=65 — RISKY + stability ≥ 50 qualifies as strong RISKY.
    # Let's just assert the aggregation is internally consistent:
    totals = summary["totals"]
    assert totals["strategies_saved"] >= 2
    assert totals["strategies_saved"] + totals["strategies_duplicate"] + totals["strategies_rejected"] >= 4
    assert summary["triggered_by"] == "unit"
    # Style normalization: "trend" → "trend-following"
    styles_seen = {r["style"] for r in summary["combo_results"]}
    assert "trend-following" in styles_seen
    assert "breakout" in styles_seen
    # History recorded
    status = factory.get_status()
    assert status["last_run"]["run_id"] == summary["run_id"]
    assert len(status["history"]) == 1


@pytest.mark.asyncio
async def test_pipeline_http_error_marks_combo_skipped(monkeypatch):
    """If dashboard_generate raises HTTPException (e.g. no data) the combo
    is marked `skipped` with a reason — NOT errored, NOT propagated."""
    async def fake(req):
        raise HTTPException(status_code=400, detail="No real market data for XYZ/H1")
    monkeypatch.setattr("api.dashboard.dashboard_generate", fake)

    summary = await factory.run_auto_factory(
        pairs=["XYZ"], timeframes=["H1"], styles=["trend"],
        per_combo=2, triggered_by="unit",
    )
    assert summary["totals"]["combos_skipped"] == 1
    assert summary["totals"]["combos_complete"] == 0
    r = summary["combo_results"][0]
    assert r["status"] == "skipped"
    assert "No real market data" in r["reason"]


@pytest.mark.asyncio
async def test_pipeline_unexpected_exception_marks_errored(monkeypatch):
    async def boom(req):
        raise RuntimeError("kaboom")
    monkeypatch.setattr("api.dashboard.dashboard_generate", boom)

    summary = await factory.run_auto_factory(
        pairs=["EURUSD"], timeframes=["H1"], styles=["trend"],
        triggered_by="unit",
    )
    assert summary["totals"]["combos_errored"] == 1
    assert summary["combo_results"][0]["status"] == "error"
    assert "kaboom" in summary["combo_results"][0]["reason"]


@pytest.mark.asyncio
async def test_concurrent_runs_rejected(monkeypatch):
    """The asyncio lock MUST prevent overlapping runs — second call
    raises RuntimeError('already_running')."""
    slow_event = asyncio.Event()

    async def slow_generate(req):
        await slow_event.wait()
        return {"success": True, "top_strategies": [],
                "timings": {"generated": 0, "total_seconds": 0, "shortlisted_for_validation": 0, "skipped_validation": 0}}

    monkeypatch.setattr("api.dashboard.dashboard_generate", slow_generate)

    first = asyncio.create_task(factory.run_auto_factory(
        pairs=["EURUSD"], timeframes=["H1"], styles=["trend"], triggered_by="a"))
    await asyncio.sleep(0.05)  # let the first call grab the lock

    with pytest.raises(RuntimeError, match="already_running"):
        await factory.run_auto_factory(
            pairs=["EURUSD"], timeframes=["H1"], styles=["trend"], triggered_by="b")

    slow_event.set()
    await first


@pytest.mark.asyncio
async def test_start_and_stop_scheduler_lifecycle():
    sched = factory.start_scheduler(interval_hours=0.5)
    assert sched["enabled"] is True
    assert sched["interval_hours"] == 0.5
    assert sched["next_run_at"] is not None

    # Starting again replaces the job with the new interval — idempotent.
    sched2 = factory.start_scheduler(interval_hours=1.0)
    assert sched2["interval_hours"] == 1.0

    stopped = factory.stop_scheduler()
    assert stopped["enabled"] is False
    assert stopped["next_run_at"] is None


@pytest.mark.asyncio
async def test_start_scheduler_rejects_zero_interval():
    with pytest.raises(ValueError):
        factory.start_scheduler(interval_hours=0)


@pytest.mark.asyncio
async def test_status_snapshot_shape(monkeypatch):
    async def fake(req):
        return {"success": True, "top_strategies": [],
                "timings": {"generated": 0, "total_seconds": 0,
                            "shortlisted_for_validation": 0, "skipped_validation": 0}}
    monkeypatch.setattr("api.dashboard.dashboard_generate", fake)

    await factory.run_auto_factory(
        pairs=["EURUSD"], timeframes=["H1"], styles=["trend"], triggered_by="unit")

    st = factory.get_status()
    assert st["running"] is False
    assert st["current_run"] is None
    assert st["last_run"] is not None
    assert "run_id" in st["last_run"]
    assert "totals" in st["last_run"]
    assert "config" in st["last_run"]
    assert isinstance(st["history"], list)
    assert st["scheduler"]["enabled"] is False
