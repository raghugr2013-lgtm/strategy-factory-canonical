"""v01 config.bi5_symbols compatibility (v1.1.1-fixed).

Every consumer that formerly used the pre-1.1.1 dict-returning shim now
uses a proper dataclass, but the field surface is a strict SUPERSET of
the old dict so no caller ever loses a key.

Consumers (as of Feb 2026):
  * data_engine/adapters/dukascopy_bi5.py         → spec.url_slug
  * data_engine/bi5_ingest_runner.py              → spec.symbol, spec.market_type
  * engines/r5_shadow_comparator.py               → spec.{url_slug, price_multiplier, quote_decimals, market_type}
  * engines/market_universe_adapter.py            → _BI5_SYMBOL_SPECS (dict), spec.url_slug, spec.quote_decimals
  * engines/seed/market_universe_seed.py          → spec.url_slug, spec.quote_decimals, spec.price_multiplier
  * tests/test_market_universe_seed.py            → spec.{url_slug, price_multiplier, quote_decimals}
  * tests/test_market_universe_adapter.py         → _BI5_SYMBOL_SPECS

The prior v1.1.1 attempt to convert to a dataclass silently dropped
`url_slug`, `price_multiplier`, and `quote_decimals` — every hourly BI5
fetch then crashed with AttributeError. This module restores those
fields AND publishes the `_BI5_SYMBOL_SPECS` module-level dict every
legacy consumer imports.
"""
from dataclasses import dataclass

from legacy.config.symbols import FOREX_SYMBOLS, METAL_SYMBOLS


@dataclass
class BI5SymbolSpec:
    symbol: str
    dukascopy_instrument: str
    url_slug: str
    digits: int
    quote_decimals: int
    price_multiplier: float
    market_type: str  # "forex" | "metal"
    pip_size: float
    point_size: float
    contract_size: float
    supported: bool = True


BI5_SYMBOLS = FOREX_SYMBOLS + METAL_SYMBOLS

# Dukascopy datafeed uses uppercase concatenated symbols in the URL path
# (e.g. `.../EURUSD/2025/00/01/00h_ticks.bi5`).
DUKASCOPY_INSTRUMENT_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD", "USDCAD": "USDCAD", "NZDUSD": "NZDUSD",
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD",
}


def _digits(sym: str) -> int:
    if sym.endswith("JPY"):
        return 3
    if sym.startswith(("XAU", "XAG")):
        return 2
    return 5


def _market_type(sym: str) -> str:
    return "metal" if sym in METAL_SYMBOLS else "forex"


def _pip_size(sym: str) -> float:
    if sym in METAL_SYMBOLS:
        return 0.01 if sym.startswith("XAU") else 0.001
    return 0.01 if sym.endswith("JPY") else 0.0001


def _contract_size(sym: str) -> float:
    if sym in METAL_SYMBOLS:
        return 100.0 if sym.startswith("XAU") else 5000.0
    return 100_000.0


def _build_spec(sym: str, supported: bool = True) -> BI5SymbolSpec:
    digits = _digits(sym)
    inst = DUKASCOPY_INSTRUMENT_MAP.get(sym, sym)
    return BI5SymbolSpec(
        symbol=sym,
        dukascopy_instrument=inst,
        url_slug=inst,                     # same as instrument for FX/metals
        digits=digits,
        quote_decimals=digits,             # canonical quote decimal count
        price_multiplier=10 ** digits,     # BI5 stores ticks as ints
        market_type=_market_type(sym),
        pip_size=_pip_size(sym),
        point_size=10 ** (-digits),
        contract_size=_contract_size(sym),
        supported=supported,
    )


# Module-level dict every legacy engine imports directly.
_BI5_SYMBOL_SPECS = {sym: _build_spec(sym) for sym in BI5_SYMBOLS}


def is_bi5_supported(symbol: str) -> bool:
    return (symbol or "").upper() in BI5_SYMBOLS


def list_bi5_symbols() -> list:
    return list(BI5_SYMBOLS)


def get_bi5_symbol_spec(symbol: str) -> BI5SymbolSpec:
    s = (symbol or "").upper()
    cached = _BI5_SYMBOL_SPECS.get(s)
    if cached is not None:
        return cached
    # Unsupported symbol — return a dataclass with supported=False so
    # callers can attribute-access every field safely.
    return _build_spec(s, supported=False)
