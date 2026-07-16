"""Phase H — Order lifecycle state machine.

Consumes fills from a broker adapter, updates `order_requests` state
via the ledger, and emits every state transition + fill into the
immutable execution_journal (Execution Replay §24.3).

Also emits `outcome_events` rows via
`engines.intelligence.explainability.emit_decision`:

  * `order_state_change` — every hop
  * `fill_recorded`      — every fill_event that lands

State machine:

  PENDING → SENT → (ACCEPTED | REJECTED)
                     ↓
                  WORKING → (PARTIAL_FILL* → FILLED | CANCELLED | EXPIRED)

Terminal states are FILLED / REJECTED / CANCELLED / EXPIRED.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import ledger
from .broker.base import BrokerAdapter, BrokerError
from .types import (
    FillEvent, JournalEventType, OrderRequest, OrderState,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _emit_outcome(decision_type: str, *,
                         reason: str = "",
                         metrics: Optional[Dict[str, Any]] = None,
                         evidence: Optional[Dict[str, Any]] = None) -> Optional[str]:
    try:
        from engines.intelligence.explainability import emit_decision
        return await emit_decision(
            decision_type, reason=reason,
            metrics=metrics or {}, evidence=evidence or {},
        )
    except Exception:  # noqa: BLE001
        return None


async def submit_order(
    order: OrderRequest, broker: BrokerAdapter,
) -> Tuple[Optional[str], str]:
    """Full end-to-end submit: journal PENDING→SENT, call broker, on
    success journal ACCEPTED/WORKING, on failure REJECTED.

    Returns (broker_order_id, terminal_state).
    """
    order.requested_at = order.requested_at or _now()
    order.updated_at   = _now()
    order.state        = OrderState.PENDING

    # Persist the initial PENDING row.
    await ledger.append_order_request(order)
    await _emit_state_change(order.account_id, order.request_id,
                              OrderState.PENDING, OrderState.SENT)

    # Journal the transition BEFORE the broker call so replay is
    # deterministic even if the broker throws.
    await ledger.append_journal(
        order.account_id, JournalEventType.ORDER_STATE_CHANGE,
        payload={"from": OrderState.PENDING, "to": OrderState.SENT,
                  "pair": order.pair, "side": order.side,
                  "qty": order.qty, "type": order.type,
                  "time_in_force": order.time_in_force},
        correlation={"request_id": order.request_id,
                     "strategy_hash": order.strategy_hash or "",
                     "brain_decision_id": order.brain_decision_id or ""},
    )
    await ledger.update_order_state(order.request_id, state=OrderState.SENT)

    try:
        broker_order_id = await broker.submit(order)
    except BrokerError as e:
        reason = str(e)[:240]
        await ledger.update_order_state(order.request_id,
                                          state=OrderState.REJECTED,
                                          reject_reason=reason)
        await ledger.append_journal(
            order.account_id, JournalEventType.ORDER_STATE_CHANGE,
            payload={"from": OrderState.SENT, "to": OrderState.REJECTED,
                      "broker_reason": reason},
            correlation={"request_id": order.request_id},
        )
        await _emit_state_change(order.account_id, order.request_id,
                                   OrderState.SENT, OrderState.REJECTED,
                                   broker_reason=reason)
        return (None, OrderState.REJECTED)

    # Broker accepted the order.
    await ledger.update_order_state(order.request_id,
                                      state=OrderState.WORKING,
                                      broker_order_id=broker_order_id)
    await ledger.append_journal(
        order.account_id, JournalEventType.ORDER_STATE_CHANGE,
        payload={"from": OrderState.SENT, "to": OrderState.WORKING,
                  "broker_order_id": broker_order_id},
        correlation={"request_id": order.request_id,
                      "broker_order_id": broker_order_id},
    )
    await _emit_state_change(order.account_id, order.request_id,
                               OrderState.SENT, OrderState.WORKING,
                               broker_order_id=broker_order_id)
    return (broker_order_id, OrderState.WORKING)


async def process_fill(fill: FillEvent) -> Dict[str, Any]:
    """Persist a fill, update the parent order, emit journal + outcome.

    Returns a dict summary suitable for API responses.
    """
    # 1. Persist fill (idempotent by fill_id)
    await ledger.append_fill_event(fill)

    # 2. Journal
    await ledger.append_journal(
        fill.account_id, JournalEventType.FILL,
        payload={"fill_id": fill.fill_id, "pair": fill.pair,
                  "side": fill.side, "qty_filled": fill.qty_filled,
                  "price": fill.price, "slippage_pips": fill.slippage_pips,
                  "latency_ms": fill.latency_ms,
                  "is_partial": fill.is_partial},
        correlation={"request_id": fill.request_id,
                      "fill_id": fill.fill_id,
                      "broker_order_id": fill.broker_order_id or ""},
    )

    # 3. Aggregate onto the parent order.
    parent = await ledger.read_order(fill.request_id)
    if parent is None:
        # Orphan fill — persist journal but skip aggregation.
        await _emit_outcome(
            "fill_recorded",
            reason=f"orphan fill_id={fill.fill_id}",
            metrics={"fill_id": fill.fill_id,
                      "qty_filled": fill.qty_filled,
                      "price": fill.price},
            evidence={"orphan": True},
        )
        return {"orphan": True, "fill_id": fill.fill_id}

    fills = await ledger.read_fills(request_id=fill.request_id, limit=1000)
    total_qty  = sum(f.qty_filled for f in fills)
    total_notional = sum(f.qty_filled * f.price for f in fills if f.qty_filled)
    avg_price  = (total_notional / total_qty) if total_qty > 0 else None

    # REJECT path: qty_filled=0 and is_partial=False → mark REJECTED.
    if fill.qty_filled == 0 and not fill.is_partial and parent.state != OrderState.REJECTED:
        await ledger.update_order_state(fill.request_id,
                                          state=OrderState.REJECTED,
                                          reject_reason="broker_reject_zero_fill")
        await _emit_state_change(fill.account_id, fill.request_id,
                                   parent.state, OrderState.REJECTED,
                                   broker_reason="zero_fill_reject")
        return {"state": OrderState.REJECTED, "qty_filled": 0.0}

    if fill.is_partial:
        new_state = OrderState.PARTIAL
    else:
        new_state = OrderState.FILLED
    await ledger.update_order_state(
        fill.request_id, state=new_state,
        qty_filled=total_qty,
        avg_fill_price=avg_price,
    )
    await _emit_state_change(fill.account_id, fill.request_id,
                               parent.state, new_state,
                               broker_order_id=parent.broker_order_id)
    await _emit_outcome(
        "fill_recorded",
        reason=f"pair={fill.pair} qty={fill.qty_filled} price={fill.price}",
        metrics={"request_id": fill.request_id,
                  "fill_id": fill.fill_id,
                  "qty_filled": fill.qty_filled,
                  "avg_fill_price": avg_price,
                  "slippage_pips": fill.slippage_pips,
                  "latency_ms": fill.latency_ms,
                  "is_partial": fill.is_partial,
                  "resulting_order_state": new_state},
        evidence={"strategy_hash": parent.strategy_hash,
                   "brain_decision_id": parent.brain_decision_id},
    )
    return {"state": new_state, "qty_filled": total_qty,
            "avg_price": avg_price}


async def cancel_order(request_id: str, broker: BrokerAdapter,
                        reason: str = "operator_cancel") -> bool:
    """Cancel a working order. Emits journal + outcome event."""
    parent = await ledger.read_order(request_id)
    if parent is None:
        return False
    if OrderState.is_terminal(parent.state):
        return False
    ok = await broker.cancel(request_id)
    if not ok:
        return False
    await ledger.update_order_state(request_id,
                                      state=OrderState.CANCELLED,
                                      cancel_reason=reason)
    await ledger.append_journal(
        parent.account_id, JournalEventType.ORDER_STATE_CHANGE,
        payload={"from": parent.state, "to": OrderState.CANCELLED,
                  "cancel_reason": reason},
        correlation={"request_id": request_id,
                      "broker_order_id": parent.broker_order_id or ""},
    )
    await _emit_state_change(parent.account_id, request_id,
                               parent.state, OrderState.CANCELLED,
                               cancel_reason=reason)
    return True


async def _emit_state_change(account_id: str, request_id: str,
                              from_state: str, to_state: str,
                              **extra: Any) -> None:
    """One outcome_events row per state transition (§24.2 Q1-Q4)."""
    metrics = {"request_id": request_id, "account_id": account_id,
               "from": from_state, "to": to_state}
    metrics.update({k: v for k, v in extra.items() if v is not None})
    await _emit_outcome(
        "order_state_change",
        reason=f"{from_state}→{to_state}",
        metrics=metrics,
    )
