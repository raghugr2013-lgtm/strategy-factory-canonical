"""Phase G — heuristic change-point detection.

Reads recent `MarketState` history for a (pair, timeframe, window) and
emits `StructuralChange` instances when a meaningful shift is detected.
No ML — pure rolling-statistics detectors, tagged `method="heuristic_*"`
so Phase G.2/H/I can drop-in a Bayesian/HMM/ML replacement without
breaking the wire contract.

Detectors:
  * volatility_regime_shift   — CUSUM-lite on volatility_mean
  * trend_duration_drift      — running-mean deviation on trend_duration_bars
  * breakout_degradation      — rolling drop in breakout_success_rate
  * correlation_breakdown     — |corr_current − corr_baseline| > threshold
  * noise_increase            — rolling noise_ratio above baseline + 2σ
  * liquidity_drop            — recent liquidity_band drops below a floor
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import List

from . import config as mcfg
from .types import MarketState, StructuralChange


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _severity(delta: float, denom: float) -> float:
    if denom <= 1e-12:
        return 0.0
    s = min(1.0, abs(delta) / max(1e-9, denom))
    return round(s, 4)


def detect_structural_changes(
    pair: str,
    timeframe: str,
    window: str,
    history: List[MarketState],
) -> List[StructuralChange]:
    """Return a list of `StructuralChange` instances for the given
    (pair, timeframe, window). `history` is chronological (oldest first).

    Requires ≥ 4 samples to fire anything — otherwise returns [].
    """
    changes: List[StructuralChange] = []
    if not history or len(history) < 4:
        return changes
    baseline = history[:-1]
    latest   = history[-1]

    # 1. volatility regime shift — CUSUM-lite: current vs rolling mean.
    vol_series = [h.volatility_mean for h in baseline]
    vol_ref = mean(vol_series) if vol_series else 0.0
    vol_std = pstdev(vol_series) if len(vol_series) > 1 else 0.0
    if vol_ref > 0 and vol_std >= 0 and abs(latest.volatility_mean - vol_ref) > max(vol_ref * 0.5, 2 * vol_std, 1e-9):
        sev = _severity(latest.volatility_mean - vol_ref, max(vol_ref, 1e-9))
        if sev >= mcfg.change_severity_min():
            changes.append(StructuralChange(
                pair=pair, timeframe=timeframe,
                change_type="volatility_regime_shift",
                severity=sev, detected_at=_now(),
                window_before=window, window_after=window,
                delta_metric={"vol_before": round(vol_ref, 8),
                              "vol_after":  round(latest.volatility_mean, 8),
                              "vol_std":    round(vol_std, 8)},
                evidence={"n_samples": len(vol_series)},
                method="heuristic_cusum_lite",
            ))

    # 2. trend duration drift — running-mean deviation.
    td_series = [h.trend_duration_bars for h in baseline]
    td_ref = mean(td_series) if td_series else 0.0
    if td_ref > 0 and abs(latest.trend_duration_bars - td_ref) > max(td_ref * 0.4, 2.0):
        sev = _severity(latest.trend_duration_bars - td_ref, td_ref)
        if sev >= mcfg.change_severity_min():
            changes.append(StructuralChange(
                pair=pair, timeframe=timeframe,
                change_type="trend_duration_drift",
                severity=sev, detected_at=_now(),
                delta_metric={"before": round(td_ref, 3),
                              "after":  round(latest.trend_duration_bars, 3)},
                evidence={"n_samples": len(td_series)},
                method="heuristic_running_mean",
            ))

    # 3. breakout degradation — rolling drop.
    bo_series = [h.breakout_success_rate for h in baseline]
    bo_ref = mean(bo_series) if bo_series else 0.5
    drop = bo_ref - latest.breakout_success_rate
    if bo_ref >= 0.5 and drop >= max(0.20, 2 * (pstdev(bo_series) if len(bo_series) > 1 else 0.0)):
        sev = _severity(drop, bo_ref)
        if sev >= mcfg.change_severity_min():
            changes.append(StructuralChange(
                pair=pair, timeframe=timeframe,
                change_type="breakout_degradation",
                severity=sev, detected_at=_now(),
                delta_metric={"before": round(bo_ref, 4),
                              "after":  round(latest.breakout_success_rate, 4),
                              "drop":   round(drop, 4)},
                evidence={"n_samples": len(bo_series)},
                method="heuristic_rolling_ratio_drop",
            ))

    # 4. correlation breakdown.
    co_baseline = [h.avg_correlation_to_universe for h in baseline
                   if h.avg_correlation_to_universe is not None]
    co_now = latest.avg_correlation_to_universe
    if co_baseline and co_now is not None:
        co_ref = mean(co_baseline)
        if abs(co_now - co_ref) >= 0.35:
            sev = _severity(co_now - co_ref, 1.0)
            if sev >= mcfg.change_severity_min():
                changes.append(StructuralChange(
                    pair=pair, timeframe=timeframe,
                    change_type="correlation_breakdown",
                    severity=sev, detected_at=_now(),
                    delta_metric={"before": round(co_ref, 4),
                                  "after":  round(co_now, 4)},
                    evidence={"n_samples": len(co_baseline)},
                    method="heuristic_delta_threshold",
                ))

    # 5. noise increase.
    n_series = [h.noise_ratio for h in baseline]
    n_ref = mean(n_series) if n_series else 0.5
    n_std = pstdev(n_series) if len(n_series) > 1 else 0.0
    if latest.noise_ratio - n_ref > max(0.15, 2 * n_std):
        sev = _severity(latest.noise_ratio - n_ref, 1.0)
        if sev >= mcfg.change_severity_min():
            changes.append(StructuralChange(
                pair=pair, timeframe=timeframe,
                change_type="noise_increase",
                severity=sev, detected_at=_now(),
                delta_metric={"before": round(n_ref, 4),
                              "after":  round(latest.noise_ratio, 4)},
                evidence={"n_samples": len(n_series),
                          "n_std":     round(n_std, 6)},
                method="heuristic_running_variance",
            ))

    # 6. liquidity drop — band demotion.
    band_order = {"high": 2, "medium": 1, "low": 0, "unknown": 1}
    baseline_band = max(band_order.get(h.liquidity_band, 1) for h in baseline)
    now_band = band_order.get(latest.liquidity_band, 1)
    if baseline_band - now_band >= 1:
        sev = 0.4 + 0.3 * (baseline_band - now_band)
        if sev >= mcfg.change_severity_min():
            changes.append(StructuralChange(
                pair=pair, timeframe=timeframe,
                change_type="liquidity_drop",
                severity=round(min(1.0, sev), 4), detected_at=_now(),
                delta_metric={"before_band": float(baseline_band),
                              "after_band":  float(now_band)},
                evidence={"before_max_band": baseline_band,
                          "current_band":    now_band},
                method="heuristic_band_demotion",
            ))

    return changes
