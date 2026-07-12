"""MB-9 Phase 2.A — Multi-Account Envelope tests.

Covers the HIGH-risk cross-account isolation contract from
architecture review §10 risk #4. Every test uses isolated TEST_
runners + accounts and cleans up at teardown.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from engines import runner_registry as runners
from engines import multi_account_envelope as mae
from engines.db import get_db


# ── Fixtures ──────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def two_runners():
    await runners.ensure_indexes()
    await mae.ensure_indexes()
    a = await runners.register_runner(
        name=f"TEST_mae_A_{uuid.uuid4().hex[:10]}", platform="windows", actor="pytest",
    )
    b = await runners.register_runner(
        name=f"TEST_mae_B_{uuid.uuid4().hex[:10]}", platform="windows", actor="pytest",
    )
    yield (a, b)
    db = get_db()
    for r in (a, b):
        await db[runners.RUNNERS_COLL].delete_one({"runner_id": r["runner_id"]})
        await db[mae.ACCOUNTS_COLL].delete_many({"runner_id": r["runner_id"]})


@pytest_asyncio.fixture
async def disabled_runner_row():
    await runners.ensure_indexes()
    await mae.ensure_indexes()
    r = await runners.register_runner(
        name=f"TEST_mae_disabled_{uuid.uuid4().hex[:10]}",
        platform="windows", actor="pytest",
    )
    await runners.disable_runner(r["runner_id"], actor="pytest")
    yield r
    db = get_db()
    await db[runners.RUNNERS_COLL].delete_one({"runner_id": r["runner_id"]})
    await db[mae.ACCOUNTS_COLL].delete_many({"runner_id": r["runner_id"]})


# ── add_account ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_account_creates_row(two_runners):
    a, _ = two_runners
    res = await mae.add_account(
        runner_id=a["runner_id"], account_id="ACC1",
        credentials_envelope="envelope-bytes-A",
    )
    assert res["runner_id"] == a["runner_id"]
    assert res["account_id"] == "ACC1"
    assert res["active"] is True
    assert res["credentials_envelope_hash"].startswith("sha256:")
    # raw envelope MUST NOT be persisted
    assert "credentials_envelope" not in res or res.get("credentials_envelope") is None


@pytest.mark.asyncio
async def test_add_account_refuses_disabled_runner(disabled_runner_row):
    with pytest.raises(mae.MultiAccountError):
        await mae.add_account(
            runner_id=disabled_runner_row["runner_id"], account_id="ACC1",
        )


@pytest.mark.asyncio
async def test_add_account_refuses_unknown_runner():
    with pytest.raises(mae.MultiAccountError):
        await mae.add_account(runner_id="bogus_runner_xx", account_id="ACC1")


@pytest.mark.asyncio
async def test_add_account_refuses_duplicate(two_runners):
    a, _ = two_runners
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1")
    with pytest.raises(mae.MultiAccountError):
        await mae.add_account(runner_id=a["runner_id"], account_id="ACC1")


@pytest.mark.asyncio
async def test_add_account_refuses_empty_account_id(two_runners):
    a, _ = two_runners
    with pytest.raises(mae.MultiAccountError):
        await mae.add_account(runner_id=a["runner_id"], account_id="")
    with pytest.raises(mae.MultiAccountError):
        await mae.add_account(runner_id=a["runner_id"], account_id="   ")


# ── Cross-runner isolation (HIGH risk path) ──────────────────────────
@pytest.mark.asyncio
async def test_same_account_id_can_exist_under_two_runners(two_runners):
    a, b = two_runners
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1",
                          credentials_envelope="env-A")
    await mae.add_account(runner_id=b["runner_id"], account_id="ACC1",
                          credentials_envelope="env-B")
    # Each runner sees only its own.
    list_a = [r for r in await mae.list_accounts_for_test(a["runner_id"])] \
        if hasattr(mae, "list_accounts_for_test") else []
    # Use the public count_accounts to avoid flag synthesis confusion.
    assert await mae.count_accounts(a["runner_id"]) == 1
    assert await mae.count_accounts(b["runner_id"]) == 1


@pytest.mark.asyncio
async def test_get_account_returns_only_matching_runner(two_runners):
    a, b = two_runners
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1",
                          credentials_envelope="env-A")
    await mae.add_account(runner_id=b["runner_id"], account_id="ACC1",
                          credentials_envelope="env-B")
    row_a = await mae.get_account(runner_id=a["runner_id"], account_id="ACC1")
    row_b = await mae.get_account(runner_id=b["runner_id"], account_id="ACC1")
    assert row_a is not None and row_b is not None
    assert row_a["credentials_envelope_hash"] != row_b["credentials_envelope_hash"]


@pytest.mark.asyncio
async def test_remove_account_only_affects_target_runner(two_runners):
    a, b = two_runners
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1")
    await mae.add_account(runner_id=b["runner_id"], account_id="ACC1")
    await mae.remove_account(runner_id=a["runner_id"], account_id="ACC1")
    assert await mae.count_accounts(a["runner_id"]) == 0
    assert await mae.count_accounts(b["runner_id"]) == 1


# ── Flag-OFF byte-identical behaviour ─────────────────────────────────
@pytest.mark.asyncio
async def test_list_accounts_returns_synthesized_legacy_when_flag_off(
    two_runners, monkeypatch,
):
    a, _ = two_runners
    monkeypatch.delenv("RUNNER_MULTI_ACCOUNT_ENABLED", raising=False)
    # Even with real rows in Mongo, flag-off returns the synthetic legacy.
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1")
    listed = await mae.list_accounts(a["runner_id"])
    assert len(listed) == 1
    assert listed[0]["account_id"] == mae.LEGACY_ACCOUNT_ID
    assert listed[0].get("_synthesized") is True


@pytest.mark.asyncio
async def test_list_accounts_flag_on_returns_real_rows(two_runners, monkeypatch):
    a, _ = two_runners
    monkeypatch.setenv("RUNNER_MULTI_ACCOUNT_ENABLED", "true")
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1",
                          credentials_envelope="env-A")
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC2",
                          credentials_envelope="env-B")
    listed = await mae.list_accounts(a["runner_id"])
    aids = {r["account_id"] for r in listed}
    assert aids == {"ACC1", "ACC2"}


@pytest.mark.asyncio
async def test_list_accounts_flag_off_with_no_rows_still_synth(two_runners, monkeypatch):
    a, _ = two_runners
    monkeypatch.delenv("RUNNER_MULTI_ACCOUNT_ENABLED", raising=False)
    listed = await mae.list_accounts(a["runner_id"])
    assert len(listed) == 1
    assert listed[0]["account_id"] == mae.LEGACY_ACCOUNT_ID


# ── set_active ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_set_active_toggles(two_runners):
    a, _ = two_runners
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1")
    await mae.set_active(runner_id=a["runner_id"], account_id="ACC1", active=False)
    row = await mae.get_account(runner_id=a["runner_id"], account_id="ACC1")
    assert row["active"] is False
    await mae.set_active(runner_id=a["runner_id"], account_id="ACC1", active=True)
    row = await mae.get_account(runner_id=a["runner_id"], account_id="ACC1")
    assert row["active"] is True


@pytest.mark.asyncio
async def test_set_active_unknown_account_raises(two_runners):
    a, _ = two_runners
    with pytest.raises(mae.MultiAccountError):
        await mae.set_active(runner_id=a["runner_id"], account_id="ACC1", active=True)


# ── remove unknown ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_remove_unknown_account_raises(two_runners):
    a, _ = two_runners
    with pytest.raises(mae.MultiAccountError):
        await mae.remove_account(runner_id=a["runner_id"], account_id="ACC1")


# ── account_id normalisation ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_account_id_trimmed(two_runners):
    a, _ = two_runners
    res = await mae.add_account(runner_id=a["runner_id"], account_id="  ACC1  ")
    assert res["account_id"] == "ACC1"


@pytest.mark.asyncio
async def test_account_id_too_long_rejected(two_runners):
    a, _ = two_runners
    with pytest.raises(mae.MultiAccountError):
        await mae.add_account(runner_id=a["runner_id"], account_id="x" * 200)


# ── envelope hashing (raw never leaks) ───────────────────────────────
@pytest.mark.asyncio
async def test_envelope_only_stored_as_hash(two_runners):
    a, _ = two_runners
    secret = "MY_SECRET_API_KEY_DO_NOT_LEAK"
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1",
                          credentials_envelope=secret)
    db = get_db()
    raw = await db[mae.ACCOUNTS_COLL].find_one(
        {"runner_id": a["runner_id"], "account_id": "ACC1"},
    )
    # No field should contain the raw secret.
    for k, v in raw.items():
        if isinstance(v, str):
            assert secret not in v, f"raw secret leaked in field {k}"


@pytest.mark.asyncio
async def test_envelope_hash_changes_with_envelope(two_runners):
    a, _ = two_runners
    r1 = await mae.add_account(runner_id=a["runner_id"], account_id="ACC1",
                               credentials_envelope="env-1")
    # Distinct account_id to avoid duplicate refusal
    r2 = await mae.add_account(runner_id=a["runner_id"], account_id="ACC2",
                               credentials_envelope="env-2")
    assert r1["credentials_envelope_hash"] != r2["credentials_envelope_hash"]


# ── count_accounts ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_count_accounts_returns_raw_count(two_runners, monkeypatch):
    a, _ = two_runners
    # count_accounts is flag-independent — it always returns real rows
    monkeypatch.delenv("RUNNER_MULTI_ACCOUNT_ENABLED", raising=False)
    assert await mae.count_accounts(a["runner_id"]) == 0
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1")
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC2")
    assert await mae.count_accounts(a["runner_id"]) == 2


# ── Indexes ensure uniqueness on (runner_id, account_id) ─────────────
@pytest.mark.asyncio
async def test_unique_index_on_runner_account_pair(two_runners):
    a, _ = two_runners
    await mae.add_account(runner_id=a["runner_id"], account_id="ACC1")
    # The library refusal hits first; verify also at the DB layer the
    # unique index prevents a direct insert duplicate.
    db = get_db()
    # ensure_indexes already called by the fixture
    from pymongo.errors import DuplicateKeyError
    with pytest.raises(DuplicateKeyError):
        await db[mae.ACCOUNTS_COLL].insert_one(
            {"runner_id": a["runner_id"], "account_id": "ACC1",
             "_collision_test": True},
        )
