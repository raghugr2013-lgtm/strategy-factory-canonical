"""
Portfolio-level risk control engine.
Analyzes combined risk of multiple strategies: correlation, combined drawdown,
volatility, portfolio risk score, and allocation suggestions.
"""
import math
import logging

logger = logging.getLogger(__name__)


def _extract_returns(equity_curve: list) -> list:
    """Convert equity curve to period returns (%)."""
    if not equity_curve or len(equity_curve) < 2:
        return []
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] != 0:
            r = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1] * 100
        else:
            r = 0
        returns.append(r)
    return returns


def _pearson_correlation(x: list, y: list) -> float:
    """Calculate Pearson correlation between two return series."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return 0.0
    return round(num / (dx * dy), 3)


def _normalize_equity(curve: list, target_len: int) -> list:
    """Resample equity curve to target_len points via linear interpolation."""
    if not curve:
        return [0.0] * target_len
    if len(curve) == target_len:
        return curve
    if len(curve) == 1:
        return curve * target_len
    result = []
    for i in range(target_len):
        t = i / (target_len - 1) * (len(curve) - 1)
        lo = int(t)
        hi = min(lo + 1, len(curve) - 1)
        frac = t - lo
        result.append(curve[lo] * (1 - frac) + curve[hi] * frac)
    return result


def analyze_portfolio(strategies: list, allocations: list = None) -> dict:
    """
    Analyze a portfolio of strategies.

    Args:
        strategies: list of strategy dicts with backtest_results containing equity_curve + trades
        allocations: optional weight list (sums to 1.0). Default: equal weight.

    Returns:
        dict with correlation_matrix, combined equity, risk metrics, allocation suggestions
    """
    n = len(strategies)
    if n == 0:
        return {"error": "No strategies provided"}
    if n == 1:
        bt = strategies[0].get("backtest_results", {})
        return {
            "num_strategies": 1,
            "combined_metrics": {
                "total_profit": bt.get("net_profit", 0),
                "total_return_pct": bt.get("total_return_pct", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "volatility": 0,
            },
            "correlation_matrix": [[1.0]],
            "portfolio_risk_score": bt.get("max_drawdown_pct", 0) * 2,
            "diversification_grade": "N/A",
            "allocations": [1.0],
            "strategies_summary": [{
                "pair": strategies[0].get("pair", ""),
                "timeframe": strategies[0].get("timeframe", ""),
                "score": strategies[0].get("score", 0),
                "net_profit": bt.get("net_profit", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
            }],
            "warnings": ["Single strategy — no diversification benefit"],
        }

    # Default equal allocation
    if not allocations or len(allocations) != n:
        allocations = [1.0 / n] * n

    # Normalize allocations to sum to 1
    total_alloc = sum(allocations)
    if total_alloc > 0:
        allocations = [a / total_alloc for a in allocations]

    # Extract equity curves and returns
    equity_curves = []
    return_series = []
    initial_balance = 10000.0

    for s in strategies:
        bt = s.get("backtest_results", {})
        ec = bt.get("equity_curve", [])
        if not ec or len(ec) < 2:
            # Synthesize from trades
            trades = bt.get("trades", [])
            bal = bt.get("initial_balance", initial_balance)
            ec = [bal]
            for t in trades:
                bal += t.get("net_pnl", 0)
                ec.append(round(bal, 2))
            if len(ec) < 2:
                ec = [initial_balance, initial_balance + bt.get("net_profit", 0)]
        equity_curves.append(ec)
        return_series.append(_extract_returns(ec))

    # Normalize all curves to same length for combination
    target_len = max(len(ec) for ec in equity_curves)
    target_len = max(target_len, 10)
    normalized = [_normalize_equity(ec, target_len) for ec in equity_curves]

    # ── Correlation Matrix ──
    corr_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                corr_matrix[i][j] = 1.0
            elif j > i:
                ri = _extract_returns(normalized[i])
                rj = _extract_returns(normalized[j])
                c = _pearson_correlation(ri, rj)
                corr_matrix[i][j] = c
                corr_matrix[j][i] = c

    # ── Highly Correlated Pairs ──
    high_corr_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if abs(corr_matrix[i][j]) > 0.7:
                high_corr_pairs.append({
                    "strategy_a": i,
                    "strategy_b": j,
                    "correlation": corr_matrix[i][j],
                })

    # ── Combined Equity Curve ──
    # Weighted sum: each strategy contributes allocation * (equity[t] / equity[0])
    combined_equity = []
    for t in range(target_len):
        combined_val = 0
        for i in range(n):
            if normalized[i][0] != 0:
                ratio = normalized[i][t] / normalized[i][0]
            else:
                ratio = 1.0
            combined_val += allocations[i] * ratio * initial_balance
        combined_equity.append(round(combined_val, 2))

    # ── Combined Metrics ──
    total_profit = combined_equity[-1] - combined_equity[0] if combined_equity else 0
    total_return_pct = (total_profit / combined_equity[0] * 100) if combined_equity and combined_equity[0] > 0 else 0

    # Max drawdown of combined curve
    peak = combined_equity[0] if combined_equity else initial_balance
    max_dd = 0
    for val in combined_equity:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Volatility (std dev of returns)
    combined_returns = _extract_returns(combined_equity)
    if combined_returns:
        mean_ret = sum(combined_returns) / len(combined_returns)
        variance = sum((r - mean_ret) ** 2 for r in combined_returns) / len(combined_returns)
        volatility = round(math.sqrt(variance), 2)
    else:
        volatility = 0

    # ── Average Correlation ──
    corr_values = []
    for i in range(n):
        for j in range(i + 1, n):
            corr_values.append(abs(corr_matrix[i][j]))
    avg_corr = round(sum(corr_values) / len(corr_values), 3) if corr_values else 0

    # ── Portfolio Risk Score (0-100, lower = better) ──
    # Components: avg_correlation (0-40), drawdown (0-40), volatility (0-20)
    corr_penalty = min(40, avg_corr * 40)
    dd_penalty = min(40, max_dd * 2)
    vol_penalty = min(20, volatility * 2)
    risk_score = round(corr_penalty + dd_penalty + vol_penalty, 1)
    risk_score = min(max(risk_score, 0), 100)

    # Diversification grade
    if risk_score <= 25:
        div_grade = "A"
    elif risk_score <= 40:
        div_grade = "B"
    elif risk_score <= 60:
        div_grade = "C"
    elif risk_score <= 80:
        div_grade = "D"
    else:
        div_grade = "F"

    # ── Optimal Allocation Suggestion ──
    # Inverse-volatility weighting: allocate more to lower-risk strategies
    individual_dd = []
    for s in strategies:
        bt = s.get("backtest_results", {})
        individual_dd.append(max(bt.get("max_drawdown_pct", 10), 0.1))

    inv_dd = [1.0 / d for d in individual_dd]
    inv_dd_sum = sum(inv_dd)
    suggested_alloc = [round(w / inv_dd_sum, 3) for w in inv_dd] if inv_dd_sum > 0 else allocations

    # ── Strategies Summary ──
    strat_summary = []
    for i, s in enumerate(strategies):
        bt = s.get("backtest_results", {})
        strat_summary.append({
            "index": i,
            "id": s.get("id", ""),
            "pair": s.get("pair", ""),
            "timeframe": s.get("timeframe", ""),
            "strategy_type": s.get("strategy_type", ""),
            "score": s.get("score", 0),
            "net_profit": bt.get("net_profit", 0),
            "win_rate": bt.get("win_rate", 0),
            "profit_factor": bt.get("profit_factor", 0),
            "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
            "total_trades": bt.get("total_trades", 0),
            "allocation": round(allocations[i], 3),
            "suggested_allocation": suggested_alloc[i],
        })

    # Warnings
    warnings = []
    if avg_corr > 0.7:
        warnings.append(f"High average correlation ({avg_corr:.2f}) — limited diversification benefit")
    if max_dd > 20:
        warnings.append(f"Combined drawdown {max_dd:.1f}% exceeds 20% threshold")
    if len(high_corr_pairs) > 0:
        warnings.append(f"{len(high_corr_pairs)} highly correlated pair(s) detected (>0.7)")
    all_same_pair = len(set(s.get("pair", "") for s in strategies)) == 1
    if all_same_pair and n > 1:
        warnings.append("All strategies on same pair — consider adding different pairs for diversification")

    logger.info(
        f"Portfolio: {n} strategies, avg_corr={avg_corr}, DD={max_dd:.1f}%, "
        f"risk_score={risk_score}, grade={div_grade}"
    )

    return {
        "num_strategies": n,
        "correlation_matrix": corr_matrix,
        "avg_correlation": avg_corr,
        "high_corr_pairs": high_corr_pairs,
        "combined_equity": combined_equity,
        "combined_metrics": {
            "total_profit": round(total_profit, 2),
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "volatility": volatility,
        },
        "portfolio_risk_score": risk_score,
        "risk_breakdown": {
            "correlation_penalty": round(corr_penalty, 1),
            "drawdown_penalty": round(dd_penalty, 1),
            "volatility_penalty": round(vol_penalty, 1),
        },
        "diversification_grade": div_grade,
        "allocations": [round(a, 3) for a in allocations],
        "suggested_allocations": suggested_alloc,
        "strategies_summary": strat_summary,
        "warnings": warnings,
    }



def auto_build_portfolio(
    candidates: list,
    target_size: int = 4,
    max_pair_corr: float = 0.6,
    min_score: float = 0,
    min_safety: float = 0,
) -> dict:
    """
    Automatically select the best portfolio from a pool of candidate strategies.

    Algorithm:
    1. Score & filter candidates (min score, min safety, must have equity data)
    2. Sort by composite merit (score + safety + return - drawdown penalty)
    3. Greedy selection: pick best, then add next-best that doesn't correlate
       highly with any already-selected strategy
    4. Prefer symbol/timeframe diversification
    5. Run full portfolio analysis on the selected set

    Args:
        candidates: list of strategy dicts from library
        target_size: desired portfolio size (3-5)
        max_pair_corr: max allowed pairwise correlation
        min_score: minimum strategy score filter
        min_safety: minimum safety score filter

    Returns:
        dict with selected_ids, portfolio analysis, selection_log
    """
    target_size = max(2, min(target_size, 7))
    selection_log = []

    # Step 1: Filter candidates
    viable = []
    for s in candidates:
        bt = s.get("backtest_results", {})
        score = s.get("score", 0)
        safety = s.get("safety", {})
        safety_score = safety.get("safety_score", 0) if isinstance(safety, dict) else 0

        # Must have equity data or trades
        ec = bt.get("equity_curve", [])
        trades = bt.get("trades", [])
        has_data = (len(ec) >= 2) or (len(trades) >= 1) or (bt.get("net_profit", 0) != 0)

        if not has_data:
            continue
        if score < min_score:
            continue
        if safety_score < min_safety:
            continue

        # Compute composite merit: higher = better
        dd = bt.get("max_drawdown_pct", 0)
        pf = bt.get("profit_factor", 0)
        ret = bt.get("total_return_pct", 0)

        merit = (
            score * 0.35
            + safety_score * 0.20
            + min(ret, 50) * 0.15  # Cap return contribution
            + min(pf, 3) * 10 * 0.15  # PF contribution (capped at 3)
            - dd * 0.15  # Drawdown penalty
        )

        # Build equity curve for correlation checks
        if not ec or len(ec) < 2:
            bal = bt.get("initial_balance", 10000)
            ec = [bal]
            for t in trades:
                bal += t.get("net_pnl", 0)
                ec.append(round(bal, 2))
            if len(ec) < 2:
                ec = [10000, 10000 + bt.get("net_profit", 0)]

        viable.append({
            **s,
            "_merit": merit,
            "_equity": ec,
            "_returns": _extract_returns(ec),
        })

    selection_log.append(f"Filtered: {len(viable)}/{len(candidates)} viable (min_score={min_score}, min_safety={min_safety})")

    if len(viable) < 2:
        return {
            "success": False,
            "error": f"Not enough viable strategies ({len(viable)}). Need at least 2.",
            "selection_log": selection_log,
        }

    # Step 2: Sort by merit
    viable.sort(key=lambda s: s["_merit"], reverse=True)

    # Step 3: Greedy diversified selection
    selected = [viable[0]]
    selected_pairs = {viable[0].get("pair", "")}
    selected_tfs = {viable[0].get("timeframe", "")}
    selection_log.append(f"Seed: {viable[0].get('pair')}/{viable[0].get('timeframe')} merit={viable[0]['_merit']:.1f}")

    for candidate in viable[1:]:
        if len(selected) >= target_size:
            break

        c_pair = candidate.get("pair", "")
        c_tf = candidate.get("timeframe", "")
        c_returns = candidate["_returns"]

        # Check correlation with all selected
        too_correlated = False
        for sel in selected:
            corr = _pearson_correlation(c_returns, sel["_returns"])
            if abs(corr) > max_pair_corr:
                too_correlated = True
                selection_log.append(
                    f"Skip: {c_pair}/{c_tf} — corr={corr:.2f} with {sel.get('pair')}/{sel.get('timeframe')}"
                )
                break

        if too_correlated:
            continue

        # Diversification bonus: prefer new pairs/timeframes
        # (no hard block, just a note)
        is_new_pair = c_pair not in selected_pairs
        is_new_tf = c_tf not in selected_tfs

        selected.append(candidate)
        selected_pairs.add(c_pair)
        selected_tfs.add(c_tf)
        selection_log.append(
            f"Added: {c_pair}/{c_tf} merit={candidate['_merit']:.1f}"
            f"{' (new pair)' if is_new_pair else ''}{' (new tf)' if is_new_tf else ''}"
        )

    # If we still need more, relax correlation threshold
    if len(selected) < 2:
        for candidate in viable[1:]:
            if len(selected) >= max(2, target_size):
                break
            cid = candidate.get("id", "")
            if any(s.get("id") == cid for s in selected):
                continue
            selected.append(candidate)
            selection_log.append(f"Added (relaxed): {candidate.get('pair')}/{candidate.get('timeframe')}")

    selection_log.append(f"Selected {len(selected)} strategies from {len(viable)} viable")

    # Step 4: Run full portfolio analysis
    # Clean up internal fields before analysis
    clean_selected = []
    for s in selected:
        clean = {k: v for k, v in s.items() if not k.startswith("_")}
        clean_selected.append(clean)

    portfolio = analyze_portfolio(clean_selected)

    return {
        "success": True,
        "selected_ids": [s.get("id", "") for s in selected],
        "num_candidates": len(candidates),
        "num_viable": len(viable),
        "num_selected": len(selected),
        "portfolio": portfolio,
        "selection_log": selection_log,
    }



# Default allocation rules by live tracking status
DEFAULT_ALLOC_RULES = {
    "STABLE": 1.0,
    "WARNING": 0.5,
    "FAILING": 0.0,
    "AUTO_DISABLED": 0.0,
}


def compute_dynamic_allocations(
    strategies: list,
    tracking_map: dict,
    alloc_rules: dict = None,
    use_safety_adjustment: bool = True,
) -> dict:
    """
    Compute dynamic capital allocations based on live tracking status.

    Args:
        strategies: list of strategy dicts from library
        tracking_map: {strategy_id: tracking_doc} from live_tracking collection
        alloc_rules: status → weight multiplier (0.0-1.0)
        use_safety_adjustment: further reduce allocation for high DD

    Returns:
        dict with per-strategy allocations, adjustments, and portfolio analysis
    """
    rules = alloc_rules or DEFAULT_ALLOC_RULES
    n = len(strategies)
    if n == 0:
        return {"error": "No strategies"}

    base_weight = 1.0 / n  # Equal base allocation
    adjustments = []

    for s in strategies:
        sid = s.get("id", "")
        tracking = tracking_map.get(sid, {})
        status = tracking.get("status", "STABLE")
        live_m = tracking.get("live_metrics", {}) or {}
        safety = s.get("safety", {}) or {}

        # Status-based multiplier
        status_mult = rules.get(status, 0.5)

        # Safety adjustment: reduce further if live DD is high
        safety_mult = 1.0
        if use_safety_adjustment and live_m:
            live_dd = live_m.get("max_drawdown_pct", 0)
            if live_dd > 20:
                safety_mult = 0.25
            elif live_dd > 15:
                safety_mult = 0.5
            elif live_dd > 10:
                safety_mult = 0.75

            # Also factor safety score
            ss = safety.get("safety_score", 100) if isinstance(safety, dict) else 100
            if ss < 40:
                safety_mult = min(safety_mult, 0.5)

        final_mult = status_mult * safety_mult
        raw_alloc = base_weight * final_mult
        cons_failures = tracking.get("consecutive_failures", 0)

        adjustments.append({
            "strategy_id": sid,
            "pair": s.get("pair", ""),
            "timeframe": s.get("timeframe", ""),
            "status": status,
            "base_weight": round(base_weight, 4),
            "status_multiplier": status_mult,
            "safety_multiplier": round(safety_mult, 2),
            "final_multiplier": round(final_mult, 2),
            "raw_allocation": round(raw_alloc, 4),
            "consecutive_failures": cons_failures,
            "live_dd": live_m.get("max_drawdown_pct", 0) if live_m else 0,
            "reduced": final_mult < 1.0,
        })

    # Normalize allocations to sum to 1.0
    total_raw = sum(a["raw_allocation"] for a in adjustments)
    if total_raw > 0:
        for a in adjustments:
            a["allocation"] = round(a["raw_allocation"] / total_raw, 4)
    else:
        for a in adjustments:
            a["allocation"] = round(1.0 / n, 4)

    # Compare with equal allocation
    equal_alloc = round(1.0 / n, 4)
    for a in adjustments:
        diff = a["allocation"] - equal_alloc
        a["change_from_equal"] = round(diff, 4)
        if diff > 0.01:
            a["direction"] = "INCREASED"
        elif diff < -0.01:
            a["direction"] = "DECREASED"
        else:
            a["direction"] = "UNCHANGED"

    # Run portfolio analysis with dynamic allocations
    alloc_list = [a["allocation"] for a in adjustments]
    portfolio = analyze_portfolio(strategies, alloc_list)

    # Also run with equal allocation for comparison
    equal_portfolio = analyze_portfolio(strategies, [equal_alloc] * n)

    # Summary
    reduced_count = sum(1 for a in adjustments if a["reduced"])
    zero_count = sum(1 for a in adjustments if a["allocation"] < 0.001)

    return {
        "num_strategies": n,
        "adjustments": adjustments,
        "alloc_rules": rules,
        "dynamic_portfolio": portfolio,
        "equal_portfolio": {
            "total_profit": equal_portfolio.get("combined_metrics", {}).get("total_profit", 0),
            "total_return_pct": equal_portfolio.get("combined_metrics", {}).get("total_return_pct", 0),
            "max_drawdown_pct": equal_portfolio.get("combined_metrics", {}).get("max_drawdown_pct", 0),
            "risk_score": equal_portfolio.get("portfolio_risk_score", 0),
        },
        "summary": {
            "reduced_count": reduced_count,
            "zero_allocation_count": zero_count,
            "active_strategies": n - zero_count,
            "total_allocated": round(sum(a["allocation"] for a in adjustments if a["allocation"] > 0.001), 4),
        },
    }


# ═════════════════════════════════════════════════════════════════════
# Phase 7 — Library-sourced Portfolio Builder
# ═════════════════════════════════════════════════════════════════════

import hashlib
import random as _rand
from datetime import datetime, timezone


def _synth_equity_curve(s: dict, points: int = 60) -> list:
    """
    Synthesize a proxy equity curve from a library strategy's flat metrics.
    Library rows don't carry `equity_curve`/`trades`, so we generate a
    deterministic random-walk whose:
      • drift comes from `total_return_pct`
      • volatility is scaled by `max_drawdown_pct`
      • seed is derived from strategy fingerprint → same strategy always
        produces the same curve (correlation checks are repeatable).

    Used ONLY as input to the correlation matrix — it is NOT stored as
    real trades and is never returned in the public API.
    """
    fp = s.get("fingerprint") or f"{s.get('pair')}:{s.get('timeframe')}:{s.get('style')}:{s.get('strategy_text', '')}"
    seed = int(hashlib.sha1(fp.encode()).hexdigest()[:8], 16)
    rng = _rand.Random(seed)

    total_ret = float(s.get("total_return_pct") or 0.0) / 100.0
    dd = float(s.get("max_drawdown_pct") or 5.0)
    vol = max(0.003, dd / 100.0 / 2.5)
    drift_per_step = total_ret / max(1, points - 1)

    start = 10000.0
    eq = [start]
    for _ in range(points - 1):
        step = drift_per_step + rng.gauss(0.0, vol)
        eq.append(round(eq[-1] * (1.0 + step), 2))
    return eq


def _library_to_engine_shape(doc: dict) -> dict:
    """Adapt a strategy_library row into the shape `auto_build_portfolio`
    expects (backtest_results + identity fields). Additive — never mutates
    the original document."""
    bt = {
        "net_profit": (float(doc.get("total_return_pct") or 0.0) / 100.0) * 10000.0,
        "total_return_pct": doc.get("total_return_pct") or 0.0,
        "max_drawdown_pct": doc.get("max_drawdown_pct") or 0.0,
        "profit_factor": doc.get("profit_factor") or 0.0,
        "win_rate": doc.get("win_rate") or 0.0,
        "total_trades": doc.get("total_trades") or 0,
        "initial_balance": 10000.0,
        "equity_curve": _synth_equity_curve(doc),
        "trades": [],
    }
    safety_proxy = max(0.0, 100.0 - float(doc.get("max_drawdown_pct") or 0.0) * 4.0)
    return {
        "id": str(doc.get("_id") or doc.get("strategy_id") or doc.get("fingerprint") or ""),
        "pair": doc.get("pair"),
        "timeframe": doc.get("timeframe"),
        "style": doc.get("style"),
        "strategy_type": doc.get("style"),
        "strategy_text": doc.get("strategy_text"),
        "score": doc.get("score") or 0.0,
        "safety": {"safety_score": safety_proxy},
        "pass_probability": doc.get("pass_probability"),
        "stability_score": doc.get("stability_score"),
        "verdict": doc.get("verdict"),
        "backtest_results": bt,
        # Keep originals for the output contract:
        "_library_doc": doc,
    }


def _diversity_index(selected: list) -> float:
    """0–100 score. 100 = fully diverse across pair+style+timeframe."""
    if len(selected) <= 1:
        return 100.0
    pairs = len({s.get("pair") for s in selected})
    styles = len({s.get("style") for s in selected})
    tfs = len({s.get("timeframe") for s in selected})
    n = len(selected)
    # Each dimension contributes up to 1.0 when every strategy is unique on it.
    return round(100.0 * ((pairs + styles + tfs) / (3.0 * n)), 1)


def _compute_risk_allocation(selected_clean: list, portfolio: dict) -> list:
    """
    Derive the Phase-7 allocation contract. Combines two principles:
      • capital_pct    — inverse-drawdown weighting (already emitted by
        analyze_portfolio as `suggested_allocations`). Fallback = equal.
      • risk_per_trade — bounded by strategy DD: risk = clip(0.25%..2%,
        1% × (5 / max_dd)). Safer strategies get a bigger per-trade
        budget up to 2%; riskier ones are capped.

    Returns a list aligned to `selected_clean`; each element carries the
    strategy identity + both allocation dimensions + the rationale.
    """
    suggested = portfolio.get("suggested_allocations") or []
    equal = 1.0 / max(1, len(selected_clean))
    rows = []
    for i, s in enumerate(selected_clean):
        bt = s.get("backtest_results", {}) or {}
        dd = max(0.5, float(bt.get("max_drawdown_pct") or 5.0))
        capital_pct = float(suggested[i]) if i < len(suggested) else equal
        risk_per_trade = max(0.25, min(2.0, 1.0 * (5.0 / dd)))
        rows.append({
            "strategy_id": s.get("id"),
            "pair": s.get("pair"),
            "timeframe": s.get("timeframe"),
            "style": s.get("style"),
            "capital_pct": round(capital_pct, 4),
            "risk_per_trade_pct": round(risk_per_trade, 2),
            "rationale": f"inverse-DD capital (dd={dd:.1f}%), risk bounded 0.25%..2%",
        })
    return rows


def _portfolio_score(
    selected: list, combined_metrics: dict, avg_corr: float, diversity: float,
) -> float:
    """
    Aggregate 0-100 portfolio score. Combines:
      • avg pass_probability       × 0.30
      • avg stability_score        × 0.20
      • combined DD penalty         (100 - dd*2, floor 0)  × 0.20
      • diversity_index            × 0.15
      • correlation bonus          ((1 - avg_corr) * 100)  × 0.15
    Each component is clipped to [0,100] before weighting.
    """
    def _clip(v): return max(0.0, min(100.0, float(v or 0.0)))

    n = max(1, len(selected))
    pp = sum(float(s.get("pass_probability") or 0.0) for s in selected) / n
    stab = sum(float(s.get("stability_score") or 0.0) for s in selected) / n
    dd = float(combined_metrics.get("max_drawdown_pct") or 0.0)
    dd_pts = max(0.0, 100.0 - dd * 2.0)
    corr_pts = max(0.0, (1.0 - abs(avg_corr)) * 100.0)

    score = (
        _clip(pp) * 0.30
        + _clip(stab) * 0.20
        + _clip(dd_pts) * 0.20
        + _clip(diversity) * 0.15
        + _clip(corr_pts) * 0.15
    )
    return round(max(0.0, min(100.0, score)), 1)


async def build_portfolio_from_library(
    *,
    top_n_pool: int = 25,
    target_size: int = 4,
    max_pair_corr: float = 0.6,
    max_same_pair: int = 2,
    max_same_style: int = 2,
    min_score: float = 0.0,
    source_filter: str | None = None,
) -> dict:
    """
    Phase 7 — Build a diversified multi-strategy portfolio from
    `strategy_library`. Reuses `auto_build_portfolio` under the hood
    (correlation control, greedy selection), then applies Phase-7-specific
    diversity caps + emits the contract:

        { portfolio_score, strategies, allocation, combined_metrics,
          diversification_grade, correlation_matrix, warnings,
          selection_log, run_id, created_at }

    Args:
        top_n_pool       : candidates pulled from the library, ordered by score.
        target_size      : desired portfolio size (2..7).
        max_pair_corr    : correlation cap passed through to the selector.
        max_same_pair    : hard cap on strategies sharing a pair.
        max_same_style   : hard cap on strategies sharing a style.
        min_score        : library filter.
        source_filter    : if set, only rows with `source == source_filter`
                           (e.g. "auto_factory" to build from Phase-5 outputs).
    """
    from engines.db import get_db

    db = get_db()
    query: dict = {}
    if source_filter:
        query["source"] = source_filter
    if min_score:
        query["score"] = {"$gte": min_score}

    cursor = db["strategy_library"].find(query).sort("score", -1).limit(
        max(2, min(int(top_n_pool), 200))
    )
    raw = []
    async for doc in cursor:
        raw.append(doc)

    if len(raw) < 2:
        return {
            "success": False,
            "error": f"Library has {len(raw)} viable strategy(ies). Need ≥ 2.",
            "pool_size": len(raw),
        }

    candidates = [_library_to_engine_shape(d) for d in raw]

    # Pre-apply hard caps on pair/style BEFORE the greedy selector runs so
    # the correlation-based picker can't exhaust the per-bucket budget.
    capped: list = []
    pair_count: dict = {}
    style_count: dict = {}
    rejected_by_cap: list = []
    for c in candidates:
        p, st = c.get("pair"), c.get("style")
        if pair_count.get(p, 0) >= max_same_pair:
            rejected_by_cap.append(f"{c['id']}:pair_cap({p})")
            continue
        if style_count.get(st, 0) >= max_same_style:
            rejected_by_cap.append(f"{c['id']}:style_cap({st})")
            continue
        capped.append(c)
        pair_count[p] = pair_count.get(p, 0) + 1
        style_count[st] = style_count.get(st, 0) + 1

    if len(capped) < 2:
        return {
            "success": False,
            "error": "Diversity caps removed too many candidates.",
            "pool_size": len(candidates),
            "after_caps": len(capped),
            "rejected_by_cap": rejected_by_cap,
        }

    target_size = max(2, min(int(target_size), 7, len(capped)))
    built = auto_build_portfolio(
        capped,
        target_size=target_size,
        max_pair_corr=max_pair_corr,
        min_score=min_score,
    )
    if not built.get("success"):
        return {"success": False, **built}

    selection_log = built.get("selection_log", [])
    if rejected_by_cap:
        selection_log = [f"Pre-cap filter dropped {len(rejected_by_cap)} candidates"] + selection_log

    portfolio = built.get("portfolio", {}) or {}
    selected_ids = set(built.get("selected_ids", []))
    selected_clean = [c for c in capped if c["id"] in selected_ids]

    diversity = _diversity_index(selected_clean)
    avg_corr = float(portfolio.get("avg_correlation") or 0.0)
    combined_metrics = portfolio.get("combined_metrics", {}) or {}

    # Augment combined_metrics with portfolio-level pass_probability +
    # stability (weighted by capital allocation).
    allocations = portfolio.get("suggested_allocations") or portfolio.get("allocations") or []
    if allocations and len(allocations) == len(selected_clean):
        weights = allocations
    else:
        weights = [1.0 / len(selected_clean)] * len(selected_clean)

    weighted_pp = round(sum(
        w * float(s.get("pass_probability") or 0.0)
        for w, s in zip(weights, selected_clean)
    ), 1)
    weighted_stab = round(sum(
        w * float(s.get("stability_score") or 0.0)
        for w, s in zip(weights, selected_clean)
    ), 1)
    combined_metrics = {
        **combined_metrics,
        "combined_pass_probability": weighted_pp,
        "portfolio_stability_score": weighted_stab,
        "avg_correlation": avg_corr,
        "diversity_index": diversity,
    }

    score = _portfolio_score(selected_clean, combined_metrics, avg_corr, diversity)

    # Output-contract strategies (flatten to library fields the caller cares about).
    strategies_out = []
    for s in selected_clean:
        lib = s.get("_library_doc", {}) or {}
        strategies_out.append({
            "strategy_id": s.get("id"),
            "pair": s.get("pair"),
            "timeframe": s.get("timeframe"),
            "style": s.get("style"),
            "verdict": s.get("verdict"),
            "score": s.get("score"),
            "pass_probability": s.get("pass_probability"),
            "stability_score": s.get("stability_score"),
            "max_drawdown_pct": lib.get("max_drawdown_pct"),
            "profit_factor": lib.get("profit_factor"),
            "total_return_pct": lib.get("total_return_pct"),
            "win_rate": lib.get("win_rate"),
            "total_trades": lib.get("total_trades"),
            "fingerprint": lib.get("fingerprint"),
            "source": lib.get("source"),
        })

    allocation_rows = _compute_risk_allocation(selected_clean, portfolio)

    run_id = hashlib.sha1(
        f"{datetime.now(timezone.utc).isoformat()}:{','.join(sorted(selected_ids))}".encode()
    ).hexdigest()[:12]

    result = {
        "success": True,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_score": score,
        "strategies": strategies_out,
        "allocation": allocation_rows,
        "combined_metrics": combined_metrics,
        "correlation_matrix": portfolio.get("correlation_matrix"),
        "diversification_grade": portfolio.get("diversification_grade"),
        "warnings": portfolio.get("warnings", []),
        "selection_log": selection_log,
        "pool_size": len(raw),
        "after_caps": len(capped),
        "config": {
            "top_n_pool": top_n_pool, "target_size": target_size,
            "max_pair_corr": max_pair_corr, "max_same_pair": max_same_pair,
            "max_same_style": max_same_style, "min_score": min_score,
            "source_filter": source_filter,
        },
    }

    # Persist a snapshot (additive collection; `/api/portfolio/status` reads it).
    try:
        await db["portfolios"].insert_one({**result})
    except Exception as e:
        logger.warning("Failed to persist portfolio snapshot: %s", e)

    return result
