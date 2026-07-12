"""
Auth + Admin Approval System tests
Hits the EXTERNAL preview URL so the AuthMiddleware path is exercised
(local-loopback bypass would otherwise hide a lot of behavior).
"""
import os
import uuid
import pytest
import requests
import jwt as pyjwt

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback (testing inside pod) — read frontend/.env
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@strategyfactory.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    raise RuntimeError(
        "ADMIN_PASSWORD env var is required to run this test suite. "
        "Export it (matching the value in backend/.env) before invoking pytest."
    )


def _post(path, **kw):
    return requests.post(f"{BASE_URL}{path}", timeout=30, **kw)


def _get(path, **kw):
    return requests.get(f"{BASE_URL}{path}", timeout=30, **kw)


@pytest.fixture(scope="module")
def admin_token():
    r = _post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["role"] == "admin"
    return data["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def pending_user():
    """Signup a fresh test user; returns dict with email, password."""
    email = f"test_user_{uuid.uuid4().hex[:8]}@example.com"
    pw = "TestPass123!"
    r = _post("/api/auth/signup", json={"email": email, "password": pw})
    assert r.status_code == 200, f"signup failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["status"] == "pending"
    assert body["email"] == email
    return {"email": email, "password": pw}


# ─── Admin seed ──────────────────────────────────────────────────────
class TestAdminSeed:
    def test_admin_login_works(self, admin_token):
        # Token decodes & has role admin
        payload = pyjwt.decode(admin_token, options={"verify_signature": False})
        assert payload.get("role") == "admin"
        assert payload.get("email") == ADMIN_EMAIL

    def test_admin_in_users_list_with_bcrypt(self, admin_headers):
        r = _get("/api/admin/users", headers=admin_headers)
        assert r.status_code == 200
        users = r.json().get("users", [])
        admin = next((u for u in users if u["email"] == ADMIN_EMAIL), None)
        assert admin is not None
        assert admin["role"] == "admin"
        assert admin["status"] == "approved"
        # password_hash must NOT leak
        assert "password_hash" not in admin


# ─── Signup + Login flow ─────────────────────────────────────────────
class TestSignupLogin:
    def test_signup_creates_pending(self, pending_user):
        # already signed up via fixture — re-test duplicate
        r = _post("/api/auth/signup", json={
            "email": pending_user["email"],
            "password": pending_user["password"],
        })
        assert r.status_code == 409

    def test_login_pending_returns_403(self, pending_user):
        r = _post("/api/auth/login", json={
            "email": pending_user["email"],
            "password": pending_user["password"],
        })
        assert r.status_code == 403
        assert "approval" in r.text.lower() or "approved" in r.text.lower()

    def test_login_wrong_password_returns_401(self):
        r = _post("/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": "wrongpassword"
        })
        assert r.status_code == 401
        assert "invalid" in r.text.lower()


# ─── /auth/me ────────────────────────────────────────────────────────
class TestAuthMe:
    def test_me_with_token(self, admin_headers):
        r = _get("/api/auth/me", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["email"] == ADMIN_EMAIL
        assert "password_hash" not in body["user"]

    def test_me_without_token(self):
        r = _get("/api/auth/me")
        assert r.status_code == 401


# ─── Admin endpoints permission ──────────────────────────────────────
class TestAdminPermissions:
    def test_users_list_no_token_401(self):
        r = _get("/api/admin/users")
        assert r.status_code == 401

    def test_non_admin_user_gets_403(self, admin_headers, pending_user):
        # Approve user, login as them, then try to hit /admin/users
        # 1) get user_id
        users = _get("/api/admin/users", headers=admin_headers).json()["users"]
        target = next(u for u in users if u["email"] == pending_user["email"])
        uid = target["user_id"]

        # 2) approve
        r = _post(f"/api/admin/approve/{uid}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # 3) login as approved non-admin
        login = _post("/api/auth/login", json={
            "email": pending_user["email"], "password": pending_user["password"],
        })
        assert login.status_code == 200
        utoken = login.json()["token"]

        # 4) /admin/users → 403
        r = _get("/api/admin/users", headers={"Authorization": f"Bearer {utoken}"})
        assert r.status_code == 403


# ─── Approve / Reject flows ──────────────────────────────────────────
class TestApproveReject:
    def test_reject_flow_blocks_login(self, admin_headers):
        email = f"reject_{uuid.uuid4().hex[:6]}@example.com"
        pw = "Pass1234!"
        _post("/api/auth/signup", json={"email": email, "password": pw})

        users = _get("/api/admin/users", headers=admin_headers).json()["users"]
        uid = next(u["user_id"] for u in users if u["email"] == email)

        r = _post(f"/api/admin/reject/{uid}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

        # login should now return 403 with rejected message
        r = _post("/api/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 403
        assert "rejected" in r.text.lower()

    def test_reject_admin_returns_400(self, admin_headers):
        users = _get("/api/admin/users", headers=admin_headers).json()["users"]
        admin = next(u for u in users if u["email"] == ADMIN_EMAIL)
        r = _post(f"/api/admin/reject/{admin['user_id']}", headers=admin_headers)
        assert r.status_code == 400
        assert "admin" in r.text.lower()


# ─── External protection of existing routes ──────────────────────────
class TestExistingRoutesProtection:
    PROTECTED = [
        "/api/execution/paper/config",
        "/api/trade-runner/list",
        "/api/portfolio-builder/recent",
    ]

    def test_health_is_public(self):
        r = _get("/api/health")
        assert r.status_code in (200, 404)  # health may or may not exist

    @pytest.mark.parametrize("path", PROTECTED)
    def test_protected_without_token_401(self, path):
        r = _get(path)
        assert r.status_code == 401, f"{path} returned {r.status_code}, expected 401"

    @pytest.mark.parametrize("path", PROTECTED)
    def test_protected_with_token_not_401(self, path, admin_headers):
        r = _get(path, headers=admin_headers)
        # We don't enforce 200 (some endpoints may legitimately 404/422),
        # but they MUST NOT be 401 with a valid admin token.
        assert r.status_code != 401, (
            f"{path} returned 401 even with valid admin token: {r.text[:200]}"
        )
        assert r.status_code != 500, (
            f"{path} returned 500: {r.text[:300]}"
        )


# ─── Localhost bypass (run from inside pod) ──────────────────────────
class TestLocalhostBypass:
    def test_localhost_no_token_works(self):
        r = requests.get("http://localhost:8001/api/execution/paper/config", timeout=15)
        assert r.status_code != 401, (
            f"Localhost bypass not honored: {r.status_code} {r.text[:200]}"
        )
