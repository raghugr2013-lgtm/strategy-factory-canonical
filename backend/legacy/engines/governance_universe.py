"""Phase 30.2 — Universe Governance.

Operator-decreed ecosystem boundary that every default scan-defining
authority filters through. The panel governs ELIGIBILITY, not forced
allocation: env_priority + orchestrator + mutation budget all retain
adaptive authority inside the allowed universe.

Discipline:
  * Additive. No rewrites of A1/A2/A3/A4/A5/A6 — each authority gets a
    single non-invasive filter call.
  * Reversible. Remove the helper import → behaviour reverts exactly.
  * READ-ONLY by default (GET). POST requires admin role (FastAPI auth).
  * Operator-explicit `scan=[...]` payloads bypass the filter — manual
    flexibility preserved per the env_priority discipline.

Persistence:
  Mongo collection ``governance_universe``, single doc ``_id="config"``.

Public surface:
  PHASE_VERSION
  CANON_TF / canon_tf(tf)
  get_universe()                    — async, 30s-cached read
  save_universe(patch, admin_email) — async admin write
  intersect_scan(scan)              — pure filter for (pair, tf) tuples
  is_pair_allowed(pair)             — pure helper
  is_tf_allowed(tf)                 — pure helper
  is_style_allowed(style)           — pure helper
  effective_preview(authority_pool) — pure diagnostic
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

PHASE_VERSION = "30.2"
COLLECTION = "governance_universe"
CONFIG_ID = "config"

# Operator-decreed initial deployment posture.
DEFAULT_PAIRS: Tuple[str, ...] = ("EURUSD", "XAUUSD")
DEFAULT_TIMEFRAMES: Tuple[str, ...] = ("H1", "H4")
DEFAULT_STYLES: Tuple[str, ...] = ("trend-following", "mean-reversion", "breakout")
DEFAULT_EXPLORATION_FLOOR_PCT = 5.0
DEFAULT_MAX_ACTIVE_CELLS = 8
DEFAULT_BREADTH_VS_DEPTH = 0.5
AUDIT_LOG_CAP = 50
_CACHE_TTL_SEC = 30.0

# Canonical timeframe form is UPPERCASE (H1, H4, M15) — matches
# multi_cycle_runner.DEFAULT_SCAN and the API surface. We translate
# between lower (env_priority uses `1h`) and upper here so callers
# never need to know.
_TF_UPPER_FROM_LOWER = {
    "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
    "1h": "H1", "4h": "H4", "1d": "D1",
}
_TF_LOWER_FROM_UPPER = {v: k for k, v in _TF_UPPER_FROM_LOWER.items()}

# Closed set of canonical timeframes for validation.
CANON_TF: Tuple[str, ...] = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")


def canon_tf(tf: str) -> str:
    """Canonical UPPER form: '1h' / 'H1' / 'h1' → 'H1'. Returns the
    input unchanged when not recognised (callers can decide)."""
    if not isinstance(tf, str):
        return tf
    t = tf.strip()
    if not t:
        return t
    u = t.upper()
    if u in CANON_TF:
        return u
    low = t.lower()
    if low in _TF_UPPER_FROM_LOWER:
        return _TF_UPPER_FROM_LOWER[low]
    # H1/M15 style with mismatched case
    if len(t) >= 2 and t[0].upper() in ("H", "M", "D") and t[1:].isdigit():
        return f"{t[0].upper()}{t[1:]}"
    return u


def canon_pair(p: str) -> str:
    return str(p).strip().upper()


def canon_style(s: str) -> str:
    return str(s).strip().lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Cache (30s read-through) ─────────────────────────────────────
_cache: Dict[str, Any] = {"doc": None, "ts": 0.0}
_lock = asyncio.Lock()


def _default_doc() -> Dict[str, Any]:
    return {
        "_id":                   CONFIG_ID,
        "pairs":                 list(DEFAULT_PAIRS),
        "timeframes":            list(DEFAULT_TIMEFRAMES),
        "styles":                list(DEFAULT_STYLES),
        "exploration_floor_pct": float(DEFAULT_EXPLORATION_FLOOR_PCT),
        "max_active_cells":      int(DEFAULT_MAX_ACTIVE_CELLS),
        "breadth_vs_depth":      float(DEFAULT_BREADTH_VS_DEPTH),
        "updated_at":            _now_iso(),
        "updated_by":            "system_seed",
        "audit_log":             [],
        "phase":                 PHASE_VERSION,
    }


async def _ensure_seeded() -> Dict[str, Any]:
    db = get_db()
    doc = await db[COLLECTION].find_one({"_id": CONFIG_ID})
    if not doc:
        seed = _default_doc()
        try:
            await db[COLLECTION].insert_one(seed)
        except Exception:                                       # pragma: no cover
            logger.debug("[universe] seed insert raced; refetching")
        doc = await db[COLLECTION].find_one({"_id": CONFIG_ID})
    return doc or _default_doc()


def _strip_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy without Mongo ``_id`` so callers can JSON-serialize."""
    if not doc:
        return {}
    return {k: v for k, v in doc.items() if k != "_id"}


