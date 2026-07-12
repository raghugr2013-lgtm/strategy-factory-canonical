"""
Phase 23 — Adaptive Environment Priority Orchestration.

Tracks per-(pair, timeframe) productivity and biases AUTONOMOUS orchestrator
runs toward consistently profitable environments while preserving exploration.

Design goals:
    * Slow, bounded adaptation — no rapid oscillation
    * Decay back to neutral when an env stops being used (prevents permanent bias)
    * Hard safety limits — no runaway allocation
    * Manual flexibility — only autonomous picks are biased; explicit `scan=[]`
      payloads in `start_multi_cycle(...)` are untouched

Public API consumed by:
    - engines.ai_orchestrator (sampling for autonomous triggers)
    - api.orchestrator         (config + stats endpoints)
    - engines.multi_cycle_runner (after each cycle finishes — not modified;
                                  feedback is pulled from `auto_run_cycles`
                                  during the orchestrator tick)

Persistence:
    * Mongo collection ``orchestrator_env_priority``
        - ``_id="config"``   →  tiers, weights, exploration floor, knobs
        - ``_id="state"``    →  per-env stats + adaptive multipliers + cursors
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import random

from engines.db import get_db

logger = logging.getLogger(__name__)

COLL = "orchestrator_env_priority"

# ── Default config (can be overridden by saved config) ───────────────
DEFAULT_TIERS: Dict[str, Dict[str, Any]] = {
    "core": {
        "pairs": ["EURUSD", "GBPUSD", "XAUUSD"],
        "timeframes": ["15m", "1h"],
        "weight": 0.70,
    },
    "secondary": {
        "pairs": ["USDJPY", "US100"],
        "timeframes": ["15m", "1h", "4h"],
        "weight": 0.20,
    },
    "exploratory": {
        "pairs": ["BTCUSD", "ETHUSD"],
        "timeframes": ["5m", "15m"],
        "weight": 0.10,
    },
}

# Hard guardrails (never disabled, only configurable within bounds).
MULTIPLIER_MIN = 0.5
MULTIPLIER_MAX = 2.0
MULTIPLIER_NEUTRAL = 1.0

DEFAULT_KNOBS: Dict[str, Any] = {
    # Adaptive update strength (EMA smoothing α, low = slow).
    "ema_alpha": 0.20,
    # Per-tick decay toward neutral when env was idle this tick.
    # 0.02 → ~50 % to neutral after ~35 ticks (about 9 hrs at 15-min cadence).
    "decay_rate": 0.02,
    # Floor reserved for exploratory tier — even when CORE dominates
    # adaptive scoring, exploratory keeps at least this much allocation.
    "exploratory_floor": 0.05,
    # Max share of total allocation any single env may capture (anti-runaway).
    "max_env_share": 0.80,
    # Allow noisy/expensive scans (1m timeframe + broad crypto brute-force)?
    "allow_noisy_scans": False,
    # Weighted feature mix used to compute per-env normalized score.
    "score_weights": {
        "pf": 0.30,
        "pass_prob": 0.25,
        "survivors": 0.20,
        "oos_pf": 0.15,
        "drawdown": 0.10,
    },
    # Master switch for adaptation (paused → only base tier weights are used).
    "adaptation_enabled": True,
}

# Timeframes considered "noisy" when allow_noisy_scans=False.
NOISY_TIMEFRAMES = {"1m"}

_lock = asyncio.Lock()
_TIER_NAMES = ("core", "secondary", "exploratory")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _norm_tf(tf: str) -> str:
    """Canonical timeframe form: ``1h`` / ``H1`` → ``1h``,
    ``15M`` / ``15m`` → ``15m``, ``D1`` / ``1d`` → ``1d``.

    The orchestrator and ``multi_cycle_runner`` use ``H1`` style; the
    UI / config use ``1h``. Both must hash to the same env key.
    """
    t = str(tf).strip().lower()
    if not t:
        return t
    # Hxx → xxh, Mxx → xxm, Dxx → xxd
    if t[0] in ("h", "m", "d") and t[1:].isdigit():
        return f"{t[1:]}{t[0]}"
    return t


def upper_tf(tf: str) -> str:
    """Convert ``1h`` / ``h1`` → ``H1`` (multi_cycle_runner format)."""
    t = _norm_tf(tf)
    if t.endswith("h") and t[:-1].isdigit():
        return f"H{t[:-1]}"
    if t.endswith("d") and t[:-1].isdigit():
        return f"D{t[:-1]}"
    if t.endswith("m") and t[:-1].isdigit():
        return f"{t[:-1]}M"
    return t.upper()


def _env_key(pair: str, tf: str) -> str:
    return f"{pair.upper()}|{_norm_tf(tf)}"


def _validate_weights(tiers: Dict[str, Dict[str, Any]]) -> None:
    s = sum(float(t.get("weight", 0)) for t in tiers.values())
    if s <= 0:
        raise ValueError("at least one tier must have weight > 0")


# ════════════════════════════════════════════════════════════════════
# Persistence
# ════════════════════════════════════════════════════════════════════

async def _load_doc(_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[COLL].find_one({"_id": _id}, {"_id": 0})


async def _save_doc(_id: str, doc: Dict[str, Any]) -> None:
    db = get_db()
    await db[COLL].update_one(
        {"_id": _id}, {"$set": {**doc, "updated_at": _now_iso()}}, upsert=True,
    )


def _default_config() -> Dict[str, Any]:
    return {
        "tiers": {
            name: {
                "pairs": list(t["pairs"]),
                "timeframes": list(t["timeframes"]),
                "weight": float(t["weight"]),
            }
            for name, t in DEFAULT_TIERS.items()
        },
        "knobs": dict(DEFAULT_KNOBS),
        # Audit cursor: highest cycle.finished_at consumed during adaptive
        # update.  Prevents double-counting across orchestrator ticks.
        "_last_consumed_cycle_iso": None,
    }


async def get_config() -> Dict[str, Any]:
    cfg = await _load_doc("config")
    if not cfg:
        cfg = _default_config()
        await _save_doc("config", cfg)
    # Backfill any newly-introduced knobs with defaults (forward-compat).
    knobs = {**DEFAULT_KNOBS, **(cfg.get("knobs") or {})}
    cfg["knobs"] = knobs
    cfg["tiers"] = cfg.get("tiers") or _default_config()["tiers"]
    return cfg


async def save_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ``patch`` into the persisted config and return the new config.
    Validates tier weights and clamps numeric knobs into safe ranges."""
    cfg = await get_config()
    tiers = patch.get("tiers")
    if isinstance(tiers, dict):
        merged = {**cfg["tiers"]}
        for name, t in tiers.items():
            if name not in _TIER_NAMES:
                raise ValueError(f"unknown tier: {name}")
            if not isinstance(t, dict):
                continue
            row = {**merged.get(name, {})}
            if "pairs" in t and isinstance(t["pairs"], list):
                row["pairs"] = [str(p).upper() for p in t["pairs"] if p]
            if "timeframes" in t and isinstance(t["timeframes"], list):
                row["timeframes"] = [_norm_tf(x) for x in t["timeframes"] if x]
            if "weight" in t:
                row["weight"] = max(0.0, min(1.0, float(t["weight"])))
            merged[name] = row
        _validate_weights(merged)
        cfg["tiers"] = merged

    knobs_patch = patch.get("knobs")
    if isinstance(knobs_patch, dict):
        knobs = {**cfg["knobs"]}
        for k, v in knobs_patch.items():
            if k not in DEFAULT_KNOBS:
                continue
            if k == "score_weights" and isinstance(v, dict):
                sw = {**knobs["score_weights"]}
                for sk, sv in v.items():
                    if sk in DEFAULT_KNOBS["score_weights"]:
                        sw[sk] = max(0.0, float(sv))
                tot = sum(sw.values()) or 1.0
                knobs["score_weights"] = {k_: round(v_ / tot, 4)
                                          for k_, v_ in sw.items()}
            elif isinstance(v, bool):
                knobs[k] = bool(v)
            elif isinstance(v, (int, float)):
                if k == "ema_alpha":
                    knobs[k] = max(0.01, min(0.9, float(v)))
                elif k == "decay_rate":
                    knobs[k] = max(0.0, min(0.5, float(v)))
                elif k == "exploratory_floor":
                    knobs[k] = max(0.0, min(0.5, float(v)))
                elif k == "max_env_share":
                    knobs[k] = max(0.1, min(1.0, float(v)))
        cfg["knobs"] = knobs

    await _save_doc("config", cfg)
    return cfg


