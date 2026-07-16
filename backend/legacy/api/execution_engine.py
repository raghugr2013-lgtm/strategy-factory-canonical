"""v1.2.0-alpha2 Phase H9 — /api/execution/* endpoints.

16 endpoints covering broker health, orders, fills, positions,
execution quality, attribution, risk, config, and replay (H11).

Admin-gated write operations: submit, cancel, kill-switch,
quality refresh, replay.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from auth_utils import require_admin
from engines.execution import (
    OrderRequest, OrderState, active_backend_name,
    broker_kill_switch, default_account_id, exec_config_snapshot,
    exec_enabled, get_paper_adapter, ledger,
)
from engines.execution.attribution import attribute_closed_positions
from engines.execution.broker_health import read_latest_health, sample_broker_health
from engines.execution.quality import measure_execution_quality
from engines.execution.replay import replay_range
from engines.execution.risk_monitor import evaluate_guards
from engines.execution import order_lifecycle

router = APIRouter(prefix="/execution", tags=["execution-engine"])


def _dormant() -> Optional[Dict[str, Any]]:
    if not exec_enabled():
        raise HTTPException(status_code=503,
            detail="EXEC_ENABLED=false (execution engine dormant)")
    return None


# ── Broker health ─────────────────────────────────────────
@router.get("/broker/health")
async def broker_health(account_id: str = Query(None)) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    h = await read_latest_health(account_id)
    return {"account_id": account_id,
            "health": h.to_dict() if h else None}


@router.get("/broker/history")
async def broker_history(
    account_id: str = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    rows = await ledger.read_broker_health_history(account_id, limit=limit)
    return {"account_id": account_id, "count": len(rows),
            "history": [r.to_dict() for r in rows]}


@router.post("/broker/kill-switch", dependencies=[Depends(require_admin)])
async def broker_kill_switch_engage() -> Dict[str, Any]:
    import os
    os.environ["BROKER_KILL_SWITCH"] = "true"
    return {"kill_switch": True,
            "note": "cancel working orders via DELETE /orders/{id} if desired"}


@router.post("/broker/kill-switch/clear", dependencies=[Depends(require_admin)])
async def broker_kill_switch_clear() -> Dict[str, Any]:
    import os
    os.environ["BROKER_KILL_SWITCH"] = "false"
    return {"kill_switch": False}


# ── Orders ────────────────────────────────────────────────
@router.get("/orders")
async def list_orders(
    strategy_hash: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    rows = await ledger.read_orders(account_id=account_id,
        strategy_hash=strategy_hash, state=state, limit=limit)
    return {"count": len(rows),
            "orders": [o.to_dict() for o in rows]}


@router.get("/orders/{request_id}")
async def get_order(request_id: str) -> Dict[str, Any]:
    _dormant()
    o = await ledger.read_order(request_id)
    if o is None:
        raise HTTPException(404, "order not found")
    fills = await ledger.read_fills(request_id=request_id, limit=100)
    return {"order": o.to_dict(),
            "fills": [f.to_dict() for f in fills]}


@router.post("/orders", dependencies=[Depends(require_admin)])
async def submit(order: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Submit an OrderRequest via the active broker adapter.
    Q6: paper=fully autonomous; live requires operator approval —
    this endpoint requires admin auth for BOTH."""
    _dormant()
    req = OrderRequest(
        request_id=order.get("request_id") or "req_" + uuid.uuid4().hex[:10],
        account_id=order.get("account_id") or default_account_id(),
        pair=order["pair"], side=order["side"],
        type=order.get("type", "MARKET"),
        qty=float(order["qty"]),
        price=order.get("price"),
        sl_pips=order.get("sl_pips"),
        tp_pips=order.get("tp_pips"),
        time_in_force=order.get("time_in_force", "IOC"),
        strategy_hash=order.get("strategy_hash"),
        brain_decision_id=order.get("brain_decision_id"),
    )
    br = get_paper_adapter()
    if not br._connected:
        await br.connect()
    boid, terminal = await order_lifecycle.submit_order(req, br)
    return {"request_id": req.request_id,
            "broker_order_id": boid, "state": terminal}


