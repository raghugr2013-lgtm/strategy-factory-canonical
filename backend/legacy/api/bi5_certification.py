"""P0B Phase 3 — BI5 strategy-certification admin API.

Endpoints
─────────
POST /api/admin/bi5/certify-strategy
GET  /api/admin/bi5/certifications
GET  /api/admin/bi5/certifications/stats
GET  /api/admin/bi5/certifications/{strategy_id}
GET  /api/admin/bi5/certifications/{strategy_id}/latest
GET  /api/admin/bi5/certified/{strategy_id}
GET  /api/admin/bi5/data-certifications
GET  /api/admin/bi5/data-certifications/latest

Discipline
──────────
* Admin-authenticated via ``auth_utils.require_admin``.
* The seam DOES NOT import Phase-1 evaluator modules directly. All
  scoring is delegated to the orchestrator, which is the only piece
  allowed to compose Phase-1 outputs.
* ``stability_score`` enters this surface as a float (passed by the
  caller / validation-PP read path). The seam never imports
  validation / pass_probability.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from auth_utils import require_admin
from engines.bi5_certification import (
    StrategyCertRequest,
    WindowRef,
    certify_strategy,
)
from engines.db import get_db
from engines.persistence_adapters.bi5_certification_store import (
    DEFAULT_FRESHNESS_DAYS,
    aggregate_stats,
    is_bi5_certified,
    list_certifications,
    list_certifications_for_strategy,
)
from engines.persistence_adapters.bi5_data_certification_store import (
    find_data_certs_by_verdict,
    get_latest_data_certification,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/bi5", tags=["admin-bi5-cert"])


# ── helpers ──────────────────────────────────────────────────────────

def _parse_utc(value: str, *, field_name: str) -> datetime:
    try:
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


def _serialise(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Stringify ObjectId + datetimes for JSON output."""
    if doc is None:
        return None
    out: Dict[str, Any] = {}
    for k, v in doc.items():
        if k == "_id":
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = (
                v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
            ).isoformat()
        elif isinstance(v, dict):
            out[k] = {
                k2: (
                    (v2.replace(tzinfo=timezone.utc) if v2.tzinfo is None else v2).isoformat()
                    if isinstance(v2, datetime) else
                    (str(v2) if k2 == "_id" else v2)
                )
                for k2, v2 in v.items()
            }
        else:
            out[k] = v
    return out


# ── POST /admin/bi5/certify-strategy ─────────────────────────────────

class _WindowPayload(BaseModel):
    window_start_utc: str
    window_end_utc:   str


class _FillPayload(BaseModel):
    side:           int
    bid:            float
    ask:            float
    mid_before:     float
    mid_after:      float
    order_size:     float = 0.0
    adv_per_minute: float = 1.0
    # accept the existing spread_analyzer dict shape too
    fill_spread:    Optional[float] = None
    mid:            Optional[float] = None


class _SignalPayload(BaseModel):
    t_signal:    str
    side:        int
    order_size:  float = 0.0


class _CertifyStrategyRequest(BaseModel):
    strategy_id:      str = Field(..., min_length=1, max_length=128)
    pair:             str = Field(..., min_length=2, max_length=32)
    timeframe:        str = Field(..., min_length=1, max_length=16)
    style:            str = Field(..., min_length=1, max_length=64)
    data_cert_window: Optional[_WindowPayload] = None
    venue_profile:    Literal["retail", "ECN", "prop_firm"] = "ECN"
    stability_score:  float = Field(..., ge=0.0, le=1.0)
    assumed_cost_bps:     float = Field(1.0, ge=0.0, le=1000.0)
    assumed_slippage_bps: float = Field(1.0, ge=0.0, le=1000.0)
    tolerance_bps:    Optional[float] = Field(None, ge=0.0, le=1000.0)
    adv_per_minute:   Optional[float] = Field(None, ge=0.0)
    # NB: ticks/signals/fills come from upstream readers in production.
    # For Phase-3 admin testing, the seam accepts them inline.
    fills:            List[_FillPayload] = Field(default_factory=list)
    signals:          List[_SignalPayload] = Field(default_factory=list)
    ticks:            List[Dict[str, Any]] = Field(default_factory=list)
    mutation_family:    Optional[str] = Field(None, max_length=128)
    parent_strategy_id: Optional[str] = Field(None, max_length=128)

    @field_validator("pair")
    @classmethod
    def _norm_pair(cls, v: str) -> str:
        return v.upper().strip()


class _TickShim:
    """Wrap a tick dict (with `ts_utc` / `bid` / `ask`) into the duck
    type the Phase-1 execution_simulator expects (`.ts_utc`, `.bid`,
    `.ask`)."""

    __slots__ = ("ts_utc", "bid", "ask")

    def __init__(self, d: Dict[str, Any]) -> None:
        ts = d.get("ts_utc") or d.get("ts") or d.get("timestamp")
        if isinstance(ts, str):
            s = ts.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            ts = datetime.fromisoformat(s)
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        self.ts_utc = ts
        self.bid = float(d.get("bid"))
        self.ask = float(d.get("ask"))


