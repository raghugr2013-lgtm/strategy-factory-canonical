"""
Phase 4 P4.14 latent-capability — Risk-of-Ruin engine.

Purpose
-------
Compute risk-of-ruin estimates per strategy and PERSIST them for
diagnostic / future-governance use. DIAGNOSTIC-ONLY initially:

  * `RISK_OF_RUIN_WEIGHT == 0.0` — RoR does NOT influence deploy_score.
  * No auto-deployment-block based on RoR.
  * No orchestration authority.

The engine is mathematically independent of every other latent
subsystem. It can be exercised from API (POST /api/latent/risk_of_ruin/
evaluate) or from internal callers (future challenge_simulator,
deployment_throttle).

Two estimators
--------------
1. Closed-form (gambler's-ruin formula) — fast, requires only
   win_rate, payoff_ratio, risk_per_trade. Returns scalar in [0, 1].
2. Monte-Carlo — samples from an empirical trade distribution and
   counts ruin events under a drawdown threshold. Returns a richer
   payload (mean RoR, time-to-target, capital paths summary).
"""
from __future__ import annotations

import logging
import math
import random
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from engines.db import get_db
from engines.feature_flags import flag

logger = logging.getLogger(__name__)

ROR_COLL = "risk_of_ruin_evaluations"


# ─────────────────────────────────────────────────────────────────────
# 1. Closed-form gambler's ruin.
# ─────────────────────────────────────────────────────────────────────

def closed_form_ror(
    win_rate: float,
    payoff_ratio: float,
    risk_per_trade: float = 0.01,
    capital_units: int = 100,
) -> float:
    """Classical gambler's-ruin probability.

    Args
    ----
    win_rate       : P(win) in [0,1]
    payoff_ratio   : avg_win / avg_loss (>0, typically 1-3)
    risk_per_trade : fraction of capital risked per trade (e.g. 0.01)
    capital_units  : capital expressed in risk-units (1/risk_per_trade)
                     If you risk 1% per trade, 100 units = 100% capital.

    Returns
    -------
    RoR ∈ [0, 1]. 0 means mathematically cannot ruin; 1 means certain
    ruin (which happens when expected value is non-positive).
    """
    # Defensive parameter clamping — never raise, this is diagnostic.
    p = max(0.0, min(1.0, float(win_rate)))
    b = max(1e-9, float(payoff_ratio))
    n = max(1, int(capital_units))

    if p <= 0.0:
        return 1.0
    q = 1.0 - p
    if q <= 0.0:
        return 0.0

    # Expected value per trade in risk-units.
    ev = p * b - q
    if ev <= 0:
        # Negative or zero EV → ruin probability is 1 over infinite time.
        return 1.0

    # Standard formula for unequal-payoff random walk to ruin:
    #   RoR = ((q/p) / b) ** capital_units   (approximation)
    # Use a more accurate form when payoff != 1.
    # Following Vince's formula adapted to asymmetric payoff:
    ratio = (q / p) / b
    if ratio <= 0.0:
        return 0.0
    if ratio >= 1.0:
        return 1.0
    try:
        return float(ratio ** n)
    except OverflowError:                                # pragma: no cover
        return 0.0


# ─────────────────────────────────────────────────────────────────────
# 2. Monte-Carlo RoR from empirical trade returns.
# ─────────────────────────────────────────────────────────────────────

