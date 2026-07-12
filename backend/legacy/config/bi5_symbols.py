"""v01 config.bi5_symbols compatibility (extended)."""
from dataclasses import dataclass

from legacy.config.symbols import FOREX_SYMBOLS, METAL_SYMBOLS


@dataclass
class BI5SymbolSpec:
    symbol: str
    dukascopy_instrument: str
    digits: int
    supported: bool = True

BI5_SYMBOLS = FOREX_SYMBOLS + METAL_SYMBOLS

DUKASCOPY_INSTRUMENT_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD", "USDCAD": "USDCAD", "NZDUSD": "NZDUSD",
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
}


def is_bi5_supported(symbol: str) -> bool:
    return symbol.upper() in BI5_SYMBOLS


def list_bi5_symbols() -> list:
    return list(BI5_SYMBOLS)


def get_bi5_symbol_spec(symbol: str) -> dict:
    s = symbol.upper()
    if s not in BI5_SYMBOLS:
        return {"supported": False}
    return {
        "supported": True,
        "symbol": s,
        "dukascopy_instrument": DUKASCOPY_INSTRUMENT_MAP.get(s, s),
        "digits": 3 if s.endswith("JPY") else (2 if s.startswith("XAU") else 5),
    }
