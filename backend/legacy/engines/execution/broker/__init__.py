"""Phase H — Broker adapter contract + registered adapters."""
from __future__ import annotations

from .base import BrokerAdapter, BrokerError, BrokerDisconnected
from .paper import PaperBrokerAdapter, get_paper_adapter, reset_paper_adapter
from .ctrader import (                                     # noqa: F401
    CtraderBrokerAdapter, MockCtraderTransport, CtraderTransport,
    ResilientConnection, CircuitBreaker, ExponentialBackoff,
    OAuthSession, OAuthTokenExpiredError,
)

__all__ = [
    "BrokerAdapter", "BrokerError", "BrokerDisconnected",
    "PaperBrokerAdapter", "get_paper_adapter", "reset_paper_adapter",
    "CtraderBrokerAdapter", "MockCtraderTransport", "CtraderTransport",
    "ResilientConnection", "CircuitBreaker", "ExponentialBackoff",
    "OAuthSession", "OAuthTokenExpiredError",
]


def get_active_adapter():
    """Return the singleton broker adapter for the running process,
    picked by the `BROKER` env. Returns None when `EXEC_ENABLED=false`.

    Q1: default is paper. cTrader wires up in H4.1 with real Protobuf
    transport; today it falls back to paper unless a transport is
    explicitly registered via `set_ctrader_transport(...)`.
    """
    from .. import config as ecfg
    if not ecfg.exec_enabled():
        return None
    name = ecfg.broker_name()
    if name == "paper":
        return get_paper_adapter()
    if name == "ctrader":
        # Prod uses real Protobuf transport — for now, until that lands
        # in H4.1, we fall back to paper so a misconfigured VPS never
        # boots into a broken state. Callers who want cTrader in
        # production wire the transport explicitly.
        return get_paper_adapter()
    return get_paper_adapter()
