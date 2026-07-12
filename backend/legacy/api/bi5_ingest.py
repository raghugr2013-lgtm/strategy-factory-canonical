"""
P0A — BI5 ingest admin API.

Exposes a single orchestrator endpoint:

    POST /api/admin/bi5/run
        body:
            {
                "symbol":     "EURUSD",                       # required
                "start_utc":  "2024-01-02T00:00:00Z",         # required, ISO-8601
                "end_utc":    "2024-01-02T02:00:00Z",         # required, ISO-8601
                "use_cache":  true                            # optional, default true
            }

The endpoint runs the full Tier-1 (archive) + Tier-2 (Mongo 1m bars) pipeline
SYNCHRONOUSLY within the request, then returns the structured report. For
P0A this is deliberate — small windows only. Background-job mode comes in
P0B alongside certification.

Admin-only (``require_admin``). Side-effects (network + filesystem +
MongoDB writes) make this an unsafe surface to leave open.

TODO(P1 — Symbol Registry Promotion):
    Symbol validation currently leans on ``config.bi5_symbols``. Swap to
    a ``market_universe`` lookup once promoted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth_utils import require_admin
from config.bi5_symbols import is_bi5_supported, list_bi5_symbols
from data_engine.bi5_ingest_runner import MAX_HOURS_PER_RUN, run_bi5_ingest
from engines.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/bi5", tags=["admin-bi5"])


def _parse_utc(value: str, field_name: str) -> datetime:
    """Parse an ISO-8601 string into a tz-aware UTC ``datetime``."""
    try:
        # ``fromisoformat`` accepts trailing 'Z' from Python 3.11+. Be defensive.
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} is not a valid ISO-8601 timestamp: {exc}",
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class RunBI5Request(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=12)
    start_utc: str
    end_utc: str
    use_cache: bool = True

    @field_validator("symbol")
    @classmethod
    def _norm_symbol(cls, v: str) -> str:
        return v.upper().strip()


@router.get("/symbols")
async def list_supported_symbols(_: dict = Depends(require_admin)):
    """List the BI5-supported symbols currently registered.

    TODO(P1): driven by market_universe once promoted.
    """
    return {"symbols": list_bi5_symbols()}


@router.post("/run")
async def post_run_bi5(
    body: RunBI5Request,
    _: dict = Depends(require_admin),
):
    """Synchronously run download → archive → aggregate → store for one symbol+window.

    Returns the structured ``IngestReport`` dict.
    """
    if not is_bi5_supported(body.symbol):
        raise HTTPException(
            status_code=400,
            detail=f"Symbol {body.symbol!r} is not BI5-supported. "
                   f"Known: {list_bi5_symbols()}",
        )

    start_utc = _parse_utc(body.start_utc, "start_utc")
    end_utc = _parse_utc(body.end_utc, "end_utc")

    if end_utc <= start_utc:
        raise HTTPException(
            status_code=400,
            detail="end_utc must be strictly greater than start_utc",
        )

    window_hours = (end_utc - start_utc).total_seconds() / 3600.0
    if window_hours > MAX_HOURS_PER_RUN:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Window is {window_hours:.0f}h, exceeds per-run cap "
                f"({MAX_HOURS_PER_RUN}h). Break into smaller chunks."
            ),
        )

    logger.info(
        "bi5.ingest.api_run symbol=%s start=%s end=%s use_cache=%s",
        body.symbol, start_utc.isoformat(), end_utc.isoformat(), body.use_cache,
    )

    try:
        report = await run_bi5_ingest(
            body.symbol,
            start_utc=start_utc,
            end_utc=end_utc,
            use_cache=body.use_cache,
            db=get_db(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("bi5.ingest.api_run.failed symbol=%s", body.symbol)
        raise HTTPException(status_code=500, detail=f"BI5 ingest failed: {exc}") from exc

    return {"status": "ok", "report": report}
