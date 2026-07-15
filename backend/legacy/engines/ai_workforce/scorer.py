"""v1.2.0-alpha2 Phase B — Provider quality scorer.

Rolls outcome events up into a per-provider "quality score" derived
from how often strategies produced by that provider survive the
downstream stages (validate → backtest → optimize). Cheap Mongo
aggregation, cached in-process for 60s so callers can hit it on every
route_call without hammering the DB.

Scoring rubric (weights are internal but exposed in the response for
transparency):

    quality_score = 0.4 * generate_pass_rate
                  + 0.3 * backtest_pass_rate
                  + 0.2 * optimize_pass_rate
                  + 0.1 * operator_pass_rate

Providers with `total_events < LEARNING_RETRIEVAL_MIN_EVENTS` receive
a `warmup=True` flag and a floor score of 0.5 so brand-new providers
don't get starved forever.
"""
from __future__ import annotations

import logging
import time
from threading import RLock
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.learning import COLL as _EVENTS_COLL

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 60.0
_LOCK = RLock()
_CACHE: Dict[str, Any] = {"ts": 0.0, "value": None}

_STAGE_WEIGHTS = {
    "generate":       0.4,
    "backtest":       0.3,
    "optimize":       0.2,
    "approve":        0.1,
}


async def _aggregate() -> List[Dict[str, Any]]:
    db = get_db()
    pipeline = [
        {"$match": {"provider": {"$ne": None}}},
        {"$group": {
            "_id": {"provider": "$provider", "stage": "$stage",
                    "status": "$status"},
            "n": {"$sum": 1},
        }},
    ]
    rows: List[Dict[str, Any]] = []
    async for r in db[_EVENTS_COLL].aggregate(pipeline):
        rows.append(r)
    return rows


def _fold(rows: List[Dict[str, Any]], min_events: int) -> Dict[str, Any]:
    from engines.learning import config as lcfg  # local — avoid import cycles at module load
    per_provider: Dict[str, Dict[str, Dict[str, int]]] = {}
    for r in rows:
        rid = r["_id"] or {}
        prov = rid.get("provider")
        stage = rid.get("stage")
        status = rid.get("status")
        if not prov or not stage or not status:
            continue
        per_provider.setdefault(prov, {}).setdefault(stage, {}).setdefault(status, 0)
        per_provider[prov][stage][status] += int(r.get("n", 0))

    scores: List[Dict[str, Any]] = []
    for prov, per_stage in per_provider.items():
        components: Dict[str, Any] = {}
        weighted_sum = 0.0
        total_weight = 0.0
        total_events = 0
        for stage, w in _STAGE_WEIGHTS.items():
            stats = per_stage.get(stage, {})
            n_pass = int(stats.get("pass", 0))
            n_fail = int(stats.get("fail", 0))
            n_part = int(stats.get("partial", 0))
            n_total = n_pass + n_fail + n_part
            rate = (n_pass + 0.5 * n_part) / n_total if n_total else 0.0
            components[stage] = {"n": n_total, "pass": n_pass,
                                 "fail": n_fail, "partial": n_part,
                                 "rate": round(rate, 4)}
            if n_total:
                weighted_sum += rate * w
                total_weight += w
                total_events += n_total
        if total_weight > 0:
            score = weighted_sum / total_weight
        else:
            score = 0.5  # neutral warm-up
        warmup = total_events < max(1, min_events)
        if warmup:
            # Bias new providers up so they get exploration, but not
            # so far that a proven provider is displaced.
            score = max(score, 0.5)
        scores.append({
            "provider": prov,
            "quality_score": round(float(score), 4),
            "total_events": total_events,
            "warmup": warmup,
            "components": components,
        })
    scores.sort(key=lambda x: (-x["quality_score"], -x["total_events"]))
    return {
        "scores": scores,
        "weights": dict(_STAGE_WEIGHTS),
        "generated_at": time.time(),
    }


async def score_snapshot(*, ttl_s: Optional[float] = None) -> Dict[str, Any]:
    """Return the cached (or freshly computed) score snapshot."""
    from engines.learning import config as lcfg
    ttl = _CACHE_TTL_S if ttl_s is None else ttl_s
    with _LOCK:
        cached = _CACHE.get("value")
        cached_ts = _CACHE.get("ts", 0.0)
    if cached is not None and (time.time() - cached_ts) < ttl:
        return cached
    try:
        rows = await _aggregate()
        snap = _fold(rows, min_events=lcfg.retrieval_min_events())
    except Exception:  # noqa: BLE001
        logger.exception("scorer: aggregate failed — returning empty snapshot")
        snap = {"scores": [], "weights": dict(_STAGE_WEIGHTS),
                "generated_at": time.time()}
    with _LOCK:
        _CACHE["value"] = snap
        _CACHE["ts"] = time.time()
    return snap


def invalidate_cache() -> None:
    with _LOCK:
        _CACHE["value"] = None
        _CACHE["ts"] = 0.0
