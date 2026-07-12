"""Phase 5.5 Auto Factory — backend API tests.

Covers:
 - Status & saved config endpoints (phase=5.5 dispatch)
 - Config update via POST /saved with op=update_config
 - History view
 - Async run kickoff + status transition
 - Concurrency 409
 - Scheduler enable/disable
 - Regression: Phase 5 endpoints unchanged
 - Validation: invalid op / wrong phase -> 400
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend .env parse at import time
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = ln.strip().split("=", 1)[1].rstrip("/")
                    break
    except Exception:
        pass

API = f"{BASE_URL}/api/auto-factory"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Status / Config ─────────────────────────────────────────────────
class TestStatusAndConfig:
    def test_status_phase55(self, s):
        r = s.get(f"{API}/status", params={"phase": "5.5"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("phase") == "5.5"
        for k in ("running", "current_run", "last_run", "history", "scheduler"):
            assert k in data, f"missing key {k}"
        assert isinstance(data["history"], list)
        assert isinstance(data["scheduler"], dict)
        assert "enabled" in data["scheduler"]

    def test_config_defaults(self, s):
        r = s.get(f"{API}/saved", params={"phase": "5.5", "view": "config"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("phase") == "5.5"
        cfg = body.get("config") or {}
        # All default keys present
        for k in ("pairs", "timeframes", "styles", "min_pf", "min_runs",
                  "max_drawdown", "firm", "per_combo", "top_n_store",
                  "run_data_maintenance", "run_ingestion", "run_mutation",
                  "run_validation", "run_selection", "step_timeout_sec"):
            assert k in cfg, f"config missing key {k}"
        # Defaults per spec
        assert float(cfg["min_pf"]) >= 0
        assert int(cfg["min_runs"]) >= 1
        assert float(cfg["max_drawdown"]) <= 1.0

    def test_update_config_min_pf(self, s):
        # Capture original
        r0 = s.get(f"{API}/saved", params={"phase": "5.5", "view": "config"}, timeout=30)
        original = (r0.json().get("config") or {}).get("min_pf", 1.2)

        body = {"phase": "5.5", "op": "update_config", "patch": {"min_pf": 1.5}}
        r = s.post(f"{API}/saved", json=body, timeout=30)
        assert r.status_code == 200, r.text
        cfg = r.json().get("config") or {}
        assert float(cfg.get("min_pf")) == 1.5, cfg

        # Verify persistence via GET
        r2 = s.get(f"{API}/saved", params={"phase": "5.5", "view": "config"}, timeout=30)
        assert float((r2.json().get("config") or {}).get("min_pf")) == 1.5

        # Restore original
        s.post(f"{API}/saved", json={"phase": "5.5", "op": "update_config",
                                     "patch": {"min_pf": original}}, timeout=30)

    def test_post_saved_wrong_phase_rejected(self, s):
        r = s.post(f"{API}/saved", json={"phase": "5", "op": "update_config", "patch": {}},
                   timeout=30)
        assert r.status_code == 400, r.text

    def test_post_saved_missing_op(self, s):
        r = s.post(f"{API}/saved", json={"phase": "5.5"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_post_saved_unknown_op(self, s):
        r = s.post(f"{API}/saved", json={"phase": "5.5", "op": "bogus"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_history_view(self, s):
        r = s.get(f"{API}/saved", params={"phase": "5.5", "view": "history"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("phase") == "5.5"
        assert "count" in body and "runs" in body
        assert isinstance(body["runs"], list)
        assert body["count"] == len(body["runs"])


# ── Run Cycle (async) ───────────────────────────────────────────────
class TestRunCycle:
    def test_async_kickoff_and_completion(self, s):
        payload = {
            "phase": "5.5",
            "wait": False,
            "run_data_maintenance": False,
            "run_ingestion": False,
            "run_mutation": False,
            "run_validation": False,
            "run_selection": False,
        }
        r = s.post(f"{API}/run", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("mode") == "async"
        assert body.get("phase") == "5.5"
        assert body.get("accepted") is True
        assert "poll" in body

        # Poll until not running (steps all skipped → should complete in a couple seconds)
        last_run = None
        deadline = time.time() + 30
        while time.time() < deadline:
            st = s.get(f"{API}/status", params={"phase": "5.5"}, timeout=15).json()
            if not st.get("running") and st.get("last_run"):
                last_run = st["last_run"]
                break
            time.sleep(1)
        assert last_run is not None, "run did not complete in 30s"

        # Verify steps array has 6 step summaries (data, generate, mutate,
        # validate, select, store)
        steps = last_run.get("steps") or []
        assert len(steps) == 6, f"expected 6 steps, got {len(steps)}: {steps}"
        step_names = [s.get("step") for s in steps]
        assert step_names == ["data", "generate", "mutate", "validate", "select", "store"], step_names
        assert "stored_count" in last_run

    def test_concurrency_returns_409(self, s):
        # Use a long-running step (mutation polls until done) + short
        # per-step timeout so overall cycle takes multiple seconds, giving
        # the second request a chance to observe the in-flight lock.
        payload = {
            "phase": "5.5",
            "wait": False,
            "run_data_maintenance": False,
            "run_ingestion": False,
            "run_mutation": True,      # keeps the cycle alive (poll loop)
            "run_validation": False,
            "run_selection": False,
            "step_timeout_sec": 30,
        }
        r1 = s.post(f"{API}/run", json=payload, timeout=30)
        assert r1.status_code == 200, r1.text

        # Try up to ~8s to catch the running window
        got_409 = False
        deadline = time.time() + 8
        while time.time() < deadline:
            r2 = s.post(f"{API}/run", json={"phase": "5.5", "wait": False,
                                            "run_data_maintenance": False,
                                            "run_ingestion": False,
                                            "run_mutation": False,
                                            "run_validation": False,
                                            "run_selection": False},
                        timeout=15)
            if r2.status_code == 409:
                got_409 = True
                break
            # Not yet in-flight — retry fast
            time.sleep(0.1)

        # Wait for quiescence before next tests
        for _ in range(60):
            st = s.get(f"{API}/status", params={"phase": "5.5"}, timeout=15).json()
            if not st.get("running"):
                break
            time.sleep(1)

        assert got_409, "expected 409 'already_running' while cycle in-flight"


# ── Scheduler ───────────────────────────────────────────────────────
class TestScheduler:
    def test_enable_then_disable(self, s):
        r = s.post(f"{API}/schedule", json={"phase": "5.5", "enabled": True,
                                            "interval_hours": 0.25}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("phase") == "5.5"
        sched = body.get("scheduler") or {}
        assert sched.get("enabled") is True
        assert float(sched.get("interval_hours")) == 0.25
        assert sched.get("next_run_at"), "next_run_at must be set when enabled"

        # Confirm via status
        st = s.get(f"{API}/status", params={"phase": "5.5"}, timeout=15).json()
        assert st.get("scheduler", {}).get("enabled") is True

        # Disable
        r2 = s.post(f"{API}/schedule", json={"phase": "5.5", "enabled": False,
                                             "interval_hours": 6}, timeout=30)
        assert r2.status_code == 200, r2.text
        assert (r2.json().get("scheduler") or {}).get("enabled") is False

        st2 = s.get(f"{API}/status", params={"phase": "5.5"}, timeout=15).json()
        assert st2.get("scheduler", {}).get("enabled") is False


# ── Phase 5 Regression ──────────────────────────────────────────────
class TestPhase5Regression:
    def test_status_no_phase_is_phase5(self, s):
        r = s.get(f"{API}/status", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Phase 5 snapshot — does NOT carry the phase:'5.5' marker
        assert data.get("phase") != "5.5"
        for k in ("running", "current_run", "last_run", "history", "scheduler"):
            assert k in data, f"Phase 5 status missing {k}"

    def test_saved_no_params_legacy_shape(self, s):
        r = s.get(f"{API}/saved", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "count" in body
        assert "strategies" in body
        # Legacy shape should not include the 'phase' discriminator
        assert body.get("phase") != "5.5"