async def get_universe(*, force_refresh: bool = False) -> Dict[str, Any]:
    """Read current allowed universe. 30-second TTL cache.

    Returns a JSON-safe dict (no ``_id``).
    """
    now = time.monotonic()
    if not force_refresh:
        if _cache["doc"] is not None and (now - _cache["ts"]) < _CACHE_TTL_SEC:
            return dict(_cache["doc"])
    async with _lock:
        # Double-check after acquiring lock.
        if not force_refresh and _cache["doc"] is not None and (
            time.monotonic() - _cache["ts"]
        ) < _CACHE_TTL_SEC:
            return dict(_cache["doc"])
        doc = await _ensure_seeded()
        safe = _strip_id(doc)
        _cache["doc"] = safe
        _cache["ts"] = time.monotonic()
        return dict(safe)


def _validate_patch(
    patch: Dict[str, Any], prior: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (validated_fields, change_summary). Raises ValueError on bad input."""
    out: Dict[str, Any] = {}
    change: Dict[str, Any] = {}

    if "pairs" in patch:
        raw = patch["pairs"]
        if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
            raise ValueError("pairs must be a list[str]")
        cleaned = sorted({canon_pair(p) for p in raw if p})
        if not cleaned:
            raise ValueError("pairs cannot be empty (at least one pair required)")
        out["pairs"] = cleaned
        if cleaned != list(prior.get("pairs") or []):
            change["pairs"] = {"prev": prior.get("pairs"), "next": cleaned}

    if "timeframes" in patch:
        raw = patch["timeframes"]
        if not isinstance(raw, list) or not all(isinstance(t, str) for t in raw):
            raise ValueError("timeframes must be a list[str]")
        cleaned: List[str] = []
        for t in raw:
            c = canon_tf(t)
            if c not in CANON_TF:
                raise ValueError(f"unknown timeframe: {t!r}")
            cleaned.append(c)
        cleaned = sorted(set(cleaned), key=lambda x: CANON_TF.index(x))
        if not cleaned:
            raise ValueError("timeframes cannot be empty")
        out["timeframes"] = cleaned
        if cleaned != list(prior.get("timeframes") or []):
            change["timeframes"] = {"prev": prior.get("timeframes"), "next": cleaned}

    if "styles" in patch:
        raw = patch["styles"]
        if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
            raise ValueError("styles must be a list[str]")
        cleaned = sorted({canon_style(s) for s in raw if s})
        if not cleaned:
            raise ValueError("styles cannot be empty")
        out["styles"] = cleaned
        if cleaned != list(prior.get("styles") or []):
            change["styles"] = {"prev": prior.get("styles"), "next": cleaned}

    if "exploration_floor_pct" in patch:
        v = float(patch["exploration_floor_pct"])
        if not (0.0 <= v <= 50.0):
            raise ValueError("exploration_floor_pct must be in [0, 50]")
        out["exploration_floor_pct"] = round(v, 2)
        if out["exploration_floor_pct"] != prior.get("exploration_floor_pct"):
            change["exploration_floor_pct"] = {
                "prev": prior.get("exploration_floor_pct"), "next": out["exploration_floor_pct"],
            }

    if "max_active_cells" in patch:
        v = int(patch["max_active_cells"])
        if not (1 <= v <= 64):
            raise ValueError("max_active_cells must be in [1, 64]")
        out["max_active_cells"] = v
        if v != prior.get("max_active_cells"):
            change["max_active_cells"] = {"prev": prior.get("max_active_cells"), "next": v}

    if "breadth_vs_depth" in patch:
        v = float(patch["breadth_vs_depth"])
        if not (0.0 <= v <= 1.0):
            raise ValueError("breadth_vs_depth must be in [0, 1]")
        out["breadth_vs_depth"] = round(v, 4)
        if out["breadth_vs_depth"] != prior.get("breadth_vs_depth"):
            change["breadth_vs_depth"] = {
                "prev": prior.get("breadth_vs_depth"), "next": out["breadth_vs_depth"],
            }

    return out, change


async def save_universe(
    patch: Dict[str, Any], *, admin_email: str,
) -> Dict[str, Any]:
    """Admin write. Appends to audit_log (cap=50) and bumps timestamps.
    Returns the new full config doc (without ``_id``)."""
    if not admin_email:
        raise ValueError("admin_email required")
    db = get_db()
    async with _lock:
        prior = await _ensure_seeded()
        prior_safe = _strip_id(prior)
        validated, change = _validate_patch(patch, prior_safe)
        if not validated:
            # No-op write — return prior. Still useful for ack.
            return prior_safe

        now = _now_iso()
        audit_entry = {
            "ts":     now,
            "by":     admin_email,
            "change": change,
        }
        new_audit = (prior.get("audit_log") or []) + [audit_entry]
        new_audit = new_audit[-AUDIT_LOG_CAP:]

        update = dict(validated)
        update.update({
            "updated_at": now,
            "updated_by": admin_email,
            "audit_log":  new_audit,
            "phase":      PHASE_VERSION,
        })
        await db[COLLECTION].update_one(
            {"_id": CONFIG_ID},
            {"$set": update},
            upsert=True,
        )
        # Invalidate cache.
        _cache["doc"] = None
        _cache["ts"]  = 0.0
        fresh = await db[COLLECTION].find_one({"_id": CONFIG_ID})
        return _strip_id(fresh or {})


# ──────────────────────────────────────────────────────────────────
# Pure filter helpers (sync — used by A1/A2/A3/A4/A5/A6 wirings)
# ──────────────────────────────────────────────────────────────────

def _pairs_set(universe: Dict[str, Any]) -> frozenset:
    return frozenset(canon_pair(p) for p in (universe.get("pairs") or []))


def _tfs_set(universe: Dict[str, Any]) -> frozenset:
    """Return BOTH upper and lower forms so callers using either format
    can intersect cleanly without normalising first."""
    upper = {canon_tf(t) for t in (universe.get("timeframes") or [])}
    lower = {_TF_LOWER_FROM_UPPER.get(t, t.lower()) for t in upper}
    return frozenset(upper | lower)


def _styles_set(universe: Dict[str, Any]) -> frozenset:
    return frozenset(canon_style(s) for s in (universe.get("styles") or []))


def is_pair_allowed(universe: Dict[str, Any], pair: str) -> bool:
    return canon_pair(pair) in _pairs_set(universe)


def is_tf_allowed(universe: Dict[str, Any], tf: str) -> bool:
    return canon_tf(tf) in {canon_tf(t) for t in (universe.get("timeframes") or [])}


def is_style_allowed(universe: Dict[str, Any], style: str) -> bool:
    return canon_style(style) in _styles_set(universe)


def intersect_scan(
    universe: Dict[str, Any],
    scan: Iterable[Any],
) -> List[Tuple[str, str]]:
    """Pure filter for (pair, timeframe) tuples in either:
        [("EURUSD", "H1"), ...]   or
        [{"pair": "EURUSD", "timeframe": "H1"}, ...]
    Returns canonical UPPER form: [("EURUSD", "H1"), ...].

    Cells whose pair OR timeframe is outside the universe are dropped.
    Empty input → empty output.
    """
    allowed_pairs = _pairs_set(universe)
    allowed_tfs   = {canon_tf(t) for t in (universe.get("timeframes") or [])}
    out: List[Tuple[str, str]] = []
    for item in (scan or []):
        if isinstance(item, dict):
            p, tf = item.get("pair"), item.get("timeframe")
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            p, tf = item[0], item[1]
        else:
            continue
        if not p or not tf:
            continue
        cp = canon_pair(p)
        ct = canon_tf(tf)
        if cp in allowed_pairs and ct in allowed_tfs:
            out.append((cp, ct))
    return out


def effective_preview(
    universe: Dict[str, Any],
    *,
    multi_cycle_default: Iterable[Tuple[str, str]],
    orchestrator_diversity: Iterable[Tuple[str, str]],
    autonomous_rotation: Iterable[Tuple[str, str]],
    env_priority_pool: Iterable[Tuple[str, str]],
    gem_factory_pool: Iterable[Tuple[str, str]],
    auto_factory_pool: Iterable[Tuple[str, str]],
) -> Dict[str, Any]:
    """Diagnostic: how many cells each authority retains after filter."""
    def _stats(pool: Iterable[Tuple[str, str]]) -> Dict[str, Any]:
        pool_l = list(pool)
        kept = intersect_scan(universe, pool_l)
        return {"total": len(pool_l), "kept": len(kept), "cells": kept}
    return {
        "multi_cycle_default":    _stats(multi_cycle_default),
        "orchestrator_diversity": _stats(orchestrator_diversity),
        "autonomous_rotation":    _stats(autonomous_rotation),
        "env_priority_pool":      _stats(env_priority_pool),
        "gem_factory_pool":       _stats(gem_factory_pool),
        "auto_factory_pool":      _stats(auto_factory_pool),
    }
