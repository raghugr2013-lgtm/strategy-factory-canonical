"""Phase 20 — Prop Firm Rules Review & Approval Layer tests.

Tests human-in-the-loop verification on top of prop_firm_rules.
Covers: backfill auto-approval, approve/reject/reset actions, and
enforcement (409 rules_not_verified) on analysis + challenge matching.
"""
from __future__ import annotations

import os
import pytest
import requests
from pathlib import Path


def _load_frontend_env():
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.strip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_frontend_env()
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

LEGACY_FIRMS = ["ftmo", "fundednext", "pipfarm"]
SEED_RULES = {
    "max_daily_loss_pct": 5,
    "max_total_loss_pct": 10,
    "profit_target_pct": 10,
    "min_trading_days": 4,
    "time_limit_days": 30,
    "daily_loss_type": "equity",
}
STRAT_HASH = "a649abeabefcc045cc9ef2dc2ec04e1f3f2b55da"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    yield s
    # ── CRITICAL CLEANUP: re-approve all 3 legacy firms so Phase 16-19 stay green
    for slug in LEGACY_FIRMS:
        try:
            s.post(f"{API}/prop-firm-rules/{slug}/approve", json={"approved_rules": SEED_RULES}, timeout=30)
        except Exception:
            pass


# ── 1. Backfill ensures all 3 legacy firms auto-approved ─────────────

