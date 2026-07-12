"""
Pass Probability Engine — Monte Carlo Simulation (Phase 5).

Estimates the probability of passing a prop firm challenge by running
N simulations with trade resampling. Each simulation either:
  - Block-shuffles trade order (groups of 5–10 consecutive trading days)
    — preserves market structure, streaks, and volatility clusters within
    each block.
  - Applies small random perturbation to PnL (tests outcome sensitivity).

The legacy day-level shuffle is still available via
`shuffle_method="legacy"` for backward-comparison tests.

Lightweight: no ML, no regime detection. Uses the existing challenge
simulator directly.

Output: pass_probability %, avg_days_to_pass, failure_breakdown,
        confidence_interval, per-simulation details.
"""

import math
import random
import logging
from collections import Counter, defaultdict
from engines.challenge_simulator import simulate_challenge

logger = logging.getLogger(__name__)

DEFAULT_MIN_BLOCK_DAYS = 5
DEFAULT_MAX_BLOCK_DAYS = 10


def _extract_day(trade: dict):
    for key in ("timestamp", "close_time", "exit_time"):
        ts = trade.get(key)
        if ts and isinstance(ts, str) and len(ts) >= 10:
            return ts[:10]
    return None


def _group_by_day(trades: list):
    """Return (day_order, day_map) preserving first-seen day order."""
    day_map = defaultdict(list)
    day_order = []
    for t in trades:
        day = _extract_day(t) or "__noday__"
        if day not in day_map:
            day_order.append(day)
        day_map[day].append(t)
    return day_order, day_map


def _shuffle_trades(trades: list, rng: random.Random) -> list:
    """
    Legacy day-level shuffle: shuffles day order AND intra-day trade order.

    Destroys multi-day streak structure. Kept for backward-comparison tests
    and reachable via `shuffle_method="legacy"` in `estimate_pass_probability`.
    """
    day_order, day_map = _group_by_day(trades)
    rng.shuffle(day_order)

    result = []
    for day in day_order:
        day_trades = list(day_map[day])
        rng.shuffle(day_trades)
        result.extend(day_trades)
    return result


