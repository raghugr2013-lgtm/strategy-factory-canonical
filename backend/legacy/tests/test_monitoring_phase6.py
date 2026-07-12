"""
Phase 6 Monitoring & Control Layer — backend tests.

Tests /api/monitoring endpoints through the preview URL, seeds
trade_runner_runs / trade_runner_trades in MongoDB for rule scenarios,
and verifies end-to-end breach detection without modifying engines.
"""

import asyncio
import os
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# Load .env so MONGO_URL/DB_NAME are available even outside supervisor.
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fallback to frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().strip('"').rstrip("/")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

MON = f"{BASE_URL}/api/monitoring"

TEST_STRAT = "TEST_strategy_xyz"
TEST_STRAT_UNDERPERF = "TEST_strategy_underperf"
TEST_STRAT_STREAK = "TEST_strategy_streak"
SEED_RUN_TOTAL_DD = "TEST_run_total_dd"
SEED_RUN_DAILY_DD = "TEST_run_daily_dd"
SEED_RUN_UNDERPERF = "TEST_run_underperf"
SEED_RUN_STREAK = "TEST_run_streak"

SEED_RUNS = [SEED_RUN_TOTAL_DD, SEED_RUN_DAILY_DD, SEED_RUN_UNDERPERF, SEED_RUN_STREAK]
SEED_STRATS = [TEST_STRAT, TEST_STRAT_UNDERPERF, TEST_STRAT_STREAK]


# ---------------- helpers ---------------- #

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _clear_seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db["trade_runner_runs"].delete_many({"run_id": {"$in": SEED_RUNS}})
    await db["trade_runner_trades"].delete_many({"run_id": {"$in": SEED_RUNS}})
    await db["strategy_status"].delete_many({"strategy_id": {"$in": SEED_STRATS}})
    client.close()


async def _seed_run(run_id, strategy_id, equity, peak_equity, starting, daily_start, daily_loss_pct=0.0, status="running"):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db["trade_runner_runs"].replace_one(
        {"run_id": run_id},
        {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "equity": equity,
            "peak_equity": peak_equity,
            "account_balance_start": starting,
            "daily_start_equity": daily_start,
            "daily_loss_pct": daily_loss_pct,
            "status": status,
            "started_at": _now_iso(),
            "pair": "EURUSD",
            "timeframe": "H1",
        },
        upsert=True,
    )
    client.close()


async def _seed_trades(run_id, pnls):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    now = datetime.now(timezone.utc)
    docs = []
    for i, pnl in enumerate(pnls):
        docs.append({
            "run_id": run_id,
            "pnl": pnl,
            "closed_at": now.isoformat(),
            "trade_id": f"{run_id}_t{i}",
        })
    await db["trade_runner_trades"].delete_many({"run_id": run_id})
    if docs:
        await db["trade_runner_trades"].insert_many(docs)
    client.close()


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if not asyncio.get_event_loop().is_running() else asyncio.run(coro)