async def _get_state() -> Dict[str, Any]:
    state = await _load_doc("state") or {}
    state.setdefault("envs", {})
    return state


async def _save_state(state: Dict[str, Any]) -> None:
    await _save_doc("state", state)


async def get_stats() -> List[Dict[str, Any]]:
    """Per-env stats — surfaced verbatim to UI for visibility/debugging."""
    cfg = await get_config()
    state = await _get_state()
    envs = state.get("envs") or {}

    # Build full matrix from configured tiers so the UI can show every
    # configured env even if it has no recorded runs yet.
    rows: List[Dict[str, Any]] = []
    for tier_name, tier in cfg["tiers"].items():
        for p in tier.get("pairs", []):
            for tf in tier.get("timeframes", []):
                key = _env_key(p, tf)
                e = envs.get(key) or {}
                rows.append({
                    "key": key,
                    "pair": p,
                    "timeframe": tf,
                    "tier": tier_name,
                    "tier_weight": float(tier.get("weight", 0)),
                    "multiplier": float(e.get("multiplier", MULTIPLIER_NEUTRAL)),
                    "score_ema": e.get("score_ema"),
                    "samples": int(e.get("samples", 0)),
                    "last_used_at": e.get("last_used_at"),
                    "last_updated_at": e.get("last_updated_at"),
                    "metrics": e.get("metrics") or {
                        "pf_ema": None, "pass_prob_ema": None,
                        "survivors_ema": None, "oos_pf_ema": None,
                        "dd_ema": None,
                    },
                    "noisy": _norm_tf(tf) in NOISY_TIMEFRAMES,
                })
    return rows


