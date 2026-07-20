"""Phase 2 Stage 4 P4C.4 — Confidence evolution.

Two audit-event stores that shape retrieval scoring over time:

  * `knowledge_endorsement_events` — one row per successful retrieval
    hit downstream (or per operator-tagged endorsement). Items with
    ≥ N endorsements over rolling 30d get a per-tier boost surfaced
    by the ranker (§ 5.4).
  * `knowledge_contradiction_events` — pairs of items in the same
    domain identified as contradictory (either by a Stage-5 agent or
    by rule). Both items get `contested=true` and are demoted one
    tier for retrieval scoring.

Feature flag: `UKIE_CONFIDENCE_EVOLUTION_ENABLED` (default OFF). When
off, every method short-circuits: `record_endorsement` returns
`flag_off`; `endorsements_last_30d` returns 0; `record_contradiction`
returns `flag_off` and does NOT set `contested=true`.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .constants import KNOWLEDGE_DB_NAME, PIPELINE_CONTRACT_VERSION, PIPELINE_VERSION
from .domains import KnowledgeDomain, storage_collection_for

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_confidence_evolution_enabled() -> bool:
    return _flag("UKIE_CONFIDENCE_EVOLUTION_ENABLED", False)


ENDORSEMENT_EVENTS_COLLECTION = "knowledge_endorsement_events"
CONTRADICTION_EVENTS_COLLECTION = "knowledge_contradiction_events"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EndorsementRow:
    event_id:     str
    at:           str
    kb_id:        str
    domain:       str
    source:       str          # "retrieval" | "operator" | "agent"
    context:      Optional[Dict[str, Any]]     = None
    pipeline_version: str      = PIPELINE_VERSION
    pipeline_contract_version: str = PIPELINE_CONTRACT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContradictionRow:
    event_id:     str
    at:           str
    domain:       str
    kb_id_a:      str
    kb_id_b:      str
    reason:       str
    reported_by:  str
    pipeline_version: str      = PIPELINE_VERSION
    pipeline_contract_version: str = PIPELINE_CONTRACT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConfidenceStore:
    """Writes + reads endorsement / contradiction rows."""

    def __init__(self, *, kb_db_getter: Optional[Callable] = None) -> None:
        self._kb_db_getter = kb_db_getter

    def _kb_db(self):
        if self._kb_db_getter is not None:
            return self._kb_db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            return get_db().client[KNOWLEDGE_DB_NAME]
        except Exception as e:                                  # pragma: no cover
            logger.warning("[confidence] cannot resolve KB DB: %s", e)
            return None

    # ── Endorsements ─────────────────────────────────────────────────

    async def record_endorsement(
        self,
        *,
        kb_id:   str,
        domain:  str,
        source:  str = "retrieval",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not is_confidence_evolution_enabled():
            return {"status": "flag_off"}
        db = self._kb_db()
        if db is None:
            return {"status": "error", "reason": "db_unavailable"}
        row = EndorsementRow(
            event_id=uuid.uuid4().hex,
            at=_now_iso(),
            kb_id=str(kb_id),
            domain=str(domain),
            source=str(source or "retrieval"),
            context=context,
        )
        try:
            await db[ENDORSEMENT_EVENTS_COLLECTION].insert_one(row.to_dict())
        except Exception as e:                                 # noqa: BLE001
            return {"status": "error", "reason": str(e)[:120]}
        return {"status": "recorded", "event_id": row.event_id}

    async def endorsements_last_30d(self, *, kb_id: str) -> int:
        if not is_confidence_evolution_enabled():
            return 0
        db = self._kb_db()
        if db is None:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        try:
            return int(await db[ENDORSEMENT_EVENTS_COLLECTION].count_documents({
                "kb_id": str(kb_id),
                "at":    {"$gte": cutoff},
            }))
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[confidence] count failed: %s", e)
            return 0

    # ── Contradictions ───────────────────────────────────────────────

    async def record_contradiction(
        self,
        *,
        domain:      str,
        kb_id_a:     str,
        kb_id_b:     str,
        reason:      str,
        reported_by: str = "operator",
    ) -> Dict[str, Any]:
        if not is_confidence_evolution_enabled():
            return {"status": "flag_off"}
        db = self._kb_db()
        if db is None:
            return {"status": "error", "reason": "db_unavailable"}
        row = ContradictionRow(
            event_id=uuid.uuid4().hex,
            at=_now_iso(),
            domain=str(domain),
            kb_id_a=str(kb_id_a),
            kb_id_b=str(kb_id_b),
            reason=str(reason or "")[:500],
            reported_by=str(reported_by or "operator"),
        )
        try:
            await db[CONTRADICTION_EVENTS_COLLECTION].insert_one(row.to_dict())
        except Exception as e:                                 # noqa: BLE001
            return {"status": "error", "reason": str(e)[:120]}
        # Mark both items `contested=true` on their KB rows
        try:
            dom = KnowledgeDomain(domain.strip().lower())
            coll_name = storage_collection_for(dom)
            for k in (kb_id_a, kb_id_b):
                try:
                    await db[coll_name].update_one(
                        {"_id": k},
                        {"$set": {"contested": True}},
                    )
                except Exception:                               # noqa: BLE001
                    pass
        except Exception:                                      # noqa: BLE001
            pass
        return {"status": "recorded", "event_id": row.event_id}


_STORE: Optional[ConfidenceStore] = None


def get_confidence_store() -> ConfidenceStore:
    global _STORE
    if _STORE is None:
        _STORE = ConfidenceStore()
    return _STORE


def _reset_for_tests() -> None:
    global _STORE
    _STORE = None
