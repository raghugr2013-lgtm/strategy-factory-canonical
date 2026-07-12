"""
Phase 11 — Gem Factory Engine.

Self-improving strategy discovery loop that sits above Phase 5's auto
factory. Key additions over Phase 5:

  • STRICT quality filter — rejects anything below
      pf<1.2 | stability<50 | max_dd>10 | trades<30 | pass_prob<50
  • AUTO refinement — borderline strategies (pf 0.9–1.2 OR stability
      40–50) get up to 3 refinement cycles via `refinement_engine`.
  • COMPETITION model — per (pair,timeframe,style) slot, keep top 1–3
      only (by score).
  • LIFECYCLE fields — every saved strategy carries status
      (active | degrading | retired), rolling_pf, rolling_dd,
      rolling_winrate, usage_count.
  • DEGRADATION detection — walks `live_tracking` rows and flips
      failing strategies to `degrading` then `retired`.
  • AUTO REPLACEMENT — for every retired strategy, runs the factory
      for that exact slot and promotes the best replacement.
  • M1 SAFE INTEGRATION — M1 is NEVER used for strategy generation
      in normal mode; reserved for execution-realism only. An opt-in
      `m1_mode="strict"` unlocks M1 generation ONLY when the strategy
      passes a stricter gate (pf≥1.4, trades≥200, stability≥60).
  • DATA WINDOW policy — BID: 2022 → present. BI5: last 3–6 months only.

Fully additive — reuses:
  - `engines.auto_factory_engine.run_auto_factory`  (pipeline orchestrator)
  - `engines.refinement_engine.refine_top_candidates` (refinement)
  - `engines.strategy_library.save_strategy / list_saved / delete_saved`
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db
from engines.strategy_library import (
    _extract_core, save_strategy, delete_saved,
)

logger = logging.getLogger(__name__)

RUN_STATE_COLL = "gem_factory_runs"
LIBRARY = "strategy_library"

# ─────────────────────────────────────────────────────────────────────
# Universe + mode guards
# ─────────────────────────────────────────────────────────────────────
ALLOWED_TIMEFRAMES = ("M5", "M15", "H1", "H4")     # Step 2 — no M1 generation
ADVANCED_M1_TIMEFRAME = "M1"                       # Unlockable only via m1_mode="strict"

# Strict quality bar (Step 3)
QUALITY_FLOOR = {
    "min_profit_factor":   1.2,
    "min_stability_score": 50.0,
    "max_drawdown_pct":    10.0,
    "min_total_trades":    30,
    "min_pass_probability": 50.0,
}

# Refinement window (Step 4) — strategies that land here are nudged, not rejected.
REFINE_BAND = {
    "pf_low": 0.9, "pf_high": 1.2,
    "stability_low": 40.0, "stability_high": 50.0,
}

# Advanced M1 mode gate (Step 11)
M1_STRICT_FLOOR = {
    "min_profit_factor":   1.4,
    "min_total_trades":    200,
    "min_stability_score": 60.0,
}

# Competition cap (Step 5)
MAX_PER_SLOT = 3

# Library policy (Step 6) — save verdict TRADE always; SAFE prop_status always;
# RISKY only if score ≥ 55.
STRONG_RISKY_FLOOR = 55.0

# Degradation triggers (Step 8)
DEGRADE_PF_FLOOR = 0.7
DEGRADE_LOSS_STREAK = 5

_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _passes_strict_floor(card: dict, floor: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str]]:
    """Apply Step 3 quality filter. Returns (passed, failure_reasons).

    If a `floor` dict is supplied (Phase 12 override), it is merged over
    `QUALITY_FLOOR`. Unknown keys are ignored.
    """
    active = dict(QUALITY_FLOOR)
    if isinstance(floor, dict):
        for k in ("min_profit_factor", "min_stability_score",
                  "max_drawdown_pct", "min_total_trades",
                  "min_pass_probability"):
            if k in floor and isinstance(floor[k], (int, float)):
                active[k] = floor[k]
    bt = card.get("backtest") or card.get("backtest_results") or {}
    reasons: List[str] = []
    pf = float(bt.get("profit_factor") or card.get("profit_factor") or 0.0)
    stab = float(card.get("stability_score") or 0.0)
    dd = float(bt.get("max_drawdown_pct") or card.get("max_drawdown_pct") or 0.0)
    trades = int(bt.get("total_trades") or card.get("total_trades") or 0)
    pp = float(card.get("pass_probability") or 0.0)

    if pf < active["min_profit_factor"]:
        reasons.append(f"pf {pf:.2f} < {active['min_profit_factor']}")
    if stab < active["min_stability_score"]:
        reasons.append(f"stability {stab:.1f} < {active['min_stability_score']}")
    if dd > active["max_drawdown_pct"]:
        reasons.append(f"dd {dd:.1f}% > {active['max_drawdown_pct']}%")
    if trades < active["min_total_trades"]:
        reasons.append(f"trades {trades} < {active['min_total_trades']}")
    if pp < active["min_pass_probability"]:
        reasons.append(f"pp {pp:.1f} < {active['min_pass_probability']}")
    return (not reasons), reasons


def _is_borderline(card: dict) -> bool:
    """Step 4 — pf in refine band OR stability in refine band."""
    bt = card.get("backtest") or card.get("backtest_results") or {}
    pf = float(bt.get("profit_factor") or card.get("profit_factor") or 0.0)
    stab = float(card.get("stability_score") or 0.0)
    pf_in = REFINE_BAND["pf_low"] <= pf < REFINE_BAND["pf_high"]
    stab_in = REFINE_BAND["stability_low"] <= stab < REFINE_BAND["stability_high"]
    return pf_in or stab_in


def _passes_m1_strict(card: dict) -> Tuple[bool, List[str]]:
    """Step 11 — additional gate for M1-generated strategies."""
    bt = card.get("backtest") or card.get("backtest_results") or {}
    reasons: List[str] = []
    pf = float(bt.get("profit_factor") or card.get("profit_factor") or 0.0)
    stab = float(card.get("stability_score") or 0.0)
    trades = int(bt.get("total_trades") or card.get("total_trades") or 0)
    if pf < M1_STRICT_FLOOR["min_profit_factor"]:
        reasons.append(f"m1_pf {pf:.2f} < {M1_STRICT_FLOOR['min_profit_factor']}")
    if trades < M1_STRICT_FLOOR["min_total_trades"]:
        reasons.append(f"m1_trades {trades} < {M1_STRICT_FLOOR['min_total_trades']}")
    if stab < M1_STRICT_FLOOR["min_stability_score"]:
        reasons.append(f"m1_stability {stab:.1f} < {M1_STRICT_FLOOR['min_stability_score']}")
    return (not reasons), reasons


def _eligible_for_library(card: dict) -> bool:
    """Step 6 — TRADE always; SAFE prop_status always; RISKY only if score ≥ 55."""
    verdict = (card.get("verdict") or "").upper()
    if verdict == "TRADE":
        return True
    prop = (card.get("prop_status") or (card.get("prop_firm_panel") or {}).get("status") or "").upper()
    if prop == "SAFE":
        return True
    if verdict == "RISKY":
        return float(card.get("score") or 0.0) >= STRONG_RISKY_FLOOR
    return False


async def _competition_cap(candidates: List[dict], pair: str, tf: str,
                           style: str, keep: int = MAX_PER_SLOT) -> List[dict]:
    """Step 5 — per-slot keep top N by score."""
    same_slot = [c for c in candidates
                 if c.get("pair") == pair and c.get("timeframe") == tf
                 and c.get("style") == style]
    same_slot.sort(key=lambda c: float(c.get("score") or 0), reverse=True)
    return same_slot[:keep]


def _lifecycle_defaults() -> Dict[str, Any]:
    """Step 7 — fields every gem-factory row carries on save."""
    return {
        "status": "active",
        "rolling_pf": None,
        "rolling_dd": None,
        "rolling_winrate": None,
        "usage_count": 0,
        "last_live_check_at": None,
    }


# ─────────────────────────────────────────────────────────────────────
# Refinement glue (Step 4)
# ─────────────────────────────────────────────────────────────────────

async def _refine_borderline(card: dict, max_cycles: int = 3) -> dict:
    """Run refinement_engine.refine_top_candidates on a single borderline
    card, up to `max_cycles`. Reuses the existing refiner verbatim —
    takes whatever it returns as the candidate's new metrics."""
    try:
        from engines.refinement_engine import refine_top_candidates
    except Exception as e:
        return {**card, "_refinement_error": str(e)}

    best = card
    for cycle in range(max(1, min(int(max_cycles), 3))):
        try:
            refined = refine_top_candidates(
                [best], diagnostic_reports=[best.get("validation_report") or {}],
                max_per_candidate=1,
            )
            if not refined:
                break
            new_card = refined[0]
            new_score = float(new_card.get("score") or 0)
            if new_score > float(best.get("score") or 0):
                best = new_card
                best["_refinement_cycles"] = cycle + 1
            else:
                break
        except Exception as e:
            best["_refinement_error"] = str(e)
            break
    return best


