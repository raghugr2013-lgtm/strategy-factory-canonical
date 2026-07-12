"""v01-compatibility shim for top-level `config` package.

The v01 code had `backend/config/{symbols.py, bi5_symbols.py, __init__.py}`
holding hard-coded symbol whitelists. Two preserved routers still import
from it. This shim mirrors the public API by re-exporting from the
consolidated locations.
"""
from __future__ import annotations

from typing import Dict, List

# Whitelist matches v01 backend/config/symbols.py.
SUPPORTED_SYMBOLS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
    "XAUUSD", "XAGUSD", "US30", "US100", "US500", "GER40", "UK100", "JPN225",
    "BTCUSD", "ETHUSD",
]

TIMEFRAMES: List[str] = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

# Additive helper used by v01 data_maintenance router.
def is_supported(symbol: str) -> bool:
    return symbol.upper() in [s.upper() for s in SUPPORTED_SYMBOLS]
