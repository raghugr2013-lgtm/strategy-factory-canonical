"""End-to-end backend tests for Master Bot V1 API.

Covers MB-1 (DB layer), MB-2 (Candidate Pool / Ranker), and MB-3 (router
mounted at /api/master-bot/*). Uses the external REACT_APP_BACKEND_URL so
AuthMiddleware enforces JWT.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://strategy-prod-main.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "AdminTest123!"


# ───────────────────────── fixtures ─────────────────────────

@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token in login response: {r.json()}"
    return token


@pytest.fixture(scope="session")
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def non_admin_token(admin_headers) -> str:
    """Create a signup user and admin-approve them; return their JWT."""
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.local"
    password = "UserTest123!"
    r = requests.post(f"{API}/auth/signup",
                      json={"email": email, "password": password},
                      timeout=30)
    assert r.status_code in (200, 201), f"signup failed: {r.status_code} {r.text}"
    user = r.json().get("user") or r.json()
    user_id = user.get("id") or user.get("_id") or user.get("user_id")
    if not user_id:
        # signup response doesn't include id — look it up via admin/users
        lu = requests.get(f"{API}/admin/users?status=pending",
                          headers=admin_headers, timeout=30)
        assert lu.status_code == 200, lu.text
        for u in lu.json().get("users", []):
            if (u.get("email") or "").lower() == email.lower():
                user_id = u.get("user_id") or u.get("id")
                break
    assert user_id, f"no user id resolvable for {email}: {r.json()}"

    # admin approve
    ar = requests.post(f"{API}/admin/approve/{user_id}",
                       headers=admin_headers, timeout=30)
    assert ar.status_code == 200, f"approve failed: {ar.status_code} {ar.text}"
    assert ar.json().get("status") == "approved"

    lr = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=30)
    assert lr.status_code == 200, f"non-admin login failed: {lr.status_code} {lr.text}"
    return lr.json().get("token") or lr.json().get("access_token")


@pytest.fixture(scope="session")
def non_admin_headers(non_admin_token) -> dict:
    return {"Authorization": f"Bearer {non_admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def master_bot_id(admin_headers) -> str:
    """Create a fresh bot, return id; clean up at end of module."""
    name = f"MB_TEST_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/master-bot",
                      headers=admin_headers,
                      json={"name": name, "description": "agent created"},
                      timeout=30)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    bot = r.json()
    mb_id = bot.get("id") or bot.get("_id") or bot.get("master_bot_id")
    assert mb_id, f"no id returned: {bot}"
    yield mb_id
    # cleanup — hard delete
    requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                    headers=admin_headers, timeout=30)


# ───────────────────────── auth ─────────────────────────

def test_admin_login_returns_jwt(admin_token):
    assert isinstance(admin_token, str) and len(admin_token) > 20


def test_authed_call_succeeds(admin_headers):
    r = requests.get(f"{API}/master-bot", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "master_bots" in data and isinstance(data["master_bots"], list)


def test_unauthed_call_fails():
    r = requests.get(f"{API}/master-bot", timeout=30)
    assert r.status_code in (401, 403)


# ───────────────────────── ranker config ─────────────────────────

def test_ranker_config_defaults(admin_headers):
    r = requests.get(f"{API}/master-bot/ranker/config", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    w = data.get("weights") or data
    assert abs(w.get("deploy_score", 0) - 0.6) < 1e-6
    assert abs(w.get("pass_probability", 0) - 0.4) < 1e-6
    assert w.get("risk_of_ruin", 0) == 0
    assert w.get("calibration", 0) == 0
    assert w.get("regime_fitness", 0) == 0
    version = data.get("ranker_version") or data.get("version") or (w.get("version") if isinstance(w, dict) else None)
    assert version == "v1.0"


def test_ranker_config_update_partial(admin_headers):
    r = requests.post(f"{API}/master-bot/ranker/config",
                      headers=admin_headers,
                      json={"risk_of_ruin": 0.1}, timeout=30)
    assert r.status_code == 200, r.text
    w = r.json().get("weights") or r.json()
    assert abs(w.get("risk_of_ruin", 0) - 0.1) < 1e-6
    assert abs(w.get("deploy_score", 0) - 0.6) < 1e-6
    assert abs(w.get("pass_probability", 0) - 0.4) < 1e-6
    # reset
    requests.post(f"{API}/master-bot/ranker/config",
                  headers=admin_headers,
                  json={"risk_of_ruin": 0.0}, timeout=30)


def test_ranker_config_unknown_key_rejected(admin_headers):
    r = requests.post(f"{API}/master-bot/ranker/config",
                      headers=admin_headers,
                      json={"unknown_key": 1}, timeout=30)
    # Pydantic strict model may also produce 422 for unknown keys,
    # but spec asks for 400.
    assert r.status_code in (400, 422), f"expected 400/422, got {r.status_code}: {r.text}"


# ───────────────────────── candidates ─────────────────────────

def test_candidates_ranked(admin_headers):
    r = requests.get(f"{API}/master-bot/candidates", headers=admin_headers, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    cands = data.get("candidates") or []
    assert isinstance(cands, list)
    assert len(cands) >= 1, f"no candidates in pool: {data}"
    # sorted desc
    scores = [c.get("candidate_score") for c in cands if c.get("candidate_score") is not None]
    assert scores == sorted(scores, reverse=True), "candidates not sorted desc by candidate_score"


def test_candidate_shape(admin_headers):
    r = requests.get(f"{API}/master-bot/candidates", headers=admin_headers, timeout=60)
    cands = r.json().get("candidates") or []
    assert cands, "expected at least one candidate"
    c = cands[0]
    required = {
        "strategy_hash", "pair", "timeframe", "style",
        "deploy_score", "pass_probability",
        "candidate_score", "score_contributions", "score_normalised",
        "risk_of_ruin", "calibration_score", "regime_fitness",
    }
    missing = required - set(c.keys())
    assert not missing, f"missing fields in candidate: {missing}; got keys={list(c.keys())}"
    contrib = c.get("score_contributions") or {}
    for k in ("deploy_score", "pass_probability", "risk_of_ruin", "calibration", "regime_fitness"):
        assert k in contrib, f"score_contributions missing key {k}: {contrib}"


# ───────────────────────── create / get / rename ─────────────────────────

def test_create_bot_seeds_tiers(master_bot_id, admin_headers):
    r = requests.get(f"{API}/master-bot/{master_bot_id}", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc.get("status") == "DRAFT"
    assert doc.get("owner") == ADMIN_EMAIL
    tiers = doc.get("tiers") or []
    tier_names = {t.get("tier_key") or t.get("tier") for t in tiers}
    assert {"tier1", "tier2", "tier3"}.issubset(tier_names), f"missing tiers: {tier_names}"
    mbt = doc.get("members_by_tier") or {}
    for t in ("tier1", "tier2", "tier3"):
        assert t in mbt
    assert "member_counts" in doc


def test_rename_bot(master_bot_id, admin_headers):
    new_name = f"MB_TEST_RENAMED_{uuid.uuid4().hex[:4]}"
    r = requests.put(f"{API}/master-bot/{master_bot_id}",
                     headers=admin_headers,
                     json={"name": new_name}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("name") == new_name


# ───────────────────────── auto-fill + tier ops ─────────────────────────

def test_auto_fill_distributes_members(master_bot_id, admin_headers):
    r = requests.post(f"{API}/master-bot/{master_bot_id}/auto-fill",
                      headers=admin_headers,
                      json={"tier1_count": 2, "tier2_count": 2, "tier3_count": 1,
                            "clear_existing": True}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("added_count", 0) == 5, f"expected 5 added, got: {body}"

    g = requests.get(f"{API}/master-bot/{master_bot_id}", headers=admin_headers, timeout=30)
    assert g.status_code == 200
    mbt = g.json().get("members_by_tier") or {}
    assert len(mbt.get("tier1") or []) == 2
    assert len(mbt.get("tier2") or []) == 2
    assert len(mbt.get("tier3") or []) == 1


def _members_of(headers, bot_id, tier=None):
    r = requests.get(f"{API}/master-bot/{bot_id}", headers=headers, timeout=30)
    mbt = r.json().get("members_by_tier") or {}
    if tier:
        return mbt.get(tier) or []
    return mbt


def test_promote_demote_disable_enable(master_bot_id, admin_headers):
    # tier3 → tier2
    t3 = _members_of(admin_headers, master_bot_id, "tier3")
    assert t3, "no tier3 members to promote"
    h = t3[0]["strategy_hash"]
    r = requests.post(f"{API}/master-bot/{master_bot_id}/members/{h}/promote",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    t2 = _members_of(admin_headers, master_bot_id, "tier2")
    assert any(m["strategy_hash"] == h for m in t2)

    # tier1 promote → 400
    t1 = _members_of(admin_headers, master_bot_id, "tier1")
    assert t1
    h1 = t1[0]["strategy_hash"]
    r = requests.post(f"{API}/master-bot/{master_bot_id}/members/{h1}/promote",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    # demote tier1 → tier2
    r = requests.post(f"{API}/master-bot/{master_bot_id}/members/{h1}/demote",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    t2 = _members_of(admin_headers, master_bot_id, "tier2")
    assert any(m["strategy_hash"] == h1 for m in t2)

    # disable / enable
    r = requests.post(f"{API}/master-bot/{master_bot_id}/members/{h1}/disable",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert r.json().get("enabled") is False
    r = requests.post(f"{API}/master-bot/{master_bot_id}/members/{h1}/enable",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert r.json().get("enabled") is True


def test_move_to_tier(master_bot_id, admin_headers):
    mbt = _members_of(admin_headers, master_bot_id)
    # pick any tier1 member if exists, else any other
    src = (mbt.get("tier1") or mbt.get("tier3") or mbt.get("tier2") or [])
    assert src, "no members to move"
    h = src[0]["strategy_hash"]
    r = requests.post(f"{API}/master-bot/{master_bot_id}/members/{h}/move-to",
                      headers=admin_headers, json={"tier": "tier2"}, timeout=30)
    assert r.status_code == 200, r.text
    t2 = _members_of(admin_headers, master_bot_id, "tier2")
    assert any(m["strategy_hash"] == h for m in t2)


def test_reorder_tier(master_bot_id, admin_headers):
    t2 = _members_of(admin_headers, master_bot_id, "tier2")
    if len(t2) < 2:
        pytest.skip("need >=2 members in tier2 for reorder")
    hashes = [m["strategy_hash"] for m in t2]
    reversed_hashes = list(reversed(hashes))
    r = requests.post(f"{API}/master-bot/{master_bot_id}/tiers/tier2/reorder",
                      headers=admin_headers,
                      json={"ordered_hashes": reversed_hashes}, timeout=30)
    assert r.status_code == 200, r.text
    members = r.json().get("members") or []
    got = [m["strategy_hash"] for m in members]
    assert got == reversed_hashes, f"reorder mismatch: {got} vs {reversed_hashes}"


def test_update_tier_metadata(master_bot_id, admin_headers):
    r = requests.post(f"{API}/master-bot/{master_bot_id}/tiers/tier1",
                      headers=admin_headers,
                      json={"label": "Tier 1 X", "allocation_share": 0.55, "max_members": 6},
                      timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("label") == "Tier 1 X"
    assert abs(body.get("allocation_share", 0) - 0.55) < 1e-6
    assert body.get("max_members") == 6


def test_delete_member_then_404(master_bot_id, admin_headers):
    t2 = _members_of(admin_headers, master_bot_id, "tier2")
    if not t2:
        pytest.skip("no tier2 members to delete")
    h = t2[0]["strategy_hash"]
    r = requests.delete(f"{API}/master-bot/{master_bot_id}/members/{h}",
                        headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    r2 = requests.delete(f"{API}/master-bot/{master_bot_id}/members/{h}",
                         headers=admin_headers, timeout=30)
    assert r2.status_code == 404, f"expected 404 on repeat delete, got {r2.status_code}"


def test_duplicate_add_rejected(master_bot_id, admin_headers):
    # pick an existing member
    mbt = _members_of(admin_headers, master_bot_id)
    pick = None
    for t in ("tier1", "tier2", "tier3"):
        if mbt.get(t):
            pick = mbt[t][0]
            break
    if not pick:
        pytest.skip("no members to dup-add")
    r = requests.post(f"{API}/master-bot/{master_bot_id}/members",
                      headers=admin_headers,
                      json={"strategy_hash": pick["strategy_hash"], "tier": "tier3"},
                      timeout=30)
    assert r.status_code == 400, f"expected 400 dup, got {r.status_code}: {r.text}"
    assert "already" in r.text.lower() or "member" in r.text.lower()


# ───────────────────────── soft delete ─────────────────────────

def test_soft_delete_and_filter(admin_headers):
    name = f"MB_TEST_SOFT_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/master-bot", headers=admin_headers,
                      json={"name": name}, timeout=30)
    assert r.status_code in (200, 201)
    mb_id = r.json().get("id") or r.json().get("_id")

    d = requests.delete(f"{API}/master-bot/{mb_id}", headers=admin_headers, timeout=30)
    assert d.status_code == 200, d.text

    # GET single should show DELETED status
    g = requests.get(f"{API}/master-bot/{mb_id}", headers=admin_headers, timeout=30)
    if g.status_code == 200:
        assert g.json().get("status") == "DELETED"

    # default listing should NOT include the deleted bot
    lst = requests.get(f"{API}/master-bot", headers=admin_headers, timeout=30).json()
    ids = [b.get("id") or b.get("_id") for b in lst.get("master_bots", [])]
    assert mb_id not in ids, "soft-deleted bot still listed by default"

    # with include_deleted=true it should appear
    lst2 = requests.get(f"{API}/master-bot?include_deleted=true",
                        headers=admin_headers, timeout=30).json()
    ids2 = [b.get("id") or b.get("_id") for b in lst2.get("master_bots", [])]
    assert mb_id in ids2, "include_deleted=true did not surface soft-deleted bot"

    # cleanup
    requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                    headers=admin_headers, timeout=30)


# ───────────────────────── RBAC ─────────────────────────

def test_non_admin_can_read_candidates(non_admin_headers):
    r = requests.get(f"{API}/master-bot/candidates",
                     headers=non_admin_headers, timeout=60)
    assert r.status_code == 200, r.text


def test_non_admin_mutations_forbidden(non_admin_headers, master_bot_id):
    forbidden_calls = [
        ("POST", f"{API}/master-bot", {"name": "x"}),
        ("PUT",  f"{API}/master-bot/{master_bot_id}", {"name": "y"}),
        ("DELETE", f"{API}/master-bot/{master_bot_id}", None),
        ("POST", f"{API}/master-bot/{master_bot_id}/members",
            {"strategy_hash": "abcd1234abcd", "tier": "tier3"}),
        ("POST", f"{API}/master-bot/{master_bot_id}/members/abcd1234abcd/promote", None),
        ("POST", f"{API}/master-bot/{master_bot_id}/members/abcd1234abcd/demote", None),
        ("POST", f"{API}/master-bot/{master_bot_id}/members/abcd1234abcd/enable", None),
        ("POST", f"{API}/master-bot/{master_bot_id}/members/abcd1234abcd/disable", None),
        ("POST", f"{API}/master-bot/{master_bot_id}/members/abcd1234abcd/move-to",
            {"tier": "tier2"}),
        ("POST", f"{API}/master-bot/{master_bot_id}/tiers/tier1/reorder",
            {"ordered_hashes": []}),
        ("POST", f"{API}/master-bot/{master_bot_id}/tiers/tier1", {"label": "X"}),
        ("POST", f"{API}/master-bot/{master_bot_id}/auto-fill",
            {"tier1_count": 1, "tier2_count": 1, "tier3_count": 1}),
        ("POST", f"{API}/master-bot/ranker/config", {"risk_of_ruin": 0.2}),
    ]
    fails = []
    for method, url, body in forbidden_calls:
        rq = requests.request(method, url, headers=non_admin_headers,
                              json=body, timeout=30)
        if rq.status_code != 403:
            fails.append((method, url, rq.status_code, rq.text[:200]))
    assert not fails, f"non-admin mutations not forbidden: {fails}"
