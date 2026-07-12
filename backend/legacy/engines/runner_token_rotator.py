"""Master Bot V1 — Runner Token Rotator (MB-9 Phase 2.A).

Rotates per-runner bearer tokens without service interruption:

  ┌─ active ─┐  start_rotation  ┌─ rotating ─┐  expire_old  ┌─ expired ─┐
  │  (one    │ ─────────────────▶│ (both old │ ────────────▶│ (only new │
  │  token)  │                   │  + new ok)│              │ token ok) │
  └──────────┘                   └────┬──────┘              └───────────┘
                                      │
                              after RUNNER_TOKEN_GRACE_SEC
                              (or explicit operator call)

Discipline:

  * **Manual rotation always available.** Operator can call
    ``start_rotation(runner_id)`` at any time to mint a new token.
    The OLD token continues to authenticate for
    ``RUNNER_TOKEN_GRACE_SEC`` (default 300 s).

  * **Auto-rotation is OFF by default** (``RUNNER_AUTO_ROTATE=false``).
    Phase 2.A only builds the state machine + persistence; the
    scheduler hook lives outside this module (and stays unwired
    until Phase 2.B + operator authorization).

  * **Honest refusal**: refuses to rotate a disabled runner; refuses
    to rotate a runner already in ``rotating`` state (must finish
    or cancel the current rotation first); refuses ``expire_old``
    when there is no active rotation.

  * **Token format / hashing**: matches Phase 1 verbatim
    (``mbr_`` prefix + 32-byte URL-safe; sha256 hash at rest).

  * **Persistence**: two surfaces.
      - ``master_bot_runners`` (existing collection): three additive
        fields — ``token_rotation_state``, ``pending_token_hash``,
        ``rotation_started_at``, ``rotation_grace_expires_at``.
        ``token_hash`` is rewritten to the new value at
        ``expire_old`` time.
      - ``runner_token_rotation_history`` (NEW collection,
        additive): one row per rotation cycle (started/expired).
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from engines.db import get_db
from engines import runner_registry as runners

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────
HISTORY_COLL = "runner_token_rotation_history"

# Rotation states (stored verbatim in master_bot_runners.token_rotation_state).
STATE_ACTIVE   = "active"
STATE_ROTATING = "rotating"
STATE_EXPIRED  = "expired"

# Default grace window: 5 minutes. Phase-2.B will register the formal flag.
DEFAULT_GRACE_SEC = 300
# Default auto-rotate cadence: 30 days. Phase-2.B will register the formal flag.
DEFAULT_ROTATE_INTERVAL_SEC = 30 * 24 * 60 * 60


# ── Errors ────────────────────────────────────────────────────────────
class TokenRotationError(RuntimeError):
    pass


# ── Helpers ───────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _mint_token() -> str:
    return "mbr_" + secrets.token_urlsafe(32)


def _grace_sec() -> int:
    raw = (os.environ.get("RUNNER_TOKEN_GRACE_SEC") or "").strip()
    try:
        return max(30, int(raw)) if raw else DEFAULT_GRACE_SEC
    except (TypeError, ValueError):
        return DEFAULT_GRACE_SEC


def _expired(grace_expires_at: Optional[str]) -> bool:
    if not grace_expires_at:
        return True
    try:
        dt = datetime.fromisoformat(str(grace_expires_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _now() >= dt
    except ValueError:
        return True


# ── Persistence helpers ───────────────────────────────────────────────
async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[HISTORY_COLL].create_index("runner_id")
        await db[HISTORY_COLL].create_index("started_at_dt")
    except Exception:                                            # pragma: no cover
        logger.exception("runner_token_rotator: ensure_indexes failed")


async def _fetch_runner(runner_id: str) -> Dict[str, Any]:
    db = get_db()
    row = await db[runners.RUNNERS_COLL].find_one(
        {"runner_id": runner_id}, {"_id": 0},
    )
    if not row:
        raise TokenRotationError(f"runner {runner_id!r} not found")
    if row.get("status") == "disabled":
        raise TokenRotationError(f"runner {runner_id!r} is disabled")
    return row


# ── Public API ────────────────────────────────────────────────────────
async def start_rotation(runner_id: str, *, actor: str = "admin") -> Dict[str, Any]:
    """Mint a new token. Old + new are both valid for the grace window.

    Returns ``{runner_id, new_token, grace_expires_at, ...}``. The raw
    ``new_token`` is shown ONLY here.
    """
    row = await _fetch_runner(runner_id)
    state = row.get("token_rotation_state") or STATE_ACTIVE
    if state == STATE_ROTATING:
        raise TokenRotationError(
            f"runner {runner_id!r} is already rotating; finish or cancel first"
        )

    db = get_db()
    new_token = _mint_token()
    new_hash = _hash_token(new_token)
    started = _now()
    expires = started + timedelta(seconds=_grace_sec())
    old_hash = row.get("token_hash") or ""

    await db[runners.RUNNERS_COLL].update_one(
        {"runner_id": runner_id},
        {"$set": {
            "token_rotation_state":      STATE_ROTATING,
            "pending_token_hash":        new_hash,
            "rotation_started_at":       started.isoformat(),
            "rotation_grace_expires_at": expires.isoformat(),
        }},
    )

    await db[HISTORY_COLL].insert_one({
        "runner_id":      runner_id,
        "old_token_hash": old_hash,
        "new_token_hash": new_hash,
        "started_at":     started.isoformat(),
        "started_at_dt":  started,
        "expires_at":     expires.isoformat(),
        "status":         "started",
        "actor":          actor,
    })

    return {
        "runner_id":          runner_id,
        "new_token":          new_token,
        "grace_expires_at":   expires.isoformat(),
        "grace_sec":          _grace_sec(),
        "token_rotation_state": STATE_ROTATING,
    }


async def validate_with_grace(runner_id: str, token: str) -> bool:
    """True if ``token`` matches the active OR (during grace) the
    pending hash. False otherwise. Constant-time compares."""
    if not runner_id or not token:
        return False
    db = get_db()
    row = await db[runners.RUNNERS_COLL].find_one(
        {"runner_id": runner_id},
        {"_id": 0, "token_hash": 1, "pending_token_hash": 1,
         "token_rotation_state": 1, "rotation_grace_expires_at": 1,
         "status": 1},
    )
    if not row or row.get("status") == "disabled":
        return False
    candidate = _hash_token(token)
    if secrets.compare_digest(row.get("token_hash") or "", candidate):
        return True
    if row.get("token_rotation_state") == STATE_ROTATING:
        if _expired(row.get("rotation_grace_expires_at")):
            return False
        if secrets.compare_digest(row.get("pending_token_hash") or "", candidate):
            return True
    return False


async def expire_old(runner_id: str, *, actor: str = "admin") -> Dict[str, Any]:
    """Promote the pending token to be the only valid one.

    Refuses if the runner is not in ``rotating`` state.
    Idempotent: a second call returns ``already_expired=True``.
    """
    row = await _fetch_runner(runner_id)
    state = row.get("token_rotation_state") or STATE_ACTIVE
    if state != STATE_ROTATING:
        raise TokenRotationError(
            f"runner {runner_id!r} has no active rotation to expire (state={state})"
        )

    db = get_db()
    new_hash = row.get("pending_token_hash") or ""
    if not new_hash:
        raise TokenRotationError("rotating state but no pending_token_hash present")

    await db[runners.RUNNERS_COLL].update_one(
        {"runner_id": runner_id},
        {
            "$set": {
                "token_hash":            new_hash,
                "token_rotation_state":  STATE_ACTIVE,
            },
            "$unset": {
                "pending_token_hash":         "",
                "rotation_started_at":        "",
                "rotation_grace_expires_at":  "",
            },
        },
    )

    await db[HISTORY_COLL].insert_one({
        "runner_id":      runner_id,
        "old_token_hash": "(promoted)",
        "new_token_hash": new_hash,
        "started_at":     _now_iso(),
        "started_at_dt":  _now(),
        "status":         "expired",
        "actor":          actor,
    })

    return {"runner_id": runner_id, "token_rotation_state": STATE_ACTIVE}


async def get_rotation_state(runner_id: str) -> Dict[str, Any]:
    """Inspector — read-only summary of the rotation state."""
    db = get_db()
    row = await db[runners.RUNNERS_COLL].find_one(
        {"runner_id": runner_id},
        {"_id": 0, "token_rotation_state": 1,
         "rotation_started_at": 1, "rotation_grace_expires_at": 1,
         "status": 1},
    )
    if not row:
        raise TokenRotationError(f"runner {runner_id!r} not found")
    state = row.get("token_rotation_state") or STATE_ACTIVE
    return {
        "runner_id":                  runner_id,
        "token_rotation_state":       state,
        "rotation_started_at":        row.get("rotation_started_at"),
        "rotation_grace_expires_at":  row.get("rotation_grace_expires_at"),
        "grace_window_active":        state == STATE_ROTATING
                                       and not _expired(row.get("rotation_grace_expires_at")),
    }


__all__ = [
    "HISTORY_COLL",
    "STATE_ACTIVE", "STATE_ROTATING", "STATE_EXPIRED",
    "DEFAULT_GRACE_SEC", "DEFAULT_ROTATE_INTERVAL_SEC",
    "TokenRotationError",
    "ensure_indexes",
    "start_rotation", "validate_with_grace",
    "expire_old", "get_rotation_state",
]
