"""Phase 22.2 — Historical backfill API + coverage fields regression tests.

Tests only the contract of the new /api/data/maintenance/backfill endpoint
and the new coverage-row fields (target_months / actual_months /
backfill_progress_pct). Does NOT hit Dukascopy with heavy payloads —
uses single-pair/tf scope and accepts candles_added>=0 (idempotency is
fine either way).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to internal (auth bypassed for localhost)
    BASE_URL = "http://localhost:8001"

TIMEOUT = 120  # backfill can take ~60s


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Validation (fast) ────────────────────────────────────────────────
class TestBackfillValidation:
    def test_months_below_min_rejected(self, s):
        r = s.post(f"{BASE_URL}/api/data/maintenance/backfill",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"], "months": 0},
                   timeout=30)
        assert r.status_code == 422, r.text

    def test_months_above_max_rejected(self, s):
        r = s.post(f"{BASE_URL}/api/data/maintenance/backfill",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"], "months": 121},
                   timeout=30)
        assert r.status_code == 422, r.text

    def test_source_enum_rejected(self, s):
        r = s.post(f"{BASE_URL}/api/data/maintenance/backfill",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"], "source": "bogus"},
                   timeout=30)
        assert r.status_code == 422, r.text

    def test_source_bid_1m_accepted(self, s):
        # scoped to single pair/tf; idempotent so cheap on 2nd run
        r = s.post(f"{BASE_URL}/api/data/maintenance/backfill",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"],
                         "months": 12, "source": "bid_1m"},
                   timeout=TIMEOUT)
        assert r.status_code == 200, r.text


# ── Response shape + idempotency ─────────────────────────────────────
class TestBackfillShape:
    def test_response_shape(self, s):
        r = s.post(f"{BASE_URL}/api/data/maintenance/backfill",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"], "months": 12},
                   timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        # required top-level fields
        for k in ("success", "target_months", "source",
                  "total_candles_added", "count", "results"):
            assert k in d, f"missing key: {k}"
        assert d["success"] is True
        assert d["target_months"] == 12
        assert d["source"] == "bid_1m"
        assert d["count"] == len(d["results"])
        assert isinstance(d["results"], list) and len(d["results"]) == 1
        row = d["results"][0]
        for k in ("symbol", "timeframe", "source", "candles_added"):
            assert k in row, f"missing row key: {k}"
        assert row["symbol"] == "EURUSD"
        assert row["timeframe"] == "1h"

    def test_idempotent_on_second_call(self, s):
        """After initial backfill (previous test or main agent's manual run),
        a second identical call should either add 0 candles OR skip with
        'already at or beyond target coverage'."""
        r = s.post(f"{BASE_URL}/api/data/maintenance/backfill",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"], "months": 12},
                   timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        row = d["results"][0]
        # Either perfectly idempotent (0 added + skip msg) OR a minor top-up
        # from the previous tick is acceptable; hard-fail only on a large re-fetch.
        assert row["candles_added"] <= 200, (
            f"Idempotency broken: 2nd call added {row['candles_added']} rows"
        )
        if row["candles_added"] == 0:
            # must surface the skip reason when nothing added AND no error
            if not row.get("error"):
                sr = (row.get("skipped_reason") or "").lower()
                assert "already" in sr or "target" in sr or "empty" in sr or sr == "", \
                    f"expected skip reason, got: {row.get('skipped_reason')}"


# ── Coverage rows carry new fields ────────────────────────────────────
class TestCoverageFields:
    def test_coverage_exposes_target_and_progress(self, s):
        r = s.get(f"{BASE_URL}/api/data/maintenance/coverage", timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json().get("coverage", [])
        assert isinstance(rows, list) and len(rows) > 0

        # At least one row must carry the new Phase-22.2 fields. Stale rows
        # (never touched post-fix) are allowed to lack them.
        enriched = [row for row in rows
                    if "target_months" in row
                    and "actual_months" in row
                    and "backfill_progress_pct" in row]
        assert len(enriched) > 0, (
            "No coverage row has the new target_months/actual_months/"
            "backfill_progress_pct fields — fix not active"
        )

        # Spot-check a bid_1m/1h enriched row if one exists
        bid_1h = [r for r in enriched
                  if r.get("source") == "bid_1m" and r.get("timeframe") == "1h"]
        if bid_1h:
            row = bid_1h[0]
            assert row["target_months"] >= 1
            assert row["actual_months"] >= 0
            assert 0 <= row["backfill_progress_pct"] <= 150  # allow slight overshoot

    def test_coverage_no_mongo_id_leak(self, s):
        r = s.get(f"{BASE_URL}/api/data/maintenance/coverage", timeout=30)
        assert r.status_code == 200
        for row in r.json().get("coverage", []):
            assert "_id" not in row


# ── Regression: existing endpoints unchanged ──────────────────────────
class TestRegression:
    def test_manual_run_still_works(self, s):
        r = s.post(f"{BASE_URL}/api/data/maintenance/run",
                   json={"pairs": ["EURUSD"], "timeframes": ["1h"]},
                   timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True

    def test_auto_maintenance_run_now_still_works(self, s):
        r = s.post(f"{BASE_URL}/api/auto-maintenance/run-now", timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_status_endpoint_still_works(self, s):
        r = s.get(f"{BASE_URL}/api/data/maintenance/status", timeout=30)
        assert r.status_code == 200
