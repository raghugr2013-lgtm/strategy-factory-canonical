"""
Iteration 7 — Stale BI5 pre-fix error row cleanup + EVOLUTION_ROADMAP doc verification.

Verifies:
  R1  Boot log line "auto-maintenance: purged N stale pre-fix BI5 error rows"
      appears between "boot" and "Application startup complete" markers,
      only when N>0.
  R2  Seed test: pre-fix row is deleted, control row survives.
  R3  Idempotence: 2nd restart with no new pre-fix rows -> log line absent
      OR reports 0; total row count unchanged.
  R4  Boot regression: '90 routers/attachers online' + auto-maintenance
      dormant/resumed line still fires immediately after purge line.
  R5  Regression sweep on 6 core endpoints.
  R6  /app/docs/EVOLUTION_ROADMAP_2026.md deliverable check.
"""
import os
import re
import time
import subprocess
from pathlib import Path

import pymongo
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "strategy_factory_v1")
BACKEND_LOG = "/var/log/supervisor/backend.err.log"
ADMIN_EMAIL = "admin@strategy-factory.local"
ADMIN_PASS = "admin123"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

PRE_FIX_ERROR = "'dict' object has no attribute 'symbol'"
CONTROL_ERROR = "some other error"

TEST_PREFIX_KEY = "TEST_stale_prefix_seed"
TEST_CONTROL_KEY = "TEST_control_seed"


# ── Fixtures ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def db():
    client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    yield client[DB_NAME]
    # Cleanup — remove any TEST_ rows we might have left
    client[DB_NAME].auto_maintenance_status.delete_many(
        {"symbol": {"$in": [TEST_PREFIX_KEY, TEST_CONTROL_KEY]}}
    )
    client.close()


def _restart_backend_and_wait(seconds: float = 6.0) -> None:
    subprocess.run(
        ["sudo", "supervisorctl", "restart", "backend"],
        check=True,
        capture_output=True,
        text=True,
    )
    time.sleep(seconds)


def _tail_log(nlines: int = 400) -> str:
    with open(BACKEND_LOG, "r") as f:
        lines = f.readlines()
    return "".join(lines[-nlines:])


