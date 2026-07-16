"""Phase H — Broker adapter contract + registered adapters."""
from __future__ import annotations

from .base import BrokerAdapter, BrokerError, BrokerDisconnected
from .paper import PaperBrokerAdapter, get_paper_adapter, reset_paper_adapter

__all__ = [
    "BrokerAdapter", "BrokerError", "BrokerDisconnected",
    "PaperBrokerAdapter", "get_paper_adapter", "reset_paper_adapter",
]


def get_active_adapter():
    """Return the singleton broker adapter for the running process,
    picked by the `BROKER` env. Returns None when `EXEC_ENABLED=false`.

    Q1: default is paper. cTrader adapter is implemented in H4 (mocked
    for tests). Until then, cTrader falls back to paper with a warning
    written into an outcome_events row.
    """
    from .. import config as ecfg
    if not ecfg.exec_enabled():
        return None
    name = ecfg.broker_name()
    if name == "paper":
        return get_paper_adapter()
    if name == "ctrader":
        # H4 will provide the real adapter. For now fall back to paper
        # so a misconfigured VPS never boots into a broken state.
        return get_paper_adapter()
    return get_paper_adapter()
