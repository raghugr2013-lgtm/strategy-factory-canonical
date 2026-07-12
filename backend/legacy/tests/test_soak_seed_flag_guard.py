"""MB-9 Phase 2 soak seed — flag-guard regression.

``--seed`` MUST refuse (exit 3) when any Phase 2 behaviour flag is set
in os.environ. ZERO writes occur. ``--unseed`` and ``--seed-status`` are
unaffected by the guard.
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
@pytest.mark.parametrize("flag", [
    "RUNNER_MULTI_ACCOUNT_ENABLED",
    "RUNNER_AUTO_ROTATE",
    "RUNNER_AUTO_ROUTE_AT_REGISTER",
])
async def test_seed_refuses_when_phase2_flag_set(
    clean_seed_state, monkeypatch, flag
):
    monkeypatch.setenv(flag, "true")
    code, receipt = await seed._do_seed(
        include_legacy=False, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code == 3, f"expected exit 3, got {code}"
    assert receipt == {}, "no receipt should be produced on refusal"

    # No rows inserted
    snap = await seed._query_seeded()
    for k in ("runners", "accounts", "definitions", "packs", "deployments"):
        assert snap[k] == [], f"{k} unexpectedly seeded: {snap[k]}"


@pytest.mark.asyncio
async def test_seed_succeeds_when_only_metadata_flags_set(
    clean_seed_state, monkeypatch
):
    """Non-behaviour flags (TOKEN_GRACE_SEC, AFFINITY_POLICY) do NOT trigger
    the guard — they're observational, not behavioural."""
    monkeypatch.setenv("RUNNER_TOKEN_GRACE_SEC", "300")
    monkeypatch.setenv("RUNNER_AFFINITY_POLICY", "sticky_pair_tf")
    code, _ = await seed._do_seed(
        include_legacy=False, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code == 0


@pytest.mark.asyncio
async def test_unseed_unaffected_by_flag(clean_seed_state, monkeypatch):
    """Even if a Phase 2 flag is set, unseed MUST still work — it's
    the operator's rollback escape hatch."""
    code, _ = await seed._do_seed(
        include_legacy=False, allow_piped_tokens=True, no_stdout_tokens=True
    )
    assert code == 0
    monkeypatch.setenv("RUNNER_MULTI_ACCOUNT_ENABLED", "true")
    code2, receipt = await seed._do_unseed(include_legacy=False)
    assert code2 == 0
    assert receipt["actual_total"] == 9
