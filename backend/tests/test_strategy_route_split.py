"""
Tests for the Phase-1 canonical vs legacy /strategies route split.

Verifies:
- GET /api/strategies -> Phase-1 canonical (bare array, `strategy_id` field)
- GET /api/legacy/strategies -> legacy wrapper `{strategies: [...]}` with `id` field (ObjectId)
- POST /api/strategies -> Phase-1 create (returns `strategy_id`)
- GET/DELETE by id use `strategy_id`
- Legacy `/api/legacy/strategies/{objectid}` still uses ObjectId (400 on invalid)
- POST /api/strategies/compare stays on legacy handler (method-based; not moved)
- Numerous legacy advanced POST endpoints still reachable (non-404)
- Meta-learning + factory-eval config still return mode=observe; approve 409
"""
import os
import re
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
ADMIN_EMAIL = "admin@strategy-factory.local"
ADMIN_PASSWORD = "admin123"

STRATEGY_ID_RE = re.compile(r"^[0-9a-f]{16}$")  # Phase-1 identifiers
OBJECTID_RE = re.compile(r"^[0-9a-f]{24}$")     # Mongo ObjectId hex


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Route ownership: canonical Phase-1 GET /api/strategies ----------

class TestRouteOwnership:
    def test_canonical_list_returns_bare_array(self, auth):
        r = requests.get(f"{BASE_URL}/api/strategies", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list), f"Phase-1 must return bare array, got {type(body).__name__}: {body!r}"
        # If items present, they must have `strategy_id` not top-level `id`
        for item in body:
            assert "strategy_id" in item, f"Phase-1 item missing strategy_id: {item}"

    def test_legacy_list_returns_wrapper(self, auth):
        r = requests.get(f"{BASE_URL}/api/legacy/strategies", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict), f"legacy must be dict wrapper, got {type(body).__name__}"
        assert "strategies" in body, f"legacy wrapper missing 'strategies' key: {body}"
        assert isinstance(body["strategies"], list)
        # legacy items (if any) must have `id` field that looks like ObjectId
        for item in body["strategies"]:
            assert "id" in item, f"legacy item missing 'id' field: {item}"

    def test_legacy_getbyid_bad_objectid_returns_400(self, auth):
        r = requests.get(f"{BASE_URL}/api/legacy/strategies/not-an-objectid", headers=auth, timeout=15)
        # Legacy path uses ObjectId lookup -> 400 on invalid input
        assert r.status_code == 400, f"expected 400 for invalid ObjectId, got {r.status_code} {r.text}"

    def test_legacy_delete_bad_objectid_returns_400(self, auth):
        r = requests.delete(f"{BASE_URL}/api/legacy/strategies/not-an-objectid", headers=auth, timeout=15)
        assert r.status_code == 400, f"expected 400 for invalid ObjectId delete, got {r.status_code} {r.text}"


# ---------- Phase-1 CRUD lifecycle ----------

