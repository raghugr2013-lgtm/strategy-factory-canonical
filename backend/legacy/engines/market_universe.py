"""
P1.6 — Dormant dynamic market-universe registry.

Status
------
* DORMANT BY DEFAULT. Gated by ``ENABLE_DYNAMIC_MARKET_UNIVERSE``
  (default ``False``). Even when the flag is ON, **no production code
  path consults this registry**.
* Activation requires BOTH the flag flip AND a deliberate future
  code change to wire a call-site (ingestion / mutation / explorer /
  replay / parity / orchestration). Statically enforced by
  ``tests/test_market_universe.py::test_no_engine_consumer``.

Purpose
-------
Operator-extensible registry of broker-supported symbols. Today's
``engines.governance_universe`` decrees ALLOWED SETS (pairs × TFs ×
styles) but knows nothing about *which* broker, *what* pip size, or
*how compute-expensive* a symbol is to backtest. This module fills
that gap WITHOUT touching governance_universe — it sits beside it
as a finer-grained per-symbol catalogue.

Tiers (operator-decreed lifecycle states)
-----------------------------------------
* ``active``           — In live deployment rotation. Operators have
                         decreed real money may trade this symbol.
                         Default empty — no symbol is promoted to
                         active without explicit operator action.
* ``candidate``        — Operator-approved for discovery / mutation /
                         backtesting but NOT for live deployment yet.
                         New symbols default here (configurable via
                         ``MARKET_UNIVERSE_DEFAULT_TIER``).
* ``dormant``          — Registered but temporarily paused (e.g.
                         broker spec verification pending, low data,
                         operator manual override).
* ``experimental``     — Operator wants to test discovery on this
                         symbol with EXTRA exploration budget but
                         doesn't trust it enough for ``candidate``.
* ``regime_activated`` — FUTURE: only enters rotation when a regime
                         classifier asserts a matching market state.
                         The ``regime_gate`` field carries the
                         predicate; today it is documentation-only.

Schema
------
``market_universe_symbols`` collection. Composite unique key:
``(symbol_norm, broker_class)``.

::

    {
      symbol:                str,    # canonical normalised key (uppercase, no sep)
      aliases:               [str],  # alternative names — "GOLD", "XRP/USD" etc.
      broker_class:          str,    # "dukascopy" | "tier1_ecn" | "<broker>"
      display_name:          str,    # human label — "EUR/USD"
      asset_class:           str,    # fx_major | fx_cross | fx_exotic | crypto | index | commodity_metal | commodity_energy | stock
      tier:                  str,    # active | candidate | dormant | experimental | regime_activated
      enabled:               bool,   # quick on/off without removing the row
      priority:              int,    # 0-1000 — for future rotational / replay sort
      exploration_budget_pct: float, # 0-100 — slice of future exploratory budget
      compute_cost_hint:     str,    # low | medium | high
      pip_size:              float,  # broker spec override; resolve_pip_size fallback when absent
      volume_min:            float,
      volume_step:           float,
      min_data_bars:         int,    # minimum bars required before strategies on this symbol are eligible
      notes:                 str | None,
      tags:                  [str],  # free-form ("major", "session-asia", "weekend-tradeable")
      source:                str,    # operator | broker_api | imported
      regime_gate:           dict | None,  # future: {regime: "trending", min_vol_percentile: 50}
      created_at:            ISO str,
      updated_at:            ISO str,
      updated_by:            str,
    }

Discipline
----------
* Read-only at the engine layer (no engine reads this module today).
* Mongo CRUD lives here; admin endpoints validate input.
* Pure helpers (``normalize_symbol``, ``exploration_budget_for``,
  ``compute_cost_hint_to_weight``) are safe to call from anywhere.
* No engine reads ``governance_universe`` *through* this registry
  either — the two surfaces remain independent.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)


COLL = "market_universe_symbols"

# R0 — companion audit collection. One row per write to ``COLL``.
# Retention is enforced by a TTL index in ``engines.db_indexes``
# (90-day default, see R0_COMPLETION_REPORT §3).
AUDIT_COLL = "market_universe_audit"

# ─── Tiers (operator-decreed lifecycle) ──────────────────────────────
VALID_TIERS = (
    "active", "candidate", "dormant", "experimental", "regime_activated",
)

# ─── R0 — Per-stage eligibility flags (independent, NOT collapsed
#     into ``tier``). See approved decision §7.2 in the design doc.
#     Defaults are conservative: only ingestion + validation are ON
#     for newly registered symbols. Operator promotes the others.
#
#     DSR-1 (2026-06-11) — added ``marketplace_enabled`` so the
#     Marketplace Layer (Phase 15) can list per-symbol availability
#     independently from live trading. The 4 operator-facing eligibility
#     buckets in the UI map onto these granular flags as follows:
#       Ingestion   →   ingestion_enabled
#       Factory     →   discovery_enabled || mutation_enabled
#       Validation  →   validation_enabled || certification_enabled
#       Marketplace →   marketplace_enabled
ELIGIBILITY_KEYS = (
    "discovery_enabled",
    "mutation_enabled",
    "certification_enabled",
    "live_trading_enabled",
    "portfolio_enabled",
    "ingestion_enabled",
    "validation_enabled",
    "marketplace_enabled",
)
DEFAULT_ELIGIBILITY: Dict[str, bool] = {
    "ingestion_enabled":      True,
    "validation_enabled":     True,
    "discovery_enabled":      False,
    "mutation_enabled":       False,
    "certification_enabled":  False,
    "portfolio_enabled":      False,
    "live_trading_enabled":   False,
    "marketplace_enabled":    False,
}

# ─── Asset classes (operator-tunable classification) ─────────────────
#
# DSR-1 (2026-06-11) — added ``cfd`` and ``futures`` so the operator
# can register custom CFD / futures contracts (e.g. US30, GER40,
# NAS100, oil futures) without code changes. The UI groups these into
# 6 high-level buckets: Forex (= fx_major | fx_cross | fx_exotic),
# Metal (= commodity_metal), Index, Crypto, CFD, Futures. The fine-
# grained sub-class lives behind a secondary dropdown on the form.
VALID_ASSET_CLASSES = (
    "fx_major", "fx_cross", "fx_exotic",
    "crypto",
    "index",
    "commodity_metal", "commodity_energy",
    "stock",
    "cfd",        # DSR-1 · CFDs that aren't already classified above
    "futures",    # DSR-1 · futures contracts (FX, commodities, indices)
    "other",
)

# ─── DSR-1 · Execution platform compatibility ───────────────────────
#
# Per-symbol multiselect declaring which execution platforms the
# operator has verified the symbol on. Strategies and Master Bots
# will later carry their own narrower compatibility lists; the
# intersection with this set decides whether deployment is allowed.
# Adding a new platform here is the ONLY code change required to
# onboard a new execution venue.
VALID_EXECUTION_PLATFORMS = (
    "ctrader",
    "mt4",
    "mt5",
    "matchtrader",
    "tradelocker",
    "dxtrade",
)


def normalize_execution_platforms(
    platforms: Optional[List[str]],
) -> List[str]:
    """Pure helper. Lowercases, strips, dedups, and drops unknowns.
    Returns a stable-sorted list so audit diffs are deterministic."""
    if not platforms:
        return []
    out: List[str] = []
    seen = set()
    for p in platforms:
        if not p:
            continue
        n = str(p).strip().lower().replace(" ", "").replace("-", "")
        if n in VALID_EXECUTION_PLATFORMS and n not in seen:
            seen.add(n)
            out.append(n)
    return sorted(out)


# ─── DSR-1 · Reserved future-phase compatibility fields ─────────────
#
# These five fields are RESERVED today — stored on the document as
# operator-supplied opaque dicts/lists but NOT validated, NOT
# consumed by any engine, and NOT surfaced in the UI. They are
# claimed by future phases (per `/app/memory/visual_approval_package/
# 10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md`):
#
#   broker_compatibility   →  Phase 14 Auto Valuation · per-broker
#                             spread / commission profiles
#   strategy_compatibility →  Phase 13 Strategy Dossier · which
#                             strategy archetypes are eligible
#   masterbot_compatibility→  Phase 14 · which Master Bot packs
#                             can include this symbol
#   marketplace_visibility →  Phase 15 Marketplace · public listing
#                             visibility rules (public / unlisted /
#                             cohort_only)
#   propfirm_eligibility   →  Phase 14 Dual Scorecard · per-firm
#                             eligibility map (FTMO / MFF / etc.)
#
# Storing them today (even as empty objects) guarantees zero schema
# migration cost when the future phases land.
RESERVED_FUTURE_FIELDS = (
    "broker_compatibility",
    "strategy_compatibility",
    "masterbot_compatibility",
    "marketplace_visibility",
    "propfirm_eligibility",
)

# ─── Compute-cost hints (for future compute-aware allocation) ────────
VALID_COMPUTE_HINTS = ("low", "medium", "high")

# Pure-function mapping consumed by future orchestrator passes. Today
# advisory-only — every caller is expected to read this lookup and
# act on it; the registry itself never throttles anything.
_COMPUTE_WEIGHT_BY_HINT = {"low": 1.0, "medium": 2.0, "high": 4.0}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Activation surface
# ─────────────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    """True iff ``ENABLE_DYNAMIC_MARKET_UNIVERSE`` is truthy.

    The registry is CALLABLE regardless — but production engines MUST
    consult this flag before substituting registry data for any
    hardcoded default (e.g. governance_universe.DEFAULT_PAIRS).
    """
    raw = os.environ.get("ENABLE_DYNAMIC_MARKET_UNIVERSE", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def default_tier() -> str:
    """Operator-configurable default tier for newly-registered symbols.

    Defaults to ``candidate`` — symbols are eligible for discovery /
    backtesting but never auto-promoted to ``active``.
    """
    raw = (os.environ.get("MARKET_UNIVERSE_DEFAULT_TIER", "") or "candidate").strip().lower()
    return raw if raw in VALID_TIERS else "candidate"


# ─────────────────────────────────────────────────────────────────────
# Normalisation (pure)
# ─────────────────────────────────────────────────────────────────────
_NORM_STRIP = re.compile(r"[^A-Z0-9]")


def normalize_symbol(symbol: str) -> str:
    """Canonical symbol form: uppercase + strip non-alphanumerics.

    Examples:
      "eur/usd"      → "EURUSD"
      "XRP-USD"      → "XRPUSD"
      "  NAS 100  "  → "NAS100"
      "us30.cash"    → "US30CASH"  (preserves vendor suffix)
    """
    if not symbol:
        return ""
    return _NORM_STRIP.sub("", str(symbol).upper())


def normalize_broker_class(broker_class: str) -> str:
    return (broker_class or "").strip().lower() or "unknown"


def normalize_tier(tier: str) -> str:
    t = (tier or "").strip().lower()
    return t if t in VALID_TIERS else default_tier()


def normalize_asset_class(asset_class: str) -> str:
    a = (asset_class or "").strip().lower()
    return a if a in VALID_ASSET_CLASSES else "other"


def normalize_compute_hint(hint: str) -> str:
    h = (hint or "").strip().lower()
    return h if h in VALID_COMPUTE_HINTS else "medium"


# R0 — eligibility normalisation (pure). Unknown keys are dropped; missing
# keys fall back to ``DEFAULT_ELIGIBILITY``. Truthy/falsy coerced to bool.
def normalize_eligibility(
    eligibility: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    out: Dict[str, bool] = dict(DEFAULT_ELIGIBILITY)
    if not eligibility:
        return out
    for k, v in eligibility.items():
        key = (k or "").strip().lower()
        if key in ELIGIBILITY_KEYS:
            out[key] = bool(v)
    return out


# ─────────────────────────────────────────────────────────────────────
# Read helpers (pure, never write)
# ─────────────────────────────────────────────────────────────────────
async def get_symbol(
    symbol: str, broker_class: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """Look up a single symbol row. Returns None when absent.

    Also matches against the ``aliases`` array so operator-typed
    "GOLD" resolves to the registered "XAUUSD" row when an alias is
    configured.
    """
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    try:
        doc = await db[COLL].find_one(
            {
                "$or": [
                    {"symbol": sym_n, "broker_class": bc_n},
                    {"aliases": sym_n, "broker_class": bc_n},
                ],
            },
            {"_id": 0},
        )
        return doc
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] get_symbol failed: %s", e)
        return None


async def list_symbols(
    *,
    tier: Optional[str] = None,
    asset_class: Optional[str] = None,
    broker_class: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {}
    if tier:
        q["tier"] = normalize_tier(tier)
    if asset_class:
        q["asset_class"] = normalize_asset_class(asset_class)
    if broker_class:
        q["broker_class"] = normalize_broker_class(broker_class)
    if enabled is not None:
        q["enabled"] = bool(enabled)
    limit = max(1, min(int(limit), 2000))
    try:
        cur = db[COLL].find(q, {"_id": 0}).sort(
            [("tier", 1), ("priority", -1), ("symbol", 1)],
        ).limit(limit)
        return [d async for d in cur]
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] list_symbols failed: %s", e)
        return []


async def count_by_tier() -> Dict[str, int]:
    """Forensic summary: count of rows per tier. Always returns the
    full tier set, with zeros for empty tiers.
    """
    db = get_db()
    out: Dict[str, int] = {t: 0 for t in VALID_TIERS}
    try:
        pipeline = [
            {"$group": {"_id": "$tier", "n": {"$sum": 1}}},
        ]
        async for row in db[COLL].aggregate(pipeline):
            tier_key = (row.get("_id") or "")
            if tier_key in out:
                out[tier_key] = int(row.get("n") or 0)
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] count_by_tier failed: %s", e)
    return out


# ─────────────────────────────────────────────────────────────────────
# Future-caller pure helpers
# ─────────────────────────────────────────────────────────────────────
def exploration_budget_for(tier: str) -> float:
    """Default exploration-budget percentages per tier.

    These are conservative starting points. Operators override on a
    per-symbol basis via the row's ``exploration_budget_pct`` field;
    this helper is the fallback when no per-row value is set.

    * ``active``           — 5% (most cycles go to refinement)
    * ``candidate``        — 25% (discovery sweet spot)
    * ``experimental``     — 50% (operator wants aggressive exploration)
    * ``regime_activated`` — 30% (regime-gated; spend on the right side
                             of the regime)
    * ``dormant``          — 0% (paused)
    """
    t = normalize_tier(tier)
    return {
        "active":           5.0,
        "candidate":        25.0,
        "experimental":     50.0,
        "regime_activated": 30.0,
        "dormant":          0.0,
    }.get(t, 25.0)


def compute_cost_hint_to_weight(hint: str) -> float:
    return _COMPUTE_WEIGHT_BY_HINT.get(normalize_compute_hint(hint), 2.0)


# ─────────────────────────────────────────────────────────────────────
# Write helpers (admin endpoint enforces auth)
# ─────────────────────────────────────────────────────────────────────
def _validate_payload(
    *,
    symbol: str,
    broker_class: str,
    asset_class: str,
    tier: str,
    priority: int,
    exploration_budget_pct: float,
    compute_cost_hint: str,
    pip_size: float,
    volume_min: float,
    volume_step: float,
    min_data_bars: int,
) -> None:
    if not symbol or not isinstance(symbol, str):
        raise ValueError("symbol: non-empty string required")
    if normalize_symbol(symbol) == "":
        raise ValueError("symbol: must contain at least one alphanumeric")
    if not broker_class or not isinstance(broker_class, str):
        raise ValueError("broker_class: non-empty string required")
    if tier not in VALID_TIERS:
        raise ValueError(
            f"tier: must be one of {sorted(VALID_TIERS)} (got {tier!r})"
        )
    if asset_class not in VALID_ASSET_CLASSES:
        raise ValueError(
            f"asset_class: must be one of {sorted(VALID_ASSET_CLASSES)} "
            f"(got {asset_class!r})"
        )
    if compute_cost_hint not in VALID_COMPUTE_HINTS:
        raise ValueError(
            f"compute_cost_hint: must be one of "
            f"{sorted(VALID_COMPUTE_HINTS)} (got {compute_cost_hint!r})"
        )
    if not (0 <= int(priority) <= 1000):
        raise ValueError(f"priority: 0..1000 (got {priority})")
    if not (0.0 <= float(exploration_budget_pct) <= 100.0):
        raise ValueError(
            f"exploration_budget_pct: 0.0..100.0 (got {exploration_budget_pct})"
        )
    for name, val in (
        ("pip_size",    pip_size),
        ("volume_min",  volume_min),
        ("volume_step", volume_step),
    ):
        if not isinstance(val, (int, float)) or val < 0:
            raise ValueError(f"{name}: non-negative numeric required (got {val})")
    if not isinstance(min_data_bars, int) or min_data_bars < 0:
        raise ValueError(f"min_data_bars: non-negative int required (got {min_data_bars})")


async def upsert_symbol(
    *,
    symbol: str,
    broker_class: str = "unknown",
    display_name: Optional[str] = None,
    asset_class: str = "other",
    tier: Optional[str] = None,
    enabled: bool = True,
    priority: int = 100,
    exploration_budget_pct: Optional[float] = None,
    compute_cost_hint: str = "medium",
    pip_size: float = 0.0,
    volume_min: float = 0.0,
    volume_step: float = 0.0,
    min_data_bars: int = 0,
    aliases: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    notes: Optional[str] = None,
    source: str = "operator",
    regime_gate: Optional[Dict[str, Any]] = None,
    updated_by: str = "<unknown>",
    # ─── R0 additions (all optional, backwards-compatible) ────────────
    broker_mapping:    Optional[Dict[str, Any]] = None,
    precision:         Optional[Dict[str, Any]] = None,
    spread_defaults:   Optional[Dict[str, Any]] = None,
    cert_defaults:     Optional[Dict[str, Any]] = None,
    calendar:          Optional[Dict[str, Any]] = None,
    eligibility:       Optional[Dict[str, Any]] = None,
    active_state:      Optional[str] = None,
    is_seed:           bool = False,
    # ─── DSR-1 additions (all optional, backwards-compatible) ────────
    execution_platforms:    Optional[List[str]] = None,
    broker_compatibility:   Optional[Dict[str, Any]] = None,   # reserved · Phase 14
    strategy_compatibility: Optional[Dict[str, Any]] = None,   # reserved · Phase 13
    masterbot_compatibility:Optional[Dict[str, Any]] = None,   # reserved · Phase 14
    marketplace_visibility: Optional[Dict[str, Any]] = None,   # reserved · Phase 15
    propfirm_eligibility:   Optional[Dict[str, Any]] = None,   # reserved · Phase 14
) -> Dict[str, Any]:
    """Insert or update a symbol row. Returns the stored document.

    The caller (admin endpoint) MUST have already authenticated and
    authorised the operator.

    R0 — adds optional nested fields ``broker_mapping``, ``precision``,
    ``spread_defaults``, ``cert_defaults``, ``calendar``, ``eligibility``,
    plus ``active_state`` and ``is_seed``. All are additive — callers that
    omit them get exactly the pre-R0 row shape.
    """
    tier_n = normalize_tier(tier or default_tier())
    ac_n = normalize_asset_class(asset_class)
    cch_n = normalize_compute_hint(compute_cost_hint)
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    eb = (
        exploration_budget_for(tier_n)
        if exploration_budget_pct is None
        else float(exploration_budget_pct)
    )
    _validate_payload(
        symbol=sym_n, broker_class=bc_n, asset_class=ac_n, tier=tier_n,
        priority=int(priority), exploration_budget_pct=float(eb),
        compute_cost_hint=cch_n, pip_size=float(pip_size),
        volume_min=float(volume_min), volume_step=float(volume_step),
        min_data_bars=int(min_data_bars),
    )

    db = get_db()
    now = _now_iso()
    # Aliases are normalised the same way symbols are.
    alias_norm = sorted({normalize_symbol(a) for a in (aliases or []) if a})
    alias_norm = [a for a in alias_norm if a and a != sym_n]
    tag_clean = sorted({(t or "").strip().lower() for t in (tags or []) if t and t.strip()})

    set_doc: Dict[str, Any] = {
        "symbol":                 sym_n,
        "broker_class":           bc_n,
        "display_name":           (display_name or sym_n)[:200],
        "asset_class":            ac_n,
        "tier":                   tier_n,
        "enabled":                bool(enabled),
        "priority":               int(priority),
        "exploration_budget_pct": float(eb),
        "compute_cost_hint":      cch_n,
        "pip_size":               float(pip_size),
        "volume_min":             float(volume_min),
        "volume_step":            float(volume_step),
        "min_data_bars":          int(min_data_bars),
        "aliases":                alias_norm,
        "tags":                   tag_clean,
        "notes":                  (notes or "")[:2000] if notes else None,
        "source":                 (source or "operator")[:120],
        "regime_gate":            regime_gate or None,
        "updated_at":             now,
        "updated_by":             (updated_by or "<unknown>")[:200],
        # ─── R0 nested fields (additive) ─────────────────────────────
        "broker_mapping":         dict(broker_mapping or {}),
        "precision":              dict(precision or {}),
        "spread_defaults":        dict(spread_defaults or {}),
        "cert_defaults":          dict(cert_defaults or {}),
        "calendar":               dict(calendar or {}),
        "eligibility":            normalize_eligibility(eligibility),
        "active_state":           (active_state or "inactive")[:64],
        "is_seed":                bool(is_seed),
        # ─── DSR-1 additions ─────────────────────────────────────────
        # Operator-verified execution platforms (cTrader, MT5, etc.).
        "execution_platforms":    normalize_execution_platforms(execution_platforms),
        # Reserved future-phase fields. Stored opaquely today; never
        # validated, consumed, or surfaced. Future phases will read
        # these as-is. Defaults to empty objects so the document
        # shape is uniform across the collection.
        "broker_compatibility":   dict(broker_compatibility or {}),
        "strategy_compatibility": dict(strategy_compatibility or {}),
        "masterbot_compatibility":dict(masterbot_compatibility or {}),
        "marketplace_visibility": dict(marketplace_visibility or {}),
        "propfirm_eligibility":   dict(propfirm_eligibility or {}),
    }
    # Read the previous doc BEFORE the write so we can audit-diff it.
    prior = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    # `created_at` only on insert; `created_by` immortalises the original operator.
    try:
        await db[COLL].update_one(
            {"symbol": sym_n, "broker_class": bc_n},
            {
                "$set": set_doc,
                "$setOnInsert": {
                    "created_at": now,
                    "created_by": (updated_by or "<unknown>")[:200],
                },
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning("[market_universe] upsert failed: %s", e)
        raise
    stored = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    # R0 — write an audit row. Failure is logged but never raises.
    try:
        from engines.market_universe_audit import write_audit_entry
        await write_audit_entry(
            symbol=sym_n,
            broker_class=bc_n,
            before=prior,
            after=stored,
            operator_email=updated_by,
            action="seed_baseline" if is_seed and prior is None else (
                "upsert_insert" if prior is None else "upsert_update"
            ),
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] audit write failed: %s", e)
    return stored or set_doc


async def delete_symbol(
    symbol: str, broker_class: str = "unknown",
    *, force: bool = False, updated_by: str = "<unknown>",
) -> Dict[str, Any]:
    """Delete a row. R0: seed rows refuse deletion unless ``force=True``.

    Returns ``{deleted: bool, reason: str|None, was_seed: bool}``.
    """
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    try:
        prior = await db[COLL].find_one(
            {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
        )
        was_seed = bool((prior or {}).get("is_seed"))
        if prior is None:
            return {"deleted": False, "reason": "not_found", "was_seed": False}
        if was_seed and not force:
            return {
                "deleted": False,
                "reason": "seed_row_protected_use_force",
                "was_seed": True,
            }
        result = await db[COLL].delete_one({"symbol": sym_n, "broker_class": bc_n})
        deleted = bool(getattr(result, "deleted_count", 0))
        if deleted:
            try:
                from engines.market_universe_audit import write_audit_entry
                await write_audit_entry(
                    symbol=sym_n, broker_class=bc_n,
                    before=prior, after=None,
                    operator_email=updated_by,
                    action=("forced_delete" if was_seed else "delete"),
                )
            except Exception as e:                          # pragma: no cover
                logger.debug("[market_universe] audit on delete failed: %s", e)
        return {"deleted": deleted, "reason": None, "was_seed": was_seed}
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] delete_symbol failed: %s", e)
        return {"deleted": False, "reason": f"error:{e}", "was_seed": False}


async def set_tier(
    symbol: str, tier: str, *, broker_class: str = "unknown",
    updated_by: str = "<unknown>",
) -> Optional[Dict[str, Any]]:
    """Quick lifecycle transition. Returns the new row or None.

    Operator-facing convenience: promote/demote without re-supplying
    the full spec. Validates `tier` against ``VALID_TIERS``.
    """
    if tier not in VALID_TIERS:
        raise ValueError(
            f"tier: must be one of {sorted(VALID_TIERS)} (got {tier!r})"
        )
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    prior = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    res = await db[COLL].update_one(
        {"symbol": sym_n, "broker_class": bc_n},
        {"$set": {
            "tier": tier, "updated_at": _now_iso(),
            "updated_by": (updated_by or "<unknown>")[:200],
        }},
    )
    if not getattr(res, "matched_count", 0):
        return None
    after = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    try:
        from engines.market_universe_audit import write_audit_entry
        await write_audit_entry(
            symbol=sym_n, broker_class=bc_n,
            before=prior, after=after,
            operator_email=updated_by, action="set_tier",
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] audit set_tier failed: %s", e)
    return after


async def set_enabled(
    symbol: str, enabled: bool, *, broker_class: str = "unknown",
    updated_by: str = "<unknown>",
) -> Optional[Dict[str, Any]]:
    """Quick on/off toggle. Returns the new row or None when no match."""
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    prior = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    res = await db[COLL].update_one(
        {"symbol": sym_n, "broker_class": bc_n},
        {"$set": {
            "enabled": bool(enabled), "updated_at": _now_iso(),
            "updated_by": (updated_by or "<unknown>")[:200],
        }},
    )
    if not getattr(res, "matched_count", 0):
        return None
    after = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    try:
        from engines.market_universe_audit import write_audit_entry
        await write_audit_entry(
            symbol=sym_n, broker_class=bc_n,
            before=prior, after=after,
            operator_email=updated_by, action="set_enabled",
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] audit set_enabled failed: %s", e)
    return after


# ─────────────────────────────────────────────────────────────────────
# R0 — additional admin transitions
# ─────────────────────────────────────────────────────────────────────
async def set_eligibility(
    symbol: str,
    eligibility_patch: Dict[str, Any],
    *,
    broker_class: str = "unknown",
    updated_by: str = "<unknown>",
) -> Optional[Dict[str, Any]]:
    """Atomic patch of one or more ``eligibility.*`` flags.

    Unknown keys are silently ignored (see ``ELIGIBILITY_KEYS``).
    Returns the updated row, or ``None`` when the symbol is unknown.
    """
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    prior = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    if prior is None:
        return None
    cur = dict(prior.get("eligibility") or DEFAULT_ELIGIBILITY)
    for k, v in (eligibility_patch or {}).items():
        key = (k or "").strip().lower()
        if key in ELIGIBILITY_KEYS:
            cur[key] = bool(v)
    cur = normalize_eligibility(cur)
    await db[COLL].update_one(
        {"symbol": sym_n, "broker_class": bc_n},
        {"$set": {
            "eligibility": cur,
            "updated_at":  _now_iso(),
            "updated_by":  (updated_by or "<unknown>")[:200],
        }},
    )
    after = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    try:
        from engines.market_universe_audit import write_audit_entry
        await write_audit_entry(
            symbol=sym_n, broker_class=bc_n,
            before=prior, after=after,
            operator_email=updated_by, action="set_eligibility",
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] audit set_eligibility failed: %s", e)
    return after


async def set_calendar(
    symbol: str,
    calendar_patch: Dict[str, Any],
    *,
    broker_class: str = "unknown",
    updated_by: str = "<unknown>",
) -> Optional[Dict[str, Any]]:
    """Patch ``calendar.*`` (and optionally ``precision.*``) atomically.

    Validates that ``calendar.market_type`` (if present) is one of
    ``{forex, crypto}``. Other fields pass through unchanged.
    """
    if calendar_patch and "market_type" in calendar_patch:
        mt = (calendar_patch["market_type"] or "").strip().lower()
        if mt not in ("forex", "crypto"):
            raise ValueError(
                "calendar.market_type: must be one of {'forex','crypto'} "
                f"(got {calendar_patch['market_type']!r})"
            )
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    prior = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    if prior is None:
        return None
    cur = dict(prior.get("calendar") or {})
    cur.update({k: v for k, v in (calendar_patch or {}).items()})
    await db[COLL].update_one(
        {"symbol": sym_n, "broker_class": bc_n},
        {"$set": {
            "calendar":   cur,
            "updated_at": _now_iso(),
            "updated_by": (updated_by or "<unknown>")[:200],
        }},
    )
    after = await db[COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    )
    try:
        from engines.market_universe_audit import write_audit_entry
        await write_audit_entry(
            symbol=sym_n, broker_class=bc_n,
            before=prior, after=after,
            operator_email=updated_by, action="set_calendar",
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[market_universe] audit set_calendar failed: %s", e)
    return after


async def bulk_import(
    rows: List[Dict[str, Any]], *, updated_by: str = "<unknown>",
) -> Dict[str, Any]:
    """Operator-pasted bulk upsert. Returns a per-row outcome summary.

    Each row is forwarded to ``upsert_symbol(**row)``. Failures are
    captured per-row; siblings are not affected. Atomicity is **per
    row**, not across the whole batch (matches the rest of the
    registry semantics).
    """
    out: Dict[str, Any] = {"total": len(rows), "succeeded": [], "failed": []}
    for r in rows or []:
        try:
            payload = dict(r or {})
            payload.setdefault("updated_by", updated_by)
            stored = await upsert_symbol(**payload)
            out["succeeded"].append({
                "symbol":       stored.get("symbol"),
                "broker_class": stored.get("broker_class"),
            })
        except Exception as e:
            out["failed"].append({
                "symbol": (r or {}).get("symbol"),
                "error":  str(e)[:240],
            })
    return out


async def list_audit_for_symbol(
    symbol: str, *, broker_class: str = "unknown", limit: int = 200,
) -> List[Dict[str, Any]]:
    """Return audit rows for a symbol, newest first."""
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    cur = db[AUDIT_COLL].find(
        {"symbol": sym_n, "broker_class": bc_n}, {"_id": 0},
    ).sort([("ts_dt", -1)]).limit(max(1, min(int(limit), 2000)))
    return [d async for d in cur]


async def get_audit_at(
    symbol: str, ts_iso: str, *, broker_class: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """Find a single audit row at an exact ``updated_at`` ISO timestamp."""
    db = get_db()
    sym_n = normalize_symbol(symbol)
    bc_n = normalize_broker_class(broker_class)
    return await db[AUDIT_COLL].find_one(
        {"symbol": sym_n, "broker_class": bc_n, "updated_at": ts_iso},
        {"_id": 0},
    )


__all__ = [
    "is_enabled", "default_tier",
    "normalize_symbol", "normalize_broker_class",
    "normalize_tier", "normalize_asset_class", "normalize_compute_hint",
    "normalize_eligibility",
    "get_symbol", "list_symbols", "count_by_tier",
    "exploration_budget_for", "compute_cost_hint_to_weight",
    "upsert_symbol", "delete_symbol",
    "set_tier", "set_enabled",
    # R0 additions:
    "set_eligibility", "set_calendar", "bulk_import",
    "list_audit_for_symbol", "get_audit_at",
    "ELIGIBILITY_KEYS", "DEFAULT_ELIGIBILITY",
    "VALID_TIERS", "VALID_ASSET_CLASSES", "VALID_COMPUTE_HINTS",
    "COLL", "AUDIT_COLL",
    # DSR-1 additions:
    "VALID_EXECUTION_PLATFORMS",
    "normalize_execution_platforms",
    "RESERVED_FUTURE_FIELDS",
]
