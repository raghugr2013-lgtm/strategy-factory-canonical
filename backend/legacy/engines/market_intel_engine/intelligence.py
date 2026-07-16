"""Phase G — Market Intelligence aggregator.

Runs the 8 observers over the latest snapshots for a (pair, timeframe),
persists a rolling `MarketState`, runs change detection, and upserts a
consumable `MarketIntelligence` payload for the Adaptive Trading Brain.

Every autonomous decision emits an `outcome_events` row so the operator
can trace every downstream brain influence back to a raw observation.

Structural changes are persisted BOTH in the dedicated
`structural_changes` collection AND via `outcome_events` (Q3 operator
ruling). This preserves the canonical timeline while keeping the audit
trail complete.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import config as mcfg
from . import ledger
from .change_detection import detect_structural_changes
from .observers import (
    observe_breakout_quality, observe_correlation, observe_liquidity,
    observe_reversal_strength, observe_session_stats,
    observe_style_performance, observe_trend_duration,
    observe_volatility_dynamics,
)
from .types import MarketIntelligence, MarketSnapshot, MarketState

logger = logging.getLogger(__name__)


# ── Snapshot cache (operator refinement) ───────────────────────────
# Prevents hammering Mongo when the brain fires many ticks per minute.
# In-memory, per-process, TTL-bounded.
_CACHE: Dict[Tuple[str, str], Tuple[float, MarketIntelligence]] = {}


def reset_snapshot_cache() -> None:
    """Test / operator hook — flush the in-memory cache."""
    _CACHE.clear()


def _cache_get(pair: str, tf: str) -> Optional[MarketIntelligence]:
    v = _CACHE.get((pair, tf))
    if not v:
        return None
    ts, mi = v
    if time.time() - ts > mcfg.snapshot_cache_ttl_seconds():
        return None
    return mi


def _cache_put(pair: str, tf: str, mi: MarketIntelligence) -> None:
    _CACHE[(pair, tf)] = (time.time(), mi)


# ── Emit helper ───────────────────────────────────────────────────
async def _emit(decision_type: str, *, reason: str = "",
                metrics: Optional[Dict[str, Any]] = None,
                evidence: Optional[Dict[str, Any]] = None) -> None:
    try:
        from engines.intelligence.explainability import emit_decision
        await emit_decision(
            decision_type, reason=reason,
            metrics=metrics or {}, evidence=evidence or {},
        )
    except Exception:  # noqa: BLE001
        pass


# ── Aggregation ────────────────────────────────────────────────────
def _build_state(pair: str, timeframe: str, window: str,
                 snaps: List[MarketSnapshot],
                 universe_snaps: Optional[Dict[str, List[MarketSnapshot]]],
                 recent_outcomes: Optional[List[Dict[str, Any]]],
                 ) -> Tuple[MarketState, Dict[str, Any]]:
    """Run all observers and produce a MarketState. Returns (state, sources)."""
    r_td = observe_trend_duration(snaps)
    r_vd = observe_volatility_dynamics(snaps)
    r_bo = observe_breakout_quality(snaps)
    r_rv = observe_reversal_strength(snaps)
    r_ss = observe_session_stats(snaps)
    r_lq = observe_liquidity(snaps)
    r_co = observe_correlation(snaps, universe_snaps=universe_snaps)
    r_sp = observe_style_performance(snaps, recent_outcomes=recent_outcomes)

    vol_mean = float(r_vd.evidence.get("short_sigma") or 0.0)
    expansion = float(r_vd.evidence.get("expansion_ratio") or 1.0)

    # Noise ratio proxy: 1 - breakout success rate (higher noise → fewer clean signals).
    noise_ratio = round(1.0 - r_bo.score, 4)

    # Liquidity band string from observer evidence.
    liq_band = str(r_lq.evidence.get("band") or "unknown")

    # Composite health score — weighted mean of observer scores.
    health = round(
        (0.20 * r_td.score + 0.20 * r_vd.score + 0.15 * r_bo.score +
         0.10 * r_rv.score + 0.10 * r_ss.score + 0.10 * r_lq.score +
         0.10 * r_co.score + 0.05 * r_sp.score),
        4,
    )

    state = MarketState(
        pair=pair, timeframe=timeframe, window=window,
        ts=datetime.now(timezone.utc).isoformat(),
        trend_duration_bars=float(r_td.evidence.get("avg_run_bars") or 0.0),
        trend_persistence_score=r_td.score,
        volatility_mean=vol_mean,
        volatility_expansion_ratio=expansion,
        breakout_attempts=int(r_bo.evidence.get("attempts") or 0),
        breakout_success_rate=r_bo.score,
        reversal_strength_avg=r_rv.score,
        noise_ratio=noise_ratio,
        session_pnl_bias={k: float(v) for k, v in
                          (r_ss.evidence.get("bias") or {}).items()},
        liquidity_band=liq_band,
        avg_correlation_to_universe=(
            r_co.evidence.get("avg_correlation")
            if r_co.evidence.get("avg_correlation") is not None
            else None
        ),
        style_performance={k: float(v) for k, v in
                            (r_sp.evidence.get("style_scores") or {}).items()},
        health_score=health,
    )
    sources = {
        "trend_duration":       r_td.to_dict(),
        "volatility_dynamics":  r_vd.to_dict(),
        "breakout_quality":     r_bo.to_dict(),
        "reversal_strength":    r_rv.to_dict(),
        "session_stats":        r_ss.to_dict(),
        "liquidity_estimator":  r_lq.to_dict(),
        "correlation_matrix":   r_co.to_dict(),
        "style_performance":    r_sp.to_dict(),
    }
    return state, sources


def _aggregate_intelligence(
    pair: str, timeframe: str, state: MarketState,
    sources: Dict[str, Any],
    active_changes: List[Dict[str, Any]],
    regime_confidence_hint: Optional[float] = None,
) -> MarketIntelligence:
    """Combine the state + active changes into a consumable payload."""
    trend_pers = state.trend_persistence_score
    breakout   = state.breakout_success_rate
    noise      = state.noise_ratio
    liq        = sources["liquidity_estimator"].get("score", 0.5)

    # regime_confidence — inherit from Phase C hint if supplied, else
    # synthesise from trend persistence and volatility band health.
    if regime_confidence_hint is not None:
        regime_conf = float(regime_confidence_hint)
    else:
        regime_conf = round(
            0.55 * trend_pers + 0.45 * sources["volatility_dynamics"]["score"],
            4)

    # market_confidence — weighted composite (all bounded 0..1).
    market_conf = round(min(1.0, max(0.0,
        0.30 * trend_pers + 0.25 * breakout + 0.25 * (1.0 - noise) +
        0.20 * regime_conf)), 4)

    # style_confidence — style_performance × regime fit for that style.
    style_conf = {s: round(min(1.0, max(0.0, v * (0.5 + 0.5 * regime_conf))), 4)
                  for s, v in (state.style_performance or {}).items()}
    best_style = max(style_conf.values()) if style_conf else 0.5

    # opportunity_score = market_conf × best_style × liquidity_factor.
    opportunity = round(market_conf * best_style * max(0.1, min(1.0, liq)), 4)

    # risk_environment = 1 - (expansion + noise + change_severity penalties).
    exp_pen = max(0.0, min(0.5,
        (state.volatility_expansion_ratio - 1.25) / 1.75)) if state.volatility_expansion_ratio > 1.25 else 0.0
    change_pen = min(0.4, sum(c.get("severity", 0.0) for c in active_changes) * 0.15)
    risk_env = round(max(0.0, min(1.0, 1.0 - exp_pen - noise * 0.25 - change_pen)), 4)

    # Discount regime_confidence when structural changes are active.
    if active_changes:
        regime_conf = round(max(0.0, regime_conf - min(0.4, change_pen)), 4)

    return MarketIntelligence(
        pair=pair, timeframe=timeframe,
        ts=datetime.now(timezone.utc).isoformat(),
        market_confidence=market_conf,
        style_confidence=style_conf,
        regime_confidence=regime_conf,
        opportunity_score=opportunity,
        risk_environment=risk_env,
        active_structural_changes=active_changes,
        sources=sources,
    )


# ── Public API ─────────────────────────────────────────────────────
async def compute_market_intelligence(
    pair: str,
    timeframe: str,
    *,
    snapshots: Optional[List[MarketSnapshot]] = None,
    universe_snapshots: Optional[Dict[str, List[MarketSnapshot]]] = None,
    recent_outcomes: Optional[List[Dict[str, Any]]] = None,
    regime_confidence_hint: Optional[float] = None,
    persist: bool = True,
) -> MarketIntelligence:
    """Compute (and optionally persist) a MarketIntelligence payload
    for (pair, timeframe). This is the workhorse used by both the
    orchestrator task and the API /refresh endpoint.

    Never raises — returns a neutral MarketIntelligence when Mongo /
    dependencies are unavailable.
    """
    # Load snapshots if not supplied.
    if snapshots is None:
        snapshots = await ledger.read_recent_snapshots(pair, timeframe, limit=500)

    if not snapshots or len(snapshots) < mcfg.observer_min_snapshots():
        mi = MarketIntelligence(
            pair=pair, timeframe=timeframe,
            ts=datetime.now(timezone.utc).isoformat(),
            sources={"reason": "insufficient_snapshots",
                     "n_snapshots": len(snapshots or [])},
        )
        if persist:
            await ledger.upsert_intelligence(mi)
        _cache_put(pair, timeframe, mi)
        return mi

    # Build state for the primary "24h" window.
    state, sources = _build_state(
        pair, timeframe, "24h", snapshots, universe_snapshots, recent_outcomes,
    )

    # Persist state.
    state_id: Optional[str] = None
    if persist:
        state_id = await ledger.upsert_state(state)
        await _emit(
            "market_state_refresh",
            reason=f"health={state.health_score}",
            metrics={"pair": pair, "timeframe": timeframe,
                      "window": "24h",
                      "health_score": state.health_score,
                      "volatility_mean": state.volatility_mean,
                      "breakout_success_rate": state.breakout_success_rate,
                      "noise_ratio": state.noise_ratio,
                      "liquidity_band": state.liquidity_band},
            evidence={"sources": sources},
        )

    # Change detection needs a bit of history.
    history = await ledger.read_state_history(pair, timeframe, "24h", limit=20)
    # `history` is newest-first — reverse to chronological.
    history_chrono = list(reversed(history))
    if not history_chrono or history_chrono[-1].ts != state.ts:
        history_chrono.append(state)
    changes = detect_structural_changes(pair, timeframe, "24h", history_chrono)
    active_changes = []
    for c in changes:
        d = c.to_dict()
        active_changes.append(d)
        if persist:
            await ledger.insert_change(c)
            await _emit(
                "structural_change_detected",
                reason=f"{c.change_type} sev={c.severity}",
                metrics={"pair": pair, "timeframe": timeframe,
                          "change_type": c.change_type,
                          "severity": c.severity,
                          "method": c.method},
                evidence={"delta_metric": c.delta_metric,
                          "evidence": c.evidence},
            )

    mi = _aggregate_intelligence(
        pair, timeframe, state, sources, active_changes,
        regime_confidence_hint=regime_confidence_hint,
    )
    if persist:
        await ledger.upsert_intelligence(mi)
        await _emit(
            "market_intelligence_refresh",
            reason=f"market_conf={mi.market_confidence} opp={mi.opportunity_score}",
            metrics={"pair": pair, "timeframe": timeframe,
                      "market_confidence":  mi.market_confidence,
                      "regime_confidence":  mi.regime_confidence,
                      "opportunity_score":  mi.opportunity_score,
                      "risk_environment":   mi.risk_environment,
                      "n_active_changes":   len(active_changes)},
            evidence={"sources_summary": {k: v.get("score") for k, v in sources.items()},
                      "active_changes":  [c.get("change_type") for c in active_changes]},
        )
    _cache_put(pair, timeframe, mi)
    return mi


async def refresh_market_intelligence(
    pair: str, timeframe: str,
) -> MarketIntelligence:
    """Convenience wrapper — full refresh with default inputs.

    Loads snapshots for `pair` AND the rest of the universe (for
    correlation), then runs the aggregator.
    """
    snaps = await ledger.read_recent_snapshots(pair, timeframe, limit=500)
    universe = {}
    for other in mcfg.mi_universe():
        if other == pair:
            continue
        try:
            other_snaps = await ledger.read_recent_snapshots(other, timeframe, limit=500)
            if other_snaps:
                universe[other] = other_snaps
        except Exception:  # noqa: BLE001
            continue
    return await compute_market_intelligence(
        pair, timeframe,
        snapshots=snaps,
        universe_snapshots=universe or None,
        persist=True,
    )