# ════════════════════════════════════════════════════════════════════
# Adaptive feedback — called from the orchestrator tick
# ════════════════════════════════════════════════════════════════════

def _norm_pf(pf: Optional[float]) -> float:
    if pf is None:
        return 0.0
    return max(0.0, min(1.0, (float(pf) - 1.0) / 1.0))     # 1.0..2.0 → 0..1


def _norm_pp(pp: Optional[float]) -> float:
    if pp is None:
        return 0.0
    return max(0.0, min(1.0, float(pp)))


def _norm_survivors(n: Optional[int]) -> float:
    if n is None:
        return 0.0
    return max(0.0, min(1.0, float(n) / 5.0))               # 0..5 → 0..1


def _norm_dd(dd: Optional[float]) -> float:
    """``dd`` is a fraction (0..1).  Lower is better; 0 % drawdown → 1.0."""
    if dd is None:
        return 0.5
    return max(0.0, min(1.0, 1.0 - float(dd) / 0.4))        # 0..40 % → 1..0


def _compute_score(metrics: Dict[str, Any], score_weights: Dict[str, float]) -> float:
    return (
        score_weights.get("pf", 0)        * _norm_pf(metrics.get("pf_ema"))
        + score_weights.get("pass_prob", 0) * _norm_pp(metrics.get("pass_prob_ema"))
        + score_weights.get("survivors", 0) * _norm_survivors(metrics.get("survivors_ema"))
        + score_weights.get("oos_pf", 0)    * _norm_pf(metrics.get("oos_pf_ema"))
        + score_weights.get("drawdown", 0)  * _norm_dd(metrics.get("dd_ema"))
    )


def _ema(prev: Optional[float], new: float, alpha: float) -> float:
    if prev is None:
        return float(new)
    return float(alpha * new + (1.0 - alpha) * prev)


def _multiplier_from_score(score: float) -> float:
    """Map normalized score 0..1 → multiplier 0.5..2.0."""
    m = MULTIPLIER_MIN + (MULTIPLIER_MAX - MULTIPLIER_MIN) * max(0.0, min(1.0, score))
    return round(m, 4)


