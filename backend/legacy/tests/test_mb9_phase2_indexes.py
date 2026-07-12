"""MB-9 Phase 2.B — ensure_indexes startup wiring regression.

Verifies the new server.py startup hook (``_ensure_mb9_phase2_indexes``)
creates the right Mongo indexes on ``runner_accounts`` and
``runner_token_rotation`` and that re-running is idempotent.

These tests touch the live Mongo configured via .env. No data is
written into the target collections — only index metadata is read.
"""
from __future__ import annotations

import pytest

from engines.db import get_db
from engines import multi_account_envelope as mae
from engines import runner_token_rotator as rtr


@pytest.mark.asyncio
async def test_runner_accounts_indexes_present():
    """The (runner_id, account_id) compound uniqueness index is the
    critical one — without it duplicate-add tests would race."""
    await mae.ensure_indexes()
    db = get_db()
    info = await db[mae.ACCOUNTS_COLL].index_information()
    # _id always exists. We need at least one compound index on
    # (runner_id, account_id) and one on (runner_id,) for list queries.
    has_compound = False
    has_runner_id = False
    for name, meta in info.items():
        key = meta.get("key") or []
        keys = [k[0] for k in key]
        if keys[:2] == ["runner_id", "account_id"] or set(keys) == {
            "runner_id", "account_id",
        }:
            has_compound = True
            assert meta.get("unique") is True, (
                f"(runner_id, account_id) MUST be unique — got {meta}"
            )
        if keys == ["runner_id"]:
            has_runner_id = True
    assert has_compound, (
        f"missing compound unique index on (runner_id, account_id): {info}"
    )
    # The runner_id-only index is a nice-to-have for list_accounts; do
    # not hard-fail if absent (the compound covers list-by-runner too).
    _ = has_runner_id


@pytest.mark.asyncio
async def test_runner_token_rotation_history_indexes_present():
    """Rotation history table (`runner_token_rotation_history`) carries
    the runner_id + started_at_dt indexes used by audit queries."""
    await rtr.ensure_indexes()
    db = get_db()
    info = await db[rtr.HISTORY_COLL].index_information()
    has_runner_id = False
    has_started_at = False
    for name, meta in info.items():
        keys = [k[0] for k in (meta.get("key") or [])]
        if keys == ["runner_id"]:
            has_runner_id = True
        if keys == ["started_at_dt"]:
            has_started_at = True
    assert has_runner_id, (
        f"missing runner_id index on {rtr.HISTORY_COLL}: {info}"
    )
    assert has_started_at, (
        f"missing started_at_dt index on {rtr.HISTORY_COLL}: {info}"
    )


@pytest.mark.asyncio
async def test_ensure_indexes_is_idempotent():
    """Running ensure_indexes twice must not raise — Mongo refuses to
    re-create existing indexes silently."""
    await mae.ensure_indexes()
    await mae.ensure_indexes()
    await rtr.ensure_indexes()
    await rtr.ensure_indexes()


def test_server_startup_hook_is_registered():
    """The server.py startup must include the Phase 2.B index hook."""
    import server  # noqa: F401
    from server import app
    handler_names = [
        h.__name__ for h in app.router.on_startup
    ]
    assert "_ensure_mb9_phase2_indexes" in handler_names, (
        f"Phase 2.B startup hook missing — found: {handler_names}"
    )