@router.post("/certify-strategy")
async def certify_strategy_endpoint(
    payload: _CertifyStrategyRequest,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    window = None
    if payload.data_cert_window is not None:
        window = WindowRef(
            window_start_utc=_parse_utc(
                payload.data_cert_window.window_start_utc,
                field_name="data_cert_window.window_start_utc",
            ),
            window_end_utc=_parse_utc(
                payload.data_cert_window.window_end_utc,
                field_name="data_cert_window.window_end_utc",
            ),
        )

    # ── Normalise signals/ticks to the shapes Phase-1 expects ──
    signals_norm: List[Dict[str, Any]] = []
    for s in payload.signals:
        signals_norm.append({
            "t_signal":   _parse_utc(s.t_signal, field_name="signals[].t_signal"),
            "side":       int(s.side),
            "order_size": float(s.order_size),
        })
    ticks_norm = [_TickShim(t) for t in payload.ticks]
    fills_norm = [f.model_dump() for f in payload.fills]

    req = StrategyCertRequest(
        strategy_id=payload.strategy_id,
        pair=payload.pair,
        timeframe=payload.timeframe,
        style=payload.style,
        data_cert_window=window,
        fills=fills_norm,
        signals=signals_norm,
        ticks=ticks_norm,
        venue_profile=payload.venue_profile,
        stability_score=float(payload.stability_score),
        assumed_cost_bps=float(payload.assumed_cost_bps),
        assumed_slippage_bps=float(payload.assumed_slippage_bps),
        tolerance_bps=payload.tolerance_bps,
        adv_per_minute=payload.adv_per_minute,
        mutation_family=payload.mutation_family,
        parent_strategy_id=payload.parent_strategy_id,
    )

    report = await certify_strategy(db, req)
    return {
        "verdict":           report.record.certification_verdict,
        "early_fail_reason": report.early_fail_reason,
        "persist_result":    report.persist_result,
        "record":            _serialise(report.record.to_doc()),
    }


# ── GET /admin/bi5/certifications ────────────────────────────────────

@router.get("/certifications")
async def list_certifications_endpoint(
    pair: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    style: Optional[str] = Query(None),
    mutation_family: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None, pattern="^(PASS|WARN|FAIL)$"),
    since: Optional[str] = Query(None, description="ISO-8601 UTC"),
    limit: int = Query(50, ge=1, le=500),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    since_dt = _parse_utc(since, field_name="since") if since else None
    rows = await list_certifications(
        db,
        pair=pair, timeframe=timeframe, style=style,
        mutation_family=mutation_family, verdict=verdict,
        since_dt=since_dt, limit=limit,
    )
    return {"count": len(rows), "items": [_serialise(r) for r in rows]}


# ── GET /admin/bi5/certifications/stats ──────────────────────────────

@router.get("/certifications/stats")
async def cert_stats_endpoint(
    group_by: Literal["pair", "style", "timeframe", "mutation_family",
                      "verdict", "day"] = Query(...),
    since:    Optional[str] = Query(None),
    top_n:    int = Query(100, ge=1, le=1000),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    since_dt = _parse_utc(since, field_name="since") if since else None
    rows = await aggregate_stats(
        db, group_by=group_by, since_dt=since_dt, top_n=int(top_n),
    )
    return {"group_by": group_by, "top_n": top_n, "rows": rows}


# ── GET /admin/bi5/certifications/{strategy_id}{/latest} ─────────────

@router.get("/certifications/{strategy_id}/latest")
async def latest_certification_for_strategy_endpoint(
    strategy_id: str,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    rows = await list_certifications_for_strategy(
        db, strategy_id=strategy_id, limit=1,
    )
    return {
        "strategy_id": strategy_id,
        "item": _serialise(rows[0]) if rows else None,
    }


@router.get("/certifications/{strategy_id}")
async def list_certifications_for_strategy_endpoint(
    strategy_id: str,
    limit: int = Query(50, ge=1, le=500),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    rows = await list_certifications_for_strategy(
        db, strategy_id=strategy_id, limit=limit,
    )
    return {
        "strategy_id": strategy_id,
        "count": len(rows),
        "items": [_serialise(r) for r in rows],
    }


# ── GET /admin/bi5/certified/{strategy_id} (derived flag) ────────────

@router.get("/certified/{strategy_id}")
async def certified_flag_endpoint(
    strategy_id: str,
    freshness_days: Optional[int] = Query(
        None, ge=1, le=3650,
        description=f"Defaults to BI5_CERT_FRESHNESS_DAYS={DEFAULT_FRESHNESS_DAYS}",
    ),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    return await is_bi5_certified(
        db, strategy_id=strategy_id, freshness_days=freshness_days,
    )


# ── GET /admin/bi5/data-certifications ───────────────────────────────

@router.get("/data-certifications")
async def list_data_certs_endpoint(
    verdict: str = Query("FAIL", pattern="^(PASS|WARN|FAIL)$"),
    since: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    since_dt = _parse_utc(since, field_name="since") if since else None
    rows = await find_data_certs_by_verdict(
        db, verdict=verdict, limit=limit, since_dt=since_dt,
    )
    return {"verdict": verdict, "count": len(rows),
            "items": [_serialise(r) for r in rows]}


@router.get("/data-certifications/latest")
async def latest_data_cert_endpoint(
    symbol: str = Query(...),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    doc = await get_latest_data_certification(db, symbol=symbol.upper().strip())
    return {"symbol": symbol.upper().strip(), "item": _serialise(doc)}
