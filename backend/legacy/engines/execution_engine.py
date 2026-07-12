"""
Execution Realism Engine — models real-world trade execution costs.

Operates on pre-computed trade dicts consumed by `challenge_simulator.simulate_challenge`.
When `execution.enabled == False` (default) → pure pass-through. When enabled:

  1. Intrabar worst-case (CRITICAL):
     If a winning (TP-hit) trade's associated candle also contains the SL price,
     assume SL hit first. The trade flips to a realized loss AND its
     `floating_min_pnl` is deepened so the simulator's intraday DD check sees
     the worst-case excursion.

  2. Spread:
     Flat USD cost per trade (BUY executes at ASK, SELL at BID → adverse entry
     for both sides → symmetrical cost on `net_pnl`).

  3. Slippage:
     Random adverse slippage in [0, max_slippage] USD per trade, subtracted
     from `net_pnl` and also deepening `floating_min_pnl` (always adverse).

The engine is intentionally simple; a later phase plugs in pip-based / tick-based
models. `config['seed']` makes slippage deterministic for testing.

Required trade fields:
    net_pnl                          — realized PnL (USD), always required

Optional trade fields (unlock intrabar flip):
    side / direction                 — 'BUY' | 'SELL'
    sl_price, tp_price               — stop/target price levels
    candle_high, candle_low          — bar extremes for the exit candle
    entry_price, pip_value, lots     — used to compute flipped SL loss when
                                       `sl_loss_amount` isn't precomputed
    sl_loss_amount                   — precomputed USD loss when SL hit (preferred)
    floating_min_pnl, floating_pnl   — if present, also deepened adversely
"""
from __future__ import annotations

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)


DEFAULT_EXECUTION_CONFIG: dict = {
    "enabled": False,
    "spread": 0.0,             # flat USD cost per trade (round-trip: entry+exit)
    "max_slippage": 0.0,       # USD max adverse slippage (random uniform [0, max])
    "commission_per_trade": 0.0,  # flat USD commission per trade (round-trip)
    "intrabar_mode": "worst_case",  # "worst_case" | "optimistic"
    "seed": None,              # deterministic RNG when set (int)
}

_ALLOWED_MODES = ("worst_case", "optimistic")


def resolve_config(rules_config: dict | None) -> dict:
    """Merge user-supplied rules_config['execution'] into the defaults."""
    raw = (rules_config or {}).get("execution") or {}
    cfg = {**DEFAULT_EXECUTION_CONFIG, **raw}
    if cfg.get("intrabar_mode") not in _ALLOWED_MODES:
        cfg["intrabar_mode"] = "worst_case"
    return cfg


def _compute_sl_loss(trade: dict) -> Optional[float]:
    """Return the USD loss if SL were hit. Returns None if insufficient data."""
    pre = trade.get("sl_loss_amount")
    if pre is not None:
        return -abs(float(pre))    # normalize sign: loss < 0
    side = (trade.get("side") or trade.get("direction") or "").upper()
    entry = trade.get("entry_price")
    sl = trade.get("sl_price")
    pip_value = trade.get("pip_value")
    lots = trade.get("lots", 1.0)
    if side not in ("BUY", "SELL") or entry is None or sl is None or pip_value is None:
        return None
    # Distance in price units; caller supplies pip_value as USD-per-1.0-price-unit*lot.
    distance = abs(entry - sl)
    return -distance * pip_value * lots


def _intrabar_flip_to_sl(trade: dict) -> Optional[dict]:
    """If both TP and SL are inside the exit candle AND the trade is currently
    recorded as a winner, return a modified dict flipping the outcome to SL.
    Returns None when no flip applies (missing fields, no overlap, or already a loss).
    """
    side = (trade.get("side") or trade.get("direction") or "").upper()
    sl = trade.get("sl_price")
    tp = trade.get("tp_price")
    ch = trade.get("candle_high")
    cl = trade.get("candle_low")
    if not side or sl is None or tp is None or ch is None or cl is None:
        return None

    both_hit = False
    if side == "BUY":
        both_hit = (cl <= sl) and (ch >= tp)
    elif side == "SELL":
        both_hit = (ch >= sl) and (cl <= tp)
    if not both_hit:
        return None

    # Only flip winners → losers. If already a loss, leave untouched.
    net_pnl = float(trade.get("net_pnl", 0.0) or 0.0)
    if net_pnl <= 0:
        return None

    sl_loss = _compute_sl_loss(trade)
    if sl_loss is None:
        # Fallback: symmetric magnitude. Conservative: same $ as the TP win.
        sl_loss = -abs(net_pnl)

    flipped = dict(trade)
    flipped["net_pnl"] = float(sl_loss)
    fm = trade.get("floating_min_pnl")
    if fm is None:
        fm = trade.get("floating_pnl")
    deepened = float(sl_loss) if fm is None else min(float(fm), float(sl_loss))
    flipped["floating_min_pnl"] = deepened
    flipped["_exec_intrabar_flipped"] = True
    flipped["_exec_original_net_pnl"] = net_pnl
    return flipped


