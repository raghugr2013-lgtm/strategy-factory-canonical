"""
Iteration 3 regression tests for commit fb1f675.
Covers the five backend fixes shipped this pass:
  1) Dukascopy pinned to requirements.txt (import works)
  2) legacy.data_engine.dukascopy_downloader — _DUKASCOPY_AVAILABLE + INTERVAL_MAP
  3) Auto-maintenance resume-on-boot (toggle + supervisor restart)
  4) /api/admin/providers graceful fallback when VIE is down (no 503)
  5) /api/llm/diagnostics — additive keys (primary_provider, vie_reachable, providers dict)
  6) BI5 symbol spec dataclass (get_bi5_symbol_spec returns dataclass, not dict)
  7) Regression: 89 routers online, strategy-recovery surfaces route
  8) Docs: /app/docs/AI_LEARNING_LAYER.md and /app/docs/PRODUCTION_AUDIT_2026-02.md
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

BACKEND = "http://localhost:8001"
ADMIN_EMAIL = "admin@strategy-factory.local"
ADMIN_PASS = "admin123"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BACKEND}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- Fix 1: dukascopy_python installable & importable ----------
class TestDukascopyImport:
    def test_requirements_pins_dukascopy(self):
        text = Path("/app/backend/requirements.txt").read_text()
        assert "dukascopy-python==4.0.1" in text

    def test_dukascopy_python_import(self):
        import dukascopy_python  # noqa: F401
        from dukascopy_python.instruments import INSTRUMENT_FX_MAJORS_EUR_USD
        assert INSTRUMENT_FX_MAJORS_EUR_USD == "EUR/USD"

    def test_legacy_downloader_wired(self):
        # backend cwd must be on path (main.py does this at boot)
        sys.path.insert(0, "/app/backend")
        from legacy.data_engine.dukascopy_downloader import (
            _DUKASCOPY_AVAILABLE, INTERVAL_MAP,
        )
        assert _DUKASCOPY_AVAILABLE is True
        assert len(INTERVAL_MAP) == 7
        assert set(INTERVAL_MAP.keys()) == {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}


# ---------- Fixes 3-5 + HTTP regressions grouped in ONE class so `--dist loadscope`
# pins them to a single xdist worker; the supervisor restarts inside this class
# would otherwise race with HTTP tests scheduled on the other worker. ----------
class TestBackendHTTPFixes:
    def _grep(self, needle: str) -> str:
        r = subprocess.run(
            ["grep", needle, "/var/log/supervisor/backend.err.log"],
            capture_output=True, text=True,
        )
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        return lines[-1] if lines else ""

    def _wait_for_backend(self, timeout: int = 30):
        for _ in range(timeout):
            try:
                if requests.get(f"{BACKEND}/api/health", timeout=2).status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def test_toggle_on_and_persist(self, admin_headers):
        r = requests.post(f"{BACKEND}/api/data/maintenance/toggle",
                          json={"enabled": True}, headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is True
        assert body["scheduler"]["enabled"] is True

        subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                       capture_output=True, timeout=30)
        assert self._wait_for_backend(), "backend did not come back up"
        time.sleep(3)  # let lifespan hook flush its INFO line
        line = self._grep("auto-maintenance scheduler resumed on boot")
        assert "config.enabled=True" in line, f"resume line missing: {line!r}"

    def test_toggle_off_and_persist(self, admin_headers):
        # need fresh token because backend was restarted
        r = requests.post(f"{BACKEND}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        r = requests.post(f"{BACKEND}/api/data/maintenance/toggle",
                          json={"enabled": False}, headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["enabled"] is False

        subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                       capture_output=True, timeout=30)
        assert self._wait_for_backend()
        time.sleep(3)
        line = self._grep("auto-maintenance scheduler dormant on boot")
        assert "config.enabled=False" in line, f"dormant line missing: {line!r}"


    # ---------- Fix 4: /api/admin/providers graceful fallback ----------
    def test_admin_providers_200(self, admin_headers):
        # fresh login (in case previous class restarted backend)
        r = requests.post(f"{BACKEND}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = requests.get(f"{BACKEND}/api/admin/providers", headers=headers, timeout=15)
        assert r.status_code == 200, f"expected 200 (not 503), got {r.status_code}: {r.text}"
        d = r.json()

        # providers list of 6, one per LLM provider
        provs = d["providers"]
        assert isinstance(provs, list) and len(provs) == 6
        names = {p["name"] for p in provs}
        assert names == {"openai", "anthropic", "gemini", "deepseek", "groq", "kimi"}
        for p in provs:
            for k in ("name", "available", "model", "key_env", "key_present"):
                assert k in p, f"provider {p} missing key {k}"

        # VIE not running in pod → fallback path must be exercised
        assert d["source"] in ("vie", "fallback")
        if d["source"] == "fallback":
            assert d["vie_status"] == "unavailable"
            assert "vie_error" in d
            assert "hint" in d


    # ---------- Fix 5: /api/llm/diagnostics additive keys ----------
    def test_diagnostics_additive(self, admin_headers):
        r = requests.post(f"{BACKEND}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = requests.get(f"{BACKEND}/api/llm/diagnostics", headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()

        # ADDITIVE keys
        assert "primary_provider" in d
        assert d["primary_provider"] is None or isinstance(d["primary_provider"], str)
        assert "vie_reachable" in d and isinstance(d["vie_reachable"], bool)
        assert "providers" in d and isinstance(d["providers"], dict)
        for pname, pdata in d["providers"].items():
            for k in ("configured", "model", "vie_available", "key_env", "key_present"):
                assert k in pdata, f"provider {pname} missing key {k}"

        # PRESERVED keys
        for k in ("flag_enabled", "vie_url", "providers_total",
                  "providers_available", "available", "task_preference"):
            assert k in d, f"preserved key missing: {k}"


    # ---------- Regression: strategy-recovery surfaces still route ----------
    def test_recovery_surfaces_route(self, admin_headers):
        r = requests.post(f"{BACKEND}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # library/list → count/items
        r = requests.get(f"{BACKEND}/api/library/list", headers=headers, timeout=15)
        assert r.status_code == 200
        b = r.json(); assert "count" in b and "items" in b

        # strategies/explorer → count/strategies
        r = requests.get(f"{BACKEND}/api/strategies/explorer", headers=headers, timeout=15)
        assert r.status_code == 200
        b = r.json(); assert "count" in b and "strategies" in b

        # strategies → strategies key (top-level)
        r = requests.get(f"{BACKEND}/api/strategies", headers=headers, timeout=15)
        assert r.status_code == 200
        b = r.json(); assert "strategies" in b

        # mutation/events → events key
        r = requests.get(f"{BACKEND}/api/mutation/events", headers=headers, timeout=15)
        assert r.status_code == 200
        b = r.json(); assert "events" in b


# ---------- Fix 6: BI5 symbol spec dataclass ----------
class TestBi5SymbolSpec:
    def test_supported_symbol(self):
        sys.path.insert(0, "/app/backend")
        from legacy.config.bi5_symbols import get_bi5_symbol_spec
        s = get_bi5_symbol_spec("EURUSD")
        assert s.symbol == "EURUSD"
        assert s.market_type == "forex"
        assert s.digits == 5
        assert s.supported is True

    def test_unsupported_symbol(self):
        sys.path.insert(0, "/app/backend")
        from legacy.config.bi5_symbols import get_bi5_symbol_spec
        s = get_bi5_symbol_spec("FAKE")
        assert s.symbol == "FAKE"
        assert s.supported is False


# ---------- Regression: 89 routers, recovery surfaces route, no bad errors ----------
class TestRegression:
    def test_89_routers_online(self):
        r = subprocess.run(
            ["grep", "-c", "89 routers/attachers online",
             "/var/log/supervisor/backend.err.log"],
            capture_output=True, text=True,
        )
        assert int(r.stdout.strip()) > 0

    def test_no_dukascopy_module_error_recent(self):
        r = subprocess.run(
            ["tail", "-n", "200", "/var/log/supervisor/backend.err.log"],
            capture_output=True, text=True,
        )
        assert "ModuleNotFoundError" not in r.stdout or "dukascopy_python" not in r.stdout, (
            "ModuleNotFoundError for dukascopy_python appeared in last 200 log lines"
        )

    def test_no_spec_symbol_attribute_error_recent(self):
        r = subprocess.run(
            ["tail", "-n", "200", "/var/log/supervisor/backend.err.log"],
            capture_output=True, text=True,
        )
        # Fix #6 target: AttributeError on '.symbol'
        assert "'dict' object has no attribute 'symbol'" not in r.stdout


# ---------- Docs ----------
class TestDocs:
    def test_ai_learning_layer(self):
        p = Path("/app/docs/AI_LEARNING_LAYER.md")
        assert p.exists()
        text = p.read_text()
        assert len(text) > 5000, f"AI_LEARNING_LAYER.md too small: {len(text)} bytes"
        # sections requested by user
        for needle in ("three layer", "L0", "L1", "L2",
                       "__migration_source", "Rollout plan"):
            assert needle.lower() in text.lower(), f"missing section keyword: {needle}"

    def test_production_audit(self):
        p = Path("/app/docs/PRODUCTION_AUDIT_2026-02.md")
        assert p.exists()
        text = p.read_text()
        assert len(text) > 5000
        needed = [
            "Missing modules", "Dead endpoints", "Legacy components",
            "Missing environment variables", "Docker issues", "Startup warnings",
            "Optional dependencies", "Broken UI pages", "Routing inconsistencies",
            "Unused code", "backlog",
        ]
        for n in needed:
            assert n.lower() in text.lower(), f"audit section missing: {n}"
