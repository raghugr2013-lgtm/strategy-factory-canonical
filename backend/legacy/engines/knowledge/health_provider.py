"""Phase 2 Stage 4 P4D.1 — UKIE health provider.

Assembles the `ukie` block for `/api/health/system`. Composes:
  * flag matrix (which UKIE flags are currently on/off)
  * KB row count per domain
  * connector count + per-connector health snapshots
  * recent audit-event counts (promote 24h, retro-score-runs 24h,
    connector-events 24h, lifecycle-events 24h)
  * dry-run verification stamp

Feature flag: `UKIE_HEALTH_PROVIDER_ENABLED` (default OFF). When off,
`snapshot()` returns None and the aggregator omits the `ukie` block —
no shape change to existing `/api/health/system` consumers.

Read-only. No mutation. Every read is best-effort — a Mongo hiccup
returns partial counts rather than crashing the health endpoint.
"""
from __future__ import annotations

import logging
import os
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


def is_ukie_health_provider_enabled() -> bool:
    return _flag("UKIE_HEALTH_PROVIDER_ENABLED", False)


_TRACKED_FLAGS: List[str] = [
    # Stage 3
    "UKIE_DOMAIN_REGISTRY_ENABLED",
    "ENABLE_DOMAIN_ROUTING",
    "ENABLE_DEDUP_CHECK",
    "ENABLE_LICENSE_GATE",
    "ENABLE_TRUST_SCORER",
    "UKIE_GOVERNANCE_CUTOVER",
    "UKIE_PROMOTE_BRIDGE_ENABLED",
    "UKIE_PROMOTE_DRY_RUN",
    "UKIE_RETRO_SCORE_ENABLED",
    # Stage 4
    "UKIE_CONNECTOR_FRAMEWORK_ENABLED",
    "UKIE_CONNECTOR_ARXIV_ENABLED",
    "UKIE_CONNECTOR_PDF_ENABLED",
    "UKIE_CONNECTOR_PROPFIRM_ENABLED",
    "UKIE_CONNECTOR_TRADINGVIEW_ENABLED",
    "UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED",
    "UKIE_QUERY_API_ENABLED",
    "UKIE_RANKING_V2_ENABLED",
    "UKIE_LIFECYCLE_SWEEP_ENABLED",
    "UKIE_CONFIDENCE_EVOLUTION_ENABLED",
    "UKIE_GOVERNANCE_POLICY_ENABLED",
    "UKIE_HEALTH_PROVIDER_ENABLED",
    "UKIE_METRICS_ENABLED",
    "UKIE_AUDIT_VISIBILITY_ENABLED",
]


class UkieHealthProvider:
    """Composes the `ukie` subsystem block for `/api/health/system`."""

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

    async def snapshot(self) -> Optional[Dict[str, Any]]:
        if not is_ukie_health_provider_enabled():
            return None

        flags = {name: _flag(name, False) for name in _TRACKED_FLAGS}
        kb_row_count = 0
        per_domain_counts: Dict[str, int] = {}
        recent_promote_events_24h = 0
        recent_retro_score_runs_24h = 0
        recent_lifecycle_events_24h = 0
        recent_connector_events_24h = 0

        db = self._kb_db()
        if db is not None:
            cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            for domain in KnowledgeDomain:
                coll = storage_collection_for(domain)
                try:
                    n = int(await db[coll].count_documents({}))
                except Exception:                              # noqa: BLE001
                    n = 0
                per_domain_counts[domain.value] = n
                kb_row_count += n
            for coll_name, target in (
                ("promote_events", "recent_promote_events_24h"),
                ("retro_score_runs", "recent_retro_score_runs_24h"),
                ("lifecycle_events", "recent_lifecycle_events_24h"),
                ("connector_events", "recent_connector_events_24h"),
            ):
                try:
                    n = int(await db[coll_name].count_documents({"at": {"$gte": cutoff_24h}}))
                except Exception:                              # noqa: BLE001
                    n = 0
                # Assign via locals — the compiler cannot help so map explicitly
                if target == "recent_promote_events_24h":       recent_promote_events_24h = n
                elif target == "recent_retro_score_runs_24h":   recent_retro_score_runs_24h = n
                elif target == "recent_lifecycle_events_24h":   recent_lifecycle_events_24h = n
                elif target == "recent_connector_events_24h":   recent_connector_events_24h = n

        # Per-connector health snapshots (from the observer)
        connector_snapshots: List[Dict[str, Any]] = []
        try:
            from .registry import list_connectors
            for c in list_connectors():
                fn = getattr(c, "health_snapshot", None)
                if callable(fn):
                    try:
                        connector_snapshots.append(fn().to_dict())
                    except Exception:                          # noqa: BLE001
                        pass
        except Exception:                                      # noqa: BLE001
            pass

        # Overall subsystem status
        cutover_on = flags.get("UKIE_GOVERNANCE_CUTOVER", False)
        registry_on = flags.get("UKIE_DOMAIN_REGISTRY_ENABLED", False)
        if not registry_on and not cutover_on:
            status = "dormant"
        elif kb_row_count == 0 and cutover_on:
            status = "healthy_empty"
        elif kb_row_count > 0:
            status = "healthy"
        else:
            status = "opted_in"

        return {
            "subsystem":                     "ukie",
            "status":                        status,
            "flags":                         flags,
            "pipeline_version":              PIPELINE_VERSION,
            "pipeline_contract_version":     PIPELINE_CONTRACT_VERSION,
            "kb_row_count":                  kb_row_count,
            "kb_row_count_per_domain":       per_domain_counts,
            "connector_count":               len(connector_snapshots),
            "connector_health":              connector_snapshots,
            "recent_promote_events_24h":     recent_promote_events_24h,
            "recent_retro_score_runs_24h":   recent_retro_score_runs_24h,
            "recent_lifecycle_events_24h":   recent_lifecycle_events_24h,
            "recent_connector_events_24h":   recent_connector_events_24h,
            "checked_at":                    datetime.now(timezone.utc).isoformat(),
        }


_PROVIDER: Optional[UkieHealthProvider] = None


def get_ukie_health_provider() -> UkieHealthProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = UkieHealthProvider()
    return _PROVIDER


def _reset_for_tests() -> None:
    global _PROVIDER
    _PROVIDER = None