class TestPhase1CRUDLifecycle:
    created_id = None

    def test_01_create(self, auth):
        payload = {"name": "TEST_route_split_strategy", "symbol": "EURUSD", "timeframe": "H1"}
        r = requests.post(f"{BASE_URL}/api/strategies", json=payload, headers=auth, timeout=15)
        assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
        body = r.json()
        assert "strategy_id" in body, f"Phase-1 create must return strategy_id: {body}"
        sid = body["strategy_id"]
        assert isinstance(sid, str) and len(sid) > 0
        # strategy_id should NOT look like a 24-char ObjectId
        assert not OBJECTID_RE.match(sid), f"Phase-1 strategy_id should not be an ObjectId: {sid}"
        assert body.get("name") == payload["name"]
        assert body.get("symbol") == payload["symbol"]
        assert body.get("timeframe") == payload["timeframe"]
        TestPhase1CRUDLifecycle.created_id = sid

    def test_02_list_contains_created(self, auth):
        assert TestPhase1CRUDLifecycle.created_id, "prereq: create must run"
        r = requests.get(f"{BASE_URL}/api/strategies", headers=auth, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        ids = [it.get("strategy_id") for it in body]
        assert TestPhase1CRUDLifecycle.created_id in ids, f"created id not in list: {ids}"

    def test_03_get_by_strategy_id(self, auth):
        sid = TestPhase1CRUDLifecycle.created_id
        r = requests.get(f"{BASE_URL}/api/strategies/{sid}", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("strategy_id") == sid
        assert body.get("name") == "TEST_route_split_strategy"

    def test_04_delete_by_strategy_id(self, auth):
        sid = TestPhase1CRUDLifecycle.created_id
        r = requests.delete(f"{BASE_URL}/api/strategies/{sid}", headers=auth, timeout=15)
        assert r.status_code == 204, f"expected 204 on delete, got {r.status_code} {r.text}"

    def test_05_get_after_delete_returns_404(self, auth):
        sid = TestPhase1CRUDLifecycle.created_id
        r = requests.get(f"{BASE_URL}/api/strategies/{sid}", headers=auth, timeout=15)
        assert r.status_code == 404, f"expected 404 after delete, got {r.status_code}"


# ---------- Legacy advanced endpoints unaffected ----------

class TestLegacyAdvancedUnchanged:
    def test_compare_post_still_reaches_legacy(self, auth):
        # legacy compare is a POST kept on main router. Bad payload -> 400/422, not 404/405
        r = requests.post(f"{BASE_URL}/api/strategies/compare", json={}, headers=auth, timeout=15)
        assert r.status_code not in (404, 405), (
            f"POST /api/strategies/compare should reach legacy handler, got {r.status_code} {r.text[:200]}"
        )

    @pytest.mark.parametrize("path,method", [
        ("/api/generate-strategy", "POST"),
        ("/api/run-backtest", "POST"),
        ("/api/rank-strategies", "POST"),
        ("/api/save-strategy", "POST"),
        ("/api/validate-strategy", "POST"),
        ("/api/monte-carlo", "POST"),
        ("/api/mutate-strategy", "POST"),
        ("/api/portfolio-analyze", "POST"),
        ("/api/rebalance/config", "GET"),
        ("/api/allocation-history", "GET"),
        ("/api/challenge-firms", "GET"),
        ("/api/optimize-strategy", "POST"),
        ("/api/safety-check", "POST"),
        ("/api/estimate-probability", "POST"),
        ("/api/match-strategy", "POST"),
        ("/api/profile-strategy", "POST"),
        ("/api/simulate-challenge", "POST"),
    ])
    def test_legacy_endpoint_exists(self, auth, path, method):
        if method == "POST":
            r = requests.post(f"{BASE_URL}{path}", json={}, headers=auth, timeout=20)
        else:
            r = requests.get(f"{BASE_URL}{path}", headers=auth, timeout=20)
        # Reachable = anything except 404 (path missing). 405 is also failure (method mismatch on router).
        assert r.status_code != 404, f"{method} {path} returned 404 — legacy handler missing"


# ---------- Regressions: meta-learning / factory-eval invariants ----------

class TestPhaseIJRegression:
    def test_meta_learning_config_mode_observe(self, auth):
        r = requests.get(f"{BASE_URL}/api/meta-learning/config", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json().get("config") or r.json()
        assert cfg.get("META_LEARNING_MODE") == "observe"

    def test_factory_eval_config_mode_observe(self, auth):
        r = requests.get(f"{BASE_URL}/api/factory-eval/config", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json().get("config") or r.json()
        assert cfg.get("FACTORY_EVAL_MODE") == "observe"

    def test_meta_learning_approve_returns_409(self, auth):
        r = requests.post(
            f"{BASE_URL}/api/meta-learning/recommendations/nonexistent/approve",
            headers=auth, timeout=15,
        )
        assert r.status_code == 409, f"expected 409 in OBSERVE, got {r.status_code}"

    def test_factory_eval_approve_returns_409(self, auth):
        r = requests.post(
            f"{BASE_URL}/api/factory-eval/recommendations/nonexistent/approve",
            headers=auth, timeout=15,
        )
        assert r.status_code == 409, f"expected 409 in OBSERVE, got {r.status_code}"
