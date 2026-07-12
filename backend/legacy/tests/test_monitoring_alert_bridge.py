"""
Phase 6 × 5.5 — Monitoring → Alerts Bridge backend tests.

Covers bridge wiring from /api/monitoring/run via monitoring_alert_bridge
and the new POST /api/auto-factory/saved op='monitoring_alerts_log'.

Reads BASE_URL from frontend env (public preview URL). MongoDB is the
local test_database (same DB backend uses). All seeds prefixed with
TEST_ and cleaned up between tests.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

# ─── BASE URL from frontend .env (public ingress) ───────────────────────
def _frontend_base_url() -> str:
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")

BASE_URL = _frontend_base_url()
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.environ.get("DB_NAME",   "test_database")

WEBHOOK_OK   = "https://httpbin.org/post"
WEBHOOK_BAD  = "http://127.0.0.1:0"

CFG_COLL     = "auto_factory_config"
CFG_ID       = "phase55_default"
RUNS_COLL    = "trade_runner_runs"
TRADES_COLL  = "trade_runner_trades"
BRIDGE_LOG   = "monitoring_alert_log"
AF_LOG       = "auto_factory_alert_log"
MON_STATE    = "monitoring_state"
STRAT_STATUS = "strategy_status"


# ────────────────────────── helpers ─────────────────────────────────────
@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _patch_cfg(api, patch: dict) -> dict:
    r = api.post(f"{API}/auto-factory/saved",
                 json={"phase": "5.5", "op": "update_config", "patch": patch},
                 timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["config"]


def _seed_run(db, *, strategy_id: str, equity: float, peak_equity: float,
              daily_start_equity: float | None = None,
              daily_loss_pct: float = 0.0, starting: float = 100000.0) -> str:
    run_id = f"TEST_run_{uuid.uuid4().hex[:8]}"
    db[RUNS_COLL].insert_one({
        "run_id": run_id,
        "strategy_id": strategy_id,
        "status": "running",
        "started_at": "2026-01-10T00:00:00+00:00",
        "pair": "EURUSD",
        "timeframe": "M15",
        "account_balance_start": starting,
        "equity": equity,
        "peak_equity": peak_equity,
        "daily_start_equity": daily_start_equity if daily_start_equity is not None else equity,
        "daily_loss_pct": daily_loss_pct,
    })
    return run_id


def _seed_trades(db, run_id: str, pnls: list[float]):
    docs = []
    for i, p in enumerate(pnls):
        docs.append({
            "run_id": run_id,
            "trade_id": f"TEST_tr_{run_id}_{i}",
            "pnl": p,
            "closed_at": f"2026-01-10T{i:02d}:00:00+00:00",
        })
    if docs:
        db[TRADES_COLL].insert_many(docs)


def _purge(db):
    db[RUNS_COLL].delete_many({"run_id": {"$regex": "^TEST_run_"}})
    db[TRADES_COLL].delete_many({"trade_id": {"$regex": "^TEST_tr_"}})
    db[BRIDGE_LOG].delete_many({})
    db[STRAT_STATUS].delete_many({"strategy_id": {"$regex": "^TEST_"}})


def _reset_state(api):
    api.post(f"{API}/monitoring/reset", timeout=15)


def _run_mon(api) -> dict:
    r = api.post(f"{API}/monitoring/run", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


# ────────────────────────── fixtures ────────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def _teardown(api, db):
    # Starting state: ensure clean
    _purge(db)
    _reset_state(api)
    yield
    # Final cleanup
    try:
        api.post(f"{API}/monitoring/scheduler", json={"enabled": False, "interval_seconds": 60}, timeout=15)
    except Exception:
        pass
    _purge(db)
    _reset_state(api)
    # Reset alerts off
    try:
        _patch_cfg(api, {"alerts_enabled": False, "webhook_url": "",
                         "monitoring_alerts_enabled": True,
                         "alert_on_daily_dd": True, "alert_on_total_dd": True,
                         "alert_on_underperformance": True, "alert_on_loss_streak": True})
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _per_test(api, db):
    # Each test starts with a clean slate for runs/trades/bridge log
    _purge(db)
    _reset_state(api)
    yield
    _purge(db)
    _reset_state(api)


# ────────────────────────── tests ───────────────────────────────────────
class TestConfigDefaults:
    """GET ?phase=5.5&view=config exposes new bridge keys"""

    def test_defaults_exposed(self, api):
        r = api.get(f"{API}/auto-factory/saved?phase=5.5&view=config", timeout=20)
        assert r.status_code == 200
        cfg = r.json()["config"]
        for k in ("monitoring_alerts_enabled", "alert_on_daily_dd",
                  "alert_on_total_dd", "alert_on_underperformance",
                  "alert_on_loss_streak"):
            assert k in cfg, f"missing cfg key {k}"
            assert cfg[k] is True, f"{k} default should be True"


class TestTotalDDBridge:
    """Happy path + dedup for TOTAL_DD_BREACH"""

    def test_total_dd_emits_once_then_dedups(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True,
                         "alert_on_total_dd": True, "alert_on_daily_dd": True,
                         "alert_on_underperformance": True, "alert_on_loss_streak": True,
                         "telegram_enabled": False})

        _seed_run(db, strategy_id="TEST_portfolio_strat",
                  equity=89000, peak_equity=100000)

        # 1st tick — should emit
        snap = _run_mon(api)
        alerts = snap.get("alerts") or {}
        results = alerts.get("results") or []
        assert alerts.get("emitted", 0) >= 1, f"expected >=1 emitted, got {alerts}"
        total = [r for r in results if r.get("event_type") == "TOTAL_DD_BREACH"]
        assert total, f"no TOTAL_DD_BREACH in results: {results}"
        r0 = total[0]
        assert r0.get("sent") is True, f"sent!=True: {r0}"
        chans = r0.get("channels") or []
        wh = [c for c in chans if c.get("channel") == "webhook"]
        assert wh and wh[0].get("ok") is True, f"webhook channel not ok: {chans}"
        assert wh[0].get("status_code") == 200

        # Dedup: after hard breach monitoring stopped the run — re-seed & reset state
        _reset_state(api)
        db[RUNS_COLL].delete_many({"run_id": {"$regex": "^TEST_run_"}})
        _seed_run(db, strategy_id="TEST_portfolio_strat",
                  equity=89000, peak_equity=100000)

        snap2 = _run_mon(api)
        alerts2 = snap2.get("alerts") or {}
        results2 = alerts2.get("results") or []
        total2 = [r for r in results2 if r.get("event_type") == "TOTAL_DD_BREACH"]
        # Could be zero results if no new breach recomputed (state sticks STOPPED);
        # monitoring still emits from snapshot.breaches collected this tick.
        if total2:
            assert total2[0].get("sent") is False
            assert total2[0].get("reason") == "duplicate"
        else:
            # Acceptable alternative: breach suppressed at engine level — log should still have 1 entry
            pass

        # bridge log should contain exactly one entry for this event
        log = list(db[BRIDGE_LOG].find({"event_type": "TOTAL_DD_BREACH"}))
        assert len(log) == 1, f"expected 1 log entry, found {len(log)}"


class TestDailyDDBridge:
    def test_daily_dd_emits(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True,
                         "alert_on_daily_dd": True, "alert_on_total_dd": True})

        _seed_run(db, strategy_id="TEST_daily_strat",
                  equity=92000, peak_equity=92000,
                  daily_start_equity=100000, daily_loss_pct=8.0)

        snap = _run_mon(api)
        alerts = snap.get("alerts") or {}
        results = alerts.get("results") or []
        daily = [r for r in results if r.get("event_type") == "DAILY_DD_BREACH"]
        assert daily, f"no DAILY_DD_BREACH in {results}"
        assert daily[0].get("sent") is True


class TestUnderperformanceBridge:
    def test_underperformance_emits(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True,
                         "alert_on_underperformance": True})

        run_id = _seed_run(db, strategy_id="TEST_under_strat",
                           equity=98000, peak_equity=100000)
        # 20 trades where losses dominate: PF < 1.0, and NO trailing-loss streak (end with a win)
        pnls = [-50.0] * 13 + [10.0] * 7
        _seed_trades(db, run_id, pnls)

        snap = _run_mon(api)
        alerts = snap.get("alerts") or {}
        results = alerts.get("results") or []
        under = [r for r in results if r.get("event_type") == "UNDERPERFORMANCE"]
        assert under, f"no UNDERPERFORMANCE in {results}"
        assert under[0].get("sent") is True
        assert under[0].get("subject_id") == "TEST_under_strat"


class TestLossStreakBridge:
    def test_loss_streak_emits(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True,
                         "alert_on_loss_streak": True})

        run_id = _seed_run(db, strategy_id="TEST_streak_strat",
                           equity=95000, peak_equity=100000)
        # 5 consecutive losing trades
        _seed_trades(db, run_id, [-100.0, -100.0, -100.0, -100.0, -100.0])

        snap = _run_mon(api)
        alerts = snap.get("alerts") or {}
        results = alerts.get("results") or []
        ls = [r for r in results if r.get("event_type") == "LOSS_STREAK"]
        assert ls, f"no LOSS_STREAK in {results}"
        assert ls[0].get("sent") is True
        assert ls[0].get("subject_id") == "TEST_streak_strat"


class TestPerEventToggle:
    def test_total_dd_disabled_per_event(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True,
                         "alert_on_total_dd": False,
                         "alert_on_daily_dd": True,
                         "alert_on_underperformance": True,
                         "alert_on_loss_streak": True})

        _seed_run(db, strategy_id="TEST_tog_strat",
                  equity=89000, peak_equity=100000)

        snap = _run_mon(api)
        alerts = snap.get("alerts") or {}
        results = alerts.get("results") or []
        total = [r for r in results if r.get("event_type") == "TOTAL_DD_BREACH"]
        assert total, f"expected TOTAL_DD_BREACH result entry, got {results}"
        assert total[0].get("sent") is False
        assert total[0].get("reason") == "event_type_disabled"
        # restore
        _patch_cfg(api, {"alert_on_total_dd": True})


class TestGlobalToggle:
    def test_bridge_disabled_globally(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": False})

        _seed_run(db, strategy_id="TEST_glob_strat",
                  equity=89000, peak_equity=100000)

        snap = _run_mon(api)
        alerts = snap.get("alerts") or {}
        assert alerts.get("emitted", 0) == 0, alerts
        assert alerts.get("skipped_reason") == "bridge_disabled", alerts
        # restore
        _patch_cfg(api, {"monitoring_alerts_enabled": True})

    def test_master_alerts_disabled(self, api, db):
        _patch_cfg(api, {"alerts_enabled": False, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True})

        _seed_run(db, strategy_id="TEST_master_strat",
                  equity=89000, peak_equity=100000)

        snap = _run_mon(api)
        alerts = snap.get("alerts") or {}
        assert alerts.get("emitted", 0) == 0
        assert alerts.get("skipped_reason") == "bridge_disabled"
        # restore
        _patch_cfg(api, {"alerts_enabled": True})


class TestMonitoringAlertsLogOp:
    def test_monitoring_alerts_log_returns_bridge_entries(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True,
                         "alert_on_total_dd": True})

        _seed_run(db, strategy_id="TEST_log_strat",
                  equity=89000, peak_equity=100000)
        snap = _run_mon(api)
        assert (snap.get("alerts") or {}).get("emitted", 0) >= 1

        r = api.post(f"{API}/auto-factory/saved",
                     json={"phase": "5.5", "op": "monitoring_alerts_log", "limit": 10},
                     timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["phase"] == "5.5"
        assert body["op"] == "monitoring_alerts_log"
        assert body["count"] >= 1
        entry = body["alerts"][0]
        for k in ("event_type", "subject_id", "date", "sent_at", "payload", "result"):
            assert k in entry, f"missing {k} in {entry}"

    def test_alerts_log_regression(self, api):
        """Phase 5.5 original alerts_log (auto_factory_alert_log) still works."""
        r = api.post(f"{API}/auto-factory/saved",
                     json={"phase": "5.5", "op": "alerts_log", "limit": 5},
                     timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["op"] == "alerts_log"
        assert "alerts" in body and isinstance(body["alerts"], list)

    def test_unknown_op_400(self, api):
        r = api.post(f"{API}/auto-factory/saved",
                     json={"phase": "5.5", "op": "nonexistent_op"},
                     timeout=15)
        assert r.status_code == 400


class TestAutoFactoryRunRegression:
    def test_phase55_run_all_steps_off_still_completes(self, api):
        r = api.post(f"{API}/auto-factory/run",
                     json={"phase": "5.5", "wait": False,
                           "run_data_maintenance": False,
                           "run_ingestion": False, "run_mutation": False,
                           "run_validation": False, "run_selection": False},
                     timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("phase") == "5.5"
        assert body.get("accepted") is True
        # give it a sec to flip lock back
        time.sleep(3)


class TestDedupReset:
    def test_dedup_resets_on_date_key(self, api, db):
        """Insert a stale bridge-log entry for the same subject on 1999-01-01 and
        verify today's emit still fires (dedup keyed by UTC date)."""
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_OK,
                         "monitoring_alerts_enabled": True,
                         "alert_on_total_dd": True})

        db[BRIDGE_LOG].insert_one({
            "event_type": "TOTAL_DD_BREACH",
            "subject_id": "portfolio",
            "date": "1999-01-01",
            "sent_at": "1999-01-01T00:00:00+00:00",
            "payload": {}, "result": {},
        })
        _seed_run(db, strategy_id="TEST_reset_strat",
                  equity=89000, peak_equity=100000)

        snap = _run_mon(api)
        results = (snap.get("alerts") or {}).get("results") or []
        total = [r for r in results if r.get("event_type") == "TOTAL_DD_BREACH"]
        assert total and total[0].get("sent") is True, \
            f"dedup must not block stale-date entry: {results}"


class TestBridgeFailSafe:
    def test_bad_webhook_does_not_break_monitoring(self, api, db):
        _patch_cfg(api, {"alerts_enabled": True, "webhook_url": WEBHOOK_BAD,
                         "monitoring_alerts_enabled": True,
                         "alert_on_total_dd": True})

        _seed_run(db, strategy_id="TEST_fail_strat",
                  equity=89000, peak_equity=100000)

        # /run must still succeed — bridge swallows errors
        r = api.post(f"{API}/monitoring/run", timeout=60)
        assert r.status_code == 200, r.text
        snap = r.json()
        assert "state" in snap
        # alerts key present; either emitted/skipped — must not raise
        assert "alerts" in snap
