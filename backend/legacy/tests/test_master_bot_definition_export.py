"""End-to-end backend tests for Master Bot V1 — MB-4 (Definition Engine)
and MB-7 (cBot Export Engine).

Re-uses admin credentials from /app/memory/test_credentials.md and the
test_master_bot_api.py patterns. Mounts at /api/master-bot/*.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://factory-v2-canonical.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "AdminTest123!"


# ───────────────────────── fixtures ─────────────────────────

@pytest.fixture(scope="session")
def admin_headers() -> dict:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"admin login: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def non_admin_headers(admin_headers) -> dict:
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.local"
    pw = "UserTest123!"
    r = requests.post(f"{API}/auth/signup",
                      json={"email": email, "password": pw}, timeout=30)
    assert r.status_code in (200, 201), r.text
    user_id = (r.json().get("user") or r.json()).get("id") \
        or (r.json().get("user") or r.json()).get("user_id")
    if not user_id:
        lu = requests.get(f"{API}/admin/users?status=pending",
                          headers=admin_headers, timeout=30)
        for u in lu.json().get("users", []):
            if (u.get("email") or "").lower() == email.lower():
                user_id = u.get("user_id") or u.get("id")
                break
    assert user_id
    ar = requests.post(f"{API}/admin/approve/{user_id}",
                       headers=admin_headers, timeout=30)
    assert ar.status_code == 200, ar.text
    lr = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": pw}, timeout=30)
    token = lr.json().get("token") or lr.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def existing_bot_with_members(admin_headers) -> str:
    """Find an existing master bot that has >=1 member (e.g. MB_DEV_01)."""
    r = requests.get(f"{API}/master-bot?limit=200", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    bots = r.json().get("master_bots") or []
    for b in bots:
        if b.get("status") == "DELETED":
            continue
        mc = b.get("member_counts") or {}
        if int(mc.get("total") or 0) > 0:
            return b.get("id")
    # If none, auto-fill a fresh bot from candidate pool
    name = f"MB_TEST_FILLED_{uuid.uuid4().hex[:6]}"
    cr = requests.post(f"{API}/master-bot", headers=admin_headers,
                       json={"name": name}, timeout=30)
    assert cr.status_code in (200, 201), cr.text
    mb_id = cr.json().get("id")
    fr = requests.post(f"{API}/master-bot/{mb_id}/auto-fill",
                       headers=admin_headers,
                       json={"tier1_count": 1, "tier2_count": 2, "tier3_count": 0},
                       timeout=30)
    assert fr.status_code == 200, fr.text
    return mb_id


@pytest.fixture(scope="module")
def empty_bot(admin_headers) -> str:
    """Create a fresh empty bot — used for negative validation tests."""
    name = f"MB_TEST_EMPTY_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/master-bot", headers=admin_headers,
                      json={"name": name}, timeout=30)
    assert r.status_code in (200, 201), r.text
    mb_id = r.json().get("id")
    yield mb_id
    requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                    headers=admin_headers, timeout=30)


@pytest.fixture(scope="module")
def soft_deleted_bot(admin_headers) -> str:
    name = f"MB_TEST_SOFTDEL_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/master-bot", headers=admin_headers,
                      json={"name": name}, timeout=30)
    assert r.status_code in (200, 201)
    mb_id = r.json().get("id")
    # add a member so it isn't empty
    fr = requests.post(f"{API}/master-bot/{mb_id}/auto-fill", headers=admin_headers,
                       json={"tier1_count": 1, "tier2_count": 0, "tier3_count": 0},
                       timeout=30)
    assert fr.status_code == 200, fr.text
    # soft delete
    dr = requests.delete(f"{API}/master-bot/{mb_id}",
                         headers=admin_headers, timeout=30)
    assert dr.status_code == 200, dr.text
    yield mb_id
    requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                    headers=admin_headers, timeout=30)


@pytest.fixture(scope="module")
def other_bot_with_members(admin_headers) -> str:
    """A SECOND filled bot so we can test cross-bot revision_id rejection."""
    name = f"MB_TEST_OTHER_{uuid.uuid4().hex[:6]}"
    cr = requests.post(f"{API}/master-bot", headers=admin_headers,
                       json={"name": name}, timeout=30)
    assert cr.status_code in (200, 201)
    mb_id = cr.json().get("id")
    fr = requests.post(f"{API}/master-bot/{mb_id}/auto-fill",
                       headers=admin_headers,
                       json={"tier1_count": 1, "tier2_count": 0, "tier3_count": 0},
                       timeout=30)
    assert fr.status_code == 200
    yield mb_id
    requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                    headers=admin_headers, timeout=30)


# ───────────────────────── MB-4: Compile ─────────────────────────

class TestCompile:
    def test_compile_multi_strategy_returns_revision(self, admin_headers, existing_bot_with_members):
        mb_id = existing_bot_with_members
        r = requests.post(f"{API}/master-bot/{mb_id}/compile",
                          headers=admin_headers,
                          json={"runtime_mode": "multi_strategy"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["rev"] >= 1
        assert d["definition_hash"].startswith("sha256:")
        assert len(d["revision_id"]) == 32  # uuid hex
        assert d["compiled_by"] == ADMIN_EMAIL

    def test_compile_increments_rev_and_unique_revision_id(self, admin_headers, existing_bot_with_members):
        mb_id = existing_bot_with_members
        prev = requests.post(f"{API}/master-bot/{mb_id}/compile",
                             headers=admin_headers,
                             json={"runtime_mode": "multi_strategy"}, timeout=60).json()
        r2 = requests.post(f"{API}/master-bot/{mb_id}/compile",
                           headers=admin_headers,
                           json={"runtime_mode": "multi_strategy"}, timeout=60)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["rev"] == prev["rev"] + 1
        assert d2["revision_id"] != prev["revision_id"]

    def test_compile_deterministic_hash(self, admin_headers, existing_bot_with_members):
        mb_id = existing_bot_with_members
        a = requests.post(f"{API}/master-bot/{mb_id}/compile",
                          headers=admin_headers,
                          json={"runtime_mode": "multi_strategy"}, timeout=60).json()
        b = requests.post(f"{API}/master-bot/{mb_id}/compile",
                          headers=admin_headers,
                          json={"runtime_mode": "multi_strategy"}, timeout=60).json()
        assert a["definition_hash"] == b["definition_hash"]
        assert a["revision_id"] != b["revision_id"]

    def test_compile_single_active_persists_policy(self, admin_headers, existing_bot_with_members):
        mb_id = existing_bot_with_members
        r = requests.post(f"{API}/master-bot/{mb_id}/compile",
                          headers=admin_headers,
                          json={"runtime_mode": "single_active",
                                "runtime_policy": {"cooldown_sec": 300}},
                          timeout=60)
        assert r.status_code == 200, r.text
        rev_id = r.json()["revision_id"]
        # Fetch full doc via /definitions/{rev}
        latest = requests.get(f"{API}/master-bot/{mb_id}/definitions/latest",
                              headers=admin_headers, timeout=30).json()
        assert latest["revision_id"] == rev_id
        runtime = latest["payload"]["runtime"]
        assert runtime["mode"] == "single_active"
        assert runtime["policy"] == {"cooldown_sec": 300}

    def test_compile_regime_aware(self, admin_headers, existing_bot_with_members):
        mb_id = existing_bot_with_members
        r = requests.post(f"{API}/master-bot/{mb_id}/compile",
                          headers=admin_headers,
                          json={"runtime_mode": "regime_aware"}, timeout=60)
        assert r.status_code == 200, r.text

    def test_compile_invalid_mode_400(self, admin_headers, existing_bot_with_members):
        r = requests.post(f"{API}/master-bot/{existing_bot_with_members}/compile",
                          headers=admin_headers,
                          json={"runtime_mode": "invalid_mode"}, timeout=30)
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        # Should mention valid modes
        assert "single_active" in detail or "multi_strategy" in detail or "runtime_mode" in detail

    def test_compile_empty_bot_400(self, admin_headers, empty_bot):
        r = requests.post(f"{API}/master-bot/{empty_bot}/compile",
                          headers=admin_headers, json={}, timeout=30)
        assert r.status_code == 400, r.text
        assert "no members" in (r.json().get("detail") or "").lower()

    def test_compile_soft_deleted_400(self, admin_headers, soft_deleted_bot):
        r = requests.post(f"{API}/master-bot/{soft_deleted_bot}/compile",
                          headers=admin_headers, json={}, timeout=30)
        assert r.status_code == 400, r.text
        assert "delete" in (r.json().get("detail") or "").lower()

    def test_compile_nonexistent_404(self, admin_headers):
        r = requests.post(f"{API}/master-bot/no_such_bot_xyz/compile",
                          headers=admin_headers, json={}, timeout=30)
        assert r.status_code == 404, r.text


# ───────────────────────── MB-4: Read definitions ─────────────────────

class TestDefinitionReads:
    def test_list_definitions_sorted_desc(self, admin_headers, existing_bot_with_members):
        r = requests.get(f"{API}/master-bot/{existing_bot_with_members}/definitions",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "definitions" in body
        defs = body["definitions"]
        assert body["count"] == len(defs)
        revs = [d["rev"] for d in defs]
        assert revs == sorted(revs, reverse=True)
        # payload omitted for brevity
        for d in defs:
            assert "payload" not in d

    def test_latest_includes_payload(self, admin_headers, existing_bot_with_members):
        r = requests.get(f"{API}/master-bot/{existing_bot_with_members}/definitions/latest",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "payload" in d
        p = d["payload"]
        for k in ("definition_engine_version", "master_bot", "tiers", "ranker",
                  "runtime", "signals", "export_targets"):
            assert k in p, f"missing key {k} in payload"

    def test_definition_by_rev(self, admin_headers, existing_bot_with_members):
        latest = requests.get(
            f"{API}/master-bot/{existing_bot_with_members}/definitions/latest",
            headers=admin_headers, timeout=30).json()
        rev = latest["rev"]
        r = requests.get(
            f"{API}/master-bot/{existing_bot_with_members}/definitions/{rev}",
            headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["rev"] == rev

    def test_definition_nonexistent_rev_404(self, admin_headers, existing_bot_with_members):
        r = requests.get(
            f"{API}/master-bot/{existing_bot_with_members}/definitions/99999",
            headers=admin_headers, timeout=30)
        assert r.status_code == 404

    def test_payload_tier_shape(self, admin_headers, existing_bot_with_members):
        latest = requests.get(
            f"{API}/master-bot/{existing_bot_with_members}/definitions/latest",
            headers=admin_headers, timeout=30).json()
        tiers = latest["payload"]["tiers"]
        assert isinstance(tiers, list)
        # Each tier has tier_key in tier1/tier2/tier3 and a members array
        keys = [t["tier_key"] for t in tiers]
        for k in keys:
            assert k in ("tier1", "tier2", "tier3")
        for t in tiers:
            assert "members" in t and isinstance(t["members"], list)
            # members sorted by order_index
            ordered = sorted(t["members"], key=lambda m: int(m.get("order_index") or 0))
            assert ordered == t["members"]


# ───────────────────────── MB-7: Export ───────────────────────────────

class TestExport:
    def test_export_with_no_revision_uses_latest(self, admin_headers, existing_bot_with_members):
        # Ensure a definition exists
        requests.post(f"{API}/master-bot/{existing_bot_with_members}/compile",
                      headers=admin_headers, json={}, timeout=60)
        r = requests.post(f"{API}/master-bot/{existing_bot_with_members}/export",
                          headers=admin_headers, json={}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("export_id", "filename_cs", "filename_meta",
                  "sha256_cs", "sha256_meta", "cs_path", "meta_path"):
            assert k in d, f"missing {k}"
        assert d["sha256_cs"].startswith("sha256:")
        assert d["sha256_meta"].startswith("sha256:")

    def test_export_explicit_revision_id(self, admin_headers, existing_bot_with_members):
        latest = requests.get(
            f"{API}/master-bot/{existing_bot_with_members}/definitions/latest",
            headers=admin_headers, timeout=30).json()
        rid = latest["revision_id"]
        rev = latest["rev"]
        r = requests.post(f"{API}/master-bot/{existing_bot_with_members}/export",
                          headers=admin_headers,
                          json={"revision_id": rid}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert f"rev{rev}" in d["filename_cs"]
        assert d["revision_id"] == rid

    def test_export_revision_id_from_other_bot_400(
        self, admin_headers, existing_bot_with_members, other_bot_with_members
    ):
        # Compile other bot first
        oc = requests.post(f"{API}/master-bot/{other_bot_with_members}/compile",
                           headers=admin_headers, json={}, timeout=60)
        assert oc.status_code == 200, oc.text
        other_rev_id = oc.json()["revision_id"]
        r = requests.post(f"{API}/master-bot/{existing_bot_with_members}/export",
                          headers=admin_headers,
                          json={"revision_id": other_rev_id}, timeout=30)
        assert r.status_code == 400, r.text
        assert "does not belong" in (r.json().get("detail") or "").lower()

    def test_export_compile_if_missing_false(self, admin_headers, admin_headers_alt=None):
        # Create a NEW bot, fill but DON'T compile, then export with compile_if_missing=false
        name = f"MB_TEST_NOCOMP_{uuid.uuid4().hex[:6]}"
        cr = requests.post(f"{API}/master-bot", headers=admin_headers,
                           json={"name": name}, timeout=30)
        mb_id = cr.json()["id"]
        try:
            fr = requests.post(f"{API}/master-bot/{mb_id}/auto-fill",
                               headers=admin_headers,
                               json={"tier1_count": 1, "tier2_count": 0, "tier3_count": 0},
                               timeout=30)
            assert fr.status_code == 200
            r = requests.post(f"{API}/master-bot/{mb_id}/export",
                              headers=admin_headers,
                              json={"compile_if_missing": False}, timeout=30)
            assert r.status_code == 400, r.text
            assert "no compiled definition" in (r.json().get("detail") or "").lower()
        finally:
            requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                            headers=admin_headers, timeout=30)

    def test_list_exports_sorted_desc(self, admin_headers, existing_bot_with_members):
        r = requests.get(f"{API}/master-bot/{existing_bot_with_members}/exports",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "exports" in body
        ts = [e["created_at"] for e in body["exports"]]
        assert ts == sorted(ts, reverse=True)


# ───────────────────────── MB-7: Download artifacts ───────────────────

class TestDownload:
    @pytest.fixture(scope="class")
    def export_row(self, admin_headers, existing_bot_with_members):
        r = requests.post(f"{API}/master-bot/{existing_bot_with_members}/export",
                          headers=admin_headers, json={}, timeout=60)
        assert r.status_code == 200, r.text
        return r.json()

    def test_download_cs(self, admin_headers, export_row):
        r = requests.get(f"{API}/master-bot/exports/{export_row['export_id']}/download/cs",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        assert "text/plain" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert export_row["filename_cs"] in cd
        # C# anchors
        body = r.text
        for needle in (
            "[Robot(",
            "public class MasterBot_",
            "public interface ITierStrategy",
            "private readonly List<ITierStrategy> _t1",
            "protected override void OnStart()",
            "protected override void OnBar()",
            "// Master Bot:",
            "// Revision:",
            "// Definition hash:",
        ):
            assert needle in body, f"missing anchor: {needle!r}"
        # Per-tier1 enabled member class
        assert "Tier1Strategy_" in body

    def test_download_meta(self, admin_headers, export_row):
        r = requests.get(f"{API}/master-bot/exports/{export_row['export_id']}/download/meta",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        assert "application/json" in r.headers.get("content-type", "")
        meta = json.loads(r.text)
        for k in ("master_bot_id", "revision_id", "rev", "definition_hash",
                  "exporter_version", "csharp_class", "filename_cs",
                  "filename_meta", "sha256_cs", "sha256_meta", "exported_at",
                  "exported_by", "payload"):
            assert k in meta, f"missing meta key {k}"
        assert isinstance(meta["payload"]["tiers"], list)
        for t in meta["payload"]["tiers"]:
            assert t["tier_key"] in ("tier1", "tier2", "tier3")

    def test_download_invalid_kind_400(self, admin_headers, export_row):
        r = requests.get(f"{API}/master-bot/exports/{export_row['export_id']}/download/wasm",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 400, r.text
        assert "cs" in (r.json().get("detail") or "").lower()

    def test_download_bad_export_id_404(self, admin_headers):
        r = requests.get(f"{API}/master-bot/exports/nonexistent_export_id_xyz/download/cs",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 404, r.text


# ───────────────────────── Export-target stamping ─────────────────────

def test_export_stamps_export_targets_on_definition(admin_headers, existing_bot_with_members):
    # Compile, export, re-fetch by rev
    c = requests.post(f"{API}/master-bot/{existing_bot_with_members}/compile",
                      headers=admin_headers, json={}, timeout=60).json()
    rev = c["rev"]
    e = requests.post(f"{API}/master-bot/{existing_bot_with_members}/export",
                      headers=admin_headers,
                      json={"revision_id": c["revision_id"]}, timeout=60).json()
    d = requests.get(
        f"{API}/master-bot/{existing_bot_with_members}/definitions/{rev}",
        headers=admin_headers, timeout=30).json()
    cs_text_target = d["payload"]["export_targets"]["cs_text"]
    assert cs_text_target is not None
    for k in ("export_id", "cs_path", "sha256_cs", "sha256_meta", "exported_at"):
        assert k in cs_text_target, f"missing {k} in export_targets.cs_text"
    assert cs_text_target["export_id"] == e["export_id"]


# ───────────────────────── RBAC ───────────────────────────────────────

class TestRBAC:
    def test_non_admin_cannot_compile(self, non_admin_headers, existing_bot_with_members):
        r = requests.post(f"{API}/master-bot/{existing_bot_with_members}/compile",
                          headers=non_admin_headers, json={}, timeout=30)
        assert r.status_code == 403, r.text

    def test_non_admin_cannot_export(self, non_admin_headers, existing_bot_with_members):
        r = requests.post(f"{API}/master-bot/{existing_bot_with_members}/export",
                          headers=non_admin_headers, json={}, timeout=30)
        assert r.status_code == 403, r.text

    def test_non_admin_can_list_definitions(self, non_admin_headers, existing_bot_with_members):
        r = requests.get(f"{API}/master-bot/{existing_bot_with_members}/definitions",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_non_admin_can_get_latest(self, non_admin_headers, existing_bot_with_members):
        r = requests.get(f"{API}/master-bot/{existing_bot_with_members}/definitions/latest",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_non_admin_can_list_exports(self, non_admin_headers, existing_bot_with_members):
        r = requests.get(f"{API}/master-bot/{existing_bot_with_members}/exports",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_non_admin_can_download(self, non_admin_headers, admin_headers, existing_bot_with_members):
        # Need an export to download — use admin to create one first
        e = requests.post(f"{API}/master-bot/{existing_bot_with_members}/export",
                          headers=admin_headers, json={}, timeout=60).json()
        r = requests.get(f"{API}/master-bot/exports/{e['export_id']}/download/cs",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text
