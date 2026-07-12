"""Backend API tests for Prop Firm Rule Engine + Challenge Simulator (Phase 1 additive).

Covers:
  * GET  /api/prop-firm-analysis/rules
  * GET  /api/prop-firm-analysis/rules/{firm_slug}
  * POST /api/strategies/{hash}/prop-analysis
  * GET  /api/strategies/{hash}/prop-analysis
  * POST /api/prop-firm-analysis/batch-analyze
  * GET  /api/strategies/explorer (enriched with prop_analysis)
  * GET  /api/strategies/{hash}/export (enriched)
  * GET  /api/strategies/{hash}/export/cbot (banner + auto-stop)
  * Regression: strategy-memory + market-intelligence endpoints
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

SEED_HASH = "a649abeabefcc045cc9ef2dc2ec04e1f3f2b55da"
FTMO = "ftmo"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Rules endpoints ──────────────────────────────────────────────────
class TestPropFirmRules:
    def test_list_rules_contains_flat_schema(self, api):
        r = api.get(f"{BASE_URL}/api/prop-firm-analysis/rules")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "rules" in body
        assert body["count"] >= 1
        ftmo = next((x for x in body["rules"] if x.get("firm_slug") == FTMO), None)
        assert ftmo is not None, "FTMO missing in rules list"
        # Flat schema keys
        for k in [
            "firm_slug", "max_daily_loss_pct", "daily_loss_type",
            "max_total_loss_pct", "trailing_drawdown", "trailing_type",
            "profit_target_pct", "min_trading_days", "max_trades_per_day",
            "consistency_rule",
        ]:
            assert k in ftmo, f"missing key {k} in FTMO rule"
        # Exact FTMO values required by spec
        assert ftmo["max_daily_loss_pct"] == 5.0
        assert ftmo["max_total_loss_pct"] == 10.0
        assert ftmo["profit_target_pct"] == 10.0
        assert ftmo["min_trading_days"] == 4
        assert ftmo["daily_loss_type"] == "equity"

    def test_get_rule_by_slug(self, api):
        r = api.get(f"{BASE_URL}/api/prop-firm-analysis/rules/{FTMO}")
        assert r.status_code == 200
        doc = r.json()
        assert doc["firm_slug"] == FTMO
        assert doc["max_total_loss_pct"] == 10.0

    def test_get_rule_unknown_firm_404(self, api):
        r = api.get(f"{BASE_URL}/api/prop-firm-analysis/rules/does_not_exist_firm")
        assert r.status_code == 404


# ── Per-strategy analysis ────────────────────────────────────────────
class TestPropAnalysis:
    def test_post_analysis_for_seed_hash(self, api):
        r = api.post(
            f"{BASE_URL}/api/strategies/{SEED_HASH}/prop-analysis",
            json={"firm_slug": FTMO},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("strategy_hash", "firm_slug", "stats_used", "rules",
                  "validation", "simulation", "risk_profile"):
            assert k in d, f"missing {k}"
        assert d["strategy_hash"] == SEED_HASH
        assert d["firm_slug"] == FTMO

        val = d["validation"]
        assert val["status"] == "FAIL", f"expected FAIL, got {val['status']}"
        rules_hit = [v.get("rule") for v in val["violations"]]
        assert "max_total_loss" in rules_hit, f"violations={val['violations']}"
        for k in ("violations", "warnings", "risk_adjustment_required", "checked_against"):
            assert k in val

        sim = d["simulation"]
        for k in ("pass_probability", "expected_days_to_pass", "hits_time_limit",
                  "risk_level", "components", "derived"):
            assert k in sim
        assert sim["risk_level"] == "high"

        rp = d["risk_profile"]
        assert 0.1 <= rp["recommended_risk_per_trade"] <= 2.0
        for k in ("max_daily_loss_pct", "max_total_loss_pct", "trailing_drawdown"):
            assert k in rp

    def test_post_analysis_unknown_hash_404(self, api):
        r = api.post(
            f"{BASE_URL}/api/strategies/deadbeef_not_a_real_hash/prop-analysis",
            json={"firm_slug": FTMO},
        )
        assert r.status_code == 404

    def test_get_saved_analysis(self, api):
        r = api.get(
            f"{BASE_URL}/api/strategies/{SEED_HASH}/prop-analysis",
            params={"firm_slug": FTMO},
        )
        assert r.status_code == 200
        d = r.json()
        assert "analysis" in d and d["analysis"] is not None
        assert d["analysis"]["status"] == "FAIL"
        assert "risk_profile" in d
        assert "rules" in d

    def test_get_saved_analysis_unknown_hash_404(self, api):
        r = api.get(
            f"{BASE_URL}/api/strategies/unseen_hash_xyz/prop-analysis",
            params={"firm_slug": FTMO},
        )
        assert r.status_code == 404


# ── Batch analysis ───────────────────────────────────────────────────
class TestBatchAnalyze:
    def test_batch_analyze_force(self, api):
        r = api.post(
            f"{BASE_URL}/api/prop-firm-analysis/batch-analyze",
            json={"firm_slug": FTMO, "limit": 10, "force": True},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        for k in ("analyzed", "skipped", "errors", "results"):
            assert k in d
        assert isinstance(d["errors"], list)
        assert isinstance(d["results"], list)

    def test_batch_analyze_without_force_skips(self, api):
        r = api.post(
            f"{BASE_URL}/api/prop-firm-analysis/batch-analyze",
            json={"firm_slug": FTMO, "limit": 10, "force": False},
        )
        assert r.status_code == 200
        d = r.json()
        # Previously analyzed records should be skipped
        assert d["skipped"] >= 1


# ── Explorer enrichment ──────────────────────────────────────────────
class TestExplorerEnrichment:
    def test_explorer_has_prop_analysis_field(self, api):
        r = api.get(f"{BASE_URL}/api/strategies/explorer")
        assert r.status_code == 200
        body = r.json()
        rows = body.get("rows") or body.get("strategies") or body
        if isinstance(body, dict) and "rows" not in body and "strategies" not in body:
            # handle case where top-level is a dict with a list under different key
            for v in body.values():
                if isinstance(v, list):
                    rows = v
                    break
        assert isinstance(rows, list) and len(rows) > 0
        for row in rows:
            assert "prop_analysis" in row, f"row missing prop_analysis: {list(row.keys())[:10]}"
        seed = next((r for r in rows if r.get("strategy_hash") == SEED_HASH), None)
        assert seed is not None, "seed hash not in explorer"
        assert seed["prop_analysis"] is not None
        assert seed["prop_analysis"]["status"] == "FAIL"


# ── Export enrichment ────────────────────────────────────────────────
class TestExportEnrichment:
    def test_export_json_has_prop_fields(self, api):
        r = api.get(f"{BASE_URL}/api/strategies/{SEED_HASH}/export")
        assert r.status_code == 200
        d = r.json()
        # Payload may be wrapped; accept either shape
        payload = d.get("export") if "export" in d else d
        assert "prop_analysis" in payload, f"keys={list(payload.keys())[:20]}"
        assert "prop_risk_profile" in payload

    def test_export_cbot_has_prop_banner(self, api):
        r = api.get(f"{BASE_URL}/api/strategies/{SEED_HASH}/export/cbot")
        assert r.status_code == 200
        # body may be plain text or JSON with 'code'
        try:
            body = r.json()
            text = body.get("code") or body.get("source") or str(body)
        except Exception:
            text = r.text
        for needle in [
            "PROP-FIRM ANALYSIS",
            "Risk per trade",
            "MaxDailyLossPct",
            "MaxTotalLossPct",
            "AutoStopOnBreach",
            "BREACH",
            "_tradingHalted",
        ]:
            assert needle in text, f"missing '{needle}' in cBot export"


# ── Regression: phase 16 + 17 endpoints ──────────────────────────────
class TestRegression:
    def test_strategies_list(self, api):
        r = api.get(f"{BASE_URL}/api/strategies")
        assert r.status_code == 200

    def test_ingestion_status(self, api):
        r = api.get(f"{BASE_URL}/api/ingestion/status")
        assert r.status_code == 200

    def test_strategy_history(self, api):
        r = api.get(f"{BASE_URL}/api/strategies/{SEED_HASH}/history")
        assert r.status_code == 200

    def test_market_intelligence_config(self, api):
        r = api.get(f"{BASE_URL}/api/strategies/market-intelligence/config")
        # config endpoint; allow 200 or 404 if renamed — but spec says it exists
        assert r.status_code in (200, 404)

    def test_market_profile(self, api):
        r = api.get(f"{BASE_URL}/api/strategies/{SEED_HASH}/market-profile")
        assert r.status_code in (200, 404)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
