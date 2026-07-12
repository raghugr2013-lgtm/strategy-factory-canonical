"""
Auto Factory Engine — Continuous Strategy Generation System (Phase 5.5).

Orchestration layer that automatically generates, evaluates, and stores
the best strategies. Uses existing engines without modifying them:
  - strategy_engine (generation)
  - backtest_engine (backtesting)
  - safety_engine (safety analysis)
  - ranking_engine (scoring)
  - strategy_profiler (DNA profiling, Phase 3)
  - matching_engine (firm matching, Phase 4)
  - pass_probability (Monte Carlo, Phase 5)

Universe: 5 pairs × 4 styles with timeframe mappings.
Rotation: each cycle picks a subset of combinations to avoid brute-forcing.
Multi-level filtering: quick → profile → match+probability.
Stores top 5 per pair/timeframe/style in auto_factory_strategies collection.
"""

import logging
import random
from datetime import datetime, timezone
from engines.db import get_db
from engines.strategy_engine import generate_strategy_text
from engines.backtest_engine import run_backtest_logic
from engines.safety_engine import run_safety_analysis
from engines.ranking_engine import rank_strategies
from engines.strategy_profiler import profile_strategy
from engines.pass_probability import estimate_pass_probability
from engines.strategy_ranking_engine import rank_strategies as rank_strategies_v2

logger = logging.getLogger(__name__)

COLLECTION = "auto_factory_strategies"


def _rank_cycle_output(stored: list, top_n: int = 5) -> list:
    """
    Phase 8.6 adapter: map auto-factory's stored_strategies format to the
    ranking engine input shape and return the top-N ranked list.
    Additive — pure function, no side-effects.
    """
    if not stored:
        return []
    adapted = []
    for s in stored:
        dd = s.get("max_drawdown_pct", 0) or 0
        # Heuristic overfit proxy when explicit validation_report absent:
        # high drawdown on backtest + no OOS proof → mildly penalise.
        overfit_proxy = min(100.0, max(0.0, dd * 2.0))
        adapted.append({
            "strategy_id": s.get("combo_key", "unknown"),
            "pass_probability": s.get("pass_probability"),
            "stability_score": s.get("composite_score"),
            "overfit_score": overfit_proxy,
            # No decision/EV at the factory layer; ranking engine defaults
            # verdict to RISKY, which is the conservative pre-validation choice.
        })
    return rank_strategies_v2(adapted, top_n=top_n)

# ═══════════════════════════════════════════════════════
# Universe Definition
# ═══════════════════════════════════════════════════════

UNIVERSE_PAIRS = ["BTCUSD", "ETHUSD", "EURUSD", "XAUUSD", "NAS100"]

STYLE_TIMEFRAME_MAP = {
    "scalping":       ["M1", "M5"],
    "trend-following": ["M15", "H1", "H4", "D1"],
    "mean-reversion": ["M5", "M15"],
    "breakout":       ["M15", "H1"],
}

STYLES = list(STYLE_TIMEFRAME_MAP.keys())


def _build_universe() -> list:
    """Build all valid (pair, style, timeframe) combinations."""
    combos = []
    for pair in UNIVERSE_PAIRS:
        for style, tfs in STYLE_TIMEFRAME_MAP.items():
            for tf in tfs:
                combos.append({"pair": pair, "style": style, "timeframe": tf})
    return combos


# ═══════════════════════════════════════════════════════
# Data loader
# ═══════════════════════════════════════════════════════

async def _load_data(pair: str, timeframe: str) -> tuple:
    """Load real market data with auto-recovery.

    Returns `(prices, data_source, data_points)`. When data is below
    the per-TF threshold, attempts an inline Dukascopy download + re-read
    (single retry). If recovery still fails, returns `(None, "none", 0)`
    so the caller can skip that (pair, tf) combo and continue the loop —
    auto systems must never break due to data.
    """
    from engines.data_access import load_with_recovery
    result = await load_with_recovery(
        pair, timeframe, auto_recover=True,
    )
    bars = result["bars"]
    if result["status"] in ("ok", "recovered") and bars:
        prices = [b["close"] for b in bars]
        return prices, "real", len(prices)
    # Recovery failed OR data truly unavailable — caller skips this combo.
    logger.warning(
        "[auto_factory] skipping %s/%s — %s",
        pair, timeframe, result.get("message", "no data"),
    )
    return None, "none", 0