# Use fresh loop per call to avoid "loop already running" issues
def _call(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------- fixtures ---------------- #

@pytest.fixture(scope="module", autouse=True)
def cleanup_and_reset():
    # pre-clean
    _call(_clear_seed())
    # reset defaults + scheduler off
    requests.post(f"{MON}/reset", timeout=15)
    requests.post(f"{MON}/scheduler", json={"enabled": False, "interval_seconds": 60}, timeout=15)
    requests.post(f"{MON}/thresholds", json={
        "daily_dd_threshold_pct": 5.0,
        "total_dd_threshold_pct": 10.0,
        "underperform_pf_threshold": 1.0,
        "underperform_window": 20,
        "loss_streak_threshold": 5,
    }, timeout=15)
    yield
    # teardown
    _call(_clear_seed())
    requests.post(f"{MON}/reset", timeout=15)
    requests.post(f"{MON}/thresholds", json={
        "daily_dd_threshold_pct": 5.0,
        "total_dd_threshold_pct": 10.0,
        "underperform_pf_threshold": 1.0,
        "underperform_window": 20,
        "loss_streak_threshold": 5,
    }, timeout=15)
    requests.post(f"{MON}/scheduler", json={"enabled": False, "interval_seconds": 60}, timeout=15)


@pytest.fixture(autouse=True)
def isolate_each():
    # ensure system back to RUNNING before each test
    requests.post(f"{MON}/reset", timeout=15)
    yield


# ---------------- tests ---------------- #

class TestMonitoringBasics:
    def test_status_defaults(self):
        r = requests.get(f"{MON}/status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["state"] == "RUNNING"
        cfg = data["config"]
        assert cfg["daily_dd_threshold_pct"] == 5.0
        assert cfg["total_dd_threshold_pct"] == 10.0
        assert cfg["underperform_pf_threshold"] == 1.0
        assert cfg["underperform_window"] == 20
        assert cfg["loss_streak_threshold"] == 5

    def test_run_with_no_active_runs(self):
        # ensure no seed runs
        _call(_clear_seed())
        r = requests.post(f"{MON}/run", timeout=20)
        assert r.status_code == 200, r.text
        snap = r.json()
        assert snap["state"] == "RUNNING"
        m = snap["metrics"]
        assert m["active_runs"] == 0
        assert m["portfolio_current_equity"] == 0
        assert snap["breaches"] == []

    def test_thresholds_update_and_persist(self):
        r = requests.post(f"{MON}/thresholds", json={
            "daily_dd_threshold_pct": 3.0,
            "total_dd_threshold_pct": 8.0,
        }, timeout=15)
        assert r.status_code == 200, r.text
        s = requests.get(f"{MON}/status", timeout=15).json()
        assert s["config"]["daily_dd_threshold_pct"] == 3.0
        assert s["config"]["total_dd_threshold_pct"] == 8.0
        # reset to defaults
        requests.post(f"{MON}/thresholds", json={
            "daily_dd_threshold_pct": 5.0, "total_dd_threshold_pct": 10.0
        }, timeout=15)

    def test_thresholds_empty_body_400(self):
        r = requests.post(f"{MON}/thresholds", json={}, timeout=15)
        assert r.status_code == 400

    def test_scheduler_enable_disable(self):
        r = requests.post(f"{MON}/scheduler", json={"enabled": True, "interval_seconds": 5}, timeout=15)
        assert r.status_code == 200, r.text
        s = requests.get(f"{MON}/status", timeout=15).json()
        assert s["scheduler"]["enabled"] is True
        assert s["scheduler"]["interval_seconds"] == 5
        r2 = requests.post(f"{MON}/scheduler", json={"enabled": False, "interval_seconds": 5}, timeout=15)
        assert r2.status_code == 200
        s2 = requests.get(f"{MON}/status", timeout=15).json()
        assert s2["scheduler"]["enabled"] is False


class TestGlobalPauseResume:
    def test_global_stop_then_resume(self):
        r = requests.post(f"{MON}/pause", json={"global_stop": True}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "STOPPED"
        r2 = requests.post(f"{MON}/resume", json={}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["state"] == "RUNNING"

    def test_strategy_manual_pause_and_resume(self):
        r = requests.post(f"{MON}/pause", json={"strategy_id": TEST_STRAT}, timeout=15)
        assert r.status_code == 200, r.text
        strategies = r.json().get("strategies", [])
        found = [s for s in strategies if s.get("strategy_id") == TEST_STRAT]
        assert found, f"strategy_status not written for {TEST_STRAT}"
        assert found[0]["state"] == "PAUSED_MANUAL"

        r2 = requests.post(f"{MON}/resume", json={"strategy_id": TEST_STRAT}, timeout=15)
        assert r2.status_code == 200
        strategies = r2.json().get("strategies", [])
        found = [s for s in strategies if s.get("strategy_id") == TEST_STRAT]
        assert found and found[0]["state"] == "ACTIVE"

    def test_reset_clears_breaches(self):
        r = requests.post(f"{MON}/reset", timeout=15)
        assert r.status_code == 200
        assert r.json()["state"] == "RUNNING"


class TestBreaches:
    def test_total_dd_triggers_stopped(self):
        _call(_clear_seed())
        _call(_seed_run(SEED_RUN_TOTAL_DD, "TEST_strat_totaldd",
                        equity=90, peak_equity=100, starting=100, daily_start=100,
                        daily_loss_pct=0.0, status="running"))
        r = requests.post(f"{MON}/run", timeout=30)
        assert r.status_code == 200, r.text
        snap = r.json()
        assert snap["metrics"]["portfolio_total_dd_pct"] == 10.0
        assert snap["state"] == "STOPPED"
        # ensure an action recorded — even if trade-runner/stop returns non-2xx
        assert any(a.get("action") == "stop_run" for a in snap.get("actions", [])), snap.get("actions")
        # cleanup
        _call(_clear_seed())
        requests.post(f"{MON}/reset", timeout=15)

    def test_daily_dd_triggers_paused_daily(self):
        _call(_clear_seed())
        _call(_seed_run(SEED_RUN_DAILY_DD, "TEST_strat_dailydd",
                        equity=92, peak_equity=100, starting=100, daily_start=100,
                        daily_loss_pct=8.0, status="running"))
        r = requests.post(f"{MON}/run", timeout=30)
        assert r.status_code == 200, r.text
        snap = r.json()
        # portfolio daily dd should be >=5% (computed from daily_start vs equity = 8%)
        assert snap["metrics"]["portfolio_daily_dd_pct"] >= 5.0
        # Should not be STOPPED because total DD is 8% < 10%
        assert snap["state"] == "PAUSED_DAILY", snap
        _call(_clear_seed())
        requests.post(f"{MON}/reset", timeout=15)

    def test_underperform_marks_under_review(self):
        _call(_clear_seed())
        _call(_seed_run(SEED_RUN_UNDERPERF, TEST_STRAT_UNDERPERF,
                        equity=100, peak_equity=100, starting=100, daily_start=100,
                        daily_loss_pct=0.0, status="running"))
        # 20 trades: 5 wins *1, 15 losses *1  -> PF = 5/15 = 0.33
        pnls = [1.0] * 5 + [-1.0] * 15
        _call(_seed_trades(SEED_RUN_UNDERPERF, pnls))

        r = requests.post(f"{MON}/run", timeout=30)
        assert r.status_code == 200, r.text
        snap = r.json()
        strat_rows = [s for s in snap.get("strategies", []) if s.get("strategy_id") == TEST_STRAT_UNDERPERF]
        assert strat_rows, snap.get("strategies")
        # either UNDER_REVIEW or PAUSED_STREAK; since trades order is all losses at end, streak may also trigger
        assert strat_rows[0]["state"] in ("UNDER_REVIEW", "PAUSED_STREAK")
        # verify PF<1.0 recorded
        assert strat_rows[0]["metrics"]["pf_last_n"] < 1.0

        _call(_clear_seed())
        requests.post(f"{MON}/reset", timeout=15)

    def test_loss_streak_paused_streak(self):
        _call(_clear_seed())
        _call(_seed_run(SEED_RUN_STREAK, TEST_STRAT_STREAK,
                        equity=100, peak_equity=100, starting=100, daily_start=100,
                        daily_loss_pct=0.0, status="running"))
        # 5 consecutive losses (less than underperform_window so UNDER_REVIEW not tripped)
        _call(_seed_trades(SEED_RUN_STREAK, [-1.0] * 5))

        r = requests.post(f"{MON}/run", timeout=30)
        assert r.status_code == 200, r.text
        snap = r.json()
        strat_rows = [s for s in snap.get("strategies", []) if s.get("strategy_id") == TEST_STRAT_STREAK]
        assert strat_rows, snap.get("strategies")
        assert strat_rows[0]["state"] == "PAUSED_STREAK"
        assert strat_rows[0]["metrics"]["loss_streak"] >= 5

        _call(_clear_seed())
        requests.post(f"{MON}/reset", timeout=15)

    def test_manual_pause_persists_across_run(self):
        _call(_clear_seed())
        _call(_seed_run(SEED_RUN_STREAK, TEST_STRAT_STREAK,
                        equity=100, peak_equity=100, starting=100, daily_start=100,
                        daily_loss_pct=0.0, status="running"))
        _call(_seed_trades(SEED_RUN_STREAK, [1.0] * 3))  # would normally be ACTIVE

        # Manually pause the strategy
        requests.post(f"{MON}/pause", json={"strategy_id": TEST_STRAT_STREAK}, timeout=15)
        # /pause with strategy_id may issue a stop to trade-runner which can flip
        # the seeded run's status to "stopped". Re-seed it as "running" so the
        # monitor has an active row to process.
        _call(_seed_run(SEED_RUN_STREAK, TEST_STRAT_STREAK,
                        equity=100, peak_equity=100, starting=100, daily_start=100,
                        daily_loss_pct=0.0, status="running"))
        # Run monitor — should NOT flip manual pause back to ACTIVE
        r = requests.post(f"{MON}/run", timeout=30)
        assert r.status_code == 200, r.text
        snap = r.json()
        strat_rows = [s for s in snap.get("strategies", []) if s.get("strategy_id") == TEST_STRAT_STREAK]
        # Verify via monitoring /status (reads strategy_status collection) that
        # manual pause persisted even after /run executed.
        s = requests.get(f"{MON}/status", timeout=15).json()
        persisted = [x for x in s.get("strategies", []) if x.get("strategy_id") == TEST_STRAT_STREAK]
        assert persisted, s.get("strategies")
        assert persisted[0]["state"] == "PAUSED_MANUAL"
        # If strategies were in snapshot, also verify row reflects manual pause
        if strat_rows:
            assert strat_rows[0]["state"] == "PAUSED_MANUAL"

        _call(_clear_seed())
        requests.post(f"{MON}/resume", json={"strategy_id": TEST_STRAT_STREAK}, timeout=15)
        requests.post(f"{MON}/reset", timeout=15)


class TestEquityCurveAndRegression:
    def test_equity_curve_returns_points(self):
        # ensure at least one snapshot exists
        requests.post(f"{MON}/run", timeout=20)
        r = requests.get(f"{MON}/equity-curve", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "count" in data and "points" in data
        assert isinstance(data["points"], list)
        assert data["count"] >= 1

    def test_failsafe_action_non2xx_is_logged(self):
        _call(_clear_seed())
        # Fake run_id that won't exist in trade-runner — stop should 404 but be recorded ok=false
        _call(_seed_run(SEED_RUN_TOTAL_DD, "TEST_strat_failsafe",
                        equity=85, peak_equity=100, starting=100, daily_start=100,
                        daily_loss_pct=0.0, status="running"))
        r = requests.post(f"{MON}/run", timeout=30)
        assert r.status_code == 200, r.text
        snap = r.json()
        assert snap["state"] == "STOPPED"
        actions = snap.get("actions", [])
        assert actions, "expected at least one action recorded"
        # Must NOT raise; either ok True or False both acceptable, but action exists
        assert any(a.get("action") == "stop_run" for a in actions)
        _call(_clear_seed())
        requests.post(f"{MON}/reset", timeout=15)

    def test_regression_trade_runner_runs_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/trade-runner/runs", timeout=15)
        assert r.status_code in (200, 204), f"trade-runner/runs broke: {r.status_code} {r.text[:200]}"

    def test_regression_auto_factory_phase55(self):
        r = requests.get(f"{BASE_URL}/api/auto-factory/status", params={"phase": "5.5"}, timeout=15)
        assert r.status_code == 200, r.text