@router.delete("/orders/{request_id}", dependencies=[Depends(require_admin)])
async def cancel(request_id: str,
                   reason: str = Query("operator_cancel")) -> Dict[str, Any]:
    _dormant()
    br = get_paper_adapter()
    ok = await order_lifecycle.cancel_order(request_id, br, reason=reason)
    return {"request_id": request_id, "cancelled": ok}


# ── Fills ─────────────────────────────────────────────────
@router.get("/fills")
async def list_fills(
    account_id: Optional[str] = Query(None),
    pair: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    rows = await ledger.read_fills(
        account_id=account_id, pair=pair, request_id=request_id, limit=limit)
    return {"count": len(rows),
            "fills": [f.to_dict() for f in rows]}


# ── Positions ─────────────────────────────────────────────
@router.get("/positions")
async def list_positions(
    account_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    rows = await ledger.read_positions(account_id=account_id, open_only=True)
    return {"count": len(rows),
            "positions": [p.to_dict() for p in rows]}


@router.get("/positions/history")
async def positions_history(
    account_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    rows = await ledger.read_closed_positions(account_id=account_id, limit=limit)
    return {"count": len(rows),
            "positions": [p.to_dict() for p in rows]}


# ── Execution quality ─────────────────────────────────────
@router.get("/quality")
async def quality(
    account_id: Optional[str] = Query(None),
    pair: str = Query(...),
    session: str = Query("all"),
    window: str = Query("24h"),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    q = await ledger.read_execution_quality(
        account_id=account_id, pair=pair, session=session, window=window)
    return {"account_id": account_id, "pair": pair,
            "quality": q.to_dict() if q else None}


@router.post("/quality/refresh", dependencies=[Depends(require_admin)])
async def quality_refresh(
    account_id: Optional[str] = Query(None),
    pair: str = Query(...),
    session: str = Query("all"),
    window: str = Query("24h"),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    q = await measure_execution_quality(
        account_id, pair, session=session, window=window, persist=True)
    return {"refreshed": True, "quality": q.to_dict()}


# ── Attribution ───────────────────────────────────────────
@router.get("/attribution")
async def attribution_list(
    strategy_hash: str = Query(...),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    _dormant()
    rows = await ledger.read_attributions_for_strategy(strategy_hash, limit=limit)
    return {"strategy_hash": strategy_hash, "count": len(rows),
            "attributions": [a.to_dict() for a in rows]}


@router.get("/attribution/{decision_id}")
async def attribution_by_decision(decision_id: str) -> Dict[str, Any]:
    _dormant()
    a = await ledger.read_attribution("attr_" + decision_id[:12].replace("-", ""))
    if a is None:
        raise HTTPException(404, "attribution not found")
    return {"attribution": a.to_dict()}


# ── Risk ──────────────────────────────────────────────────
@router.get("/risk/status")
async def risk_status(
    account_id: Optional[str] = Query(None),
    account_equity: float = Query(100_000.0),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    recs = await evaluate_guards(account_id, account_equity=account_equity)
    return {"account_id": account_id,
            "n_breaches": len(recs),
            "recommendations": [r.to_dict() for r in recs]}


# ── Config & introspection ────────────────────────────────
@router.get("/config")
async def config_snapshot() -> Dict[str, Any]:
    return {"config": exec_config_snapshot(),
            "kill_switch": broker_kill_switch(),
            "ledger_backend": active_backend_name()}


# ── H11 · Replay ──────────────────────────────────────────
@router.post("/replay", dependencies=[Depends(require_admin)])
async def replay(
    account_id: Optional[str] = Query(None),
    start_seq: Optional[int] = Query(None),
    end_seq: Optional[int] = Query(None),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    report = await replay_range(
        account_id, start_seq=start_seq, end_seq=end_seq)
    return {"report": report.to_dict()}


@router.get("/journal")
async def journal(
    account_id: Optional[str] = Query(None),
    start_seq: Optional[int] = Query(None),
    end_seq: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
) -> Dict[str, Any]:
    _dormant()
    account_id = account_id or default_account_id()
    rows = await ledger.read_journal_range(account_id,
        start_seq=start_seq, end_seq=end_seq,
        event_type=event_type, limit=limit)
    return {"account_id": account_id, "count": len(rows),
            "events": [e.to_dict() for e in rows]}
