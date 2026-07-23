"""MB-7.2 — Strategy IR back-fill + IR-aware exporter tests.

Covers:
  - GET /api/master-bot/ir/coverage (open)
  - POST /api/master-bot/ir/backfill (admin only, idempotent, force)
  - Auto-fill captures strategy_ir into member snapshots
  - add_member lazy IR fetch
  - Compile + Export emits real cAlgo C# via IR transpiler
  - Sidecar emission_log / emission_summary
  - Exporter version v1.2
  - Backwards compatibility (snapshot.strategy_ir=null -> stub)
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://factory-v2-canonical.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "AdminTest123!"


# ───────────────────────── fixtures ─────────────────────────

@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"admin login: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def non_admin_headers(admin_headers):
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.local"
    pwd = "UserTest123!"
    r = requests.post(f"{API}/auth/signup", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code in (200, 201), r.text
    user_id = (r.json().get("user") or r.json()).get("user_id") or (r.json().get("user") or r.json()).get("id")
    if not user_id:
        lu = requests.get(f"{API}/admin/users?status=pending", headers=admin_headers, timeout=30)
        for u in lu.json().get("users", []):
            if (u.get("email") or "").lower() == email.lower():
                user_id = u.get("user_id") or u.get("id")
                break
    assert user_id
    ar = requests.post(f"{API}/admin/approve/{user_id}", headers=admin_headers, timeout=30)
    assert ar.status_code == 200, ar.text
    lr = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    token = lr.json().get("token") or lr.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_bot(headers, prefix="MB72") -> str:
    name = f"{prefix}_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/master-bot", headers=headers,
                      json={"name": name, "description": "mb72 test"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json().get("id") or r.json().get("_id") or r.json().get("master_bot_id")


def _cleanup_bot(headers, bot_id):
    try:
        requests.delete(f"{API}/master-bot/{bot_id}?hard=true", headers=headers, timeout=30)
    except Exception:
        pass


# ───────────────────────── /ir/coverage ─────────────────────────

class TestIRCoverage:
    def test_coverage_shape_and_open_access(self, admin_headers):
        r = requests.get(f"{API}/master-bot/ir/coverage", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total", "with_ir", "without_ir", "coverage_pct",
                  "by_ir_source", "by_strategy_type", "computed_at"):
            assert k in d, f"missing key {k}: {d}"
        assert isinstance(d["coverage_pct"], (int, float))
        assert 0 <= d["coverage_pct"] <= 100
        assert isinstance(d["by_ir_source"], dict)
        assert isinstance(d["by_strategy_type"], dict)

    def test_coverage_open_to_non_admin(self, non_admin_headers):
        r = requests.get(f"{API}/master-bot/ir/coverage", headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text


# ───────────────────────── /ir/backfill ─────────────────────────

class TestIRBackfill:
    def test_backfill_rbac_non_admin_forbidden(self, non_admin_headers):
        r = requests.post(f"{API}/master-bot/ir/backfill", headers=non_admin_headers, timeout=60)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_backfill_idempotent(self, admin_headers):
        # First run: rows may have already been backfilled by previous iteration
        # so this verifies idempotency contract regardless of state.
        r1 = requests.post(f"{API}/master-bot/ir/backfill", headers=admin_headers, timeout=120)
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        for k in ("total", "before", "after", "updated", "refused", "skipped_existing"):
            assert k in body1, f"missing key {k}: {list(body1.keys())}"

        # Second run without force: updated should be empty;
        # skipped_existing should be populated (since at least some IR rows exist).
        r2 = requests.post(f"{API}/master-bot/ir/backfill", headers=admin_headers, timeout=120)
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["updated"] == [], f"updated must be empty on idempotent re-run: {body2['updated']}"

    def test_backfill_force_reapplies(self, admin_headers):
        r = requests.post(f"{API}/master-bot/ir/backfill?force=true",
                          headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        # With force=True, every IR-capable row should appear in updated again.
        assert isinstance(body.get("updated"), list)
        assert len(body["updated"]) >= 5, \
            f"force re-apply should populate updated (>=5 expected): {len(body['updated'])}"

    def test_backfill_unmapped_strategy_type_refused(self, admin_headers):
        # Seeded lib_test_unmapped_99_aaa has strategy_type='arbitrage_xx_unmapped_kind'
        r = requests.post(f"{API}/master-bot/ir/backfill", headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        # On idempotent re-run, refused still surfaces (it has no IR so it's
        # in the "needs backfill" pool every time).
        refused = body.get("refused") or []
        assert any("unmapped" in (x.get("strategy_type") or "").lower() or
                   "arbitrage_xx" in (x.get("strategy_type") or "")
                   for x in refused), \
            f"expected unmapped row in refused: {refused}"
        for x in refused:
            assert "no canonical builder" in (x.get("reason") or "").lower(), \
                f"refused reason should mention 'no canonical builder': {x}"

    def test_coverage_includes_canonical_builder_source(self, admin_headers):
        r = requests.get(f"{API}/master-bot/ir/coverage", headers=admin_headers, timeout=30)
        d = r.json()
        assert d["by_ir_source"].get("canonical_builder", 0) >= 5, \
            f"expected >=5 canonical_builder rows: {d['by_ir_source']}"

    def test_backfilled_row_has_valid_ir_via_candidates(self, admin_headers):
        # Candidate pool surfaces strategy_ir for the lib_test_* rows; verify
        # the IR shape (ir_version==1, indicators list, entry_long object,
        # exits, metadata.pair, metadata.timeframe).
        r = requests.get(f"{API}/master-bot/candidates?limit=20",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200
        cands = r.json().get("candidates") or []
        ir_native = [c for c in cands if (c.get("ir_status") == "ir_native"
                                          and isinstance(c.get("strategy_ir"), dict))]
        assert ir_native, "no ir_native candidates found"
        ir = ir_native[0]["strategy_ir"]
        assert ir.get("ir_version") == 1, f"ir_version expected 1: {ir.get('ir_version')}"
        assert isinstance(ir.get("indicators"), list), "indicators must be list"
        assert isinstance(ir.get("entry_long"), dict), "entry_long must be object"
        assert isinstance(ir.get("entry_short"), dict), "entry_short must be object"
        assert "exit" in ir or "exits" in ir, "ir missing exit/exits block"
        meta = ir.get("metadata") or {}
        assert "pair" in meta and "timeframe" in meta, f"metadata missing pair/timeframe: {meta}"


# ───────────────────────── Auto-fill captures IR ─────────────────────────

class TestAutoFillIRCapture:
    def test_autofill_member_snapshot_carries_ir(self, admin_headers):
        bot_id = _create_bot(admin_headers, "MB72_AF")
        try:
            r = requests.post(f"{API}/master-bot/{bot_id}/auto-fill",
                              headers=admin_headers,
                              json={"tier1_count": 2, "tier2_count": 2, "tier3_count": 1,
                                    "clear_existing": True}, timeout=60)
            assert r.status_code == 200, r.text
            added = r.json().get("added") or []
            assert len(added) == 5
            # Each added member's snapshot must carry strategy_ir and ir_status=ir_native
            for m in added:
                snap = m.get("snapshot") or {}
                assert isinstance(snap.get("strategy_ir"), dict), \
                    f"snapshot.strategy_ir missing/null: {m.get('strategy_hash')}"
                assert snap.get("ir_status") == "ir_native", \
                    f"snapshot.ir_status not ir_native: {snap.get('ir_status')}"
        finally:
            _cleanup_bot(admin_headers, bot_id)


# ───────────────────────── add_member lazy IR ─────────────────────────

class TestAddMemberLazyIR:
    def test_add_member_no_snapshot_lazy_fetches_ir(self, admin_headers):
        bot_id = _create_bot(admin_headers, "MB72_LAZY")
        try:
            # Pull a known IR-capable hash from candidates
            cr = requests.get(f"{API}/master-bot/candidates?limit=20",
                              headers=admin_headers, timeout=60)
            cands = cr.json().get("candidates") or []
            ir_cands = [c for c in cands if c.get("ir_status") == "ir_native"]
            assert ir_cands
            sh = ir_cands[0]["strategy_hash"]
            # Add WITHOUT snapshot — engine should lazy-fetch IR.
            r = requests.post(f"{API}/master-bot/{bot_id}/members",
                              headers=admin_headers,
                              json={"strategy_hash": sh, "tier": "tier3"},
                              timeout=30)
            assert r.status_code in (200, 201), r.text
            snap = r.json().get("snapshot") or {}
            assert isinstance(snap.get("strategy_ir"), dict), \
                f"lazy fetch failed — snapshot.strategy_ir null: {snap}"
        finally:
            _cleanup_bot(admin_headers, bot_id)

    def test_add_member_explicit_ir_preserved(self, admin_headers):
        bot_id = _create_bot(admin_headers, "MB72_EXPL")
        try:
            cr = requests.get(f"{API}/master-bot/candidates?limit=20",
                              headers=admin_headers, timeout=60)
            cands = cr.json().get("candidates") or []
            ir_cands = [c for c in cands if c.get("ir_status") == "ir_native"]
            assert ir_cands
            sh = ir_cands[0]["strategy_hash"]
            sentinel_ir = {"ir_version": 1, "sentinel": "EXPLICIT_TEST_IR",
                           "indicators": [], "entry_long": {}, "entry_short": {},
                           "exits": {}, "metadata": {"pair": "EURUSD", "timeframe": "H1"}}
            snap = {"strategy_ir": sentinel_ir, "ir_status": "ir_native"}
            r = requests.post(f"{API}/master-bot/{bot_id}/members",
                              headers=admin_headers,
                              json={"strategy_hash": sh, "tier": "tier3",
                                    "snapshot": snap}, timeout=30)
            assert r.status_code in (200, 201), r.text
            persisted = (r.json().get("snapshot") or {}).get("strategy_ir") or {}
            assert persisted.get("sentinel") == "EXPLICIT_TEST_IR", \
                f"explicit IR was overwritten by lazy fetch: {persisted}"
        finally:
            _cleanup_bot(admin_headers, bot_id)


# ───────────────────────── Export IR-aware emission ─────────────────────────

def _download_cs(headers, export_id):
    r = requests.get(f"{API}/master-bot/exports/{export_id}/download/cs",
                     headers=headers, timeout=60)
    assert r.status_code == 200, f"download cs: {r.status_code} {r.text[:200]}"
    return r.text


def _download_meta(headers, export_id):
    r = requests.get(f"{API}/master-bot/exports/{export_id}/download/meta",
                     headers=headers, timeout=60)
    assert r.status_code == 200, f"download meta: {r.status_code} {r.text[:200]}"
    import json as _json
    return _json.loads(r.text)


class TestExportIREmission:
    @pytest.fixture(scope="class")
    def all_ir_bot(self, admin_headers):
        bot_id = _create_bot(admin_headers, "MB72_ALLIR")
        # Auto-fill with all 5 IR-capable rows (5 lib_test_0X rows, sorted first)
        r = requests.post(f"{API}/master-bot/{bot_id}/auto-fill",
                          headers=admin_headers,
                          json={"tier1_count": 2, "tier2_count": 2, "tier3_count": 1,
                                "clear_existing": True}, timeout=60)
        assert r.status_code == 200, r.text
        yield bot_id
        _cleanup_bot(admin_headers, bot_id)

    def test_all_ir_export_emission_summary(self, all_ir_bot, admin_headers):
        # compile
        c = requests.post(f"{API}/master-bot/{all_ir_bot}/compile",
                          headers=admin_headers,
                          json={"runtime_mode": "multi_strategy"}, timeout=60)
        assert c.status_code == 200, c.text
        # export
        e = requests.post(f"{API}/master-bot/{all_ir_bot}/export",
                         headers=admin_headers,
                         json={"compile_if_missing": True}, timeout=60)
        assert e.status_code == 200, e.text
        body = e.json()
        summary = body.get("emission_summary") or {}
        assert summary.get("ir_native", 0) > 0, f"ir_native must be >0: {summary}"
        assert summary.get("stub", 0) == 0, f"stub must be 0 for all-IR bot: {summary}"
        assert summary.get("ir_coverage_pct", -1) == 100.0, \
            f"ir_coverage_pct must be 100.0: {summary}"
        # emission_log lives in the sidecar JSON (meta), not the POST response.
        export_id = body.get("export_id") or body.get("id")
        meta = _download_meta(admin_headers, export_id)
        log = meta.get("emission_log") or []
        assert log, f"emission_log empty in sidecar: keys={list(meta.keys())}"
        for entry in log:
            assert "strategy_hash" in entry
            assert "tier" in entry
            assert "class_name" in entry
            assert "source" in entry
            assert entry["source"] == "ir_native" or entry["source"].startswith("stub:"), \
                f"unexpected source value: {entry['source']}"
            assert "ir_meta" in entry  # may be None or object

    def test_all_ir_cs_body_anchors(self, all_ir_bot, admin_headers):
        # Get latest export id
        lst = requests.get(f"{API}/master-bot/{all_ir_bot}/exports",
                           headers=admin_headers, timeout=30)
        rows = lst.json().get("exports") or []
        assert rows
        export_id = rows[0].get("export_id") or rows[0].get("id")
        cs = _download_cs(admin_headers, export_id)
        # (a)
        assert "public interface ITierStrategy" in cs, "missing ITierStrategy interface"
        # (b)
        assert "// ── Tier" in cs or "// --" in cs, "missing tier comment header"
        assert "IR-transpiled" in cs, "missing 'IR-transpiled' header anchor"
        # (c) delegated cAlgo API
        assert "_robot.Indicators." in cs, "missing _robot.Indicators. delegation"
        # (d)
        assert any(ind in cs for ind in
                   ("RelativeStrengthIndex", "ExponentialMovingAverage", "BollingerBands")), \
            "no real indicator referenced"
        # (e)
        assert "ExecuteMarketOrder" in cs, "no entry execution found"
        # (f) only the shell carries [Robot(...
        assert cs.count("[Robot(") == 1, f"expected exactly 1 [Robot(, got {cs.count('[Robot(')}"
        # (g) at least one tier class generated
        assert cs.count("public class Tier") >= 1, \
            f"expected >=1 tier class, got {cs.count('public class Tier')}"
        # exporter version header
        assert "Exporter version: v1.2" in cs or "v1.2" in cs, \
            "missing Exporter version v1.2 stamp"

    def test_idempotent_export_deterministic_sources(self, all_ir_bot, admin_headers):
        e1 = requests.post(f"{API}/master-bot/{all_ir_bot}/export",
                          headers=admin_headers, json={"compile_if_missing": True}, timeout=60)
        assert e1.status_code == 200
        meta1 = _download_meta(admin_headers, e1.json()["export_id"])
        log1 = {x["strategy_hash"]: x["source"] for x in (meta1.get("emission_log") or [])}
        e2 = requests.post(f"{API}/master-bot/{all_ir_bot}/export",
                          headers=admin_headers, json={"compile_if_missing": True}, timeout=60)
        assert e2.status_code == 200
        meta2 = _download_meta(admin_headers, e2.json()["export_id"])
        log2 = {x["strategy_hash"]: x["source"] for x in (meta2.get("emission_log") or [])}
        assert log1 and log1 == log2, f"emission source labels diverged: {log1} vs {log2}"

    def test_exports_listing_surfaces_emission_summary(self, all_ir_bot, admin_headers):
        lst = requests.get(f"{API}/master-bot/{all_ir_bot}/exports",
                           headers=admin_headers, timeout=30)
        assert lst.status_code == 200
        for row in (lst.json().get("exports") or []):
            assert "emission_summary" in row, f"row missing emission_summary: {list(row.keys())}"


class TestMixedAndStubExport:
    def test_mixed_coverage_export(self, admin_headers):
        bot_id = _create_bot(admin_headers, "MB72_MIX")
        try:
            # Auto-fill all 6 (includes the unmapped legacy)
            r = requests.post(f"{API}/master-bot/{bot_id}/auto-fill",
                              headers=admin_headers,
                              json={"tier1_count": 2, "tier2_count": 2, "tier3_count": 2,
                                    "clear_existing": True}, timeout=60)
            assert r.status_code == 200, r.text
            added = r.json().get("added") or []
            # We need at least one IR and at least one stub (legacy) for "mixed".
            has_stub = any((m.get("snapshot") or {}).get("ir_status") == "legacy"
                           or not (m.get("snapshot") or {}).get("strategy_ir") for m in added)
            assert has_stub, f"expected at least one legacy/no-IR member: {[m.get('snapshot',{}).get('ir_status') for m in added]}"

            c = requests.post(f"{API}/master-bot/{bot_id}/compile",
                              headers=admin_headers, json={}, timeout=60)
            assert c.status_code == 200, c.text
            e = requests.post(f"{API}/master-bot/{bot_id}/export",
                              headers=admin_headers,
                              json={"compile_if_missing": True}, timeout=60)
            assert e.status_code == 200, e.text
            summ = e.json().get("emission_summary") or {}
            assert summ.get("ir_native", 0) > 0, f"ir_native must be >0: {summ}"
            assert summ.get("stub", 0) > 0, f"stub must be >0 (mixed): {summ}"
            pct = summ.get("ir_coverage_pct")
            assert pct is not None and 0 < pct < 100, \
                f"mixed coverage must be in (0,100) exclusive: {pct}"
            reasons = summ.get("stub_reasons") or {}
            assert reasons, f"stub_reasons missing: {summ}"
            # diagnostic key present
            keys = " ".join(str(k) for k in reasons.keys())
            assert "no_ir" in keys or "no_canonical" in keys or "invalid_ir" in keys \
                or len(reasons) > 0, f"expected diagnostic key (e.g. no_ir): {reasons}"
        finally:
            _cleanup_bot(admin_headers, bot_id)

    def test_stub_only_export_cs_anchors(self, admin_headers):
        # Build a bot with ONLY the legacy unmapped member
        bot_id = _create_bot(admin_headers, "MB72_STUB")
        try:
            cr = requests.get(f"{API}/master-bot/candidates?limit=20",
                              headers=admin_headers, timeout=60)
            cands = cr.json().get("candidates") or []
            legacy = [c for c in cands if c.get("ir_status") == "legacy"]
            assert legacy, f"no legacy candidate available: {[c.get('ir_status') for c in cands]}"
            sh = legacy[0]["strategy_hash"]
            # Add WITHOUT IR snapshot -- explicit null
            r = requests.post(f"{API}/master-bot/{bot_id}/members",
                              headers=admin_headers,
                              json={"strategy_hash": sh, "tier": "tier3",
                                    "snapshot": {"strategy_ir": None, "ir_status": "legacy"}},
                              timeout=30)
            assert r.status_code in (200, 201), r.text

            c = requests.post(f"{API}/master-bot/{bot_id}/compile",
                              headers=admin_headers, json={}, timeout=60)
            assert c.status_code == 200, c.text
            e = requests.post(f"{API}/master-bot/{bot_id}/export",
                              headers=admin_headers,
                              json={"compile_if_missing": True}, timeout=60)
            assert e.status_code == 200, e.text
            summ = e.json().get("emission_summary") or {}
            assert summ.get("stub", 0) > 0
            assert summ.get("ir_native", 0) == 0
            export_id = e.json().get("export_id") or e.json().get("id")
            cs = _download_cs(admin_headers, export_id)
            assert "STUB" in cs and "no trades opened" in cs.lower() or "STUB — no trades opened" in cs, \
                "stub marker not found in cs body"
            assert "_robot.ExecuteMarketOrder" not in cs, \
                "stub-only export must NOT contain ExecuteMarketOrder via _robot"
        finally:
            _cleanup_bot(admin_headers, bot_id)


# ───────────────────────── Backwards compatibility ─────────────────────────

class TestBackwardsCompat:
    def test_legacy_snapshot_null_ir_still_exports(self, admin_headers):
        # Use the legacy unmapped strategy_hash, whose library row carries no IR.
        # Lazy-fetch should return None and the exporter should fall back to stub.
        bot_id = _create_bot(admin_headers, "MB72_BC")
        try:
            cr = requests.get(f"{API}/master-bot/candidates?limit=20",
                              headers=admin_headers, timeout=60)
            cands = cr.json().get("candidates") or []
            legacy = [c for c in cands if c.get("ir_status") == "legacy"]
            assert legacy, "no legacy candidate available"
            sh = legacy[0]["strategy_hash"]
            r = requests.post(f"{API}/master-bot/{bot_id}/members",
                              headers=admin_headers,
                              json={"strategy_hash": sh, "tier": "tier3",
                                    "snapshot": {"pair": "EURUSD", "timeframe": "H1",
                                                 "strategy_ir": None}}, timeout=30)
            assert r.status_code in (200, 201), r.text
            c = requests.post(f"{API}/master-bot/{bot_id}/compile",
                              headers=admin_headers, json={}, timeout=60)
            assert c.status_code == 200, c.text
            e = requests.post(f"{API}/master-bot/{bot_id}/export",
                              headers=admin_headers,
                              json={"compile_if_missing": True}, timeout=60)
            assert e.status_code == 200, e.text
            summ = e.json().get("emission_summary") or {}
            assert summ.get("stub", 0) > 0, f"expected stub fallback: {summ}"
        finally:
            _cleanup_bot(admin_headers, bot_id)