def _candle_range_multiplier(trade: dict) -> float:
    """Scale slippage mildly by candle volatility (high-low range vs entry).
    Returns a multiplier in [1.0, 2.0]. Falls back to 1.0 when candle data
    is missing — preserves legacy behavior.
    """
    ch = trade.get("candle_high")
    cl = trade.get("candle_low")
    entry = trade.get("entry_price")
    if ch is None or cl is None or entry is None or entry <= 0:
        return 1.0
    try:
        range_pct = (float(ch) - float(cl)) / float(entry)
    except (TypeError, ValueError, ZeroDivisionError):
        return 1.0
    if range_pct <= 0:
        return 1.0
    # 0% range → 1.0x, 1% range → 2.0x (capped). Typical intraday FX: 0.1–0.3%.
    mult = 1.0 + min(1.0, range_pct * 100.0)
    return mult


def apply_execution(trade: dict, config: dict, rng: random.Random | None = None) -> dict:
    """Return a NEW trade dict with execution realism applied.

    Order of operations (applied to the round-trip entry + exit together):
      1. Intrabar worst-case flip (may convert winner → loser).
      2. Spread cost subtraction (covers adverse entry + adverse exit combined).
      3. Adverse slippage subtraction, scaled by candle range when available.
      4. Commission subtraction (round-trip).
    Spread + slippage + commission deepen `floating_min_pnl` so intraday DD
    sees the full realistic cost too.

    When `config['enabled']` is False the trade is returned unchanged.
    """
    if not config.get("enabled"):
        return trade

    # Step 1: intrabar worst-case
    # Default the mode when the caller passed a config dict without it (keeps
    # low-level `apply_execution` calls in sync with `resolve_config` defaults).
    intrabar_mode = config.get("intrabar_mode")
    if intrabar_mode not in _ALLOWED_MODES:
        intrabar_mode = "worst_case"
    if intrabar_mode == "worst_case":
        flipped = _intrabar_flip_to_sl(trade)
        if flipped is not None:
            trade = flipped

    # Step 2 + 3 + 4: spread + slippage + commission
    rng = rng or random
    spread = float(config.get("spread") or 0.0)
    max_slip = float(config.get("max_slippage") or 0.0)
    commission = float(config.get("commission_per_trade") or 0.0)
    base_slip = rng.uniform(0.0, max_slip) if max_slip > 0 else 0.0
    slip = base_slip * _candle_range_multiplier(trade) if base_slip > 0 else 0.0
    cost = spread + slip + commission

    result = dict(trade)
    if cost > 0:
        result["net_pnl"] = float(result.get("net_pnl", 0.0) or 0.0) - cost
        fm = result.get("floating_min_pnl")
        if fm is None:
            fm = result.get("floating_pnl")
        result["floating_min_pnl"] = (-cost) if fm is None else (float(fm) - cost)
        result["_exec_spread_cost"] = spread
        result["_exec_slippage_cost"] = round(slip, 6)
        result["_exec_commission_cost"] = commission
    return result


def apply_execution_to_trades(trades: list, rules_config: dict | None) -> list:
    """Apply execution realism to a list of trades. Returns a NEW list.

    Fast-path (`enabled == False`): returns the input list as-is (pure pass-through,
    preserves object identity so existing tests & downstream logic are unaffected).
    """
    cfg = resolve_config(rules_config)
    if not cfg.get("enabled"):
        return trades
    seed = cfg.get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()
    adjusted = [apply_execution(t, cfg, rng) for t in trades]
    flipped = sum(1 for t in adjusted if t.get("_exec_intrabar_flipped"))
    total_cost = sum(
        (t.get("_exec_spread_cost", 0.0)
         + t.get("_exec_slippage_cost", 0.0)
         + t.get("_exec_commission_cost", 0.0))
        for t in adjusted
    )
    logger.info(
        "execution_engine: applied to %d trades (%d intrabar flips, total spread+slip+commission cost=$%.2f)",
        len(adjusted), flipped, total_cost,
    )
    return adjusted


def summarize_config(rules_config: dict | None) -> dict:
    """Compact execution summary for the simulator's `rules_used` response block."""
    cfg = resolve_config(rules_config)
    return {
        "enabled": bool(cfg.get("enabled")),
        "spread": float(cfg.get("spread") or 0.0),
        "max_slippage": float(cfg.get("max_slippage") or 0.0),
        "commission_per_trade": float(cfg.get("commission_per_trade") or 0.0),
        "intrabar_mode": cfg.get("intrabar_mode"),
    }
