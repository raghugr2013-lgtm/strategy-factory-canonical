"""P0B Phase 4 — Index verification via real-Mongo `explain()`.

For each indexed query path used by the Phase-3 store and API, drive
a real Mongo (localhost:27017) with `serverSelectionTimeoutMS=2000`
and assert that the query planner picks the expected index.

If Mongo is not reachable, the whole module is skipped at collection
time — the unit tests already exercise behaviour, and these are
ops-grade verifications that need a real planner.

NOTE: The Phase 4 spec explicitly requested `explain()` results, so
we use Mongo's `db.runCommand({explain: …})` and parse the winning
plan to extract every IXSCAN node.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
import pytest_asyncio

motor = pytest.importorskip("motor.motor_asyncio")
pymongo_errors = pytest.importorskip("pymongo.errors")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from engines.db_indexes import ensure_indexes  # noqa: E402
from engines.persistence_adapters.bi5_certification_store import (  # noqa: E402
    BI5_CERT_COLL,
)
from engines.persistence_adapters.bi5_data_certification_store import (  # noqa: E402
    BI5_DATA_CERT_COLL,
)
from engines.persistence_adapters.market_spread_store import (  # noqa: E402
    MARKET_SPREAD_COLL,
)


MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


def _walk_ixscans(plan: Any) -> List[Dict[str, Any]]:
    """Collect every IXSCAN node anywhere in the winning plan tree."""
    out: List[Dict[str, Any]] = []

    def _walk(n: Any) -> None:
        if isinstance(n, dict):
            if n.get("stage") == "IXSCAN":
                out.append(n)
            for v in n.values():
                _walk(v)
        elif isinstance(n, list):
            for v in n:
                _walk(v)
    _walk(plan)
    return out


@pytest_asyncio.fixture
async def mongo_client():
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=2000)
    try:
        await client.admin.command("ping")
    except Exception as exc:
        client.close()
        pytest.skip(f"real Mongo at {MONGO_URL} not reachable: {exc}")
    yield client
    client.close()


@pytest_asyncio.fixture
async def db(mongo_client):
    """Per-test isolated DB so explain() plans are deterministic."""
    name = f"p0b_phase4_explain_{uuid.uuid4().hex[:8]}"
    db_ = mongo_client[name]
    # Point the global engines.db handle at this throw-away db so
    # ensure_indexes() installs the Phase-3 indexes here.
    from engines import db as db_mod
    prev_db, prev_client = db_mod._db, db_mod._client
    db_mod._db = db_
    db_mod._client = mongo_client
    try:
        await ensure_indexes()
        yield db_
    finally:
        await mongo_client.drop_database(name)
        db_mod._db, db_mod._client = prev_db, prev_client


async def _explain_find(db, coll: str, *, filter_: Dict[str, Any],
                        sort: Dict[str, int] = None) -> Dict[str, Any]:
    cmd: Dict[str, Any] = {"find": coll, "filter": filter_}
    if sort:
        cmd["sort"] = sort
    plan = await db.command("explain", cmd, verbosity="queryPlanner")
    return plan["queryPlanner"]["winningPlan"]


async def _explain_aggregate(db, coll: str, pipeline: List[Dict[str, Any]]):
    plan = await db.command(
        "explain",
        {"aggregate": coll, "pipeline": pipeline, "cursor": {}},
        verbosity="queryPlanner",
    )
    # Aggregate plans nest the find-stage under "stages"[0]["$cursor"].
    if "stages" in plan:
        first = plan["stages"][0]
        for v in first.values():
            if isinstance(v, dict) and "queryPlanner" in v:
                return v["queryPlanner"]["winningPlan"]
    return plan.get("queryPlanner", {}).get("winningPlan")


async def _seed_strategy_cert(db, *, n: int = 50):
    """Seed enough docs that the planner prefers IXSCAN over COLLSCAN."""
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    docs = []
    for i in range(n):
        docs.append({
            "strategy_id":             f"S{i % 5}",
            "pair":                    ["EURUSD", "GBPUSD", "USDJPY"][i % 3],
            "timeframe":               ["M1", "M5", "H1"][i % 3],
            "style":                   ["trend", "meanrev", "breakout"][i % 3],
            "certification_timestamp": base + timedelta(minutes=i),
            "certification_verdict":   ["PASS", "WARN", "FAIL"][i % 3],
            "certification_version":   "bi5_cert@P0B-v1",
            "integrity_score": 0.9, "spread_score": 0.9, "slippage_score": 0.9,
            "execution_score": 0.9, "stability_score": 0.9,
            "composite_score":         0.5 + (i % 50) / 100.0,
            "mutation_family":         f"fam_{i % 4}" if i % 7 else None,
            "weights_used": {"integrity": 0.30, "spread": 0.20,
                             "slippage": 0.20, "execution": 0.15,
                             "stability": 0.15},
            "thresholds_used": {"pass": 0.90, "warn": 0.70},
        })
    await db[BI5_CERT_COLL].insert_many(docs)


# ── strategy-cert index hits ────────────────────────────────────────

@pytest.mark.asyncio
async def test_uses_ix_bi5cert_strategy_ts(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={"strategy_id": "S2"},
        sort={"certification_timestamp": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5cert_strategy_ts" in names, names


@pytest.mark.asyncio
async def test_uses_ix_bi5cert_pair_ts(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={"pair": "EURUSD"},
        sort={"certification_timestamp": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5cert_pair_ts" in names, names


@pytest.mark.asyncio
async def test_uses_ix_bi5cert_tf_ts(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={"timeframe": "M5"},
        sort={"certification_timestamp": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5cert_tf_ts" in names, names


@pytest.mark.asyncio
async def test_uses_ix_bi5cert_style_ts(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={"style": "trend"},
        sort={"certification_timestamp": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5cert_style_ts" in names, names


@pytest.mark.asyncio
async def test_uses_ix_bi5cert_family_ts(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={"mutation_family": "fam_2"},
        sort={"certification_timestamp": -1},
    )
    ixscans = _walk_ixscans(plan)
    # The planner may pick either the partial family-ts index OR the
    # global ts index — both produce sorted output. What matters for
    # this audit is: IXSCAN, never COLLSCAN. The partial index exists
    # and was created (asserted separately via index_information() in
    # the audit_trail tests).
    assert ixscans, (
        "expected at least one IXSCAN (got COLLSCAN — partial index "
        f"unreachable). plan={plan}"
    )
    # Confirm the family index is at least present in the catalog —
    # whether or not the planner picked it for this particular shape.
    info = await db[BI5_CERT_COLL].index_information()
    assert "ix_bi5cert_family_ts" in info, list(info)


@pytest.mark.asyncio
async def test_uses_ix_bi5cert_verdict_ts(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={"certification_verdict": "PASS"},
        sort={"certification_timestamp": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5cert_verdict_ts" in names, names


@pytest.mark.asyncio
async def test_uses_ix_bi5cert_composite_for_topn(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={},
        sort={"composite_score": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5cert_composite" in names, names


@pytest.mark.asyncio
async def test_uses_ix_bi5cert_ts_for_global_recent(db) -> None:
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={},
        sort={"certification_timestamp": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5cert_ts" in names, names


@pytest.mark.asyncio
async def test_derived_flag_query_uses_strategy_ts_index(db) -> None:
    """The is_bi5_certified() query: equality on strategy_id + verdict
    + range on certification_timestamp, sorted DESC."""
    await _seed_strategy_cert(db)
    plan = await _explain_find(
        db, BI5_CERT_COLL,
        filter_={
            "strategy_id": "S0",
            "certification_verdict": "PASS",
            "certification_timestamp": {
                "$gte": datetime(2026, 1, 1, tzinfo=timezone.utc),
            },
        },
        sort={"certification_timestamp": -1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    # Either the strategy_ts or verdict_ts index is acceptable here —
    # both cover the query. The point is: NO COLLSCAN.
    assert names, "expected at least one IXSCAN, got COLLSCAN"
    assert any(n in ("ix_bi5cert_strategy_ts", "ix_bi5cert_verdict_ts")
               for n in names), names


# ── data-cert index hits ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_uses_ix_bi5datacert_sym_window(db) -> None:
    base = datetime(2026, 2, 3, tzinfo=timezone.utc)
    docs = [{
        "symbol": "EURUSD",
        "window_start_utc": base + timedelta(days=i),
        "window_end_utc":   base + timedelta(days=i, hours=23),
        "verdict": "PASS", "bi5_score": 0.95,
        "subscores": {"cov": 1, "integrity": 0.95, "price": 1,
                      "density": 0.9, "continuity": 0.9},
        "certified_at_dt": base + timedelta(days=i, hours=23),
        "evaluator_version": "tick_validator@P0B-v1",
    } for i in range(20)]
    await db[BI5_DATA_CERT_COLL].insert_many(docs)
    plan = await _explain_find(
        db, BI5_DATA_CERT_COLL,
        filter_={
            "symbol": "EURUSD",
            "window_start_utc": base,
            "window_end_utc":   base + timedelta(hours=23),
        },
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_bi5datacert_sym_window" in names, names


# ── market_spread index hits ────────────────────────────────────────

@pytest.mark.asyncio
async def test_uses_ix_spread_sym_min(db) -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    docs = [{
        "symbol": "EURUSD",
        "minute_utc": base + timedelta(minutes=i),
        "spread_open": 0.0001, "spread_high": 0.0001,
        "spread_low": 0.0001, "spread_close": 0.0001,
        "spread_mean": 0.0001, "tick_count": 100,
        "created_at_dt": base + timedelta(hours=1),
        "src": "bi5", "evaluator_version": "spread_analyzer@P0B-v1",
    } for i in range(50)]
    await db[MARKET_SPREAD_COLL].insert_many(docs)
    plan = await _explain_find(
        db, MARKET_SPREAD_COLL,
        filter_={
            "symbol": "EURUSD",
            "minute_utc": {"$gte": base, "$lt": base + timedelta(minutes=10)},
        },
        sort={"minute_utc": 1},
    )
    names = [ix["indexName"] for ix in _walk_ixscans(plan)]
    assert "ix_spread_sym_min" in names, names
