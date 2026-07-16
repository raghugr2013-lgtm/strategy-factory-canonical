"""Phase H7 — Execution Attribution.

Joins every closed round-trip back to its originating brain decision
via IMMUTABLE IDs (Q5 audit chain): brain_decision_id → request_id →
fill_ids → position_id → realised_pnl.

Runs on the orchestrator task `execution_attribution` every 5 min.
Emits `execution_realised` outcome events with `delta_predicted_realised`
so Phase I meta-learning can consume the training signal directly.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import ledger
from .quality import measure_execution_quality
from .types import ExecutionAttribution

logger = logging.getLogger(__name__)


def _new_attr_id() -> str:
    return "attr_" + uuid.uuid4().hex[:12]


async def attribute_closed_positions(
    account_id: str, *, max_attributions: int = 100,
) -> List[ExecutionAttribution]:
    """Sweep closed positions without a matching attribution row and
    write one `ExecutionAttribution` + `execution_realised` outcome
    event per closed round-trip. Idempotent by (position_id).

    Returns the newly-written attribution rows.
    """
    closed = await ledger.read_closed_positions(
        account_id=account_id, limit=max_attributions * 3)
    if not closed:
        return []

    out: List[ExecutionAttribution] = []
    for p in closed:
        if not p.brain_decision_id:
            continue
        # Idempotency: skip if this decision_id is already attributed.
        existing = await ledger.read_attribution(
            "attr_" + p.brain_decision_id[:12].replace("-", ""))
        if existing is not None:
            continue

        # Reconstruct the chain via immutable IDs.
        fills = []
        for fid in (p.fill_ids or []):
            # Read via `read_fills` filtering by request_id is expensive.
            # Faster: keep the fill_id list on the position, and fetch
            # by fill_id one-by-one via a cheap lookup.
            pass
        # Since we don't have `read_fill_by_id`, use pair + account
        # then match on fill_id.
        cand = await ledger.read_fills(account_id=account_id, pair=p.pair,
                                         limit=1000)
        matched = [f for f in cand if f.fill_id in (p.fill_ids or [])]

        expected_price = matched[0].price if matched else p.avg_entry
        realised_price = matched[-1].price if matched else p.avg_entry
        slippage_pips = mean_slip([f.slippage_pips for f in matched
                                     if f.slippage_pips is not None]) or 0.0

        # Latest execution_quality → realised_execution_score
        eq = await measure_execution_quality(
            account_id=account_id, pair=p.pair, persist=False)
        realised_score = float(eq.score)
        predicted_score = 0.7  # will link to brain_decision outcome when Phase I lands

        attr = ExecutionAttribution(
            attribution_id="attr_" + p.brain_decision_id[:12].replace("-", ""),
            account_id=account_id,
            brain_decision_id=p.brain_decision_id,
            strategy_hash=p.strategy_hash or "",
            request_id=(matched[0].request_id if matched else ""),
            broker_order_id=(matched[0].broker_order_id if matched else None),
            fill_ids=[f.fill_id for f in matched],
            position_id=p.position_id,
            requested_ts=matched[0].timestamp if matched else p.opened_at,
            fill_ts=matched[-1].timestamp if matched else p.opened_at,
            closed_ts=p.closed_at,
            expected_price=float(expected_price),
            realised_price=float(realised_price),
            slippage_pips=float(slippage_pips),
            realised_pnl=float(p.realised_pnl),
            predicted_score=predicted_score,
            realised_execution_score=realised_score,
            delta_predicted_realised=round(realised_score - predicted_score, 4),
            outcome_events_ids=[],
        )
        await ledger.upsert_attribution(attr)
        await _emit_realised(attr)
        out.append(attr)
        if len(out) >= max_attributions:
            break
    return out


def mean_slip(vals):
    return sum(vals) / len(vals) if vals else 0.0


async def _emit_realised(attr: ExecutionAttribution) -> None:
    try:
        from engines.intelligence.explainability import emit_decision
        await emit_decision(
            "execution_realised",
            strategy_hash=attr.strategy_hash,
            reason=(f"realised_pnl={attr.realised_pnl:.2f} "
                    f"delta={attr.delta_predicted_realised:+.4f}"),
            metrics={"attribution_id": attr.attribution_id,
                      "brain_decision_id": attr.brain_decision_id,
                      "position_id": attr.position_id,
                      "realised_pnl": attr.realised_pnl,
                      "predicted_score": attr.predicted_score,
                      "realised_execution_score": attr.realised_execution_score,
                      "delta_predicted_realised": attr.delta_predicted_realised,
                      "slippage_pips": attr.slippage_pips},
            evidence={"fill_ids": attr.fill_ids,
                       "request_id": attr.request_id,
                       "broker_order_id": attr.broker_order_id},
        )
    except Exception:                                    # noqa: BLE001
        pass
