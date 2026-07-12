"""Master Bot V1 — Multi-Account Envelope (MB-9 Phase 2.A).

Per-account credentials envelope for a runner. One Mongo collection
``runner_accounts`` keyed by ``(runner_id, account_id)``.

Discipline (HIGH-risk path per architecture review §10 risk #4):

  * **Strict isolation.** Every CRUD operation is keyed on the
    ``(runner_id, account_id)`` pair. There is no cross-runner
    listing; queries always pin the runner.

  * **Schema stores only a hash.** Raw credentials never enter
    Mongo. The operator-managed secret store holds the envelope; we
    record only ``credentials_envelope_hash`` (sha256:hex) as proof
    that the operator pushed an envelope.

  * **Default-OFF.** When ``RUNNER_MULTI_ACCOUNT_ENABLED=false``
    (the default), ``list_accounts`` returns a single "legacy"
    pseudo-account so that downstream consumers (Phase 2.B's poll
    envelope assembly) see byte-identical Phase 1 behaviour. CRUD
    endpoints still WORK when the flag is off (operators can
    pre-seed) — only the consumption path is gated.

  * **Honest refusal.** Refuses to add an account to a disabled
    runner; refuses duplicate ``(runner_id, account_id)``; refuses
    empty account_id.

  * **Audit trail.** Every CRUD operation stamps actor + timestamp.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines import runner_registry as runners

logger = logging.getLogger(__name__)


ACCOUNTS_COLL = "runner_accounts"

LEGACY_ACCOUNT_ID = "_legacy_single_account"


class MultiAccountError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flag_enabled() -> bool:
    raw = (os.environ.get("RUNNER_MULTI_ACCOUNT_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _hash_envelope(envelope_str: str) -> str:
    if envelope_str is None:
        envelope_str = ""
    return "sha256:" + hashlib.sha256(envelope_str.encode("utf-8")).hexdigest()


def _norm_account_id(account_id: str) -> str:
    if not account_id or not str(account_id).strip():
        raise MultiAccountError("account_id must be non-empty")
    aid = str(account_id).strip()
    if len(aid) > 120:
        raise MultiAccountError("account_id too long (max 120 chars)")
    return aid


async def _assert_runner_active(runner_id: str) -> Dict[str, Any]:
    db = get_db()
    row = await db[runners.RUNNERS_COLL].find_one(
        {"runner_id": runner_id},
        {"_id": 0, "runner_id": 1, "status": 1, "name": 1},
    )
    if not row:
        raise MultiAccountError(f"runner {runner_id!r} not found")
    if row.get("status") == "disabled":
        raise MultiAccountError(f"runner {runner_id!r} is disabled")
    return row


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[ACCOUNTS_COLL].create_index(
            [("runner_id", 1), ("account_id", 1)], unique=True,
        )
        await db[ACCOUNTS_COLL].create_index("runner_id")
    except Exception:                                            # pragma: no cover
        logger.exception("multi_account_envelope: ensure_indexes failed")


# ── CRUD ──────────────────────────────────────────────────────────────
async def add_account(
    *,
    runner_id: str,
    account_id: str,
    broker: str = "ctrader",
    credentials_envelope: Optional[str] = None,
    notes: str = "",
    actor: str = "admin",
) -> Dict[str, Any]:
    """Add a new account row. Raises if duplicate or runner disabled."""
    await _assert_runner_active(runner_id)
    aid = _norm_account_id(account_id)
    db = get_db()
    if await db[ACCOUNTS_COLL].find_one({"runner_id": runner_id, "account_id": aid}):
        raise MultiAccountError(
            f"(runner_id={runner_id!r}, account_id={aid!r}) already exists"
        )
    doc = {
        "runner_id":                  runner_id,
        "account_id":                 aid,
        "broker":                     (broker or "ctrader").strip().lower(),
        "credentials_envelope_hash":  _hash_envelope(credentials_envelope or ""),
        "active":                     True,
        "created_at":                 _now_iso(),
        "created_by":                 actor,
        "notes":                      notes or "",
    }
    await db[ACCOUNTS_COLL].insert_one(doc)
    out = {k: v for k, v in doc.items() if k != "_id"}
    return out


async def remove_account(
    *, runner_id: str, account_id: str, actor: str = "admin",
) -> Dict[str, Any]:
    """Hard-delete one account row. Refuses if not found."""
    aid = _norm_account_id(account_id)
    db = get_db()
    res = await db[ACCOUNTS_COLL].delete_one(
        {"runner_id": runner_id, "account_id": aid},
    )
    if res.deleted_count == 0:
        raise MultiAccountError(
            f"(runner_id={runner_id!r}, account_id={aid!r}) not found"
        )
    return {"runner_id": runner_id, "account_id": aid, "removed_at": _now_iso(),
            "removed_by": actor}


async def set_active(
    *, runner_id: str, account_id: str, active: bool, actor: str = "admin",
) -> Dict[str, Any]:
    aid = _norm_account_id(account_id)
    db = get_db()
    res = await db[ACCOUNTS_COLL].update_one(
        {"runner_id": runner_id, "account_id": aid},
        {"$set": {"active": bool(active),
                  "updated_at": _now_iso(),
                  "updated_by": actor}},
    )
    if res.matched_count == 0:
        raise MultiAccountError(
            f"(runner_id={runner_id!r}, account_id={aid!r}) not found"
        )
    return {"runner_id": runner_id, "account_id": aid, "active": bool(active)}


async def get_account(
    *, runner_id: str, account_id: str,
) -> Optional[Dict[str, Any]]:
    aid = _norm_account_id(account_id)
    db = get_db()
    return await db[ACCOUNTS_COLL].find_one(
        {"runner_id": runner_id, "account_id": aid}, {"_id": 0},
    )


async def list_accounts(runner_id: str) -> List[Dict[str, Any]]:
    """List accounts FOR THIS RUNNER ONLY.

    When ``RUNNER_MULTI_ACCOUNT_ENABLED=false`` (default), returns a
    single-element list with a synthetic legacy account so downstream
    poll-envelope code stays byte-identical to Phase 1 even when the
    operator has pre-seeded multi-account rows.
    """
    db = get_db()
    if not _flag_enabled():
        return [{
            "runner_id":                 runner_id,
            "account_id":                LEGACY_ACCOUNT_ID,
            "broker":                    "ctrader",
            "credentials_envelope_hash": None,
            "active":                    True,
            "_synthesized":              True,
        }]
    cur = db[ACCOUNTS_COLL].find({"runner_id": runner_id}, {"_id": 0})
    return [r async for r in cur]


async def count_accounts(runner_id: str) -> int:
    """Raw collection count for a runner — bypasses the flag-OFF
    synthesis. Used by tests + admin diagnostics."""
    db = get_db()
    return await db[ACCOUNTS_COLL].count_documents({"runner_id": runner_id})


__all__ = [
    "ACCOUNTS_COLL", "LEGACY_ACCOUNT_ID",
    "MultiAccountError",
    "ensure_indexes",
    "add_account", "remove_account", "set_active",
    "get_account", "list_accounts", "count_accounts",
]
