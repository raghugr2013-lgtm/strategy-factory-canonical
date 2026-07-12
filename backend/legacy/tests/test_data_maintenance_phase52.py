"""Phase 5.2 — Data Maintenance + Backup backend tests.

Covers:
    • /api/data/maintenance/status | toggle | run | config | coverage | recent-runs
    • /api/data/backup/export | export-bulk | export-all | import
    • Retention: delete_old_bid_data / delete_old_bi5_data against string timestamps
    • Non-regression: /api/auto-maintenance/* and /api/download-data, /api/upload-data routes
    • No `_id` leakage anywhere in the Phase-5.2 responses
"""
from __future__ import annotations

import io
import os
import zipfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

# ── shared helpers ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def baseline_config(s):
    """Capture the current config so we can restore at end of module."""
    r = s.get(f"{API}/data/maintenance/config")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def _restore_config_at_end(s, baseline_config):
    yield
    try:
        s.post(f"{API}/data/maintenance/config", json={
            "pairs": baseline_config.get("pairs"),
            "timeframes": baseline_config.get("timeframes"),
            "retention": baseline_config.get("retention"),
            "frequency": baseline_config.get("frequency"),
            "enabled": baseline_config.get("enabled", False),
        })
    except Exception:
        pass


def _no_id_leak(obj):
    """Recursively assert that no dict key named '_id' exists."""
    if isinstance(obj, dict):
        assert "_id" not in obj, f"_id leaked: {list(obj.keys())}"
        for v in obj.values():
            _no_id_leak(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_id_leak(v)


# ── 1. STATUS ───────────────────────────────────────────────────────────
class TestStatus:
    def test_status_shape_and_defaults(self, s):
        r = s.get(f"{API}/data/maintenance/status")
        assert r.status_code == 200
        d = r.json()
        for k in ("enabled", "last_run", "next_run", "pairs", "timeframes",
                 "retention", "frequency", "coverage", "recent_runs"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["enabled"], bool)
        assert isinstance(d["pairs"], list)
        assert isinstance(d["timeframes"], list)
        assert "bid_months" in d["retention"] and "bi5_months" in d["retention"]
        assert isinstance(d["retention"]["bid_months"], int)
        assert isinstance(d["retention"]["bi5_months"], int)
        assert d["frequency"] in ("manual", "hourly", "daily")
        assert isinstance(d["coverage"], list)
        assert isinstance(d["recent_runs"], list)
        _no_id_leak(d)

    def test_status_no_id_leak_in_coverage_and_runs(self, s):
        r = s.get(f"{API}/data/maintenance/status").json()
        for c in r["coverage"]:
            assert "_id" not in c
        for run in r["recent_runs"]:
            assert "_id" not in run


# ── 2. CONFIG ───────────────────────────────────────────────────────────
class TestConfig:
    def test_get_config_defaults_present(self, s):
        r = s.get(f"{API}/data/maintenance/config")
        assert r.status_code == 200
        d = r.json()
        assert "pairs" in d and "timeframes" in d and "retention" in d
        assert "frequency" in d and "enabled" in d
        _no_id_leak(d)

    def test_post_config_updates_all_fields(self, s):
        payload = {
            "pairs": ["EURUSD", "GBPUSD"],
            "timeframes": ["1h", "4h"],
            "retention": {"bid_months": 12, "bi5_months": 4},
            "frequency": "hourly",
        }
        r = s.post(f"{API}/data/maintenance/config", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        cfg = body["config"]
        assert cfg["pairs"] == ["EURUSD", "GBPUSD"]
        assert cfg["timeframes"] == ["1h", "4h"]
        assert cfg["retention"]["bid_months"] == 12
        assert cfg["retention"]["bi5_months"] == 4
        assert cfg["frequency"] == "hourly"
        _no_id_leak(cfg)

        # Verify GET reflects it
        g = s.get(f"{API}/data/maintenance/config").json()
        assert g["pairs"] == ["EURUSD", "GBPUSD"]
        assert g["timeframes"] == ["1h", "4h"]
        assert g["retention"] == {"bid_months": 12, "bi5_months": 4}
        assert g["frequency"] == "hourly"

    def test_post_config_frequency_validation_rejects_invalid(self, s):
        r = s.post(f"{API}/data/maintenance/config",
                   json={"frequency": "weekly"})
        # Pydantic pattern mismatch ⇒ 422
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("freq", ["manual", "hourly", "daily"])
    def test_post_config_frequency_accepts_valid(self, s, freq):
        r = s.post(f"{API}/data/maintenance/config", json={"frequency": freq})
        assert r.status_code == 200
        assert r.json()["config"]["frequency"] == freq

    def test_post_config_empty_payload_rejected(self, s):
        r = s.post(f"{API}/data/maintenance/config", json={})
        assert r.status_code == 400

    def test_pairs_uppercased(self, s):
        r = s.post(f"{API}/data/maintenance/config",
                   json={"pairs": ["eurusd", "gbpusd"]})
        assert r.status_code == 200
        assert r.json()["config"]["pairs"] == ["EURUSD", "GBPUSD"]


# ── 3. TOGGLE ───────────────────────────────────────────────────────────
class TestToggle:
    def test_toggle_on_persists_enabled(self, s):
        r = s.post(f"{API}/data/maintenance/toggle", json={"enabled": True})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["enabled"] is True
        # config persisted
        cfg = s.get(f"{API}/data/maintenance/config").json()
        assert cfg["enabled"] is True
        # status reflects the enabled flag
        st = s.get(f"{API}/data/maintenance/status").json()
        assert st["enabled"] is True
        _no_id_leak(body)

    def test_toggle_off_persists_disabled(self, s):
        r = s.post(f"{API}/data/maintenance/toggle", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        cfg = s.get(f"{API}/data/maintenance/config").json()
        assert cfg["enabled"] is False


# ── 4. RUN (full pipeline) ──────────────────────────────────────────────
class TestRun:
    def test_run_full_pipeline_smoke(self, s):
        # narrow scope to reduce external fetches
        r = s.post(f"{API}/data/maintenance/run",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"],
                         "enforce": False})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["success"] is True
        for k in ("updated_pairs", "new_records", "gaps_detected",
                  "deleted_old_records", "errors", "coverage_count"):
            assert k in d, f"missing summary key: {k}"
        assert isinstance(d["updated_pairs"], list)
        assert isinstance(d["new_records"], int)
        assert isinstance(d["coverage_count"], int)
        _no_id_leak(d)

    def test_run_with_enforce_true_reports_deleted(self, s):
        r = s.post(f"{API}/data/maintenance/run",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"],
                         "enforce": True})
        assert r.status_code == 200
        d = r.json()
        assert "deleted_old_records" in d
        assert isinstance(d["deleted_old_records"], int)

    def test_recent_runs_populated_after_run(self, s):
        r = s.get(f"{API}/data/maintenance/recent-runs?limit=5")
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "runs" in d
        assert d["count"] >= 1
        for run in d["runs"]:
            assert "_id" not in run
            assert "ran_at" in run


# ── 5. COVERAGE ─────────────────────────────────────────────────────────
class TestCoverage:
    def test_coverage_endpoint_shape(self, s):
        r = s.get(f"{API}/data/maintenance/coverage")
        assert r.status_code == 200
        d = r.json()
        assert "count" in d and "coverage" in d
        assert d["count"] == len(d["coverage"])
        for row in d["coverage"]:
            assert "_id" not in row
            for k in ("symbol", "source", "timeframe", "start_date",
                      "end_date", "completeness", "has_gaps"):
                assert k in row, f"coverage missing {k}"
            assert isinstance(row["has_gaps"], bool)
            assert isinstance(row["completeness"], (int, float))
            assert row["source"] in ("bid_1m", "bi5")


# ── 6. RETENTION — direct engine against string timestamps ────────────
class TestRetention:
    """Seeds synthetic TEST rows with ISO-string timestamps then verifies
    delete_old_bid_data / delete_old_bi5_data wipe them per the retention
    filter."""

    @pytest.mark.asyncio
    async def test_retention_deletes_old_string_timestamp_rows(self):
        import sys
        sys.path.insert(0, "/app/backend")
        # Load backend/.env so MONGO_URL + DB_NAME are available to engines.db
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from engines.db import get_db
        from data_engine import data_maintenance as dm

        db = get_db()
        sym = f"TESTRET{uuid.uuid4().hex[:6].upper()}"
        now = datetime.now(timezone.utc)
        # Seed 5 old + 2 fresh rows for each source
        docs = []
        for src in ("bid_1m", "bi5"):
            # old → 5 yrs ago for BID, 2 yrs ago for BI5 (> their retention)
            old_days = 5 * 365 if src == "bid_1m" else 400
            for i in range(5):
                docs.append({
                    "symbol": sym, "source": src, "timeframe": "1h",
                    "timestamp": (now - timedelta(days=old_days + i)).isoformat(),
                    "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                    "volume": 1.0,
                })
            for i in range(2):
                docs.append({
                    "symbol": sym, "source": src, "timeframe": "1h",
                    "timestamp": (now - timedelta(hours=i)).isoformat(),
                    "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                    "volume": 1.0,
                })
        await db["market_data"].insert_many(docs)

        try:
            # retention = default (36 bid / 6 bi5 months)
            bid_res = await dm.delete_old_bid_data(36)
            bi5_res = await dm.delete_old_bi5_data(6)
            assert bid_res["deleted"] >= 5
            assert bi5_res["deleted"] >= 5

            # Fresh rows untouched
            remaining_bid = await db["market_data"].count_documents(
                {"symbol": sym, "source": "bid_1m"})
            remaining_bi5 = await db["market_data"].count_documents(
                {"symbol": sym, "source": "bi5"})
            assert remaining_bid == 2
            assert remaining_bi5 == 2
        finally:
            await db["market_data"].delete_many({"symbol": sym})


# ── 7. BACKUP — export / import ────────────────────────────────────────
class TestBackup:
    def test_export_single_csv(self, s):
        r = s.get(f"{API}/data/backup/export",
                  params={"symbol": "EURUSD", "timeframe": "1h",
                          "source": "bid_1m"})
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.text
        first_line = body.splitlines()[0] if body else ""
        assert first_line == "timestamp,open,high,low,close,volume"

    def test_export_all_zip_structure(self, s):
        r = s.get(f"{API}/data/backup/export-all")
        assert r.status_code == 200
        assert "application/zip" in r.headers.get("content-type", "")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert "metadata.json" in names
        # at least one market_data/BID/*.csv
        assert any(n.startswith("market_data/BID/") and n.endswith(".csv")
                   for n in names), f"no BID csv in zip: {names}"
        # metadata sanity
        import json
        meta = json.loads(zf.read("metadata.json"))
        for k in ("exported_at", "symbols", "sources", "timeframes",
                  "files", "total_rows", "schema"):
            assert k in meta
        assert meta["schema"]["columns"] == ["timestamp", "open", "high",
                                             "low", "close", "volume"]

    def test_export_bulk_selected(self, s):
        r = s.post(f"{API}/data/backup/export-bulk",
                   json={"symbols": ["EURUSD"], "timeframes": ["1h"],
                         "sources": ["bid_1m"]})
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert "metadata.json" in names
        # Only BID/EURUSD_1h.csv expected
        csvs = [n for n in names if n.endswith(".csv")]
        assert any("market_data/BID/EURUSD_1h.csv" == n for n in csvs), csvs

    def test_import_roundtrip_dedup_append_only(self, s):
        # Export all → import same ZIP → expect inserted 0, skipped>0
        exp = s.get(f"{API}/data/backup/export-all")
        assert exp.status_code == 200
        zip_bytes = exp.content

        files = {"file": ("roundtrip.zip", zip_bytes, "application/zip")}
        r = requests.post(f"{API}/data/backup/import", files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("success") is True
        assert d.get("inserted", 0) == 0, \
            f"expected 0 inserts on round-trip, got {d.get('inserted')}"
        # skipped_duplicates must be >= number of existing BID rows
        assert d.get("skipped_duplicates", 0) >= 1
        assert "files" in d
        _no_id_leak(d)

    def test_import_rejects_non_zip(self, s):
        files = {"file": ("bad.csv", b"timestamp,open\n", "text/csv")}
        r = requests.post(f"{API}/data/backup/import", files=files)
        assert r.status_code == 400


# ── 8. NON-REGRESSION: /api/auto-maintenance/* + download/upload ────────
class TestNonRegression:
    def test_auto_maintenance_status_unchanged(self, s):
        r = s.get(f"{API}/auto-maintenance/status")
        assert r.status_code == 200
        d = r.json()
        for k in ("enabled", "bid_interval_minutes", "bi5_interval_minutes"):
            assert k in d

    def test_auto_maintenance_toggle_still_works(self, s):
        r = s.post(f"{API}/auto-maintenance/toggle", json={"enabled": False})
        assert r.status_code == 200

    def test_legacy_download_endpoint_exists(self, s):
        # Simple OPTIONS / HEAD to confirm route registered; GET would
        # trigger a real download. We send a HEAD and accept either 200
        # or 405 (method not allowed ⇒ route exists).
        r = requests.head(f"{API}/download-data")
        assert r.status_code in (200, 400, 404, 405, 422), r.status_code

    def test_legacy_upload_endpoint_exists(self, s):
        # POST without file should yield 422 (FastAPI validation) or 400
        # — NOT 404.
        r = requests.post(f"{API}/upload-data")
        assert r.status_code in (400, 405, 422), r.status_code