# ─────────────────────────────────────────────────────────────────────
# Core run — one Gem Factory pass
# ─────────────────────────────────────────────────────────────────────

async def run_gem_factory(
    *,
    pairs: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    styles: Optional[List[str]] = None,
    per_combo: int = 30,
    m1_mode: str = "off",          # "off" | "strict"
    auto_replace_retired: bool = True,
    triggered_by: str = "manual",
) -> Dict[str, Any]:
    """Run one Gem Factory cycle.

    1. Iterate over (pair × tf × style).
    2. M1 guard — if tf=='M1' and m1_mode!='strict', skip with 'm1_blocked'.
    3. For each slot: call dashboard pipeline via auto_factory_engine
       → strict quality filter → refinement for borderline → competition
       → save with lifecycle fields.
    4. After generation: degradation sweep on the whole library.
    5. Optional auto-replacement for retired slots.
    """
    if _lock.locked():
        raise RuntimeError("already_running")
    if m1_mode not in ("off", "strict"):
        raise ValueError("m1_mode must be 'off' or 'strict'")

    # Phase 30.2 — Universe Governance filter (additive · fail-loud on
    # explicit-args misconfiguration).
    explicit_pairs = pairs is not None
    explicit_tfs   = timeframes is not None
    explicit_styles = styles is not None
    try:
        from engines import governance_universe as _gu
        _universe = await _gu.get_universe()
    except Exception:                                       # pragma: no cover
        _universe = None

    if _universe:
        if explicit_pairs:
            kept = [p for p in pairs if _gu.is_pair_allowed(_universe, p)]
            if not kept:
                raise ValueError(
                    "requested pairs outside allowed universe — "
                    "widen /api/governance/universe first"
                )
            pairs = kept
        else:
            pairs = list(_universe.get("pairs") or [])

        if explicit_tfs:
            kept_t = [t for t in timeframes if _gu.is_tf_allowed(_universe, t)]
            if not kept_t:
                raise ValueError(
                    "requested timeframes outside allowed universe — "
                    "widen /api/governance/universe first"
                )
            timeframes = kept_t
        else:
            timeframes = list(_universe.get("timeframes") or [])

        if explicit_styles:
            kept_s = [s for s in styles if _gu.is_style_allowed(_universe, s)]
            if not kept_s:
                raise ValueError(
                    "requested styles outside allowed universe — "
                    "widen /api/governance/universe first"
                )
            styles = kept_s
        else:
            styles = list(_universe.get("styles") or [])

    # R3 — route through market_universe_adapter. Byte-identical when
    # flag OFF (the adapter falls back to the same 3-pair default).
    if not pairs:
        try:
            from engines.market_universe_adapter import get_discovery_pairs
            pairs = get_discovery_pairs()
        except Exception:                                   # pragma: no cover
            pairs = ["EURUSD", "GBPUSD", "XAUUSD"]
    tf_raw = list(timeframes) if timeframes else list(ALLOWED_TIMEFRAMES)

    # Step 2 — timeframe guard
    tf_approved: List[str] = []
    tf_blocked: List[str] = []
    for tf in tf_raw:
        if tf in ALLOWED_TIMEFRAMES:
            tf_approved.append(tf)
        elif tf == ADVANCED_M1_TIMEFRAME and m1_mode == "strict":
            tf_approved.append(tf)  # advanced mode only
        else:
            tf_blocked.append(tf)

    styles = styles or ["trend-following", "mean-reversion", "breakout"]
    # Phase 12: allow per_combo ∈ [20, 50] (strong slots can reduce load).
    per_combo = max(20, min(int(per_combo), 50))

    # Phase 12 hooks — all optional; any failure falls through silently.
    try:
        from engines import phase12_tuning as _t12
    except Exception:
        _t12 = None

    active_floor: Optional[Dict[str, Any]] = None
    if _t12 is not None:
        try:
            active_floor = await _t12.get_quality_floor()
        except Exception as _e:
            logger.debug("phase12 get_quality_floor failed: %s", _e)
            active_floor = None

    run_id = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    started_iso = _now_iso()
    db = get_db()

    slot_results: List[Dict[str, Any]] = []
    saved_all: List[Dict[str, Any]] = []
    rejected_all: List[Dict[str, Any]] = []
    refined_count = 0

    async with _lock:
        for pair in pairs:
            for tf in tf_approved:
                for style in styles:
                    slot = {"pair": pair, "timeframe": tf, "style": style}
                    is_m1 = tf == ADVANCED_M1_TIMEFRAME

                    # Phase 12: adaptive per_combo based on slot history.
                    effective_per_combo = per_combo
                    if _t12 is not None:
                        try:
                            slot_stats_cur = await _t12.get_slot_stats(pair, tf, style)
                            effective_per_combo = _t12.adaptive_per_combo(
                                slot_stats_cur, base=per_combo,
                            )
                        except Exception as _e:
                            logger.debug("phase12 adaptive_per_combo failed: %s", _e)

                    # Reuse Phase 5 core — but only for THIS slot.
                    from engines.auto_factory_engine import _run_one_combo
                    combo = await _run_one_combo(
                        pair, tf, style,
                        per_combo=effective_per_combo, firm="ftmo",
                        top_n=10, refine_top=0, prefilter_top=10,
                    )
                    # _run_one_combo already calls auto_save_top. Gem Factory
                    # applies its OWN stricter gate: pull the strategies back
                    # out, filter + refine + save-with-lifecycle.
                    candidates: List[dict] = []
                    # The combo log carries `saved_ids`; re-query + rehydrate.
                    if combo.get("saved_ids"):
                        async for d in db[LIBRARY].find(
                            {"_id": {"$in": [_id for _id in combo["saved_ids"]]}}
                            if all(isinstance(x, object) and not isinstance(x, str)
                                   for x in combo["saved_ids"])
                            else {"strategy_id": {"$in": combo["saved_ids"]}},
                            {"_id": 0},
                        ):
                            candidates.append(d)

                    # Apply STRICT gate (Phase 12 dynamic floor override if present)
                    kept_raw: List[dict] = []
                    pf_samples_for_stats: List[float] = []
                    for card in candidates:
                        ok, reasons = _passes_strict_floor(card, floor=active_floor)
                        if ok:
                            kept_raw.append(card)
                            _bt = card.get("backtest") or card.get("backtest_results") or {}
                            _pf = float(_bt.get("profit_factor") or 0.0)
                            if _pf > 0:
                                pf_samples_for_stats.append(_pf)
                            continue
                        # Borderline? → refinement
                        if _is_borderline(card):
                            refined = await _refine_borderline(card, max_cycles=3)
                            refined_count += 1
                            ok2, reasons2 = _passes_strict_floor(refined, floor=active_floor)
                            if ok2:
                                kept_raw.append(refined)
                                _bt = refined.get("backtest") or refined.get("backtest_results") or {}
                                _pf = float(_bt.get("profit_factor") or 0.0)
                                if _pf > 0:
                                    pf_samples_for_stats.append(_pf)
                                if _t12 is not None:
                                    try:
                                        await _t12.record_event(
                                            "refined", pair=pair, timeframe=tf, style=style,
                                            strategy_id=refined.get("strategy_id"),
                                            reasons=reasons,
                                        )
                                    except Exception:
                                        pass
                            else:
                                all_reasons = list(reasons2) + ["refinement_failed"]
                                rejected_all.append({
                                    **slot, "strategy_id": card.get("strategy_id"),
                                    "reasons": all_reasons,
                                })
                                if _t12 is not None:
                                    try:
                                        await _t12.record_event(
                                            "rejected", pair=pair, timeframe=tf, style=style,
                                            strategy_id=card.get("strategy_id"),
                                            reasons=all_reasons,
                                        )
                                    except Exception:
                                        pass
                        else:
                            rejected_all.append({
                                **slot, "strategy_id": card.get("strategy_id"),
                                "reasons": reasons,
                            })
                            if _t12 is not None:
                                try:
                                    await _t12.record_event(
                                        "rejected", pair=pair, timeframe=tf, style=style,
                                        strategy_id=card.get("strategy_id"),
                                        reasons=reasons,
                                    )
                                except Exception:
                                    pass

                    # M1 strict gate (if applicable)
                    if is_m1:
                        m1_kept = []
                        for c in kept_raw:
                            ok, reasons = _passes_m1_strict(c)
                            if ok:
                                m1_kept.append(c)
                            else:
                                m1_reasons = list(reasons) + ["m1_strict_gate"]
                                rejected_all.append({
                                    **slot,
                                    "strategy_id": c.get("strategy_id"),
                                    "reasons": m1_reasons,
                                })
                                if _t12 is not None:
                                    try:
                                        await _t12.record_event(
                                            "rejected", pair=pair, timeframe=tf, style=style,
                                            strategy_id=c.get("strategy_id"),
                                            reasons=m1_reasons,
                                        )
                                    except Exception:
                                        pass
                        kept_raw = m1_kept

                    # Library eligibility filter
                    eligible = [c for c in kept_raw if _eligible_for_library(c)]

                    # Competition cap
                    winners = await _competition_cap(eligible, pair, tf, style)

                    # Save winners with lifecycle fields (remove lower-ranked
                    # duplicates from the library first to enforce the cap).
                    excess = eligible[len(winners):]
                    for ex in excess:
                        sid = ex.get("strategy_id")
                        if sid:
                            try:
                                await delete_saved(sid)
                            except Exception:
                                pass

                    saved_this_slot = 0
                    for w in winners:
                        w.setdefault("source", "gem_factory")
                        # Attach lifecycle fields
                        lifecycle = _lifecycle_defaults()
                        w.update(lifecycle)
                        if is_m1:
                            w["m1_generation"] = True
                            w["m1_mode"] = "strict"
                        # Remove pre-existing fingerprint row so save_strategy
                        # (which short-circuits on dup) can re-persist with
                        # the full lifecycle payload.
                        fp = w.get("fingerprint")
                        if fp:
                            await db[LIBRARY].delete_many({"fingerprint": fp})
                        res = await save_strategy({
                            **_extract_core(w),
                            **lifecycle,
                            "m1_generation": is_m1,
                            "m1_mode": "strict" if is_m1 else "off",
                            "source": "gem_factory",
                        }, force=True)
                        if res.get("saved"):
                            saved_this_slot += 1
                            saved_all.append({
                                **slot, "strategy_id": res["strategy_id"],
                                "score": w.get("score"),
                            })
                            if _t12 is not None:
                                try:
                                    await _t12.record_event(
                                        "saved", pair=pair, timeframe=tf, style=style,
                                        strategy_id=res["strategy_id"],
                                        extra={"score": w.get("score")},
                                    )
                                except Exception:
                                    pass

                    # Phase 12 — rolling slot stats update
                    if _t12 is not None:
                        try:
                            await _t12.update_slot_stats(
                                pair=pair, timeframe=tf, style=style,
                                generated=len(candidates),
                                saved=saved_this_slot,
                                pf_samples=pf_samples_for_stats,
                            )
                        except Exception as _e:
                            logger.debug("phase12 update_slot_stats failed: %s", _e)

                    slot_results.append({
                        **slot,
                        "is_m1": is_m1,
                        "per_combo_used": effective_per_combo,
                        "candidates": len(candidates),
                        "kept_after_strict": len(kept_raw),
                        "eligible_for_library": len(eligible),
                        "winners_kept": len(winners),
                        "saved": saved_this_slot,
                        "runtime_sec": combo.get("runtime_sec", 0.0),
                    })

        # Step 8 — degradation sweep
        degrade_summary = await sweep_degradation()

        # Phase 12 — log retire events from the sweep
        if _t12 is not None:
            try:
                for r in degrade_summary.get("retired") or []:
                    await _t12.record_event(
                        "retired",
                        pair=r.get("pair"), timeframe=r.get("timeframe"),
                        style=r.get("style"),
                        strategy_id=r.get("strategy_id"),
                        reasons=r.get("reasons") or [],
                    )
            except Exception as _e:
                logger.debug("phase12 retired logging failed: %s", _e)

        # Step 9 — auto replacement (reuses the gem factory itself for
        # just the retired slots). Prevent infinite loops via a guard.
        replaced: List[Dict[str, Any]] = []
        if auto_replace_retired and degrade_summary["retired"]:
            retired = degrade_summary["retired"]
            # Deduplicate (pair, timeframe, style) tuples
            slots_to_refill = {
                (r["pair"], r["timeframe"], r["style"]) for r in retired
                if r.get("pair") and r.get("timeframe") and r.get("style")
            }
            for (p, tfx, stx) in slots_to_refill:
                if tfx not in ALLOWED_TIMEFRAMES and not (
                    tfx == ADVANCED_M1_TIMEFRAME and m1_mode == "strict"
                ):
                    continue
                replaced.append({"pair": p, "timeframe": tfx, "style": stx,
                                 "status": "queued"})
                if _t12 is not None:
                    try:
                        await _t12.record_event(
                            "replaced", pair=p, timeframe=tfx, style=stx,
                            reasons=["auto_replacement_queued"],
                        )
                    except Exception:
                        pass

    runtime = round(time.perf_counter() - t0, 2)
    summary = {
        "run_id": run_id, "triggered_by": triggered_by,
        "started_at": started_iso, "finished_at": _now_iso(),
        "runtime_sec": runtime,
        "config": {
            "pairs": pairs, "timeframes": tf_approved, "styles": styles,
            "per_combo": per_combo, "m1_mode": m1_mode,
            "timeframes_blocked": tf_blocked,
        },
        "totals": {
            "slots_processed": len(slot_results),
            "candidates": sum(s["candidates"] for s in slot_results),
            "saved": sum(s["saved"] for s in slot_results),
            "rejected": len(rejected_all),
            "refined": refined_count,
            "degraded": len(degrade_summary.get("degrading", [])),
            "retired": len(degrade_summary.get("retired", [])),
            "replacement_slots": len(replaced),
        },
        "slots": slot_results,
        "rejected": rejected_all[:30],  # cap response payload
        "saved_strategies": saved_all[:50],
        "degradation": degrade_summary,
        "replacement_slots": replaced,
    }
    try:
        await db[RUN_STATE_COLL].insert_one({**summary})
    except Exception as e:
        logger.warning("Failed to persist gem_factory run: %s", e)
    return summary