def _summarise_trades(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Pull pnl / risk_per_trade summaries from a trade list."""
    pnls: List[float] = []
    for t in trades:
        if not isinstance(t, dict):
            continue
        # tolerate multiple shapes
        for key in ("pnl_pct", "pnl", "return_pct", "return"):
            v = t.get(key)
            if isinstance(v, (int, float)) and math.isfinite(v):
                pnls.append(float(v))
                break
    if not pnls:
        return {"count": 0}
    return {
        "count":   len(pnls),
        "mean":    statistics.fmean(pnls),
        "stdev":   statistics.pstdev(pnls) if len(pnls) > 1 else 0.0,
        "min":     min(pnls),
        "max":     max(pnls),
        "samples": pnls,
    }


def monte_carlo_ror(
    trades: Sequence[Dict[str, Any]],
    *,
    capital_units: int = 100,
    dd_limit_pct: float = 30.0,
    n_simulations: Optional[int] = None,
    seed: int = 42,
) -> Dict[str, Any]:
    """Bootstrap-resample the empirical trade distribution to estimate
    ruin probability under a drawdown limit (institutional prop-firm
    constraint).

    `n_simulations` defaults to RISK_OF_RUIN_DEFAULT_SIMS (2000).

    Returns
    -------
    {
        "n_simulations":     int,
        "ror":               float ∈ [0,1],
        "median_dd_pct":     float,
        "p95_dd_pct":        float,
        "trades_per_path":   int,
        "trade_distribution": {...empirical summary...},
    }
    """
    sims = int(n_simulations or flag("RISK_OF_RUIN_DEFAULT_SIMS"))
    sims = max(100, min(sims, 20000))

    summary = _summarise_trades(trades)
    if summary["count"] < 5:
        return {
            "n_simulations":     sims,
            "ror":               None,
            "median_dd_pct":     None,
            "p95_dd_pct":        None,
            "trades_per_path":   summary["count"],
            "trade_distribution": summary,
            "error":             "insufficient_trades",
        }

    samples = summary["samples"]
    n_trades = max(60, summary["count"])  # path length ~= sample size

    rng = random.Random(seed)
    ruined = 0
    max_dds: List[float] = []

    for _ in range(sims):
        # capital tracked as percentage of initial; ruin if drops below
        # (100 - dd_limit_pct).
        equity = 100.0
        peak = 100.0
        max_dd = 0.0
        for _i in range(n_trades):
            equity += rng.choice(samples)
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
            if dd >= dd_limit_pct:
                ruined += 1
                break
        max_dds.append(max_dd)

    ror = ruined / sims
    max_dds_sorted = sorted(max_dds)
    median_dd = max_dds_sorted[len(max_dds_sorted) // 2]
    p95_dd = max_dds_sorted[min(len(max_dds_sorted) - 1, int(0.95 * len(max_dds_sorted)))]

    return {
        "n_simulations":     sims,
        "ror":               round(float(ror), 4),
        "median_dd_pct":     round(float(median_dd), 3),
        "p95_dd_pct":        round(float(p95_dd), 3),
        "trades_per_path":   n_trades,
        "trade_distribution": {
            k: v for k, v in summary.items() if k != "samples"
        },
    }


# ─────────────────────────────────────────────────────────────────────
# 3. Persistence — diagnostic-only.
# ─────────────────────────────────────────────────────────────────────

async def persist_evaluation(
    *,
    strategy_hash: str,
    closed_form: Optional[float],
    monte_carlo: Optional[Dict[str, Any]],
    inputs: Dict[str, Any],
    source: str = "manual",
) -> Dict[str, Any]:
    """Write one RoR row. Best-effort — never raises."""
    now = datetime.now(timezone.utc)
    doc = {
        "strategy_hash":    strategy_hash,
        "ts":               now.isoformat(),
        "ts_dt":            now,
        "closed_form_ror":  closed_form,
        "monte_carlo":      monte_carlo,
        "inputs":           inputs,
        "source":           source,
        # Stamped here so future readers know which weight regime
        # produced this row.
        "weight_in_deploy_score": float(flag("RISK_OF_RUIN_WEIGHT")),
    }
    try:
        await get_db()[ROR_COLL].insert_one({**doc})
        # Strip _id (mutated by insert) before returning.
        doc.pop("_id", None)
    except Exception as e:                                  # pragma: no cover
        logger.warning("[risk_of_ruin] persist failed: %s", e)
        doc["_persist_error"] = str(e)[:200]
    return doc


async def evaluate(
    *,
    strategy_hash: str,
    win_rate: Optional[float] = None,
    payoff_ratio: Optional[float] = None,
    risk_per_trade: float = 0.01,
    capital_units: int = 100,
    trades: Optional[Sequence[Dict[str, Any]]] = None,
    dd_limit_pct: float = 30.0,
    n_simulations: Optional[int] = None,
    source: str = "manual",
) -> Dict[str, Any]:
    """Convenience wrapper — runs whichever estimators have inputs and
    persists the result. Always returns a payload (no exceptions)."""
    cf: Optional[float] = None
    if win_rate is not None and payoff_ratio is not None:
        cf = closed_form_ror(
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
            risk_per_trade=risk_per_trade,
            capital_units=capital_units,
        )

    mc: Optional[Dict[str, Any]] = None
    if trades:
        mc = monte_carlo_ror(
            trades,
            capital_units=capital_units,
            dd_limit_pct=dd_limit_pct,
            n_simulations=n_simulations,
        )

    inputs = {
        "win_rate":       win_rate,
        "payoff_ratio":   payoff_ratio,
        "risk_per_trade": risk_per_trade,
        "capital_units":  capital_units,
        "dd_limit_pct":   dd_limit_pct,
        "n_simulations":  n_simulations,
        "trade_count":    len(trades) if trades else 0,
    }
    return await persist_evaluation(
        strategy_hash=strategy_hash,
        closed_form=cf,
        monte_carlo=mc,
        inputs=inputs,
        source=source,
    )


async def list_evaluations(
    strategy_hash: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 500))
    q: Dict[str, Any] = {}
    if strategy_hash:
        q["strategy_hash"] = strategy_hash
    # Project _id away to keep responses JSON-clean.
    cur = db[ROR_COLL].find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    return [d async for d in cur]


def deploy_score_weight() -> float:
    """Live read of the dormant weight. Always 0.0 until operator
    explicitly raises it via env. Callers SHOULD use this rather than
    reading the flag directly so a future audit trace is reproducible.
    """
    return float(flag("RISK_OF_RUIN_WEIGHT"))
