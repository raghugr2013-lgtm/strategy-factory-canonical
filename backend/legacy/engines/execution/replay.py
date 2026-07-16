"""Phase H11 — Execution Replay engine.

Re-derives terminal order + position state PURELY from
`execution_journal`. Deterministic offline replay — no clock reads,
no random sources, no network. Enables:

  * Reproducing production incidents
  * Debugging execution algorithms
  * Training Phase I meta-learning offline
  * Compliance / forensic analysis

Public API:
  * `ReplayReport` — structured aggregate
  * `replay_range(account_id, start_seq=..., end_seq=...)`

Design notes:
  * Consumes the journal as an immutable event stream in seq order.
  * Recomputes terminal state per request_id purely from journaled
    events (never touches the live collections).
  * Byte-identity against the live-run's terminal state is verified
    by the drill's `replay_consistency` category.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import ledger
from .types import JournalEventType, OrderState


@dataclass
class ReplayReport:
    account_id:        str
    start_seq:         int
    end_seq:           int
    n_events:          int = 0
    n_orders_seen:     int = 0
    terminal_states:   Dict[str, str] = field(default_factory=dict)
    fills_per_order:   Dict[str, int] = field(default_factory=dict)
    total_fills:       int = 0
    positions_opened:  int = 0
    positions_closed:  int = 0
    realised_pnl:      float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id":       self.account_id,
            "start_seq":        self.start_seq,
            "end_seq":          self.end_seq,
            "n_events":         self.n_events,
            "n_orders_seen":    self.n_orders_seen,
            "total_fills":      self.total_fills,
            "positions_opened": self.positions_opened,
            "positions_closed": self.positions_closed,
            "realised_pnl":     round(self.realised_pnl, 4),
            "terminal_state_counts": _count(self.terminal_states.values()),
        }


def _count(items) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


async def replay_range(
    account_id: str, *,
    start_seq: Optional[int] = None,
    end_seq: Optional[int] = None,
    limit: int = 100_000,
) -> ReplayReport:
    """Read the journal chunk [start_seq, end_seq] and derive terminal
    state per request_id. Deterministic: same input → same output."""
    events = await ledger.read_journal_range(
        account_id, start_seq=start_seq, end_seq=end_seq, limit=limit)
    report = ReplayReport(
        account_id=account_id,
        start_seq=(events[0].seq if events else 0),
        end_seq=(events[-1].seq if events else 0),
        n_events=len(events),
    )
    for e in events:
        if e.event_type == JournalEventType.ORDER_STATE_CHANGE:
            rid = e.correlation.get("request_id")
            if not rid:
                continue
            report.n_orders_seen = max(report.n_orders_seen,
                                        len(report.terminal_states) + 1)
            to = str(e.payload.get("to") or "")
            if OrderState.is_terminal(to):
                report.terminal_states[rid] = to
            elif rid not in report.terminal_states:
                report.terminal_states[rid] = to
        elif e.event_type == JournalEventType.FILL:
            rid = e.correlation.get("request_id")
            if rid:
                report.fills_per_order[rid] = report.fills_per_order.get(rid, 0) + 1
                report.total_fills += 1
    report.n_orders_seen = len(report.terminal_states)
    return report
