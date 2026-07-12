"""MB-9 Phase 2 soak seed — marker-safety regression.

``--unseed`` filters STRICTLY on ``seed_marker == mb9_phase2_soak_seed``.
Rows without the marker are NEVER touched, even if their name matches the
seed convention. This is the safety contract that protects pre-existing
operator data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from engines import db as _db_module
from scripts import mb9_phase2_soak_seed as seed


def _iso():
    return datetime.now(timezone.utc).isoformat()


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
async def test_unseed_does_not_delete_rows_without_marker(clean_seed_state):
    """Even if the operator names a runner with the seed prefix, without
    the marker field it is NOT deleted."""
    db = _db_module.get_db()

    # Hand-insert a runner that looks like a seed but lacks the marker.
    # Use a unique name to avoid colliding with any pre-existing fixture.
    pristine_name = f"soak_seed_runner_pristine_{uuid.uuid4().hex[:8]}"
    pristine = {
        "runner_id":          uuid.uuid4().hex,
        "name":               pristine_name,
        "hostname":           "operator-manual",
        "platform":           "linux",
        "token_hash":         "sha256:" + "f" * 64,
        "pair_filters":       ["AUDUSD"],
        "timeframe_filters":  ["H1"],
        "status":             "registered",
        "last_heartbeat_at":  None,
        "last_snapshot":      None,
        "created_at":         _iso(),
        "created_by":         "operator",
        "notes":              "hand-inserted; no seed_marker",
        # NB: NO seed_marker field
    }
    await db["master_bot_runners"].insert_one(pristine)

    try:
        # Seed
        code, _ = await seed._do_seed(
            include_legacy=False, allow_piped_tokens=True,
            no_stdout_tokens=True,
        )
        assert code == 0

        # Unseed
        code2, receipt = await seed._do_unseed(include_legacy=False)
        assert code2 == 0
        assert receipt["actual_total"] == 9

        # Pristine runner MUST still exist.
        still = await db["master_bot_runners"].find_one(
            {"name": pristine_name}, {"_id": 0}
        )
        assert still is not None, "pristine runner was wrongly deleted"
        assert still.get("seed_marker") is None
        assert still["name"] == pristine_name
    finally:
        await db["master_bot_runners"].delete_one({"name": pristine_name})


@pytest.mark.asyncio
async def test_unseed_does_not_delete_account_without_marker(clean_seed_state):
    """Same protection for runner_accounts: marker is authoritative."""
    db = _db_module.get_db()

    pristine_runner_id = uuid.uuid4().hex
    pristine_acct = {
        "runner_id":                 pristine_runner_id,
        "account_id":                "operator-manual-acct",
        "broker":                    "ctrader",
        "credentials_envelope_hash": "sha256:" + "e" * 64,
        "active":                    True,
        "created_at":                _iso(),
        "created_by":                "operator",
        "notes":                     "hand-inserted; no marker",
    }
    await db["runner_accounts"].insert_one(pristine_acct)

    try:
        # Seed + unseed cycle
        code, _ = await seed._do_seed(
            include_legacy=True, allow_piped_tokens=True,
            no_stdout_tokens=True,
        )
        assert code == 0
        code2, receipt = await seed._do_unseed(include_legacy=True)
        assert code2 == 0
        assert receipt["actual_total"] == 10

        # Pristine account must still exist.
        still = await db["runner_accounts"].find_one(
            {"runner_id": pristine_runner_id,
             "account_id": "operator-manual-acct"}, {"_id": 0}
        )
        assert still is not None
        assert still.get("seed_marker") is None
    finally:
        await db["runner_accounts"].delete_one(
            {"runner_id": pristine_runner_id,
             "account_id": "operator-manual-acct"}
        )
