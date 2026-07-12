"""
Phase 8 — True Out-Of-Sample Holdout.

Classic 80/20 holdout:
  1. Split dataset chronologically into train (default 80%) and OOS (20%).
  2. Optimize parameters on train ONLY via random search.
  3. Freeze the winning parameters.
  4. Replay once on the OOS slice — the OOS slice is never seen during
     selection and never re-optimized.

Returns train vs OOS metrics and a degradation percentage.
"""
from __future__ import annotations

import hashlib
import logging
from engines.random_search_optimizer import fit_best_params, score_frozen_params

logger = logging.getLogger(__name__)

MIN_TRAIN_BARS = 80
MIN_OOS_BARS = 20
DEFAULT_TRAIN_PCT = 0.80
DEFAULT_NUM_VARIANTS = 60


def _seed_for_holdout(strategy_text: str) -> int:
    return int(hashlib.md5(f"{strategy_text}|holdout".encode()).hexdigest()[:8], 16)


def _degradation_pct(is_val: float, oos_val: float) -> float:
    if is_val is None or oos_val is None:
        return 0.0
    if abs(is_val) < 1e-9:
        return 0.0 if abs(oos_val) < 1e-9 else (-100.0 if oos_val > 0 else 100.0)
    deg = (is_val - oos_val) / abs(is_val) * 100.0
    return round(max(-200.0, min(200.0, deg)), 2)


def run_oos_holdout(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    train_pct: float = DEFAULT_TRAIN_PCT,
    num_variants: int = DEFAULT_NUM_VARIANTS,
    sim_config: dict = None,
) -> dict:
    """
    Strict 80/20 train/OOS holdout.

    No leakage:
      * fit_best_params sees train_prices ONLY
      * score_frozen_params sees oos_prices ONLY
      * params are frozen between the two calls
    """
    if not prices or len(prices) < MIN_TRAIN_BARS + MIN_OOS_BARS:
        return {
            "success": False,
            "mode": "holdout",
            "error": (
                f"Holdout requires at least {MIN_TRAIN_BARS + MIN_OOS_BARS} candles "
                f"(got {len(prices) if prices else 0})."
            ),
        }

    train_pct = max(0.5, min(float(train_pct), 0.9))
    num_variants = max(10, min(int(num_variants), 200))
    sim_config = sim_config or {}

    split_idx = int(len(prices) * train_pct)
    train_prices = prices[:split_idx]
    oos_prices = prices[split_idx:]

    if len(train_prices) < MIN_TRAIN_BARS or len(oos_prices) < MIN_OOS_BARS:
        return {
            "success": False,
            "mode": "holdout",
            "error": (
                f"Holdout split too small: train={len(train_prices)}, "
                f"oos={len(oos_prices)} (need >= {MIN_TRAIN_BARS}/{MIN_OOS_BARS})."
            ),
        }

    # ── STEP 1: optimize on train ONLY ──
    fit = fit_best_params(
        strategy_text, pair, timeframe,
        train_prices=train_prices,
        num_variants=num_variants,
        sim_config=sim_config,
        rng_seed=_seed_for_holdout(strategy_text),
    )
    if not fit.get("success"):
        return {
            "success": False,
            "mode": "holdout",
            "error": fit.get("error", "fit_best_params failed"),
        }

    frozen_params = fit["params"]
    strategy_type = fit["strategy_type"]
    train_metrics = fit["metrics"]

    # ── STEP 2: replay on OOS with frozen params ──
    oos = score_frozen_params(
        strategy_text, pair, timeframe,
        prices=oos_prices,
        params=frozen_params,
        strategy_type=strategy_type,
        sim_config=sim_config,
    )
    if not oos.get("success"):
        return {
            "success": False,
            "mode": "holdout",
            "error": oos.get("error", "score_frozen_params failed"),
        }
    oos_metrics = oos["metrics"]

    # ── Degradation & overfit flag ──
    train_ret = train_metrics.get("total_return_pct", 0)
    oos_ret = oos_metrics.get("total_return_pct", 0)
    deg_return = _degradation_pct(train_ret, oos_ret)
    deg_sharpe = _degradation_pct(
        train_metrics.get("sharpe_ratio", 0),
        oos_metrics.get("sharpe_ratio", 0),
    )

    overfit_flag = False
    overfit_reason = None
    if train_ret > 0 and oos_ret < 0:
        overfit_flag = True
        overfit_reason = "Profitable on train, negative on OOS."
    elif train_ret > 0 and oos_ret < train_ret * 0.3:
        overfit_flag = True
        overfit_reason = "OOS return < 30% of train return."

    return {
        "success": True,
        "mode": "holdout",
        "train_pct": round(train_pct, 2),
        "total_candles": len(prices),
        "train_candles": len(train_prices),
        "oos_candles": len(oos_prices),
        "strategy_type": strategy_type,
        "frozen_params": frozen_params,
        "variants_evaluated": fit.get("variants_evaluated", 0),
        "train_metrics": train_metrics,
        "oos_metrics": oos_metrics,
        "degradation": {
            "return_pct_degradation": deg_return,
            "sharpe_degradation": deg_sharpe,
        },
        "overfit": {
            "flagged": overfit_flag,
            "reason": overfit_reason,
        },
        "_leakage_guard": {
            "fit_sees_train_only": True,
            "score_sees_oos_only": True,
            "params_frozen_before_oos": True,
        },
    }



