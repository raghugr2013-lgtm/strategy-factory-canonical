"""MB-7.1 (mode-specific dispatchers) + MB-10 (export-time parity gate).

Tests cover:
- MB-7.1: multi_strategy / single_active / regime_aware emit distinct .cs
- MB-7.1: shell invariants (single [Robot(, Tier class, ITierStrategy iface)
- MB-7.1: EXPORTER_VERSION == v1.3 in header
- MB-10: gate-status, parity/preview, default-OFF backwards compat
- MB-10: env-toggled enforcement (block + force_parity override)
- MB-10: seeded PASSED sign-offs → clean export
- MB-10: seeded FAILED sign-off → 409 with verdict details
- MB-10: non-admin RBAC on /export + read access on /parity/*

NOTE: A few tests toggle MB_PARITY_GATE_ENABLED in /app/backend/.env and
restart the backend via supervisorctl. The teardown_module hook restores
the .env to gate-OFF state.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest
import requests
from pymongo import MongoClient

def _load_react_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url
    fe_env = Path("/app/frontend/.env")
    if fe_env.exists():
        for ln in fe_env.read_text().splitlines():
            if ln.startswith("REACT_APP_BACKEND_URL"):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_react_url().rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "AdminTest123!"

ENV_PATH = Path("/app/backend/.env")
PARITY_FLAG = "MB_PARITY_GATE_ENABLED"
SIGNOFF_COLL = "cbot_parity_signoff"


# ──────────────────────── helpers ────────────────────────

def _backend_env_value() -> str:
    txt = ENV_PATH.read_text()
    m = re.search(rf"^{PARITY_FLAG}\s*=\s*(.*)$", txt, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _set_parity_env(value: str | None) -> None:
    """Set or remove MB_PARITY_GATE_ENABLED in /app/backend/.env, then
    restart backend. value=None removes the line."""
    txt = ENV_PATH.read_text()
    # strip any existing
    new_lines = [ln for ln in txt.splitlines() if not ln.strip().startswith(f"{PARITY_FLAG}=")]
    if value is not None:
        new_lines.append(f"{PARITY_FLAG}={value}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n")
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True,
                   capture_output=True, timeout=30)
    # wait for backend to be reachable again
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            r = requests.get(f"{API}/health", timeout=2)
            if r.status_code in (200, 404):  # 404 also OK — server is up
                break
        except Exception:
            pass
        time.sleep(0.5)
    time.sleep(1.0)  # belt-and-braces


def _mongo():
    cli = MongoClient(os.environ["MONGO_URL"])
    return cli, cli[os.environ["DB_NAME"]]


def teardown_module(module):
    """Always restore gate-OFF state for next agent / dev."""
    try:
        _set_parity_env(None)
    except Exception:
        pass


# ──────────────────────── fixtures ────────────────────────

@pytest.fixture(scope="module")
def admin_headers() -> dict:
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"admin login: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def non_admin_headers(admin_headers) -> dict:
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.local"
    pw = "UserTest123!"
    r = requests.post(f"{API}/auth/signup", json={"email": email, "password": pw},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    user_id = (body.get("user") or body).get("id") \
        or (body.get("user") or body).get("user_id")
    if not user_id:
        lu = requests.get(f"{API}/admin/users?status=pending",
                          headers=admin_headers, timeout=30).json()
        for u in lu.get("users", []):
            if (u.get("email") or "").lower() == email.lower():
                user_id = u.get("user_id") or u.get("id")
                break
    assert user_id
    requests.post(f"{API}/admin/approve/{user_id}", headers=admin_headers,
                  timeout=30)
    lr = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": pw}, timeout=30)
    token = lr.json().get("token") or lr.json().get("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def filled_bot(admin_headers) -> str:
    """Fresh bot, auto-filled (uses candidate pool)."""
    name = f"MB_TEST_MB71_{uuid.uuid4().hex[:6]}"
    cr = requests.post(f"{API}/master-bot", headers=admin_headers,
                       json={"name": name}, timeout=30)
    assert cr.status_code in (200, 201), cr.text
    mb_id = cr.json()["id"]
    fr = requests.post(f"{API}/master-bot/{mb_id}/auto-fill",
                       headers=admin_headers,
                       json={"tier1_count": 2, "tier2_count": 2, "tier3_count": 0},
                       timeout=60)
    assert fr.status_code == 200, fr.text
    assert fr.json().get("added_count", 0) >= 1, fr.json()
    yield mb_id
    requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                    headers=admin_headers, timeout=30)


def _compile_export_download(mb_id: str, admin_headers: dict, mode: str) -> str:
    """Compile in `mode`, export, download .cs, return decoded text."""
    cr = requests.post(f"{API}/master-bot/{mb_id}/compile",
                       headers=admin_headers,
                       json={"runtime_mode": mode}, timeout=60)
    assert cr.status_code == 200, f"[{mode}] compile: {cr.status_code} {cr.text}"
    er = requests.post(f"{API}/master-bot/{mb_id}/export",
                       headers=admin_headers, json={}, timeout=60)
    assert er.status_code == 200, f"[{mode}] export: {er.status_code} {er.text}"
    export_id = er.json()["export_id"]
    dl = requests.get(f"{API}/master-bot/exports/{export_id}/download/cs",
                      headers=admin_headers, timeout=30)
    assert dl.status_code == 200, dl.text
    return dl.text


# ════════════════════════════════════════════════════════════════════
# MB-7.1 — mode-specific dispatchers
# ════════════════════════════════════════════════════════════════════

class TestMB71Dispatchers:
    def test_multi_strategy_emits_no_dispatcher_helpers(self, admin_headers, filled_bot):
        cs = _compile_export_download(filled_bot, admin_headers, "multi_strategy")
        assert "// Mode: multi_strategy" in cs
        assert "PickActive()" not in cs
        assert "ClassifyRegime()" not in cs
        assert "COOLDOWN_SEC" not in cs
        assert "MIN_REGIME_FITNESS" not in cs

    def test_single_active_emits_pickactive_and_cooldown(self, admin_headers, filled_bot):
        cs = _compile_export_download(filled_bot, admin_headers, "single_active")
        assert "// Mode: single_active" in cs
        assert "// Mode: multi_strategy" not in cs
        assert "PickActive()" in cs
        assert "COOLDOWN_SEC = 900" in cs
        assert "_cooldownUntil" in cs
        assert "try" in cs and "catch (Exception ex)" in cs
        assert "ClassifyRegime()" not in cs

    def test_regime_aware_emits_classifyregime_honest_refusal(self, admin_headers, filled_bot):
        cs = _compile_export_download(filled_bot, admin_headers, "regime_aware")
        assert "// Mode: regime_aware" in cs
        assert "ClassifyRegime()" in cs
        assert "MIN_REGIME_FITNESS = 0.20" in cs
        assert "REGIME_WINDOW_BARS = 50" in cs
        assert 'regime == "unknown"' in cs
        assert "PickActive()" not in cs
        assert "// Mode: multi_strategy" not in cs

    def test_shell_invariants_all_modes(self, admin_headers, filled_bot):
        for mode in ("multi_strategy", "single_active", "regime_aware"):
            cs = _compile_export_download(filled_bot, admin_headers, mode)
            robot_count = len(re.findall(r"\[Robot\(", cs))
            assert robot_count == 1, f"[{mode}] expected 1 [Robot(, got {robot_count}"
            assert re.search(r"public\s+class\s+Tier\w*", cs), \
                f"[{mode}] no `public class Tier...` found"
            assert "public interface ITierStrategy" in cs, \
                f"[{mode}] missing ITierStrategy interface"

    def test_exporter_version_v13_in_header(self, admin_headers, filled_bot):
        cs = _compile_export_download(filled_bot, admin_headers, "multi_strategy")
        # header comment + EXPORTER_VERSION constant
        assert 'EXPORTER_VERSION' in cs
        assert '"v1.3"' in cs or "'v1.3'" in cs


# ════════════════════════════════════════════════════════════════════
# MB-10 — parity gate
# ════════════════════════════════════════════════════════════════════

class TestMB10GateStatusDefaultOff:
    def test_gate_status_default_off(self, admin_headers):
        # Ensure clean default-OFF state for this test
        _set_parity_env(None)
        r = requests.get(f"{API}/master-bot/parity/gate-status",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["enabled"] is False
        assert d["env_var"] == "MB_PARITY_GATE_ENABLED"
        assert isinstance(d.get("override_via"), str) and "force_parity" in d["override_via"]

    def test_gate_status_accessible_to_non_admin(self, non_admin_headers):
        r = requests.get(f"{API}/master-bot/parity/gate-status",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["enabled"] is False


class TestMB10PreviewVerdict:
    def test_preview_returns_structured_verdict(self, admin_headers, filled_bot):
        # Ensure a compile exists
        requests.post(f"{API}/master-bot/{filled_bot}/compile",
                      headers=admin_headers, json={"runtime_mode": "multi_strategy"},
                      timeout=60)
        r = requests.get(f"{API}/master-bot/{filled_bot}/parity/preview",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        v = r.json()
        required = {"revision_id", "enforced", "would_block", "total_enabled",
                    "passed_count", "failed_count", "missing_count",
                    "per_member", "checked_at", "policy"}
        missing = required - set(v.keys())
        assert not missing, f"missing keys: {missing}"
        assert v["enforced"] is False  # gate OFF
        assert v["total_enabled"] >= 1
        # With no sign-offs (likely), missing == total_enabled, would_block True
        # (lib_test_* may have PASSED rows; just assert consistency)
        assert v["passed_count"] + v["failed_count"] + v["missing_count"] == v["total_enabled"]
        assert v["would_block"] == ((v["failed_count"] + v["missing_count"]) > 0)
        assert isinstance(v["per_member"], list)

    def test_preview_accessible_to_non_admin(self, non_admin_headers, admin_headers, filled_bot):
        # ensure a definition exists
        requests.post(f"{API}/master-bot/{filled_bot}/compile",
                      headers=admin_headers, json={"runtime_mode": "multi_strategy"},
                      timeout=60)
        r = requests.get(f"{API}/master-bot/{filled_bot}/parity/preview",
                         headers=non_admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_preview_nonexistent_bot_404(self, admin_headers):
        r = requests.get(f"{API}/master-bot/no_such_bot_xyz/parity/preview",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 404, r.text


class TestMB10GateOffBackwardsCompat:
    def test_export_succeeds_with_advisory_verdict_when_gate_off(
        self, admin_headers, filled_bot,
    ):
        _set_parity_env(None)  # ensure off
        # Re-fetch token because backend restarted
        lr = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=30)
        token = lr.json().get("token") or lr.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        requests.post(f"{API}/master-bot/{filled_bot}/compile",
                      headers=headers, json={"runtime_mode": "multi_strategy"},
                      timeout=60)
        r = requests.post(f"{API}/master-bot/{filled_bot}/export",
                          headers=headers, json={}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("parity_gate_enabled") is False
        assert d.get("parity_overridden") is False
        verdict = d.get("parity_verdict")
        assert verdict is not None, "expected advisory verdict in export row"
        assert "would_block" in verdict
        assert "total_enabled" in verdict


class TestMB10GateOnEnforcement:
    """Toggle env ON via .env + restart; verify blocking + override + signoff seeding."""

    @pytest.fixture(scope="class")
    def gate_on_admin_headers(self):
        _set_parity_env("1")
        # Re-login after backend restart
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=30)
        assert r.status_code == 200, r.text
        token = r.json().get("token") or r.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def gate_on_bot(self, gate_on_admin_headers):
        """Fresh filled bot for gate-on tests so we can manipulate sign-offs."""
        name = f"MB_TEST_GATE_{uuid.uuid4().hex[:6]}"
        cr = requests.post(f"{API}/master-bot", headers=gate_on_admin_headers,
                           json={"name": name}, timeout=30)
        assert cr.status_code in (200, 201), cr.text
        mb_id = cr.json()["id"]
        fr = requests.post(f"{API}/master-bot/{mb_id}/auto-fill",
                           headers=gate_on_admin_headers,
                           json={"tier1_count": 2, "tier2_count": 1, "tier3_count": 0},
                           timeout=60)
        assert fr.status_code == 200, fr.text
        assert fr.json().get("added_count", 0) >= 2, fr.json()
        yield mb_id
        requests.delete(f"{API}/master-bot/{mb_id}?hard=true",
                        headers=gate_on_admin_headers, timeout=30)

    def _enabled_member_hashes(self, admin_headers, mb_id) -> List[str]:
        r = requests.get(f"{API}/master-bot/{mb_id}", headers=admin_headers,
                         timeout=30)
        doc = r.json()
        hashes = []
        # API returns `members_by_tier`: {tier_key: [member_doc, ...]}
        for tier_key, members in (doc.get("members_by_tier") or {}).items():
            for m in members or []:
                if m.get("enabled", True):
                    hashes.append(m["strategy_hash"])
        # Fallback for older shape
        if not hashes:
            for t in doc.get("tiers", []):
                for m in t.get("members", []):
                    if m.get("enabled", True):
                        hashes.append(m["strategy_hash"])
        return hashes

    def test_a_gate_status_enabled(self, gate_on_admin_headers):
        r = requests.get(f"{API}/master-bot/parity/gate-status",
                         headers=gate_on_admin_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_b_export_blocks_when_signoffs_missing(self, gate_on_admin_headers, gate_on_bot):
        # Clear any pre-existing signoffs for this bot's members
        _, db = _mongo()
        hashes = self._enabled_member_hashes(gate_on_admin_headers, gate_on_bot)
        assert hashes, "expected enabled members"
        db[SIGNOFF_COLL].delete_many({"strategy_hash": {"$in": hashes}})
        # compile
        requests.post(f"{API}/master-bot/{gate_on_bot}/compile",
                      headers=gate_on_admin_headers,
                      json={"runtime_mode": "multi_strategy"}, timeout=60)
        r = requests.post(f"{API}/master-bot/{gate_on_bot}/export",
                          headers=gate_on_admin_headers, json={}, timeout=60)
        assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
        body = r.json()
        detail = body.get("detail") or {}
        assert detail.get("error") == "parity_gate_blocked"
        msg = detail.get("message") or ""
        assert "parity gate blocked export" in msg
        assert "force_parity=true" in msg
        v = detail.get("verdict") or {}
        assert v.get("would_block") is True
        assert v.get("missing_count", 0) >= 1

    def test_c_force_parity_override_returns_200(self, gate_on_admin_headers, gate_on_bot):
        r = requests.post(f"{API}/master-bot/{gate_on_bot}/export",
                          headers=gate_on_admin_headers,
                          json={"force_parity": True}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("parity_overridden") is True
        assert d.get("parity_gate_enabled") is True
        v = d.get("parity_verdict") or {}
        assert v.get("would_block") is True, "verdict still computed for audit"

    def test_d_all_passed_signoffs_clean_export(self, gate_on_admin_headers, gate_on_bot):
        _, db = _mongo()
        hashes = self._enabled_member_hashes(gate_on_admin_headers, gate_on_bot)
        assert hashes
        now = datetime.now(timezone.utc).isoformat()
        for h in hashes:
            db[SIGNOFF_COLL].update_one(
                {"strategy_hash": h},
                {"$set": {
                    "strategy_hash": h,
                    "status": "PASSED",
                    "fixtures_passed": 5,
                    "fixtures_total": 5,
                    "signed_at": now,
                    "notes": "TEST_seed PASSED for mb10 gate test",
                    "parity_mode": "TEST",
                }},
                upsert=True,
            )
        try:
            r = requests.post(f"{API}/master-bot/{gate_on_bot}/export",
                              headers=gate_on_admin_headers, json={}, timeout=60)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d.get("parity_overridden") is False
            v = d.get("parity_verdict") or {}
            assert v.get("would_block") is False, f"expected would_block False, got {v}"
            assert v.get("passed_count") == v.get("total_enabled"), v
            assert v.get("failed_count", 0) == 0
            assert v.get("missing_count", 0) == 0
        finally:
            # cleanup our test seeds
            db[SIGNOFF_COLL].delete_many(
                {"strategy_hash": {"$in": hashes},
                 "notes": "TEST_seed PASSED for mb10 gate test"})

    def test_e_one_failed_signoff_blocks(self, gate_on_admin_headers, gate_on_bot):
        _, db = _mongo()
        hashes = self._enabled_member_hashes(gate_on_admin_headers, gate_on_bot)
        assert len(hashes) >= 2
        now = datetime.now(timezone.utc).isoformat()
        # seed: all PASSED, then flip first to FAILED
        for h in hashes:
            db[SIGNOFF_COLL].update_one(
                {"strategy_hash": h},
                {"$set": {
                    "strategy_hash": h,
                    "status": "PASSED",
                    "fixtures_passed": 5,
                    "fixtures_total": 5,
                    "signed_at": now,
                    "notes": "TEST_seed_mb10_failed_test",
                }},
                upsert=True,
            )
        failed_hash = hashes[0]
        db[SIGNOFF_COLL].update_one(
            {"strategy_hash": failed_hash},
            {"$set": {"status": "FAILED",
                      "notes": "TEST_seed_mb10_failed_test (forced FAILED)"}},
        )
        try:
            r = requests.post(f"{API}/master-bot/{gate_on_bot}/export",
                              headers=gate_on_admin_headers, json={}, timeout=60)
            assert r.status_code == 409, r.text
            detail = r.json().get("detail") or {}
            v = detail.get("verdict") or {}
            assert v.get("failed_count", 0) >= 1, v
            per_member = v.get("per_member") or []
            failed_entries = [p for p in per_member if p.get("verdict") == "FAILED"]
            assert any(p.get("strategy_hash") == failed_hash for p in failed_entries), \
                f"expected {failed_hash} in failed entries, got {failed_entries}"
        finally:
            db[SIGNOFF_COLL].delete_many(
                {"strategy_hash": {"$in": hashes},
                 "notes": {"$regex": "TEST_seed_mb10_failed_test"}})


class TestMB10NonAdminRBAC:
    def test_non_admin_cannot_export(self, non_admin_headers, filled_bot):
        r = requests.post(f"{API}/master-bot/{filled_bot}/export",
                          headers=non_admin_headers, json={}, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


class TestMB10Cleanup:
    """Final teardown — leave the pod in default-OFF state."""

    def test_cleanup_gate_off_after_env_removal(self, admin_headers):
        _set_parity_env(None)
        # Re-login (token still valid usually, but be safe)
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=30)
        token = r.json().get("token") or r.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        gs = requests.get(f"{API}/master-bot/parity/gate-status",
                          headers=headers, timeout=30)
        assert gs.status_code == 200
        assert gs.json()["enabled"] is False
        # also confirm .env no longer has the line
        assert not _backend_env_value()
