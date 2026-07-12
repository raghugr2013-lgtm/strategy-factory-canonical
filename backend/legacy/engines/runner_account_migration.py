"""MB-9 Phase 2.B — Runner Account Migration helper.

One-shot, idempotent bootstrap that creates a legacy
``runner_accounts`` row for every existing runner that does not yet
carry one. Lets the operator flip ``RUNNER_MULTI_ACCOUNT_ENABLED=true``
*later* without losing the per-runner single-account semantics that
Phase 1 deployments already rely on.

Discipline (R-track, default-OFF, additive-only):

  * **Read-mostly.** Touches the ``runner_accounts`` collection ONLY
    (insert + count + list). NEVER mutates ``master_bot_runners``.
  * **Idempotent.** Re-running yields zero inserts on a fully
    migrated fleet. Safe to invoke at any time, including before any
    Phase 2 flag is flipped.
  * **Honest refusal.** A disabled runner is skipped (never seeded).
  * **No flag consultation.** The migration is operator-driven (admin
    API call). It does NOT auto-run at boot — the call site is the
    new admin endpoint, not the startup hook.
  * **Sha256-hash-only.** The legacy row carries
    ``credentials_envelope_hash=None`` to signal "the operator has
    not yet pushed an envelope for this account".

Schema written (one row per skipped runner, ``broker="ctrader"`` by
default to match Phase 1):

    {
        "runner_id":                  <existing runner_id>,
        "account_id":                 multi_account_envelope.LEGACY_ACCOUNT_ID,
        "broker":                     "ctrader",
        "credentials_envelope_hash":  None,
        "active":                     True,
        "created_at":                 <ISO utc now>,
        "created_by":                 <actor>,
        "migration_source":           "mb9_phase2_legacy_bootstrap",
        "notes":                      "Auto-bootstrap from master_bot_runners",
    }

Returns a structured report:

    {
        "considered":   <int>,
        "inserted":     [<runner_id>, ...],
        "already":      [<runner_id>, ...],
        "skipped":      [{"runner_id": ..., "reason": "disabled"}, ...],
        "errors":       [{"runner_id": ..., "error": ...}, ...],
        "completed_at": <ISO utc now>,
    }
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from engines.db import get_db
from engines import multi_account_envelope as mae
from engines import runner_registry as runners

logger = logging.getLogger(__name__)

MIGRATION_SOURCE_TAG = "mb9_phase2_legacy_bootstrap"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def bootstrap_legacy_accounts(*, actor: str = "admin") -> Dict[str, Any]:
    """Insert one ``runner_accounts`` row per active runner that lacks
    a legacy row. Idempotent on repeat calls."""
    db = get_db()
    # Make sure both target collections have their indexes.
    await mae.ensure_indexes()

    cur = db[runners.RUNNERS_COLL].find(
        {}, {"_id": 0, "runner_id": 1, "status": 1, "name": 1},
    )
    considered = 0
    inserted: List[str] = []
    already:  List[str] = []
    skipped:  List[Dict[str, Any]] = []
    errors:   List[Dict[str, Any]] = []
    async for r in cur:
        runner_id = r.get("runner_id")
        if not runner_id:
            continue
        considered += 1
        if r.get("status") == "disabled":
            skipped.append({"runner_id": runner_id, "reason": "disabled"})
            continue
        # Existence check on the legacy row only — operator-added
        # account rows must NEVER be overwritten by this helper.
        existing = await db[mae.ACCOUNTS_COLL].find_one(
            {"runner_id":  runner_id,
             "account_id": mae.LEGACY_ACCOUNT_ID},
            {"_id": 0, "runner_id": 1},
        )
        if existing:
            already.append(runner_id)
            continue
        doc = {
            "runner_id":                  runner_id,
            "account_id":                 mae.LEGACY_ACCOUNT_ID,
            "broker":                     "ctrader",
            "credentials_envelope_hash":  None,
            "active":                     True,
            "created_at":                 _now_iso(),
            "created_by":                 actor,
            "migration_source":           MIGRATION_SOURCE_TAG,
            "notes":                      "Auto-bootstrap from master_bot_runners",
        }
        try:
            await db[mae.ACCOUNTS_COLL].insert_one(doc)
            inserted.append(runner_id)
        except Exception as exc:  # pragma: no cover — DuplicateKeyError race
            logger.exception("legacy-account insert failed for %s", runner_id)
            errors.append({"runner_id": runner_id, "error": str(exc)})
    return {
        "considered":   considered,
        "inserted":     inserted,
        "already":      already,
        "skipped":      skipped,
        "errors":       errors,
        "completed_at": _now_iso(),
    }


async def migration_status() -> Dict[str, Any]:
    """Read-only summary suitable for the admin diagnostic surface."""
    db = get_db()
    total_runners = await db[runners.RUNNERS_COLL].count_documents({})
    active_runners = await db[runners.RUNNERS_COLL].count_documents(
        {"status": {"$ne": "disabled"}},
    )
    legacy_rows = await db[mae.ACCOUNTS_COLL].count_documents(
        {"account_id": mae.LEGACY_ACCOUNT_ID},
    )
    bootstrap_rows = await db[mae.ACCOUNTS_COLL].count_documents(
        {"migration_source": MIGRATION_SOURCE_TAG},
    )
    return {
        "total_runners":          total_runners,
        "active_runners":         active_runners,
        "legacy_account_rows":    legacy_rows,
        "bootstrapped_rows":      bootstrap_rows,
        "fully_migrated":         legacy_rows >= active_runners,
        "computed_at":            _now_iso(),
    }


__all__ = [
    "MIGRATION_SOURCE_TAG",
    "bootstrap_legacy_accounts",
    "migration_status",
]
