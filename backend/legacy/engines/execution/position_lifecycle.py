"""Phase H — Position lifecycle.

Consumes filled orders (via `order_lifecycle.process_fill` results) and
maintains the `positions` collection. Each closing fill computes
realised PnL and emits a `position_closed` outcome event tagged with
`strategy_hash` + `brain_decision_id` so closed learning can attribute
realised outcomes back to the emitting brain decision (§12).

Positions are keyed by `(account_id, pair, strategy_hash?)`. Same-pair
opposing fills close the existing position first, then open a new one
with any residual.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import ledger
from .types import FillEvent, Position, PositionState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_position_id() -> str:
    return "pos_" + uuid.uuid4().hex[:12]


async def _emit_outcome(decision_type: str, *,
                         reason: str = "",
                         strategy_hash: Optional[str] = None,
                         metrics: Optional[Dict[str, Any]] = None,
                         evidence: Optional[Dict[str, Any]] = None) -> None:
    try:
        from engines.intelligence.explainability import emit_decision
        await emit_decision(
            decision_type, strategy_hash=strategy_hash,
            reason=reason, metrics=metrics or {}, evidence=evidence or {},
        )
    except Exception:  # noqa: BLE001
        return None


async def _find_open_position(
    account_id: str, pair: str, strategy_hash: Optional[str],
) -> Optional[Position]:
    """Return the currently open position for (account, pair,
    strategy_hash) or None."""
    positions = await ledger.read_positions(account_id=account_id, open_only=True)
    for p in positions:
        if p.pair == pair and (p.strategy_hash or "") == (strategy_hash or ""):
            return p
    return None


async def apply_fill_to_position(fill: FillEvent,
                                  strategy_hash: Optional[str] = None,
                                  brain_decision_id: Optional[str] = None,
                                  ) -> Optional[Position]:
    """Update or open a Position based on a FillEvent. Returns the
    resulting Position (open, partial-closed, or closed).

    Rules:
      * Same-side fill → adds to existing (or opens new) position at
        volume-weighted average price.
      * Opposite-side fill → reduces existing position, computing
        realised PnL on the closed quantity. Any residual opens a new
        position on the OPPOSITE side.
    """
    if fill.qty_filled <= 0:                # rejection/synthetic filler
        return None

    existing = await _find_open_position(
        fill.account_id, fill.pair, strategy_hash,
    )

    # No existing position → open a new one.
    if existing is None:
        pos = Position(
            position_id=_new_position_id(),
            account_id=fill.account_id, pair=fill.pair,
            side=fill.side, qty=float(fill.qty_filled),
            avg_entry=float(fill.price),
            opened_at=fill.timestamp or _now(),
            state=PositionState.OPEN,
            realised_pnl=0.0, unrealised_pnl=0.0,
            strategy_hash=strategy_hash,
            brain_decision_id=brain_decision_id,
            fill_ids=[fill.fill_id],
        )
        await ledger.upsert_position(pos)
        return pos

    # Same-side fill → add.
    if existing.side == fill.side:
        new_qty = existing.qty + fill.qty_filled
        new_avg = ((existing.avg_entry * existing.qty
                     + fill.price * fill.qty_filled) / new_qty
                    if new_qty > 0 else existing.avg_entry)
        existing.qty = float(new_qty)
        existing.avg_entry = float(new_avg)
        existing.fill_ids = list(existing.fill_ids) + [fill.fill_id]
        await ledger.upsert_position(existing)
        return existing

    # Opposite side → reduce/close.
    close_qty = min(existing.qty, float(fill.qty_filled))
    # Realised PnL per unit (BUY was existing side → sell exit).
    if existing.side == "BUY":
        pnl_per_unit = fill.price - existing.avg_entry
    else:
        pnl_per_unit = existing.avg_entry - fill.price
    realised_delta = pnl_per_unit * close_qty
    existing.realised_pnl = float(existing.realised_pnl + realised_delta)
    existing.qty = float(existing.qty - close_qty)
    existing.fill_ids = list(existing.fill_ids) + [fill.fill_id]

    if existing.qty <= 1e-9:
        existing.qty = 0.0
        existing.state = PositionState.CLOSED
        existing.closed_at = fill.timestamp or _now()
        await ledger.upsert_position(existing)
        await _emit_outcome(
            "position_closed",
            reason=f"pair={existing.pair} realised_pnl={existing.realised_pnl:.4f}",
            strategy_hash=existing.strategy_hash,
            metrics={"position_id": existing.position_id,
                      "pair": existing.pair, "side": existing.side,
                      "realised_pnl": existing.realised_pnl,
                      "qty": close_qty},
            evidence={"brain_decision_id": existing.brain_decision_id,
                       "fill_ids": existing.fill_ids},
        )
    else:
        existing.state = PositionState.PARTIAL_CLOSE
        await ledger.upsert_position(existing)
        await _emit_outcome(
            "position_partial_close",
            reason=f"remaining_qty={existing.qty}",
            strategy_hash=existing.strategy_hash,
            metrics={"position_id": existing.position_id,
                      "realised_pnl_delta": realised_delta,
                      "cumulative_realised_pnl": existing.realised_pnl,
                      "remaining_qty": existing.qty},
            evidence={"brain_decision_id": existing.brain_decision_id,
                       "fill_ids": existing.fill_ids},
        )

    # Residual on the incoming fill opens a new opposite-side position.
    residual = float(fill.qty_filled) - close_qty
    if residual > 1e-9:
        new_pos = Position(
            position_id=_new_position_id(),
            account_id=fill.account_id, pair=fill.pair,
            side=fill.side, qty=residual, avg_entry=float(fill.price),
            opened_at=fill.timestamp or _now(),
            state=PositionState.OPEN,
            strategy_hash=strategy_hash,
            brain_decision_id=brain_decision_id,
            fill_ids=[fill.fill_id],
        )
        await ledger.upsert_position(new_pos)
        return new_pos
    return existing