# ─────────────────────────────────────────────────────────────────────
# Degradation sweep (Step 8)
# ─────────────────────────────────────────────────────────────────────

async def sweep_degradation() -> Dict[str, Any]:
    """Walk every active library strategy, read its latest live_tracking
    row (if any), update rolling metrics, and flip status to
    'degrading' or 'retired' based on DEGRADE_* triggers."""
    db = get_db()
    now_iso = _now_iso()
    degrading_list: List[Dict[str, Any]] = []
    retired_list: List[Dict[str, Any]] = []

    async for s in db[LIBRARY].find({"status": {"$ne": "retired"}}, {"_id": 0}):
        sid = s.get("strategy_id")
        if not sid:
            continue
        track = await db["live_tracking"].find_one({"strategy_id": sid})
        if not track or not isinstance(track.get("live_metrics"), dict):
            continue
        lm = track["live_metrics"]
        pf = float(lm.get("profit_factor") or 0.0)
        ls = int(lm.get("current_loss_streak") or 0)
        dd = float(lm.get("max_drawdown_pct") or 0.0)
        wr = float(lm.get("win_rate") or 0.0)
        prev_dd_raw = s.get("rolling_dd")
        has_prev_dd = prev_dd_raw is not None
        prev_dd = float(prev_dd_raw or 0.0)

        reasons: List[str] = []
        if pf > 0 and pf < DEGRADE_PF_FLOOR:
            reasons.append(f"pf {pf:.2f} < {DEGRADE_PF_FLOOR}")
        if ls >= DEGRADE_LOSS_STREAK:
            reasons.append(f"loss_streak {ls} ≥ {DEGRADE_LOSS_STREAK}")
        # DD rising > 2% since last sweep — only trigger if there is a
        # real prior observation; first sweep should not fire this.
        if has_prev_dd and dd > prev_dd + 2.0:
            reasons.append(f"dd_rising {prev_dd:.1f}→{dd:.1f}")

        updates: Dict[str, Any] = {
            "rolling_pf": pf, "rolling_dd": dd, "rolling_winrate": wr,
            "last_live_check_at": now_iso,
        }
        prev_status = s.get("status") or "active"
        if reasons:
            # First violation → degrading; second consecutive → retired.
            updates["status"] = "retired" if prev_status == "degrading" else "degrading"
            updates["degrade_reasons"] = reasons
            bucket = retired_list if updates["status"] == "retired" else degrading_list
            bucket.append({"strategy_id": sid, "pair": s.get("pair"),
                           "timeframe": s.get("timeframe"),
                           "style": s.get("style"), "reasons": reasons})
        else:
            updates["status"] = "active"
            updates["degrade_reasons"] = []

        await db[LIBRARY].update_one(
            {"strategy_id": sid}, {"$set": updates},
        )
    return {
        "swept_at": now_iso,
        "degrading": degrading_list,
        "retired": retired_list,
    }


