"""
Phase 12 — System Tuning & Optimization.

Fully additive layer on top of Phase 11 (Gem Factory). Provides:

  * Configurable quality-filter floors (overrides the Phase 11 defaults
    when present; otherwise falls through transparently).
  * Recent-data weighting helper for scoring (last 6mo ≈ 2×, 6–12mo ≈
    1.5×, older ≈ 1×).
  * Performance tracking — per-strategy survival duration, live-vs-
    backtest gap, and replacement frequency.
  * Slot quality score — rolling `avg_pf`, `success_rate`, `n_generated`,
    `n_saved` per (pair, timeframe, style).
  * Adaptive generation — recommend `per_combo` based on slot quality:
    weak slots explore more, strong slots spend less.
  * Append-only event log — every reject / replace / retire event is
    recorded for postmortem and telemetry.

No existing engine is rewritten. Phase 11 calls into this module through
optional hook points that all wrap their work in try/except so that a
missing or failing Phase 12 never breaks Phase 11.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Collection names
# ─────────────────────────────────────────────────────────────────────
SETTINGS_COLL = "tuning_settings"
SLOT_STATS_COLL = "slot_stats"
PERF_COLL = "performance_snapshots"
EVENTS_COLL = "gem_factory_events"


# ─────────────────────────────────────────────────────────────────────
# Defaults (mirrors Phase 11 `QUALITY_FLOOR`; kept here so Phase 12 is
# self-contained and returns a usable floor even if Phase 11 is absent).
# ─────────────────────────────────────────────────────────────────────
DEFAULT_QUALITY_FLOOR: Dict[str, float] = {
    "min_profit_factor":    1.2,
    "min_stability_score":  50.0,
    "max_drawdown_pct":     10.0,
    "min_total_trades":     30,
    "min_pass_probability": 50.0,
}

ALLOWED_FLOOR_KEYS = set(DEFAULT_QUALITY_FLOOR.keys())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


# ─────────────────────────────────────────────────────────────────────
# Step 1 — Configurable quality floor
# ─────────────────────────────────────────────────────────────────────

async def get_quality_floor() -> Dict[str, float]:
    """Return the active quality floor, merging stored overrides over
    `DEFAULT_QUALITY_FLOOR`. Invalid or unknown keys are ignored."""
    db = get_db()
    doc = await db[SETTINGS_COLL].find_one({"key": "quality_floor"}, {"_id": 0})
    floor = dict(DEFAULT_QUALITY_FLOOR)
    if doc and isinstance(doc.get("values"), dict):
        for k, v in doc["values"].items():
            if k in ALLOWED_FLOOR_KEYS and isinstance(v, (int, float)):
                floor[k] = float(v)
    return floor


async def set_quality_floor(overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a partial override dict. Returns the effective merged floor."""
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be a dict")
    cleaned: Dict[str, float] = {}
    for k, v in overrides.items():
        if k not in ALLOWED_FLOOR_KEYS:
            continue
        try:
            cleaned[k] = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{k} must be numeric")
    db = get_db()
    await db[SETTINGS_COLL].update_one(
        {"key": "quality_floor"},
        {"$set": {"values": cleaned, "updated_at": _now_iso()}},
        upsert=True,
    )
    return await get_quality_floor()


async def reset_quality_floor() -> Dict[str, float]:
    db = get_db()
    await db[SETTINGS_COLL].delete_one({"key": "quality_floor"})
    return dict(DEFAULT_QUALITY_FLOOR)


# ─────────────────────────────────────────────────────────────────────
# Step 2 — Recent-data weighting
# ─────────────────────────────────────────────────────────────────────

def _months_ago(ts: Any, now: Optional[datetime] = None) -> Optional[float]:
    """Convert a trade timestamp (datetime, ISO string, or epoch seconds)
    to a 'months ago' float. Returns None if unparseable."""
    if ts is None:
        return None
    now = now or _now()
    dt: Optional[datetime] = None
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except Exception:
            return None
    elif isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return max(0.0, delta.total_seconds() / (30.0 * 24.0 * 3600.0))


