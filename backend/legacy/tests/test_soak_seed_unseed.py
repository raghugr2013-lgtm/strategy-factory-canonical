"""MB-9 Phase 2 soak seed — full round-trip regression.

``--seed`` then ``--unseed`` returns Mongo counts to the pre-seed values
for every collection. Receipt receipts are written, and unseed receipts
record actual_total == expected_total.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from engines import db as _db_module
from scripts import mb9_phase2_soak_seed as seed


@pytest_asyncio.fixture
async def clean_seed_state():
    db = _db_module.get_db()
    f = {"seed_marker": seed.SEED_MARKER}
    for coll in ("master_bot_deployments", "master_bot_packs",
                 "master_bot_definitions", "runner_accounts",
                 "master_bot_runners"):
        await db[coll].delete_many(f)
    yield
    for coll in ("master_bot_deployments", "master_bot_packs",
                 "master_bot_definitions", "runner_accounts",
                 "master_bot_runners"):
        await db[coll].delete_many(f)


@pytest.mark.asyncio
async def test_seed_then_unseed_returns_to_zero(clean_seed_state):
    db = _db_module.get_db()
    # Baseline counts (non-seeded rows in the database).
    f = {"seed_marker": seed.SEED_MARKER}
    base = {
        c: await db[c].count_documents({})
        for c in ("master_bot_deployments", "master_bot_packs",
                  "master_bot_definitions", "runner_accounts",
                  "master_bot_runners")
    }

    code, _ = await seed._do_seed(
        include_legacy=False, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code == 0

    # Confirm 9 rows present
    snap = await seed._query_seeded()
    assert sum(len(snap[k]) for k in
               ("runners", "accounts", "definitions", "packs",
                "deployments")) == 9

    # Unseed
    code2, receipt = await seed._do_unseed(include_legacy=False)
    assert code2 == 0
    assert receipt["actual_total"] == 9
    assert receipt["status"] == "complete"

    # Confirm 0 seed-marker rows left
    snap2 = await seed._query_seeded()
    for k in ("runners", "accounts", "definitions", "packs", "deployments"):
        assert snap2[k] == [], f"{k} still has seeded rows: {snap2[k]}"

    # Confirm non-seeded rows untouched
    after = {c: await db[c].count_documents({})
             for c in base}
    assert after == base, f"non-seed rows touched: before={base} after={after}"


@pytest.mark.asyncio
async def test_unseed_with_legacy_returns_to_zero(clean_seed_state):
    code, _ = await seed._do_seed(
        include_legacy=True, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code == 0
    snap = await seed._query_seeded()
    assert len(snap["accounts"]) == 3

    code2, receipt = await seed._do_unseed(include_legacy=True)
    assert code2 == 0
    assert receipt["actual_total"] == 10

    snap2 = await seed._query_seeded()
    assert all(snap2[k] == [] for k in
               ("runners", "accounts", "definitions", "packs", "deployments"))


@pytest.mark.asyncio
async def test_unseed_when_already_clean_is_noop(clean_seed_state):
    code, receipt = await seed._do_unseed(include_legacy=False)
    assert code == 0
    assert receipt["actual_total"] == 0
    for v in receipt["deletions"].values():
        assert v == 0