# ────────────────────────────────────────────────────────────────────
# Phase 29.0 — regime-stratified OOS (SUPPLEMENT, NOT replacement)
# ────────────────────────────────────────────────────────────────────
#
# Operator decision #3: this is a supplement, NOT a replacement. The
# canonical `run_oos_holdout` above is byte-identical to its pre-Phase-29
# form. `_gate_validated` continues reading `lib.oos_holdout.ratio`
# from the original path.
#
# Contiguity caveat: each canonical regime's longest contiguous
# stable-regime run is used as the per-regime stratum. This preserves
# indicator continuity. A regime that never appears as a stable run of
# ≥ MIN_TRAIN_BARS + MIN_OOS_BARS contributes `null` evidence (honest
# refusal, never silent zero).
#
# Output is observational only. Does NOT write to `lib.oos_holdout`,
# does NOT alter `_gate_validated` inputs, does NOT touch lifecycle docs.
# ────────────────────────────────────────────────────────────────────


def _regime_labels_for_prices(
    prices: list,
    window: int = 100,
) -> list:
    """Per-bar regime label using the trailing window. Bars without a
    full window report `unknown` (honest refusal, never silent default).
    """
    from engines.regime_classifier import classify_regime, MIN_SAMPLES
    labels: list = []
    n = len(prices)
    for i in range(n):
        lo = max(0, i - window + 1)
        sub = prices[lo: i + 1]
        if len(sub) < MIN_SAMPLES:
            labels.append("unknown")
            continue
        try:
            labels.append(classify_regime(sub, window=window))
        except Exception:
            labels.append("unknown")
    return labels


def _longest_contiguous_run(labels: list, target: str) -> tuple:
    """Return (start_idx, end_idx) of the longest contiguous run where
    `labels[i] == target`. Returns (None, None) if none found."""
    best_start = None
    best_len = 0
    cur_start = None
    cur_len = 0
    for i, lab in enumerate(labels):
        if lab == target:
            if cur_start is None:
                cur_start = i
                cur_len = 1
            else:
                cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
        else:
            cur_start = None
            cur_len = 0
    if best_start is None:
        return (None, None)
    return (best_start, best_start + best_len)


