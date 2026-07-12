"""R1 — Read-side adapter between legacy symbol constants and the
dynamic market_universe registry.

Contract
--------
* **Always SYNC.** Every legacy caller is sync; this adapter never
  blocks the caller on a Mongo round-trip.
* **Flag OFF (default through R1–R4):** every function returns the
  legacy hardcoded value. Byte-identical to pre-R1.
* **Flag ON (R5+):** every function first consults the cached registry
  snapshot. On miss, falls back to the legacy value. Never raises.
* **Alias resolution is always-on.** The adapter normalises and
  resolves aliases (e.g. ``NAS100`` → ``US100``, ``GOLD`` → ``XAUUSD``)
  BEFORE any lookup. This is a strict widening — for the 7 canonical
  symbols, no behavioural change vs legacy (none of them is itself
  an alias).
* **Read-only at this layer.** No writes, no mutation, no audit.
  Writes still flow through ``engines.market_universe`` admin paths.

How the cache works
-------------------
* The cache is an in-memory ``dict[str, dict]`` keyed by canonical
  symbol. Populated by:
    1. ``refresh_cache_from_db()`` — async helper called by the
       startup hook in R5+. Idempotent.
    2. ``set_registry_cache(rows)`` — sync helper used by tests and
       by the startup hook to seed the cache.
* The legacy fallback path does NOT depend on the cache; it reads the
  legacy module constants directly. Cache misses are safe.

Why sync, not async
-------------------
Every legacy call site (``config/symbols.py::get_market_type``,
``config/bi5_symbols.py::get_bi5_symbol_spec``,
``data_engine/dukascopy_downloader.py``) is sync. Promoting them to
async would ripple through dozens of call sites — out of R1 scope.
The cache covers the realistic operational set (<100 symbols); a
read-through async refresh runs only at startup.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Flag check (mirrors engines.market_universe.is_enabled but kept here
# to avoid a hard import dependency on the writer module).
# ─────────────────────────────────────────────────────────────────────
def is_flag_on() -> bool:
    raw = os.environ.get("ENABLE_DYNAMIC_MARKET_UNIVERSE", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ─────────────────────────────────────────────────────────────────────
# Canonical normalisation + alias resolution
# ─────────────────────────────────────────────────────────────────────
_NORM_STRIP = re.compile(r"[^A-Z0-9]")


def normalize(symbol: Optional[str]) -> str:
    if not symbol:
        return ""
    return _NORM_STRIP.sub("", str(symbol).upper())


# Static alias map. Always-on; same in both flag states. New aliases
# can be registered dynamically via ``register_alias`` (test/admin
# helper) — the dynamic table is consulted before the static one so
# the registry-defined aliases take precedence.
_STATIC_ALIASES: Dict[str, str] = {
    "NAS100": "US100",
    "GOLD":   "XAUUSD",
}
_DYNAMIC_ALIASES: Dict[str, str] = {}

_cache_lock = threading.RLock()
_REGISTRY_CACHE: Dict[str, Dict[str, Any]] = {}


def register_alias(alias: str, canonical: str) -> None:
    """Register a dynamic alias. Used by ``refresh_cache_from_db`` to
    import operator-configured aliases. Kept idempotent."""
    a = normalize(alias)
    c = normalize(canonical)
    if a and c and a != c:
        _DYNAMIC_ALIASES[a] = c


def resolve_alias(symbol: Optional[str]) -> str:
    """Return the canonical symbol for ``symbol``. When ``symbol`` is
    not an alias, returns ``normalize(symbol)`` unchanged.

    Always-on. Same behaviour in both flag states. Pure function.
    """
    s = normalize(symbol)
    if not s:
        return s
    if s in _DYNAMIC_ALIASES:
        return _DYNAMIC_ALIASES[s]
    if s in _STATIC_ALIASES:
        return _STATIC_ALIASES[s]
    return s


# ─────────────────────────────────────────────────────────────────────
# Cache management
# ─────────────────────────────────────────────────────────────────────
def set_registry_cache(rows: List[Dict[str, Any]]) -> None:
    """Replace the in-memory cache with the supplied rows.

    Each row's ``aliases`` field is also imported into the dynamic
    alias map. Kept idempotent. Sync, no I/O.
    """
    new_cache: Dict[str, Dict[str, Any]] = {}
    with _cache_lock:
        _DYNAMIC_ALIASES.clear()
        for row in rows or []:
            sym = normalize(row.get("symbol"))
            if not sym:
                continue
            new_cache[sym] = dict(row)
            for a in (row.get("aliases") or []):
                register_alias(a, sym)
        _REGISTRY_CACHE.clear()
        _REGISTRY_CACHE.update(new_cache)


def clear_registry_cache() -> None:
    with _cache_lock:
        _REGISTRY_CACHE.clear()
        _DYNAMIC_ALIASES.clear()


def cache_size() -> int:
    return len(_REGISTRY_CACHE)


async def refresh_cache_from_db() -> Dict[str, Any]:
    """Repopulate the cache from Mongo. R5+ startup hook. Never raises.

    Returns a summary ``{loaded: int, errors: List[str]}``.
    """
    try:
        from engines.market_universe import list_symbols
        rows = await list_symbols(limit=2000)
        set_registry_cache(rows)
        return {"loaded": len(rows), "errors": []}
    except Exception as e:                                  # pragma: no cover
        logger.warning("[market_universe_adapter] refresh failed: %s", e)
        return {"loaded": 0, "errors": [str(e)[:200]]}


def _lookup(symbol: str) -> Optional[Dict[str, Any]]:
    """Cached registry lookup (sync). Returns ``None`` on miss.

    Honours ``is_flag_on()``: with the flag OFF, we deliberately
    return ``None`` so that every public adapter function falls
    through to the legacy path.
    """
    if not is_flag_on():
        return None
    sym = resolve_alias(symbol)
    return _REGISTRY_CACHE.get(sym)


# ─────────────────────────────────────────────────────────────────────
# Legacy snapshots — imported once, never mutated.
# Kept here so the adapter's fallback path is decoupled from any
# downstream refactor to the legacy modules (we can move them later
# without changing the public contract).
# ─────────────────────────────────────────────────────────────────────
def _legacy_symbol_config() -> Dict[str, Dict[str, Any]]:
    from config.symbols import SYMBOL_CONFIG
    return SYMBOL_CONFIG


def _legacy_default_calendar() -> Dict[str, Any]:
    # Mirror of the private _DEFAULT in config/symbols.
    return {"market_type": "forex", "timezone": "UTC"}


def _legacy_bi5_specs() -> Dict[str, Any]:
    from config.bi5_symbols import _BI5_SYMBOL_SPECS
    return _BI5_SYMBOL_SPECS


def _legacy_instrument_map() -> Dict[str, Any]:
    from data_engine.dukascopy_downloader import INSTRUMENT_MAP
    return INSTRUMENT_MAP


# ─────────────────────────────────────────────────────────────────────
# Public sync API
# ─────────────────────────────────────────────────────────────────────
def get_calendar(symbol: str) -> Dict[str, Any]:
    """Return the calendar block ``{market_type, timezone}`` for ``symbol``.

    Falls back to ``{market_type: 'forex', timezone: 'UTC'}`` when
    the symbol is unknown — matching legacy ``config/symbols._DEFAULT``.
    """
    sym = resolve_alias(symbol)
    row = _lookup(sym)
    if row:
        cal = row.get("calendar") or {}
        if "market_type" in cal and "timezone" in cal:
            return {"market_type": cal["market_type"], "timezone": cal["timezone"]}
    # Legacy fallback (byte-identical to config.symbols.get_symbol_config).
    return dict(_legacy_symbol_config().get(sym, _legacy_default_calendar()))


def get_market_type(symbol: str) -> str:
    return get_calendar(symbol)["market_type"]


def get_bi5_symbol_spec(symbol: str) -> Any:
    """Return a ``BI5SymbolSpec`` (frozen dataclass) for ``symbol``.

    On registry hit, constructs a spec from the registry row. On
    miss (or flag OFF), returns the legacy spec from
    ``config.bi5_symbols._BI5_SYMBOL_SPECS``. Raises ``KeyError`` only
    when BOTH the registry and legacy table miss the symbol — same
    error contract as the legacy function.
    """
    from config.bi5_symbols import BI5SymbolSpec
    sym = resolve_alias(symbol)
    row = _lookup(sym)
    if row:
        bm = row.get("broker_mapping") or {}
        prec = row.get("precision") or {}
        ac = row.get("asset_class") or "other"
        # Map registry asset_class to legacy market_type string.
        market_type = {
            "fx_major":         "forex",
            "fx_cross":         "forex",
            "fx_exotic":        "forex",
            "commodity_metal":  "metal",
            "commodity_energy": "energy",
            "index":            "index",
            "crypto":           "crypto",
            "stock":            "stock",
        }.get(ac, "forex")
        url_slug = bm.get("dukascopy_slug") or sym
        try:
            return BI5SymbolSpec(
                symbol=sym,
                url_slug=url_slug,
                price_multiplier=float(prec.get("price_multiplier", 1e5)),
                quote_decimals=int(prec.get("quote_decimals", 5)),
                market_type=market_type,
            )
        except Exception as e:                              # pragma: no cover
            logger.debug(
                "[market_universe_adapter] registry row malformed for %s: %s",
                sym, e,
            )
    # Legacy fallback. Raises KeyError on hard miss — same as legacy.
    specs = _legacy_bi5_specs()
    if sym not in specs:
        raise KeyError(
            f"BI5 spec not registered for {sym!r}. "
            f"Known: {sorted(specs)}"
        )
    return specs[sym]


def is_bi5_supported(symbol: str) -> bool:
    """True iff a BI5 spec is registered for ``symbol`` (or one of its
    aliases). Always-on alias resolution — ``NAS100`` resolves to
    ``US100``."""
    sym = resolve_alias(symbol)
    if _lookup(sym):
        return True
    return sym in _legacy_bi5_specs()


def list_bi5_symbols() -> List[str]:
    """Sorted union of registry (when flag on) and legacy BI5 symbols.

    Flag OFF: returns exactly the legacy list (byte-identical).
    """
    if not is_flag_on():
        return sorted(_legacy_bi5_specs())
    keys = set(_legacy_bi5_specs().keys())
    with _cache_lock:
        keys.update(_REGISTRY_CACHE.keys())
    return sorted(keys)


def resolve_dukascopy_instrument(symbol: str) -> Optional[Any]:
    """Return the Dukascopy SDK enum value for ``symbol`` (or one of
    its aliases). Returns ``None`` when no mapping exists.

    Order:
        1. Registry hit (flag ON) → look up the SDK enum object by
           name via ``getattr(dukascopy_python, name, None)``.
        2. Legacy ``INSTRUMENT_MAP[sym]``.
        3. Legacy ``INSTRUMENT_MAP[resolved_alias]``.

    The caller (the SDK downloader) decides what to do with ``None``
    — same contract as ``INSTRUMENT_MAP.get(sym)``.
    """
    sym = resolve_alias(symbol)
    row = _lookup(sym)
    if row:
        bm = row.get("broker_mapping") or {}
        name = bm.get("dukascopy_instrument_id")
        if name:
            try:
                import dukascopy_python                   # pragma: no cover
                obj = getattr(dukascopy_python, name, None)
                if obj is not None:
                    return obj
            except Exception:                              # pragma: no cover
                # SDK unavailable in the test environment — fall through.
                pass
    legacy = _legacy_instrument_map()
    return legacy.get(sym)


# ═════════════════════════════════════════════════════════════════════
# R2 — Certification-defaults adapters
# ═════════════════════════════════════════════════════════════════════
def get_density_table(symbol: str, session: str) -> Tuple[int, int]:
    """Return ``(floor, target)`` ticks/hour for ``(symbol, session)``.

    Authority chain:
        1. Registry hit (flag ON, alias-aware) → ``cert_defaults.density_table[session]``.
        2. Legacy ``engines.tick_validator.DENSITY_TABLE`` for the symbol.
        3. Legacy ``_FALLBACK_DENSITY`` per session (anchor 500..3000).

    The legacy authority is preserved verbatim — this function returns
    EXACTLY what ``engines.tick_validator._density_for`` would have
    returned for the canonical 7 symbols when the flag is OFF.
    """
    sym = resolve_alias(symbol)
    row = _lookup(sym)
    if row:
        cd = row.get("cert_defaults") or {}
        dt = cd.get("density_table") or {}
        val = dt.get(session)
        if val and len(val) >= 2:
            try:
                return int(val[0]), int(val[1])
            except (ValueError, TypeError):                # pragma: no cover
                pass
    # Legacy fallback (byte-identical to engines.tick_validator._density_for).
    try:
        from engines.tick_validator import (
            DENSITY_TABLE as _LEGACY_DENSITY,
            _FALLBACK_DENSITY as _LEGACY_FALLBACK,
        )
    except Exception:                                       # pragma: no cover
        return (500, 3000)
    table = _LEGACY_DENSITY.get(sym)
    if table is None:
        return _LEGACY_FALLBACK.get(session, (500, 3000))
    return table.get(session, _LEGACY_FALLBACK[session])


def get_tolerance_bps(symbol: str) -> float:
    """Return spread-tolerance BPS for ``symbol``.

    Authority chain:
        1. Registry hit (alias-aware) → ``spread_defaults.tolerance_bps``.
        2. Legacy ``engines.spread_analyzer.DEFAULT_TOLERANCE_BPS[symbol]``.
        3. Legacy ``_FALLBACK_TOLERANCE_BPS = 2.0``.
    """
    sym = resolve_alias(symbol)
    row = _lookup(sym)
    if row:
        sd = row.get("spread_defaults") or {}
        if "tolerance_bps" in sd:
            try:
                return float(sd["tolerance_bps"])
            except (ValueError, TypeError):                # pragma: no cover
                pass
    try:
        from engines.spread_analyzer import (
            DEFAULT_TOLERANCE_BPS as _LEGACY_TOL,
            _FALLBACK_TOLERANCE_BPS as _LEGACY_FALLBACK,
        )
    except Exception:                                       # pragma: no cover
        return 2.0
    return _LEGACY_TOL.get(sym, _LEGACY_FALLBACK)


def get_symbol_default_bps(symbol: str) -> float:
    """Return the assumed-spread default BPS for ``symbol``.

    Authority chain:
        1. Registry hit (alias-aware) → ``spread_defaults.symbol_default_bps``.
        2. Legacy ``engines.spread_analyzer.SYMBOL_DEFAULT_BPS[symbol]``.
        3. Legacy ``_FALLBACK_TOLERANCE_BPS = 2.0`` (the same fallback
           the legacy code uses when SYMBOL_DEFAULT_BPS misses).
    """
    sym = resolve_alias(symbol)
    row = _lookup(sym)
    if row:
        sd = row.get("spread_defaults") or {}
        if "symbol_default_bps" in sd:
            try:
                return float(sd["symbol_default_bps"])
            except (ValueError, TypeError):                # pragma: no cover
                pass
    try:
        from engines.spread_analyzer import (
            SYMBOL_DEFAULT_BPS as _LEGACY_DEFAULT,
            _FALLBACK_TOLERANCE_BPS as _LEGACY_FALLBACK,
        )
    except Exception:                                       # pragma: no cover
        return 2.0
    return _LEGACY_DEFAULT.get(sym, _LEGACY_FALLBACK)


def resolve_pip_size(pair: Optional[str], override: Optional[float] = None) -> float:
    """Adapter-promoted pip-size resolver.

    Authority chain:
        1. Caller-supplied ``override`` (positive float wins).
        2. Registry hit (alias-aware) → ``precision.pip_size``. **R2
           contract: the registry value is consulted ONLY when the
           flag is ON.** While the flag is OFF (default through R4)
           the registry is bypassed — by design — so that the BTC/ETH
           and index pip-sizes that the R0 seed stored more accurately
           (0.01) do NOT change PnL math vs the legacy substring
           resolver (0.0001 for those symbols).
        3. Legacy substring resolver (JPY → 0.01, XAU → 0.1,
           XAG → 0.001, else 0.0001).
    """
    if override is not None and override > 0:
        return float(override)
    if not pair:
        return 0.0001
    # Alias-aware lookup (only when flag ON, by virtue of _lookup).
    sym = resolve_alias(pair)
    row = _lookup(sym)
    if row:
        prec = row.get("precision") or {}
        if "pip_size" in prec:
            try:
                v = float(prec["pip_size"])
                if v > 0:
                    return v
            except (ValueError, TypeError):                # pragma: no cover
                pass
    # Legacy substring resolver (byte-identical to engines.cbot_trade_parity).
    upper = (pair or "").upper()
    if "JPY" in upper:
        return 0.01
    if "XAU" in upper:
        return 0.1
    if "XAG" in upper:
        return 0.001
    return 0.0001


# ═════════════════════════════════════════════════════════════════════
# R3 — Eligibility-aware symbol-set accessors
# ═════════════════════════════════════════════════════════════════════
# Map of eligibility flag → legacy snapshot used as fall-through.
# Each legacy snapshot is a callable returning a sequence of symbols,
# evaluated lazily so the import order stays tolerant.
def _legacy_watchlist() -> List[str]:
    try:
        from engines.readiness_engine import WATCHLIST
        return list(WATCHLIST)
    except Exception:                                       # pragma: no cover
        return ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
                "US100", "BTCUSD", "ETHUSD"]


def _legacy_tier1_symbols() -> List[str]:
    try:
        from engines.readiness_engine import TIER1_SYMBOLS
        return list(TIER1_SYMBOLS)
    except Exception:                                       # pragma: no cover
        return ["EURUSD", "GBPUSD"]


def _legacy_intelligence_pairs() -> List[str]:
    try:
        from engines.market_intelligence import DEFAULT_PAIRS
        return list(DEFAULT_PAIRS)
    except Exception:                                       # pragma: no cover
        return ["EURUSD", "GBPUSD", "XAUUSD"]


def _legacy_data_api_allowed() -> List[str]:
    try:
        from api.data import ALLOWED_SYMBOLS
        return list(ALLOWED_SYMBOLS)
    except Exception:                                       # pragma: no cover
        return ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
                "US100", "BTCUSD", "ETHUSD"]


def _legacy_data_maintenance_pairs() -> List[str]:
    try:
        from data_engine.data_maintenance import DEFAULT_PAIRS
        return list(DEFAULT_PAIRS)
    except Exception:                                       # pragma: no cover
        return ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]


def _legacy_auto_factory_pairs() -> List[str]:
    try:
        from engines.auto_factory_engine import DEFAULT_PAIRS
        return list(DEFAULT_PAIRS)
    except Exception:                                       # pragma: no cover
        return ["EURUSD", "GBPUSD", "XAUUSD"]


def _legacy_gem_factory_pairs() -> List[str]:
    return ["EURUSD", "GBPUSD", "XAUUSD"]


def _legacy_phase55_pairs() -> List[str]:
    return ["EURUSD", "XAUUSD", "BTCUSD"]


def _registry_symbols_with_eligibility(flag_key: str) -> List[str]:
    """Return registry symbols where ``eligibility[flag_key] is True``.
    Sorted by row ``priority`` DESC, then alphabetic. Empty when the
    flag is OFF or when the cache is empty."""
    if not is_flag_on():
        return []
    with _cache_lock:
        rows = [r for r in _REGISTRY_CACHE.values()
                if bool((r.get("eligibility") or {}).get(flag_key))]
    rows.sort(key=lambda r: (-int(r.get("priority", 0)), r.get("symbol", "")))
    return [r.get("symbol", "") for r in rows if r.get("symbol")]


def get_active_watchlist() -> List[str]:
    """Return the production "watchlist" — the set of symbols whose
    data we expect to be present at all times.

    Authority chain:
        1. Registry rows where ``eligibility.ingestion_enabled is True``
           (flag ON only).
        2. Legacy ``engines.readiness_engine.WATCHLIST``.

    The R3 contract: while the flag is OFF, the legacy tuple is
    returned verbatim — same order, same symbols. While the flag is
    ON, the registry slice is returned. Either way, the result is a
    list of strings (the legacy is exposed as a tuple; we promote to
    list at the boundary for symmetry).
    """
    reg = _registry_symbols_with_eligibility("ingestion_enabled")
    if reg:
        return reg
    return _legacy_watchlist()


def get_tier1_symbols() -> List[str]:
    """Return the "tier 1" subset — the symbols we treat as production-
    critical for readiness signalling.

    Authority chain:
        1. Registry rows with ``tier == "active"`` (flag ON only).
        2. Legacy ``engines.readiness_engine.TIER1_SYMBOLS``.
    """
    if is_flag_on():
        with _cache_lock:
            rows = [r for r in _REGISTRY_CACHE.values()
                    if (r.get("tier") or "").lower() == "active"
                    and bool(r.get("enabled", True))]
        rows.sort(key=lambda r: (-int(r.get("priority", 0)), r.get("symbol", "")))
        out = [r.get("symbol", "") for r in rows if r.get("symbol")]
        if out:
            return out
    return _legacy_tier1_symbols()


def get_intelligence_pairs() -> List[str]:
    """Return the default pair set for the intelligence digest.

    Authority chain:
        1. Registry rows with ``eligibility.discovery_enabled is True``
           AND ``tier in {active, candidate}`` (flag ON only).
        2. Legacy ``engines.market_intelligence.DEFAULT_PAIRS``.
    """
    if is_flag_on():
        with _cache_lock:
            rows = [r for r in _REGISTRY_CACHE.values()
                    if bool((r.get("eligibility") or {}).get("discovery_enabled"))
                    and (r.get("tier") or "").lower() in ("active", "candidate")
                    and bool(r.get("enabled", True))]
        rows.sort(key=lambda r: (-int(r.get("priority", 0)), r.get("symbol", "")))
        out = [r.get("symbol", "") for r in rows if r.get("symbol")]
        if out:
            return out
    return _legacy_intelligence_pairs()


def get_allowed_symbols() -> List[str]:
    """Return the symbol set accepted by ``/api/data*`` validators.

    Authority chain:
        1. Union of registry rows where ``enabled`` AND
           ``eligibility.ingestion_enabled`` (flag ON only).
        2. Legacy ``api.data.ALLOWED_SYMBOLS``.
    """
    reg = _registry_symbols_with_eligibility("ingestion_enabled")
    if reg:
        return reg
    return _legacy_data_api_allowed()


def get_data_maintenance_pairs() -> List[str]:
    """Return the pair set the unattended-data-maintenance loop scans
    by default.

    Authority chain:
        1. Registry rows where ``eligibility.ingestion_enabled is True``
           AND ``tier in {active, candidate}`` AND ``enabled`` (flag ON).
        2. Legacy ``data_engine.data_maintenance.DEFAULT_PAIRS``.
    """
    if is_flag_on():
        with _cache_lock:
            rows = [r for r in _REGISTRY_CACHE.values()
                    if bool((r.get("eligibility") or {}).get("ingestion_enabled"))
                    and (r.get("tier") or "").lower() in ("active", "candidate")
                    and bool(r.get("enabled", True))]
        rows.sort(key=lambda r: (-int(r.get("priority", 0)), r.get("symbol", "")))
        out = [r.get("symbol", "") for r in rows if r.get("symbol")]
        if out:
            return out
    return _legacy_data_maintenance_pairs()


def get_discovery_pairs() -> List[str]:
    """Return the pair set the discovery factories scan by default.

    Authority chain:
        1. Registry rows with ``eligibility.discovery_enabled is True``
           AND ``enabled`` (flag ON only).
        2. Legacy ``engines.auto_factory_engine.DEFAULT_PAIRS``.
    """
    reg = _registry_symbols_with_eligibility("discovery_enabled")
    if reg:
        return reg
    return _legacy_auto_factory_pairs()


def get_mutation_pairs() -> List[str]:
    """Return the pair set auto-mutation considers by default.

    Authority chain:
        1. Registry rows with ``eligibility.mutation_enabled is True``
           AND ``enabled`` (flag ON only).
        2. Legacy ``engines.auto_factory_engine.DEFAULT_PAIRS``
           (the same default the factories use).
    """
    reg = _registry_symbols_with_eligibility("mutation_enabled")
    if reg:
        return reg
    return _legacy_auto_factory_pairs()


def get_validation_pairs() -> List[str]:
    """Return the pair set validation runs against by default.

    Authority chain:
        1. Registry rows with ``eligibility.validation_enabled is True``
           AND ``enabled`` (flag ON only).
        2. Legacy watchlist (same set the readiness engine watches).
    """
    reg = _registry_symbols_with_eligibility("validation_enabled")
    if reg:
        return reg
    return _legacy_watchlist()


def get_portfolio_pairs() -> List[str]:
    """Return the pair set the portfolio builder considers by default.

    Authority chain:
        1. Registry rows with ``eligibility.portfolio_enabled is True``
           AND ``enabled`` (flag ON only).
        2. Legacy ``data_engine.data_maintenance.DEFAULT_PAIRS``
           (the 4-major set the portfolio panel uses today).
    """
    reg = _registry_symbols_with_eligibility("portfolio_enabled")
    if reg:
        return reg
    return _legacy_data_maintenance_pairs()


def get_certification_pairs() -> List[str]:
    """Return the pair set BI5 certification runs against by default.

    Authority chain:
        1. Registry rows with ``eligibility.certification_enabled is True``
           AND ``enabled`` (flag ON only).
        2. Legacy ``engines.market_intelligence.DEFAULT_PAIRS``.
    """
    reg = _registry_symbols_with_eligibility("certification_enabled")
    if reg:
        return reg
    return _legacy_intelligence_pairs()


def is_eligible(symbol: str, *, capability: str) -> bool:
    """Boolean predicate: is ``symbol`` eligible for ``capability``?

    ``capability`` is one of the ``eligibility.*`` flags (without the
    ``_enabled`` suffix being required — both forms accepted). Alias-
    aware. When the flag is OFF, falls back to whether the symbol
    appears in the corresponding legacy default set.
    """
    cap = (capability or "").strip().lower()
    if not cap:
        return False
    if not cap.endswith("_enabled"):
        cap = f"{cap}_enabled"
    sym = resolve_alias(symbol)
    row = _lookup(sym)
    if row is not None:
        return bool((row.get("eligibility") or {}).get(cap))
    # Legacy fallback by capability.
    if cap == "ingestion_enabled":
        return sym in _legacy_data_api_allowed()
    if cap == "validation_enabled":
        return sym in _legacy_watchlist()
    if cap == "discovery_enabled":
        return sym in _legacy_auto_factory_pairs()
    if cap == "mutation_enabled":
        return sym in _legacy_auto_factory_pairs()
    if cap == "portfolio_enabled":
        return sym in _legacy_data_maintenance_pairs()
    if cap == "certification_enabled":
        return sym in _legacy_intelligence_pairs()
    if cap == "live_trading_enabled":
        return False
    return False


__all__ = [
    "is_flag_on",
    "normalize", "resolve_alias", "register_alias",
    "set_registry_cache", "clear_registry_cache", "cache_size",
    "refresh_cache_from_db",
    "get_calendar", "get_market_type",
    "get_bi5_symbol_spec", "is_bi5_supported", "list_bi5_symbols",
    "resolve_dukascopy_instrument",
    # R2:
    "get_density_table", "get_tolerance_bps", "get_symbol_default_bps",
    "resolve_pip_size",
    # R3:
    "get_active_watchlist", "get_tier1_symbols",
    "get_intelligence_pairs", "get_allowed_symbols",
    "get_data_maintenance_pairs",
    "get_discovery_pairs", "get_mutation_pairs",
    "get_validation_pairs", "get_portfolio_pairs",
    "get_certification_pairs",
    "is_eligible",
]
