"""
Phase 8 — Walk-Forward Validation Engine.

Rolling walk-forward: for each window the strategy parameters are fitted on
an IS (in-sample) train slice, FROZEN, and then replayed on the immediately
following OOS (out-of-sample) slice. The window then rolls forward.

No data leakage guarantees:
  * `fit_best_params` only sees train_prices[i]
  * `score_frozen_params` only sees oos_prices[i]
  * No aggregate metric combines IS and OOS during selection
  * Per-window RNG seed is deterministic (strategy_text + window index)

Output:
  {
    "success": True,
    "mode": "walk_forward",
    "n_windows": int,
    "train_size": int,
    "oos_size": int,
    "step_size": int,
    "windows": [ {window, train_range, oos_range, is_metrics, oos_metrics, degradation_pct, params}, ... ],
    "aggregate": {
        "oos_avg_return_pct": float,
        "oos_avg_sharpe": float,
        "oos_profitable_ratio": float,
        "is_avg_return_pct": float,
        "mean_degradation_pct": float,
        "stability_score": float,  # 0-100
    },
  }
"""
from __future__ import annotations

import hashlib
import logging
from engines.random_search_optimizer import fit_best_params, score_frozen_params

logger = logging.getLogger(__name__)

MIN_TRAIN_BARS = 60
MIN_OOS_BARS = 20
DEFAULT_N_WINDOWS = 5
DEFAULT_TRAIN_PCT = 0.70   # % of each window used as IS
DEFAULT_NUM_VARIANTS = 40


def _seed_for_window(strategy_text: str, window_idx: int) -> int:
    """Deterministic per-window seed so walk-forward runs are reproducible."""
    key = f"{strategy_text}|wf|{window_idx}".encode()
    return int(hashlib.md5(key).hexdigest()[:8], 16)


def _build_windows(n_total: int, n_windows: int, train_pct: float) -> list[dict]:
    """
    Build non-overlapping rolling windows. Each window = [train_slice | oos_slice].
    Windows advance by step = oos_size so OOS slices are contiguous and
    never reused as OOS elsewhere.
    """
    if n_windows < 2:
        n_windows = 2
    # Size a single window so n_windows back-to-back windows fit in n_total.
    window_size = n_total // n_windows
    train_size = max(MIN_TRAIN_BARS, int(window_size * train_pct))
    oos_size = max(MIN_OOS_BARS, window_size - train_size)

    # Recompute window_size in case the floor pushed us over — shrink train if so.
    if train_size + oos_size > window_size:
        train_size = window_size - oos_size
        if train_size < MIN_TRAIN_BARS:
            return []

    windows = []
    step = oos_size  # slide by OOS size so OOS never overlaps across windows
    start = 0
    idx = 0
    while idx < n_windows and start + train_size + oos_size <= n_total:
        windows.append({
            "idx": idx,
            "train_start": start,
            "train_end": start + train_size,
            "oos_start": start + train_size,
            "oos_end": start + train_size + oos_size,
        })
        start += step
        idx += 1
    return windows


def _degradation_pct(is_val: float, oos_val: float) -> float:
    """
    Degradation = (IS - OOS) / |IS| * 100. Positive = OOS worse than IS.
    Clipped to [-200, 200] for sanity.
    """
    if is_val is None or oos_val is None:
        return 0.0
    if abs(is_val) < 1e-9:
        return 0.0 if abs(oos_val) < 1e-9 else (-100.0 if oos_val > 0 else 100.0)
    deg = (is_val - oos_val) / abs(is_val) * 100.0
    return round(max(-200.0, min(200.0, deg)), 2)


def _stability_from_windows(windows: list[dict]) -> float:
    """
    Stability score 0-100 from walk-forward OOS results.
    Rewards:
      - High ratio of profitable OOS windows (40 pts)
      - Positive mean OOS return (30 pts)
      - Low degradation IS->OOS (30 pts)
    """
    if not windows:
        return 0.0
    oos_rets = [w["oos_metrics"].get("total_return_pct", 0) for w in windows]
    profitable = sum(1 for r in oos_rets if r > 0)
    profit_ratio = profitable / len(oos_rets)
    mean_oos = sum(oos_rets) / len(oos_rets)
    degs = [w["degradation_pct"] for w in windows]
    mean_deg = sum(degs) / len(degs) if degs else 0

    consistency_pts = 40.0 * profit_ratio
    return_pts = max(0.0, min(30.0, 15.0 + mean_oos * 1.5))
    # Low degradation = good. 0% deg = full 30; 100% deg = 0 pts
    deg_pts = max(0.0, min(30.0, 30.0 - abs(mean_deg) * 0.3))
    return round(consistency_pts + return_pts + deg_pts, 1)


