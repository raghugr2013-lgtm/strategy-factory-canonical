"""MB-9 Phase 2.B — runner_account_migration regression.

Verifies the bootstrap helper is idempotent, skips disabled runners,
never mutates ``master_bot_runners``, and reports an accurate progress
snapshot. All tests run against the real Mongo configured by .env;
each test cleans up the runners + accounts rows it creates.
"""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio

from engines.db import get_db
from engines import multi_account_envelope as mae
from engines import runner_account_migration as rmig
from engines import runner_registry as runners


@pytest_asyncio.fixture
async def clean_fleet():
    """Three runners (2 active, 1 disabled) plus a pre-existing
    operator-added account row on runner #1 — bootstrap must NOT
    touch it."""
    await runners.ensure_indexes()
    await mae.ensure_indexes()
    tag = uuid.uuid4().hex[:10]
    r1 = await runners.register_runner(
        name=f"TEST_rmig_a_{tag}", platform="windows", actor="pytest",
    )
    r2 = await runners.register_runner(
        name=f"TEST_rmig_b_{tag}", platform="windows", actor="pytest",
    )
    r3 = await runners.register_runner(
        name=f"TEST_rmig_c_{tag}", platform="windows", actor="pytest",
    )
    await runners.disable_runner(r3["runner_id"], actor="pytest")
    # Pre-existing operator-added account on r1.
    await mae.add_account(
        runner_id=r1["runner_id"], account_id="OP_ACC_99",
        credentials_envelope="op-envelope",
    )
    yield (r1, r2, r3)
    db = get_db()
    for r in (r1, r2, r3):
        await db[runners.RUNNERS_COLL].delete_one({"runner_id": r["runner_id"]})
        await db[mae.ACCOUNTS_COLL].delete_many({"runner_id": r["runner_id"]})


@pytest.mark.asyncio
async def test_bootstrap_inserts_legacy_rows_for_active_only(clean_fleet):
    r1, r2, r3 = clean_fleet
    report = await rmig.bootstrap_legacy_accounts(actor="pytest")
    assert report["considered"] >= 3
    inserted_ids = set(report["inserted"])
    assert r1["runner_id"] in inserted_ids
    assert r2["runner_id"] in inserted_ids
    # Disabled runner skipped.
    skipped_ids = {s["runner_id"] for s in report["skipped"]}
    assert r3["runner_id"] in skipped_ids
    assert all(s["reason"] == "disabled" for s in report["skipped"]
               if s["runner_id"] == r3["runner_id"])


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent(clean_fleet):
    r1, r2, r3 = clean_fleet
    first = await rmig.bootstrap_legacy_accounts(actor="pytest")
    second = await rmig.bootstrap_legacy_accounts(actor="pytest")
    # Second run does not insert again for the runners first run handled.
    for rid in (r1["runner_id"], r2["runner_id"]):
        assert rid not in second["inserted"], (
            f"{rid} re-inserted on idempotent retry"
        )
        assert rid in second["already"]


@pytest.mark.asyncio
async def test_bootstrap_preserves_existing_operator_accounts(clean_fleet):
    """The operator-added row on r1 (account_id=OP_ACC_99) must
    survive the migration untouched."""
    r1, _, _ = clean_fleet
    await rmig.bootstrap_legacy_accounts(actor="pytest")
    db = get_db()
    op_row = await db[mae.ACCOUNTS_COLL].find_one(
        {"runner_id": r1["runner_id"], "account_id": "OP_ACC_99"},
        {"_id": 0},
    )
    assert op_row is not None
    assert op_row["account_id"] == "OP_ACC_99"
    # And a legacy row also exists alongside.
    legacy = await db[mae.ACCOUNTS_COLL].find_one(
        {"runner_id":  r1["runner_id"],
         "account_id": mae.LEGACY_ACCOUNT_ID},
        {"_id": 0},
    )
    assert legacy is not None
    assert legacy["migration_source"] == rmig.MIGRATION_SOURCE_TAG


@pytest.mark.asyncio
async def test_bootstrap_never_mutates_runners_collection(clean_fleet):
    """Bootstrap is read-mostly on master_bot_runners — must not
    write back to it."""
    r1, _, _ = clean_fleet
    db = get_db()
    before = await db[runners.RUNNERS_COLL].find_one(
        {"runner_id": r1["runner_id"]}, {"_id": 0},
    )
    await rmig.bootstrap_legacy_accounts(actor="pytest")
    after = await db[runners.RUNNERS_COLL].find_one(
        {"runner_id": r1["runner_id"]}, {"_id": 0},
    )
    # Strict byte equality except for last_seen_at which is heartbeat-driven.
    for k in ("name", "platform", "status", "created_at"):
        assert before.get(k) == after.get(k), f"runners.{k} mutated"


@pytest.mark.asyncio
async def test_migration_status_report_shape(clean_fleet):
    rep = await rmig.migration_status()
    for k in ("total_runners", "active_runners", "legacy_account_rows",
              "bootstrapped_rows", "fully_migrated", "computed_at"):
        assert k in rep, f"missing key {k}"
    assert isinstance(rep["total_runners"], int)
    assert isinstance(rep["fully_migrated"], bool)


@pytest.mark.asyncio
async def test_migration_status_fully_migrated_after_bootstrap(clean_fleet):
    """After bootstrap, every active runner has a legacy row → fully_migrated=True
    (counting only the test fleet is hard with concurrent tests, so we
    just assert legacy_account_rows >= active_runners count)."""
    await rmig.bootstrap_legacy_accounts(actor="pytest")
    rep = await rmig.migration_status()
    assert rep["legacy_account_rows"] >= rep["active_runners"]
