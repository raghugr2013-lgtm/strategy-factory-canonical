"""Backend tests for Safe Execution Layer (Paper Trading) - Phase Safe-Exec."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
           "http://localhost:8001"

API = f"{BASE_URL}/api"
PORTFOLIO_ID = "pb_seed_001"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---- Ensure clean state: stop any running paper run -------------
@pytest.fixture(scope="module", autouse=True)
def _clean_active(session):
    try:
        r = session.get(f"{API}/execution/paper/status", timeout=10)
        if r.status_code == 200:
            active = (r.json() or {}).get("active")
            if active and active.get("status") == "running":
                session.post(f"{API}/execution/paper/stop",
                             json={"run_id": active["run_id"]}, timeout=10)
                time.sleep(0.5)
    except Exception:
        pass
    yield


# ---- Health / non-regression of existing endpoints --------------
class TestNonRegression:
    def test_health(self, session):
        r = session.get(f"{API}/health", timeout=10)
        assert r.status_code == 200

    def test_execution_status_still_works(self, session):
        r = session.get(f"{API}/execution/status", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # structure: should have active/history keys
        assert isinstance(data, dict)


# ---- /config --------------------------------------------------
class TestPaperConfig:
    def test_config_defaults_and_sources(self, session):
        r = session.get(f"{API}/execution/paper/config", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "defaults" in d and "sources" in d
        assert d["defaults"]["account_balance"] == 10000.0
        assert d["defaults"]["risk_pct"] == 1.0
        assert d["defaults"]["daily_loss_limit_pct"] == 5.0
        assert d["defaults"]["total_loss_limit_pct"] == 10.0
        assert "bid_1m" in d["sources"]
        assert "bi5" in d["sources"]


# ---- Full lifecycle run --------------------------------------
class TestPaperLifecycle:
    run_id = None
    strategy_hash = None

    def test_01_start_run(self, session):
        payload = {
            "portfolio_id": PORTFOLIO_ID,
            "account_balance": 10000,
            "risk_pct": 1.0,
            "daily_loss_limit_pct": 5.0,
            "total_loss_limit_pct": 10.0,
            "tick_ms": 50,
            "bars_limit": 2000,
            "source": "bid_1m",
        }
        r = session.post(f"{API}/execution/paper/start", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") == "started"
        run = body["run"]
        assert run["status"] == "running"
        assert run["portfolio_id"] == PORTFOLIO_ID
        assert isinstance(run.get("run_id"), str) and run["run_id"].startswith("px_")
        assert len(run.get("strategies") or []) >= 1
        TestPaperLifecycle.run_id = run["run_id"]
        TestPaperLifecycle.strategy_hash = run["strategies"][0]["strategy_hash"]

    def test_02_single_active_run_enforced(self, session):
        payload = {"portfolio_id": PORTFOLIO_ID, "tick_ms": 100}
        r = session.post(f"{API}/execution/paper/start", json=payload, timeout=15)
        assert r.status_code == 409
        assert "already_active" in r.text

    def test_03_status_polling_populates_trades(self, session):
        rid = TestPaperLifecycle.run_id
        assert rid
        # Poll up to ~10s for trades to populate / halt
        trades = []
        equity_curve = []
        active_status = None
        for _ in range(25):
            r = session.get(f"{API}/execution/paper/status",
                            params={"run_id": rid}, timeout=10)
            assert r.status_code == 200, r.text
            data = r.json()
            active = data.get("active") or {}
            active_status = active.get("status")
            trades = data.get("trades") or []
            equity_curve = data.get("equity_curve") or []
            if len(trades) >= 3 or active_status in ("halted", "stopped", "errored"):
                break
            time.sleep(0.5)
        assert len(equity_curve) >= 1, "equity curve should start populating"
        # Typically trades >= some count within 10s for synthetic feed
        assert len(trades) >= 1, f"no trades populated; status={active_status}"
        # Validate trade schema on first trade
        t = trades[0]
        for k in ("expected_entry", "actual_entry", "deviation_pips",
                 "sl_price", "tp_price", "exit_price", "exit_reason",
                 "pnl", "result", "strategy_hash", "direction"):
            assert k in t, f"trade missing field: {k}"
        assert t["exit_reason"] in ("SL", "TP", "flat")
        assert t["result"] in ("WIN", "LOSS", "FLAT")
        assert t["direction"] in ("BUY", "SELL")

    def test_04_trades_endpoint(self, session):
        rid = TestPaperLifecycle.run_id
        r = session.get(f"{API}/execution/paper/trades",
                        params={"run_id": rid, "limit": 100}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "trades" in d
        assert d["count"] == len(d["trades"])
        assert d["count"] >= 1

    def test_05_equity_endpoint(self, session):
        rid = TestPaperLifecycle.run_id
        r = session.get(f"{API}/execution/paper/equity",
                        params={"run_id": rid, "limit": 500}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "equity_curve" in d
        assert d["count"] >= 1
        pt = d["equity_curve"][0]
        assert "equity" in pt and "timestamp" in pt

    def test_06_runs_endpoint(self, session):
        r = session.get(f"{API}/execution/paper/runs", params={"limit": 10}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        rids = [x["run_id"] for x in d.get("runs", [])]
        assert TestPaperLifecycle.run_id in rids

    def test_07_deviation_history_after_trades(self, session):
        # Wait longer so we cross the 5-trade snapshot threshold per strategy
        sh = TestPaperLifecycle.strategy_hash
        for _ in range(30):
            r = session.get(f"{API}/execution/paper/deviation/{sh}",
                            params={"limit": 50}, timeout=10)
            assert r.status_code == 200
            d = r.json()
            if d.get("count", 0) >= 1:
                hist = d["history"][0]
                assert hist["strategy_hash"] == sh
                assert "running_pf" in hist and "backtest_pf" in hist
                return
            time.sleep(0.5)
        # Not fatal — strategy may not have reached 5 trades before halt
        pytest.skip("No deviation snapshot created before halt (strategy <5 trades)")

    def test_08_dd_halt_or_stop(self, session):
        rid = TestPaperLifecycle.run_id
        # Poll up to 20s for either auto-halt (dd) or still running
        halted = False
        doc = None
        for _ in range(40):
            r = session.get(f"{API}/execution/paper/status",
                            params={"run_id": rid}, timeout=10)
            doc = (r.json() or {}).get("active") or {}
            if doc.get("status") in ("halted", "stopped", "errored"):
                halted = True
                break
            time.sleep(0.5)
        if halted and doc.get("status") == "halted":
            assert doc.get("halted_reason") in (
                "daily_loss_limit", "total_loss_limit")
            assert doc.get("halted_at") is not None
        else:
            # If still running, issue manual stop and verify transition
            r = session.post(f"{API}/execution/paper/stop",
                             json={"run_id": rid}, timeout=10)
            assert r.status_code == 200
            body = r.json()
            assert body.get("status") == "stopped"
            assert body["run"]["status"] in ("stopped", "halted")

    def test_09_stop_halted_returns_doc(self, session):
        # Calling stop on an already-terminal run should just return current doc
        rid = TestPaperLifecycle.run_id
        r = session.post(f"{API}/execution/paper/stop",
                         json={"run_id": rid}, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["run"]["run_id"] == rid
        assert body["run"]["status"] in ("halted", "stopped", "errored")

    def test_10_stop_nonexistent_returns_404(self, session):
        r = session.post(f"{API}/execution/paper/stop",
                         json={"run_id": "px_does_not_exist_xyz"}, timeout=10)
        assert r.status_code == 404


# ---- Validation errors ----------------------------------------
class TestValidation:
    def test_invalid_source(self, session):
        r = session.post(f"{API}/execution/paper/start",
                         json={"source": "nope"}, timeout=10)
        # Pydantic pattern mismatch -> 422
        assert r.status_code in (400, 422)

    def test_tick_ms_too_low(self, session):
        r = session.post(f"{API}/execution/paper/start",
                         json={"tick_ms": 1}, timeout=10)
        assert r.status_code in (400, 422)