def _recency_weight(months: Optional[float]) -> float:
    """Last 6mo → 2×, 6–12mo → 1.5×, older / unknown → 1×."""
    if months is None:
        return 1.0
    if months <= 6.0:
        return 2.0
    if months <= 12.0:
        return 1.5
    return 1.0


def weighted_profit_factor(trades: Iterable[Dict[str, Any]],
                           now: Optional[datetime] = None) -> float:
    """Recency-weighted profit factor.

    Each trade must expose a signed `pnl` (or `profit`) and ideally a
    timestamp under one of: `ts`, `timestamp`, `closed_at`, `date`.
    Missing timestamps are treated as old (weight 1×).
    """
    now = now or _now()
    num = 0.0
    den = 0.0
    for t in trades or []:
        if not isinstance(t, dict):
            continue
        pnl = t.get("pnl")
        if pnl is None:
            pnl = t.get("profit")
        if pnl is None:
            continue
        try:
            pnl = float(pnl)
        except (TypeError, ValueError):
            continue
        ts = (t.get("ts") or t.get("timestamp")
              or t.get("closed_at") or t.get("date"))
        w = _recency_weight(_months_ago(ts, now))
        if pnl >= 0:
            num += w * pnl
        else:
            den += w * abs(pnl)
    if den == 0:
        return float("inf") if num > 0 else 0.0
    return round(num / den, 4)


def attach_recency_score(card: Dict[str, Any]) -> Dict[str, Any]:
    """Non-destructively attach `recency_weighted_pf` if the card carries
    `trades` or `backtest.trades` with timestamps. Returns the same dict."""
    if not isinstance(card, dict):
        return card
    trades = (card.get("trades")
              or (card.get("backtest") or {}).get("trades")
              or (card.get("backtest_results") or {}).get("trades"))
    if trades:
        try:
            card["recency_weighted_pf"] = weighted_profit_factor(trades)
        except Exception as e:
            logger.debug("recency_weighted_pf failed: %s", e)
    return card


# ─────────────────────────────────────────────────────────────────────
# Step 4 — Slot quality score
# ─────────────────────────────────────────────────────────────────────

def _slot_key(pair: str, tf: str, style: str) -> Dict[str, str]:
    return {"pair": pair, "timeframe": tf, "style": style}


