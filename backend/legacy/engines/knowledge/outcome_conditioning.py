"""v1.2.0-alpha2 Phase B — Outcome-conditioned retrieval scoring.

Extends the metadata retriever with a lightweight boost derived from
the `outcome_events` ledger. For every candidate strategy_hash in the
knowledge index we look up:

    * validate.pass_rate        (backtest survives)
    * repair.success_rate       (repair converted a fail into a pass)
    * optimize.uplift_avg       (mean numeric uplift in optimize stage)
    * operator.avg_rating       (approve/reject ratings)
    * cycles_completed          (how many full cycles this hash lived through)

The boost is:
    outcome_boost = W * (0.5 * validate + 0.2 * repair
                         + 0.2 * uplift_norm + 0.1 * operator)

where `W = LEARNING_RETRIEVAL_OUTCOME_WEIGHT` (env-tunable; default 2.0).

Providers with fewer than `LEARNING_RETRIEVAL_MIN_EVENTS` events for a
given hash receive `boost=0.0` so the metadata ranker stays in charge
until we have enough signal.

Cached in-process for 60 s to keep retrieval hot-path cheap.
"""
from __future__ import annotations

import logging
import time
from threading import RLock
from typing import Any, Dict, List, Optional, Set

from engines.db import get_db

logger = logging.getLogger(__name__)

_COLL = "outcome_events"
_CACHE_TTL_S = 60.0
_LOCK = RLock()
_CACHE: Dict[str, Any] = {}   # {hash: {"ts": t, "value": dict}}


async def _aggregate_hashes(hashes: List[str]) -> Dict[str, Dict[str, Any]]:
    """Bulk aggregate outcome stats for a list of strategy_hashes."""
    if not hashes:
        return {}
    db = get_db()
    pipeline = [
        {"$match": {"strategy_hash": {"$in": hashes}}},
        {"$group": {
            "_id": {"hash": "$strategy_hash", "stage": "$stage", "status": "$status"},
            "n": {"$sum": 1},
            "uplift_avg": {"$avg": "$metrics.optimization_uplift"},
            "avg_rating": {"$avg": "$operator.rating"},
        }},
    ]
    per_hash: Dict[str, Dict[str, Any]] = {}
    async for row in db[_COLL].aggregate(pipeline):
        rid = row["_id"] or {}
        h = rid.get("hash")
        stage = rid.get("stage")
        status = rid.get("status")
        if not h:
            continue
        rec = per_hash.setdefault(h, {"total_events": 0, "per_stage": {}})
        rec["total_events"] += int(row.get("n", 0))
        stage_rec = rec["per_stage"].setdefault(stage, {"pass": 0, "fail": 0, "partial": 0, "skipped": 0})
        stage_rec[status] = stage_rec.get(status, 0) + int(row.get("n", 0))
        if row.get("uplift_avg") is not None:
            rec.setdefault("uplift_avg", []).append(float(row["uplift_avg"]))
        if row.get("avg_rating") is not None:
            rec.setdefault("rating_avg", []).append(float(row["avg_rating"]))
    return per_hash


def _score_from_stats(stats: Dict[str, Any], weight: float, min_events: int) -> Dict[str, Any]:
    """Fold per-hash stats into a numerical outcome-boost."""
    total = int(stats.get("total_events", 0))
    if total < max(1, min_events):
        return {"boost": 0.0, "reason": "warmup", "total_events": total}

    per_stage = stats.get("per_stage", {})

    def _rate(stage: str) -> float:
        s = per_stage.get(stage, {})
        n_pass = int(s.get("pass", 0))
        n_partial = int(s.get("partial", 0))
        n_fail = int(s.get("fail", 0))
        n_total = n_pass + n_partial + n_fail
        return (n_pass + 0.5 * n_partial) / n_total if n_total else 0.0

    validate_rate = _rate("validate") if "validate" in per_stage else _rate("backtest")
    repair_rate = _rate("repair")
    approve_rate = _rate("approve")
    # Uplift is a signed number — normalise to [0, 1] via a soft cap.
    uplift_vals = stats.get("uplift_avg") or []
    if uplift_vals:
        raw_uplift = sum(uplift_vals) / len(uplift_vals)
        uplift_norm = max(0.0, min(1.0, 0.5 + raw_uplift / 2.0))
    else:
        uplift_norm = 0.5

    composite = (0.5 * validate_rate
                 + 0.2 * repair_rate
                 + 0.2 * uplift_norm
                 + 0.1 * approve_rate)
    boost = weight * (composite - 0.5)  # centre at 0 so wins add, losses subtract
    return {
        "boost": round(boost, 4),
        "composite": round(composite, 4),
        "validate_rate": round(validate_rate, 4),
        "repair_rate": round(repair_rate, 4),
        "approve_rate": round(approve_rate, 4),
        "uplift_norm": round(uplift_norm, 4),
        "total_events": total,
    }


async def boosts_for(hashes: List[str],
                     *,
                     weight: Optional[float] = None,
                     min_events: Optional[int] = None,
                     ttl_s: Optional[float] = None) -> Dict[str, Dict[str, Any]]:
    """Return `{strategy_hash: {boost, composite, ...}}` for each hash.

    Missing hashes get an empty entry `{boost: 0.0, reason: "no_events"}`.
    Never raises — DB errors return an empty dict so retrieval degrades
    gracefully.
    """
    from engines.learning import config as lcfg
    w = lcfg.retrieval_outcome_weight() if weight is None else weight
    if w <= 0 or not hashes:
        return {}
    me = lcfg.retrieval_min_events() if min_events is None else min_events
    ttl = _CACHE_TTL_S if ttl_s is None else ttl_s

    now = time.time()
    fresh: Dict[str, Dict[str, Any]] = {}
    to_fetch: List[str] = []
    with _LOCK:
        for h in hashes:
            entry = _CACHE.get(h)
            if entry and (now - entry.get("ts", 0.0)) < ttl:
                fresh[h] = entry["value"]
            else:
                to_fetch.append(h)

    if to_fetch:
        try:
            raw = await _aggregate_hashes(to_fetch)
        except Exception:  # noqa: BLE001
            logger.exception("boosts_for: aggregate failed — degrading")
            raw = {}
        with _LOCK:
            for h in to_fetch:
                stats = raw.get(h, {"total_events": 0, "per_stage": {}})
                val = _score_from_stats(stats, w, me)
                _CACHE[h] = {"ts": now, "value": val}
                fresh[h] = val
    return fresh


def apply_boosts(scored: List[tuple], boosts: Dict[str, Dict[str, Any]]) -> List[tuple]:
    """Merge outcome boosts into a `[(score, row), ...]` list."""
    if not boosts:
        return scored
    out = []
    for score, row in scored:
        h = str(row.get("strategy_hash") or "")
        b = boosts.get(h)
        if b:
            row = dict(row)
            row["_outcome_boost"] = b.get("boost", 0.0)
            row["_outcome"] = b
            new_score = float(score) + float(b.get("boost", 0.0))
        else:
            new_score = float(score)
        out.append((new_score, row))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def invalidate_cache(strategy_hash: Optional[str] = None) -> None:
    with _LOCK:
        if strategy_hash:
            _CACHE.pop(strategy_hash, None)
        else:
            _CACHE.clear()
