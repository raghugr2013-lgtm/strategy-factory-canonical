"""P0B Phase 4 — Certification audit-trail verification.

Covers:

    * repeated certifications create new records (audit trail)
    * unique key (strategy_id, certification_timestamp) is enforced
    * derived flag honours freshness window across PASS/WARN/FAIL
    * STALE_CERTIFICATION path: writing an explicit stale row and
      verifying the orchestrator-side reason validator accepts it
      and the read paths surface it correctly.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient
from pymongo.errors import DuplicateKeyError

from engines.persistence_adapters.bi5_certification_store import (
    BI5_CERT_COLL,
    EVALUATOR_VERSION,
    StrategyCertRecord,
    get_latest_certification,
    is_bi5_certified,
    list_certifications,
    list_certifications_for_strategy,
    upsert_certification,
)


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    yield client["p0b_phase4_audit"]
    client.close()


def _rec(*, sid="EM-X", ts=None, verdict="PASS", composite=0.93,
         reason=None) -> StrategyCertRecord:
    ts = ts or datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    return StrategyCertRecord(
        strategy_id=sid, pair="EURUSD", timeframe="M5", style="trend",
        certification_timestamp=ts,
        certification_verdict=verdict,
        certification_version=EVALUATOR_VERSION,
        integrity_score=0.98, spread_score=0.95, slippage_score=0.91,
        execution_score=0.93, stability_score=0.88,
        composite_score=composite,
        reason=reason,
    )


# ── audit trail: repeated runs ───────────────────────────────────────

@pytest.mark.asyncio
async def test_repeated_certifications_create_separate_audit_rows(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    # Three distinct runs, three distinct timestamps → three rows.
    for i in range(3):
        await upsert_certification(db, _rec(
            ts=base + timedelta(days=i), composite=0.80 + i * 0.05,
        ))
    n = await db[BI5_CERT_COLL].count_documents({"strategy_id": "EM-X"})
    assert n == 3, "audit trail must preserve every run"

    rows = await list_certifications_for_strategy(db, strategy_id="EM-X")
    assert len(rows) == 3
    # Newest first.
    composites = [r["composite_score"] for r in rows]
    assert composites == sorted(composites, reverse=True)


# ── audit trail: uniqueness on the compound key ──────────────────────

@pytest.mark.asyncio
async def test_unique_key_is_strategy_id_plus_timestamp(db) -> None:
    """Same key → idempotent overwrite, NOT a duplicate row.

    Real Mongo would raise DuplicateKeyError on a plain insert; the
    store uses an upsert so legitimate retries are no-ops.
    """
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _rec(ts=base, composite=0.93))
    res2 = await upsert_certification(db, _rec(ts=base, composite=0.50))
    assert res2["upserted"] == 0
    assert res2["matched"] == 1
    # Only ONE row.
    assert await db[BI5_CERT_COLL].count_documents({"strategy_id": "EM-X"}) == 1
    # Update went through.
    doc = await db[BI5_CERT_COLL].find_one({"strategy_id": "EM-X"})
    assert doc["composite_score"] == pytest.approx(0.50)


@pytest.mark.asyncio
async def test_unique_index_blocks_raw_duplicate_insert(db) -> None:
    """Belt-and-braces: declare the unique index manually and verify
    a raw insert with the same (strategy_id, certification_timestamp)
    is rejected. This proves the index *would* enforce uniqueness on
    real Mongo (mongomock's index enforcement covers this case)."""
    await db[BI5_CERT_COLL].create_index(
        [("strategy_id", 1), ("certification_timestamp", -1)],
        name="ix_bi5cert_strategy_ts", unique=True,
    )
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await db[BI5_CERT_COLL].insert_one({
        "strategy_id": "EM-Y",
        "certification_timestamp": base,
        "verdict": "PASS",
    })
    with pytest.raises(DuplicateKeyError):
        await db[BI5_CERT_COLL].insert_one({
            "strategy_id": "EM-Y",
            "certification_timestamp": base,
            "verdict": "FAIL",
        })


# ── derived flag: freshness behaviour ────────────────────────────────

@pytest.mark.asyncio
async def test_derived_flag_pass_within_window(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _rec(ts=base, verdict="PASS"))
    flag = await is_bi5_certified(
        db, strategy_id="EM-X", now_dt=base + timedelta(days=10),
        freshness_days=30,
    )
    assert flag["certified"] is True
    assert flag["freshness_days"] == 30


@pytest.mark.asyncio
async def test_derived_flag_pass_outside_window(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _rec(ts=base, verdict="PASS"))
    # 45 days later with a 30-day freshness → not certified.
    flag = await is_bi5_certified(
        db, strategy_id="EM-X", now_dt=base + timedelta(days=45),
        freshness_days=30,
    )
    assert flag["certified"] is False


@pytest.mark.asyncio
async def test_derived_flag_falls_back_to_newest_pass(db) -> None:
    """Mixed history: WARN today, PASS yesterday → certified=True
    because the derived flag tracks the latest PASS within the
    window, not the absolute latest row."""
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _rec(ts=base, verdict="PASS"))
    await upsert_certification(
        db, _rec(ts=base + timedelta(hours=12), verdict="WARN",
                 composite=0.75),
    )
    flag = await is_bi5_certified(
        db, strategy_id="EM-X", now_dt=base + timedelta(days=1),
    )
    assert flag["certified"] is True


