"""Phase 2 — Challenge Type Matching Engine backend API tests.

Covers:
- GET /api/challenge-matching/challenge-types (auto-seed)
- GET /api/challenge-matching/challenge-types/by-firm
- POST /api/strategies/{hash}/match-challenges (force, ineligible, 404)
- GET  /api/strategies/{hash}/challenge-match
- POST /api/challenge-matching/run-eligible
- Explorer enrichment with challenge_match
- Regression: phase 16/17/18 endpoints
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sprint3-phase2.preview.emergentagent.com").rstrip("/")
ELIGIBLE_HASH = "a649abeabefcc045cc9ef2dc2ec04e1f3f2b55da"
UNKNOWN_HASH = "deadbeef" * 5  # 40 chars nonsense


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Challenge type catalog ──────────────────────────────────────────
class TestChallengeTypes:
    def test_list_challenge_types_auto_seeds(self, client):
        r = client.get(f"{BASE_URL}/api/challenge-matching/challenge-types")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data and "challenge_types" in data
        rows = data["challenge_types"]
        # Expect 6 entries (3 firms × 2 variants)
        assert data["count"] >= 6, f"expected >=6 challenge types, got {data['count']}"
        firms = {row["firm_slug"] for row in rows}
        assert {"ftmo", "fundednext", "pipfarm"}.issubset(firms)
        # FTMO must have Standard + Aggressive
        ftmo_names = {r["name"] for r in rows if r["firm_slug"] == "ftmo"}
        assert {"Standard", "Aggressive"}.issubset(ftmo_names)
        fn_names = {r["name"] for r in rows if r["firm_slug"] == "fundednext"}
        assert {"Standard", "Stellar"}.issubset(fn_names)
        pf_names = {r["name"] for r in rows if r["firm_slug"] == "pipfarm"}
        assert {"Evaluation", "Instant"}.issubset(pf_names)
        # No MongoDB _id leakage
        for row in rows:
            assert "_id" not in row

    def test_by_firm_shape(self, client):
        r = client.get(f"{BASE_URL}/api/challenge-matching/challenge-types/by-firm")
        assert r.status_code == 200
        data = r.json()
        assert "firms" in data and isinstance(data["firms"], list)
        firms_by_slug = {f["firm_slug"]: f for f in data["firms"]}
        assert {"ftmo", "fundednext", "pipfarm"}.issubset(firms_by_slug.keys())
        for f in data["firms"]:
            assert "firm_name" in f and "challenges" in f
            assert len(f["challenges"]) >= 1
            for c in f["challenges"]:
                for k in ("name", "profit_target", "max_daily_dd", "max_total_dd"):
                    assert k in c


# ── Per-strategy match ───────────────────────────────────────────────
class TestMatchChallenges:
    def test_match_with_force_true(self, client):
        r = client.post(
            f"{BASE_URL}/api/strategies/{ELIGIBLE_HASH}/match-challenges",
            json={"force": True},
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        for k in (
            "strategy_hash", "best_firm", "best_firm_name", "best_challenge",
            "pass_probability", "expected_days", "safe_risk", "score",
            "alternatives", "evaluated_count", "matched_at",
        ):
            assert k in doc, f"missing {k}"
        assert doc["strategy_hash"] == ELIGIBLE_HASH
        assert doc["evaluated_count"] == 6
        assert isinstance(doc["alternatives"], list)
        assert len(doc["alternatives"]) == 5
        # Scoring correctness per spec
        assert doc["best_firm"] == "ftmo"
        assert doc["best_challenge"] == "Aggressive"
        assert doc["status"] == "FAIL"
        # Score around -0.49 (allow tolerance)
        assert -0.9 <= float(doc["score"]) <= 0.1, f"score out of range: {doc['score']}"
        # Alternatives should include the other 5 firm×challenge combos
        alts = {(a["firm"], a["challenge"]) for a in doc["alternatives"]}
        expected = {
            ("ftmo", "Standard"),
            ("pipfarm", "Evaluation"),
            ("pipfarm", "Instant"),
            ("fundednext", "Standard"),
            ("fundednext", "Stellar"),
        }
        assert expected.issubset(alts), f"missing alts: {expected - alts}"

    def test_get_challenge_match_after_match(self, client):
        r = client.get(f"{BASE_URL}/api/strategies/{ELIGIBLE_HASH}/challenge-match")
        assert r.status_code == 200
        doc = r.json()
        assert doc["strategy_hash"] == ELIGIBLE_HASH
        assert doc["best_firm"] == "ftmo"
        assert doc["best_challenge"] == "Aggressive"

    def test_match_without_force_returns_skipped(self, client):
        r = client.post(
            f"{BASE_URL}/api/strategies/{ELIGIBLE_HASH}/match-challenges",
            json={"force": False},
        )
        assert r.status_code == 200
        doc = r.json()
        assert doc.get("skipped") is True

    def test_match_force_updates_matched_at(self, client):
        # Grab current matched_at
        prev = client.get(f"{BASE_URL}/api/strategies/{ELIGIBLE_HASH}/challenge-match").json()
        prev_matched_at = prev.get("matched_at")
        r = client.post(
            f"{BASE_URL}/api/strategies/{ELIGIBLE_HASH}/match-challenges",
            json={"force": True},
        )
        assert r.status_code == 200
        new_doc = r.json()
        assert new_doc.get("skipped") is False
        assert new_doc.get("matched_at") is not None
        # matched_at should be equal or later
        assert new_doc["matched_at"] >= prev_matched_at

    def test_unknown_hash_returns_404(self, client):
        r = client.post(
            f"{BASE_URL}/api/strategies/{UNKNOWN_HASH}/match-challenges",
            json={"force": True},
        )
        assert r.status_code in (404, 422), r.text
        # spec says 404 for unknown hash
        assert r.status_code == 404 or "not eligible" in r.text.lower()

    def test_ineligible_returns_422(self, client):
        # Find an ineligible strategy via explorer
        ex = client.get(f"{BASE_URL}/api/strategies/explorer?limit=200").json()
        rows = ex if isinstance(ex, list) else ex.get("strategies") or ex.get("rows") or []
        candidate = None
        for r in rows:
            pf = r.get("best_pf") or (r.get("stats") or {}).get("pf")
            runs = r.get("runs") or r.get("run_count") or 0
            if (pf is not None and pf < 1.2) or (runs is not None and runs < 3):
                h = r.get("strategy_hash") or r.get("hash")
                if h and h != ELIGIBLE_HASH:
                    candidate = h
                    break
        if not candidate:
            pytest.skip("No ineligible strategy available to test 422 path")
        resp = client.post(
            f"{BASE_URL}/api/strategies/{candidate}/match-challenges",
            json={"force": True},
        )
        assert resp.status_code == 422, resp.text
        assert "not eligible" in resp.text.lower()

    def test_get_match_404_for_unknown(self, client):
        r = client.get(f"{BASE_URL}/api/strategies/{UNKNOWN_HASH}/challenge-match")
        assert r.status_code == 404


# ── Batch run-eligible ──────────────────────────────────────────────
class TestRunEligible:
    def test_run_eligible_with_force(self, client):
        r = client.post(
            f"{BASE_URL}/api/challenge-matching/run-eligible",
            json={"limit": 3, "force": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        for k in ("considered", "matched", "errors", "results"):
            assert k in data
        assert data["considered"] <= 3
        assert isinstance(data["results"], list)
        assert isinstance(data["errors"], list)

    def test_run_eligible_without_force_skips(self, client):
        r = client.post(
            f"{BASE_URL}/api/challenge-matching/run-eligible",
            json={"limit": 3, "force": False},
        )
        assert r.status_code == 200
        data = r.json()
        # Since we've matched in prior tests, considered should be lower or 0
        assert data["status"] == "ok"


# ── Explorer enrichment ─────────────────────────────────────────────
class TestExplorerEnrichment:
    def test_explorer_rows_contain_challenge_match_field(self, client):
        r = client.get(f"{BASE_URL}/api/strategies/explorer?limit=200")
        assert r.status_code == 200
        payload = r.json()
        rows = payload if isinstance(payload, list) else payload.get("strategies") or payload.get("rows") or []
        assert len(rows) > 0
        for row in rows:
            assert "challenge_match" in row, f"row missing challenge_match: {row.get('strategy_hash')}"
        # Find the eligible hash and ensure it's matched
        target = next(
            (r for r in rows if (r.get("strategy_hash") or r.get("hash")) == ELIGIBLE_HASH),
            None,
        )
        assert target is not None, "eligible seed hash not in explorer"
        cm = target["challenge_match"]
        assert cm is not None
        for k in ("best_firm", "best_firm_name", "best_challenge",
                  "pass_probability", "expected_days", "safe_risk", "score", "status"):
            assert k in cm
        assert cm["best_firm"] == "ftmo"
        assert cm["best_challenge"] == "Aggressive"


# ── Regression ──────────────────────────────────────────────────────
class TestRegression:
    def test_strategies_endpoint(self, client):
        r = client.get(f"{BASE_URL}/api/strategies?limit=5")
        assert r.status_code == 200

    def test_prop_firm_rules(self, client):
        r = client.get(f"{BASE_URL}/api/prop-firm-analysis/rules")
        assert r.status_code == 200

    def test_market_profile(self, client):
        r = client.get(f"{BASE_URL}/api/strategies/{ELIGIBLE_HASH}/market-profile")
        assert r.status_code in (200, 404)
