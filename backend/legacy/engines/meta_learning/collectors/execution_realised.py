"""Phase I collector — execution_realised outcome_events + attribution rows.

Joins realised events to their originating brain_decision via
`metrics.brain_decision_id`. Provides the training-signal input for
weight_sensitivity / execution_quality_gate evaluators.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def collect_execution_realised(
    *, window_hours: int, limit: int = 2000,
) -> List[Dict[str, Any]]:
    """Return `execution_realised` outcome_events emitted in the window.

    Each record embeds `attribution_id`, `brain_decision_id`,
    `realised_pnl`, `predicted_score`, `realised_execution_score`,
    `delta_predicted_realised`, `slippage_pips`.
    """
    try:
        from engines.db import get_db
        db = get_db()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=int(window_hours))
        cur = db["outcome_events"].find({
            "stage": "approve",
            "metrics.decision_type": "execution_realised",
            "ts": {"$gte": cutoff},
        }).sort("ts", -1).limit(int(limit))
        out: List[Dict[str, Any]] = []
        for d in await cur.to_list(length=int(limit)):
            d["_id"] = str(d.get("_id", ""))
            out.append(d)
        return out
    except Exception:  # noqa: BLE001
        logger.exception("collect_execution_realised failed (non-fatal)")
        return []


async def join_decision_to_realised(
    decisions: List[Dict[str, Any]],
    realised: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Join brain_decision rows to their execution_realised twin by
    matching `brain_decision_id`. Decisions carry `_id` (the source
    outcome_event _id). Attribution.py builds `attribution_id` from
    `brain_decision_id[:12]`, and the realised event carries the
    brain_decision_id in `metrics.brain_decision_id`.

    Returns [(decision, realised)] pairs — only pairs where both are
    present.
    """
    by_did: Dict[str, Dict[str, Any]] = {}
    for r in realised:
        m = r.get("metrics") or {}
        did = m.get("brain_decision_id")
        if did:
            by_did[str(did)] = r
    pairs: List[Dict[str, Any]] = []
    for d in decisions:
        did = str(d.get("_id") or "")
        if did in by_did:
            pairs.append({"decision": d, "realised": by_did[did]})
    return pairs