def run_oos_holdout_regime_stratified(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    train_pct: float = DEFAULT_TRAIN_PCT,
    num_variants: int = DEFAULT_NUM_VARIANTS,
    sim_config: dict = None,
    regime_window: int = 100,
) -> dict:
    """SUPPLEMENT to ``run_oos_holdout``. Stratifies by canonical regime
    (longest contiguous run per regime), runs an 80/20 holdout WITHIN
    each stratum, and reports per-regime OOS metrics.

    This function does NOT mutate `lib.oos_holdout`. It does NOT alter
    `_gate_validated` inputs. It is observational evidence only.

    Returns:
        {
          "success": bool,
          "mode": "holdout_regime_stratified",
          "per_regime": {
              "trending":         {pf, total_return_pct, sharpe, ratio,
                                    train_bars, oos_bars, edge_positive,
                                    frozen_params} | None,
              "ranging":          { ... } | None,
              "high_volatility":  { ... } | None,
              "low_volatility":   { ... } | None,
          },
          "regimes_with_evidence": int,
          "regime_window":         int,
          "_note":                 "supplement only — does not write lib.oos_holdout",
          "_leakage_guard":        {...},
          "phase":                 "29.0",
          "advisory_only":         True,
        }
    """
    from engines.regime_performance import REGIMES_CANONICAL

    out_per_regime: dict = {r: None for r in REGIMES_CANONICAL}

    if not prices or len(prices) < MIN_TRAIN_BARS + MIN_OOS_BARS:
        return {
            "success": False,
            "mode": "holdout_regime_stratified",
            "error": (
                f"Stratified holdout requires at least "
                f"{MIN_TRAIN_BARS + MIN_OOS_BARS} candles "
                f"(got {len(prices) if prices else 0})."
            ),
            "per_regime":            out_per_regime,
            "regimes_with_evidence": 0,
            "regime_window":         int(regime_window),
            "phase":                 "29.0",
            "advisory_only":         True,
        }

    train_pct = max(0.5, min(float(train_pct), 0.9))
    num_variants = max(10, min(int(num_variants), 200))
    sim_config = sim_config or {}

    labels = _regime_labels_for_prices(prices, window=int(regime_window))
    regimes_with_evidence = 0

    for regime in REGIMES_CANONICAL:
        start, end = _longest_contiguous_run(labels, regime)
        if start is None or (end - start) < MIN_TRAIN_BARS + MIN_OOS_BARS:
            out_per_regime[regime] = None
            continue

        seg = prices[start:end]
        split_idx = int(len(seg) * train_pct)
        train_slice = seg[:split_idx]
        oos_slice = seg[split_idx:]
        if len(train_slice) < MIN_TRAIN_BARS or len(oos_slice) < MIN_OOS_BARS:
            out_per_regime[regime] = None
            continue

        try:
            fit = fit_best_params(
                strategy_text, pair, timeframe,
                train_prices=train_slice,
                num_variants=num_variants,
                sim_config=sim_config,
                rng_seed=_seed_for_holdout(f"{strategy_text}|regime|{regime}"),
            )
        except Exception as e:                               # pragma: no cover
            logger.debug("stratified fit failed (%s): %s", regime, e)
            out_per_regime[regime] = None
            continue

        if not fit.get("success"):
            out_per_regime[regime] = None
            continue

        try:
            oos = score_frozen_params(
                strategy_text, pair, timeframe,
                prices=oos_slice,
                params=fit["params"],
                strategy_type=fit["strategy_type"],
                sim_config=sim_config,
            )
        except Exception as e:                               # pragma: no cover
            logger.debug("stratified score failed (%s): %s", regime, e)
            out_per_regime[regime] = None
            continue

        if not oos.get("success"):
            out_per_regime[regime] = None
            continue

        train_m = fit.get("metrics") or {}
        oos_m = oos.get("metrics") or {}
        train_ret = train_m.get("total_return_pct", 0) or 0
        oos_ret = oos_m.get("total_return_pct", 0) or 0
        ratio = _degradation_pct(train_ret, oos_ret)

        out_per_regime[regime] = {
            "pf":                  oos_m.get("profit_factor"),
            "total_return_pct":    oos_m.get("total_return_pct"),
            "sharpe":              oos_m.get("sharpe_ratio"),
            "train_total_return":  train_ret,
            "degradation_pct":     ratio,
            "train_bars":          len(train_slice),
            "oos_bars":            len(oos_slice),
            "stratum_start":       start,
            "stratum_end":         end,
            "edge_positive": bool(
                isinstance(oos_m.get("profit_factor"), (int, float))
                and oos_m["profit_factor"] >= 1.0
                and oos_ret > 0
            ),
            "frozen_params":       fit.get("params"),
            "strategy_type":       fit.get("strategy_type"),
        }
        regimes_with_evidence += 1

    return {
        "success":               True,
        "mode":                  "holdout_regime_stratified",
        "total_candles":         len(prices),
        "regime_window":         int(regime_window),
        "per_regime":            out_per_regime,
        "regimes_with_evidence": regimes_with_evidence,
        "_note": "supplement only — does not write lib.oos_holdout",
        "_leakage_guard": {
            "fit_sees_train_only":     True,
            "score_sees_oos_only":     True,
            "params_frozen_before_oos": True,
            "per_regime_stratified":   True,
        },
        "phase":          "29.0",
        "advisory_only":  True,
    }
