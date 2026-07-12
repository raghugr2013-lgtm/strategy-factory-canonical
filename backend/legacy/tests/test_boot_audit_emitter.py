"""Test the always-on latent-capability boot-line audit emitter.

This test is NOT @pytest.mark.latent — boot audit emission is
always-on operational telemetry, not dormant infrastructure. Regression
must fire on every default test run.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from engines import feature_flags as ff
from engines.db import get_db


@pytest_asyncio.fixture(autouse=True)
async def _fresh_motor_client():
    """Reset the module-level Motor client so each test gets one bound
    to its own pytest-asyncio event loop. Mirrors the pattern used by
    test_phase14_mutation.py and other async test files."""
    from engines import db as _dbm
    _dbm._client = None
    _dbm._db = None
    yield


@pytest.mark.asyncio
async def test_boot_audit_row_persisted_with_required_fields(monkeypatch):
    db = get_db()
    # Snapshot count before so we don't race other writers.
    before = await db["audit_log"].count_documents(
        {"event": "latent_capability:boot_state"},
    )

    ok = await ff.emit_boot_audit_event(
        source="pytest",
        extra={"pytest_marker": "test_boot_audit_row_persisted"},
    )
    assert ok is True, "emit_boot_audit_event should return True on success"

    after = await db["audit_log"].count_documents(
        {"event": "latent_capability:boot_state"},
    )
    assert after == before + 1, "exactly one boot row should be written"

    # Inspect the freshly-written row.
    row = await db["audit_log"].find_one(
        {"event": "latent_capability:boot_state",
         "pytest_marker": "test_boot_audit_row_persisted"},
        {"_id": 0},
    )
    assert row is not None
    for required in (
        "ts", "ts_dt", "event", "phase", "source", "process_pid",
        "flag_count", "overridden_count", "all_dormant",
        "active_overrides", "scopes",
    ):
        assert required in row, f"boot audit row missing field {required!r}"
    assert row["event"] == "latent_capability:boot_state"
    assert row["phase"] == "latent-os"
    assert row["source"] == "pytest"
    assert isinstance(row["flag_count"], int) and row["flag_count"] >= 10
    assert isinstance(row["overridden_count"], int)
    # ts_dt MUST be a BSON Date so the TTL reaper picks it up. Mongo
    # returns BSON dates as tz-naive UTC datetimes by default — that
    # is still TTL-eligible (Mongo internally treats them as UTC).
    assert isinstance(row["ts_dt"], datetime)
    # Don't test exact equality (other tests / live boots may have
    # leaked env), but the dormancy contract: all_dormant True ⇔
    # overridden_count == 0.
    assert row["all_dormant"] == (row["overridden_count"] == 0)


@pytest.mark.asyncio
async def test_boot_audit_captures_active_overrides(monkeypatch):
    """When an override is in env, the boot row reflects it."""
    monkeypatch.setenv("ENABLE_RISK_OF_RUIN", "true")

    db = get_db()
    await ff.emit_boot_audit_event(
        source="pytest_override",
        extra={"pytest_marker": "test_captures_active_overrides"},
    )

    row = await db["audit_log"].find_one(
        {"event": "latent_capability:boot_state",
         "pytest_marker": "test_captures_active_overrides"},
        sort=[("ts_dt", -1)],
    )
    assert row is not None
    assert row["overridden_count"] >= 1
    assert row["all_dormant"] is False
    assert "ENABLE_RISK_OF_RUIN" in row["active_overrides"]
    assert row["active_overrides"]["ENABLE_RISK_OF_RUIN"] is True


@pytest.mark.asyncio
async def test_boot_audit_ts_dt_makes_row_ttl_eligible():
    """The audit_log TTL index reaps rows where `ts_dt < now - 90d`.
    Verify our boot rows have a BSON Date (not an ISO string) in ts_dt
    so they ARE reapable — otherwise the activation timeline grows
    forever.
    """
    db = get_db()
    # Get most recent boot row written by this test session.
    row = await db["audit_log"].find_one(
        {"event": "latent_capability:boot_state"},
        sort=[("ts_dt", -1)],
    )
    assert row is not None
    assert isinstance(row.get("ts_dt"), datetime)
    # Mongo strips tzinfo on read; normalise to UTC for comparison.
    ts_dt = row["ts_dt"]
    if ts_dt.tzinfo is None:
        ts_dt = ts_dt.replace(tzinfo=timezone.utc)
    # And it should be "recent" — within the last 60 seconds.
    delta = (datetime.now(timezone.utc) - ts_dt).total_seconds()
    assert -5 < delta < 60, f"unexpected ts_dt age: {delta}s"


@pytest.mark.asyncio
async def test_audit_log_ttl_index_exists():
    """The TTL index is the OTHER half of the bounded-retention
    contract. Verify it's present and configured for 90d (or whatever
    AUDIT_LOG_RETENTION_DAYS resolves to)."""
    db = get_db()
    info = await db["audit_log"].index_information()
    ttl = info.get("ttl_audit_log")
    assert ttl is not None, "ttl_audit_log index is missing"
    assert ttl.get("expireAfterSeconds") is not None
    # Default is 90 * 86400 = 7,776,000. Allow operator-tunable.
    assert int(ttl["expireAfterSeconds"]) > 0


# ─────────────────────────────────────────────────────────────────────
# Phase 4/5 — forensic governance-state transition emitter
# (latent_capability:override_diff). Always-on observability layered
# on top of boot_state; verifies the persistence contract for the
# activation-timeline-diff row that operators query when answering
# "when did flag X first flip on/off?".
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_override_diff_first_boot_reason(monkeypatch):
    """When fewer than two boot_state rows exist for the test source,
    emit_override_diff_event reports `first_boot` and does NOT write
    an override_diff row.

    We can't drop the global audit_log (other tests + live boots use
    it), so the contract is asserted via the function's return
    payload — which the production callers never depend on but is
    the documented diagnostic surface.
    """
    # Clear leaked env so the diff has a deterministic baseline.
    for spec in ff.iter_specs():
        monkeypatch.delenv(spec["name"], raising=False)

    out = await ff.emit_override_diff_event(
        source="pytest_first_boot_reason",
    )
    # Either first_boot (no prior row) OR no_change (prior row had
    # identical empty overrides). Both must NOT write a diff row.
    assert out["reason"] in ("first_boot", "no_change")
    assert out["emitted"] is False


@pytest.mark.asyncio
async def test_override_diff_writes_row_on_added_flag(monkeypatch):
    """Activation transition — a flag flipped on between two boots
    must produce ONE override_diff row whose `added` bucket contains
    the new flag."""
    # Clean baseline boot (no overrides), then activated boot.
    for spec in ff.iter_specs():
        monkeypatch.delenv(spec["name"], raising=False)

    db = get_db()
    await ff.emit_boot_audit_event(
        source="pytest_diff_added_baseline",
        extra={"pytest_marker": "diff_added_baseline"},
    )
    monkeypatch.setenv("ENABLE_RISK_OF_RUIN", "true")
    await ff.emit_boot_audit_event(
        source="pytest_diff_added_activated",
        extra={"pytest_marker": "diff_added_activated"},
    )

    before = await db["audit_log"].count_documents(
        {"event": "latent_capability:override_diff"},
    )
    out = await ff.emit_override_diff_event(
        source="pytest_diff_added_activated",
        extra={"pytest_marker": "diff_added_emit"},
    )
    after = await db["audit_log"].count_documents(
        {"event": "latent_capability:override_diff"},
    )

    assert out["emitted"] is True
    assert out["reason"] == "diff_written"
    assert "ENABLE_RISK_OF_RUIN" in out["diff"]["added"]
    assert out["diff"]["removed"] == {}
    assert out["diff"]["changed"] == {}
    assert after == before + 1, "exactly one override_diff row should be written"

    row = await db["audit_log"].find_one(
        {"event": "latent_capability:override_diff",
         "pytest_marker": "diff_added_emit"},
        {"_id": 0},
    )
    assert row is not None
    for required in (
        "ts", "ts_dt", "event", "phase", "source", "process_pid",
        "added", "removed", "changed",
        "n_added", "n_removed", "n_changed",
        "previous_boot_ts", "previous_boot_source", "previous_boot_pid",
    ):
        assert required in row, f"override_diff row missing field {required!r}"
    assert row["phase"] == "latent-os"
    assert row["n_added"] == 1
    assert row["n_removed"] == 0
    assert row["n_changed"] == 0
    # TTL-eligibility: ts_dt must be a BSON Date.
    assert isinstance(row["ts_dt"], datetime)


@pytest.mark.asyncio
async def test_override_diff_no_emission_on_no_change(monkeypatch):
    """Two identical boots in a row produce ZERO override_diff rows.
    The institutional timeline only records TRANSITIONS, not steady
    state — preventing the audit_log from being flooded by reboots."""
    for spec in ff.iter_specs():
        monkeypatch.delenv(spec["name"], raising=False)
    monkeypatch.setenv("ENABLE_AGING_PENALTY", "true")

    db = get_db()
    await ff.emit_boot_audit_event(
        source="pytest_diff_steady_prior",
        extra={"pytest_marker": "diff_steady_prior"},
    )
    await ff.emit_boot_audit_event(
        source="pytest_diff_steady_curr",
        extra={"pytest_marker": "diff_steady_curr"},
    )

    before = await db["audit_log"].count_documents(
        {"event": "latent_capability:override_diff"},
    )
    out = await ff.emit_override_diff_event(
        source="pytest_diff_steady_curr",
    )
    after = await db["audit_log"].count_documents(
        {"event": "latent_capability:override_diff"},
    )

    assert out["emitted"] is False
    assert out["reason"] == "no_change"
    assert after == before, "no override_diff row should be written on no-change"