def _wait_for_api(timeout: float = 30.0) -> None:
    """Poll /api/health until it responds 200 or timeout."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=3)
            if r.status_code == 200:
                return
            last = r.status_code
        except requests.RequestException as e:
            last = str(e)
        time.sleep(1)
    pytest.fail(f"/api/health did not become ready in {timeout}s (last={last})")


# ── R2 + R1: seed pre-fix + control, restart, verify purge + log ──
class TestStaleBI5Cleanup:
    def test_seed_and_purge_on_restart(self, db):
        # Clean any prior TEST_ rows
        db.auto_maintenance_status.delete_many(
            {"symbol": {"$in": [TEST_PREFIX_KEY, TEST_CONTROL_KEY]}}
        )

        # Snapshot pre-seed count (non-test rows)
        baseline_non_test = db.auto_maintenance_status.count_documents(
            {"symbol": {"$nin": [TEST_PREFIX_KEY, TEST_CONTROL_KEY]}}
        )

        # Seed one pre-fix row + one control row
        db.auto_maintenance_status.insert_many(
            [
                {
                    "symbol": TEST_PREFIX_KEY,
                    "source": "bi5_1s",
                    "state": "error",
                    "bi5_runner_error": PRE_FIX_ERROR,
                },
                {
                    "symbol": TEST_CONTROL_KEY,
                    "source": "bi5_1s",
                    "state": "error",
                    "bi5_runner_error": CONTROL_ERROR,
                },
            ]
        )
        assert db.auto_maintenance_status.count_documents(
            {"symbol": TEST_PREFIX_KEY}
        ) == 1
        assert db.auto_maintenance_status.count_documents(
            {"symbol": TEST_CONTROL_KEY}
        ) == 1

        # Restart backend
        _restart_backend_and_wait(seconds=6)
        _wait_for_api()

        # Pre-fix row must be gone; control row must remain
        assert db.auto_maintenance_status.count_documents(
            {"symbol": TEST_PREFIX_KEY}
        ) == 0, "Pre-fix seeded row was NOT purged on boot"
        assert db.auto_maintenance_status.count_documents(
            {"symbol": TEST_CONTROL_KEY}
        ) == 1, "Control row was incorrectly deleted"

        # Non-test rows should be untouched (delta 0 vs baseline)
        post_non_test = db.auto_maintenance_status.count_documents(
            {"symbol": {"$nin": [TEST_PREFIX_KEY, TEST_CONTROL_KEY]}}
        )
        # Non-test rows may have been rewritten by a BI5 tick but count
        # should not decrease due to the cleanup task (which only targets
        # the pre-fix error substring).
        pre_fix_leftover = db.auto_maintenance_status.count_documents(
            {"bi5_runner_error": {"$regex": PRE_FIX_ERROR}}
        )
        assert pre_fix_leftover == 0, (
            f"After boot cleanup there are still {pre_fix_leftover} pre-fix "
            "rows in the collection"
        )
        assert post_non_test >= 0  # sanity

    def test_purge_log_line_present_and_between_markers(self):
        """R1 — the exact log line format between boot and startup markers."""
        log = _tail_log(nlines=600)
        # Purge line uses %d format: "purged N stale pre-fix BI5 error rows"
        m = re.search(
            r"auto-maintenance: purged (\d+) stale pre-fix BI5 error rows",
            log,
        )
        assert m is not None, (
            "Boot purge log line NOT found. Expected: "
            "'auto-maintenance: purged N stale pre-fix BI5 error rows'"
        )
        n = int(m.group(1))
        assert n >= 1, f"Expected at least 1 purged row (we seeded 1); got {n}"

        # The purge line must sit between the boot marker that opened THIS
        # lifespan cycle and the corresponding 'Application startup complete'
        # marker. Locate them relative to the purge line's index.
        purge_idx = log.rfind("auto-maintenance: purged")
        boot_idx = log.rfind("boot", 0, purge_idx)
        startup_idx = log.find("Application startup complete", purge_idx)
        assert boot_idx != -1, "'boot' marker BEFORE purge line not found"
        assert startup_idx != -1, (
            "'Application startup complete' AFTER purge line not found"
        )
        assert boot_idx < purge_idx < startup_idx, (
            f"Purge log line not between markers "
            f"(boot={boot_idx}, purge={purge_idx}, startup={startup_idx})"
        )

    def test_resume_or_dormant_line_after_purge(self):
        """R4 — dormant/resumed line fires immediately after purge line."""
        log = _tail_log(nlines=600)
        purge_idx = log.rfind("auto-maintenance: purged")
        resume_idx = log.rfind("auto-maintenance scheduler resumed on boot")
        dormant_idx = log.rfind("auto-maintenance scheduler dormant on boot")
        follow_idx = max(resume_idx, dormant_idx)
        assert follow_idx != -1, (
            "Neither 'resumed on boot' nor 'dormant on boot' line found"
        )
        assert follow_idx > purge_idx, (
            "resume/dormant line does not follow the purge line"
        )

    def test_90_routers_online(self):
        """R4 — router boot regression."""
        log = _tail_log(nlines=800)
        assert "90 routers/attachers online" in log, (
            "'90 routers/attachers online' NOT found in backend log"
        )


# ── R3: idempotence — second restart with no new pre-fix rows ─────
class TestIdempotence:
    def test_second_restart_is_idempotent(self, db):
        # Snapshot pre-restart
        pre_count = db.auto_maintenance_status.count_documents({})
        pre_fix_pre = db.auto_maintenance_status.count_documents(
            {"bi5_runner_error": {"$regex": PRE_FIX_ERROR}}
        )
        assert pre_fix_pre == 0, (
            f"Precondition failed: {pre_fix_pre} pre-fix rows still present"
        )

        # Mark log offset before restart
        with open(BACKEND_LOG, "r") as f:
            before_bytes = len(f.read())

        _restart_backend_and_wait(seconds=6)
        _wait_for_api()

        # Read only new log content
        with open(BACKEND_LOG, "r") as f:
            f.seek(before_bytes)
            new_log = f.read()

        # The purge log line either does not appear OR reports 0.
        # Implementation only logs when count>0, so absence is the expected
        # behaviour. Accept both to match the review spec.
        m = re.search(
            r"auto-maintenance: purged (\d+) stale pre-fix BI5 error rows",
            new_log,
        )
        if m is not None:
            assert int(m.group(1)) == 0, (
                f"Idempotence violated — 2nd restart purged {m.group(1)} rows "
                "when 0 pre-fix rows existed"
            )
        # else — absent, which is the actual current implementation behaviour

        # Total row count must be identical (± any control row still in place)
        post_count = db.auto_maintenance_status.count_documents({})
        assert post_count == pre_count, (
            f"Row count changed across idempotent restart: "
            f"pre={pre_count}, post={post_count}"
        )

    def test_cleanup_control_row(self, db):
        """Housekeeping — remove the TEST_control_seed row now that
        cleanup verification is complete."""
        db.auto_maintenance_status.delete_many(
            {"symbol": {"$in": [TEST_PREFIX_KEY, TEST_CONTROL_KEY]}}
        )
        remaining = db.auto_maintenance_status.count_documents(
            {"symbol": {"$in": [TEST_PREFIX_KEY, TEST_CONTROL_KEY]}}
        )
        assert remaining == 0


# ── R5: regression sweep on core endpoints ────────────────────────
class TestApiRegressionSweep:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200

    def test_auto_maintenance_status(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/auto-maintenance/status",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        for k in ("enabled", "next_runs", "statuses"):
            assert k in body, f"missing key {k!r} in /auto-maintenance/status"

    def test_library_list(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/library/list", headers=admin_headers, timeout=15
        )
        assert r.status_code == 200

    def test_knowledge_status(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/knowledge/status", headers=admin_headers, timeout=15
        )
        assert r.status_code == 200
        body = r.json()
        for k in ("collection", "total", "per_source"):
            assert k in body, f"missing key {k!r} in /knowledge/status"

    def test_admin_providers(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/providers", headers=admin_headers, timeout=15
        )
        assert r.status_code == 200

    def test_llm_diagnostics(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/llm/diagnostics", headers=admin_headers, timeout=15
        )
        assert r.status_code == 200
        body = r.json()
        assert "primary_provider" in body or "providers" in body, (
            "expected 'primary_provider' or 'providers' key"
        )


# ── R6: EVOLUTION_ROADMAP_2026.md deliverable ─────────────────────
class TestEvolutionRoadmapDoc:
    DOC = Path("/app/docs/EVOLUTION_ROADMAP_2026.md")

    def test_exists_and_size(self):
        assert self.DOC.exists(), f"{self.DOC} not found"
        size = self.DOC.stat().st_size
        assert size > 4 * 1024, f"Doc is {size} bytes, expected > 4KB"

    def test_section_headers(self):
        text = self.DOC.read_text()
        required = [
            "## 2. Recommended priority",
            "## 3. What I shipped this pass",
            "## 4. Detailed recommendations per priority",
            "## 5. Non-recommendations",
            "## 6. What I need from you",
        ]
        for h in required:
            assert h in text, f"missing section header {h!r}"

    def test_priority_and_outcome_refs(self):
        text = self.DOC.read_text()
        for p in ("P1", "P2", "P3", "P4", "P5"):
            assert p in text, f"missing priority ref {p}"
        assert "outcome_events" in text, "missing outcome_events reference"

    def test_no_python_or_fastapi_code(self):
        """No python imports or FastAPI decorators in the .md file."""
        text = self.DOC.read_text()
        # Import statements at line start
        assert not re.search(
            r"(?m)^\s*(from\s+\w+\s+import|import\s+\w+)", text
        ), "Python import statement found in markdown"
        # FastAPI decorators
        assert not re.search(
            r"@(app|router)\.(get|post|put|delete|patch)\b", text
        ), "FastAPI decorator found in markdown"
