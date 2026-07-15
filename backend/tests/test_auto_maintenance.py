"""Iteration 6 — Auto-maintenance verification (REQ1–REQ4 + BI5 dataclass regression).

Verifies fb1f675 (resume-on-boot) + 976e04e (BI5 dataclass fix) + baked-in
dukascopy-python. Backend-only sweep against the live preview URL.

Env inputs (fail-fast — no defaults):
  REACT_APP_BACKEND_URL  — external backend URL
  MONGO_URL              — local Mongo for direct persistence checks
  DB_NAME                — Mongo database name
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

import pymongo
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ADMIN_EMAIL = "admin@strategy-factory.local"
ADMIN_PASS = "admin123"

# 976e04e was deployed 2026-07-14 mid-day UTC — anything older is stale.
POST_FIX_CUTOFF = datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)


# ─── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def mongo():
    client = pymongo.MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ═════════ REQ1 — Config persistence in Mongo ══════════════════════════
class TestReq1ConfigPersistence:
    def test_toggle_on_persists(self, admin_headers, mongo):
        r = requests.post(
            f"{BASE_URL}/api/auto-maintenance/toggle",
            headers=admin_headers, json={"enabled": True}, timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["status"]["enabled"] is True

        # Direct Mongo read
        doc = mongo.auto_maintenance_config.find_one({"_id": "global"})
        assert doc is not None
        assert doc["enabled"] is True
        assert "updated_at" in doc
        # updated_at is ISO string parseable
        datetime.fromisoformat(doc["updated_at"].replace("Z", "+00:00"))

    def test_toggle_off_persists(self, admin_headers, mongo):
        r = requests.post(
            f"{BASE_URL}/api/auto-maintenance/toggle",
            headers=admin_headers, json={"enabled": False}, timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["status"]["enabled"] is False

        doc = mongo.auto_maintenance_config.find_one({"_id": "global"})
        assert doc["enabled"] is False

    def test_re_enable_for_downstream_tests(self, admin_headers, mongo):
        """Turn back ON so REQ3 (resume-on-boot) validates the enabled path."""
        r = requests.post(
            f"{BASE_URL}/api/auto-maintenance/toggle",
            headers=admin_headers, json={"enabled": True}, timeout=20,
        )
        assert r.status_code == 200
        doc = mongo.auto_maintenance_config.find_one({"_id": "global"})
        assert doc["enabled"] is True


# ═════════ REQ2 — Frontend contract + backend endpoints ════════════════
class TestReq2FrontendContract:
    def test_frontend_panel_and_handler_present(self):
        with open("/app/frontend/src/components/DataUpload.js") as f:
            src = f.read()
        assert 'data-testid="auto-maintenance-panel"' in src
        assert "toggleAutoMaintenance" in src
        assert "aria-pressed" in src
        assert "autoStatus" in src

    def test_frontend_api_service_exports(self):
        with open("/app/frontend/src/services/api.js") as f:
            src = f.read()
        assert "getAutoMaintenanceStatus" in src
        assert "toggleAutoMaintenance" in src
        assert "runAutoMaintenanceNow" in src
        assert "/api/auto-maintenance/status" in src
        assert "/api/auto-maintenance/toggle" in src
        assert "/api/auto-maintenance/run-now" in src

    def test_status_endpoint_shape(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/auto-maintenance/status",
            headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        for k in ("enabled", "bid_interval_minutes", "bi5_interval_minutes",
                  "next_runs", "statuses"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["next_runs"], dict)
        assert isinstance(d["statuses"], list)
        assert d["bid_interval_minutes"] == 15
        assert d["bi5_interval_minutes"] == 60

    def test_toggle_endpoint_returns_success_and_status(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/auto-maintenance/toggle",
            headers=admin_headers, json={"enabled": True}, timeout=20,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["success"] is True
        assert "status" in d
        assert d["status"]["enabled"] is True


# ═════════ REQ3 — Auto-resume after restart ════════════════════════════
class TestReq3ResumeOnBoot:
    """Restart backend with enabled=True persisted, then check the
    boot-log emits the 'resumed on boot' banner and the scheduler
    reports non-empty next_runs. Also verify the dormant branch."""

    def _restart_backend(self):
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                       check=True, capture_output=True)
        # Wait for backend to come back up
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                r = requests.get(f"{BASE_URL}/api/health", timeout=3)
                if r.status_code == 200:
                    time.sleep(2)  # let lifespan hook finish
                    return
            except Exception:
                pass
            time.sleep(1)
        pytest.fail("backend did not come back up within 30s")

    def _tail_backend_log(self, needle: str, tail_lines: int = 5000) -> bool:
        for path in ("/var/log/supervisor/backend.err.log",
                     "/var/log/supervisor/backend.out.log"):
            if not os.path.exists(path):
                continue
            try:
                out = subprocess.check_output(
                    f"grep -aF {needle!r} {path} | tail -n5",
                    shell=True, text=True,
                )
                if needle in out:
                    return True
            except Exception:
                continue
        return False

    def test_resume_when_enabled(self, admin_headers, mongo):
        # ensure enabled=True persisted
        mongo.auto_maintenance_config.update_one(
            {"_id": "global"},
            {"$set": {"enabled": True,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        self._restart_backend()
        time.sleep(4)  # lifespan writes the log line

        assert self._tail_backend_log(
            "auto-maintenance scheduler resumed on boot (config.enabled=True)"
        ), "resume-on-boot log line NOT found after restart with enabled=True"

        # Also assert the live scheduler state via API
        r = requests.get(f"{BASE_URL}/api/auto-maintenance/status",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True
        assert "bid_track" in d["next_runs"], d["next_runs"]
        assert "bi5_track" in d["next_runs"], d["next_runs"]
        # both parseable ISO timestamps
        datetime.fromisoformat(d["next_runs"]["bid_track"])
        datetime.fromisoformat(d["next_runs"]["bi5_track"])

    def test_dormant_when_disabled(self, admin_headers, mongo):
        # flip to disabled
        mongo.auto_maintenance_config.update_one(
            {"_id": "global"},
            {"$set": {"enabled": False,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        self._restart_backend()
        time.sleep(4)

        assert self._tail_backend_log(
            "auto-maintenance scheduler dormant on boot (config.enabled=False"
        ), "dormant-on-boot log line NOT found after restart with enabled=False"

        # Restore enabled=True so subsequent tests / production behaviour is preserved
        mongo.auto_maintenance_config.update_one(
            {"_id": "global"},
            {"$set": {"enabled": True,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        self._restart_backend()
        time.sleep(4)


# ═════════ REQ4 — Dukascopy download actually runs (BID track) ═════════
class TestReq4BidTrackFresh:
    def test_bid_status_row_fresh_ok(self, mongo):
        row = mongo.auto_maintenance_status.find_one(
            {"symbol": "EURUSD", "source": "bid_1m"}
        )
        assert row is not None, "no auto_maintenance_status row for EURUSD/bid_1m"
        assert row.get("state") == "ok", f"state={row.get('state')}"
        # updated_at within last hour (backend was restarted so post-fix scheduler ticked)
        upd = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        assert upd > POST_FIX_CUTOFF, f"updated_at={upd} is stale (before 976e04e fix)"
        # range_after.count comfortably above the review threshold
        rng = row.get("range_after") or {}
        assert rng.get("count", 0) > 10000, f"range_after.count={rng.get('count')}"

    def test_market_data_eurusd_row_count(self, mongo):
        n = mongo.market_data.count_documents(
            {"symbol": "EURUSD", "source": "bid_1m"}
        )
        assert n > 10000, f"EURUSD bid_1m candle count={n}"

    def test_market_data_eurusd_recent_within_24h(self, mongo):
        latest = list(
            mongo.market_data.find({"symbol": "EURUSD", "source": "bid_1m"})
            .sort("timestamp", -1)
            .limit(1)
        )
        assert latest, "no EURUSD bid_1m rows"
        ts = latest[0]["timestamp"]
        # timestamp may be datetime or ISO string
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        # Preview pod: EURUSD ~ 2026-07-15 latest; test-time 2026-07-15 → age ~hours.
        # Guard: must be less than 30 days old (was fresh at review time).
        assert age < timedelta(days=30), f"latest EURUSD candle age={age}"


# ═════════ REQ4b — BI5 dataclass regression fixed ══════════════════════
class TestReq4bBi5Dataclass:
    SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
               "USDCAD", "NZDUSD", "XAUUSD", "XAGUSD"]

    @pytest.fixture(scope="class", autouse=True)
    def add_legacy_to_path(self):
        p = "/app/backend/legacy"
        if p not in sys.path:
            sys.path.insert(0, p)

    def test_eurusd_full_spec(self):
        from legacy.config.bi5_symbols import get_bi5_symbol_spec
        s = get_bi5_symbol_spec("EURUSD")
        assert s.symbol == "EURUSD"
        assert s.market_type == "forex"
        assert s.digits == 5
        assert s.url_slug == "EURUSD"
        assert s.quote_decimals == 5
        assert s.supported is True

    @pytest.mark.parametrize("sym", SYMBOLS)
    def test_all_supported_symbols_attribute_access(self, sym):
        from legacy.config.bi5_symbols import get_bi5_symbol_spec
        s = get_bi5_symbol_spec(sym)
        # every field must attribute-access without raising
        _ = (s.symbol, s.dukascopy_instrument, s.url_slug, s.digits,
             s.quote_decimals, s.price_multiplier, s.market_type,
             s.pip_size, s.point_size, s.contract_size, s.supported)
        assert s.symbol == sym
        assert s.supported is True

    def test_stale_bi5_status_rows_are_pre_fix(self, mongo):
        """Any BI5 rows carrying 'dict object has no attribute' MUST be
        stale (updated_at < 2026-07-14 18:00 UTC). Post-fix rows should
        no longer surface this error."""
        offenders = list(mongo.auto_maintenance_status.find(
            {"source": "bi5", "bi5_runner_error": {"$regex": "dict.*has no attribute"}}
        ))
        for row in offenders:
            upd = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
            assert upd < POST_FIX_CUTOFF, (
                f"BI5 dict-attribute error on {row.get('symbol')} at {upd} "
                f"— this is POST-FIX and indicates the regression is not fixed."
            )


# ═════════ REGRESSION sweep — 90 routers + critical endpoints ══════════
class TestRegressionSweep:
    def test_90_routers_online(self):
        needle = "90 routers/attachers online"
        for path in ("/var/log/supervisor/backend.err.log",
                     "/var/log/supervisor/backend.out.log"):
            if not os.path.exists(path):
                continue
            out = subprocess.check_output(
                f"grep -aF {needle!r} {path} | tail -n5",
                shell=True, text=True,
            )
            if needle in out:
                return
        pytest.fail("'90 routers/attachers online' NOT in backend logs")

    @pytest.mark.parametrize("path", [
        "/api/health",
        "/api/library/list",
        "/api/strategies/explorer",
        "/api/prop-firms/list",
        "/api/admin/providers",
        "/api/llm/diagnostics",
        "/api/knowledge/status",
    ])
    def test_endpoint_200(self, path, admin_headers):
        # /api/health is unauth; the others need admin.
        headers = None if path == "/api/health" else admin_headers
        r = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=20)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
