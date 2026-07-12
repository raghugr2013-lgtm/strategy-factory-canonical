"""
Phase 15 — Evolution Engine (additive only).
Phase 16 — Regime Awareness (additive only).

Reads the Phase-14.3 `mutation_stability_log` collection and produces per-
mutation-type weights that bias future mutation selection toward high-
performing variants — while never hard-filtering a type (each type keeps
a small baseline probability so randomness is preserved).

Phase 16 extends this with regime-aware weights: when the caller supplies
a `regime_type`, weights are computed from rows whose `regime_type`
matches. Regime-specific weights activate only when the filtered log has
at least `MIN_LOGS_PER_REGIME` rows; otherwise callers should fall back
to the global (Phase 15) weights.

Safety contract:
    * If fewer than `MIN_LOGS_FOR_WEIGHTS` rows exist in the stability log,
      `compute_mutation_weights()` returns `None` and callers MUST fall
      back to the legacy uniform / deterministic selection path.
    * Regime-specific weights require `MIN_LOGS_PER_REGIME` within that
      regime; otherwise the call returns `None`.
    * No changes to scoring, validation, ranking, or save logic — weights
      only affect which mutation_types are *tried*, not how their outputs
      are judged.
    * Every declared mutation_type receives at least `BASELINE_WEIGHT`,
      so a type that under-performed in the past can still recover.

Public surface:
    * MIN_LOGS_FOR_WEIGHTS   — global activation threshold (50 by default)
    * MIN_LOGS_PER_REGIME    — per-regime activation threshold (20)
    * BASELINE_WEIGHT        — per-type floor before normalisation (0.1)
    * compute_mutation_weights(regime_type=None) → {type: weight} | None
    * get_evolution_stats(regime_type=None)      → full diagnostic rollup
    * weighted_select_types(weights, k, rng=None) → list[str]
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from engines.mutation_engine import (
    MUTATION_TYPES,
    STABILITY_COLL,
    get_stability_stats,
)
from engines.db import get_db


# ── Tunables ──────────────────────────────────────────────────────────

MIN_LOGS_FOR_WEIGHTS = 50
MIN_LOGS_PER_REGIME = 20           # Phase 16 — per-regime activation floor
BASELINE_WEIGHT = 0.10             # floor so no type ever drops to 0
# Score = SUCCESS_WEIGHT * success_rate + PF_WEIGHT * normalised_avg_pf
SUCCESS_WEIGHT = 0.6
PF_WEIGHT = 0.4
# avg_pf gets clipped then divided by this — PF >= PF_CAP → full credit
PF_CAP = 2.0


# ── Scoring ───────────────────────────────────────────────────────────

def _normalise_pf(avg_pf) -> float:
    if avg_pf is None:
        return 0.0
    try:
        v = float(avg_pf)
    except (TypeError, ValueError):
        return 0.0
    if v <= 0:
        return 0.0
    if v >= PF_CAP:
        return 1.0
    return v / PF_CAP


def _score_row(row: dict) -> float:
    """Combine success_rate + normalised avg_pf into a single 0..1 score."""
    success = float(row.get("success_rate") or 0.0)
    pf_norm = _normalise_pf(row.get("avg_pf"))
    return max(0.0, SUCCESS_WEIGHT * success + PF_WEIGHT * pf_norm)


def _top_reason(row: dict) -> Optional[str]:
    reasons = row.get("rejection_reasons") or {}
    if not reasons:
        return None
    return max(reasons.items(), key=lambda kv: kv[1])[0]


# ── Regime-filtered rollup (Phase 16) ────────────────────────────────

async def _stability_rollup(regime_type: Optional[str] = None) -> Dict[str, object]:
    """Produce the same rollup shape as `get_stability_stats()` but
    optionally scoped to a single `regime_type`. When `regime_type` is
    None this delegates to the unfiltered helper (Phase 15 behaviour).
    """
    if regime_type is None:
        return await get_stability_stats()

    db = get_db()
    rollup: Dict[str, Dict[str, object]] = {}
    global_reasons: Dict[str, int] = {}
    total = 0
    q = {"regime_type": regime_type}
    async for e in db[STABILITY_COLL].find(q, {"_id": 0}):
        total += 1
        mt = e.get("mutation_type") or "unknown"
        row = rollup.setdefault(mt, {
            "mutation_type": mt, "count": 0, "saved": 0,
            "pf_sum": 0.0, "pf_n": 0,
            "trades_sum": 0, "trades_n": 0,
            "dd_sum": 0.0, "dd_n": 0,
            "rejection_reasons": {},
        })
        row["count"] += 1
        if e.get("auto_save_status") == "saved":
            row["saved"] += 1
        else:
            reason = e.get("rejection_reason") or e.get("auto_save_status")
            if reason:
                # Lean on the same buckets mutation_engine uses so the
                # per-regime distribution matches the global one.
                from engines.mutation_engine import _bucket_rejection_reason
                bucket = _bucket_rejection_reason(
                    e.get("rejection_reason"), e.get("auto_save_status"),
                )
                if bucket:
                    row["rejection_reasons"][bucket] = (
                        row["rejection_reasons"].get(bucket, 0) + 1
                    )
                    global_reasons[bucket] = global_reasons.get(bucket, 0) + 1
        pf = e.get("profit_factor")
        if isinstance(pf, (int, float)):
            row["pf_sum"] += float(pf); row["pf_n"] += 1
        tr = e.get("trades")
        if isinstance(tr, int):
            row["trades_sum"] += tr; row["trades_n"] += 1
        dd = e.get("max_drawdown")
        if isinstance(dd, (int, float)):
            row["dd_sum"] += float(dd); row["dd_n"] += 1

    out: List[Dict[str, object]] = []
    for mt, r in rollup.items():
        out.append({
            "mutation_type": mt,
            "count": r["count"],
            "saved": r["saved"],
            "success_rate": (
                round(r["saved"] / r["count"], 4) if r["count"] else 0.0
            ),
            "avg_pf": round(r["pf_sum"] / r["pf_n"], 4) if r["pf_n"] else None,
            "avg_trades": (
                round(r["trades_sum"] / r["trades_n"], 2) if r["trades_n"] else None
            ),
            "avg_drawdown": (
                round(r["dd_sum"] / r["dd_n"], 4) if r["dd_n"] else None
            ),
            "rejection_reasons": dict(r["rejection_reasons"]),
        })
    out.sort(
        key=lambda x: (x["success_rate"], x["avg_pf"] if x["avg_pf"] is not None else -1),
        reverse=True,
    )
    return {"by_type": out, "total_logs": total, "rejection_reasons": global_reasons}


# ── Public: weights ───────────────────────────────────────────────────

async def compute_mutation_weights(
    regime_type: Optional[str] = None,
) -> Optional[Dict[str, float]]:
    """Return a normalised {mutation_type: weight} dict.

    Phase 15 — global weights: callable with `regime_type=None`. Returns
    `None` when the stability log has fewer than `MIN_LOGS_FOR_WEIGHTS`
    entries.

    Phase 16 — regime-specific weights: pass a concrete regime string
    (e.g. "trending"). Returns `None` when the filtered log has fewer
    than `MIN_LOGS_PER_REGIME` entries so callers can fall back to
    global weights.

    Every declared mutation_type (from `MUTATION_TYPES`) appears in the
    dict with weight >= (BASELINE_WEIGHT normalised). Weights sum to 1.
    """
    stats = await _stability_rollup(regime_type)
    total = int(stats.get("total_logs") or 0)
    threshold = MIN_LOGS_PER_REGIME if regime_type else MIN_LOGS_FOR_WEIGHTS
    if total < threshold:
        return None

    by_type = {row["mutation_type"]: row for row in (stats.get("by_type") or [])}

    raw: Dict[str, float] = {}
    for mtype in MUTATION_TYPES:
        row = by_type.get(mtype)
        score = _score_row(row) if row else 0.0
        raw[mtype] = BASELINE_WEIGHT + score

    total_raw = sum(raw.values()) or 1.0
    return {k: round(v / total_raw, 6) for k, v in raw.items()}


async def get_evolution_stats(
    regime_type: Optional[str] = None,
) -> Dict[str, object]:
    """Diagnostic rollup surfaced via `GET /api/mutation/evolution/stats`.

    Shape:
        {
          active: bool,
          min_logs_for_weights: int,       # threshold that was applied
          total_logs: int,
          regime_type: str | None,         # echoed back
          weights: [
            {mutation_type, weight, score,
             success_rate, avg_pf, avg_trades, avg_drawdown,
             count, saved, top_rejection_reason}, ...
          ],
          rejection_reasons: { bucket: count },
          note: str
        }
    """
    stats = await _stability_rollup(regime_type)
    total = int(stats.get("total_logs") or 0)
    threshold = MIN_LOGS_PER_REGIME if regime_type else MIN_LOGS_FOR_WEIGHTS
    active = total >= threshold

    by_type = {row["mutation_type"]: row for row in (stats.get("by_type") or [])}

    raw: Dict[str, float] = {}
    scores: Dict[str, float] = {}
    for mtype in MUTATION_TYPES:
        row = by_type.get(mtype)
        s = _score_row(row) if row else 0.0
        scores[mtype] = s
        raw[mtype] = BASELINE_WEIGHT + s

    total_raw = sum(raw.values()) or 1.0
    normalised = {k: v / total_raw for k, v in raw.items()}

    rows: List[Dict[str, object]] = []
    for mtype in MUTATION_TYPES:
        r = by_type.get(mtype) or {}
        rows.append({
            "mutation_type": mtype,
            "weight": round(normalised[mtype], 6),
            "score": round(scores[mtype], 6),
            "count": int(r.get("count") or 0),
            "saved": int(r.get("saved") or 0),
            "success_rate": r.get("success_rate"),
            "avg_pf": r.get("avg_pf"),
            "avg_trades": r.get("avg_trades"),
            "avg_drawdown": r.get("avg_drawdown"),
            "top_rejection_reason": _top_reason(r),
        })
    rows.sort(key=lambda x: x["weight"], reverse=True)

    scope = f"regime={regime_type!r}" if regime_type else "global"
    if active:
        note = f"Weights active ({scope}) — mutation pipeline will use them."
    else:
        note = (
            f"Need {threshold - total} more logs ({scope}) before weights "
            f"activate. Pipeline falls back to "
            f"{'global weights or legacy selection' if regime_type else 'legacy selection'}."
        )

    return {
        "active": active,
        "min_logs_for_weights": threshold,
        "total_logs": total,
        "regime_type": regime_type,
        "weights": rows,
        "rejection_reasons": stats.get("rejection_reasons") or {},
        "note": note,
    }


# ── Public: weighted sampling ─────────────────────────────────────────

def weighted_select_types(
    weights: Dict[str, float],
    k: int,
    rng: Optional[random.Random] = None,
) -> List[str]:
    """Sample up to `k` distinct mutation_types without replacement, biased
    by `weights`. Types with zero/negative weight fall through to the
    remaining bucket only if nothing else is pickable.

    `rng` — pass a seeded `random.Random` for deterministic tests; default
    uses the module-level random.
    """
    if k <= 0 or not weights:
        return []
    r = rng or random

    pool = [(t, max(0.0, float(w))) for t, w in weights.items() if t in MUTATION_TYPES]
    if not pool:
        # Fallback: uniform over catalogue.
        catalogue = list(MUTATION_TYPES)
        r.shuffle(catalogue)
        return catalogue[: min(k, len(catalogue))]

    chosen: List[str] = []
    while pool and len(chosen) < k:
        total = sum(w for _, w in pool)
        if total <= 0:
            # All remaining weights zero → uniform over leftovers.
            remaining = [t for t, _ in pool]
            r.shuffle(remaining)
            needed = k - len(chosen)
            chosen.extend(remaining[:needed])
            break
        x = r.random() * total
        acc = 0.0
        pick_idx = 0
        for i, (_t, w) in enumerate(pool):
            acc += w
            if x <= acc:
                pick_idx = i
                break
        t, _w = pool.pop(pick_idx)
        chosen.append(t)
    return chosen
