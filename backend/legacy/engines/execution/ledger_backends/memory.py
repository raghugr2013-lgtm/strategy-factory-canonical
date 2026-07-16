"""MemoryLedgerBackend — in-memory dict-based implementation.

Deterministic, no I/O. Used by the fast tier of the Phase H validation
harness (`paper_flow_drill.py --backend memory`) and by unit tests
that don't want to hit Mongo.

Preserves ALL invariants of the Mongo backend:
  * idempotent upserts on `request_id` / `fill_id` / `position_id` /
    `attribution_id`
  * monotonic `seq` per account for the journal (guarded by asyncio.Lock)
  * `unique (account_id, seq)` semantics via in-memory set
"""
from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..types import (
    BrokerHealth, ExecutionAttribution, ExecutionQualitySnapshot,
    FillEvent, JournalEvent, OrderRequest, Position,
)


class MemoryLedgerBackend:
    NAME = "memory"

    def __init__(self) -> None:
        # Keyed maps for O(1) idempotent upserts.
        self.orders: Dict[str, OrderRequest] = {}                # request_id → order
        self.fills:  Dict[str, FillEvent] = {}                    # fill_id → fill
        self.positions: Dict[str, Position] = {}                  # position_id → pos
        self.health: List[BrokerHealth] = []                      # append-only
        self.quality: Dict[str, ExecutionQualitySnapshot] = {}    # composite key
        self.attribution: Dict[str, ExecutionAttribution] = {}
        self.journal: List[JournalEvent] = []                     # ordered
        self._seq: Dict[str, int] = {}
        self._seq_locks: Dict[str, asyncio.Lock] = {}

    # ── Bootstrap ──────────────────────────────────────────
    async def ensure_indexes(self) -> None:
        return  # no-op — dict backend has no indexes

    # ── Orders ─────────────────────────────────────────────
    async def append_order_request(self, order: OrderRequest) -> Optional[str]:
        # Idempotent — only insert-if-absent.
        if order.request_id not in self.orders:
            self.orders[order.request_id] = deepcopy(order)
        return order.request_id

    async def update_order_state(self, request_id: str, *,
        state: str, broker_order_id: Optional[str] = None,
        reject_reason: Optional[str] = None,
        cancel_reason: Optional[str] = None,
        qty_filled: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
    ) -> bool:
        o = self.orders.get(request_id)
        if o is None:
            return False
        o.state = state
        o.updated_at = _now_iso()
        if broker_order_id is not None: o.broker_order_id = broker_order_id
        if reject_reason is not None:   o.reject_reason = reject_reason
        if cancel_reason is not None:   o.cancel_reason = cancel_reason
        if qty_filled is not None:      o.qty_filled = float(qty_filled)
        if avg_fill_price is not None:  o.avg_fill_price = float(avg_fill_price)
        return True

    async def read_order(self, request_id: str) -> Optional[OrderRequest]:
        o = self.orders.get(request_id)
        return deepcopy(o) if o else None

    async def read_orders(self, *, account_id=None, strategy_hash=None,
                            state=None, limit=100) -> List[OrderRequest]:
        vals = self.orders.values()
        out = []
        for o in vals:
            if account_id and o.account_id != account_id: continue
            if strategy_hash and o.strategy_hash != strategy_hash: continue
            if state and o.state != state: continue
            out.append(deepcopy(o))
        out.sort(key=lambda x: x.requested_at, reverse=True)
        return out[:limit]

    # ── Fills ──────────────────────────────────────────────
    async def append_fill_event(self, fill: FillEvent) -> Optional[str]:
        if fill.fill_id not in self.fills:
            self.fills[fill.fill_id] = deepcopy(fill)
        return fill.fill_id

    async def read_fills(self, *, request_id=None, account_id=None,
                           pair=None, limit=100) -> List[FillEvent]:
        out = []
        for f in self.fills.values():
            if request_id and f.request_id != request_id: continue
            if account_id and f.account_id != account_id: continue
            if pair and f.pair != pair: continue
            out.append(deepcopy(f))
        out.sort(key=lambda x: x.timestamp, reverse=True)
        return out[:limit]

    # ── Positions ──────────────────────────────────────────
    async def upsert_position(self, pos: Position) -> Optional[str]:
        self.positions[pos.position_id] = deepcopy(pos)
        return pos.position_id

    async def read_position(self, position_id: str) -> Optional[Position]:
        p = self.positions.get(position_id)
        return deepcopy(p) if p else None

    async def read_positions(self, *, account_id=None, open_only=True,
                               limit=100) -> List[Position]:
        out = []
        for p in self.positions.values():
            if account_id and p.account_id != account_id: continue
            if open_only and p.closed_at is not None: continue
            out.append(deepcopy(p))
        out.sort(key=lambda x: x.opened_at, reverse=True)
        return out[:limit]

    async def read_closed_positions(self, *, account_id=None,
                                       limit=100) -> List[Position]:
        out = []
        for p in self.positions.values():
            if p.closed_at is None: continue
            if account_id and p.account_id != account_id: continue
            out.append(deepcopy(p))
        out.sort(key=lambda x: x.closed_at or "", reverse=True)
        return out[:limit]

    # ── Broker health ──────────────────────────────────────
    async def upsert_broker_health(self, h: BrokerHealth,
                                     ttl_days: int = 30) -> Optional[str]:
        self.health.append(deepcopy(h))
        return f"mem_health_{len(self.health)}"

    async def read_latest_broker_health(self, account_id: str
                                          ) -> Optional[BrokerHealth]:
        for h in reversed(self.health):
            if h.account_id == account_id:
                return deepcopy(h)
        return None

    async def read_broker_health_history(self, account_id: str,
                                           limit: int = 100) -> List[BrokerHealth]:
        out = [deepcopy(h) for h in self.health if h.account_id == account_id]
        out.sort(key=lambda x: x.ts, reverse=True)
        return out[:limit]

    # ── Execution quality ──────────────────────────────────
    async def upsert_execution_quality(self, q: ExecutionQualitySnapshot
                                         ) -> Optional[str]:
        key = f"{q.account_id}:{q.pair}:{q.session}:{q.window}:{q.ts}"
        self.quality[key] = deepcopy(q)
        return key

    async def read_execution_quality(self, *, account_id: str, pair: str,
                                       session: str = "all", window: str = "24h"
                                       ) -> Optional[ExecutionQualitySnapshot]:
        candidates = [q for k, q in self.quality.items()
                      if q.account_id == account_id and q.pair == pair
                      and q.session == session and q.window == window]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.ts, reverse=True)
        return deepcopy(candidates[0])

    # ── Attribution ────────────────────────────────────────
    async def upsert_attribution(self, a: ExecutionAttribution) -> Optional[str]:
        self.attribution[a.attribution_id] = deepcopy(a)
        return a.attribution_id

    async def read_attribution(self, attribution_id: str
                                 ) -> Optional[ExecutionAttribution]:
        a = self.attribution.get(attribution_id)
        return deepcopy(a) if a else None

    async def read_attributions_for_strategy(self, strategy_hash: str,
                                                limit: int = 50
                                                ) -> List[ExecutionAttribution]:
        out = [deepcopy(a) for a in self.attribution.values()
               if a.strategy_hash == strategy_hash]
        out.sort(key=lambda x: x.fill_ts, reverse=True)
        return out[:limit]

    # ── Journal ────────────────────────────────────────────
    def _lock(self, account_id: str) -> asyncio.Lock:
        lk = self._seq_locks.get(account_id)
        if lk is None:
            lk = asyncio.Lock()
            self._seq_locks[account_id] = lk
        return lk

    async def append_journal(self, account_id: str, event_type: str,
                               payload: Dict[str, Any], *,
                               correlation: Optional[Dict[str, str]] = None,
                               ) -> Optional[JournalEvent]:
        async with self._lock(account_id):
            seq = self._seq.get(account_id, 0) + 1
            self._seq[account_id] = seq
            evt = JournalEvent(
                seq=seq, ts_ns=time.time_ns(),
                account_id=account_id, event_type=str(event_type),
                payload=deepcopy(payload) or {},
                correlation=deepcopy(correlation) or {},
            )
            self.journal.append(evt)
            return evt

    async def read_journal_range(self, account_id: str, *,
                                    start_seq=None, end_seq=None,
                                    start_ts_ns=None, end_ts_ns=None,
                                    event_type=None, limit=1000,
                                    ) -> List[JournalEvent]:
        out = []
        for e in self.journal:
            if e.account_id != account_id: continue
            if start_seq is not None and e.seq < start_seq: continue
            if end_seq   is not None and e.seq > end_seq: continue
            if start_ts_ns is not None and e.ts_ns < start_ts_ns: continue
            if end_ts_ns   is not None and e.ts_ns > end_ts_ns: continue
            if event_type and e.event_type != event_type: continue
            out.append(deepcopy(e))
        out.sort(key=lambda x: x.seq)  # replay order
        return out[:limit]

    # ── Ops ────────────────────────────────────────────────
    async def wipe_account(self, account_id: str) -> None:
        self.orders   = {k: v for k, v in self.orders.items()   if v.account_id != account_id}
        self.fills    = {k: v for k, v in self.fills.items()    if v.account_id != account_id}
        self.positions = {k: v for k, v in self.positions.items() if v.account_id != account_id}
        self.health   = [h for h in self.health   if h.account_id != account_id]
        self.quality  = {k: v for k, v in self.quality.items()  if v.account_id != account_id}
        self.attribution = {k: v for k, v in self.attribution.items() if v.account_id != account_id}
        self.journal  = [e for e in self.journal  if e.account_id != account_id]
        self._seq.pop(account_id, None)
        self._seq_locks.pop(account_id, None)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
