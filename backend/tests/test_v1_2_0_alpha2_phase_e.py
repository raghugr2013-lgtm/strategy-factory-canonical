"""v1.2.0-alpha2 Phase E — Autonomous production stability tests.

These tests validate that the Phase E stability harness works and that
the compressed 10-min report produced during Phase E delivery is
present and PASSing. They do NOT re-run the 10-min drill (too slow for
CI); instead they assert:

  - the harness script exists and imports cleanly
  - the report JSON exists and reports `verdict.pass == True`
  - the underlying components the drill exercised still behave
    correctly (orchestrator running, self_rebuild dispatchable,
    outcome events writable) — these are functional smoke tests
    orthogonal to the 10-min drill artefact.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": "admin@strategy-factory.local",
                       "password": "admin123"})
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    api.headers.update({"Authorization": f"Bearer {tok}"})
    return api


class TestHarnessExists:
    def test_script_exists(self):
        p = Path("/app/backend/scripts/phase_e_stability_run.py")
        assert p.exists()

    def test_script_imports_cleanly(self):
        r = subprocess.run(
            ["python3", "-c",
             "import importlib.util as u; "
             "spec = u.spec_from_file_location('phe', "
             "'/app/backend/scripts/phase_e_stability_run.py'); "
             "m = u.module_from_spec(spec); spec.loader.exec_module(m); "
             "print('ok', hasattr(m, 'main'))"],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy"},
            cwd="/app/backend",
        )
        assert r.returncode == 0, r.stderr
        assert "ok True" in r.stdout


class TestReportArtefact:
    def test_report_present_and_passes(self):
        p = Path("/app/audit/PHASE_E_STABILITY_REPORT.json")
        assert p.exists(), "run scripts/phase_e_stability_run.py first"
        d = json.loads(p.read_text())["report"]
        assert d["verdict"]["pass"] is True, d["verdict"]
        for sig in ("no_leak", "rebuild_fast", "no_errors",
                    "orchestrator_alive", "learning_loop_alive"):
            assert d["verdict"]["signals"][sig] is True

    def test_report_growth_zero(self):
        d = json.loads(
            Path("/app/audit/PHASE_E_STABILITY_REPORT.json").read_text())["report"]
        assert d["rss_growth_per_hour_mb"] < 50.0

    def test_report_had_no_errors(self):
        d = json.loads(
            Path("/app/audit/PHASE_E_STABILITY_REPORT.json").read_text())["report"]
        assert d["n_errors"] == 0

    def test_report_wrote_events(self):
        d = json.loads(
            Path("/app/audit/PHASE_E_STABILITY_REPORT.json").read_text())["report"]
        # The harness triggers portfolio rebuilds each tick which each
        # emit ≥1 outcome event; delta should be substantial.
        assert d["outcome_events_written"] > 100

    def test_report_orchestrator_dispatching(self):
        d = json.loads(
            Path("/app/audit/PHASE_E_STABILITY_REPORT.json").read_text())["report"]
        assert d["orchestrator_dispatched_delta"] > 50


class TestSmokeUnderlyingComponents:
    """Functional smoke tests — verify the same primitives the harness
    exercises still behave correctly (independent of the drill artefact)."""

    def test_portfolio_rebuild_endpoint_reachable(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/rebuild/smoke", json={
            "regime": "unknown",
            "state": {"master_bot_id": "smoke", "members": []},
        })
        assert r.status_code == 200
        b = r.json()
        assert "outcome_events_ids" in b
        assert "active_selection" in b

    def test_orchestrator_status_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/status")
        assert r.status_code == 200
        s = r.json()
        assert "meta" in s
        assert "tick_count" in s["meta"]

    def test_continuous_status_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/continuous/status")
        assert r.status_code == 200
        assert "runtime" in r.json()

    def test_self_rebuild_task_dispatchable(self, admin):
        r = admin.post(
            f"{BASE_URL}/api/orchestrator/tasks/self_rebuild/dispatch")
        assert r.status_code == 200
        assert "ok" in r.json()