# ═══════════════════════════════════════════════════════
# Multi-level filtering
# ═══════════════════════════════════════════════════════

def _quick_filter(bt: dict) -> tuple:
    """
    Level 1: Quick reject — only remove clearly broken strategies.
    Pass marginal ones through; ranking + matching handle quality.
    Returns (passed: bool, reason: str).
    """
    if not bt:
        return False, "no_backtest"
    if bt.get("total_trades", 0) < 3:
        return False, "too_few_trades"
    if bt.get("max_drawdown_pct", 0) > 40:
        return False, "extreme_drawdown"
    if bt.get("win_rate", 0) < 10:
        return False, "negligible_win_rate"
    return True, ""


# ═══════════════════════════════════════════════════════
# Storage
# ═══════════════════════════════════════════════════════

async def _store_top_strategies(combo_key: str, candidates: list, keep_n: int = 5):
    """
    Store top N strategies for a combo, replacing old ones.
    combo_key: "pair:timeframe:style"
    """
    db = get_db()
    candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    top = candidates[:keep_n]

    # Remove old entries for this combo
    await db[COLLECTION].delete_many({"combo_key": combo_key})

    if not top:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for rank, s in enumerate(top, 1):
        docs.append({
            "combo_key": combo_key,
            "pair": s["pair"],
            "timeframe": s["timeframe"],
            "style": s["style"],
            "rank": rank,
            "strategy_text": s.get("strategy_text", ""),
            "score": s.get("ranking_score", 0),
            "composite_score": s.get("composite_score", 0),
            "pass_probability": s.get("pass_probability", 0),
            "best_firm_fit": s.get("best_firm_fit", ""),
            "best_firm_score": s.get("best_firm_score", 0),
            "metrics": {
                "net_profit": s.get("net_profit", 0),
                "total_return_pct": s.get("total_return_pct", 0),
                "win_rate": s.get("win_rate", 0),
                "profit_factor": s.get("profit_factor", 0),
                "max_drawdown_pct": s.get("max_drawdown_pct", 0),
                "total_trades": s.get("total_trades", 0),
                "sharpe_ratio": s.get("sharpe_ratio", 0),
            },
            "classification": s.get("classification", {}),
            "safety": {
                "score": s.get("safety_score", 0),
                "grade": s.get("safety_grade", ""),
            },
            "last_updated": now,
        })

    await db[COLLECTION].insert_many(docs)
    return len(docs)


# ═══════════════════════════════════════════════════════
# Main cycle
# ═══════════════════════════════════════════════════════

async def run_auto_factory_cycle(
    max_combos: int = 5,
    strategies_per_combo: int = 5,
    keep_top_n: int = 5,
    seed: int = None,
    mc_simulations: int = 20,
) -> dict:
    """
    Run one auto factory cycle.

    1. Build universe, select subset (rotation)
    2. For each combo with available data:
       a. Generate strategies via LLM
       b. Backtest each
       c. Level 1: Quick filter (profit, DD)
       d. Safety + ranking
       e. Level 2: Profile (DNA, Phase 3)
       f. Level 3: Match + probability (Phase 4+5)
    3. Store top 5 per combo
    4. Return results

    Args:
        max_combos: how many combinations to process this cycle (rotation)
        strategies_per_combo: how many strategies to generate per combo
        keep_top_n: how many to store per combo
        seed: random seed for combo selection (None = random)
        mc_simulations: Monte Carlo runs per matching

    VPS Scaling P1.D — wrapped in `admission_gate(FACTORY_CYCLE)`. With
    `ENABLE_ADMISSION_CONTROL=false` (default) the gate is a no-op and
    behaviour is byte-identical to pre-P1.D. With the flag ON, the gate
    refuses to start a new cycle when the host is `warn`/`critical` or
    pressure is critical.
    """
    from engines.workload_classes import WorkloadClass
    from engines.admission_wrapper import admission_gate

    async with admission_gate(
        WorkloadClass.FACTORY_CYCLE,
        metadata={"site": "auto_factory.run_auto_factory_cycle",
                  "max_combos": max_combos,
                  "strategies_per_combo": strategies_per_combo},
    ):
        return await _run_auto_factory_cycle_inner(
            max_combos=max_combos,
            strategies_per_combo=strategies_per_combo,
            keep_top_n=keep_top_n,
            seed=seed,
            mc_simulations=mc_simulations,
        )


