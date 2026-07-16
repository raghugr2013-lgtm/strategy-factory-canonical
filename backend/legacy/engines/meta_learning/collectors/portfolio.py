"""Phase I collector — portfolio_rebuild + activation + promotion + retirement."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def collect_portfolio_events(
    *, window_hours: int, limit: int = 2000,
) -> List[Dict[str, Any]]:
    try:
        from engines.db import get_db
        db = get_db()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=int(window_hours))
        cur = db["outcome_events"].find({
            "stage": "approve",
            "metrics.decision_type": {"$in": [
                "portfolio_rebuild", "portfolio_activate", "portfolio_promote",
                "portfolio_retire", "activation",
            ]},
            "ts": {"$gte": cutoff},
        }).sort("ts", -1).limit(int(limit))
        out: List[Dict[str, Any]] = []
        for d in await cur.to_list(length=int(limit)):
            d["_id"] = str(d.get("_id", ""))
            out.append(d)
        return out
    except Exception:  # noqa: BLE001
        logger.exception("collect_portfolio_events failed (non-fatal)")
        return []
