"""MB-9 Phase 2.A — Runner Token Rotator tests.

Tests the rotation state machine end-to-end against the live Mongo
test database. Every test isolates itself via a TEST_ prefix on
``runner_id``; teardown removes all created rows.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from engines import runner_registry as runners
from engines import runner_token_rotator as rot
from engines.db import get_db


# ── Fixtures ──────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def fresh_runner():
    """Register a unique runner; clean up at test end."""
    await runners.ensure_indexes()
    await rot.ensure_indexes()
    name = f"TEST_rot_runner_{uuid.uuid4().hex[:10]}"
    r = await runners.register_runner(
        name=name, platform="windows",
        pair_filters=["EURUSD"], timeframe_filters=["H1"], actor="pytest",
    )
    yield r
    db = get_db()
    await db[runners.RUNNERS_COLL].delete_one({"runner_id": r["runner_id"]})
    await db[rot.HISTORY_COLL].delete_many({"runner_id": r["runner_id"]})


@pytest_asyncio.fixture
async def disabled_runner():
    await runners.ensure_indexes()
    await rot.ensure_indexes()
    name = f"TEST_rot_disabled_{uuid.uuid4().hex[:10]}"
    r = await runners.register_runner(
        name=name, platform="windows", actor="pytest",
    )
    await runners.disable_runner(r["runner_id"], actor="pytest")
    yield r
    db = get_db()
    await db[runners.RUNNERS_COLL].delete_one({"runner_id": r["runner_id"]})
    await db[rot.HISTORY_COLL].delete_many({"runner_id": r["runner_id"]})


# ── start_rotation ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_start_rotation_mints_new_token(fresh_runner):
    res = await rot.start_rotation(fresh_runner["runner_id"])
    assert res["runner_id"] == fresh_runner["runner_id"]
    assert res["new_token"].startswith("mbr_")
    assert res["token_rotation_state"] == rot.STATE_ROTATING
    assert "grace_expires_at" in res
    assert res["grace_sec"] >= 30


@pytest.mark.asyncio
async def test_start_rotation_persists_history(fresh_runner):
    await rot.start_rotation(fresh_runner["runner_id"], actor="pytest-A")
    db = get_db()
    h = await db[rot.HISTORY_COLL].find_one(
        {"runner_id": fresh_runner["runner_id"], "status": "started"},
    )
    assert h is not None
    assert h["actor"] == "pytest-A"
    assert h["old_token_hash"].startswith("sha256:")
    assert h["new_token_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_start_rotation_refuses_on_disabled_runner(disabled_runner):
    with pytest.raises(rot.TokenRotationError):
        await rot.start_rotation(disabled_runner["runner_id"])


@pytest.mark.asyncio
async def test_start_rotation_refuses_double_start(fresh_runner):
    await rot.start_rotation(fresh_runner["runner_id"])
    with pytest.raises(rot.TokenRotationError):
        await rot.start_rotation(fresh_runner["runner_id"])


@pytest.mark.asyncio
async def test_start_rotation_unknown_runner_raises():
    with pytest.raises(rot.TokenRotationError):
        await rot.start_rotation("nonexistent_runner_id_xxx")


# ── validate_with_grace ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_old_token_valid_pre_rotation(fresh_runner):
    ok = await rot.validate_with_grace(
        fresh_runner["runner_id"], fresh_runner["token"],
    )
    assert ok is True


@pytest.mark.asyncio
async def test_both_tokens_valid_during_grace(fresh_runner):
    res = await rot.start_rotation(fresh_runner["runner_id"])
    new_token = res["new_token"]
    # Old token still valid
    assert await rot.validate_with_grace(
        fresh_runner["runner_id"], fresh_runner["token"],
    ) is True
    # New token also valid
    assert await rot.validate_with_grace(
        fresh_runner["runner_id"], new_token,
    ) is True


@pytest.mark.asyncio
async def test_bogus_token_rejected(fresh_runner):
    assert await rot.validate_with_grace(
        fresh_runner["runner_id"], "mbr_not_a_real_token",
    ) is False


@pytest.mark.asyncio
async def test_validate_rejects_disabled_runner(disabled_runner):
    # Even with the correct original token, disabled runner rejects.
    assert await rot.validate_with_grace(
        disabled_runner["runner_id"], disabled_runner["token"],
    ) is False


@pytest.mark.asyncio
async def test_validate_empty_inputs_return_false():
    assert await rot.validate_with_grace("", "") is False
    assert await rot.validate_with_grace("any", "") is False


# ── expire_old ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_expire_old_promotes_pending(fresh_runner):
    res = await rot.start_rotation(fresh_runner["runner_id"])
    new_token = res["new_token"]
    await rot.expire_old(fresh_runner["runner_id"])
    # Old token now rejected
    assert await rot.validate_with_grace(
        fresh_runner["runner_id"], fresh_runner["token"],
    ) is False
    # New token still accepted
    assert await rot.validate_with_grace(
        fresh_runner["runner_id"], new_token,
    ) is True


@pytest.mark.asyncio
async def test_expire_old_refuses_when_not_rotating(fresh_runner):
    with pytest.raises(rot.TokenRotationError):
        await rot.expire_old(fresh_runner["runner_id"])


@pytest.mark.asyncio
async def test_expire_old_state_returns_to_active(fresh_runner):
    await rot.start_rotation(fresh_runner["runner_id"])
    out = await rot.expire_old(fresh_runner["runner_id"])
    assert out["token_rotation_state"] == rot.STATE_ACTIVE
    state = await rot.get_rotation_state(fresh_runner["runner_id"])
    assert state["token_rotation_state"] == rot.STATE_ACTIVE


@pytest.mark.asyncio
async def test_expire_old_writes_history(fresh_runner):
    await rot.start_rotation(fresh_runner["runner_id"])
    await rot.expire_old(fresh_runner["runner_id"])
    db = get_db()
    cnt = await db[rot.HISTORY_COLL].count_documents(
        {"runner_id": fresh_runner["runner_id"], "status": "expired"},
    )
    assert cnt == 1


# ── get_rotation_state ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_initial_state_is_active(fresh_runner):
    state = await rot.get_rotation_state(fresh_runner["runner_id"])
    assert state["token_rotation_state"] == rot.STATE_ACTIVE
    assert state["grace_window_active"] is False


@pytest.mark.asyncio
async def test_state_during_grace_window_is_rotating(fresh_runner):
    await rot.start_rotation(fresh_runner["runner_id"])
    state = await rot.get_rotation_state(fresh_runner["runner_id"])
    assert state["token_rotation_state"] == rot.STATE_ROTATING
    assert state["grace_window_active"] is True


@pytest.mark.asyncio
async def test_get_state_unknown_runner_raises():
    with pytest.raises(rot.TokenRotationError):
        await rot.get_rotation_state("nonexistent_xxx")


# ── Grace expiry semantics ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_grace_window_env_override(monkeypatch, fresh_runner):
    monkeypatch.setenv("RUNNER_TOKEN_GRACE_SEC", "120")
    res = await rot.start_rotation(fresh_runner["runner_id"])
    assert res["grace_sec"] == 120


@pytest.mark.asyncio
async def test_grace_window_floor_at_30(monkeypatch, fresh_runner):
    monkeypatch.setenv("RUNNER_TOKEN_GRACE_SEC", "5")
    res = await rot.start_rotation(fresh_runner["runner_id"])
    assert res["grace_sec"] == 30  # floor


@pytest.mark.asyncio
async def test_grace_expired_makes_pending_invalid(fresh_runner):
    """Force-expire the grace window by mutating the stored expiry."""
    res = await rot.start_rotation(fresh_runner["runner_id"])
    new_token = res["new_token"]
    db = get_db()
    # Backdate the grace window so the validator sees it as expired.
    await db[runners.RUNNERS_COLL].update_one(
        {"runner_id": fresh_runner["runner_id"]},
        {"$set": {"rotation_grace_expires_at": "2000-01-01T00:00:00+00:00"}},
    )
    # Old still works (matches token_hash directly).
    assert await rot.validate_with_grace(
        fresh_runner["runner_id"], fresh_runner["token"],
    ) is True
    # Pending should now be invalid because grace window passed.
    assert await rot.validate_with_grace(
        fresh_runner["runner_id"], new_token,
    ) is False


# ── Idempotency / re-rotation after expire ───────────────────────────
@pytest.mark.asyncio
async def test_rotation_cycle_can_repeat(fresh_runner):
    r1 = await rot.start_rotation(fresh_runner["runner_id"])
    await rot.expire_old(fresh_runner["runner_id"])
    # Now the runner is back to active with the new token. We can rotate again.
    r2 = await rot.start_rotation(fresh_runner["runner_id"])
    assert r2["new_token"] != r1["new_token"]
    await rot.expire_old(fresh_runner["runner_id"])
    state = await rot.get_rotation_state(fresh_runner["runner_id"])
    assert state["token_rotation_state"] == rot.STATE_ACTIVE


# ── Phase 1 contract preservation: registry.validate_token still works
@pytest.mark.asyncio
async def test_runner_registry_validate_unchanged_pre_rotation(fresh_runner):
    """validate_with_grace MUST not break runner_registry.validate_token
    on a runner that has never been rotated."""
    row = await runners.validate_token(
        fresh_runner["runner_id"], fresh_runner["token"],
    )
    assert row is not None
    assert row["runner_id"] == fresh_runner["runner_id"]