async def _run_auto_factory_cycle_inner(
    max_combos: int = 5,
    strategies_per_combo: int = 5,
    keep_top_n: int = 5,
    seed: int = None,
    mc_simulations: int = 20,
) -> dict:
    """Inner body of `run_auto_factory_cycle` — pre-P1.D verbatim."""
    from engines.rule_engine import get_all_rules, rules_to_sim_config

    universe = _build_universe()
    rng = random.Random(seed)
    rng.shuffle(universe)
    selected = universe[:max_combos]

    cycle_log = []
    cycle_stats = {
        "combos_selected": len(selected),
        "combos_with_data": 0,
        "combos_skipped_no_data": 0,
        "total_generated": 0,
        "total_backtested": 0,
        "level1_passed": 0,
        "level1_rejected": 0,
        "level2_profiled": 0,
        "level3_matched": 0,
        "total_stored": 0,
    }
    stored_strategies = []
    combo_results = []

    # Pre-load firm rules for matching
    all_firms = await get_all_rules()
    firm_configs = []
    for firm_doc in all_firms:
        sim_cfg = await rules_to_sim_config(firm_doc)
        firm_configs.append({
            "slug": firm_doc.get("firm_slug", ""),
            "name": firm_doc.get("firm_name", ""),
            "config": sim_cfg,
        })

    for combo in selected:
        pair = combo["pair"]
        style = combo["style"]
        tf = combo["timeframe"]
        combo_key = f"{pair}:{tf}:{style}"

        cycle_log.append(f"--- {combo_key} ---")

        # Load data
        prices, data_source, data_points = await _load_data(pair, tf)
        if data_source == "none":
            cycle_stats["combos_skipped_no_data"] += 1
            cycle_log.append(f"  SKIP: No data for {pair}/{tf}")
            combo_results.append({
                "combo_key": combo_key, "pair": pair, "timeframe": tf, "style": style,
                "status": "skipped_no_data", "generated": 0, "stored": 0,
            })
            continue

        cycle_stats["combos_with_data"] += 1
        cycle_log.append(f"  Data: {data_points} candles ({data_source})")

        # ── Generate strategies ──
        raw_strategies = []
        # Phase-1 UI: raise per-combo cap so the numeric 1..50 input is honoured.
        gen_count = max(1, min(strategies_per_combo, 50))
        for i in range(gen_count):
            try:
                text = await generate_strategy_text(pair, tf, style)
                raw_strategies.append({
                    "strategy_text": text, "pair": pair,
                    "timeframe": tf, "style": style,
                })
                cycle_stats["total_generated"] += 1
            except Exception as e:
                cycle_log.append(f"  Gen failed #{i+1}: {str(e)[:60]}")

        if not raw_strategies:
            cycle_log.append(f"  All generation failed for {combo_key}")
            combo_results.append({
                "combo_key": combo_key, "pair": pair, "timeframe": tf, "style": style,
                "status": "generation_failed", "generated": 0, "stored": 0,
            })
            continue

        # ── Backtest each ──
        for s in raw_strategies:
            try:
                bt = run_backtest_logic(
                    s["strategy_text"], s["pair"], s["timeframe"],
                    external_prices=prices, data_source=data_source,
                    data_points=data_points,
                )
                s["backtest"] = bt
                cycle_stats["total_backtested"] += 1
            except Exception:
                s["backtest"] = None

        backtested = [s for s in raw_strategies if s.get("backtest")]
        if not backtested:
            cycle_log.append(f"  All backtests failed for {combo_key}")
            combo_results.append({
                "combo_key": combo_key, "pair": pair, "timeframe": tf, "style": style,
                "status": "backtest_failed", "generated": len(raw_strategies), "stored": 0,
            })
            continue

        # ── Level 1: Quick filter ──
        level1 = []
        for s in backtested:
            passed, reason = _quick_filter(s["backtest"])
            if passed:
                level1.append(s)
                cycle_stats["level1_passed"] += 1
            else:
                cycle_stats["level1_rejected"] += 1

        cycle_log.append(f"  L1 filter: {len(level1)}/{len(backtested)} passed")

        if not level1:
            combo_results.append({
                "combo_key": combo_key, "pair": pair, "timeframe": tf, "style": style,
                "status": "all_filtered", "generated": len(raw_strategies),
                "backtested": len(backtested), "stored": 0,
            })
            continue

        # ── Safety + Ranking ──
        for s in level1:
            s["safety"] = run_safety_analysis(s["backtest"], timeframe=tf)

        ranked = rank_strategies(level1)

        # ── Level 2: Profile (DNA) ──
        for s in ranked:
            bt = s.get("backtest", s.get("backtest_results", {}))
            trades = bt.get("trades", [])
            dna = profile_strategy(trades)
            s["profile"] = dna
            cycle_stats["level2_profiled"] += 1

        cycle_log.append(f"  L2 profiled: {len(ranked)} strategies")

        # ── Level 3: Match + Probability ──
        enriched = []
        for s in ranked:
            bt = s.get("backtest", s.get("backtest_results", {}))
            trades = bt.get("trades", [])
            ranking = s.get("ranking", {})
            safety = s.get("safety", {})
            dna = s.get("profile", {})

            # Run matching (lightweight, without MC here — MC per firm below)
            best_firm = ""
            best_firm_score = 0
            best_prob = 0
            best_robustness = None

            for fc in firm_configs:
                prob_result = estimate_pass_probability(
                    trades, fc["config"], n_simulations=mc_simulations
                )
                prob = prob_result.get("pass_probability", 0)
                if prob > best_prob:
                    best_prob = prob
                    best_firm = fc["name"]
                    best_firm_score = prob
                    best_robustness = prob_result.get("structural_robustness")

            cycle_stats["level3_matched"] += 1

            # Composite score: 40% ranking + 30% safety + 30% pass probability
            rank_score = ranking.get("score", 0)
            safety_score_val = safety.get("safety_score", 0)
            composite = round(
                rank_score * 0.40 +
                safety_score_val * 0.30 +
                best_prob * 0.30,
                2,
            )

            enriched.append({
                "pair": pair,
                "timeframe": tf,
                "style": style,
                "strategy_text": s.get("strategy_text", ""),
                "ranking_score": rank_score,
                "safety_score": safety_score_val,
                "safety_grade": safety.get("grade", ""),
                "pass_probability": best_prob,
                "best_firm_fit": best_firm,
                "best_firm_score": best_firm_score,
                "structural_robustness": best_robustness,
                "composite_score": composite,
                "classification": dna.get("classification", {}),
                "net_profit": bt.get("net_profit", 0),
                "total_return_pct": bt.get("total_return_pct", 0),
                "win_rate": bt.get("win_rate", 0),
                "profit_factor": bt.get("profit_factor", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "total_trades": bt.get("total_trades", 0),
                "sharpe_ratio": dna.get("stability", {}).get("sharpe_ratio", 0),
            })

        cycle_log.append(f"  L3 matched: {len(enriched)} strategies")

        # ── Store top N ──
        stored_count = await _store_top_strategies(combo_key, enriched, keep_top_n)
        cycle_stats["total_stored"] += stored_count

        stored_strategies.extend([
            {
                "combo_key": combo_key,
                "pair": s["pair"],
                "timeframe": s["timeframe"],
                "style": s["style"],
                "composite_score": s["composite_score"],
                "ranking_score": s["ranking_score"],
                "pass_probability": s["pass_probability"],
                "best_firm_fit": s["best_firm_fit"],
                "win_rate": s["win_rate"],
                "profit_factor": s["profit_factor"],
                "max_drawdown_pct": s["max_drawdown_pct"],
            }
            for s in sorted(enriched, key=lambda x: x["composite_score"], reverse=True)[:keep_top_n]
        ])

        combo_results.append({
            "combo_key": combo_key,
            "pair": pair,
            "timeframe": tf,
            "style": style,
            "status": "complete",
            "generated": len(raw_strategies),
            "backtested": len(backtested),
            "level1_passed": len(level1),
            "profiled": len(ranked),
            "matched": len(enriched),
            "stored": stored_count,
        })

        cycle_log.append(
            f"  STORED {stored_count}/{len(enriched)} for {combo_key}"
        )

    return {
        "success": True,
        "stats": cycle_stats,
        "stored_strategies": stored_strategies,
        "combo_results": combo_results,
        "cycle_log": cycle_log,
        # Phase 8.6 — unified ranking over the full cycle's stored strategies.
        # Additive: leaves composite_score / ranking_score intact.
        "ranked_strategies": _rank_cycle_output(stored_strategies, top_n=5),
    }
