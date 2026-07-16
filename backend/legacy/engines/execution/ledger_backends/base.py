"""LedgerBackend Protocol — every implementation must satisfy this."""
from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable

from ..types import (
    BrokerHealth, ExecutionAttribution, ExecutionQualitySnapshot,
    FillEvent, JournalEvent, OrderRequest, Position,
)


@runtime_checkable
class LedgerBackend(Protocol):
    """Every persistence backend for the execution engine.

    Free-function facade in `ledger.py` delegates to the active
    backend selected via `ledger_backends.get_backend()`.
    """

    NAME: str

    async def ensure_indexes(self) -> None: ...

    # ── Orders ─────────────────────────────────────────────
    async def append_order_request(self, order: OrderRequest) -> Optional[str]: ...
    async def update_order_state(self, request_id: str, *,
        state: str, broker_order_id: Optional[str] = None,
        reject_reason: Optional[str] = None,
        cancel_reason: Optional[str] = None,
        qty_filled: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
    ) -> bool: ...
    async def read_order(self, request_id: str) -> Optional[OrderRequest]: ...
    async def read_orders(self, *, account_id: Optional[str] = None,
        strategy_hash: Optional[str] = None, state: Optional[str] = None,
        limit: int = 100) -> List[OrderRequest]: ...

    # ── Fills ──────────────────────────────────────────────
    async def append_fill_event(self, fill: FillEvent) -> Optional[str]: ...
    async def read_fills(self, *, request_id: Optional[str] = None,
        account_id: Optional[str] = None, pair: Optional[str] = None,
        limit: int = 100) -> List[FillEvent]: ...

    # ── Positions ──────────────────────────────────────────
    async def upsert_position(self, pos: Position) -> Optional[str]: ...
    async def read_position(self, position_id: str) -> Optional[Position]: ...
    async def read_positions(self, *, account_id: Optional[str] = None,
        open_only: bool = True, limit: int = 100) -> List[Position]: ...
    async def read_closed_positions(self, *,
        account_id: Optional[str] = None, limit: int = 100) -> List[Position]: ...

    # ── Broker health ──────────────────────────────────────
    async def upsert_broker_health(self, h: BrokerHealth,
        ttl_days: int = 30) -> Optional[str]: ...
    async def read_latest_broker_health(self, account_id: str) -> Optional[BrokerHealth]: ...
    async def read_broker_health_history(self, account_id: str,
        limit: int = 100) -> List[BrokerHealth]: ...

    # ── Execution quality ──────────────────────────────────
    async def upsert_execution_quality(self,
        q: ExecutionQualitySnapshot) -> Optional[str]: ...
    async def read_execution_quality(self, *, account_id: str, pair: str,
        session: str = "all", window: str = "24h",
    ) -> Optional[ExecutionQualitySnapshot]: ...

    # ── Attribution ────────────────────────────────────────
    async def upsert_attribution(self, a: ExecutionAttribution) -> Optional[str]: ...
    async def read_attribution(self, attribution_id: str) -> Optional[ExecutionAttribution]: ...
    async def read_attributions_for_strategy(self, strategy_hash: str,
        limit: int = 50) -> List[ExecutionAttribution]: ...

    # ── Journal ────────────────────────────────────────────
    async def append_journal(self, account_id: str, event_type: str,
        payload: dict, *, correlation: Optional[dict] = None,
    ) -> Optional[JournalEvent]: ...
    async def read_journal_range(self, account_id: str, *,
        start_seq: Optional[int] = None, end_seq: Optional[int] = None,
        start_ts_ns: Optional[int] = None, end_ts_ns: Optional[int] = None,
        event_type: Optional[str] = None, limit: int = 1000,
    ) -> List[JournalEvent]: ...

    # ── Ops helper ─────────────────────────────────────────
    async def wipe_account(self, account_id: str) -> None:
        """Delete every row for an account. Used by test harnesses."""
        ...
