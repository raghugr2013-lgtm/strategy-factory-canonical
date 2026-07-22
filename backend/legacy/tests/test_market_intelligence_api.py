"""Strategy Market Intelligence API tests.

Covers all endpoints added by the Market Intelligence layer:
- GET  /api/market-intelligence/config
- POST /api/strategies/{hash}/market-scan   (+ force, + 404, + skip behaviour)
- GET  /api/strategies/{hash}/market-profile (+ 404)
- POST /api/market-intelligence/scan-eligible
- GET  /api/market-intelligence/rankings
- Explorer/export regression: now include best_environment / market_profile_cells
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://stall-debug.preview.emergentagent.com",
).rstrip("/")

SEED_RSI = "a649abeabefcc045cc9ef2dc2ec04e1f3f2b55da"
UNKNOWN_HASH = "deadbeef" * 5


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Config ──────────────────────────────────────────────────────────

class TestConfig:
    def test_config_shape(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/market-intelligence/config", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["default_pairs"] == ["EURUSD", "GBPUSD", "XAUUSD"]
        assert d["default_timeframes"] == ["M30", "H1", "H4"]
        assert d["min_pf_for_scan"] == 1.2
        assert d["min_runs_for_scan"] == 3
        assert d["max_strategies_per_cycle"] == 3


# ── Market scan (per-strategy) ──────────────────────────────────────

class TestMarketScan:
    def test_scan_unknown_hash_404(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/strategies/{UNKNOWN_HASH}/market-scan",
            json={}, timeout=30,
        )
        assert r.status_code == 404

    def test_scan_force_true_seeded(self, api_client):
        """force=True re-computes all cells and must not 500 on GBPUSD (no candles)."""
        r = api_client.post(
            f"{BASE_URL}/api/strategies/{SEED_RSI}/market-scan",
            json={"force": True}, timeout=120,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "ok"
        assert d["strategy_hash"] == SEED_RSI
        assert d["scanned"] == 9, f"expected 9 cells, got {d.get('scanned')}"
        cells = d["cells"]
        assert len(cells) == 9
        # GBPUSD has zero candles - should come back as no_data
        gbp_cells = [c for c in cells if c["pair"] == "GBPUSD"]
        assert len(gbp_cells) == 3
        for c in gbp_cells:
            assert c["status"] == "no_data", c
        assert all(lbl.startswith("GBPUSD/") for lbl in d["no_data"])
        assert d["best_environment"] is not None
        be = d["best_environment"]
        for k in ("pair", "timeframe", "pf", "dd_pct", "score", "confidence"):
            assert k in be

    def test_scan_skip_without_force(self, api_client):
        """Without force, a second call should skip already-scored cells
        (ts unchanged on EURUSD/H1)."""
        # Ensure baseline scored exists (previous test did force)
        first = api_client.post(
            f"{BASE_URL}/api/strategies/{SEED_RSI}/market-scan",
            json={}, timeout=120,
        )
        assert first.status_code == 200
        cells_first = {(c["pair"], c["timeframe"]): c for c in first.json()["cells"]}

        # tiny sleep to ensure new ts would differ if it changed
        time.sleep(1.2)

        second = api_client.post(
            f"{BASE_URL}/api/strategies/{SEED_RSI}/market-scan",
            json={}, timeout=120,
        )
        assert second.status_code == 200
        d2 = second.json()
        cells_second = {(c["pair"], c["timeframe"]): c for c in d2["cells"]}

        # EURUSD/H1 must be scored in both and ts unchanged
        key = ("EURUSD", "H1")
        assert cells_first[key]["status"] == "scored"
        assert cells_second[key]["status"] == "scored"
        assert cells_first[key]["ts"] == cells_second[key]["ts"], (
            f"ts should be unchanged without force: "
            f"{cells_first[key]['ts']} vs {cells_second[key]['ts']}"
        )
        # At least one EURUSD or XAUUSD cell must be in skipped
        assert any(lbl.startswith(("EURUSD/", "XAUUSD/")) for lbl in d2.get("skipped", []))

    def test_scan_force_changes_ts(self, api_client):
        """force=true should refresh ts on at least one scored cell."""
        # take snapshot of current ts via profile
        prof = api_client.get(
            f"{BASE_URL}/api/strategies/{SEED_RSI}/market-profile", timeout=30,
        ).json()
        before = {(c["pair"], c["timeframe"]): c.get("ts") for c in prof["cells"]}
        time.sleep(1.2)
        r = api_client.post(
            f"{BASE_URL}/api/strategies/{SEED_RSI}/market-scan",
            json={"force": True}, timeout=120,
        )
        assert r.status_code == 200
        after = {(c["pair"], c["timeframe"]): c.get("ts") for c in r.json()["cells"]}
        changed = [k for k in before if before[k] and after.get(k) and before[k] != after[k]]
        assert len(changed) >= 1, f"force=true did not refresh any cell ts. before={before} after={after}"


# ── Market profile (read) ───────────────────────────────────────────

class TestMarketProfile:
    def test_profile_ok(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/strategies/{SEED_RSI}/market-profile", timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["strategy_hash"] == SEED_RSI
        assert isinstance(d["cells"], list) and len(d["cells"]) >= 1
        assert "best_environment" in d
        assert "scanned_at" in d

    def test_profile_unknown_hash_404(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/strategies/{UNKNOWN_HASH}/market-profile", timeout=30,
        )
        assert r.status_code == 404


# ── Batch eligible scan ─────────────────────────────────────────────

class TestScanEligible:
    def test_scan_eligible_limit3(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/market-intelligence/scan-eligible",
            json={"limit": 3}, timeout=300,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "ok"
        assert "eligible_considered" in d
        assert "scanned" in d and isinstance(d["scanned"], list)
        assert d["eligible_considered"] <= 3
        for s in d["scanned"]:
            assert "strategy_hash" in s
            assert "best_environment" in s  # may be None


# ── Rankings ────────────────────────────────────────────────────────

class TestRankings:
    def test_rankings(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/market-intelligence/rankings", timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "environments" in d and "count" in d
        envs = d["environments"]
        # Ordered by avg_score desc
        scores = [e.get("avg_score") or 0.0 for e in envs]
        assert scores == sorted(scores, reverse=True)
        # Each env has pair/timeframe
        for e in envs:
            assert "pair" in e and "timeframe" in e


# ── Explorer / Export regression with new fields ────────────────────

class TestExplorerExportEnrichment:
    def test_explorer_has_best_environment_field(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/explorer", timeout=30)
        assert r.status_code == 200
        strats = r.json()["strategies"]
        assert len(strats) > 0
        # Every row must have the key, even if null
        for s in strats:
            assert "best_environment" in s, f"missing best_environment on row: {s.get('strategy_hash')}"
        # SEED_RSI must have a populated best_environment (we just scanned it)
        rsi_row = next((s for s in strats if s["strategy_hash"] == SEED_RSI), None)
        assert rsi_row is not None
        assert rsi_row["best_environment"] is not None, "SEED_RSI best_environment should be populated after scans"
        be = rsi_row["best_environment"]
        for k in ("pair", "timeframe", "pf", "score", "confidence"):
            assert k in be

    def test_export_json_includes_market_profile(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{SEED_RSI}/export", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "best_environment" in d
        assert "market_profile_cells" in d
        assert isinstance(d["market_profile_cells"], list)
        assert len(d["market_profile_cells"]) >= 1

    def test_export_cbot_has_recommended_env(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{SEED_RSI}/export/cbot", timeout=30)
        assert r.status_code == 200
        body = r.text
        assert "RECOMMENDED ENVIRONMENT" in body, body[:800]


# ── Regression: existing endpoints still healthy ────────────────────

class TestRegression:
    def test_strategies_list(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies", timeout=30)
        assert r.status_code == 200

    def test_ingestion_status(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/ingestion/status", timeout=30)
        assert r.status_code < 500

    def test_history_still_works(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{SEED_RSI}/history", timeout=30)
        assert r.status_code == 200
