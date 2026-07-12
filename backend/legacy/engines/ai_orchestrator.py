"""
AI Orchestrator (Decision Engine) — Phase 22.

PURPOSE
-------
A small, deterministic, rule-based system manager that reduces manual
intervention during the discovery → optimisation → library-building
loop. It does ONE thing: read the current state of the factory, match
it against a fixed rule-book, and emit (optionally execute) a list of
recommended actions.

INTENTIONALLY RULE-BASED. No LLM, no heuristic weights, no learning
feedback. Every decision is a pure function of the observed state, so
behaviour is reproducible and debuggable.

Public surface (consumed by `api/orchestrator.py`):

    * observe_state(limit=5)       -> dict
    * decide(state)                -> list[Recommendation]
    * execute(actions)             -> list[Execution]
    * run_tick(execute=True|False) -> dict

Recommendation schema:
    {
      "rule_id":     str,          # stable rule identifier
      "action":      str,          # one of ACTION_TYPES
      "reason":      str,          # human-readable justification
      "params":      dict,         # action-specific payload
      "severity":    "info|warn|critical",
    }

Action catalogue (action names are contract):
    * "trigger_multi_cycle"   — POST-equivalent of /auto/multi-cycle/start
    * "stop_multi_cycle"      — POST /auto/multi-cycle/stop
    * "log_recommendation"    — advisory only (no side effect)
    * "promote_best_strategy" — surface best-of-latest-run for promotion

The orchestrator NEVER mutates the LLM prompt, eligibility thresholds,
or any engine defaults. It only twiddles the knobs that
`multi_cycle_runner.start_multi_cycle` exposes (cycles, batch_size,
scan, quality_threshold) plus advisory hints in log_recommendation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines import multi_cycle_runner as mcr
from engines.db import get_db
from engines.strategy_library import COLLECTION as LIB_COLL
from engines import env_priority

logger = logging.getLogger(__name__)

# ── Configurable thresholds (dev-tuned; deterministic) ──────────────
LOW_SAVE_WINDOW = 3                # look back this many runs
LOW_SAVE_RATIO_THRESHOLD = 0.0     # "no saves across N runs" → escalate
INSUFFICIENT_TRADES_SHARE = 0.5    # >50% of candidates rejected with it
LOW_PF_THRESHOLD = 1.0             # avg PF below → diversity bump
GOOD_STRATEGY_PF = 1.4             # avg PF at/above → "good cycle" signal
GOOD_STRATEGY_SCORE = 60.0         # library row score floor for promote
BATCH_SIZE_STEP = 2                # incremental bump per rule
BATCH_SIZE_CAP = 8                 # hard cap (matches StartRequest validator)

# Extended scan — used when the "diversity bump" rule fires. Strictly a
# subset of pairs that already have market_data loaded (see audit).
DIVERSITY_SCAN: Tuple[Tuple[str, str], ...] = (
    ("EURUSD", "H1"), ("EURUSD", "H4"),
    ("XAUUSD", "H1"), ("XAUUSD", "H4"),
    ("GBPUSD", "H1"), ("GBPUSD", "H4"),
    ("USDJPY", "H1"), ("USDJPY", "H4"),
)

ACTION_TYPES = {
    "trigger_multi_cycle",
    "stop_multi_cycle",
    "log_recommendation",
    "promote_best_strategy",
    # Phase 27.2 / G6 — autonomous lifecycle progression
    "evaluate_lifecycle_cohort",
    "auto_build_portfolio",
}

# G6 — when the elite cohort is large enough to seed/refresh a
# portfolio AND the system has not built one recently, the orchestrator
# emits an `auto_build_portfolio` action. These thresholds are the
# only G6 knobs; everything else is driven by the lifecycle gates.
AUTO_BUILD_MIN_ELITE = 3                # ≥ this many elite strategies needed
AUTO_BUILD_COOLDOWN_HOURS = 6           # don't rebuild more often than this
LIFECYCLE_TRANSITION_WINDOW_HOURS = 1   # window for promotion/demotion advisories

# Phase 30.1 · Δ3 — Autonomous Discovery Tick (RULE 12).
# DORMANT by default per operator decree. When enabled later, the rule
# evaluates survivor headroom + a rotating pair/TF target to decide if
# the orchestrator should auto-trigger a discovery cycle. Until then
# RULE 12 emits OBSERVATIONAL TELEMETRY only — every tick records:
#   • rule evaluation timestamp
#   • whether conditions passed
#   • trigger reason OR skip reason
#   • rotating pair/TF target
#   • survivor headroom snapshot
AUTONOMOUS_DISCOVERY_ENABLED = False
AUTONOMOUS_DISCOVERY_MIN_HEADROOM = 10   # survivor universe headroom needed
AUTONOMOUS_DISCOVERY_ROTATION: Tuple[Tuple[str, str], ...] = (
    ("EURUSD", "H1"), ("EURUSD", "H4"),
    ("XAUUSD", "H1"), ("XAUUSD", "H4"),
    ("GBPUSD", "H1"), ("GBPUSD", "H4"),
    ("USDJPY", "H1"), ("USDJPY", "H4"),
)


# ════════════════════════════════════════════════════════════════════
# OBSERVE
# ════════════════════════════════════════════════════════════════════

async def observe_state(limit: int = LOW_SAVE_WINDOW) -> Dict[str, Any]:
    """Pull a structured snapshot of the discovery system's health."""
    db = get_db()

    # 0. Adaptive feedback — pull stats from any cycles finished since last
    #    tick, update env_priority multipliers, then sample fresh envs to
    #    use for any autonomous trigger this tick.
    try:
        await env_priority.consume_recent_cycles()
    except Exception:
        logger.exception("[orchestrator] env_priority feedback failed")

    try:
        adaptive_scan = await env_priority.pick_environments(len(DIVERSITY_SCAN))
    except Exception:
        logger.exception("[orchestrator] env_priority sampling failed")
        adaptive_scan = []

    # 1. Live multi-cycle snapshot (in-memory; single source of truth).
    live = mcr.get_status()

    # 2. Last N persisted runs.
    recent_runs = await mcr.list_runs(limit=limit)

    # 3. Per-scan rollup — count saves, PF trend, rejection reasons.
    saves_per_run = []
    pfs_per_run = []
    for r in recent_runs:
        saved = 0
        pfs = []
        for c in (r.get("cycles") or []):
            saved += int(c.get("strategies_saved") or 0)
            bp = c.get("best_pf")
            if isinstance(bp, (int, float)):
                pfs.append(float(bp))
        saves_per_run.append(saved)
        if pfs:
            pfs_per_run.append(round(sum(pfs) / len(pfs), 3))

    # 4. Rejection-reason breakdown from auto_run_cycles (where every
    #    variant's auto_save_status + auto_save_reason is persisted).
    rej_window = []
    async for row in db["auto_run_cycles"].find(
        {}, {"_id": 0, "per_strategy": 1, "started_at": 1},
    ).sort("started_at", -1).limit(20):
        for s in (row.get("per_strategy") or []):
            st = s.get("auto_save_status")
            rs = s.get("auto_save_reason") or ""
            if st == "rejected" or st == "skipped":
                rej_window.append({"status": st, "reason": rs})

    rejection_breakdown = _bucket_rejections(rej_window)

    # 5. Library counts.
    lib_count = await db[LIB_COLL].count_documents({})
    lib_new_this_hour = await db[LIB_COLL].count_documents({
        "created_at": {"$gte": _one_hour_ago_iso()},
    })

    # 6. Best current strategy candidate (for promote rule).
    best_candidate = await db[LIB_COLL].find_one(
        {"score": {"$gte": GOOD_STRATEGY_SCORE}},
        {"_id": 0},
        sort=[("score", -1), ("created_at", -1)],
    )

    # 7. Phase 27.2 / G6 — lifecycle state snapshot.
    lifecycle = await _observe_lifecycle(db)

    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "live": {
            "status": live.get("status"),
            "run_id": live.get("run_id"),
            "current_cycle": live.get("current_cycle"),
            "total_cycles": live.get("total_cycles"),
        },
        "recent_runs": [
            {
                "run_id": r.get("run_id"),
                "status": r.get("status"),
                "started_at": r.get("started_at"),
                "finished_at": r.get("finished_at"),
                "cycles_completed": len(r.get("cycles") or []),
            }
            for r in recent_runs
        ],
        "saves_per_run": saves_per_run,
        "pfs_per_run": pfs_per_run,
        "avg_pf_recent": (
            round(sum(pfs_per_run) / len(pfs_per_run), 3)
            if pfs_per_run else None
        ),
        "total_saves_recent": sum(saves_per_run),
        "rejection_breakdown": rejection_breakdown,
        "library": {
            "total": lib_count,
            "new_last_hour": lib_new_this_hour,
        },
        "best_candidate": best_candidate,
        "adaptive_scan": adaptive_scan,
        "lifecycle": lifecycle,
    }


