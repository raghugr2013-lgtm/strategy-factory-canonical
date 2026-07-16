"""Phase H — Mongo-persisted execution ledger.

Single source of truth for the 7 Phase H collections:

  * `order_requests`      — every submitted order + client idempotency key
  * `fill_events`         — every fill (partial + final)
  * `positions`           — live + closed positions
  * `broker_health`       — rolling broker-health snapshots
  * `execution_quality`   — per-pair×session×window execution quality
  * `execution_attribution` — brain-decision ↔ fill joins (immutable IDs)
  * `execution_journal`   — immutable append-only replay log (§24.3)

Every write route through this module. Never write these collections
from anywhere else — that is the invariant enforced by regression
tests.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .types import (
    BrokerHealth, ExecutionAttribution, ExecutionQualitySnapshot,
    FillEvent, JournalEvent, OrderRequest, Position,
)

logger = logging.getLogger(__name__)


COLL_ORDERS       = "order_requests"
COLL_FILLS        = "fill_events"
COLL_POSITIONS    = "positions"
COLL_HEALTH       = "broker_health"
COLL_QUALITY      = "execution_quality"
COLL_ATTRIBUTION  = "execution_attribution"
COLL_JOURNAL      = "execution_journal"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_db():
    """Best-effort db handle. Returns None when Mongo unreachable
    (ledger operations degrade to no-ops)."""
    try:
        from engines.db import get_db
        return get_db()
    except Exception:  # noqa: BLE001
        return None


async def ensure_indexes() -> None:
    """Idempotent index bootstrap — safe to re-run at every boot.

    Every collection is (account_id, ...)-indexed — Q8 multi-account
    readiness. `order_requests.request_id` and `fill_events.fill_id`
    are unique to preserve idempotency semantics."""
    db = await _get_db()
    if db is None:
        return
    try:
        # order_requests
        await db[COLL_ORDERS].create_index("request_id", unique=True,
                                            name="request_id_unique")
        await db[COLL_ORDERS].create_index(
            [("account_id", 1), ("strategy_hash", 1), ("requested_at", -1)],
            name="acct_strat_requested_1")
        await db[COLL_ORDERS].create_index(
            [("account_id", 1), ("state", 1), ("updated_at", -1)],
            name="acct_state_updated_1")
        await db[COLL_ORDERS].create_index("brain_decision_id", sparse=True,
                                            name="brain_decision_id_1")
        # fill_events
        await db[COLL_FILLS].create_index("fill_id", unique=True,
                                           name="fill_id_unique")
        await db[COLL_FILLS].create_index("request_id",
                                           name="request_id_1")
        await db[COLL_FILLS].create_index(
            [("account_id", 1), ("pair", 1), ("timestamp", -1)],
            name="acct_pair_ts_1")
        # positions
        await db[COLL_POSITIONS].create_index("position_id", unique=True,
                                                name="position_id_unique")
        await db[COLL_POSITIONS].create_index(
            [("account_id", 1), ("pair", 1), ("opened_at", -1)],
            name="acct_pair_opened_1")
        await db[COLL_POSITIONS].create_index("closed_at", sparse=True,
                                                name="closed_at_1")
        await db[COLL_POSITIONS].create_index("strategy_hash", sparse=True,
                                                name="strategy_hash_1")
        # broker_health — TTL 30d
        await db[COLL_HEALTH].create_index(
            [("account_id", 1), ("ts", -1)], name="acct_ts_1")
        await db[COLL_HEALTH].create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_expires_at")
        # execution_quality
        await db[COLL_QUALITY].create_index(
            [("account_id", 1), ("pair", 1), ("session", 1),
             ("window", 1), ("ts", -1)],
            name="acct_pair_sess_win_ts_1")
        # execution_attribution
        await db[COLL_ATTRIBUTION].create_index(
            "attribution_id", unique=True, name="attribution_id_unique")
        await db[COLL_ATTRIBUTION].create_index(
            "brain_decision_id", name="brain_decision_id_1")
        await db[COLL_ATTRIBUTION].create_index(
            [("account_id", 1), ("strategy_hash", 1), ("fill_ts", -1)],
            name="acct_strat_fill_ts_1")
        # execution_journal — permanent, chronological
        await db[COLL_JOURNAL].create_index(
            [("account_id", 1), ("seq", 1)], unique=True,
            name="acct_seq_unique")
        await db[COLL_JOURNAL].create_index(
            [("account_id", 1), ("ts_ns", 1)], name="acct_ts_1")
        await db[COLL_JOURNAL].create_index(
            [("account_id", 1), ("event_type", 1), ("ts_ns", -1)],
            name="acct_type_ts_1")
    except Exception:  # noqa: BLE001
        logger.exception("execution.ensure_indexes failed (non-fatal)")


# ── Order requests ────────────────────────────────────────────────
async def append_order_request(order: OrderRequest) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = order.to_dict()
        # Insert if new, otherwise update by idempotent request_id.
        await db[COLL_ORDERS].update_one(
            {"request_id": order.request_id},
            {"$setOnInsert": doc}, upsert=True,
        )
        return order.request_id
    except Exception:  # noqa: BLE001
        logger.exception("append_order_request failed")
        return None


async def update_order_state(
    request_id: str, *,
    state: str,
    broker_order_id: Optional[str] = None,
    reject_reason: Optional[str] = None,
    cancel_reason: Optional[str] = None,
    qty_filled: Optional[float] = None,
    avg_fill_price: Optional[float] = None,
) -> bool:
    db = await _get_db()
    if db is None:
        return False
    try:
        update: Dict[str, Any] = {"state": state, "updated_at": _now_iso()}
        if broker_order_id is not None:
            update["broker_order_id"] = broker_order_id
        if reject_reason is not None:
            update["reject_reason"] = reject_reason
        if cancel_reason is not None:
            update["cancel_reason"] = cancel_reason
        if qty_filled is not None:
            update["qty_filled"] = float(qty_filled)
        if avg_fill_price is not None:
            update["avg_fill_price"] = float(avg_fill_price)
        r = await db[COLL_ORDERS].update_one(
            {"request_id": request_id}, {"$set": update}
        )
        return r.modified_count > 0 or r.matched_count > 0
    except Exception:  # noqa: BLE001
        logger.exception("update_order_state failed")
        return False


async def read_order(request_id: str) -> Optional[OrderRequest]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_ORDERS].find_one({"request_id": request_id})
        if not d:
            return None
        d.pop("_id", None)
        return OrderRequest.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_orders(
    *, account_id: Optional[str] = None,
    strategy_hash: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 100,
) -> List[OrderRequest]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {}
        if account_id: q["account_id"] = account_id
        if strategy_hash: q["strategy_hash"] = strategy_hash
        if state: q["state"] = state
        cur = db[COLL_ORDERS].find(q).sort("requested_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(OrderRequest.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Fill events ───────────────────────────────────────────────────
async def append_fill_event(fill: FillEvent) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = fill.to_dict()
        await db[COLL_FILLS].update_one(
            {"fill_id": fill.fill_id},
            {"$setOnInsert": doc}, upsert=True,
        )
        return fill.fill_id
    except Exception:  # noqa: BLE001
        logger.exception("append_fill_event failed")
        return None


async def read_fills(
    *, request_id: Optional[str] = None,
    account_id: Optional[str] = None,
    pair: Optional[str] = None,
    limit: int = 100,
) -> List[FillEvent]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {}
        if request_id: q["request_id"] = request_id
        if account_id: q["account_id"] = account_id
        if pair: q["pair"] = pair
        cur = db[COLL_FILLS].find(q).sort("timestamp", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(FillEvent.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Positions ─────────────────────────────────────────────────────
async def upsert_position(pos: Position) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        await db[COLL_POSITIONS].update_one(
            {"position_id": pos.position_id},
            {"$set": pos.to_dict()}, upsert=True,
        )
        return pos.position_id
    except Exception:  # noqa: BLE001
        return None


async def read_position(position_id: str) -> Optional[Position]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_POSITIONS].find_one({"position_id": position_id})
        if not d:
            return None
        d.pop("_id", None)
        return Position.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_positions(
    *, account_id: Optional[str] = None, open_only: bool = True,
    limit: int = 100,
) -> List[Position]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {}
        if account_id: q["account_id"] = account_id
        if open_only: q["closed_at"] = None
        cur = db[COLL_POSITIONS].find(q).sort("opened_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(Position.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


async def read_closed_positions(
    *, account_id: Optional[str] = None, limit: int = 100,
) -> List[Position]:
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {"closed_at": {"$ne": None}}
        if account_id: q["account_id"] = account_id
        cur = db[COLL_POSITIONS].find(q).sort("closed_at", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(Position.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Broker health ─────────────────────────────────────────────────
async def upsert_broker_health(h: BrokerHealth, ttl_days: int = 30) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        doc = h.to_dict()
        expires = datetime.fromtimestamp(
            time.time() + ttl_days * 86400, tz=timezone.utc,
        )
        doc["expires_at"] = expires
        r = await db[COLL_HEALTH].insert_one(doc)
        return str(r.inserted_id)
    except Exception:  # noqa: BLE001
        return None


async def read_latest_broker_health(
    account_id: str,
) -> Optional[BrokerHealth]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_HEALTH].find_one(
            {"account_id": account_id}, sort=[("ts", -1)],
        )
        if not d:
            return None
        d.pop("_id", None)
        d.pop("expires_at", None)
        return BrokerHealth.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_broker_health_history(
    account_id: str, limit: int = 100,
) -> List[BrokerHealth]:
    db = await _get_db()
    if db is None:
        return []
    try:
        cur = db[COLL_HEALTH].find({"account_id": account_id}).sort(
            "ts", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None); d.pop("expires_at", None)
            try: out.append(BrokerHealth.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Execution quality ─────────────────────────────────────────────
async def upsert_execution_quality(
    q: ExecutionQualitySnapshot,
) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        await db[COLL_QUALITY].update_one(
            {"account_id": q.account_id, "pair": q.pair,
             "session": q.session, "window": q.window, "ts": q.ts},
            {"$set": q.to_dict()}, upsert=True,
        )
        return f"{q.account_id}:{q.pair}:{q.session}:{q.window}:{q.ts}"
    except Exception:  # noqa: BLE001
        return None


async def read_execution_quality(
    *, account_id: str, pair: str, session: str = "all",
    window: str = "24h",
) -> Optional[ExecutionQualitySnapshot]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_QUALITY].find_one(
            {"account_id": account_id, "pair": pair,
             "session": session, "window": window},
            sort=[("ts", -1)],
        )
        if not d:
            return None
        d.pop("_id", None)
        return ExecutionQualitySnapshot.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


# ── Attribution ───────────────────────────────────────────────────
async def upsert_attribution(a: ExecutionAttribution) -> Optional[str]:
    db = await _get_db()
    if db is None:
        return None
    try:
        await db[COLL_ATTRIBUTION].update_one(
            {"attribution_id": a.attribution_id},
            {"$set": a.to_dict()}, upsert=True,
        )
        return a.attribution_id
    except Exception:  # noqa: BLE001
        return None


async def read_attribution(attribution_id: str) -> Optional[ExecutionAttribution]:
    db = await _get_db()
    if db is None:
        return None
    try:
        d = await db[COLL_ATTRIBUTION].find_one(
            {"attribution_id": attribution_id})
        if not d:
            return None
        d.pop("_id", None)
        return ExecutionAttribution.from_dict(d)
    except Exception:  # noqa: BLE001
        return None


async def read_attributions_for_strategy(
    strategy_hash: str, limit: int = 50,
) -> List[ExecutionAttribution]:
    db = await _get_db()
    if db is None:
        return []
    try:
        cur = db[COLL_ATTRIBUTION].find(
            {"strategy_hash": strategy_hash}
        ).sort("fill_ts", -1).limit(int(limit))
        out = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try: out.append(ExecutionAttribution.from_dict(d))
            except TypeError: continue
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Execution journal (Replay §24.3) ──────────────────────────────
# Monotonic seq per account_id. In-memory counter (fast path) guarded
# by a per-account asyncio.Lock to prevent races under
# `asyncio.gather` when multiple writers append concurrently. On first
# use we recover base seq from Mongo max(seq).
_SEQ_CACHE: Dict[str, int] = {}
_SEQ_LOCKS: Dict[str, "asyncio.Lock"] = {}


def _seq_lock(account_id: str) -> "asyncio.Lock":
    import asyncio
    lk = _SEQ_LOCKS.get(account_id)
    if lk is None:
        lk = asyncio.Lock()
        _SEQ_LOCKS[account_id] = lk
    return lk


async def _next_seq(db, account_id: str) -> int:
    cached = _SEQ_CACHE.get(account_id)
    if cached is not None:
        _SEQ_CACHE[account_id] = cached + 1
        return cached + 1
    try:
        d = await db[COLL_JOURNAL].find_one(
            {"account_id": account_id},
            sort=[("seq", -1)], projection={"seq": 1},
        )
        base = int(d["seq"]) if d else 0
    except Exception:  # noqa: BLE001
        base = 0
    _SEQ_CACHE[account_id] = base + 1
    return base + 1


async def append_journal(
    account_id: str, event_type: str, payload: Dict[str, Any],
    *, correlation: Optional[Dict[str, str]] = None,
) -> Optional[JournalEvent]:
    """Append one immutable row to execution_journal. Returns the
    JournalEvent that was written (with its assigned seq).

    Seq allocation is guarded by a per-account asyncio.Lock so
    concurrent `asyncio.gather` writers never collide on the
    (account_id, seq) unique index.
    """
    db = await _get_db()
    if db is None:
        return None
    try:
        async with _seq_lock(account_id):
            seq = await _next_seq(db, account_id)
            evt = JournalEvent(
                seq=seq,
                ts_ns=time.time_ns(),
                account_id=account_id,
                event_type=str(event_type),
                payload=payload or {},
                correlation=correlation or {},
            )
            try:
                await db[COLL_JOURNAL].insert_one(evt.to_dict())
            except Exception:  # noqa: BLE001 — cache stale after crash, refetch and retry once
                _SEQ_CACHE.pop(account_id, None)
                seq = await _next_seq(db, account_id)
                evt = JournalEvent(seq=seq, ts_ns=time.time_ns(),
                                    account_id=account_id,
                                    event_type=str(event_type),
                                    payload=payload or {},
                                    correlation=correlation or {})
                await db[COLL_JOURNAL].insert_one(evt.to_dict())
        return evt
    except Exception:  # noqa: BLE001
        logger.exception("append_journal failed")
        return None


async def read_journal_range(
    account_id: str, *,
    start_seq: Optional[int] = None, end_seq: Optional[int] = None,
    start_ts_ns: Optional[int] = None, end_ts_ns: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = 1000,
) -> List[JournalEvent]:
    """Read the journal in seq-order (ascending — replay order)."""
    db = await _get_db()
    if db is None:
        return []
    try:
        q: Dict[str, Any] = {"account_id": account_id}
        if start_seq is not None or end_seq is not None:
            r = {}
            if start_seq is not None: r["$gte"] = int(start_seq)
            if end_seq is not None: r["$lte"] = int(end_seq)
            q["seq"] = r
        if start_ts_ns is not None or end_ts_ns is not None:
            r = {}
            if start_ts_ns is not None: r["$gte"] = int(start_ts_ns)
            if end_ts_ns is not None: r["$lte"] = int(end_ts_ns)
            q["ts_ns"] = r
        if event_type:
            q["event_type"] = event_type
        cur = db[COLL_JOURNAL].find(q).sort("seq", 1).limit(int(limit))
        out: List[JournalEvent] = []
        for d in await cur.to_list(length=int(limit)):
            d.pop("_id", None)
            try:
                out.append(JournalEvent(
                    seq=int(d["seq"]), ts_ns=int(d["ts_ns"]),
                    account_id=str(d["account_id"]),
                    event_type=str(d["event_type"]),
                    payload=d.get("payload") or {},
                    correlation=d.get("correlation") or {},
                ))
            except (KeyError, TypeError):
                continue
        return out
    except Exception:  # noqa: BLE001
        return []
