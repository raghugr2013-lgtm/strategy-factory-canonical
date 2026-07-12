"""R0 — Idempotent seed for the dynamic market_universe registry.

Populates ``market_universe_symbols`` with the 7 symbols that the
codebase currently treats as the operational universe. Every field is
byte-identical to the corresponding legacy constant:

* ``calendar.market_type / timezone`` ← ``config/symbols.py::SYMBOL_CONFIG``
* ``broker_mapping.dukascopy_slug`` ← ``config/bi5_symbols.py::_BI5_SYMBOL_SPECS.url_slug``
* ``broker_mapping.dukascopy_instrument_id`` ← ``data_engine/dukascopy_downloader.py::INSTRUMENT_MAP``
* ``precision.price_multiplier`` ← ``config/bi5_symbols.py``
* ``precision.quote_decimals`` ← ``config/bi5_symbols.py``
* ``precision.pip_size`` ← derived (JPY→0.01, XAU→0.1, US100→0.01, BTC/ETH→0.01, else 0.0001)
* ``spread_defaults.tolerance_bps`` ← ``engines/spread_analyzer.py::DEFAULT_TOLERANCE_BPS``
* ``spread_defaults.symbol_default_bps`` ← ``engines/spread_analyzer.py::SYMBOL_DEFAULT_BPS``
* ``cert_defaults.density_table`` ← ``engines/tick_validator.py::DENSITY_TABLE``
* ``aliases`` — ``NAS100`` registered as an alias of ``US100``

The seed is **idempotent**:
* ``upsert_symbol`` keys on ``(symbol, broker_class)``.
* ``$setOnInsert`` preserves ``created_at`` / ``created_by`` across
  re-seeds.
* Operator-modified fields are NOT overwritten — the seeder only
  re-applies the canonical defaults if the row is missing or carries
  ``is_seed=true`` AND has never been operator-touched. (See
  ``_should_apply_seed_payload``.)

The seed also writes a single baseline audit row per symbol on first
insert (``action="seed_baseline"``) per approved decision §7.4 of the
design document.

Discipline
----------
* **Never raises.** Seed failure is logged but never blocks startup.
* **No flag flip.** Seeding happens regardless of
  ``ENABLE_DYNAMIC_MARKET_UNIVERSE``; the flag still gates *consumption*.
* **No engine consults this.** Pure data — runtime adapters are R1+.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from engines import market_universe as MU
from engines.db import get_db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Canonical defaults — byte-identical to legacy constants.
# DO NOT EDIT without an R0 follow-up; these are the parity contract.
# ─────────────────────────────────────────────────────────────────────

_FX_DENSITY_DEFAULT = {
    "asia":    [500, 3000],
    "london":  [2000, 12000],
    "ny":      [2500, 15000],
    "overlap": [2500, 15000],
}

# Per-symbol byte-identical values mirroring:
#   engines/tick_validator.DENSITY_TABLE
#   engines/spread_analyzer.{DEFAULT_TOLERANCE_BPS, SYMBOL_DEFAULT_BPS}
#   config/bi5_symbols._BI5_SYMBOL_SPECS
#   config/symbols.SYMBOL_CONFIG
#   data_engine/dukascopy_downloader.INSTRUMENT_MAP (id token names)
SEED_SYMBOLS: List[Dict[str, Any]] = [
    {
        "symbol":        "EURUSD",
        "broker_class":  "dukascopy",
        "display_name":  "EUR/USD",
        "asset_class":   "fx_major",
        "tier":          "candidate",
        "enabled":       True,
        "priority":      900,
        "compute_cost_hint": "low",
        "pip_size":      0.0001,
        "aliases":       [],
        "tags":          ["major", "fx"],
        "source":        "imported",
        "is_seed":       True,
        "calendar":      {"market_type": "forex", "timezone": "UTC"},
        "broker_mapping": {
            "dukascopy_slug":          "EURUSD",
            "dukascopy_instrument_id": "INSTRUMENT_FX_MAJORS_EUR_USD",
        },
        "precision":     {
            "price_multiplier": 1e5,
            "quote_decimals":   5,
            "pip_size":         0.0001,
        },
        "spread_defaults": {"tolerance_bps": 1.0, "symbol_default_bps": 0.8},
        "cert_defaults":   {"density_table": {
            "asia":    [1000, 6000],
            "london":  [5000, 25000],
            "ny":      [6000, 30000],
            "overlap": [6000, 30000],
        }},
        "eligibility": {
            "ingestion_enabled":      True,
            "validation_enabled":     True,
            "discovery_enabled":      True,
            "mutation_enabled":       True,
            "certification_enabled":  True,
            "portfolio_enabled":      True,
            "live_trading_enabled":   False,
        },
    },
    {
        "symbol":        "GBPUSD",
        "broker_class":  "dukascopy",
        "display_name":  "GBP/USD",
        "asset_class":   "fx_major",
        "tier":          "candidate",
        "enabled":       True,
        "priority":      850,
        "compute_cost_hint": "low",
        "pip_size":      0.0001,
        "tags":          ["major", "fx"],
        "source":        "imported",
        "is_seed":       True,
        "calendar":      {"market_type": "forex", "timezone": "UTC"},
        "broker_mapping": {
            "dukascopy_slug":          "GBPUSD",
            "dukascopy_instrument_id": "INSTRUMENT_FX_MAJORS_GBP_USD",
        },
        "precision":     {
            "price_multiplier": 1e5,
            "quote_decimals":   5,
            "pip_size":         0.0001,
        },
        "spread_defaults": {"tolerance_bps": 1.0, "symbol_default_bps": 1.0},
        "cert_defaults":   {"density_table": {
            "asia":    [800,  4000],
            "london":  [4000, 20000],
            "ny":      [5000, 24000],
            "overlap": [5000, 24000],
        }},
        "eligibility": {
            "ingestion_enabled":      True,
            "validation_enabled":     True,
            "discovery_enabled":      True,
            "mutation_enabled":       True,
            "certification_enabled":  True,
            "portfolio_enabled":      True,
            "live_trading_enabled":   False,
        },
    },
    {
        "symbol":        "USDJPY",
        "broker_class":  "dukascopy",
        "display_name":  "USD/JPY",
        "asset_class":   "fx_major",
        "tier":          "candidate",
        "enabled":       True,
        "priority":      800,
        "compute_cost_hint": "low",
        "pip_size":      0.01,
        "tags":          ["major", "fx", "jpy"],
        "source":        "imported",
        "is_seed":       True,
        "calendar":      {"market_type": "forex", "timezone": "UTC"},
        "broker_mapping": {
            "dukascopy_slug":          "USDJPY",
            "dukascopy_instrument_id": "INSTRUMENT_FX_MAJORS_USD_JPY",
        },
        "precision":     {
            "price_multiplier": 1e3,
            "quote_decimals":   3,
            "pip_size":         0.01,
        },
        "spread_defaults": {"tolerance_bps": 1.2, "symbol_default_bps": 1.0},
        "cert_defaults":   {"density_table": {
            "asia":    [3000, 14000],
            "london":  [3000, 14000],
            "ny":      [4000, 18000],
            "overlap": [4000, 18000],
        }},
        "eligibility": {
            "ingestion_enabled":      True,
            "validation_enabled":     True,
            "discovery_enabled":      True,
            "mutation_enabled":       False,
            "certification_enabled":  False,
            # D5 (R5 Phase-2 prep, 2026-06-04): preserve legacy parity —
            # USDJPY was historically in `data_maintenance.DEFAULT_PAIRS`
            # (the 4-major set) and therefore visible in the portfolio
            # picker. Keeping that visibility through the initial
            # market_universe promotion. Operator may revisit later.
            "portfolio_enabled":      True,
            "live_trading_enabled":   False,
        },
    },
    {
        "symbol":        "XAUUSD",
        "broker_class":  "dukascopy",
        "display_name":  "XAU/USD (Gold)",
        "asset_class":   "commodity_metal",
        "tier":          "candidate",
        "enabled":       True,
        "priority":      750,
        "compute_cost_hint": "medium",
        "pip_size":      0.1,
        "aliases":       ["GOLD"],
        "tags":          ["metal", "commodity"],
        "source":        "imported",
        "is_seed":       True,
        "calendar":      {"market_type": "forex", "timezone": "UTC"},
        "broker_mapping": {
            "dukascopy_slug":          "XAUUSD",
            "dukascopy_instrument_id": "INSTRUMENT_FX_METALS_XAU_USD",
        },
        "precision":     {
            "price_multiplier": 1e3,
            "quote_decimals":   3,
            "pip_size":         0.1,
        },
        "spread_defaults": {"tolerance_bps": 5.0, "symbol_default_bps": 8.0},
        "cert_defaults":   {"density_table": {
            "asia":    [500,  3000],
            "london":  [3000, 16000],
            "ny":      [4000, 20000],
            "overlap": [4000, 20000],
        }},
        "eligibility": {
            "ingestion_enabled":      True,
            "validation_enabled":     True,
            "discovery_enabled":      True,
            "mutation_enabled":       True,
            "certification_enabled":  True,
            "portfolio_enabled":      True,
            "live_trading_enabled":   False,
        },
    },
    {
        # Canonical "US100"; legacy "NAS100" registered as alias to allow
        # the auto_factory.UNIVERSE_PAIRS naming drift to resolve.
        "symbol":        "US100",
        "broker_class":  "dukascopy",
        "display_name":  "US Nasdaq 100",
        "asset_class":   "index",
        "tier":          "candidate",
        "enabled":       True,
        "priority":      600,
        "compute_cost_hint": "medium",
        # D7 (R5 Phase-2 prep, 2026-06-04): pip_size pinned to 0.0001
        # to preserve legacy substring-resolver behaviour for the
        # initial market_universe flip. The physically correct value
        # (0.01) is deferred to a dedicated recalibration project so
        # the flag flip does not change BTC/ETH/index PnL math.
        "pip_size":      0.0001,
        "aliases":       ["NAS100"],
        "tags":          ["index", "us"],
        "source":        "imported",
        "is_seed":       True,
        "calendar":      {"market_type": "forex", "timezone": "UTC"},
        "broker_mapping": {
            "dukascopy_slug":          "NASUSD",
            "dukascopy_instrument_id": "INSTRUMENT_IDX_AMERICA_E_NQ_100",
        },
        "precision":     {
            "price_multiplier": 1e2,
            "quote_decimals":   2,
            # D7 — see comment above. 0.0001 preserves legacy PnL math.
            "pip_size":         0.0001,
        },
        "spread_defaults": {"tolerance_bps": 2.0, "symbol_default_bps": 2.0},
        "cert_defaults":   {"density_table": dict(_FX_DENSITY_DEFAULT)},
        "eligibility": {
            "ingestion_enabled":      True,
            "validation_enabled":     True,
            "discovery_enabled":      False,
            "mutation_enabled":       False,
            "certification_enabled":  False,
            "portfolio_enabled":      False,
            "live_trading_enabled":   False,
        },
    },
    {
        "symbol":        "BTCUSD",
        "broker_class":  "dukascopy",
        "display_name":  "BTC/USD",
        "asset_class":   "crypto",
        "tier":          "candidate",
        "enabled":       True,
        "priority":      500,
        "compute_cost_hint": "medium",
        # D7 (R5 Phase-2 prep, 2026-06-04): pip_size pinned to 0.0001
        # to preserve legacy substring-resolver behaviour during the
        # initial market_universe flip.
        "pip_size":      0.0001,
        "tags":          ["crypto"],
        "source":        "imported",
        "is_seed":       True,
        "calendar":      {"market_type": "crypto", "timezone": "UTC"},
        "broker_mapping": {
            "dukascopy_slug":          "BTCUSD",
            "dukascopy_instrument_id": "INSTRUMENT_VCCY_BTC_USD",
        },
        "precision":     {
            "price_multiplier": 1e3,
            "quote_decimals":   3,
            # D7 — see comment above.
            "pip_size":         0.0001,
        },
        "spread_defaults": {"tolerance_bps": 2.0, "symbol_default_bps": 2.0},
        "cert_defaults":   {"density_table": dict(_FX_DENSITY_DEFAULT)},
        "eligibility": {
            "ingestion_enabled":      True,
            "validation_enabled":     True,
            "discovery_enabled":      False,
            "mutation_enabled":       False,
            "certification_enabled":  False,
            "portfolio_enabled":      False,
            "live_trading_enabled":   False,
        },
    },
    {
        "symbol":        "ETHUSD",
        "broker_class":  "dukascopy",
        "display_name":  "ETH/USD",
        "asset_class":   "crypto",
        "tier":          "candidate",
        "enabled":       True,
        "priority":      490,
        "compute_cost_hint": "medium",
        # D7 (R5 Phase-2 prep, 2026-06-04): pip_size pinned to 0.0001
        # to preserve legacy substring-resolver behaviour during the
        # initial market_universe flip.
        "pip_size":      0.0001,
        "tags":          ["crypto"],
        "source":        "imported",
        "is_seed":       True,
        "calendar":      {"market_type": "crypto", "timezone": "UTC"},
        "broker_mapping": {
            "dukascopy_slug":          "ETHUSD",
            "dukascopy_instrument_id": "INSTRUMENT_VCCY_ETH_USD",
        },
        "precision":     {
            "price_multiplier": 1e3,
            "quote_decimals":   3,
            # D7 — see comment above.
            "pip_size":         0.0001,
        },
        "spread_defaults": {"tolerance_bps": 2.0, "symbol_default_bps": 2.0},
        "cert_defaults":   {"density_table": dict(_FX_DENSITY_DEFAULT)},
        "eligibility": {
            "ingestion_enabled":      True,
            "validation_enabled":     True,
            "discovery_enabled":      False,
            "mutation_enabled":       False,
            "certification_enabled":  False,
            "portfolio_enabled":      False,
            "live_trading_enabled":   False,
        },
    },
]


def _should_apply_seed_payload(prior: Dict[str, Any]) -> bool:
    """Decide whether re-seed should overwrite an existing row.

    Rule: only re-apply the canonical seed payload when:
      * the row is missing (``prior is None`` — handled by upsert), OR
      * the row carries ``is_seed=true`` AND ``updated_by`` is
        ``"r0_seed"`` (i.e. operator never touched it).

    Any operator edit changes ``updated_by``; once that happens, the
    seed becomes a no-op for that row.
    """
    if not prior:
        return True
    if not prior.get("is_seed"):
        return False
    return (prior.get("updated_by") or "").strip() == "r0_seed"


async def run_market_universe_seed() -> Dict[str, Any]:
    """Seed the 7 canonical symbols. Idempotent and operator-safe.

    Returns a structured summary suitable for logging / a diagnostic
    endpoint. Never raises.
    """
    db = get_db()
    inserted: List[str] = []
    refreshed: List[str] = []
    skipped: List[str] = []
    errors: List[Dict[str, str]] = []

    for row in SEED_SYMBOLS:
        sym = row["symbol"]
        bc = row.get("broker_class", "dukascopy")
        try:
            prior = await db[MU.COLL].find_one(
                {"symbol": sym, "broker_class": bc}, {"_id": 0},
            )
            if prior is None:
                payload = dict(row)
                payload["updated_by"] = "r0_seed"
                await MU.upsert_symbol(**payload)
                inserted.append(sym)
            elif _should_apply_seed_payload(prior):
                payload = dict(row)
                payload["updated_by"] = "r0_seed"
                await MU.upsert_symbol(**payload)
                refreshed.append(sym)
            else:
                skipped.append(sym)
        except Exception as e:                              # pragma: no cover
            errors.append({"symbol": sym, "error": str(e)[:200]})
            logger.warning("[market_universe_seed] %s failed: %s", sym, e)

    summary = {
        "phase":     "R0",
        "inserted":  inserted,
        "refreshed": refreshed,
        "skipped":   skipped,
        "errors":    errors,
        "total":     len(SEED_SYMBOLS),
    }
    logger.info(
        "[market_universe_seed] done — inserted=%d refreshed=%d skipped=%d errors=%d",
        len(inserted), len(refreshed), len(skipped), len(errors),
    )
    return summary


__all__ = ["SEED_SYMBOLS", "run_market_universe_seed"]