def _bucket_rejections(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    buckets = {
        "insufficient_trades": 0,
        "prop_status_fail": 0,
        "oos_gate_failed": 0,
        "weak_risky": 0,
        "data_missing": 0,
        "other": 0,
    }
    for it in items:
        r = (it.get("reason") or "").lower()
        if "insufficient_trades" in r:
            buckets["insufficient_trades"] += 1
        elif "status is fail" in r:
            buckets["prop_status_fail"] += 1
        elif "oos_gate_failed" in r:
            buckets["oos_gate_failed"] += 1
        elif "weak risky" in r:
            buckets["weak_risky"] += 1
        elif "data_missing" in r or "data missing" in r:
            buckets["data_missing"] += 1
        else:
            buckets["other"] += 1
    total = sum(buckets.values())
    return {
        "counts": buckets,
        "total": total,
        "top_reason": (
            max(buckets.items(), key=lambda kv: kv[1])[0] if total else None
        ),
    }


def _one_hour_ago_iso() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


# Phase 27.2 / G6 — lifecycle observation helpers ────────────────────

def _hours_ago_iso(hours: float) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(hours=float(hours))).isoformat()


async def _observe_lifecycle(db) -> Dict[str, Any]:
    """Bring lifecycle state into the orchestrator's observed snapshot.

    Cheap, additive — purely reads two collections that the lifecycle
    module owns:
      * ``strategy_lifecycle``         — current per-strategy state
      * ``strategy_lifecycle_history`` — transition audit log

    Failures fall through gracefully; the orchestrator never crashes
    because lifecycle observation is unavailable.
    """
    out: Dict[str, Any] = {
        "stage_counts":          {},
        "promotions_recent":     [],
        "demotions_recent":      [],
        "transitions_total":     0,
        "last_portfolio_built_at": None,
        "survivor_universe":     {},
        "allowed_universe":      None,        # Phase 30.2
    }
    try:
        from engines import strategy_lifecycle as lc
        out["stage_counts"] = await lc.cohort_stage_counts()
        since = _hours_ago_iso(LIFECYCLE_TRANSITION_WINDOW_HOURS)
        recent = await lc.recent_transitions(since_iso=since, limit=50)
        out["transitions_total"] = len(recent)
        for t in recent:
            from_rank = int(t.get("from_stage_rank") or 0)
            to_rank = int(t.get("to_stage_rank") or 0)
            entry = {
                "strategy_hash": t.get("strategy_hash"),
                "library_id":    t.get("library_id"),
                "from_stage":    t.get("from_stage"),
                "to_stage":      t.get("to_stage"),
                "transition_at": t.get("transition_at"),
            }
            if to_rank > from_rank:
                out["promotions_recent"].append(entry)
            elif to_rank < from_rank:
                out["demotions_recent"].append(entry)
    except Exception:
        logger.debug("[orchestrator] lifecycle observation failed", exc_info=True)
    # Phase 30.1 · Δ3 — survivor universe headroom snapshot for RULE 12.
    try:
        from engines import survivor_registry as sr
        uni = await sr.fetch_survivor_universe()
        out["survivor_universe"] = {
            "active_count": uni.get("active_count"),
            "cap":          uni.get("cap"),
            "headroom":     uni.get("headroom"),
            "over_cap":     uni.get("over_cap"),
        }
    except Exception:                                       # pragma: no cover
        logger.debug("[orchestrator] survivor universe snapshot failed",
                     exc_info=True)
    # Phase 30.2 — allowed research universe (operator-decreed boundary).
    # Stashed here so the sync `decide()` can filter without await.
    try:
        from engines import governance_universe as gu
        out["allowed_universe"] = await gu.get_universe()
    except Exception:                                       # pragma: no cover
        logger.debug("[orchestrator] allowed_universe fetch failed",
                     exc_info=True)
    # Last portfolio built — used by AUTO_BUILD_PORTFOLIO cooldown gate.
    try:
        last = await db["portfolios"].find_one(
            {}, {"_id": 0, "saved_at": 1, "built_at": 1, "portfolio_id": 1},
            sort=[("saved_at", -1)],
        )
        if last:
            out["last_portfolio_built_at"] = (
                last.get("saved_at") or last.get("built_at")
            )
    except Exception:                                       # pragma: no cover
        pass
    return out


