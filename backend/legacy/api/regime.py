"""Phase 29.0 — Regime evidence API (read-only, on-read backfill only).

Three GET endpoints surface regime evidence computed live from
``strategy_performance_history`` rows. No POST / PATCH / DELETE — no
writes anywhere. Lifecycle docs are NEVER mutated by this router.

All endpoints stamp ``phase: "29.0"`` and ``advisory_only: true`` so the
operator can distinguish observation mode from any future hard-gate
mode (29.1 candidate decision).

Mounted under ``/api`` by ``server.py`` — produces:
    GET /api/regime/strategy/{strategy_hash}
    GET /api/regime/cohort-distribution
    GET /api/lifecycle/regime-evidence/{strategy_hash}

Auth: gated by the global ``AuthMiddleware`` (allowlist exempts only
``/api/health`` and ``/api/auth/*``).

Reversibility:
    Drop this file + remove the router mount in ``server.py`` → 260
    pre-29 routes resume bit-identical. No data migration needed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from engines import regime_performance as rp
from engines.db import get_db
from engines.strategy_memory import HISTORY_COLL

logger = logging.getLogger(__name__)

# Mounted by server.py with prefix="/api" → routes resolve under
# /api/regime/* and /api/lifecycle/regime-evidence/*.
router = APIRouter(tags=["regime"])


async def _fetch_history_rows(strategy_hash: str) -> List[Dict[str, Any]]:
    """Load all `strategy_performance_history` rows for a hash.

    Projection excludes ``_id`` (MongoDB ObjectId — not JSON-serialisable
    and operator-policy excluded from every API response).
    """
    if not strategy_hash:
        return []
    db = get_db()
    cur = db[HISTORY_COLL].find(
        {"strategy_hash": strategy_hash}, {"_id": 0},
    )
    return [doc async for doc in cur]


# ── 1. Per-strategy regime evidence ─────────────────────────────────

@router.get("/regime/strategy/{strategy_hash}")
async def regime_for_strategy(strategy_hash: str) -> Dict[str, Any]:
    """Return on-read regime evidence for one strategy.

    Returns 200 with a stable shape even when the strategy has zero
    history rows — that is the "no evidence yet" semantic, parallel to
    ``BI5_DATA_MISSING``. The advisory ``fragile`` field defaults to
    True with breadth_count=0 in that case (zero evidence IS fragile),
    but per operator decision #1 this NEVER caps any lifecycle stage.
    """
    rows = await _fetch_history_rows(strategy_hash)
    evidence = rp.compute_regime_performance(rows)
    return {
        "strategy_hash":  strategy_hash,
        "row_count":      len(rows),
        "evidence":       evidence,
    }


# ── 2. Cohort distribution (read-only aggregate) ────────────────────

@router.get("/regime/cohort-distribution")
async def regime_cohort_distribution(
    limit: int = Query(500, ge=1, le=500),
) -> Dict[str, Any]:
    """Aggregate regime-evidence distribution across the cohort.

    Live-computed. No writes. Sweeps distinct strategy hashes in
    ``strategy_performance_history`` (capped at ``limit``) and reports:

      * histogram of ``breadth_count`` across the cohort (0..4)
      * count of strategies flagged ``fragile`` (advisory; 0 of which
        cap any stage in 29.0)
      * per-canonical-regime occupancy: how many strategies have
        evidential edge (sample_adequate AND edge_positive) in each
    """
    db = get_db()
    pipeline = [
        {"$match": {"strategy_hash": {"$ne": None}}},
        {"$group": {"_id": "$strategy_hash"}},
        {"$limit": int(limit)},
    ]
    hashes: List[str] = []
    async for doc in db[HISTORY_COLL].aggregate(pipeline):
        h = doc.get("_id")
        if h:
            hashes.append(h)

    distribution: Dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}
    fragile_count = 0
    per_regime_occupancy: Dict[str, int] = {r: 0 for r in rp.REGIMES_CANONICAL}
    strategies_with_unknown_only = 0

    for h in hashes:
        rows = await _fetch_history_rows(h)
        evidence = rp.compute_regime_performance(rows)
        bc = evidence["breadth_count"]
        distribution[str(bc)] = distribution.get(str(bc), 0) + 1
        if evidence["fragile"]:
            fragile_count += 1
        for regime in evidence["regimes_breadth"]:
            if regime in per_regime_occupancy:
                per_regime_occupancy[regime] += 1
        # Operator guarantee #2: unknown is a refusal state. We surface
        # it as a separate counter so operators can see how often the
        # classifier refuses, WITHOUT treating it as negative evidence.
        if (
            not evidence["regimes_seen"]
            or evidence["regimes_seen"] == [rp.REGIME_UNKNOWN]
        ):
            strategies_with_unknown_only += 1

    return {
        "strategies_evaluated":         len(hashes),
        "limit":                        int(limit),
        "breadth_count_distribution":   distribution,
        "fragile_count":                fragile_count,
        "per_regime_breadth_occupancy": per_regime_occupancy,
        "strategies_with_unknown_only": strategies_with_unknown_only,
        "computed_at":                  rp._now_iso(),
        "phase":                        rp.PHASE_VERSION,
        "advisory_only":                True,
    }


# ── 3. Lifecycle-prefixed alias (operator convenience) ──────────────

@router.get("/lifecycle/regime-evidence/{strategy_hash}")
async def lifecycle_regime_evidence(strategy_hash: str) -> Dict[str, Any]:
    """Alias of ``/regime/strategy/{hash}`` mounted under the lifecycle
    namespace for operators inspecting a strategy's promotion narrative.

    The lifecycle doc itself is NEVER mutated by this endpoint
    (operator decision #4 — on-read backfill only). The evidence is
    computed live and returned as a separate payload.
    """
    rows = await _fetch_history_rows(strategy_hash)
    evidence = rp.compute_regime_performance(rows)
    return {
        "strategy_hash":              strategy_hash,
        "row_count":                  len(rows),
        "regime_evidence":            evidence,
        "lifecycle_doc_mutated":      False,
        "note":                       (
            "Phase 29.0 — observational only. Lifecycle doc is not "
            "written by this endpoint. REGIME_FRAGILE flag exists in "
            "the taxonomy but is not emitted to persisted lifecycle "
            "docs in 29.0 (operator-decision deferred to 29.1)."
        ),
    }
