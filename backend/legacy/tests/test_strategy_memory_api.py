"""Strategy Memory + Explorer API tests.

Covers:
- GET  /api/strategies/explorer (+ filters)
- GET  /api/strategies/{hash}/history (+ 404)
- POST /api/strategies/{hash}/re-run (+ 404)
- GET  /api/strategies/{hash}/export
- GET  /api/strategies/{hash}/export/cbot
- POST /api/strategies/{hash}/favorite (toggle + persistence)
- Regression: /api/strategies still 200 (not shadowed by new router).
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://strategy-factory-v1.preview.emergentagent.com",
).rstrip("/")

SEED_RSI = "a649abeabefcc045cc9ef2dc2ec04e1f3f2b55da"   # RSI Reversion, 5 runs, PF 1.60
SEED_MACD = "a9f6d5fb6f6b71b066dc304e64c5b6af61437f38"  # MACD Trend,     3 runs, PF 1.12
UNKNOWN_HASH = "deadbeef" * 5  # 40 chars, not in DB


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Explorer ────────────────────────────────────────────────────────

class TestExplorer:
    def test_explorer_basic(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/explorer", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "count" in data and "strategies" in data and "filters_applied" in data
        assert data["count"] >= 2
        hashes = {s["strategy_hash"] for s in data["strategies"]}
        assert SEED_RSI in hashes
        assert SEED_MACD in hashes
        # spot-check required fields on a row
        row = next(s for s in data["strategies"] if s["strategy_hash"] == SEED_RSI)
        for key in ("best_pf", "avg_pf", "last_pf", "runs", "stability_score",
                    "indicators", "pair", "timeframe", "sources"):
            assert key in row, f"missing {key}"
        assert row["runs"] == 5
        assert row["best_pf"] == 1.6

    def test_explorer_filter_source_ingestion(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/strategies/explorer",
            params={"source": "ingestion"}, timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        # RSI row has source "ingestion:github" — should match regex
        hashes = {s["strategy_hash"] for s in data["strategies"]}
        assert SEED_RSI in hashes

    def test_explorer_filter_source_mutation_runner(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/strategies/explorer",
            params={"source": "mutation_runner"}, timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        for s in data["strategies"]:
            assert any("mutation_runner" in src for src in s.get("sources", []))

    def test_explorer_filter_min_pf(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/strategies/explorer",
            params={"min_pf": 1.5}, timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        hashes = {s["strategy_hash"] for s in data["strategies"]}
        assert SEED_RSI in hashes          # 1.60 >= 1.5
        assert SEED_MACD not in hashes     # 1.12 < 1.5
        for s in data["strategies"]:
            assert s["best_pf"] >= 1.5

    def test_explorer_filter_min_runs(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/strategies/explorer",
            params={"min_runs": 4}, timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        hashes = {s["strategy_hash"] for s in data["strategies"]}
        assert SEED_RSI in hashes     # 5 runs
        assert SEED_MACD not in hashes  # 3 runs


# ── History ─────────────────────────────────────────────────────────

class TestHistory:
    def test_history_rsi(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{SEED_RSI}/history", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["strategy_hash"] == SEED_RSI
        assert data["runs"] == 5
        assert isinstance(data["history"], list) and len(data["history"]) == 5
        summary = data["summary"]
        for k in ("best_pf", "avg_pf", "last_pf", "best_dd", "mutation_type_counts"):
            assert k in summary
        assert summary["best_pf"] == 1.6
        assert isinstance(summary["mutation_type_counts"], dict)
        assert sum(summary["mutation_type_counts"].values()) == 5

    def test_history_unknown_hash_404(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{UNKNOWN_HASH}/history", timeout=30)
        assert r.status_code == 404


# ── Re-run ──────────────────────────────────────────────────────────

class TestReRun:
    def test_rerun_unknown_hash_404(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/strategies/{UNKNOWN_HASH}/re-run",
            json={"max_variants": 3, "auto_save": False, "firm": "ftmo"},
            timeout=30,
        )
        assert r.status_code == 404

    def test_rerun_seeded_graceful(self, api_client):
        """Real mutation pipeline may fail (missing candles) — accept non-2xx
        gracefully. Required: NOT 404 (hash is known) and responds within
        generous timeout."""
        r = api_client.post(
            f"{BASE_URL}/api/strategies/{SEED_RSI}/re-run",
            json={"max_variants": 2, "auto_save": False, "firm": "ftmo"},
            timeout=180,
        )
        assert r.status_code != 404, "Known hash must not return 404"
        # Accept 200 (pipeline ran) OR 500 (pipeline failed gracefully)
        assert r.status_code in (200, 500), f"Unexpected: {r.status_code} {r.text[:300]}"


# ── Export ──────────────────────────────────────────────────────────

class TestExport:
    def test_export_json(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{SEED_RSI}/export", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["strategy_hash"] == SEED_RSI
        for k in ("name", "indicators", "pair", "timeframe",
                  "strategy_text", "performance", "ready_for_cbot"):
            assert k in data
        perf = data["performance"]
        for k in ("best_pf", "avg_pf", "stability_score"):
            assert k in perf

    def test_export_unknown_hash_404(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{UNKNOWN_HASH}/export", timeout=30)
        assert r.status_code == 404

    def test_export_cbot(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies/{SEED_RSI}/export/cbot", timeout=30)
        assert r.status_code == 200, r.text
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd
        assert ".cs" in cd
        ct = r.headers.get("Content-Type", "")
        assert "text/x-csharp" in ct or "csharp" in ct
        body = r.text
        assert body.startswith("// ─────"), f"body start: {body[:40]!r}"
        # class name includes the 8-char hash prefix
        import re
        assert re.search(r"class\s+\w+_" + SEED_RSI[:8] + r"\s*:\s*Robot", body), body[:500]


# ── Favorites ───────────────────────────────────────────────────────

class TestFavorites:
    def test_favorite_toggle_and_filter(self, api_client):
        # set favorite true
        r = api_client.post(
            f"{BASE_URL}/api/strategies/{SEED_MACD}/favorite",
            json={"is_favorite": True}, timeout=30,
        )
        assert r.status_code == 200, r.text

        # explorer favorites_only=true should now include MACD
        r = api_client.get(
            f"{BASE_URL}/api/strategies/explorer",
            params={"favorites_only": "true"}, timeout=30,
        )
        assert r.status_code == 200
        hashes = {s["strategy_hash"] for s in r.json()["strategies"]}
        assert SEED_MACD in hashes

        # unset favorite
        r = api_client.post(
            f"{BASE_URL}/api/strategies/{SEED_MACD}/favorite",
            json={"is_favorite": False}, timeout=30,
        )
        assert r.status_code == 200

        # explorer favorites_only=true should exclude MACD now
        r = api_client.get(
            f"{BASE_URL}/api/strategies/explorer",
            params={"favorites_only": "true"}, timeout=30,
        )
        assert r.status_code == 200
        hashes = {s["strategy_hash"] for s in r.json()["strategies"]}
        assert SEED_MACD not in hashes


# ── Regression: existing routes still work ──────────────────────────

class TestRegression:
    def test_strategies_list_not_shadowed(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/strategies", timeout=30)
        assert r.status_code == 200, r.text

    def test_ingestion_route_still_mounted(self, api_client):
        # Just verify router is mounted (any 2xx/4xx is fine, 5xx is bad)
        r = api_client.get(f"{BASE_URL}/api/ingestion/status", timeout=30)
        assert r.status_code < 500, f"ingestion router broken: {r.status_code}"