def run_walk_forward(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    n_windows: int = DEFAULT_N_WINDOWS,
    train_pct: float = DEFAULT_TRAIN_PCT,
    num_variants: int = DEFAULT_NUM_VARIANTS,
    sim_config: dict = None,
) -> dict:
    """
    Rolling walk-forward validation with strict IS/OOS separation.

    For each window:
      1. fit_best_params on train slice   → sees IS only
      2. Freeze params
      3. score_frozen_params on OOS slice → sees OOS only
      4. Record IS metrics, OOS metrics, degradation

    Returns per-window detail + aggregate OOS stats + stability score.
    """
    if not prices or len(prices) < MIN_TRAIN_BARS + MIN_OOS_BARS:
        return {
            "success": False,
            "mode": "walk_forward",
            "error": (
                f"Walk-forward requires at least {MIN_TRAIN_BARS + MIN_OOS_BARS} "
                f"candles (got {len(prices) if prices else 0})."
            ),
        }

    n_windows = max(2, min(int(n_windows), 10))
    train_pct = max(0.5, min(float(train_pct), 0.9))
    num_variants = max(10, min(int(num_variants), 100))
    sim_config = sim_config or {}

    windows_spec = _build_windows(len(prices), n_windows, train_pct)
    if not windows_spec:
        return {
            "success": False,
            "mode": "walk_forward",
            "error": (
                f"Could not build {n_windows} walk-forward windows from "
                f"{len(prices)} candles with train_pct={train_pct}."
            ),
        }

    results = []
    for spec in windows_spec:
        train_slice = prices[spec["train_start"]:spec["train_end"]]
        oos_slice = prices[spec["oos_start"]:spec["oos_end"]]

        # ── STEP 1: fit params on IS ONLY ──
        fit = fit_best_params(
            strategy_text, pair, timeframe,
            train_prices=train_slice,
            num_variants=num_variants,
            sim_config=sim_config,
            rng_seed=_seed_for_window(strategy_text, spec["idx"]),
        )
        if not fit.get("success"):
            logger.warning(f"WF window {spec['idx']} fit failed: {fit.get('error')}")
            continue

        frozen_params = fit["params"]
        strategy_type = fit["strategy_type"]
        is_metrics = fit["metrics"]

        # ── STEP 2: score on OOS with frozen params ──
        oos = score_frozen_params(
            strategy_text, pair, timeframe,
            prices=oos_slice,
            params=frozen_params,
            strategy_type=strategy_type,
            sim_config=sim_config,
        )
        if not oos.get("success"):
            logger.warning(f"WF window {spec['idx']} OOS score failed: {oos.get('error')}")
            continue
        oos_metrics = oos["metrics"]

        results.append({
            "window": spec["idx"] + 1,
            "train_range": [spec["train_start"], spec["train_end"]],
            "oos_range": [spec["oos_start"], spec["oos_end"]],
            "train_candles": len(train_slice),
            "oos_candles": len(oos_slice),
            "frozen_params": frozen_params,
            "strategy_type": strategy_type,
            "is_metrics": is_metrics,
            "oos_metrics": oos_metrics,
            "degradation_pct": _degradation_pct(
                is_metrics.get("total_return_pct", 0),
                oos_metrics.get("total_return_pct", 0),
            ),
            "variants_evaluated": fit.get("variants_evaluated", 0),
        })

    if not results:
        return {
            "success": False,
            "mode": "walk_forward",
            "error": "No walk-forward windows produced valid results.",
        }

    # ── Aggregate ──
    oos_rets = [w["oos_metrics"].get("total_return_pct", 0) for w in results]
    oos_sharpes = [w["oos_metrics"].get("sharpe_ratio", 0) for w in results]
    is_rets = [w["is_metrics"].get("total_return_pct", 0) for w in results]
    degs = [w["degradation_pct"] for w in results]
    profitable = sum(1 for r in oos_rets if r > 0)

    aggregate = {
        "oos_avg_return_pct": round(sum(oos_rets) / len(oos_rets), 2),
        "oos_avg_sharpe": round(sum(oos_sharpes) / len(oos_sharpes), 3),
        "oos_profitable_ratio": round(profitable / len(results), 3),
        "oos_profitable_windows": profitable,
        "is_avg_return_pct": round(sum(is_rets) / len(is_rets), 2),
        "mean_degradation_pct": round(sum(degs) / len(degs), 2),
        "stability_score": _stability_from_windows(results),
    }

    return {
        "success": True,
        "mode": "walk_forward",
        "n_windows": len(results),
        "requested_windows": n_windows,
        "train_pct": round(train_pct, 2),
        "num_variants": num_variants,
        "total_candles": len(prices),
        "train_size": results[0]["train_candles"] if results else 0,
        "oos_size": results[0]["oos_candles"] if results else 0,
        "step_size": results[0]["oos_candles"] if results else 0,
        "windows": results,
        "aggregate": aggregate,
        "_leakage_guard": {
            "fit_sees_train_only": True,
            "score_sees_oos_only": True,
            "params_frozen_before_oos": True,
        },
    }



