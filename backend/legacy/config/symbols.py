"""v01 config.symbols compatibility (extended per grep survey)."""
from legacy.config import SUPPORTED_SYMBOLS, is_supported  # noqa: F401

FOREX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"]
METAL_SYMBOLS = ["XAUUSD", "XAGUSD"]
INDEX_SYMBOLS = ["US30", "US100", "US500", "GER40", "UK100", "JPN225"]
CRYPTO_SYMBOLS = ["BTCUSD", "ETHUSD"]
ALL_SYMBOLS = FOREX_SYMBOLS + METAL_SYMBOLS + INDEX_SYMBOLS + CRYPTO_SYMBOLS

DEFAULT_TIMEFRAMES = ["M5", "M15", "M30", "H1", "H4", "D1"]

SYMBOL_CONFIG = {s: {"type": t, "digits": 5 if t == "forex" else 2, "point": 0.00001 if t == "forex" else 0.01}
                 for group, t in ((FOREX_SYMBOLS, "forex"), (METAL_SYMBOLS, "metal"),
                                  (INDEX_SYMBOLS, "index"), (CRYPTO_SYMBOLS, "crypto"))
                 for s in group}


def get_market_type(symbol: str) -> str:
    s = symbol.upper()
    if s in FOREX_SYMBOLS: return "forex"
    if s in METAL_SYMBOLS: return "metal"
    if s in INDEX_SYMBOLS: return "index"
    if s in CRYPTO_SYMBOLS: return "crypto"
    return "unknown"
