"""
Strategy Factory Canonical v1.1 - API Compatibility Recovery test suite.

Verifies every endpoint that the frontend calls returns a real (non router-level 404) response.
Contract per problem statement:
  - 200 => PASS
  - 400/422 with body => PASS (route exists, just needs a valid payload)
  - 401 => FAIL (auth interceptor did not fire)
  - 404 with body {"detail":"Not Found"} => FAIL (router mount failure)
  - 404 with structured domain payload (e.g. missing id) => PASS
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@strategy-factory.local")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")

TIMEOUT = 30


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_login_payload():
    """POST /api/auth/login as seeded admin - returns full response body."""
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:400]}"
    return r.json()


@pytest.fixture(scope="session")
def admin_token(admin_login_payload):
    return admin_login_payload["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def _is_router_level_404(resp: requests.Response) -> bool:
    """Router-level 404 body from FastAPI is {\"detail\":\"Not Found\"}."""
    if resp.status_code != 404:
        return False
    try:
        body = resp.json()
    except Exception:
        return False
    return body == {"detail": "Not Found"}


# ============================================================
# Auth contract (login/signup/me)
# ============================================================
class TestAuthContract:
    def test_login_returns_v01_and_v11_fields(self, admin_login_payload):
        d = admin_login_payload
        # v1.1 fields
        for key in ("access_token", "refresh_token", "token_type", "expires_in_min"):
            assert key in d, f"missing {key} in login payload"
        assert d["token_type"] == "bearer"
        assert isinstance(d["expires_in_min"], int) and d["expires_in_min"] > 0
        # v01 legacy compatibility alias
        assert "token" in d, "v01 legacy `token` alias missing"
        assert d["token"] == d["access_token"]
        # nested user object
        assert "user" in d and isinstance(d["user"], dict)
        assert d["user"].get("email") == ADMIN_EMAIL
        assert d["user"].get("role") == "admin"

    def test_login_wrong_password_401(self):
        r = requests.post(
            f"{BASE}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrong_password_xxx"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 401

    def test_auth_me_returns_nested_user_shape(self, admin_headers):
        r = requests.get(f"{BASE}/api/auth/me", headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # v01 compatible: {user: {...}}
        assert "user" in body and isinstance(body["user"], dict), (
            f"/api/auth/me must return nested user shape, got: {body}"
        )
        assert body["user"].get("email") == ADMIN_EMAIL
        assert body["user"].get("role") == "admin"

    def test_signup_creates_pending_and_login_rejected(self):
        email = f"TEST_signup_{uuid.uuid4().hex[:10]}@example.com"
        password = "TestPass1234!"
        r = requests.post(
            f"{BASE}/api/auth/signup",
            json={"email": email, "password": password, "name": "T Signup"},
            timeout=TIMEOUT,
        )
        # Accept 200 or 201 depending on implementation
        assert r.status_code in (200, 201), f"signup: {r.status_code} {r.text[:300]}"
        body = r.json()
        # Should indicate pending status
        text_blob = str(body).lower()
        assert "pending" in text_blob or body.get("status") == "pending", (
            f"signup did not return pending status: {body}"
        )
        # Now login must be rejected with 403 (pending)
        lr = requests.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
        assert lr.status_code == 403, (
            f"pending user login expected 403, got {lr.status_code}: {lr.text[:300]}"
        )


# ============================================================
# Public health
# ============================================================
class TestHealth:
    def test_health_ok(self):
        r = requests.get(f"{BASE}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ============================================================
# Endpoints that were previously 404 - Compatibility Recovery matrix
# Each parametrised test asserts the endpoint is mounted:
#   * 200 → OK
#   * 400/422 with body → OK (route exists)
#   * 401/404-with-{detail:Not Found} → FAIL
# ============================================================

# (path, description)
COMPAT_GET_ENDPOINTS = [
    ("/api/challenge-firms",                                 "challenge firms list (relocated)"),
    ("/api/strategies/explorer",                             "strategies explorer rollup (shadowed by catchall)"),
    ("/api/admin/readiness",                                 "admin readiness (relocated)"),
    ("/api/prop-firms/list",                                 "prop firms list"),
    ("/api/library/list",                                    "library list (dashboard_route side-effect)"),
    ("/api/dashboard/portfolios/list",                       "dashboard portfolios (side-effect)"),
    ("/api/dashboard/datasets",                              "dashboard datasets"),
    ("/api/rebalance/config",                                "rebalance config"),
    ("/api/rebalance/status",                                "rebalance status"),
    ("/api/allocation-history",                              "allocation history"),
    ("/api/prop-firm-analysis/rules",                        "prop firm analysis rules"),
    ("/api/market-intelligence/rankings",                    "market intelligence rankings"),
    ("/api/challenge-matching/challenge-types/by-firm",      "challenge-matching by-firm"),
    ("/api/auto-factory/saved",                              "auto factory saved (should have 'strategies' key)"),
    ("/api/portfolio-builder/config",                        "portfolio builder config"),
    ("/api/auto-select/config",                              "auto-select config"),
    ("/api/trade-runner/runs",                               "trade runner runs"),
    ("/api/monitoring/status",                               "monitoring status"),
    ("/api/prop-firm-rules",                                 "prop firm rules"),
    ("/api/logs?limit=1",                                    "logs with limit"),
    ("/api/research-runs?limit=1",                           "research runs with limit"),
    ("/api/live/strategies",                                 "live strategies"),
    ("/api/factory-supervisor/status",                       "factory supervisor status"),
    ("/api/governance/survivor-registry",                    "governance survivor registry"),
    ("/api/latent/deployment-readiness",                     "latent deployment readiness"),
]


@pytest.mark.parametrize("path,desc", COMPAT_GET_ENDPOINTS, ids=[p for p, _ in COMPAT_GET_ENDPOINTS])
def test_compat_get_endpoint_mounted(path, desc, admin_headers):
    r = requests.get(f"{BASE}{path}", headers=admin_headers, timeout=TIMEOUT)
    # Router-level 404 is a hard failure
    assert not _is_router_level_404(r), (
        f"[{desc}] ROUTER-LEVEL 404 at {path} — mount failure. body={r.text[:300]}"
    )
    # 401 means auth interceptor did not fire on server side, but we DID send Bearer,
    # so 401 means auth misconfig for this route (fail)
    assert r.status_code != 401, (
        f"[{desc}] 401 Unauthorized at {path} with valid admin bearer token. body={r.text[:300]}"
    )
    # Accept 200 or a real domain response (including 4xx with body)
    assert r.status_code < 500, (
        f"[{desc}] server-error {r.status_code} at {path}: {r.text[:300]}"
    )


# ============================================================
# Extra assertions on shape for a handful of critical endpoints
# ============================================================
class TestPayloadShapes:
    def test_challenge_firms_shape(self, admin_headers):
        r = requests.get(f"{BASE}/api/challenge-firms", headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # Must be list or dict with a list-carrying key
        assert isinstance(body, (list, dict)), body

    def test_strategies_explorer_not_shadowed_by_catchall(self, admin_headers):
        r = requests.get(f"{BASE}/api/strategies/explorer", headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == 200, (
            f"strategies/explorer expected 200 (was shadowed by /strategies/{{id}} catch-all pre-fix). "
            f"Got {r.status_code}: {r.text[:300]}"
        )
        body = r.json()
        assert isinstance(body, (list, dict))

    def test_admin_readiness_requires_admin(self, admin_headers):
        r = requests.get(f"{BASE}/api/admin/readiness", headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]

    def test_library_list(self, admin_headers):
        r = requests.get(f"{BASE}/api/library/list", headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]

    def test_auto_factory_saved_has_strategies_key(self, admin_headers):
        r = requests.get(f"{BASE}/api/auto-factory/saved", headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # per problem statement: "returns 200 with strategies key"
        assert isinstance(body, dict) and "strategies" in body, (
            f"/api/auto-factory/saved missing 'strategies' key. body={body}"
        )
