"""Phase 2 Stage 4 P4B.2 — Dead-letter repository.

Collects tasks that exhaust their retry budget (per §4.2 of the master
plan). Persisted to `workload_dead_letter` with TTL 90 days on
`first_failed_at`.

Feature flag: `COE_DEAD_LETTER_ENABLED` (default OFF). When off,
`record()` / `list_rows()` / `requeue()` / `discard()` all return
early with a `flag_off` marker — the collection is never touched.

Design invariants:
  * Every row carries `pipeline_version_note` and per-class metadata
    for provenance.
  * `requeue()` marks the row `requeued_at` but does not delete —
    audit history is preserved.
  * `discard()` soft-deletes with `discarded_at`, `discarded_by`, and
    a reason string.
  * The repository never mutates production `strategies` or any
    UKIE-KB collection.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_dead_letter_enabled() -> bool:
    return _flag("COE_DEAD_LETTER_ENABLED", False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEAD_LETTER_COLLECTION = "workload_dead_letter"


# ── Row shape ────────────────────────────────────────────────────────

@dataclass
class DeadLetterRow:
    """One row in the dead-letter collection.

    Attributes match plan §4.2. `payload_snapshot` is deliberately
    optional — some tasks carry PII / large payloads that we do not
    want to persist. The caller supplies a redacted / summarised form.
    """
    row_id:            str
    workload_class:    str
    task_kind:         str
    task_id:           str
    error_class:       str
    error_message:     str
    first_failed_at:   str
    last_failed_at:    str
    attempts:          int
    provider:          Optional[str]                    = None
    payload_snapshot:  Optional[Dict[str, Any]]         = None
    requeued_at:       Optional[str]                    = None
    discarded_at:      Optional[str]                    = None
    discarded_by:      Optional[str]                    = None
    discard_reason:    Optional[str]                    = None
    pipeline_version_note: str                          = "coe_gamma_dead_letter_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Repository ───────────────────────────────────────────────────────

class DeadLetterRepository:
    """Persists dead-letter rows to Mongo.

    Injectable DB getter for tests. When
    `COE_DEAD_LETTER_ENABLED=false`, every method returns a
    flag-off marker without touching Mongo.
    """

    def __init__(self, db_getter=None) -> None:
        self._db_getter = db_getter

    def _db(self):
        if self._db_getter is not None:
            return self._db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            return get_db()
        except Exception as e:                                 # pragma: no cover
            logger.warning("[coe_gamma.dead_letter] cannot resolve DB: %s", e)
            return None

    # ── Writes ───────────────────────────────────────────────────────

    async def record(
        self,
        *,
        workload_class: str,
        task_kind:      str,
        task_id:        str,
        error_class:    str,
        error_message:  str,
        attempts:       int,
        provider:       Optional[str] = None,
        payload_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not is_dead_letter_enabled():
            return {"status": "flag_off", "reason": "COE_DEAD_LETTER_ENABLED is off"}
        db = self._db()
        if db is None:
            return {"status": "error", "reason": "db_unavailable"}
        now = _now_iso()
        row = DeadLetterRow(
            row_id=uuid.uuid4().hex,
            workload_class=workload_class,
            task_kind=task_kind,
            task_id=task_id,
            error_class=error_class,
            error_message=(error_message or "")[:2000],
            first_failed_at=now,
            last_failed_at=now,
            attempts=int(attempts or 1),
            provider=provider,
            payload_snapshot=payload_snapshot,
        )
        try:
            await db[DEAD_LETTER_COLLECTION].insert_one(row.to_dict())
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[coe_gamma.dead_letter] record failed: %s", e)
            return {"status": "error", "reason": f"insert_failed:{str(e)[:120]}"}
        return {"status": "recorded", "row_id": row.row_id}

    async def requeue(self, row_id: str, *, requested_by: str) -> Dict[str, Any]:
        if not is_dead_letter_enabled():
            return {"status": "flag_off"}
        db = self._db()
        if db is None:
            return {"status": "error", "reason": "db_unavailable"}
        try:
            res = await db[DEAD_LETTER_COLLECTION].update_one(
                {"row_id": row_id},
                {"$set": {
                    "requeued_at":     _now_iso(),
                    "requeued_by":     requested_by,
                }},
            )
        except Exception as e:                                 # noqa: BLE001
            return {"status": "error", "reason": str(e)[:120]}
        return {
            "status":   "requeued" if getattr(res, "matched_count", 0) else "not_found",
            "row_id":   row_id,
        }

    async def discard(self, row_id: str, *, requested_by: str, reason: str) -> Dict[str, Any]:
        if not is_dead_letter_enabled():
            return {"status": "flag_off"}
        db = self._db()
        if db is None:
            return {"status": "error", "reason": "db_unavailable"}
        try:
            res = await db[DEAD_LETTER_COLLECTION].update_one(
                {"row_id": row_id},
                {"$set": {
                    "discarded_at":     _now_iso(),
                    "discarded_by":     requested_by,
                    "discard_reason":   (reason or "")[:500],
                }},
            )
        except Exception as e:                                 # noqa: BLE001
            return {"status": "error", "reason": str(e)[:120]}
        return {
            "status":   "discarded" if getattr(res, "matched_count", 0) else "not_found",
            "row_id":   row_id,
        }

    # ── Reads ────────────────────────────────────────────────────────

    async def list_rows(
        self,
        *,
        workload_class: Optional[str] = None,
        limit:          int           = 100,
        offset:         int           = 0,
        include_discarded: bool       = False,
    ) -> List[Dict[str, Any]]:
        if not is_dead_letter_enabled():
            return []
        db = self._db()
        if db is None:
            return []
        q: Dict[str, Any] = {}
        if workload_class:
            q["workload_class"] = workload_class
        if not include_discarded:
            q["discarded_at"] = None
        try:
            cur = db[DEAD_LETTER_COLLECTION].find(q).skip(int(offset)).limit(int(limit))
            rows: List[Dict[str, Any]] = []
            async for r in cur:
                r.pop("_id", None)
                rows.append(r)
            return rows
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[coe_gamma.dead_letter] list failed: %s", e)
            return []

    async def get(self, row_id: str) -> Optional[Dict[str, Any]]:
        if not is_dead_letter_enabled():
            return None
        db = self._db()
        if db is None:
            return None
        try:
            row = await db[DEAD_LETTER_COLLECTION].find_one({"row_id": row_id})
            if row is None:
                return None
            row.pop("_id", None)
            return row
        except Exception:                                       # noqa: BLE001
            return None

    async def depth(self, *, workload_class: Optional[str] = None) -> int:
        """Non-discarded, non-requeued row count — used by the depth alert."""
        if not is_dead_letter_enabled():
            return 0
        db = self._db()
        if db is None:
            return 0
        q: Dict[str, Any] = {"discarded_at": None, "requeued_at": None}
        if workload_class:
            q["workload_class"] = workload_class
        try:
            return int(await db[DEAD_LETTER_COLLECTION].count_documents(q))
        except Exception:                                       # noqa: BLE001
            return 0


# ── Module-level singleton ───────────────────────────────────────────

_REPO: Optional[DeadLetterRepository] = None


def get_dead_letter_repository() -> DeadLetterRepository:
    global _REPO
    if _REPO is None:
        _REPO = DeadLetterRepository()
    return _REPO


def _reset_for_tests() -> None:
    global _REPO
    _REPO = None