def _summarize_cycle(cyc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull adaptive features out of one ``auto_run_cycles`` doc."""
    pair = cyc.get("pair")
    tf = cyc.get("timeframe")
    if not pair or not tf:
        return None
    counts = cyc.get("counts") or {}
    survivors = int(counts.get("auto_save_saved") or 0)
    pf = cyc.get("best_pf_cycle")

    pp_vals: List[float] = []
    oos_vals: List[float] = []
    dd_vals: List[float] = []
    for s in (cyc.get("strategies") or []):
        pp = s.get("pass_probability")
        if isinstance(pp, (int, float)):
            pp_vals.append(float(pp))
        oos = s.get("oos_best_pf") or s.get("oos_pf")
        if isinstance(oos, (int, float)):
            oos_vals.append(float(oos))
        dd = s.get("best_max_dd") or s.get("max_drawdown")
        if isinstance(dd, (int, float)):
            dd_vals.append(float(dd))

    return {
        "pair": pair, "timeframe": tf,
        "pf": float(pf) if isinstance(pf, (int, float)) else None,
        "survivors": survivors,
        "pass_prob": (sum(pp_vals) / len(pp_vals)) if pp_vals else None,
        "oos_pf": (sum(oos_vals) / len(oos_vals)) if oos_vals else None,
        "dd": (sum(dd_vals) / len(dd_vals)) if dd_vals else None,
        "finished_at": cyc.get("finished_at"),
    }


async def consume_recent_cycles(limit: int = 200) -> Dict[str, Any]:
    """Pull cycles finished since our last cursor and update env stats.

    Idempotent — uses a finished_at cursor stored on the config doc to
    avoid double-counting.  Safe to call from every orchestrator tick.
    """
    async with _lock:
        cfg = await get_config()
        knobs = cfg["knobs"]
        if not knobs.get("adaptation_enabled", True):
            return {"updated": 0, "skipped_pause": True}

        cursor = cfg.get("_last_consumed_cycle_iso")
        db = get_db()
        q: Dict[str, Any] = {"finished_at": {"$ne": None}}
        if cursor:
            q["finished_at"] = {"$gt": cursor}
        cursor_new: Optional[str] = cursor
        cycles: List[Dict[str, Any]] = []
        async for row in (
            db["auto_run_cycles"]
            .find(q, {"_id": 0})
            .sort("finished_at", 1)
            .limit(limit)
        ):
            cycles.append(row)

        if not cycles:
            await _decay_idle(cfg)
            return {"updated": 0, "decayed_only": True}

        state = await _get_state()
        envs = state.setdefault("envs", {})
        alpha = float(knobs["ema_alpha"])
        score_weights = knobs["score_weights"]
        touched: set[str] = set()

        for cyc in cycles:
            summ = _summarize_cycle(cyc)
            if not summ:
                continue
            key = _env_key(summ["pair"], summ["timeframe"])
            e = envs.setdefault(key, {
                "pair": summ["pair"].upper(),
                "timeframe": _norm_tf(summ["timeframe"]),
                "multiplier": MULTIPLIER_NEUTRAL,
                "samples": 0,
                "metrics": {},
            })
            metrics = e.setdefault("metrics", {})
            metrics["pf_ema"] = _ema(metrics.get("pf_ema"), summ["pf"] or 0.0, alpha)
            metrics["pass_prob_ema"] = _ema(metrics.get("pass_prob_ema"),
                                            summ["pass_prob"] or 0.0, alpha)
            metrics["survivors_ema"] = _ema(metrics.get("survivors_ema"),
                                            float(summ["survivors"]), alpha)
            metrics["oos_pf_ema"] = _ema(metrics.get("oos_pf_ema"),
                                         summ["oos_pf"] or 0.0, alpha)
            metrics["dd_ema"] = _ema(metrics.get("dd_ema"),
                                     summ["dd"] if summ["dd"] is not None else 0.1,
                                     alpha)

            score = _compute_score(metrics, score_weights)
            target_mult = _multiplier_from_score(score)
            # Smooth multiplier update (extra layer on top of EMA-driven score).
            e["multiplier"] = round(
                _ema(e.get("multiplier", MULTIPLIER_NEUTRAL), target_mult, alpha),
                4,
            )
            e["score_ema"] = round(score, 4)
            e["samples"] = int(e.get("samples", 0)) + 1
            e["last_used_at"] = summ["finished_at"]
            e["last_updated_at"] = _now_iso()
            touched.add(key)

            ft = summ["finished_at"]
            if ft and (cursor_new is None or ft > cursor_new):
                cursor_new = ft

        # Decay envs that did NOT receive an update this batch.
        await _decay_idle(cfg, state=state, exclude=touched, save=False)

        await _save_state(state)
        if cursor_new and cursor_new != cursor:
            cfg["_last_consumed_cycle_iso"] = cursor_new
            await _save_doc("config", cfg)

        return {
            "updated": len(touched),
            "cycles_consumed": len(cycles),
            "cursor": cursor_new,
        }


async def _decay_idle(
    cfg: Dict[str, Any],
    *,
    state: Optional[Dict[str, Any]] = None,
    exclude: Optional[set] = None,
    save: bool = True,
) -> None:
    """Pull every idle env's multiplier slightly toward neutral. Prevents
    permanent bias from old performance."""
    knobs = cfg["knobs"]
    decay = float(knobs.get("decay_rate", 0))
    if decay <= 0:
        return
    if state is None:
        state = await _get_state()
    envs = state.get("envs") or {}
    excl = exclude or set()
    changed = False
    for key, e in envs.items():
        if key in excl:
            continue
        m = float(e.get("multiplier", MULTIPLIER_NEUTRAL))
        if abs(m - MULTIPLIER_NEUTRAL) < 1e-3:
            continue
        new_m = m + (MULTIPLIER_NEUTRAL - m) * decay
        e["multiplier"] = round(new_m, 4)
        changed = True
    if changed and save:
        await _save_state(state)


async def reset_multipliers() -> Dict[str, Any]:
    """Clear all adaptive multipliers and reset feature EMAs."""
    async with _lock:
        state = await _get_state()
        envs = state.get("envs") or {}
        n = len(envs)
        for e in envs.values():
            e["multiplier"] = MULTIPLIER_NEUTRAL
            e["score_ema"] = None
            e["metrics"] = {}
        await _save_state(state)
        # Also reset cursor so we can re-warm from history if desired.
        cfg = await get_config()
        cfg["_last_consumed_cycle_iso"] = None
        await _save_doc("config", cfg)
        return {"reset_envs": n}


# ════════════════════════════════════════════════════════════════════
# Sampling — picks N (pair, timeframe) tuples for an autonomous run
# ════════════════════════════════════════════════════════════════════

def _enumerate_envs(
    cfg: Dict[str, Any], allow_noisy: bool,
    allowed_universe: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str, str, float]]:
    """Returns ``[(pair, tf, tier, base_tier_weight), ...]`` filtered.

    Phase 30.2 — when ``allowed_universe`` is supplied (operator-decreed
    ecosystem boundary), cells whose pair OR timeframe is not in the
    universe are dropped before tier weighting. Empty universe filter
    (no overlap) → returns []; caller falls back gracefully.
    """
    out: List[Tuple[str, str, str, float]] = []
    if allowed_universe:
        try:
            from engines import governance_universe as _gu
            uni_pairs = {_gu.canon_pair(p) for p in (allowed_universe.get("pairs") or [])}
            uni_tfs_lower = {
                _gu._TF_LOWER_FROM_UPPER.get(_gu.canon_tf(t), _gu.canon_tf(t).lower())
                for t in (allowed_universe.get("timeframes") or [])
            }
        except Exception:                                   # pragma: no cover
            allowed_universe = None
    for tier_name, tier in cfg["tiers"].items():
        w = float(tier.get("weight", 0))
        if w <= 0:
            continue
        for p in tier.get("pairs", []):
            for tf in tier.get("timeframes", []):
                if not allow_noisy and _norm_tf(tf) in NOISY_TIMEFRAMES:
                    continue
                if allowed_universe:
                    if p.upper() not in uni_pairs:
                        continue
                    if _norm_tf(tf) not in uni_tfs_lower:
                        continue
                out.append((p.upper(), _norm_tf(tf), tier_name, w))
    return out


def _build_weights(
    cfg: Dict[str, Any], envs_state: Dict[str, Any], allow_noisy: bool,
    allowed_universe: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Compute final per-env sampling weights with safety caps + floors.
    Returns a list of dicts ready for visibility export."""
    knobs = cfg["knobs"]
    pool = _enumerate_envs(cfg, allow_noisy=allow_noisy, allowed_universe=allowed_universe)
    if not pool:
        return []

    rows: List[Dict[str, Any]] = []
    tier_totals: Dict[str, float] = {}
    for (p, tf, tier, base_w) in pool:
        key = _env_key(p, tf)
        mult = float((envs_state.get(key) or {}).get("multiplier", MULTIPLIER_NEUTRAL))
        eff = mult
        rows.append({
            "pair": p, "timeframe": tf, "tier": tier,
            "tier_weight": base_w, "multiplier": mult, "score_eff": eff,
        })
        tier_totals[tier] = tier_totals.get(tier, 0.0) + eff

    # Within-tier normalization: each row gets share = tier_weight × eff / Σ_eff_in_tier
    for r in rows:
        tot = tier_totals.get(r["tier"], 0.0) or 1.0
        r["weight"] = float(r["tier_weight"]) * (r["score_eff"] / tot)

    # Apply exploratory floor.
    floor = float(knobs.get("exploratory_floor", 0))
    if floor > 0:
        explo_sum = sum(r["weight"] for r in rows if r["tier"] == "exploratory")
        if 0 < explo_sum < floor and any(r["tier"] == "exploratory" for r in rows):
            scale_up = floor / explo_sum
            other_total = 1.0 - floor
            old_other_total = max(1e-9, 1.0 - explo_sum)
            scale_down = other_total / old_other_total
            for r in rows:
                if r["tier"] == "exploratory":
                    r["weight"] = r["weight"] * scale_up
                else:
                    r["weight"] = r["weight"] * scale_down

    # Per-env hard cap.
    cap = float(knobs.get("max_env_share", 1.0))
    if 0 < cap < 1.0:
        spillover = 0.0
        capped_keys: List[int] = []
        for i, r in enumerate(rows):
            if r["weight"] > cap:
                spillover += r["weight"] - cap
                r["weight"] = cap
                capped_keys.append(i)
        if spillover > 0:
            uncapped = [i for i in range(len(rows)) if i not in capped_keys]
            uw_total = sum(rows[i]["weight"] for i in uncapped) or 1e-9
            for i in uncapped:
                rows[i]["weight"] += spillover * (rows[i]["weight"] / uw_total)

    # Final renorm — guard against floating drift.
    s = sum(r["weight"] for r in rows) or 1.0
    for r in rows:
        r["weight"] = round(r["weight"] / s, 6)

    return rows


async def preview_allocation(allow_noisy: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Return per-env final allocation (after multiplier + cap + floor) so
    the UI can show "if I sampled 1 000 picks, here's the distribution"."""
    cfg = await get_config()
    if allow_noisy is None:
        allow_noisy = bool(cfg["knobs"].get("allow_noisy_scans"))
    state = await _get_state()
    # Phase 30.2 — filter through allowed universe.
    allowed_universe = None
    try:
        from engines import governance_universe as _gu
        allowed_universe = await _gu.get_universe()
    except Exception:                                       # pragma: no cover
        pass
    return _build_weights(cfg, state.get("envs") or {}, bool(allow_noisy),
                          allowed_universe=allowed_universe)


async def pick_environments(
    n: int,
    *,
    allow_noisy: Optional[bool] = None,
    seed: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """Return up to ``n`` ``(pair, TIMEFRAME_UPPERCASE)`` tuples sampled
    by adaptive weights. Used by the autonomous orchestrator triggers.

    Manual ``scan=`` payloads bypass this — manual flexibility preserved.
    """
    cfg = await get_config()
    if allow_noisy is None:
        allow_noisy = bool(cfg["knobs"].get("allow_noisy_scans"))
    state = await _get_state()
    # Phase 30.2 — filter through allowed universe (operator boundary).
    allowed_universe = None
    try:
        from engines import governance_universe as _gu
        allowed_universe = await _gu.get_universe()
    except Exception:                                       # pragma: no cover
        pass
    rows = _build_weights(cfg, state.get("envs") or {}, bool(allow_noisy),
                          allowed_universe=allowed_universe)
    if not rows:
        return []

    rng = random.Random(seed) if seed is not None else random
    weights = [max(0.0, r["weight"]) for r in rows]
    if sum(weights) <= 0:
        return []

    chosen: List[Tuple[str, str]] = []
    chosen_keys: set = set()
    pool_idx = list(range(len(rows)))
    pool_w = list(weights)
    while len(chosen) < min(n, len(rows)) and sum(pool_w) > 0:
        pick = rng.choices(pool_idx, weights=pool_w, k=1)[0]
        i = pool_idx.index(pick)
        r = rows[pick]
        key = _env_key(r["pair"], r["timeframe"])
        if key not in chosen_keys:
            chosen.append((r["pair"], upper_tf(r["timeframe"])))
            chosen_keys.add(key)
        # Remove sampled from pool
        pool_idx.pop(i)
        pool_w.pop(i)

    return chosen
