"""Phase H — BrokerAdapter Protocol.

Every venue integration (paper, cTrader, future IB/MT5) must satisfy
this Protocol. Adapters are:

  * asyncio-native
  * account-scoped (single account_id per adapter instance — Q8
    architected for multi-account, single-instance impl now)
  * idempotent on `submit()` via the caller's `request_id`
  * side-effect FREE outside their own broker connection (they NEVER
    write to the ledger; the caller does — this preserves single
    source of truth)

Adapters raise `BrokerError` on transient failures. `BrokerDisconnected`
means the resilience layer should re-open the connection.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, List, Protocol, runtime_checkable

from ..types import BrokerHealth, FillEvent, OrderRequest, Position


class BrokerError(Exception):
    """Transient broker failure — safe to retry after backoff."""


class BrokerDisconnected(BrokerError):
    """Connection dropped — resilience layer should reconnect."""


@runtime_checkable
class BrokerAdapter(Protocol):
    """Every venue integration MUST satisfy this Protocol."""

    NAME: str

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...

    async def submit(self, req: OrderRequest) -> str:
        """Send order to broker. Returns broker-assigned order id.
        MUST be idempotent on `req.request_id`."""
        ...

    async def cancel(self, request_id: str) -> bool: ...

    async def positions(self) -> List[Position]: ...

    async def stream_fills(self) -> AsyncIterator[FillEvent]:
        """Yield FillEvent instances as they arrive from the venue.
        For paper broker this is deterministic (yields immediately
        after submit)."""
        ...

    async def health(self) -> BrokerHealth: ...