# ────────────────────────────────────────────────────────────────────
# Phase 29.0 — regime coverage summary (SUPPLEMENT, observational only)
# ────────────────────────────────────────────────────────────────────
#
# Annotates each walk-forward window with the regime label of its OOS
# slice and aggregates a distribution + Shannon entropy. Does NOT mutate
# the input `windows` list. Does NOT call the optimizer. Does NOT write
# anywhere. Pure function.
#
# Original `run_walk_forward` above remains byte-identical.
# ────────────────────────────────────────────────────────────────────


def _shannon_entropy(counts: dict) -> float:
    """Shannon entropy (natural log) over a count distribution.
    Returns 0.0 when all counts are concentrated in a single bucket.
    Returns ln(k) when uniform across k non-zero buckets."""
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    import math as _math
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * _math.log(p)
    return round(h, 6)


def regime_coverage_summary(
    windows: list,
    prices: list,
    regime_window: int = 100,
) -> dict:
    """Annotate walk-forward windows with regime coverage.

    Args:
        windows: the `windows` list returned by ``run_walk_forward`` —
            each item carries ``train_range``, ``oos_range``,
            ``window`` (1-indexed). Read-only — function does NOT
            mutate.
        prices: the original price series used by the walk-forward
            (needed to classify each window's slice regime).
        regime_window: trailing-window size for the regime classifier
            (default 100, matching ``regime_classifier.WINDOW_DEFAULT``).

    Returns:
        {
          "windows_summary": [
              {"window": int, "train_regime": str, "oos_regime": str,
               "train_range": [a, b], "oos_range": [c, d]},
              ...
          ],
          "regime_distribution_oos":   {trending: int, ranging: int,
                                         high_volatility: int,
                                         low_volatility: int,
                                         unknown: int},
          "regime_entropy_oos":        float,
          "windows_total":             int,
          "phase":                     "29.0",
          "advisory_only":             True,
        }

    Honest refusal: empty windows or empty prices → stable shape with
    zero counts and entropy 0.0. Never raises.
    """
    from engines.regime_classifier import classify_regime
    from engines.regime_performance import REGIMES_CANONICAL, REGIME_UNKNOWN

    all_regimes = list(REGIMES_CANONICAL) + [REGIME_UNKNOWN]
    distribution: dict = {r: 0 for r in all_regimes}
    summary: list = []

    if not windows or not prices:
        return {
            "windows_summary":         [],
            "regime_distribution_oos": distribution,
            "regime_entropy_oos":      0.0,
            "windows_total":           0,
            "phase":                   "29.0",
            "advisory_only":           True,
        }

    n = len(prices)
    for win in windows:
        try:
            train_range = list(win.get("train_range") or [])
            oos_range = list(win.get("oos_range") or [])
            if len(train_range) != 2 or len(oos_range) != 2:
                continue
            ts, te = int(train_range[0]), int(train_range[1])
            os_, oe = int(oos_range[0]), int(oos_range[1])
            # Bound checks — never crash on stale window indices.
            ts = max(0, min(ts, n))
            te = max(ts, min(te, n))
            os_ = max(0, min(os_, n))
            oe = max(os_, min(oe, n))

            train_slice = prices[ts:te]
            oos_slice = prices[os_:oe]

            try:
                train_regime = classify_regime(
                    train_slice, window=int(regime_window),
                ) if train_slice else REGIME_UNKNOWN
            except Exception:
                train_regime = REGIME_UNKNOWN

            try:
                oos_regime = classify_regime(
                    oos_slice, window=int(regime_window),
                ) if oos_slice else REGIME_UNKNOWN
            except Exception:
                oos_regime = REGIME_UNKNOWN

            # Bucket non-canonical labels under unknown for safety.
            if oos_regime not in all_regimes:
                oos_regime = REGIME_UNKNOWN
            if train_regime not in all_regimes:
                train_regime = REGIME_UNKNOWN

            distribution[oos_regime] = distribution.get(oos_regime, 0) + 1
            summary.append({
                "window":       win.get("window"),
                "train_regime": train_regime,
                "oos_regime":   oos_regime,
                "train_range":  [ts, te],
                "oos_range":    [os_, oe],
            })
        except Exception:                                    # pragma: no cover
            continue

    return {
        "windows_summary":         summary,
        "regime_distribution_oos": distribution,
        "regime_entropy_oos":      _shannon_entropy(distribution),
        "windows_total":           len(summary),
        "phase":                   "29.0",
        "advisory_only":           True,
    }
