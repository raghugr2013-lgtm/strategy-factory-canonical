"""Phase I collector — brain_decision outcome_events.

Reads `outcome_events` where `metrics.decision_type == "brain_decision"`
within the configured meta-learning window. Returns plain dicts sorted
newest-first. Read-only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def collect_brain_decisions(
    *, window_hours: int, limit: int = 2000,
    strategy_hash: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return brain_decision events emitted in the last `window_hours`.

    Each record contains `_id`, `strategy_hash`, `metrics` (with
    embedded scorer `components`), `ts`. Never raises; returns `[]`
    on failure.
    """
    try:
        from engines.db import get_db
        db = get_db()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=int(window_hours))
        q: Dict[str, Any] = {
            "stage": "approve",
            "metrics.decision_type": "brain_decision",
            "ts": {"$gte": cutoff},
        }
        if strategy_hash:
            q["strategy_hash"] = strategy_hash
        cur = db["outcome_events"].find(q).sort("ts", -1).limit(int(limit))
        out: List[Dict[str, Any]] = []
        for d in await cur.to_list(length=int(limit)):
            d["_id"] = str(d.get("_id", ""))
            out.append(d)
        return out
    except Exception:  # noqa: BLE001
        logger.exception("collect_brain_decisions failed (non-fatal)")
        return []