@pytest.mark.asyncio
async def test_derived_flag_fail_only_history_returns_false(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    for i in range(3):
        await upsert_certification(db, _rec(
            ts=base + timedelta(hours=i), verdict="FAIL",
            composite=0.2, reason="LOW_COMPOSITE",
        ))
    flag = await is_bi5_certified(db, strategy_id="EM-X", now_dt=base)
    assert flag["certified"] is False


# ── STALE_CERTIFICATION path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_certification_reason_accepted_at_store_boundary(db) -> None:
    """The store must accept STALE_CERTIFICATION as a reason code."""
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    rec = replace(
        _rec(ts=base, verdict="FAIL", composite=0.0),
        reason="STALE_CERTIFICATION",
    )
    res = await upsert_certification(db, rec)
    assert res["upserted"] == 1
    doc = await db[BI5_CERT_COLL].find_one({"strategy_id": "EM-X"})
    assert doc["reason"] == "STALE_CERTIFICATION"


@pytest.mark.asyncio
async def test_stale_certification_is_visible_in_filtered_lists(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    # A fresh PASS for strategy A.
    await upsert_certification(db, _rec(sid="A", ts=base, verdict="PASS"))
    # A STALE_CERTIFICATION FAIL for strategy B (e.g. a write that
    # marks an old cert stale).
    rec_b = replace(
        _rec(sid="B", ts=base + timedelta(hours=1), verdict="FAIL",
             composite=0.0),
        reason="STALE_CERTIFICATION",
    )
    await upsert_certification(db, rec_b)

    fails = await list_certifications(db, verdict="FAIL")
    assert [r["strategy_id"] for r in fails] == ["B"]
    assert fails[0]["reason"] == "STALE_CERTIFICATION"

    # The derived flag for B still correctly says NOT certified
    # (FAIL doesn't count) — confirming STALE_CERTIFICATION rows
    # don't accidentally satisfy the deployable gate.
    flag = await is_bi5_certified(db, strategy_id="B",
                                  now_dt=base + timedelta(hours=2))
    assert flag["certified"] is False


@pytest.mark.asyncio
async def test_stale_certification_after_window_expiry_research_friendly(db) -> None:
    """A workflow demonstration:

        1. Strategy gets a PASS far in the past.
        2. Time moves forward beyond the freshness window.
        3. Anyone querying `is_bi5_certified` sees certified=False.
        4. An optional STALE_CERTIFICATION row is written (by the
           orchestrator's future stale-sweeper, planned for Phase 5)
           to record the transition. Research queries on
           `reason=STALE_CERTIFICATION` then surface every stale
           strategy without needing freshness math at query time.
    """
    far_past = datetime(2025, 8, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)

    await upsert_certification(db, _rec(ts=far_past, verdict="PASS"))
    flag_now = await is_bi5_certified(
        db, strategy_id="EM-X", now_dt=now, freshness_days=30,
    )
    assert flag_now["certified"] is False

    # Record the stale-transition row.
    await upsert_certification(db, replace(
        _rec(ts=now, verdict="FAIL", composite=0.0),
        reason="STALE_CERTIFICATION",
    ))

    # Audit trail now has two rows; latest_one is the STALE row.
    latest = await get_latest_certification(db, strategy_id="EM-X")
    assert latest["reason"] == "STALE_CERTIFICATION"
    # And the flag still says NOT certified.
    flag_after = await is_bi5_certified(
        db, strategy_id="EM-X", now_dt=now, freshness_days=30,
    )
    assert flag_after["certified"] is False