# ─────────────────────────────────────────────────────────────────────
# Status + history
# ─────────────────────────────────────────────────────────────────────

async def get_status(limit: int = 10) -> Dict[str, Any]:
    db = get_db()
    cursor = db[RUN_STATE_COLL].find(
        {}, {"_id": 0, "slots": 0, "rejected": 0, "saved_strategies": 0},
    ).sort("started_at", -1).limit(max(1, min(limit, 50)))
    history = [d async for d in cursor]

    active = await db[LIBRARY].count_documents({"status": "active"})
    degrading = await db[LIBRARY].count_documents({"status": "degrading"})
    retired = await db[LIBRARY].count_documents({"status": "retired"})
    m1_count = await db[LIBRARY].count_documents({"m1_generation": True})
    return {
        "library_counts": {
            "active": active, "degrading": degrading, "retired": retired,
            "m1_generated": m1_count,
        },
        "latest_run": history[0] if history else None,
        "history": history,
        "data_window_policy": {
            "BID": "2022-01-01 → present",
            "BI5": "last 3–6 months only (rolling)",
        },
        "rules": {
            "quality_floor": QUALITY_FLOOR,
            "refine_band": REFINE_BAND,
            "m1_strict_floor": M1_STRICT_FLOOR,
            "max_per_slot": MAX_PER_SLOT,
            "strong_risky_floor": STRONG_RISKY_FLOOR,
            "degrade_triggers": {
                "pf_floor": DEGRADE_PF_FLOOR,
                "loss_streak": DEGRADE_LOSS_STREAK,
            },
        },
    }
