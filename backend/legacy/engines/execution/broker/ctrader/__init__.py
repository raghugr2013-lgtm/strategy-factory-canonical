"""cTrader integration package.

Fully mocked-friendly. The real Protobuf websocket wiring is deferred
to a follow-up task; the interface + resilience layer + OAuth session
management + fill-normalisation are complete and unit-tested with a
mocked transport.

When a production cTrader integration is wired in later (H4.1), the
only concrete piece that needs to change is `client.py`'s transport
layer — the resilience wrapper, session cache, and event normaliser
already implement the required behavior contracts.
"""
from __future__ import annotations

from .client import CtraderBrokerAdapter, MockCtraderTransport, CtraderTransport
from .resilience import ResilientConnection, CircuitBreaker, ExponentialBackoff
from .session import OAuthSession, OAuthTokenExpiredError

__all__ = [
    "CtraderBrokerAdapter", "MockCtraderTransport", "CtraderTransport",
    "ResilientConnection", "CircuitBreaker", "ExponentialBackoff",
    "OAuthSession", "OAuthTokenExpiredError",
]
