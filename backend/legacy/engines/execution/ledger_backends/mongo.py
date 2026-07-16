"""MongoLedgerBackend — delegates to the free functions in `ledger.py`.

This wrapper preserves the existing Mongo-backed behaviour byte-for-byte.
It exists so the Protocol interface is uniform between backends.
"""
from __future__ import annotations

from typing import List, Optional

from ..types import (
    BrokerHealth, ExecutionAttribution, ExecutionQualitySnapshot,
    FillEvent, JournalEvent, OrderRequest, Position,
)


class MongoLedgerBackend:
    NAME = "mongo"

    # ── Orders ─────────────────────────────────────────────
    async def ensure_indexes(self):
        from .. import ledger as _l
        return await _l._mongo_ensure_indexes()

    async def append_order_request(self, order):
        from .. import ledger as _l
        return await _l._mongo_append_order_request(order)

    async def update_order_state(self, request_id, **kw):
        from .. import ledger as _l
        return await _l._mongo_update_order_state(request_id, **kw)

    async def read_order(self, request_id):
        from .. import ledger as _l
        return await _l._mongo_read_order(request_id)

    async def read_orders(self, **kw):
        from .. import ledger as _l
        return await _l._mongo_read_orders(**kw)

    # ── Fills ──────────────────────────────────────────────
    async def append_fill_event(self, fill):
        from .. import ledger as _l
        return await _l._mongo_append_fill_event(fill)

    async def read_fills(self, **kw):
        from .. import ledger as _l
        return await _l._mongo_read_fills(**kw)

    # ── Positions ──────────────────────────────────────────
    async def upsert_position(self, pos):
        from .. import ledger as _l
        return await _l._mongo_upsert_position(pos)

    async def read_position(self, position_id):
        from .. import ledger as _l
        return await _l._mongo_read_position(position_id)

    async def read_positions(self, **kw):
        from .. import ledger as _l
        return await _l._mongo_read_positions(**kw)

    async def read_closed_positions(self, **kw):
        from .. import ledger as _l
        return await _l._mongo_read_closed_positions(**kw)

    # ── Broker health ──────────────────────────────────────
    async def upsert_broker_health(self, h, ttl_days=30):
        from .. import ledger as _l
        return await _l._mongo_upsert_broker_health(h, ttl_days=ttl_days)

    async def read_latest_broker_health(self, account_id):
        from .. import ledger as _l
        return await _l._mongo_read_latest_broker_health(account_id)

    async def read_broker_health_history(self, account_id, limit=100):
        from .. import ledger as _l
        return await _l._mongo_read_broker_health_history(account_id, limit=limit)

    # ── Execution quality ──────────────────────────────────
    async def upsert_execution_quality(self, q):
        from .. import ledger as _l
        return await _l._mongo_upsert_execution_quality(q)

    async def read_execution_quality(self, **kw):
        from .. import ledger as _l
        return await _l._mongo_read_execution_quality(**kw)

    # ── Attribution ────────────────────────────────────────
    async def upsert_attribution(self, a):
        from .. import ledger as _l
        return await _l._mongo_upsert_attribution(a)

    async def read_attribution(self, attribution_id):
        from .. import ledger as _l
        return await _l._mongo_read_attribution(attribution_id)

    async def read_attributions_for_strategy(self, strategy_hash, limit=50):
        from .. import ledger as _l
        return await _l._mongo_read_attributions_for_strategy(strategy_hash, limit=limit)

    # ── Journal ────────────────────────────────────────────
    async def append_journal(self, account_id, event_type, payload,
                              *, correlation=None):
        from .. import ledger as _l
        return await _l._mongo_append_journal(
            account_id, event_type, payload, correlation=correlation)

    async def read_journal_range(self, account_id, **kw):
        from .. import ledger as _l
        return await _l._mongo_read_journal_range(account_id, **kw)

    # ── Ops ────────────────────────────────────────────────
    async def wipe_account(self, account_id):
        from .. import ledger as _l
        return await _l._mongo_wipe_account(account_id)