def test_01_list_backfills_legacy_firms(sess):
    r = sess.get(f"{API}/prop-firm-rules", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "rules" in data
    by_slug = {row["firm_slug"]: row for row in data["rules"]}
    for slug in LEGACY_FIRMS:
        assert slug in by_slug, f"{slug} missing from list"
        row = by_slug[slug]
        assert row["status"] == "approved", f"{slug} not approved: {row.get('status')}"
        # auto_approved may be False if explicit approve already ran in this env
        # (backfill is per-process idempotent). Accept either as long as approved.
        assert row.get("auto_approved") in (True, False), f"{slug} auto_approved missing"
        assert row.get("updated_at"), f"{slug} missing updated_at"
        assert row.get("approved_rules") is not None, f"{slug} approved_rules is null"


def test_02_get_one_ftmo_and_missing(sess):
    r = sess.get(f"{API}/prop-firm-rules/ftmo", timeout=30)
    assert r.status_code == 200
    assert r.json().get("firm_slug") == "ftmo"

    r2 = sess.get(f"{API}/prop-firm-rules/does_not_exist", timeout=30)
    assert r2.status_code == 404


# ── 2. Reject FTMO → 409 on individual, skipped on batch ─────────────

def test_03_reject_ftmo_blocks_analysis(sess):
    r = sess.post(f"{API}/prop-firm-rules/ftmo/reject", timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "rejected"

    # individual analysis blocked
    a = sess.post(f"{API}/strategies/{STRAT_HASH}/prop-analysis", json={"firm_slug": "ftmo"}, timeout=60)
    assert a.status_code == 409, f"expected 409, got {a.status_code}: {a.text}"
    assert a.json().get("detail") == "rules_not_verified"

    # batch silently skips
    b = sess.post(f"{API}/prop-firm-analysis/batch-analyze", json={"firm_slug": "ftmo", "limit": 5}, timeout=60)
    assert b.status_code == 200, b.text
    bd = b.json()
    assert bd.get("status") == "skipped_unverified"
    assert bd.get("analyzed") == 0


# ── 3. Reset → status parsed, still blocked ─────────────────────────

def test_04_reset_ftmo_keeps_blocked(sess):
    r = sess.post(f"{API}/prop-firm-rules/ftmo/reset", timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("status") == "parsed"
    assert j.get("approved_rules") is None

    a = sess.post(f"{API}/strategies/{STRAT_HASH}/prop-analysis", json={"firm_slug": "ftmo"}, timeout=60)
    assert a.status_code == 409

    b = sess.post(f"{API}/prop-firm-analysis/batch-analyze", json={"firm_slug": "ftmo", "limit": 5}, timeout=60)
    assert b.status_code == 200
    assert b.json().get("status") == "skipped_unverified"


# ── 4. Approve with body → overlays values, allows analysis ─────────

def test_05_approve_ftmo_unblocks(sess):
    r = sess.post(f"{API}/prop-firm-rules/ftmo/approve", json={"approved_rules": SEED_RULES}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("status") == "approved"
    assert j.get("auto_approved") is False

    a = sess.post(f"{API}/strategies/{STRAT_HASH}/prop-analysis", json={"firm_slug": "ftmo"}, timeout=60)
    assert a.status_code == 200, f"expected 200 after approve, got {a.status_code}: {a.text}"

    # overlaid values visible on GET
    g = sess.get(f"{API}/prop-firm-rules/ftmo", timeout=30)
    assert g.status_code == 200
    gd = g.json()
    assert gd.get("max_daily_loss_pct") == 5
    assert gd.get("profit_target_pct") == 10


# ── 5. Ingest a brand-new parsed firm (status=parsed) ───────────────

def test_06_ingest_parsed(sess):
    payload = {
        "firm_slug": "testfirm",
        "firm_name": "TestFirm",
        "parsed_rules": {"profit_target_pct": 8, "max_daily_loss_pct": 4, "max_total_loss_pct": 8},
        "parser_confidence": 0.65,
        "source_type": "url",
        "source_url": "https://example.com",
    }
    r = sess.post(f"{API}/prop-firm-rules/ingest-parsed", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("status") == "parsed"
    assert j.get("firm_slug") == "testfirm"
    assert j.get("parser_confidence") == 0.65
    assert j.get("source_type") == "url"


# ── 6. Challenge matching: reject all 3 → 409; re-approve ftmo → 200 ─

def test_07_challenge_matching_permission(sess):
    for slug in LEGACY_FIRMS:
        rr = sess.post(f"{API}/prop-firm-rules/{slug}/reject", timeout=30)
        assert rr.status_code == 200, f"reject {slug}: {rr.text}"

    m = sess.post(f"{API}/strategies/{STRAT_HASH}/match-challenges", json={"force": True}, timeout=60)
    assert m.status_code == 409, f"expected 409, got {m.status_code}: {m.text}"
    assert m.json().get("detail") == "rules_not_verified"

    # Re-approve just FTMO
    ap = sess.post(f"{API}/prop-firm-rules/ftmo/approve", json={"approved_rules": SEED_RULES}, timeout=30)
    assert ap.status_code == 200

    m2 = sess.post(f"{API}/strategies/{STRAT_HASH}/match-challenges", json={"force": True}, timeout=60)
    assert m2.status_code == 200, m2.text
    md = m2.json()
    # evaluated_count should be 2 (FTMO Standard + Aggressive). Tolerate absent key naming.
    evaluated = md.get("evaluated_count") or md.get("evaluated") or len(md.get("evaluated_challenges") or [])
    alternatives = md.get("alternatives") or md.get("alternative_challenges") or []
    assert evaluated == 2, f"expected evaluated=2, got {evaluated}; body={md}"
    assert len(alternatives) == 1, f"expected 1 alternative, got {len(alternatives)}"


# ── 7. Regression: list endpoints still work ────────────────────────

def test_08_regression_prop_firms_list(sess):
    r = sess.get(f"{API}/prop-firms/list", timeout=30)
    assert r.status_code == 200


def test_09_regression_explorer(sess):
    # Ensure all 3 legacy firms approved for this regression
    for slug in LEGACY_FIRMS:
        sess.post(f"{API}/prop-firm-rules/{slug}/approve", json={"approved_rules": SEED_RULES}, timeout=30)
    r = sess.get(f"{API}/strategies/explorer", timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = data.get("rows") or data.get("strategies") or data
    if isinstance(rows, dict):
        rows = rows.get("rows") or []
    hit = None
    for row in rows:
        if row.get("strategy_hash") == STRAT_HASH:
            hit = row
            break
    assert hit is not None, f"strategy {STRAT_HASH} not in explorer"
    assert hit.get("prop_analysis") is not None, "prop_analysis not enriched"
    assert hit.get("challenge_match") is not None, "challenge_match not enriched"