def _block_shuffle_trades(
    trades: list,
    rng: random.Random,
    min_block_days: int = DEFAULT_MIN_BLOCK_DAYS,
    max_block_days: int = DEFAULT_MAX_BLOCK_DAYS,
) -> list:
    """
    Block-based shuffle (Phase 5 upgrade).

    - Groups trades by trading day (preserves intra-day trade order).
    - Splits the ordered day list into consecutive blocks whose length is
      drawn uniformly from [min_block_days, max_block_days] per call.
    - Shuffles the blocks (not the days within a block, not the trades
      within a day) → preserves realistic streaks & volatility clusters.

    If the dataset is too small to form 2+ blocks, returns the original
    sequence unchanged (no valid block shuffle possible).
    """
    day_order, day_map = _group_by_day(trades)
    n_days = len(day_order)

    if n_days < 2:
        return list(trades)

    # Pick a block size for this run; if we have few days, shrink it so that
    # at least two blocks are formed (otherwise the shuffle is a no-op).
    block_size = rng.randint(min_block_days, max_block_days)
    if block_size > n_days // 2:
        block_size = max(1, n_days // 2)

    blocks = [
        day_order[i : i + block_size]
        for i in range(0, n_days, block_size)
    ]
    if len(blocks) < 2:
        return list(trades)

    rng.shuffle(blocks)

    result = []
    for block in blocks:
        for day in block:
            # Preserve intra-day trade order to keep realistic session structure.
            result.extend(day_map[day])
    return result


def _perturb_trades(trades: list, rng: random.Random, noise_pct: float = 0.10) -> list:
    """
    Apply small random perturbation to each trade's PnL.
    noise_pct: max ±% variation (default 10%).
    Preserves trade direction (win stays win, loss stays loss).
    """
    perturbed = []
    for t in trades:
        trade = {**t}
        pnl = trade.get("net_pnl", 0)
        if pnl != 0:
            noise = rng.uniform(-noise_pct, noise_pct)
            new_pnl = pnl * (1 + noise)
            # Preserve direction
            if pnl > 0 and new_pnl < 0:
                new_pnl = pnl * 0.1
            elif pnl < 0 and new_pnl > 0:
                new_pnl = pnl * 0.1
            trade["net_pnl"] = round(new_pnl, 2)

        # Perturb floating PnL too
        floating = trade.get("floating_pnl", 0)
        if floating != 0:
            noise = rng.uniform(-noise_pct, noise_pct)
            trade["floating_pnl"] = round(floating * (1 + noise), 2)

        perturbed.append(trade)
    return perturbed


def _confidence_interval(pass_rate: float, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for binomial proportion (95% CI)."""
    if n == 0:
        return (0.0, 0.0)
    p = pass_rate / 100.0
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    lo = max(0.0, center - spread) * 100
    hi = min(100.0, center + spread) * 100
    return (round(lo, 1), round(hi, 1))


def _robustness_label(score: float) -> str:
    """Interpret a structural robustness score."""
    if score > 80:
        return "robust"
    if score >= 50:
        return "moderate"
    return "fragile"


def _structural_robustness(block_prob: float, legacy_prob: float) -> dict:
    """
    Ratio of block-based (cluster-preserving) pass probability to the
    legacy (structure-destroying) pass probability, expressed 0–100.

      score = 100 × block_prob / legacy_prob,   clamped to [0, 100].

    If legacy_prob == 0, score = 0 (we cannot measure inflation when the
    inflated estimate itself is zero).
    """
    if legacy_prob <= 0:
        score = 0.0
    else:
        score = 100.0 * (block_prob / legacy_prob)
        if score < 0.0:
            score = 0.0
        elif score > 100.0:
            score = 100.0
    score = round(score, 1)
    return {
        "score": score,
        "label": _robustness_label(score),
        "block_pass_probability": round(block_prob, 1),
        "legacy_pass_probability": round(legacy_prob, 1),
    }


def estimate_pass_probability(
    trades: list,
    rules_config: dict,
    n_simulations: int = 50,
    seed: int = 42,
    noise_pct: float = 0.10,
    shuffle_method: str = "block_based",
    min_block_days: int = DEFAULT_MIN_BLOCK_DAYS,
    max_block_days: int = DEFAULT_MAX_BLOCK_DAYS,
    compute_robustness: bool = True,
) -> dict:
    """
    Monte Carlo pass probability estimation.

    For each of N simulations:
      - Odd runs: shuffle trade order
      - Even runs: perturb trade PnL by ±noise_pct
    Then run challenge simulator and collect results.

    When `compute_robustness=True` and `shuffle_method="block_based"` (the
    default), the engine also runs a parallel legacy-shuffle MC with the
    same seed / n_simulations and attaches a `structural_robustness` block:

        score = 100 × (block_pass_prob / legacy_pass_prob), clamped [0,100].

    A high score → the block-based estimate agrees with the legacy one,
    so the strategy is not relying on favorable path structure.
    A low score → the legacy estimate was inflated by cluster-breaking
    shuffles; the strategy is fragile to realistic sequencing.

    Args:
        trades: list of trade dicts (same format as challenge simulator)
        rules_config: firm rules (flat dict for simulator)
        n_simulations: number of MC runs (default 50, capped at 200)
        seed: random seed for reproducibility
        noise_pct: max perturbation as fraction (default 0.10 = ±10%)
        shuffle_method: "block_based" (Phase 5 default — preserves streaks)
                        or "legacy" (day-level shuffle, inflates pass rate).
        min_block_days / max_block_days: block-size range for block shuffle
                        (ignored when shuffle_method == "legacy").
        compute_robustness: if True (default) and shuffle_method is block_based,
                        also run a legacy-shuffle MC and return the structural
                        robustness score / label.

    Returns:
        dict with pass_probability, avg_days_to_pass, failure_breakdown,
        confidence_interval, simulation_details, `shuffle_method`, and
        (when applicable) `structural_robustness`.
    """
    if not trades:
        return {
            "pass_probability": 0.0,
            "confidence_interval": [0.0, 0.0],
            "n_simulations": 0,
            "avg_days_to_pass": 0,
            "failure_breakdown": {},
            "shuffle_method": shuffle_method,
            "error": "No trades provided",
        }

    if shuffle_method not in ("block_based", "legacy"):
        raise ValueError(
            f"shuffle_method must be 'block_based' or 'legacy', got {shuffle_method!r}"
        )
    if min_block_days < 1 or max_block_days < min_block_days:
        raise ValueError("invalid block size range")

    n_simulations = max(10, min(n_simulations, 200))
    rng = random.Random(seed)

    passes = 0
    fails = 0
    days_to_pass = []
    failure_reasons = Counter()
    sim_details = []

    # Also run the original (unmodified) trade sequence as simulation 0
    baseline = simulate_challenge(trades, rules_config)
    baseline_status = baseline.get("status", "fail")

    for i in range(n_simulations):
        # Alternate between shuffle and perturb
        if i % 2 == 0:
            if shuffle_method == "block_based":
                sim_trades = _block_shuffle_trades(
                    trades, rng, min_block_days, max_block_days
                )
            else:
                sim_trades = _shuffle_trades(trades, rng)
            method = "shuffle"
        else:
            sim_trades = _perturb_trades(trades, rng, noise_pct)
            method = "perturb"

        result = simulate_challenge(sim_trades, rules_config)
        status = result.get("status", "fail")

        if status == "pass":
            passes += 1
            days_to_pass.append(result.get("days_taken", 0))
        else:
            fails += 1
            reason = result.get("failure_reason", "unknown")
            failure_reasons[reason] += 1

        sim_details.append({
            "run": i + 1,
            "method": method,
            "status": status,
            "days_taken": result.get("days_taken", 0),
            "profit_pct": result.get("profit_pct", 0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0),
            "max_daily_dd_pct": result.get("max_daily_drawdown_pct", 0),
            "failure_reason": result.get("failure_reason"),
        })

    total = passes + fails
    pass_prob = round((passes / total) * 100, 1) if total > 0 else 0
    ci = _confidence_interval(pass_prob, total)
    avg_days = round(sum(days_to_pass) / len(days_to_pass), 1) if days_to_pass else 0

    # Failure breakdown as percentages of total failures
    fail_breakdown = {}
    if fails > 0:
        for reason, count in failure_reasons.items():
            fail_breakdown[reason] = round((count / fails) * 100, 1)

    # Stability: how consistent are the results across methods
    shuffle_passes = sum(1 for d in sim_details if d["method"] == "shuffle" and d["status"] == "pass")
    perturb_passes = sum(1 for d in sim_details if d["method"] == "perturb" and d["status"] == "pass")
    shuffle_total = sum(1 for d in sim_details if d["method"] == "shuffle")
    perturb_total = sum(1 for d in sim_details if d["method"] == "perturb")
    shuffle_rate = round(shuffle_passes / shuffle_total * 100, 1) if shuffle_total > 0 else 0
    perturb_rate = round(perturb_passes / perturb_total * 100, 1) if perturb_total > 0 else 0

    # Risk assessment
    if pass_prob >= 80:
        risk_label = "low"
    elif pass_prob >= 50:
        risk_label = "medium"
    elif pass_prob >= 20:
        risk_label = "high"
    else:
        risk_label = "very_high"

    result = {
        "pass_probability": pass_prob,
        "confidence_interval": list(ci),
        "risk_label": risk_label,
        "n_simulations": n_simulations,
        "passes": passes,
        "fails": fails,
        "avg_days_to_pass": avg_days,
        "failure_breakdown": fail_breakdown,
        "shuffle_method": shuffle_method,
        "method_comparison": {
            "shuffle_pass_rate": shuffle_rate,
            "perturb_pass_rate": perturb_rate,
        },
        "baseline": {
            "status": baseline_status,
            "profit_pct": baseline.get("profit_pct", 0),
            "max_drawdown_pct": baseline.get("max_drawdown_pct", 0),
        },
        "simulation_details": sim_details,
    }

    # ── Structural robustness: block-based vs legacy comparison ──
    # Only meaningful when the primary run used block-based shuffle.
    if compute_robustness and shuffle_method == "block_based":
        legacy = estimate_pass_probability(
            trades, rules_config,
            n_simulations=n_simulations,
            seed=seed,
            noise_pct=noise_pct,
            shuffle_method="legacy",
            compute_robustness=False,   # prevent recursion
        )
        result["structural_robustness"] = _structural_robustness(
            block_prob=pass_prob,
            legacy_prob=legacy["pass_probability"],
        )

    return result