async def update_slot_stats(
    *, pair: str, timeframe: str, style: str,
    generated: int = 0, saved: int = 0,
    pf_samples: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Rolling update on the per-slot counters. `pf_samples` is a list of
    profit-factor values from this run's accepted candidates; they fold
    into a running mean via exponential smoothing (α = 0.3)."""
    db = get_db()
    key = _slot_key(pair, timeframe, style)
    cur = await db[SLOT_STATS_COLL].find_one(key, {"_id": 0}) or {}
    n_gen = int(cur.get("n_generated", 0)) + max(0, int(generated))
    n_saved = int(cur.get("n_saved", 0)) + max(0, int(saved))
    avg_pf = float(cur.get("avg_pf", 0.0))
    if pf_samples:
        alpha = 0.3
        for v in pf_samples:
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            avg_pf = round(
                v if avg_pf == 0.0 else alpha * v + (1 - alpha) * avg_pf, 4,
            )
    success_rate = round((n_saved / n_gen), 4) if n_gen > 0 else 0.0
    payload = {
        **key,
        "n_generated": n_gen,
        "n_saved": n_saved,
        "avg_pf": avg_pf,
        "success_rate": success_rate,
        "updated_at": _now_iso(),
    }
    await db[SLOT_STATS_COLL].update_one(key, {"$set": payload}, upsert=True)
    return payload


async def get_slot_stats(pair: str, timeframe: str, style: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db[SLOT_STATS_COLL].find_one(
        _slot_key(pair, timeframe, style), {"_id": 0},
    )
    if not doc:
        return {**_slot_key(pair, timeframe, style),
                "n_generated": 0, "n_saved": 0, "avg_pf": 0.0,
                "success_rate": 0.0, "updated_at": None}
    return doc


async def list_slot_stats() -> List[Dict[str, Any]]:
    db = get_db()
    return [d async for d in db[SLOT_STATS_COLL].find({}, {"_id": 0})
            .sort("success_rate", -1)]


# ─────────────────────────────────────────────────────────────────────
# Step 5 — Adaptive generation
# ─────────────────────────────────────────────────────────────────────

# Tunable thresholds
SLOT_STRONG_MIN_SAMPLES = 5          # need at least this many attempts
SLOT_STRONG_SUCCESS_RATE = 0.50      # ≥ 50 % strong → reduce load
SLOT_WEAK_SUCCESS_RATE   = 0.20      # ≤ 20 % weak → raise load
PER_COMBO_STRONG = 20
PER_COMBO_BASELINE = 30
PER_COMBO_WEAK = 45
PER_COMBO_MIN = 20
PER_COMBO_MAX = 50


def adaptive_per_combo(slot_stats: Dict[str, Any], base: int = PER_COMBO_BASELINE) -> int:
    """Recommend `per_combo` for a slot based on its rolling stats.

    * < SLOT_STRONG_MIN_SAMPLES samples → return `base` (neutral).
    * success_rate ≤ SLOT_WEAK_SUCCESS_RATE → PER_COMBO_WEAK.
    * success_rate ≥ SLOT_STRONG_SUCCESS_RATE → PER_COMBO_STRONG.
    * otherwise → `base`.

    Result is clamped to [PER_COMBO_MIN, PER_COMBO_MAX].
    """
    try:
        base = int(base)
    except (TypeError, ValueError):
        base = PER_COMBO_BASELINE
    if not isinstance(slot_stats, dict):
        return max(PER_COMBO_MIN, min(base, PER_COMBO_MAX))
    n = int(slot_stats.get("n_generated", 0) or 0)
    if n < SLOT_STRONG_MIN_SAMPLES:
        out = base
    else:
        sr = float(slot_stats.get("success_rate", 0.0) or 0.0)
        if sr <= SLOT_WEAK_SUCCESS_RATE:
            out = PER_COMBO_WEAK
        elif sr >= SLOT_STRONG_SUCCESS_RATE:
            out = PER_COMBO_STRONG
        else:
            out = base
    return max(PER_COMBO_MIN, min(out, PER_COMBO_MAX))


# ─────────────────────────────────────────────────────────────────────
# Step 3 — Performance tracking
# ─────────────────────────────────────────────────────────────────────

async def record_performance_snapshot(strategy_id: str) -> Optional[Dict[str, Any]]:
    """Compute and persist a per-strategy snapshot combining
    `strategy_library` (backtest + saved_at) and `live_tracking`
    (current live metrics).

    Returns the snapshot dict, or None if the strategy is unknown.
    """
    db = get_db()
    lib = await db["strategy_library"].find_one({"strategy_id": strategy_id}, {"_id": 0})
    if not lib:
        return None
    live = await db["live_tracking"].find_one({"strategy_id": strategy_id}, {"_id": 0})
    saved_at = lib.get("saved_at") or lib.get("created_at")
    survival_days: Optional[float] = None
    try:
        if saved_at:
            if isinstance(saved_at, datetime):
                dt = saved_at if saved_at.tzinfo else saved_at.replace(tzinfo=timezone.utc)
            else:
                dt = datetime.fromisoformat(str(saved_at).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            survival_days = round((_now() - dt).total_seconds() / 86400.0, 2)
    except Exception:
        survival_days = None

    bt = lib.get("backtest") or lib.get("backtest_results") or {}
    bt_pf = float(bt.get("profit_factor") or 0.0)
    live_pf = float((live or {}).get("live_metrics", {}).get("profit_factor") or 0.0)
    gap = round(live_pf - bt_pf, 4) if live else None

    replacement_count = await db[EVENTS_COLL].count_documents({
        "type": "replaced",
        "slot.pair": lib.get("pair"),
        "slot.timeframe": lib.get("timeframe"),
        "slot.style": lib.get("style"),
    })

    snap = {
        "strategy_id": strategy_id,
        "pair": lib.get("pair"),
        "timeframe": lib.get("timeframe"),
        "style": lib.get("style"),
        "status": lib.get("status") or "active",
        "backtest_pf": bt_pf,
        "live_pf": live_pf,
        "live_vs_backtest_gap": gap,
        "survival_days": survival_days,
        "replacement_count": replacement_count,
        "snapshot_at": _now_iso(),
    }
    await db[PERF_COLL].update_one(
        {"strategy_id": strategy_id},
        {"$set": snap}, upsert=True,
    )
    return snap


async def list_performance(limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 500))
    cursor = db[PERF_COLL].find({}, {"_id": 0}).sort("snapshot_at", -1).limit(limit)
    return [d async for d in cursor]


# ─────────────────────────────────────────────────────────────────────
# Step 6 — Event log (rejected / replaced / retired / refined)
# ─────────────────────────────────────────────────────────────────────

ALLOWED_EVENT_TYPES = {"rejected", "refined", "replaced", "retired", "saved"}


async def record_event(
    event_type: str, *,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    style: Optional[str] = None,
    strategy_id: Optional[str] = None,
    reasons: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(
            f"event_type must be one of {sorted(ALLOWED_EVENT_TYPES)}"
        )
    db = get_db()
    doc: Dict[str, Any] = {
        "type": event_type,
        "slot": {"pair": pair, "timeframe": timeframe, "style": style},
        "strategy_id": strategy_id,
        "reasons": list(reasons or []),
        "extra": extra or {},
        "ts": _now_iso(),
    }
    await db[EVENTS_COLL].insert_one({**doc})
    # Strip _id before returning
    doc.pop("_id", None)
    return doc


async def list_events(
    *, event_type: Optional[str] = None, limit: int = 100,
) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 500))
    q: Dict[str, Any] = {}
    if event_type:
        if event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(
                f"event_type must be one of {sorted(ALLOWED_EVENT_TYPES)}"
            )
        q["type"] = event_type
    cur = db[EVENTS_COLL].find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    return [d async for d in cur]


# ─────────────────────────────────────────────────────────────────────
# Convenience: summary snapshot for a single API call
# ─────────────────────────────────────────────────────────────────────

async def get_tuning_overview() -> Dict[str, Any]:
    slots = await list_slot_stats()
    top_slots = slots[:10]
    weakest = sorted(slots, key=lambda s: s.get("success_rate", 0.0))[:10]
    floor = await get_quality_floor()
    db = get_db()
    events_total = await db[EVENTS_COLL].count_documents({})
    rejected_total = await db[EVENTS_COLL].count_documents({"type": "rejected"})
    retired_total = await db[EVENTS_COLL].count_documents({"type": "retired"})
    replaced_total = await db[EVENTS_COLL].count_documents({"type": "replaced"})
    return {
        "quality_floor": floor,
        "quality_floor_defaults": DEFAULT_QUALITY_FLOOR,
        "slots_tracked": len(slots),
        "top_slots": top_slots,
        "weakest_slots": weakest,
        "event_totals": {
            "total": events_total,
            "rejected": rejected_total,
            "retired": retired_total,
            "replaced": replaced_total,
        },
        "adaptive_bounds": {
            "weak_per_combo": PER_COMBO_WEAK,
            "baseline_per_combo": PER_COMBO_BASELINE,
            "strong_per_combo": PER_COMBO_STRONG,
            "min_samples_for_adaptive": SLOT_STRONG_MIN_SAMPLES,
            "weak_threshold": SLOT_WEAK_SUCCESS_RATE,
            "strong_threshold": SLOT_STRONG_SUCCESS_RATE,
        },
    }
