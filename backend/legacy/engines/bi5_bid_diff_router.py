"""Phase 2 Stage 2 — BI5 ↔ BID shadow-diff router.

Admin-only, read-only, feature-gated by `BI5_BID_DIFF_ENABLED`.

Endpoint:
  POST /api/data/bi5-bid-diff
    body: { "symbol": str, "timeframe": "1h" (default),
            "days_back": int (default 30),
            "return_detail": bool (default false),
            "detail_format": "json" (default) | "csv" }
    returns: { "summary": {...}, "detail": [...] | "csv-body" | null }

Zero writes. No side effects on `market_data` or `market_data_htf_cache`.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Response

from .bi5_bid_diff import (
    diffs_to_csv,
    is_enabled,
    run_diff_for_symbol,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["bi5-bid-diff"])


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


@router.post("/bi5-bid-diff")
async def post_bi5_bid_diff(payload: Optional[Dict[str, Any]] = Body(default=None)) -> Any:
    """Run a BI5 ↔ BID shadow diff and return summary (+ optional detail).

    Body schema (all optional except `symbol`):
        {
          "symbol":         "EURUSD",
          "timeframe":      "1h",       # default
          "days_back":      30,         # default
          "return_detail":  false,      # default
          "detail_format":  "json"      # "json" | "csv"
        }
    """
    if not is_enabled():
        raise HTTPException(status_code=503, detail="BI5_BID_DIFF_ENABLED is off")
    body = payload or {}
    symbol = str(body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    timeframe     = str(body.get("timeframe") or "1h")
    days_back     = int(body.get("days_back") or 30)
    return_detail = bool(body.get("return_detail") or False)
    detail_fmt    = str(body.get("detail_format") or "json").lower()
    if detail_fmt not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="detail_format must be 'json' or 'csv'")

    summary, diffs = await run_diff_for_symbol(
        symbol, timeframe=timeframe, days_back=days_back,
    )
    if return_detail and detail_fmt == "csv":
        body_txt = diffs_to_csv(diffs)
        return Response(
            content=body_txt,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="bi5_bid_diff_{symbol}_{timeframe}.csv"',
                "X-Diff-Summary-Ok": "true" if summary.pass_ok else "false",
                "X-Diff-Reason": summary.reason,
            },
        )
    out: Dict[str, Any] = {"summary": summary.to_dict()}
    if return_detail:
        out["detail"] = [d.to_dict() for d in diffs]
    else:
        out["detail"] = None
    return out