# ════════════════════════════════════════════════════════════════════
# DECIDE — rule-book (ordered; first match wins per action slot)
# ════════════════════════════════════════════════════════════════════

def decide(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pure function: state → ordered list of recommendations.

    Rules are checked in order. A rule emits at most one recommendation.
    Multiple rules may fire in a single tick (e.g. "low PF" + "promote
    existing best"). The orchestrator layer upstream decides whether to
    execute all, just advisory ones, or just one.
    """
    recs: List[Dict[str, Any]] = []

    # RULE 0 — if a run is currently active, short-circuit with advisory.
    live_status = (state.get("live") or {}).get("status")
    if live_status == "running":
        recs.append(_rec(
            "RUN_ACTIVE",
            "log_recommendation",
            "A multi-cycle run is currently active — orchestrator will "
            "wait for completion before issuing new trigger actions.",
            {"live_status": live_status},
            "info",
        ))
        # We still emit downstream advisory rules (promote/log) but NOT
        # trigger_multi_cycle — guarded per-rule below.

    saves = state.get("total_saves_recent") or 0
    recent_runs = state.get("recent_runs") or []
    rej = (state.get("rejection_breakdown") or {})
    rej_counts = rej.get("counts") or {}
    rej_total = rej.get("total") or 0
    avg_pf = state.get("avg_pf_recent")
    best = state.get("best_candidate")

    # Adaptive scan (env_priority sampling) — falls back to the static
    # DIVERSITY_SCAN if env_priority returned nothing (cold start / all
    # tiers disabled). Manual `start_multi_cycle(scan=…)` calls are
    # untouched — only autonomous triggers below consume this list.
    adaptive_scan_pairs = state.get("adaptive_scan") or []
    if not adaptive_scan_pairs:
        adaptive_scan_pairs = list(DIVERSITY_SCAN)

    # Phase 30.2 · A2 — filter DIVERSITY_SCAN fallback through allowed
    # universe (adaptive_scan from env_priority is already filtered at
    # source — this is purely a cold-start safety net).
    allowed_universe = (state.get("lifecycle") or {}).get("allowed_universe")
    if allowed_universe:
        try:
            from engines import governance_universe as _gu
            filtered = _gu.intersect_scan(allowed_universe, adaptive_scan_pairs)
            if filtered:
                adaptive_scan_pairs = filtered
            # else: keep unfiltered list — operator universe excludes all
            # default cells; never silently black-hole the orchestrator.
        except Exception:                                   # pragma: no cover
            logger.debug("[orchestrator] universe filter A2 failed")

    diversity_scan_payload = [
        {"pair": p, "timeframe": tf} for p, tf in adaptive_scan_pairs
    ]

    # Guard flag for trigger rules
    can_trigger = live_status != "running"

    # RULE 1 — "No saves across recent runs" → boost batch size + scan.
    # Fires when we have at least the lookback window of completed runs
    # AND total saves == 0.
    if len(recent_runs) >= LOW_SAVE_WINDOW and saves <= 0:
        if can_trigger:
            recs.append(_rec(
                "NO_SAVES_BOOST_DIVERSITY",
                "trigger_multi_cycle",
                f"No strategies saved across last {len(recent_runs)} runs. "
                f"Boosting batch_size and broadening scan to increase "
                f"discovery surface.",
                {
                    "cycles": 3,
                    "batch_size": min(BATCH_SIZE_CAP,
                                      4 + BATCH_SIZE_STEP),
                    "scan": diversity_scan_payload,
                },
                "warn",
            ))
        else:
            recs.append(_rec(
                "NO_SAVES_WAIT",
                "log_recommendation",
                f"No saves in last {len(recent_runs)} runs but a run is "
                f"active — will re-evaluate after completion.",
                {}, "info",
            ))

    # RULE 2 — "insufficient_trades dominates rejections" → hint toward
    #          higher-frequency generation via advisory. (We do NOT
    #          mutate the LLM prompt here — that's a manual toggle.)
    if rej_total > 0:
        ins_share = rej_counts.get("insufficient_trades", 0) / max(rej_total, 1)
        if ins_share >= INSUFFICIENT_TRADES_SHARE:
            recs.append(_rec(
                "HIGH_INSUFFICIENT_TRADES",
                "log_recommendation",
                f"{ins_share:.0%} of recent rejections are "
                f"insufficient_trades (< 30 trades). Recommend running "
                f"a cycle biased to higher-frequency strategy_types "
                f"(e.g. mean_reversion on M30/H1).",
                {
                    "share": round(ins_share, 3),
                    "count": rej_counts.get("insufficient_trades", 0),
                    "hint": "generation_style=high_frequency_preferred",
                },
                "warn",
            ))

    # RULE 3 — "PF < 1.0 across recent runs" → diversity trigger.
    if (
        isinstance(avg_pf, (int, float))
        and avg_pf < LOW_PF_THRESHOLD
        and can_trigger
        and len(recent_runs) >= 2
    ):
        recs.append(_rec(
            "LOW_PF_DIVERSITY",
            "trigger_multi_cycle",
            f"Average PF across last {len(recent_runs)} runs is "
            f"{avg_pf:.2f} (< {LOW_PF_THRESHOLD}). Rerunning with a "
            f"broader scan and smaller batch to accelerate exploration.",
            {
                "cycles": 2,
                "batch_size": 3,
                "scan": diversity_scan_payload,
            },
            "warn",
        ))

    # RULE 4 — "prop_status=FAIL dominates" → stricter DD strategies
    #          advisory. Actionable only via the prompt-tuning layer.
    if rej_total > 0 and rej_counts.get("prop_status_fail", 0) / max(rej_total, 1) >= 0.5:
        recs.append(_rec(
            "PROP_STATUS_FAIL_DOMINANT",
            "log_recommendation",
            "Majority of rejections are prop_status=FAIL (DD blows prop "
            "firm rules). Strategies need tighter SL / lower exposure. "
            "Prompt is already prop-firm-tuned — consider restricting "
            "scan to H4 timeframes where DDs are smaller.",
            {
                "share": round(rej_counts.get("prop_status_fail", 0) / max(rej_total, 1), 3),
                "hint": "prefer_H4_timeframes",
            },
            "warn",
        ))

    # RULE 5 — "OOS gate dominant" → overfitting signal. Advisory.
    if rej_total > 0 and rej_counts.get("oos_gate_failed", 0) / max(rej_total, 1) >= 0.3:
        recs.append(_rec(
            "OOS_GATE_DOMINANT",
            "log_recommendation",
            "30 %+ of rejections are OOS-gate failures — strategies are "
            "overfitting to in-sample data. This is healthy protection; "
            "continue mutation with more variants per type to find "
            "robust exits.",
            {
                "share": round(rej_counts.get("oos_gate_failed", 0) / max(rej_total, 1), 3),
            },
            "info",
        ))

    # RULE 6 — "Good strategy found" → promote.
    if best:
        recs.append(_rec(
            "PROMOTE_BEST",
            "promote_best_strategy",
            f"High-scoring strategy found: {best.get('pair')}/"
            f"{best.get('timeframe')} score={best.get('score')} "
            f"stability={best.get('stability_score')}. Surface on "
            f"dashboard for trader review.",
            {
                "strategy_id": best.get("strategy_id"),
                "pair": best.get("pair"),
                "timeframe": best.get("timeframe"),
                "score": best.get("score"),
                "pass_probability": best.get("pass_probability"),
                "stability_score": best.get("stability_score"),
            },
            "info",
        ))

    # RULE 7 — "All green, library growing" → keep current trajectory.
    if (
        saves > 0
        and isinstance(avg_pf, (int, float))
        and avg_pf >= GOOD_STRATEGY_PF
    ):
        recs.append(_rec(
            "HEALTHY_TRAJECTORY",
            "log_recommendation",
            f"System healthy: avg_pf={avg_pf:.2f} ≥ {GOOD_STRATEGY_PF}, "
            f"{saves} new saves in recent window. No intervention "
            f"required — continue current cycle cadence.",
            {"saves": saves, "avg_pf": avg_pf},
            "info",
        ))

    # ════════════════════════════════════════════════════════════════
    # Phase 27.2 / G6 — autonomous lifecycle progression rules.
    # The rules below ACT on the lifecycle classifier rather than just
    # observing it. They are intentionally additive — every rule above
    # remains untouched. All G6 rules are no-ops when lifecycle data is
    # unavailable so the orchestrator never crashes during cold start.
    # ════════════════════════════════════════════════════════════════
    lifecycle = state.get("lifecycle") or {}
    stage_counts = lifecycle.get("stage_counts") or {}
    promotions_recent = lifecycle.get("promotions_recent") or []
    demotions_recent = lifecycle.get("demotions_recent") or []

    # RULE 8 — LIFECYCLE_EVALUATE: every tick, run one cohort pass.
    # This is the cheapest self-driving step in G6: it converts the
    # lifecycle classifier from passive (Explorer-fetch only) to
    # autonomous (every tick → persisted state + audit log). The
    # `evaluate_lifecycle_cohort` action is independent of the multi-
    # cycle gate and therefore safe to fire even while a multi-cycle
    # run is in flight (it only touches lifecycle collections).
    recs.append(_rec(
        "LIFECYCLE_EVALUATE",
        "evaluate_lifecycle_cohort",
        "Tick-driven lifecycle evaluation pass over the cohort — "
        "advances strategies through the 8-stage ladder using cached "
        "metrics only.",
        {},
        "info",
    ))

    # RULE 9 — LIFECYCLE_PROMOTIONS_DETECTED: visibility for stage-up
    # transitions in the recent window. Advisory only (the persistence
    # already happened inside the lifecycle evaluator).
    if promotions_recent:
        promo_summary: Dict[str, int] = {}
        for t in promotions_recent:
            key = f"{t.get('from_stage')}→{t.get('to_stage')}"
            promo_summary[key] = promo_summary.get(key, 0) + 1
        recs.append(_rec(
            "LIFECYCLE_PROMOTIONS_DETECTED",
            "log_recommendation",
            f"{len(promotions_recent)} lifecycle promotion(s) recorded in "
            f"the last {LIFECYCLE_TRANSITION_WINDOW_HOURS}h: "
            + ", ".join(f"{k} ×{v}" for k, v in sorted(promo_summary.items())),
            {
                "count": len(promotions_recent),
                "by_transition": promo_summary,
                "window_hours": LIFECYCLE_TRANSITION_WINDOW_HOURS,
                "samples": promotions_recent[:5],
            },
            "info",
        ))

    # RULE 10 — LIFECYCLE_DEMOTIONS_DETECTED: same shape, opposite
    # direction. We surface these as `warn` because demotion under
    # hysteresis means the supporting evidence has materially eroded.
    if demotions_recent:
        demo_summary: Dict[str, int] = {}
        for t in demotions_recent:
            key = f"{t.get('from_stage')}→{t.get('to_stage')}"
            demo_summary[key] = demo_summary.get(key, 0) + 1
        recs.append(_rec(
            "LIFECYCLE_DEMOTIONS_DETECTED",
            "log_recommendation",
            f"{len(demotions_recent)} lifecycle demotion(s) recorded in "
            f"the last {LIFECYCLE_TRANSITION_WINDOW_HOURS}h: "
            + ", ".join(f"{k} ×{v}" for k, v in sorted(demo_summary.items())),
            {
                "count": len(demotions_recent),
                "by_transition": demo_summary,
                "window_hours": LIFECYCLE_TRANSITION_WINDOW_HOURS,
                "samples": demotions_recent[:5],
            },
            "warn",
        ))

    # RULE 11 — AUTO_BUILD_PORTFOLIO: when the elite cohort is large
    # enough to seed a portfolio AND the system has not built one in
    # the last `AUTO_BUILD_COOLDOWN_HOURS`, the orchestrator emits an
    # `auto_build_portfolio` action. The portfolio_builder_engine
    # already filters for diversification, correlation, and firm-match
    # eligibility — once a strategy lands in a saved portfolio its
    # `portfolio_membership` becomes truthy and the next lifecycle
    # evaluator pass advances it from `elite` → `portfolio_worthy`.
    elite_count = int(stage_counts.get("elite", 0) or 0)
    last_built = lifecycle.get("last_portfolio_built_at")
    cooldown_cutoff = _hours_ago_iso(AUTO_BUILD_COOLDOWN_HOURS)
    cooldown_active = bool(last_built and last_built >= cooldown_cutoff)
    if elite_count >= AUTO_BUILD_MIN_ELITE and not cooldown_active:
        recs.append(_rec(
            "AUTO_BUILD_PORTFOLIO",
            "auto_build_portfolio",
            f"Elite cohort holds {elite_count} strategies "
            f"(≥ {AUTO_BUILD_MIN_ELITE}) and no portfolio has been built in "
            f"the last {AUTO_BUILD_COOLDOWN_HOURS}h — building a portfolio "
            f"to advance them toward PORTFOLIO_WORTHY.",
            {
                "elite_count":          elite_count,
                "min_elite":            AUTO_BUILD_MIN_ELITE,
                "last_built":           last_built,
                "cooldown_hours":       AUTO_BUILD_COOLDOWN_HOURS,
                "stage_counts":         stage_counts,
            },
            "info",
        ))
    elif elite_count >= AUTO_BUILD_MIN_ELITE and cooldown_active:
        # Quiet advisory so operators can see the system is poised but
        # waiting on the cooldown window.
        recs.append(_rec(
            "AUTO_BUILD_PORTFOLIO_COOLDOWN",
            "log_recommendation",
            f"Elite cohort {elite_count} ≥ {AUTO_BUILD_MIN_ELITE} but "
            f"portfolio built recently (last_built={last_built}); will "
            f"re-evaluate after the {AUTO_BUILD_COOLDOWN_HOURS}h cooldown.",
            {
                "elite_count":   elite_count,
                "last_built":    last_built,
                "cooldown_until": cooldown_cutoff,
            },
            "info",
        ))

    # ════════════════════════════════════════════════════════════════
    # Phase 30.1 · Δ3 — RULE 12 · AUTONOMOUS_DISCOVERY_TICK (DORMANT).
    # ════════════════════════════════════════════════════════════════
    # Operator constraint:
    #   • `autonomous_discovery_enabled = False` by default. RULE 12
    #     therefore emits ADVISORY telemetry only — no trigger action
    #     until the operator flips the flag.
    #   • RULE 12 still RUNS every tick (observational telemetry is the
    #     whole point) so later convergence analysis has a full record
    #     of when conditions would-have / did fire.
    # Telemetry recorded every tick:
    #   • rule evaluation timestamp
    #   • whether conditions passed
    #   • trigger reason OR skip reason
    #   • rotating pair/TF target
    #   • survivor headroom snapshot
    survivor_universe = lifecycle.get("survivor_universe") or {}
    headroom = int(survivor_universe.get("headroom") or 0)
    active_universe = int(survivor_universe.get("active_count") or 0)
    universe_cap    = int(survivor_universe.get("cap") or 0)

    # Rotating target picks deterministically from the rotation list
    # using the current UTC hour so consecutive ticks within the same
    # hour stay on the same pair/TF (avoids noisy churn).
    now_hour = datetime.now(timezone.utc).hour
    rotation = AUTONOMOUS_DISCOVERY_ROTATION
    # Phase 30.2 · A3 — filter the rotation list through the allowed
    # universe BEFORE picking the rotating target. If the operator's
    # universe excludes every rotation cell, the rotation falls back to
    # the unfiltered list (anti-blackhole) and the telemetry records it.
    rotation_filtered_by_universe = False
    if allowed_universe:
        try:
            from engines import governance_universe as _gu
            filt = _gu.intersect_scan(allowed_universe, rotation)
            if filt:
                rotation = tuple(filt)
                rotation_filtered_by_universe = True
        except Exception:                                   # pragma: no cover
            pass
    rotating_target = (
        {"pair": rotation[now_hour % len(rotation)][0],
         "timeframe": rotation[now_hour % len(rotation)][1]}
        if rotation else None
    )

    conditions_passed = (
        AUTONOMOUS_DISCOVERY_ENABLED
        and live_status != "running"
        and headroom >= AUTONOMOUS_DISCOVERY_MIN_HEADROOM
    )
    if not AUTONOMOUS_DISCOVERY_ENABLED:
        skip_reason = "autonomous_discovery_disabled"
    elif live_status == "running":
        skip_reason = "run_active"
    elif headroom < AUTONOMOUS_DISCOVERY_MIN_HEADROOM:
        skip_reason = (
            f"insufficient_headroom ({headroom} < "
            f"{AUTONOMOUS_DISCOVERY_MIN_HEADROOM})"
        )
    else:
        skip_reason = None
    trigger_reason = (
        f"headroom={headroom} ≥ {AUTONOMOUS_DISCOVERY_MIN_HEADROOM} → "
        f"target {rotating_target['pair']}/{rotating_target['timeframe']}"
        if conditions_passed and rotating_target else None
    )

    recs.append(_rec(
        "AUTONOMOUS_DISCOVERY_TICK",
        "log_recommendation",   # advisory-only while dormant
        (
            "RULE 12 advisory: autonomous discovery would trigger — "
            + trigger_reason
            if conditions_passed
            else f"RULE 12 dormant: {skip_reason or 'no_action'}"
        ),
        {
            "evaluated_at":               datetime.now(timezone.utc).isoformat(),
            "autonomous_discovery_enabled": AUTONOMOUS_DISCOVERY_ENABLED,
            "conditions_passed":          conditions_passed,
            "trigger_reason":             trigger_reason,
            "skip_reason":                skip_reason,
            "rotating_target":            rotating_target,
            "rotation_filtered_by_universe": rotation_filtered_by_universe,
            "survivor_headroom":          headroom,
            "survivor_active_count":      active_universe,
            "survivor_universe_cap":      universe_cap,
            "min_headroom_required":      AUTONOMOUS_DISCOVERY_MIN_HEADROOM,
            "phase":                      "30.1",
        },
        "info",
    ))

    # ════════════════════════════════════════════════════════════════
    # RULE 13 · COMPUTE_AWARE_TELEMETRY (DORMANT-default, observational).
    # ════════════════════════════════════════════════════════════════
    # When COMPUTE_AWARE_ORCHESTRATION=true, emit an advisory rec that
    # carries the live compute_probe headroom snapshot alongside the
    # current scan width. This is OBSERVATIONAL ONLY — RULE 13 does
    # NOT alter scan width, cadence, or trigger conditions; it merely
    # surfaces "if the orchestrator were compute-aware right now, here
    # is what it would see". Operators can correlate the telemetry
    # with the safe-to-widen verdict before flipping any flag.
    try:
        import os as _os
        _raw = (_os.environ.get("COMPUTE_AWARE_ORCHESTRATION") or "").strip().lower()
        _ca_on = _raw in ("1", "true", "yes", "on")
        if _ca_on:
            from engines import compute_probe as _cp
            snap = _cp.snapshot()
            head = _cp.headroom_summary(snap)
            recs.append(_rec(
                "COMPUTE_AWARE_TELEMETRY",
                "log_recommendation",
                (
                    f"RULE 13 advisory: compute headroom ok={head.get('ok')} "
                    f"(cpu_head={head.get('cpu_headroom_pct')}%, "
                    f"mem_head={head.get('mem_headroom_pct')}%, "
                    f"load/core={head.get('load_per_core')}). "
                    f"Scan width unchanged — telemetry only."
                ),
                {
                    "evaluated_at":   datetime.now(timezone.utc).isoformat(),
                    "compute_aware_enabled": True,
                    "snapshot":       snap,
                    "headroom":       head,
                    "current_scan_size": len(adaptive_scan_pairs),
                    "phase":          "scaffolding-1",
                    "authoritative":  False,
                },
                "info",
            ))
    except Exception:                                       # pragma: no cover
        logger.debug("[orchestrator] RULE 13 telemetry failed", exc_info=True)

    return recs


def _rec(
    rule_id: str, action: str, reason: str,
    params: Dict[str, Any], severity: str,
) -> Dict[str, Any]:
    if action not in ACTION_TYPES:
        raise ValueError(f"unknown action type: {action}")
    if severity not in ("info", "warn", "critical"):
        raise ValueError(f"unknown severity: {severity}")
    return {
        "rule_id": rule_id,
        "action": action,
        "reason": reason,
        "params": params,
        "severity": severity,
    }


# ════════════════════════════════════════════════════════════════════
# EXECUTE
# ════════════════════════════════════════════════════════════════════

async def execute(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute recommended actions. Advisory rules (log_recommendation,
    promote_best_strategy) are NO-OPs at this layer — they surface to
    the caller (API / UI) which decides how to render them.

    Trigger actions call the same public entry points the dashboard
    uses so behaviour is identical to a manual button click.
    """
    results: List[Dict[str, Any]] = []
    # Only ONE trigger_multi_cycle may run at a time — first wins.
    trigger_consumed = False

    for a in actions:
        action = a.get("action")
        rule_id = a.get("rule_id")
        params = a.get("params") or {}

        if action == "trigger_multi_cycle":
            if trigger_consumed:
                results.append({
                    "rule_id": rule_id, "action": action,
                    "status": "skipped",
                    "reason": "another trigger_multi_cycle already executed this tick",
                })
                continue
            try:
                scan_pairs = None
                raw_scan = params.get("scan")
                if isinstance(raw_scan, list):
                    scan_pairs = [
                        (s["pair"], s["timeframe"])
                        for s in raw_scan
                        if isinstance(s, dict) and "pair" in s and "timeframe" in s
                    ] or None
                # G1 — open a research_run owned by this orchestrator
                # tick. The downstream multi-cycle will reuse it.
                research_run_id: Optional[str] = None
                try:
                    from engines import research_lineage
                    research_run_id = await research_lineage.new_research_run(
                        trigger_type="orchestrator_tick",
                        trigger_reason=a.get("reason"),
                        rule_id=rule_id,
                        config={
                            "cycles": int(params.get("cycles", 5)),
                            "batch_size": int(params.get("batch_size", 3)),
                            "scan": scan_pairs,
                            "quality_threshold": float(params.get("quality_threshold", 35.0)),
                            "rule_params": dict(params),
                        },
                    )
                except Exception as e:                          # pragma: no cover
                    logger.debug("[lineage] orchestrator new_research_run failed: %s", e)
                snapshot = await mcr.start_multi_cycle(
                    cycles=int(params.get("cycles", 5)),
                    batch_size=int(params.get("batch_size", 3)),
                    scan=scan_pairs,
                    quality_threshold=float(params.get("quality_threshold", 35.0)),
                    research_run_id=research_run_id,
                )
                trigger_consumed = True
                results.append({
                    "rule_id": rule_id, "action": action,
                    "status": "executed",
                    "run_id": snapshot.get("run_id"),
                    "research_run_id": research_run_id,
                    "live_status": snapshot.get("status"),
                })
            except Exception as e:
                logger.exception("[orchestrator] trigger_multi_cycle failed")
                results.append({
                    "rule_id": rule_id, "action": action,
                    "status": "error", "error": str(e)[:240],
                })

        elif action == "stop_multi_cycle":
            try:
                stopping = mcr.request_stop()
                results.append({
                    "rule_id": rule_id, "action": action,
                    "status": "executed", "stopping": stopping,
                })
            except Exception as e:
                results.append({
                    "rule_id": rule_id, "action": action,
                    "status": "error", "error": str(e)[:240],
                })

        elif action in ("log_recommendation", "promote_best_strategy"):
            # Advisory — surfaced to caller verbatim. No side effect.
            results.append({
                "rule_id": rule_id, "action": action,
                "status": "advisory", "params": params,
            })

        elif action == "evaluate_lifecycle_cohort":
            # Phase 27.2 / G6 — drive autonomous lifecycle progression.
            # The cohort pass is bounded by `limit` and uses cached
            # fields only — safe to run on every tick.
            try:
                from engines import strategy_lifecycle as lc
                summary = await lc.evaluate_cohort(persist=True)
                results.append({
                    "rule_id":  rule_id,
                    "action":   action,
                    "status":   "executed",
                    "summary": {
                        "evaluated":   summary.get("evaluated"),
                        "promotions":  summary.get("promotions"),
                        "demotions":   summary.get("demotions"),
                        "first_touch": summary.get("first_touch"),
                        "upserted":    summary.get("upserted"),
                        "stage_counts": summary.get("stage_counts"),
                    },
                })
            except Exception as e:
                logger.exception("[orchestrator] lifecycle eval failed")
                results.append({
                    "rule_id": rule_id, "action": action,
                    "status": "error", "error": str(e)[:240],
                })

        elif action == "auto_build_portfolio":
            # Phase 27.2 / G6 — graduate the elite cohort into a saved
            # portfolio. We use the existing portfolio_builder_engine
            # with `persist=True`; subsequent lifecycle ticks will see
            # the new memberships and advance strategies to
            # PORTFOLIO_WORTHY.
            try:
                from engines import portfolio_builder_engine as pb
                built = await pb.build_portfolio(persist=True)
                results.append({
                    "rule_id":      rule_id,
                    "action":       action,
                    "status":       "executed" if built.get("persisted")
                                    else "advisory",
                    "portfolio_id": built.get("portfolio_id"),
                    "selected":     built.get("selected_count"),
                    "build_status": built.get("status"),
                    "expected_pf":  built.get("expected_pf"),
                    "pass_probability": built.get("pass_probability"),
                })
            except Exception as e:
                logger.exception("[orchestrator] auto_build_portfolio failed")
                results.append({
                    "rule_id": rule_id, "action": action,
                    "status": "error", "error": str(e)[:240],
                })

        else:
            results.append({
                "rule_id": rule_id, "action": action,
                "status": "skipped", "reason": "unknown action type",
            })

    return results


# ════════════════════════════════════════════════════════════════════
# TICK — observe → decide → (optionally) execute
# ════════════════════════════════════════════════════════════════════

async def run_tick(
    execute_actions: bool = False,
) -> Dict[str, Any]:
    """One full orchestration tick. Returns the observed state, the
    recommended actions, and (when `execute_actions=True`) the results
    of executing them.
    """
    state = await observe_state()
    recs = decide(state)
    executions: List[Dict[str, Any]] = []
    if execute_actions:
        executions = await execute(recs)
    return {
        "observed_at": state.get("observed_at"),
        "state": state,
        "recommendations": recs,
        "executions": executions if execute_actions else None,
        "executed": bool(execute_actions),
    }
