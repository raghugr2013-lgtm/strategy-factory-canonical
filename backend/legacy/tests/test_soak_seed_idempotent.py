"""MB-9 Phase 2 soak seed — idempotency regression.

Running ``--seed`` twice MUST produce 9 rows (or 10 with --include-legacy),
not 18 (or 20). The script reuses pre-existing rows tagged with the
seed marker and never inserts duplicates.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from engines import db as _db_module
from scripts import mb9_phase2_soak_seed as seed


@pytest_asyncio.fixture
async def clean_seed_state():
    """Ensure no seed-marker rows are present before/after each test."""
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
async def test_seed_then_seed_again_is_idempotent(clean_seed_state):
    """Two consecutive seeds yield exactly 9 rows total, not 18."""
    code1, r1 = await seed._do_seed(
        include_legacy=False, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code1 == 0, f"first seed failed: {r1.get('errors')}"

    code2, r2 = await seed._do_seed(
        include_legacy=False, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code2 == 0, f"second seed failed: {r2.get('errors')}"

    # Every record in the second run must report status=exists
    for r in r2["runners"]:
        assert r["status"] == "exists", r
    for a in r2["accounts"]:
        assert a["status"] == "exists", a
    assert r2["definition"]["status"] == "exists"
    assert r2["pack"]["status"] == "exists"
    for d in r2["deployments"]:
        assert d["status"] == "exists", d

    # Count rows directly.
    snap = await seed._query_seeded()
    assert len(snap["runners"]) == 3
    assert len(snap["accounts"]) == 2
    assert len(snap["definitions"]) == 1
    assert len(snap["packs"]) == 1
    assert len(snap["deployments"]) == 2
    total = (len(snap["runners"]) + len(snap["accounts"])
             + len(snap["definitions"]) + len(snap["packs"])
             + len(snap["deployments"]))
    assert total == 9, f"expected 9 seeded rows, found {total}"


@pytest.mark.asyncio
async def test_seed_with_include_legacy_idempotent(clean_seed_state):
    code1, _ = await seed._do_seed(
        include_legacy=True, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code1 == 0
    code2, r2 = await seed._do_seed(
        include_legacy=True, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code2 == 0
    assert r2["legacy_account"]["status"] == "exists"
    snap = await seed._query_seeded()
    assert len(snap["accounts"]) == 3  # S-2.a, S-2.b, S-6
    legacy = [a for a in snap["accounts"]
              if a.get("migration_source") == "mb9_phase2_legacy_bootstrap"]
    assert len(legacy) == 1
