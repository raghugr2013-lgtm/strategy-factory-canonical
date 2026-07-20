"""Phase 2 Stage 4 P4D.3 — Knowledge metrics.

`GET /api/knowledge/metrics` — aggregate operational metrics over
`strategy_knowledge_base`. Read-only.

Feature flag: `UKIE_METRICS_ENABLED` (default OFF). Endpoint returns
HTTP 503 when off.

Design: every count is a best-effort Mongo aggregation with a
try/except fall-through — the endpoint never crashes on a partial
DB failure.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from .constants import KNOWLEDGE_DB_NAME
from .domains import KnowledgeDomain, storage_collection_for

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_metrics_enabled() -> bool:
    return _flag("UKIE_METRICS_ENABLED", False)


class KnowledgeMetrics:
    """Aggregates KB metrics."""

    def __init__(self, *, kb_db_getter: Optional[Callable] = None) -> None:
        self._kb_db_getter = kb_db_getter

    def _kb_db(self):
        if self._kb_db_getter is not None:
            return self._kb_db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            return get_db().client[KNOWLEDGE_DB_NAME]
        except Exception:                                       # pragma: no cover
            return None

    async def snapshot(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        result: Dict[str, Any] = {
            "generated_at":                 now.isoformat(),
            "rows_per_domain":              {},
            "trust_tier_distribution":      {},
            "license_outcome_distribution": {},
            "rows_last_24h":                0,
            "rows_last_7d":                 0,
            "rows_last_30d":                0,
            "promote_event_counts":         {},
            "retro_score_run_counts":       {},
        }
        db = self._kb_db()
        if db is None:
            result["status"] = "db_unavailable"
            return result

        cutoff_24h = (now - timedelta(days=1)).isoformat()
        cutoff_7d = (now - timedelta(days=7)).isoformat()
        cutoff_30d = (now - timedelta(days=30)).isoformat()

        for domain in KnowledgeDomain:
            coll_name = storage_collection_for(domain)
            try:
                n = int(await db[coll_name].count_documents({}))
            except Exception:                                   # noqa: BLE001
                n = 0
            result["rows_per_domain"][domain.value] = n

            # per-domain time-windowed counts (best-effort)
            for cutoff, key in ((cutoff_24h, "rows_last_24h"),
                                (cutoff_7d, "rows_last_7d"),
                                (cutoff_30d, "rows_last_30d")):
                try:
                    c = int(await db[coll_name].count_documents({"inserted_at": {"$gte": cutoff}}))
                except Exception:                              # noqa: BLE001
                    c = 0
                result[key] += c

            # trust tier + licence distributions
            for tier in (1, 2, 3, 4, 5):
                try:
                    c = int(await db[coll_name].count_documents({"trust_tier": tier}))
                except Exception:                              # noqa: BLE001
                    c = 0
                key = f"T{tier}"
                result["trust_tier_distribution"][key] = result["trust_tier_distribution"].get(key, 0) + c

            for outcome in ("permissive", "weak_copyleft", "strong_copyleft", "proprietary", "unknown"):
                try:
                    c = int(await db[coll_name].count_documents({"license_verdict.outcome": outcome}))
                except Exception:                              # noqa: BLE001
                    c = 0
                result["license_outcome_distribution"][outcome] = (
                    result["license_outcome_distribution"].get(outcome, 0) + c
                )

        # promote_event / retro_score_run aggregates
        for (coll_name, target_key, field, values) in (
            ("promote_events",   "promote_event_counts",   "resolved",
             ("promoted", "refused", "dry_run", "demoted", "already_demoted", "flag_off")),
            ("retro_score_runs", "retro_score_run_counts", "dry_run",
             (True, False)),
        ):
            for v in values:
                try:
                    c = int(await db[coll_name].count_documents({field: v}))
                except Exception:                              # noqa: BLE001
                    c = 0
                result[target_key][str(v)] = c

        result["status"] = "ok"
        return result


_METRICS: Optional[KnowledgeMetrics] = None


def get_knowledge_metrics() -> KnowledgeMetrics:
    global _METRICS
    if _METRICS is None:
        _METRICS = KnowledgeMetrics()
    return _METRICS


def _reset_for_tests() -> None:
    global _METRICS
    _METRICS = None
