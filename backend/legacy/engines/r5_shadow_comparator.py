"""R5 — Shadow comparator (read-only).

Compares the *legacy* authority against the *registry-backed* authority
across every adapter surface promoted in R1/R2/R3 and the frontend
selectors promoted in R4.

This is a **read-only diagnostic**. It never flips
``ENABLE_DYNAMIC_MARKET_UNIVERSE`` at the process level — it instead
toggles the adapter's flag via the standard env-var contract for the
duration of the comparison, then restores the prior value.

Out of scope (per R5 boundary):
  * scheduler redesign
  * VPS-aware scaling
  * activation matrix
  * factory supervisor
  * flipping the production flag

Public entry point
------------------
``run_shadow_comparison(seeded_db)`` — given a Mongo (or mongomock) DB
that already holds the seeded ``market_universe_symbols`` collection,
return a structured delta report.

The report shape is:

    {
      "flag_state_before": bool,
      "flag_state_after":  bool,
      "cache_size":        int,
      "groups": [
        {
          "name":      str,
          "scope":     str,   # symbol_list | bi5 | instrument | eligibility | cert_defaults | frontend
          "ok":        bool,
          "checks":    [ {"name": str, "ok": bool,
                           "legacy": Any, "shadow": Any, "delta": Any } ],
        },
        ...
      ],
      "summary": {
        "total_checks":     int,
        "ok":               int,
        "mismatches":       int,
        "groups_with_diff": [str, ...],
      },
    }
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List


FLAG_ENV = "ENABLE_DYNAMIC_MARKET_UNIVERSE"
CANONICAL_7 = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD")


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
@contextmanager
def _flag_on():
    """Temporarily flip the flag ON for the comparator only. Restores
    the original env value on exit. **Never persists to .env.**"""
    prior = os.environ.get(FLAG_ENV)
    os.environ[FLAG_ENV] = "1"
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop(FLAG_ENV, None)
        else:
            os.environ[FLAG_ENV] = prior


@contextmanager
def _flag_off():
    prior = os.environ.get(FLAG_ENV)
    os.environ.pop(FLAG_ENV, None)
    try:
        yield
    finally:
        if prior is not None:
            os.environ[FLAG_ENV] = prior


def _eq(a: Any, b: Any) -> bool:
    """Tolerant equality:
        * lists/tuples are compared as sequences (order matters)
        * sets/frozensets/dicts are compared as-is
        * floats with abs diff < 1e-9 are considered equal
    """
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) < 1e-9
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_eq(x, y) for x, y in zip(a, b))
    return a == b


def _delta(legacy: Any, shadow: Any) -> Any:
    """Human-readable delta description (returned only when not equal)."""
    if _eq(legacy, shadow):
        return None
    if isinstance(legacy, (list, tuple)) and isinstance(shadow, (list, tuple)):
        ls, ss = set(legacy), set(shadow)
        return {
            "missing_in_shadow": sorted(ls - ss),
            "extra_in_shadow":   sorted(ss - ls),
            "order_changed":     ls == ss,
        }
    return {"legacy": legacy, "shadow": shadow}


def _run_check(
    name: str,
    legacy_fn: Callable[[], Any],
    shadow_fn: Callable[[], Any],
) -> Dict[str, Any]:
    try:
        legacy = legacy_fn()
    except Exception as e:                                   # pragma: no cover
        legacy = f"<error: {e}>"
    try:
        shadow = shadow_fn()
    except Exception as e:                                   # pragma: no cover
        shadow = f"<error: {e}>"
    ok = _eq(legacy, shadow)
    return {
        "name":   name,
        "ok":     ok,
        "legacy": legacy,
        "shadow": shadow,
        "delta":  None if ok else _delta(legacy, shadow),
    }


async def _populate_cache_from_db() -> int:
    """Pull rows from the seeded registry and load them into the adapter
    cache. Returns the row count."""
    from engines import market_universe as MU
    from engines import market_universe_adapter as ADAPTER
    rows = await MU.list_symbols(limit=2000)
    ADAPTER.set_registry_cache(rows)
    return len(rows)


def _cached_rows():
    """Snapshot of the current adapter cache for re-seeding between
    flag flips. Kept module-level so the sync comparator groups can
    restore the cache after each `_flag_off()` block that clears it."""
    from engines import market_universe_adapter as ADAPTER
    with ADAPTER._cache_lock:  # noqa: SLF001 (read-only snapshot)
        return [dict(r) for r in ADAPTER._REGISTRY_CACHE.values()]


# ─────────────────────────────────────────────────────────────────────
# Comparator groups
# ─────────────────────────────────────────────────────────────────────
def _group_symbol_lists() -> Dict[str, Any]:
    """R3 eligibility-aware symbol-set accessors."""
    from engines import market_universe_adapter as ADAPTER

    accessors = [
        ("get_allowed_symbols",        ADAPTER.get_allowed_symbols),
        ("get_active_watchlist",       ADAPTER.get_active_watchlist),
        ("get_tier1_symbols",          ADAPTER.get_tier1_symbols),
        ("get_intelligence_pairs",     ADAPTER.get_intelligence_pairs),
        ("get_data_maintenance_pairs", ADAPTER.get_data_maintenance_pairs),
        ("get_discovery_pairs",        ADAPTER.get_discovery_pairs),
        ("get_mutation_pairs",         ADAPTER.get_mutation_pairs),
        ("get_validation_pairs",       ADAPTER.get_validation_pairs),
        ("get_portfolio_pairs",        ADAPTER.get_portfolio_pairs),
        ("get_certification_pairs",    ADAPTER.get_certification_pairs),
    ]
    seeded = _cached_rows()
    checks = []
    for name, fn in accessors:
        # Legacy path: flag OFF + empty cache so the registry is
        # *guaranteed* to be bypassed.
        with _flag_off():
            ADAPTER.clear_registry_cache()
            legacy_val = sorted(fn())
        # Shadow path: re-seed the cache, flag ON, capture the
        # registry-driven authority.
        ADAPTER.set_registry_cache(seeded)
        with _flag_on():
            shadow_val = sorted(fn())
        ok = _eq(legacy_val, shadow_val)
        checks.append({
            "name":   name,
            "ok":     ok,
            "legacy": legacy_val,
            "shadow": shadow_val,
            "delta":  None if ok else _delta(legacy_val, shadow_val),
        })
    # Restore the seeded cache for downstream groups.
    ADAPTER.set_registry_cache(seeded)
    return _wrap_group("symbol_lists", "symbol_list", checks)


def _group_bi5_mappings() -> Dict[str, Any]:
    """R1 BI5 spec / supported / list mappings."""
    from engines import market_universe_adapter as ADAPTER

    checks: List[Dict[str, Any]] = []

    # list_bi5_symbols equality
    with _flag_off():
        legacy_list = ADAPTER.list_bi5_symbols()
    with _flag_on():
        shadow_list = ADAPTER.list_bi5_symbols()
    checks.append({
        "name":   "list_bi5_symbols",
        "ok":     _eq(legacy_list, shadow_list),
        "legacy": legacy_list,
        "shadow": shadow_list,
        "delta":  None if _eq(legacy_list, shadow_list) else _delta(legacy_list, shadow_list),
    })

    # Per-symbol get_bi5_symbol_spec must produce identical field set.
    fields = ("symbol", "url_slug", "price_multiplier", "quote_decimals", "market_type")
    for sym in CANONICAL_7:
        with _flag_off():
            try:
                lg = ADAPTER.get_bi5_symbol_spec(sym)
                lg_dict = {f: getattr(lg, f) for f in fields}
            except KeyError:
                lg_dict = None
        with _flag_on():
            try:
                sh = ADAPTER.get_bi5_symbol_spec(sym)
                sh_dict = {f: getattr(sh, f) for f in fields}
            except KeyError:
                sh_dict = None
        ok = _eq(lg_dict, sh_dict)
        checks.append({
            "name":   f"get_bi5_symbol_spec({sym})",
            "ok":     ok,
            "legacy": lg_dict,
            "shadow": sh_dict,
            "delta":  None if ok else _delta(lg_dict, sh_dict),
        })

    # is_bi5_supported for canonical + NAS100 alias.
    for sym in list(CANONICAL_7) + ["NAS100", "GOLD"]:
        with _flag_off():
            lg = ADAPTER.is_bi5_supported(sym)
        with _flag_on():
            sh = ADAPTER.is_bi5_supported(sym)
        ok = (lg == sh)
        checks.append({
            "name":   f"is_bi5_supported({sym})",
            "ok":     ok,
            "legacy": lg,
            "shadow": sh,
            "delta":  None if ok else {"legacy": lg, "shadow": sh},
        })
    return _wrap_group("bi5_mappings", "bi5", checks)


def _group_instrument_mappings() -> Dict[str, Any]:
    """R1 Dukascopy instrument enum resolution. Identity-compares the
    resolved enum object across flag states.
    """
    from engines import market_universe_adapter as ADAPTER
    checks: List[Dict[str, Any]] = []
    for sym in list(CANONICAL_7) + ["NAS100"]:
        with _flag_off():
            try:
                lg = ADAPTER.resolve_dukascopy_instrument(sym)
            except Exception as e:                            # pragma: no cover
                lg = f"<err: {e}>"
        with _flag_on():
            try:
                sh = ADAPTER.resolve_dukascopy_instrument(sym)
            except Exception as e:                            # pragma: no cover
                sh = f"<err: {e}>"
        ok = (lg is sh) or (lg == sh)
        checks.append({
            "name":   f"resolve_dukascopy_instrument({sym})",
            "ok":     ok,
            "legacy": repr(lg),
            "shadow": repr(sh),
            "delta":  None if ok else {"legacy": repr(lg), "shadow": repr(sh)},
        })
    return _wrap_group("instrument_mappings", "instrument", checks)


def _group_eligibility() -> Dict[str, Any]:
    """is_eligible(symbol, capability) parity across canonical and
    alias inputs."""
    from engines import market_universe_adapter as ADAPTER

    capabilities = [
        "ingestion", "discovery", "mutation",
        "validation", "certification", "portfolio", "live_trading",
    ]
    inputs = list(CANONICAL_7) + ["NAS100"]
    checks: List[Dict[str, Any]] = []
    for sym in inputs:
        for cap in capabilities:
            with _flag_off():
                lg = ADAPTER.is_eligible(sym, capability=cap)
            with _flag_on():
                sh = ADAPTER.is_eligible(sym, capability=cap)
            ok = (lg == sh)
            checks.append({
                "name":   f"is_eligible({sym}, {cap})",
                "ok":     ok,
                "legacy": lg,
                "shadow": sh,
                "delta":  None if ok else {"legacy": lg, "shadow": sh},
            })
    return _wrap_group("eligibility", "eligibility", checks)


def _group_cert_defaults() -> Dict[str, Any]:
    """R2 certification-defaults adapters: density_table, tolerance_bps,
    symbol_default_bps, pip_size resolver.
    """
    from engines import market_universe_adapter as ADAPTER

    checks: List[Dict[str, Any]] = []
    sessions = ("asia", "london", "ny", "overlap")
    for sym in CANONICAL_7:
        for sess in sessions:
            with _flag_off():
                lg = ADAPTER.get_density_table(sym, sess)
            with _flag_on():
                sh = ADAPTER.get_density_table(sym, sess)
            ok = _eq(lg, sh)
            checks.append({
                "name":   f"get_density_table({sym}, {sess})",
                "ok":     ok,
                "legacy": lg,
                "shadow": sh,
                "delta":  None if ok else _delta(lg, sh),
            })
        for fn_name, fn in [
            ("get_tolerance_bps",      ADAPTER.get_tolerance_bps),
            ("get_symbol_default_bps", ADAPTER.get_symbol_default_bps),
        ]:
            with _flag_off():
                lg = fn(sym)
            with _flag_on():
                sh = fn(sym)
            ok = _eq(lg, sh)
            checks.append({
                "name":   f"{fn_name}({sym})",
                "ok":     ok,
                "legacy": lg,
                "shadow": sh,
                "delta":  None if ok else _delta(lg, sh),
            })
        # pip_size resolver (with the flag OFF, the registry is
        # intentionally bypassed per R2 design — see adapter docstring.
        # We still compare the two paths to flag any drift). The
        # adapter explicitly designs *flag-OFF* and *flag-ON* to differ
        # for BTC/ETH/US100, so we record the delta here without
        # failing the audit gate.
        with _flag_off():
            lg = ADAPTER.resolve_pip_size(sym)
        with _flag_on():
            sh = ADAPTER.resolve_pip_size(sym)
        checks.append({
            "name":   f"resolve_pip_size({sym})",
            "ok":     _eq(lg, sh),
            "legacy": lg,
            "shadow": sh,
            "delta":  None if _eq(lg, sh) else _delta(lg, sh),
            "advisory": (
                "Per R2 design: flag-OFF uses the substring resolver "
                "(0.0001 for BTC/ETH/US100); flag-ON uses the registry "
                "precision (0.01). Documented in market_universe_adapter."
            ),
        })
    return _wrap_group("cert_defaults", "cert_defaults", checks)


def _group_frontend_selectors() -> Dict[str, Any]:
    """R4 — frontend hook fallback constants must equal backend authority.
    Parses the JS source statically so we don't need a JS runtime.
    """
    hook_path = Path("/app/frontend/src/hooks/useMarketUniverse.js")
    text = hook_path.read_text(encoding="utf-8")

    array_re = re.compile(
        r"(?:export\s+)?const\s+(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*\[(?P<body>[^\]]*)\]",
        re.DOTALL,
    )
    string_re = re.compile(r"['\"]([A-Z0-9]{3,12})['\"]")

    def _extract(name: str) -> List[str]:
        for m in array_re.finditer(text):
            if m.group("name") == name:
                return string_re.findall(m.group("body"))
        return []

    pairs = {
        "LEGACY_PAIRS":         "ALLOWED_SYMBOLS (api.data)",
        "LEGACY_TIER1":         "TIER1_SYMBOLS (readiness_engine)",
        "LEGACY_DISCOVERY":     "DEFAULT_PAIRS (auto_factory_engine)",
        "LEGACY_MUTATION":      "DEFAULT_PAIRS (auto_factory_engine)",
        "LEGACY_PORTFOLIO":     "DEFAULT_PAIRS (data_maintenance)",
        "LEGACY_CERTIFICATION": "DEFAULT_PAIRS (market_intelligence)",
    }

    from api import data as DATA_API
    from engines import readiness_engine as RE
    from engines import auto_factory_engine as AFE
    from engines import market_intelligence as MI
    from data_engine import data_maintenance as DM

    backend = {
        "LEGACY_PAIRS":         sorted(DATA_API.ALLOWED_SYMBOLS),
        "LEGACY_TIER1":         sorted(RE.TIER1_SYMBOLS),
        "LEGACY_DISCOVERY":     sorted(AFE.DEFAULT_PAIRS),
        "LEGACY_MUTATION":      sorted(AFE.DEFAULT_PAIRS),
        "LEGACY_PORTFOLIO":     sorted(DM.DEFAULT_PAIRS),
        "LEGACY_CERTIFICATION": sorted(MI.DEFAULT_PAIRS),
    }
    checks: List[Dict[str, Any]] = []
    for js_const, backend_label in pairs.items():
        js_vals = sorted(_extract(js_const))
        be_vals = backend[js_const]
        ok = _eq(js_vals, be_vals)
        checks.append({
            "name":   f"{js_const} ≡ {backend_label}",
            "ok":     ok,
            "legacy": be_vals,
            "shadow": js_vals,
            "delta":  None if ok else _delta(be_vals, js_vals),
        })

    # Hook must call the same endpoint the audit consults.
    checks.append({
        "name":   "hook consumes /api/latent/market-universe",
        "ok":     "/api/latent/market-universe" in text,
        "legacy": "/api/latent/market-universe",
        "shadow": "/api/latent/market-universe" in text,
        "delta":  None,
    })
    return _wrap_group("frontend_selectors", "frontend", checks)


def _wrap_group(name: str, scope: str, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "name":   name,
        "scope":  scope,
        "ok":     all(c["ok"] for c in checks),
        "checks": checks,
    }


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────
async def run_shadow_comparison() -> Dict[str, Any]:
    """Run every comparator group against the seeded registry.

    Caller must have:
      1. patched ``engines.db.get_db`` to point at a seeded mongomock/Mongo
      2. run ``market_universe_seed.run_market_universe_seed()`` to
         populate the 7 canonical rows.

    Returns the structured report described in the module docstring.
    """

    flag_before = os.environ.get(FLAG_ENV, "")
    cache_size = await _populate_cache_from_db()

    groups = [
        _group_symbol_lists(),
        _group_bi5_mappings(),
        _group_instrument_mappings(),
        _group_eligibility(),
        _group_cert_defaults(),
        _group_frontend_selectors(),
    ]

    total = sum(len(g["checks"]) for g in groups)
    ok = sum(sum(1 for c in g["checks"] if c["ok"]) for g in groups)
    mismatches = total - ok
    diff_groups = [g["name"] for g in groups if not g["ok"]]

    flag_after = os.environ.get(FLAG_ENV, "")
    return {
        "flag_state_before": flag_before,
        "flag_state_after":  flag_after,
        "flag_persisted":    flag_before == flag_after,
        "cache_size":        cache_size,
        "groups":            groups,
        "summary": {
            "total_checks":     total,
            "ok":               ok,
            "mismatches":       mismatches,
            "groups_with_diff": diff_groups,
        },
    }


__all__ = ["run_shadow_comparison", "FLAG_ENV", "CANONICAL_7"]
