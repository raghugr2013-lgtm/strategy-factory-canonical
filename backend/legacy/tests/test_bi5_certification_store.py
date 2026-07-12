"""P0B Phase 3 — Tests for engines/persistence_adapters/bi5_certification_store.py.

Strategy-level certification store. Uses mongomock_motor — no real Mongo.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from engines.persistence_adapters.bi5_certification_store import (
    BI5_CERT_COLL,
    EVALUATOR_VERSION,
    StrategyCertRecord,
    aggregate_stats,
    get_latest_certification,
    is_bi5_certified,
    list_certifications,
    list_certifications_for_strategy,
    upsert_certification,
)


def _naive_utc(dt: datetime) -> datetime:
    return (dt.astimezone(timezone.utc).replace(tzinfo=None)
            if dt.tzinfo else dt)


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    yield client["test_p0b_phase3_strategy"]
    client.close()


def _record(
    *,
    strategy_id: str = "EM-xyz",
    pair: str = "EURUSD",
    timeframe: str = "M5",
    style: str = "trend",
    ts: datetime = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc),
    verdict: str = "PASS",
    integrity: float = 0.98,
    spread: float = 0.95,
    slippage: float = 0.91,
    execution: float = 0.93,
    stability: float = 0.88,
    composite: float = 0.93,
    mutation_family: str = "trend.ema_cross.v2",
    parent: str = "EM-parent",
    reason: str = None,
) -> StrategyCertRecord:
    return StrategyCertRecord(
        strategy_id=strategy_id, pair=pair, timeframe=timeframe, style=style,
        certification_timestamp=ts,
        certification_verdict=verdict,
        certification_version=EVALUATOR_VERSION,
        integrity_score=integrity, spread_score=spread, slippage_score=slippage,
        execution_score=execution, stability_score=stability,
        composite_score=composite,
        mutation_family=mutation_family, parent_strategy_id=parent,
        reason=reason,
    )


# ── upsert / validation ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_inserts_new_row(db) -> None:
    res = await upsert_certification(db, _record())
    assert res["upserted"] == 1
    assert await db[BI5_CERT_COLL].count_documents({}) == 1


@pytest.mark.asyncio
async def test_audit_trail_two_runs_two_rows(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(ts=base))
    await upsert_certification(db, _record(ts=base + timedelta(days=2)))
    assert await db[BI5_CERT_COLL].count_documents({}) == 2


@pytest.mark.asyncio
async def test_same_timestamp_is_idempotent_no_op(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(ts=base, composite=0.93))
    res2 = await upsert_certification(db, _record(ts=base, composite=0.80))
    # Same key → updates in place (audit row is not duplicated for retries).
    assert res2["upserted"] == 0
    assert await db[BI5_CERT_COLL].count_documents({}) == 1


@pytest.mark.asyncio
async def test_rejects_bad_verdict(db) -> None:
    with pytest.raises(ValueError):
        await upsert_certification(db, replace(_record(), certification_verdict="MAYBE"))


@pytest.mark.asyncio
async def test_rejects_bad_reason(db) -> None:
    with pytest.raises(ValueError):
        await upsert_certification(db, replace(_record(), reason="OOPS"))


@pytest.mark.asyncio
async def test_rejects_weight_deviation(db) -> None:
    bad = replace(
        _record(),
        weights_used={"integrity": 0.5, "spread": 0.2, "slippage": 0.1,
                      "execution": 0.1, "stability": 0.1},
    )
    with pytest.raises(ValueError):
        await upsert_certification(db, bad)


@pytest.mark.asyncio
async def test_rejects_extra_or_missing_weight_keys(db) -> None:
    bad = replace(
        _record(),
        weights_used={"integrity": 0.30, "spread": 0.20, "slippage": 0.20,
                      "execution": 0.30},  # missing stability
    )
    with pytest.raises(ValueError):
        await upsert_certification(db, bad)


@pytest.mark.asyncio
async def test_clamps_scores_into_0_1(db) -> None:
    rec = replace(
        _record(),
        integrity_score=1.7, spread_score=-0.2, slippage_score=10.0,
        execution_score=0.5, stability_score=0.5, composite_score=1.5,
    )
    await upsert_certification(db, rec)
    doc = await db[BI5_CERT_COLL].find_one({})
    assert doc["integrity_score"] == 1.0
    assert doc["spread_score"] == 0.0
    assert doc["slippage_score"] == 1.0
    assert doc["composite_score"] == 1.0


# ── reads ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_latest_certification_returns_newest(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(ts=base, composite=0.80))
    await upsert_certification(db, _record(ts=base + timedelta(days=2),
                                           composite=0.95))
    latest = await get_latest_certification(db, strategy_id="EM-xyz")
    assert latest is not None
    assert latest["composite_score"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_list_certifications_filters(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(
        strategy_id="A", pair="EURUSD", style="trend", verdict="PASS",
        ts=base))
    await upsert_certification(db, _record(
        strategy_id="B", pair="EURUSD", style="meanrev", verdict="FAIL",
        composite=0.2, ts=base + timedelta(hours=1),
        reason="LOW_COMPOSITE"))
    await upsert_certification(db, _record(
        strategy_id="C", pair="GBPUSD", style="trend", verdict="WARN",
        composite=0.75, ts=base + timedelta(hours=2)))

    rows = await list_certifications(db, pair="EURUSD")
    assert {r["strategy_id"] for r in rows} == {"A", "B"}

    rows = await list_certifications(db, style="trend")
    assert {r["strategy_id"] for r in rows} == {"A", "C"}

    rows = await list_certifications(db, verdict="FAIL")
    assert [r["strategy_id"] for r in rows] == ["B"]


@pytest.mark.asyncio
async def test_list_for_strategy_returns_newest_first(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(ts=base))
    await upsert_certification(db, _record(ts=base + timedelta(days=2),
                                           composite=0.80))
    rows = await list_certifications_for_strategy(db, strategy_id="EM-xyz")
    assert len(rows) == 2
    assert rows[0]["composite_score"] == pytest.approx(0.80)


# ── derived BI5-Certified flag ───────────────────────────────────────

@pytest.mark.asyncio
async def test_is_bi5_certified_fresh_pass_returns_true(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(verdict="PASS", ts=base))
    out = await is_bi5_certified(
        db, strategy_id="EM-xyz",
        now_dt=base + timedelta(days=10),
    )
    assert out["certified"] is True
    assert out["freshness_days"] == 30
    assert "expires_at" in out


@pytest.mark.asyncio
async def test_is_bi5_certified_stale_returns_false(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(verdict="PASS", ts=base))
    out = await is_bi5_certified(
        db, strategy_id="EM-xyz",
        now_dt=base + timedelta(days=60),
    )
    assert out["certified"] is False


@pytest.mark.asyncio
async def test_is_bi5_certified_fail_does_not_count(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    await upsert_certification(db, _record(verdict="FAIL", composite=0.2,
                                           reason="LOW_COMPOSITE", ts=base))
    out = await is_bi5_certified(db, strategy_id="EM-xyz", now_dt=base)
    assert out["certified"] is False


@pytest.mark.asyncio
async def test_is_bi5_certified_unknown_strategy_returns_false(db) -> None:
    out = await is_bi5_certified(db, strategy_id="not-real")
    assert out["certified"] is False


# ── aggregate_stats ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregate_stats_group_by_style(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    for i, (style, v) in enumerate([
        ("trend", "PASS"), ("trend", "PASS"), ("trend", "FAIL"),
        ("meanrev", "WARN"), ("meanrev", "FAIL"),
    ]):
        await upsert_certification(db, _record(
            strategy_id=f"S{i}", style=style, verdict=v,
            composite=0.93 if v == "PASS" else (0.75 if v == "WARN" else 0.2),
            reason="LOW_COMPOSITE" if v == "FAIL" else None,
            ts=base + timedelta(minutes=i),
        ))
    rows = await aggregate_stats(db, group_by="style")
    by_key = {r["key"]: r for r in rows}
    assert by_key["trend"]["total"] == 3
    assert by_key["trend"]["pass"] == 2
    assert by_key["trend"]["pass_rate"] == pytest.approx(2 / 3)
    assert by_key["meanrev"]["total"] == 2
    assert by_key["meanrev"]["pass"] == 0


@pytest.mark.asyncio
async def test_aggregate_stats_top_n_cap(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    for i in range(20):
        await upsert_certification(db, _record(
            strategy_id=f"S{i}", style=f"style_{i}", verdict="PASS",
            ts=base + timedelta(minutes=i),
        ))
    rows = await aggregate_stats(db, group_by="style", top_n=5)
    assert len(rows) == 5


@pytest.mark.asyncio
async def test_aggregate_stats_rejects_bad_group_by(db) -> None:
    with pytest.raises(ValueError):
        await aggregate_stats(db, group_by="strategy_id")


@pytest.mark.asyncio
async def test_aggregate_stats_drops_docs_missing_mutation_family(db) -> None:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    # One doc WITH mutation_family, one WITHOUT.
    await upsert_certification(db, _record(
        strategy_id="A", mutation_family="trend.v2",
        ts=base,
    ))
    await upsert_certification(db, replace(
        _record(strategy_id="B", ts=base + timedelta(minutes=1)),
        mutation_family=None,
    ))
    rows = await aggregate_stats(db, group_by="mutation_family")
    keys = {r["key"] for r in rows}
    assert keys == {"trend.v2"}
