"""Phase 2 Stage 4 P4C.3 — Knowledge lifecycle sweeper.

Respects each domain's `default_retention_policy`:
  * `forever`  → never expires
  * `365d`, `180d`, `90d` → TTL on `inserted_at`
  * `session` → deleted on every sweep

Every expiry writes one row to
`strategy_knowledge_base.lifecycle_events` with:
  event_id, at, run_id, domain, deleted_count, retention_policy,
  cutoff_iso, pipeline_version, pipeline_contract_version.

Feature flag: `UKIE_LIFECYCLE_SWEEP_ENABLED` (default OFF). When off,
`sweep()` returns `{"status": "flag_off"}` immediately — nothing is
read, nothing is written.

Decay annotation (§5.3 second half): items in `market` /
`execution` that survive a sweep get `confidence_decay=<0..1>`
annotated so retrieval can penalise them without deleting. Decay is
computed as `min(1.0, age_s / policy_seconds)` — 0 at insert time,
1.0 at the retention boundary. Setting `annotate_decay_only=True`
skips deletion and only annotates (safe dry-run mode).
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .constants import KNOWLEDGE_DB_NAME, PIPELINE_CONTRACT_VERSION, PIPELINE_VERSION
from .domains import KnowledgeDomain, get_domain_spec, storage_collection_for

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_lifecycle_sweep_enabled() -> bool:
    return _flag("UKIE_LIFECYCLE_SWEEP_ENABLED", False)


LIFECYCLE_EVENTS_COLLECTION = "lifecycle_events"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_seconds(policy: str) -> Optional[int]:
    """Return TTL in seconds for a policy string, or None for `forever`.
    `session` maps to 0 (immediate — sweep deletes anything without a
    fresh-session marker)."""
    p = (policy or "").strip().lower()
    if p == "forever":
        return None
    if p == "session":
        return 0
    if p.endswith("d"):
        try:
            return int(p[:-1]) * 86400
        except ValueError:
            return None
    return None


@dataclass
class SweepSummary:
    run_id:                       str
    started_at:                   str
    finished_at:                  str
    dry_run:                      bool
    annotate_decay_only:          bool
    total_scanned:                int  = 0
    total_deleted:                int  = 0
    total_decayed:                int  = 0
    per_domain:                   List[Dict[str, Any]] = field(default_factory=list)
    pipeline_version:             str  = PIPELINE_VERSION
    pipeline_contract_version:    str  = PIPELINE_CONTRACT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LifecycleSweeper:
    """Runs retention + decay across every KB domain sub-collection."""

    def __init__(self, *, kb_db_getter: Optional[Callable] = None) -> None:
        self._kb_db_getter = kb_db_getter

    def _kb_db(self):
        if self._kb_db_getter is not None:
            return self._kb_db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            return get_db().client[KNOWLEDGE_DB_NAME]
        except Exception as e:                                  # pragma: no cover
            logger.warning("[lifecycle] cannot resolve KB DB: %s", e)
            return None

    async def sweep(
        self,
        *,
        dry_run: bool = True,
        annotate_decay_only: bool = False,
    ) -> SweepSummary:
        summary = SweepSummary(
            run_id=uuid.uuid4().hex,
            started_at=_now_iso(),
            finished_at="",
            dry_run=dry_run,
            annotate_decay_only=annotate_decay_only,
        )
        if not is_lifecycle_sweep_enabled():
            summary.finished_at = _now_iso()
            summary.per_domain.append({"reason": "flag_off"})
            return summary

        db = self._kb_db()
        if db is None:
            summary.finished_at = _now_iso()
            summary.per_domain.append({"reason": "db_unavailable"})
            return summary

        now = datetime.now(timezone.utc)

        for domain in KnowledgeDomain:
            try:
                spec = get_domain_spec(domain)
            except Exception:                                   # noqa: BLE001
                continue
            policy = spec.default_retention_policy
            ttl = _policy_seconds(policy)
            coll = storage_collection_for(domain)
            per = {
                "domain":            domain.value,
                "retention_policy":  policy,
                "collection":        coll,
                "scanned":           0,
                "deleted":           0,
                "decayed":           0,
            }
            if ttl is None:  # forever
                per["reason"] = "forever_no_ttl"
                summary.per_domain.append(per)
                continue

            cutoff = now - timedelta(seconds=ttl)
            try:
                # SCAN — count everything in the collection for reporting
                cur = db[coll].find({}).limit(50000)
                deletable_ids: List[Any] = []
                decayed = 0
                async for row in cur:
                    per["scanned"] += 1
                    inserted_at = row.get("inserted_at")
                    if not isinstance(inserted_at, str):
                        continue
                    try:
                        ts = datetime.fromisoformat(inserted_at)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue

                    age_s = max(0, (now - ts).total_seconds())
                    if age_s >= ttl:
                        deletable_ids.append(row.get("_id"))
                    else:
                        # decay annotation for market / execution
                        if domain in (KnowledgeDomain.MARKET, KnowledgeDomain.EXECUTION):
                            decay = min(1.0, age_s / max(1, ttl))
                            if not dry_run and annotate_decay_only is not False:  # noqa: SIM108
                                pass
                            if not dry_run:
                                try:
                                    await db[coll].update_one(
                                        {"_id": row.get("_id")},
                                        {"$set": {"confidence_decay": decay}},
                                    )
                                    decayed += 1
                                except Exception:                # noqa: BLE001
                                    pass
                            else:
                                decayed += 1

                per["decayed"] = decayed
                summary.total_scanned += per["scanned"]
                summary.total_decayed += decayed

                if deletable_ids and not annotate_decay_only:
                    if dry_run:
                        per["deleted"] = len(deletable_ids)
                        per["dry_run"] = True
                    else:
                        try:
                            res = await db[coll].delete_many({"_id": {"$in": deletable_ids}})
                            per["deleted"] = int(getattr(res, "deleted_count", 0) or 0)
                        except Exception as e:                   # noqa: BLE001
                            per["deleted"] = 0
                            per["error"] = str(e)[:120]
                summary.total_deleted += int(per["deleted"] or 0)

                # audit event per (domain, run)
                if not dry_run:
                    try:
                        await db[LIFECYCLE_EVENTS_COLLECTION].insert_one({
                            "event_id":                  uuid.uuid4().hex,
                            "at":                        _now_iso(),
                            "run_id":                    summary.run_id,
                            "domain":                    domain.value,
                            "deleted_count":             per["deleted"],
                            "decayed_count":             per["decayed"],
                            "retention_policy":          policy,
                            "cutoff_iso":                cutoff.isoformat(),
                            "pipeline_version":          PIPELINE_VERSION,
                            "pipeline_contract_version": PIPELINE_CONTRACT_VERSION,
                        })
                    except Exception as e:                       # noqa: BLE001
                        logger.debug("[lifecycle] audit failed: %s", e)
            except Exception as e:                              # noqa: BLE001
                per["error"] = str(e)[:120]
            summary.per_domain.append(per)

        summary.finished_at = _now_iso()
        return summary


_SWEEPER: Optional[LifecycleSweeper] = None


def get_lifecycle_sweeper() -> LifecycleSweeper:
    global _SWEEPER
    if _SWEEPER is None:
        _SWEEPER = LifecycleSweeper()
    return _SWEEPER


def _reset_for_tests() -> None:
    global _SWEEPER
    _SWEEPER = None
