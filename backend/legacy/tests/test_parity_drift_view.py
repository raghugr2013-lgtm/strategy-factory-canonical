"""MB-9 Phase 2.A — Parity Drift Aggregator tests.

The pure decision function ``decide_drift_from_timeline`` is unit-tested
in isolation with synthetic sign-off rows. Mongo-backed wrappers
``compute_drift_for_deployment`` / ``compute_drift_for_all_live`` are
exercised with isolated TEST_ rows that are cleaned up at teardown.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest
import pytest_asyncio

from engines import parity_drift_view as pdv
from engines.db import get_db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sign_row(
    *, days_ago: float, strategy_hash: str = "test_strat",
    htf: str = "WITHIN_TOLERANCE", trade_passed: bool = True,
    status: str = "PASSED",
) -> Dict[str, Any]:
    ts = (_now() - timedelta(days=days_ago)).isoformat()
    return {
        "signed_at":           ts,
        "strategy_hash":       strategy_hash,
        "status":              status,
        "htf_parity_verdict":  htf,
        "trade_parity_passed": trade_passed,
        "htf_divergence_pct":  0.0,
    }


# ── Pure decision function: timeline edge cases ───────────────────────
def test_empty_timeline_insufficient():
    d = pdv.decide_drift_from_timeline([])
    assert d["decision"] == pdv.DECISION_INSUFFICIENT
    assert d["rows_in_window"] == 0


def test_single_signoff_insufficient():
    d = pdv.decide_drift_from_timeline([_sign_row(days_ago=1)])
    assert d["decision"] == pdv.DECISION_INSUFFICIENT
    assert d["rows_in_window"] == 1


def test_two_stable_signoffs_returns_stable():
    timeline = [
        _sign_row(days_ago=5, htf="WITHIN_TOLERANCE", trade_passed=True),
        _sign_row(days_ago=1, htf="WITHIN_TOLERANCE", trade_passed=True),
    ]
    d = pdv.decide_drift_from_timeline(timeline)
    assert d["decision"] == pdv.DECISION_STABLE


def test_htf_severity_increase_is_drift():
    timeline = [
        _sign_row(days_ago=5, htf="WITHIN_TOLERANCE"),
        _sign_row(days_ago=1, htf="DIVERGED"),
    ]
    d = pdv.decide_drift_from_timeline(timeline)
    assert d["decision"] == pdv.DECISION_DRIFTING
    assert "htf_severity" in (d["regression_reason"] or "")


def test_trade_passed_to_failed_is_drift():
    timeline = [
        _sign_row(days_ago=5, trade_passed=True),
        _sign_row(days_ago=1, trade_passed=False),
    ]
    d = pdv.decide_drift_from_timeline(timeline)
    assert d["decision"] == pdv.DECISION_DRIFTING
    assert "trade_severity" in (d["regression_reason"] or "")


def test_recovery_detected():
    timeline = [
        _sign_row(days_ago=5, htf="DIVERGED"),
        _sign_row(days_ago=1, htf="WITHIN_TOLERANCE"),
    ]
    d = pdv.decide_drift_from_timeline(timeline)
    assert d["decision"] == pdv.DECISION_RECOVERED


def test_window_excludes_old_rows():
    # 30-day old row should be excluded from a 7-day window.
    timeline = [
        _sign_row(days_ago=30, htf="WITHIN_TOLERANCE"),
        _sign_row(days_ago=1,  htf="DIVERGED"),
    ]
    d = pdv.decide_drift_from_timeline(timeline, window_days=7)
    # Only 1 row in window → insufficient_data.
    assert d["decision"] == pdv.DECISION_INSUFFICIENT


def test_window_override_includes_more_history():
    timeline = [
        _sign_row(days_ago=20, htf="WITHIN_TOLERANCE"),
        _sign_row(days_ago=1,  htf="DIVERGED"),
    ]
    d = pdv.decide_drift_from_timeline(timeline, window_days=30)
    assert d["decision"] == pdv.DECISION_DRIFTING


def test_anchor_is_oldest_in_window():
    timeline = [
        _sign_row(days_ago=6, htf="WITHIN_TOLERANCE"),
        _sign_row(days_ago=3, htf="NOT_APPLICABLE"),
        _sign_row(days_ago=1, htf="DIVERGED"),
    ]
    d = pdv.decide_drift_from_timeline(timeline)
    # Anchor (oldest = days_ago=6) is WITHIN_TOLERANCE
    assert d["anchor"]["htf_parity_verdict"] == "WITHIN_TOLERANCE"
    # Current (newest = days_ago=1) is DIVERGED
    assert d["current"]["htf_parity_verdict"] == "DIVERGED"
    assert d["decision"] == pdv.DECISION_DRIFTING


def test_severity_ladder_not_applicable_better_than_diverged():
    timeline = [
        _sign_row(days_ago=5, htf="NOT_APPLICABLE"),
        _sign_row(days_ago=1, htf="DIVERGED"),
    ]
    d = pdv.decide_drift_from_timeline(timeline)
    assert d["decision"] == pdv.DECISION_DRIFTING


def test_unknown_htf_treated_as_worst():
    timeline = [
        _sign_row(days_ago=5, htf="WITHIN_TOLERANCE"),
        _sign_row(days_ago=1, htf="WEIRD_NEW_VALUE_NOT_IN_LADDER"),
    ]
    d = pdv.decide_drift_from_timeline(timeline)
    assert d["decision"] == pdv.DECISION_DRIFTING


def test_timeline_payload_present_in_decision():
    timeline = [_sign_row(days_ago=5), _sign_row(days_ago=1)]
    d = pdv.decide_drift_from_timeline(timeline)
    assert "timeline" in d
    assert len(d["timeline"]) == 2


# ── Mongo-backed wrappers ─────────────────────────────────────────────
@pytest_asyncio.fixture
async def isolated_signoff_set():
    """Insert TEST_ audit rows for a unique strategy_hash; clean up.

    The drift view reads its timeline from ``cbot_parity_audit`` (per
    architecture review §1; ``cbot_parity_signoff`` carries a unique
    index per strategy_hash and therefore can only hold the latest
    verdict, not a history).
    """
    db = get_db()
    strategy_hash = f"TEST_drift_{uuid.uuid4().hex[:12]}"
    deployment_id = f"TEST_dep_{uuid.uuid4().hex[:12]}"
    rows = [
        {**_sign_row(days_ago=5, htf="WITHIN_TOLERANCE", strategy_hash=strategy_hash),
         "_test_marker": True},
        {**_sign_row(days_ago=1, htf="DIVERGED", strategy_hash=strategy_hash),
         "_test_marker": True},
    ]
    for r in rows:
        await db[pdv.AUDIT_COLL].insert_one(r)
    dep_doc = {
        "deployment_id":   deployment_id,
        "strategy_hash":   strategy_hash,
        "state":           "live",
        "_test_marker":    True,
    }
    await db[pdv.DEPLOYMENTS_COLL].insert_one(dep_doc)
    yield {"strategy_hash": strategy_hash, "deployment_id": deployment_id}
    await db[pdv.AUDIT_COLL].delete_many({"strategy_hash": strategy_hash})
    await db[pdv.SIGNOFF_COLL].delete_many({"strategy_hash": strategy_hash})
    await db[pdv.DEPLOYMENTS_COLL].delete_one({"deployment_id": deployment_id})


@pytest.mark.asyncio
async def test_compute_drift_for_deployment_returns_drifting(isolated_signoff_set):
    d = await pdv.compute_drift_for_deployment(isolated_signoff_set["deployment_id"])
    assert d["decision"] == pdv.DECISION_DRIFTING
    assert d["deployment_id"] == isolated_signoff_set["deployment_id"]
    assert d["strategy_hash"] == isolated_signoff_set["strategy_hash"]


@pytest.mark.asyncio
async def test_compute_drift_for_unknown_deployment_returns_not_found():
    d = await pdv.compute_drift_for_deployment("totally_unknown_xxx")
    assert d["decision"] == pdv.DECISION_NO_DEPLOYMENT


@pytest.mark.asyncio
async def test_compute_drift_for_all_live_includes_test_row(isolated_signoff_set):
    out = await pdv.compute_drift_for_all_live()
    assert out["live_deployments_considered"] >= 1
    matched = [r for r in out["rows"]
               if r.get("deployment_id") == isolated_signoff_set["deployment_id"]]
    assert len(matched) == 1
    assert matched[0]["decision"] == pdv.DECISION_DRIFTING


@pytest.mark.asyncio
async def test_window_env_override(monkeypatch):
    monkeypatch.setenv("RUNNER_PARITY_DRIFT_WINDOW_DAYS", "30")
    out = await pdv.compute_drift_for_all_live()
    assert out["window_days"] == 30


# ── Honest-refusal contract ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_deployment_without_strategy_hash_returns_insufficient():
    db = get_db()
    deployment_id = f"TEST_dep_nohash_{uuid.uuid4().hex[:8]}"
    await db[pdv.DEPLOYMENTS_COLL].insert_one(
        {"deployment_id": deployment_id, "state": "live", "_test_marker": True},
    )
    try:
        d = await pdv.compute_drift_for_deployment(deployment_id)
        assert d["decision"] == pdv.DECISION_INSUFFICIENT
        assert "strategy_hash" in d["reason"]
    finally:
        await db[pdv.DEPLOYMENTS_COLL].delete_one({"deployment_id": deployment_id})


# ── Fallback: audit empty, signoff single row → insufficient ────────
@pytest.mark.asyncio
async def test_fallback_to_signoff_single_row_insufficient():
    """When audit is empty but signoff has the single 'current' row,
    the result must be insufficient_data — never coerced to stable."""
    db = get_db()
    strategy_hash = f"TEST_drift_fb_{uuid.uuid4().hex[:8]}"
    deployment_id = f"TEST_dep_fb_{uuid.uuid4().hex[:8]}"
    await db[pdv.SIGNOFF_COLL].insert_one({
        **_sign_row(days_ago=1, strategy_hash=strategy_hash),
        "_test_marker": True,
    })
    await db[pdv.DEPLOYMENTS_COLL].insert_one({
        "deployment_id": deployment_id, "strategy_hash": strategy_hash,
        "state": "live", "_test_marker": True,
    })
    try:
        d = await pdv.compute_drift_for_deployment(deployment_id)
        assert d["decision"] == pdv.DECISION_INSUFFICIENT
        assert d["rows_in_window"] == 1
    finally:
        await db[pdv.SIGNOFF_COLL].delete_many({"strategy_hash": strategy_hash})
        await db[pdv.DEPLOYMENTS_COLL].delete_one({"deployment_id": deployment_id})


@pytest.mark.asyncio
async def test_audit_one_row_plus_signoff_promotes_to_two_for_decision():
    """1 audit row + 1 different signoff row inside the window ⇒
    timeline length 2 ⇒ decision is computable."""
    db = get_db()
    strategy_hash = f"TEST_drift_mix_{uuid.uuid4().hex[:8]}"
    deployment_id = f"TEST_dep_mix_{uuid.uuid4().hex[:8]}"
    await db[pdv.AUDIT_COLL].insert_one({
        **_sign_row(days_ago=5, htf="WITHIN_TOLERANCE", strategy_hash=strategy_hash),
        "_test_marker": True,
    })
    await db[pdv.SIGNOFF_COLL].insert_one({
        **_sign_row(days_ago=1, htf="DIVERGED", strategy_hash=strategy_hash),
        "_test_marker": True,
    })
    await db[pdv.DEPLOYMENTS_COLL].insert_one({
        "deployment_id": deployment_id, "strategy_hash": strategy_hash,
        "state": "live", "_test_marker": True,
    })
    try:
        d = await pdv.compute_drift_for_deployment(deployment_id)
        assert d["decision"] == pdv.DECISION_DRIFTING
        assert d["rows_in_window"] == 2
    finally:
        await db[pdv.AUDIT_COLL].delete_many({"strategy_hash": strategy_hash})
        await db[pdv.SIGNOFF_COLL].delete_many({"strategy_hash": strategy_hash})
        await db[pdv.DEPLOYMENTS_COLL].delete_one({"deployment_id": deployment_id})
