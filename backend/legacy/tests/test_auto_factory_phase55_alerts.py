"""Phase 5.5 Alert Hook System tests (backend-only).

Exercises the additive alert endpoints piggybacked onto
/api/auto-factory/saved via POST ops: update_config, test_alert, alerts_log.
Also validates regression for existing Phase 5 endpoints.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
           "https://strategy-prod-main.preview.emergentagent.com"

SAVED = f"{BASE_URL}/api/auto-factory/saved"
RUN = f"{BASE_URL}/api/auto-factory/run"
STATUS = f"{BASE_URL}/api/auto-factory/status"

TEST_WEBHOOK = "https://httpbin.org/post"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def _cleanup(client):
    """Reset alert config to defaults after all tests in this module."""
    yield
    try:
        client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {
                "alerts_enabled": False,
                "webhook_url": "",
                "telegram_enabled": False,
                "telegram_bot_token": "",
                "telegram_chat_id": "",
            },
        }, timeout=15)
    except Exception:
        pass


# ── Config GET returns alert defaults ───────────────────────────────────
class TestAlertConfigDefaults:
    def test_config_contains_alert_keys(self, client):
        # Start with defaults disabled + empty webhook
        client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {"alerts_enabled": False, "webhook_url": "",
                      "telegram_enabled": False, "telegram_bot_token": "",
                      "telegram_chat_id": ""},
        }, timeout=15)
        r = client.get(f"{SAVED}?phase=5.5&view=config", timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json().get("config") or {}
        for k in ["alerts_enabled", "webhook_url", "telegram_enabled",
                  "telegram_bot_token", "telegram_chat_id",
                  "alert_min_pass_probability", "alert_min_env_confidence"]:
            assert k in cfg, f"missing alert key: {k}"
        assert cfg["alerts_enabled"] is False
        assert cfg["webhook_url"] == ""
        assert cfg["telegram_enabled"] is False
        assert cfg["telegram_bot_token"] == ""
        assert cfg["telegram_chat_id"] == ""
        assert float(cfg["alert_min_pass_probability"]) == 0.6
        assert float(cfg["alert_min_env_confidence"]) == 0.6


# ── update_config persistence ────────────────────────────────────────────
class TestUpdateConfig:
    def test_update_alert_config(self, client):
        r = client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {"alerts_enabled": True, "webhook_url": TEST_WEBHOOK},
        }, timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json().get("config") or {}
        assert cfg["alerts_enabled"] is True
        assert cfg["webhook_url"] == TEST_WEBHOOK

        # GET to verify persistence
        g = client.get(f"{SAVED}?phase=5.5&view=config", timeout=15)
        assert g.status_code == 200
        gcfg = g.json().get("config") or {}
        assert gcfg["alerts_enabled"] is True
        assert gcfg["webhook_url"] == TEST_WEBHOOK


# ── test_alert dispatch paths ────────────────────────────────────────────
class TestTestAlert:
    def test_test_alert_success_webhook(self, client):
        # Ensure enabled + webhook present
        client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {"alerts_enabled": True, "webhook_url": TEST_WEBHOOK,
                      "telegram_enabled": False},
        }, timeout=15)
        r = client.post(SAVED, json={"phase": "5.5", "op": "test_alert"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("op") == "test_alert"
        res = body.get("result") or {}
        assert res.get("sent") is True, f"expected sent=True, got {res}"
        channels = res.get("channels") or []
        assert len(channels) >= 1
        wh = next((c for c in channels if c.get("channel") == "webhook"), None)
        assert wh is not None, "webhook channel missing"
        assert wh.get("ok") is True
        assert wh.get("status_code") == 200
        # Payload contents for sample data
        payload = res.get("payload") or {}
        assert payload.get("pair") == "GBPUSD"
        assert float(payload.get("pf")) == pytest.approx(1.52, rel=1e-3)

    def test_test_alert_disabled(self, client):
        client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {"alerts_enabled": False},
        }, timeout=15)
        r = client.post(SAVED, json={"phase": "5.5", "op": "test_alert"}, timeout=20)
        assert r.status_code == 200, r.text
        res = r.json().get("result") or {}
        assert res.get("sent") is False
        assert res.get("reason") == "alerts_disabled"

    def test_test_alert_no_channels(self, client):
        # enabled but no webhook and telegram disabled
        client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {"alerts_enabled": True, "webhook_url": "",
                      "telegram_enabled": False,
                      "telegram_bot_token": "", "telegram_chat_id": ""},
        }, timeout=15)
        r = client.post(SAVED, json={"phase": "5.5", "op": "test_alert"}, timeout=20)
        assert r.status_code == 200, r.text
        res = r.json().get("result") or {}
        assert res.get("sent") is False
        assert res.get("reason") == "no_channels_configured"


# ── alerts_log schema & content ──────────────────────────────────────────
class TestAlertsLog:
    def test_alerts_log_after_successful_send(self, client):
        # Re-enable + webhook, send one, then read log
        client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {"alerts_enabled": True, "webhook_url": TEST_WEBHOOK,
                      "telegram_enabled": False},
        }, timeout=15)
        send = client.post(SAVED, json={"phase": "5.5", "op": "test_alert"}, timeout=30)
        assert send.status_code == 200
        assert (send.json().get("result") or {}).get("sent") is True

        r = client.post(SAVED, json={"phase": "5.5", "op": "alerts_log", "limit": 10},
                        timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("phase") == "5.5"
        assert body.get("op") == "alerts_log"
        assert int(body.get("count") or 0) >= 1
        alerts = body.get("alerts") or []
        assert len(alerts) >= 1
        top = alerts[0]
        # Schema
        for k in ["strategy_hash", "sent_at", "payload", "channels"]:
            assert k in top, f"alert log missing key {k}: {top}"
        # run_id allowed to be None for test_alert
        assert "run_id" in top
        payload = top.get("payload") or {}
        for pk in ["strategy", "pair", "timeframe", "pf", "dd",
                   "pass_probability", "safe_risk", "environment", "firm"]:
            assert pk in payload, f"payload missing {pk}"
        assert payload.get("pair") == "GBPUSD"
        assert float(payload.get("pf")) == pytest.approx(1.52, rel=1e-3)


# ── Unknown op returns 400 ───────────────────────────────────────────────
class TestUnknownOp:
    def test_unknown_op(self, client):
        r = client.post(SAVED, json={"phase": "5.5", "op": "nope"}, timeout=15)
        assert r.status_code == 400
        # detail includes 'unknown op'
        detail = (r.json() or {}).get("detail", "")
        assert "unknown op" in detail.lower()


# ── Regression: Phase 5.5 run cycle exposes last_run.alerts ─────────────
class TestRunCycleAlertsField:
    def test_run_cycle_no_steps_has_alerts(self, client):
        # Ensure alerts disabled so we don't send anything during run
        client.post(SAVED, json={
            "phase": "5.5", "op": "update_config",
            "patch": {"alerts_enabled": False, "webhook_url": ""},
        }, timeout=15)

        r = client.post(RUN, json={
            "phase": "5.5", "wait": False,
            "run_data_maintenance": False, "run_ingestion": False,
            "run_mutation": False, "run_validation": False,
            "run_selection": False,
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("accepted") is True

        # Poll status for last_run
        last_run = None
        for _ in range(30):
            time.sleep(1)
            st = client.get(f"{STATUS}?phase=5.5", timeout=15)
            assert st.status_code == 200
            body = st.json()
            if not body.get("running") and body.get("last_run"):
                last_run = body["last_run"]
                break
        assert last_run is not None, "no last_run after cycle"
        assert "alerts" in last_run, f"last_run missing alerts: keys={list(last_run.keys())}"
        alerts = last_run["alerts"]
        # With alerts disabled, either skipped='alerts_disabled' or alerts_sent=0
        assert alerts.get("skipped") == "alerts_disabled" or int(alerts.get("alerts_sent") or 0) == 0


# ── Regression: Existing Phase 5 endpoints unchanged ────────────────────
class TestPhase5Regression:
    def test_status_no_phase_param(self, client):
        r = client.get(STATUS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Phase 5 shape: no phase='5.5' field
        assert body.get("phase") != "5.5"

    def test_saved_no_phase_param(self, client):
        r = client.get(SAVED, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "count" in body and "strategies" in body
        assert "phase" not in body  # Phase 5 default shape
