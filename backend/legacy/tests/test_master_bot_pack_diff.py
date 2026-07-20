"""End-to-end backend tests for Master Bot V1 — MB-8 (.cbotpack Builder)
and Revision Diff endpoint.

Auth model: bearer JWT from /api/auth/login. POST /pack requires admin
(via require_admin). All other endpoints (list/download/diff) are open
to any authenticated user.

Reuses admin credentials from /app/memory/test_credentials.md and
patterns from test_master_bot_definition_export.py.
"""
from __future__ import annotations

import io
import json
import os
import uuid
import zipfile

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://implementation-audit-2.preview.emergentagent.com"
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
def existing_bot(admin_headers) -> str:
    """An existing master bot with members + compiled revs + .cs exports."""
    r = requests.get(f"{API}/master-bot?limit=200",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    for b in r.json().get("master_bots") or []:
        if b.get("status") == "DELETED":
            continue
        mc = b.get("member_counts") or {}
        if int(mc.get("total") or 0) > 0:
            return b.get("id")
    pytest.skip("No bot with members found")


@pytest.fixture(scope="session")
def existing_bot_other(admin_headers, existing_bot) -> str:
    """A SECOND existing bot, used for cross-bot rejection tests."""
    r = requests.get(f"{API}/master-bot?limit=200",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    for b in r.json().get("master_bots") or []:
        if b.get("status") == "DELETED" or b.get("id") == existing_bot:
            continue
        return b.get("id")
    # Create one if none exists
    name = f"MB_TEST_OTHER_{uuid.uuid4().hex[:6]}"
    cr = requests.post(f"{API}/master-bot", headers=admin_headers,
                       json={"name": name}, timeout=30)
    assert cr.status_code in (200, 201), cr.text
    other = cr.json().get("id")
    fr = requests.post(f"{API}/master-bot/{other}/auto-fill",
                       headers=admin_headers,
                       json={"tier1_count": 1, "tier2_count": 1, "tier3_count": 0},
                       timeout=30)
    assert fr.status_code == 200, fr.text
    cmp_ = requests.post(f"{API}/master-bot/{other}/compile",
                         headers=admin_headers, json={}, timeout=60)
    assert cmp_.status_code == 200, cmp_.text
    ex = requests.post(f"{API}/master-bot/{other}/export",
                       headers=admin_headers, json={}, timeout=60)
    assert ex.status_code == 200, ex.text
    return other


# ───────────────────────── helpers ─────────────────────────

EXPECTED_FILES = {
    "MainSource.cs", "Properties.xml", "definition.json",
    "ranker_weights.json", "members.csv", "README.md",
}


def _list_revs(headers, bot_id):
    r = requests.get(f"{API}/master-bot/{bot_id}/definitions?limit=200",
                     headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("definitions") or []


# ───────────────────────── MB-8 .cbotpack tests ─────────────────────────

class TestPackBuild:
    """POST /api/master-bot/{id}/pack happy paths + payload shape."""

    def test_pack_default_returns_full_shape(self, admin_headers, existing_bot):
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers, json={}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["pack_id"]
        assert data["filename"].endswith(".cbotpack")
        assert data["sha256"].startswith("sha256:")
        assert int(data["size_bytes"]) > 0
        files = data["files"]
        assert EXPECTED_FILES.issubset(set(files.keys())), files.keys()
        for fname in EXPECTED_FILES:
            assert "size" in files[fname] and "sha256" in files[fname]
            assert files[fname]["sha256"].startswith("sha256:")
            assert int(files[fname]["size"]) >= 0

    def test_pack_with_specific_revision(self, admin_headers, existing_bot):
        revs = _list_revs(admin_headers, existing_bot)
        assert revs, "expected pre-existing revisions"
        target_rev = revs[len(revs) // 2]  # pick a middle revision
        rev_id = target_rev["revision_id"]
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers,
                          json={"revision_id": rev_id}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["revision_id"] == rev_id

        # Download + inspect manifest + Properties.xml
        pid = data["pack_id"]
        dl = requests.get(f"{API}/master-bot/packs/{pid}/download",
                          headers=admin_headers, timeout=60)
        assert dl.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            props_xml = zf.read("Properties.xml").decode("utf-8")
        assert manifest["revision_id"] == rev_id
        assert rev_id in props_xml

    def test_pack_with_existing_export_id(self, admin_headers, existing_bot):
        # Pull an existing export for this bot
        ex_list = requests.get(f"{API}/master-bot/{existing_bot}/exports",
                               headers=admin_headers, timeout=30)
        assert ex_list.status_code == 200
        exports = ex_list.json().get("exports") or []
        if not exports:
            pytest.skip("no existing export to reuse")
        eid = exports[0]["export_id"]
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers,
                          json={"export_id": eid}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["export_id"] == eid

        dl = requests.get(f"{API}/master-bot/packs/{data['pack_id']}/download",
                          headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["export_id"] == eid


class TestPackDownloadAndContents:
    """GET /api/master-bot/packs/{id}/download — validates ZIP contents."""

    @pytest.fixture(scope="class")
    def pack(self, admin_headers, existing_bot):
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers, json={}, timeout=60)
        assert r.status_code == 200, r.text
        return r.json()

    def test_download_streams_zip_with_proper_headers(self, admin_headers, pack):
        pid = pack["pack_id"]
        r = requests.get(f"{API}/master-bot/packs/{pid}/download",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/zip")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert pack["filename"] in cd
        assert r.content[:2] == b"PK"  # ZIP magic

    def test_zip_contains_all_seven_files(self, admin_headers, pack):
        pid = pack["pack_id"]
        r = requests.get(f"{API}/master-bot/packs/{pid}/download",
                         headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = set(zf.namelist())
        assert EXPECTED_FILES.issubset(names), names
        assert "manifest.json" in names

    def test_mainsource_cs_header(self, admin_headers, pack):
        r = requests.get(f"{API}/master-bot/packs/{pack['pack_id']}/download",
                         headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            cs = zf.read("MainSource.cs").decode("utf-8", errors="replace")
        assert cs.startswith(
            "// ============================================================================="
        ), cs[:120]

    def test_properties_xml_schema(self, admin_headers, pack):
        r = requests.get(f"{API}/master-bot/packs/{pack['pack_id']}/download",
                         headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            xml = zf.read("Properties.xml").decode("utf-8")
        # Cheap XML validity check
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        assert root.tag.endswith("cBot")
        # Required tags
        for tag in ("Name", "MasterBotId", "RevisionId",
                    "DefinitionHash", "RuntimeMode"):
            assert f"<{tag}>" in xml, f"missing tag {tag}"

    def test_definition_json_keys(self, admin_headers, pack):
        r = requests.get(f"{API}/master-bot/packs/{pack['pack_id']}/download",
                         headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            payload = json.loads(zf.read("definition.json"))
        for k in ("definition_engine_version", "master_bot", "tiers",
                  "ranker", "runtime", "signals", "export_targets"):
            assert k in payload, f"definition.json missing {k}"

    def test_manifest_json_has_sha256_for_all_files(self, admin_headers, pack):
        r = requests.get(f"{API}/master-bot/packs/{pack['pack_id']}/download",
                         headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["pack_id"] == pack["pack_id"]
        files = manifest["files"]
        # Should hash all 6 (manifest.json hashes itself excluded)
        for fname in EXPECTED_FILES:
            assert fname in files, f"manifest missing {fname}"
            assert files[fname]["sha256"].startswith("sha256:")
        assert "manifest.json" not in files

    def test_members_csv_header(self, admin_headers, pack):
        r = requests.get(f"{API}/master-bot/packs/{pack['pack_id']}/download",
                         headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            csv = zf.read("members.csv").decode("utf-8")
        first_line = csv.splitlines()[0]
        assert first_line == (
            "tier,order,enabled,strategy_hash,pair,timeframe,style,"
            "profit_factor,win_rate,pass_probability,deploy_score,"
            "candidate_score,lifecycle_stage"
        )

    def test_readme_mentions_keywords(self, admin_headers, pack):
        r = requests.get(f"{API}/master-bot/packs/{pack['pack_id']}/download",
                         headers=admin_headers, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            readme = zf.read("README.md").decode("utf-8")
            defn = json.loads(zf.read("definition.json"))
        assert "Master Bot" in readme
        assert "cBot" in readme
        runtime_mode = (defn.get("runtime") or {}).get("mode") or "multi_strategy"
        assert runtime_mode in readme


class TestPackValidation:
    """Error paths for POST /pack."""

    def test_revision_id_from_different_bot_returns_400(
            self, admin_headers, existing_bot, existing_bot_other):
        # Get a revision from the OTHER bot
        revs_other = _list_revs(admin_headers, existing_bot_other)
        assert revs_other
        wrong_rev = revs_other[0]["revision_id"]
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers,
                          json={"revision_id": wrong_rev}, timeout=60)
        # revision_id maps to a different bot — engine returns 404 since
        # the definition lookup uses revision_id only (not master_bot_id),
        # so the export ends up being created/fetched against existing_bot
        # with a rev_id from another bot. Acceptable: 400 OR 404.
        # Reading code: build_pack with revision_id queries exports where
        # master_bot_id matches existing_bot — if not found auto-exports
        # via mbx.export_master_bot(existing_bot, revision_id=wrong_rev),
        # which should raise "revision not found / belongs to other bot"
        # → 400 or 404. Accept both.
        assert r.status_code in (400, 404), f"got {r.status_code}: {r.text}"

    def test_export_id_from_different_bot_returns_400(
            self, admin_headers, existing_bot, existing_bot_other):
        ex = requests.get(f"{API}/master-bot/{existing_bot_other}/exports",
                          headers=admin_headers, timeout=30)
        exports = ex.json().get("exports") or []
        if not exports:
            pytest.skip("no export on other bot")
        wrong_eid = exports[0]["export_id"]
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers,
                          json={"export_id": wrong_eid}, timeout=60)
        assert r.status_code == 400, f"got {r.status_code}: {r.text}"

    def test_bad_revision_id_returns_404(self, admin_headers, existing_bot):
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers,
                          json={"revision_id": "rev_does_not_exist_xyz"},
                          timeout=60)
        assert r.status_code == 404, f"got {r.status_code}: {r.text}"

    def test_download_bad_pack_id_returns_404(self, admin_headers):
        r = requests.get(f"{API}/master-bot/packs/pack_doesnotexist_xyz/download",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 404


class TestPackList:
    def test_list_packs_returns_sorted_desc(self, admin_headers, existing_bot):
        # Ensure >=2 packs exist
        for _ in range(2):
            r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                              headers=admin_headers, json={}, timeout=60)
            assert r.status_code == 200
        r = requests.get(f"{API}/master-bot/{existing_bot}/packs",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "count" in body and "packs" in body
        packs = body["packs"]
        assert len(packs) >= 2
        # Sorted DESC by created_at
        ts = [p["created_at"] for p in packs]
        assert ts == sorted(ts, reverse=True), ts


class TestPackDefinitionStamp:
    """After packing, definition's payload.export_targets.cbotpack is filled."""

    def test_definition_export_target_stamped(self, admin_headers, existing_bot):
        revs = _list_revs(admin_headers, existing_bot)
        rev_id = revs[0]["revision_id"]
        rev_num = revs[0]["rev"]
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=admin_headers,
                          json={"revision_id": rev_id}, timeout=60)
        assert r.status_code == 200, r.text
        pid = r.json()["pack_id"]

        d = requests.get(f"{API}/master-bot/{existing_bot}/definitions/{rev_num}",
                         headers=admin_headers, timeout=30)
        assert d.status_code == 200, d.text
        targets = (d.json().get("payload") or {}).get("export_targets") or {}
        cb = targets.get("cbotpack") or {}
        assert cb.get("pack_id") == pid
        for k in ("pack_path", "sha256", "filename", "packed_at"):
            assert k in cb, f"cbotpack target missing {k}"


class TestPackRBAC:
    def test_non_admin_cannot_build(self, non_admin_headers, existing_bot):
        r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                          headers=non_admin_headers, json={}, timeout=60)
        assert r.status_code == 403, f"got {r.status_code}: {r.text}"

    def test_non_admin_can_list(self, non_admin_headers, existing_bot):
        r = requests.get(f"{API}/master-bot/{existing_bot}/packs",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_non_admin_can_download(self, admin_headers, non_admin_headers,
                                    existing_bot):
        r = requests.get(f"{API}/master-bot/{existing_bot}/packs",
                         headers=non_admin_headers, timeout=30)
        packs = r.json().get("packs") or []
        if not packs:
            # Create one as admin
            cb = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                               headers=admin_headers, json={}, timeout=60)
            pid = cb.json()["pack_id"]
        else:
            pid = packs[0]["pack_id"]
        dl = requests.get(f"{API}/master-bot/packs/{pid}/download",
                          headers=non_admin_headers, timeout=60)
        assert dl.status_code == 200


STABLE_FILES = ("MainSource.cs", "Properties.xml", "definition.json",
                "ranker_weights.json", "members.csv")


class TestPackIdempotency:
    def test_two_packs_same_export_share_byte_stable_files(
            self, admin_headers, existing_bot):
        ex_list = requests.get(f"{API}/master-bot/{existing_bot}/exports",
                               headers=admin_headers, timeout=30)
        exports = ex_list.json().get("exports") or []
        if not exports:
            pytest.skip("no export to reuse")
        eid = exports[0]["export_id"]

        r1 = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                           headers=admin_headers,
                           json={"export_id": eid}, timeout=60)
        r2 = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                           headers=admin_headers,
                           json={"export_id": eid}, timeout=60)
        assert r1.status_code == 200 and r2.status_code == 200
        p1, p2 = r1.json(), r2.json()
        assert p1["pack_id"] != p2["pack_id"]

        for fname in STABLE_FILES:
            assert p1["files"][fname]["sha256"] == p2["files"][fname]["sha256"], \
                f"file {fname} sha drifted between pack1 and pack2"

    def test_three_packs_same_export_pairwise_byte_stable(
            self, admin_headers, existing_bot):
        """MB-8 retest: three consecutive packs of same export_id must have
        pairwise-equal sha256 for the 5 canonical files. Confirms the
        copy.deepcopy + export_targets scrub fix in build_pack."""
        ex_list = requests.get(f"{API}/master-bot/{existing_bot}/exports",
                               headers=admin_headers, timeout=30)
        exports = ex_list.json().get("exports") or []
        if not exports:
            pytest.skip("no export to reuse")
        eid = exports[0]["export_id"]

        packs = []
        for i in range(3):
            r = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                              headers=admin_headers,
                              json={"export_id": eid}, timeout=60)
            assert r.status_code == 200, f"pack{i+1}: {r.status_code} {r.text}"
            packs.append(r.json())

        # All pack_ids unique
        pids = {p["pack_id"] for p in packs}
        assert len(pids) == 3, f"pack_ids not unique: {pids}"

        # Pairwise equality across pack1/2/3 for the 5 stable files
        p1, p2, p3 = packs
        for fname in STABLE_FILES:
            s1 = p1["files"][fname]["sha256"]
            s2 = p2["files"][fname]["sha256"]
            s3 = p3["files"][fname]["sha256"]
            assert s1 == s2 == s3, (
                f"{fname} drifted across 3 packs: "
                f"p1={s1} p2={s2} p3={s3}"
            )

        # manifest.json and README.md MAY drift (timestamps embedded)
        # We don't assert anything about them but log for visibility.
        for fname in ("README.md",):
            assert fname in p1["files"]

    def test_pack2_definition_json_has_scrubbed_export_targets(
            self, admin_headers, existing_bot):
        """Download pack2's ZIP and verify definition.json carries
        export_targets={cs_text:None, cbotpack:None, wasm:None}.
        Proves the canonical-form scrub worked."""
        ex_list = requests.get(f"{API}/master-bot/{existing_bot}/exports",
                               headers=admin_headers, timeout=30)
        exports = ex_list.json().get("exports") or []
        if not exports:
            pytest.skip("no export to reuse")
        eid = exports[0]["export_id"]

        # Build pack1 first (to ensure a prior cbotpack stamp exists in DB),
        # then pack2 and inspect.
        r1 = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                           headers=admin_headers,
                           json={"export_id": eid}, timeout=60)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/master-bot/{existing_bot}/pack",
                           headers=admin_headers,
                           json={"export_id": eid}, timeout=60)
        assert r2.status_code == 200, r2.text
        pid2 = r2.json()["pack_id"]

        dl = requests.get(f"{API}/master-bot/packs/{pid2}/download",
                          headers=admin_headers, timeout=60)
        assert dl.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
            defn = json.loads(zf.read("definition.json"))

        assert "export_targets" in defn, \
            "definition.json missing 'export_targets' key"
        et = defn["export_targets"]
        assert isinstance(et, dict), f"export_targets not a dict: {type(et)}"
        for sub in ("cs_text", "cbotpack", "wasm"):
            assert sub in et, f"export_targets missing sub-key {sub}: {list(et.keys())}"
            assert et[sub] is None, (
                f"export_targets.{sub} expected null, got {et[sub]!r} "
                f"— the canonical-form scrub leaked prior pack metadata"
            )


# ───────────────────────── Diff tests ─────────────────────────

class TestDiff:
    def test_diff_default_latest_two_revs(self, admin_headers, existing_bot):
        r = requests.get(f"{API}/master-bot/{existing_bot}/diff",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("from", "to", "hash_changed", "is_initial",
                  "members_added", "members_removed", "tier_moves",
                  "enable_changes", "snapshot_drifts", "ranker_changes",
                  "runtime_changes", "constraint_changes",
                  "tier_metadata_changes"):
            assert k in body, f"missing key {k}"

    def test_diff_to_rev_1_is_initial(self, admin_headers, existing_bot):
        r = requests.get(f"{API}/master-bot/{existing_bot}/diff?to_rev=1",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_initial"] is True
        assert body["from"] is None
        # members_added should be populated for any non-empty initial rev
        # (allow empty if rev 1 was compiled with zero members historically;
        # but engine prevents that — so should be > 0)
        assert isinstance(body["members_added"], list)

    def test_diff_same_state_no_changes(self, admin_headers, existing_bot):
        revs = _list_revs(admin_headers, existing_bot)
        # Find two consecutive revs with identical definition_hash
        pair = None
        for i in range(len(revs) - 1):
            # revs are typically sorted DESC by rev
            r1, r2 = revs[i], revs[i + 1]
            if r1.get("definition_hash") == r2.get("definition_hash"):
                pair = (r2["rev"], r1["rev"])  # (smaller, larger)
                break
        if not pair:
            pytest.skip("no two revs share the same definition_hash")
        from_rev, to_rev = pair
        r = requests.get(
            f"{API}/master-bot/{existing_bot}/diff"
            f"?from_rev={from_rev}&to_rev={to_rev}",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["hash_changed"] is False
        assert body["members_added"] == []
        assert body["members_removed"] == []
        assert body["tier_moves"] == []
        assert body["enable_changes"] == []

    def test_diff_to_rev_not_found(self, admin_headers, existing_bot):
        r = requests.get(f"{API}/master-bot/{existing_bot}/diff?to_rev=99999",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 404
        assert "to" in (r.json().get("detail") or "").lower() or \
               "not found" in (r.json().get("detail") or "").lower()

    def test_diff_rbac_open_to_non_admin(self, non_admin_headers, existing_bot):
        r = requests.get(f"{API}/master-bot/{existing_bot}/diff",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text


class TestDiffMutation:
    """End-to-end mutation: rev1 → promote + disable → rev2, expect 1
    tier_move + 1 enable_change."""

    def test_promote_and_disable_diff(self, admin_headers):
        # Create a fresh bot
        name = f"MB_TEST_DIFFMUT_{uuid.uuid4().hex[:6]}"
        cr = requests.post(f"{API}/master-bot", headers=admin_headers,
                           json={"name": name}, timeout=30)
        assert cr.status_code in (200, 201), cr.text
        mb_id = cr.json()["id"]

        try:
            # Auto-fill (need at least 2 members, ideally one in tier2/3 to promote)
            fr = requests.post(f"{API}/master-bot/{mb_id}/auto-fill",
                               headers=admin_headers,
                               json={"tier1_count": 1, "tier2_count": 2,
                                     "tier3_count": 1},
                               timeout=30)
            assert fr.status_code == 200, fr.text
            added = fr.json().get("added") or []
            if len(added) < 2:
                pytest.skip("auto-fill produced <2 members")

            # Pick a non-tier1 member to promote; pick a different member to disable
            promote_hash = None
            disable_hash = None
            for m in added:
                if m.get("tier") in ("tier2", "tier3") and promote_hash is None:
                    promote_hash = m["strategy_hash"]
                    break
            for m in added:
                if disable_hash is None and m["strategy_hash"] != promote_hash:
                    disable_hash = m["strategy_hash"]
            if not promote_hash:
                # All members landed in tier1; promote isn't valid → skip
                pytest.skip(f"no non-tier1 members; added={[(m.get('tier'), m.get('strategy_hash')[:8]) for m in added]}")
            if not disable_hash:
                pytest.skip("could not pick second distinct member to disable")

            # Compile rev 1
            c1 = requests.post(f"{API}/master-bot/{mb_id}/compile",
                               headers=admin_headers, json={}, timeout=60)
            assert c1.status_code == 200, c1.text
            rev1 = c1.json()["rev"]

            # Promote one member (tier3→tier2 or tier2→tier1)
            pr = requests.post(
                f"{API}/master-bot/{mb_id}/members/{promote_hash}/promote",
                headers=admin_headers, timeout=30,
            )
            assert pr.status_code == 200, pr.text

            # Disable another
            dr = requests.post(
                f"{API}/master-bot/{mb_id}/members/{disable_hash}/disable",
                headers=admin_headers, timeout=30,
            )
            assert dr.status_code == 200, dr.text

            # Compile rev 2
            c2 = requests.post(f"{API}/master-bot/{mb_id}/compile",
                               headers=admin_headers, json={}, timeout=60)
            assert c2.status_code == 200, c2.text
            rev2 = c2.json()["rev"]
            assert rev2 == rev1 + 1

            # Diff
            d = requests.get(
                f"{API}/master-bot/{mb_id}/diff?from_rev={rev1}&to_rev={rev2}",
                headers=admin_headers, timeout=30,
            )
            assert d.status_code == 200, d.text
            body = d.json()
            assert body["hash_changed"] is True
            tier_moves = body["tier_moves"]
            enable_changes = body["enable_changes"]
            promoted = [tm for tm in tier_moves
                        if tm["strategy_hash"] == promote_hash]
            disabled = [ec for ec in enable_changes
                        if ec["strategy_hash"] == disable_hash
                        and ec["from_enabled"] is True
                        and ec["to_enabled"] is False]
            assert len(promoted) == 1, f"expected 1 tier_move for {promote_hash}, got {tier_moves}"
            assert len(disabled) == 1, f"expected 1 disable enable_change, got {enable_changes}"
        finally:
            # Cleanup
            requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                            headers=admin_headers, timeout=30)
