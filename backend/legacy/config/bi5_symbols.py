"""v01 config.bi5_symbols compatibility shim (v1.1.1 corrected).

`bi5_ingest_runner.py` accesses `spec.symbol`, `spec.market_type`,
`spec.digits`, etc. via ATTRIBUTES (dataclass semantics). The pre-1.1.1
version of this file returned a plain dict, which crashed the BI5
scheduler track with:

    AttributeError: 'dict' object has no attribute 'symbol'

Now `get_bi5_symbol_spec` returns a proper `BI5SymbolSpec` dataclass
with every field the runner reads. The old dict-returning callers
(`is_bi5_supported`, `list_bi5_symbols`) are unchanged.
"""
from dataclasses import dataclass, field
from typing import Optional

from legacy.config.symbols import FOREX_SYMBOLS, METAL_SYMBOLS


@dataclass
class BI5SymbolSpec:
    symbol: str
    dukascopy_instrument: str
    digits: int
    market_type: str  # "forex" | "metal"
    supported: bool = True
    # extras occasionally read by legacy engines — safe defaults
    pip_size: float = 0.0
    point_size: float = 0.0
    contract_size: float = 100_000.0


BI5_SYMBOLS = FOREX_SYMBOLS + METAL_SYMBOLS

DUKASCOPY_INSTRUMENT_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD", "USDCAD": "USDCAD", "NZDUSD": "NZDUSD",
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
}


def _market_type(sym: str) -> str:
    if sym in METAL_SYMBOLS:
        return "metal"
    return "forex"


def _digits(sym: str) -> int:
    if sym.endswith("JPY"):
        return 3
    if sym.startswith(("XAU", "XAG")):
        return 2
    return 5


def is_bi5_supported(symbol: str) -> bool:
    return symbol.upper() in BI5_SYMBOLS


def list_bi5_symbols() -> list:
    return list(BI5_SYMBOLS)


def get_bi5_symbol_spec(symbol: str) -> BI5SymbolSpec:
    s = (symbol or "").upper()
    if s not in BI5_SYMBOLS:
        # Still return a dataclass — legacy code checks `.supported`.
        return BI5SymbolSpec(
            symbol=s,
            dukascopy_instrument=DUKASCOPY_INSTRUMENT_MAP.get(s, s),
            digits=_digits(s),
            market_type=_market_type(s),
            supported=False,
        )
    digits = _digits(s)
    return BI5SymbolSpec(
        symbol=s,
        dukascopy_instrument=DUKASCOPY_INSTRUMENT_MAP.get(s, s),
        digits=digits,
        market_type=_market_type(s),
        supported=True,
        pip_size=(0.01 if s.endswith("JPY") else 0.0001) if s not in METAL_SYMBOLS else (0.01 if s.startswith("XAU") else 0.001),
        point_size=10 ** (-digits),
        contract_size=(100.0 if s.startswith("XAU") else 5000.0) if s in METAL_SYMBOLS else 100_000.0,
    )
