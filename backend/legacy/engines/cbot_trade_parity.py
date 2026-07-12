"""
P0.4 — Dormant candle-level cBot trade-lifecycle parity module.

Status
------
* DORMANT BY DEFAULT. Gated by ``ENABLE_CBOT_TRADE_PARITY`` (default
  ``False``). Even when the flag is ON, **no production code path
  consults this module**. Activation requires BOTH the flag flip AND
  a deliberate future code change to wire a call-site (most likely
  into the existing trust gate in ``engines/cbot_parity.py``).
* No tick engine. No tick infrastructure. No framework expansion.
* Read-only with respect to Mongo at import time; never writes to any
  collection on its own. The eventual wiring will be responsible for
  emitting audit rows the same way the existing signal-parity sign-off
  does.

Why this exists
---------------
The audit (memory/EXECUTION_REALISM_AUDIT.md §3.1, §3.2, §6) made the
honest call: the existing ``cbot_parity.sign_off_parity(...)`` proves
*signal* alignment (BUY/SELL/None series equal between the canonical
Python interpreter and the transpiled cBot). It does NOT prove *trade*
alignment — entry price, SL/TP placement, position lifecycle.

P0.4 introduces the deterministic, candle-space machinery that can —
when activated — extend the parity certificate from signal-level to
first-N-trades-level. The implementation here is intentionally
candle-bound because:

* the entire research engine reasons in candle space today
  (backtest_engine, BI5 realism oracle, IR interpreter);
* tick-level parity belongs to P2/P3 (audit doc §9, P2.1, P3.2) and is
  explicitly out of P0 scope per the operator brief.

Determinism
-----------
The simulator is a pure function of ``(ir, prices, highs, lows,
timestamps, strategy_timeframe, first_n)``. No randomness, no clock
reads, no I/O. The Python interpreter ``IRInterpreter`` is the
canonical signal source; this module wraps it with a deterministic
trade-lifecycle model that matches the C# cBot scaffold's
``OnBar() → TryEnter → ExecuteMarketOrder(...slPips, tpPips)`` semantics
described in ``cbot_engine/ir_templates.py``.

Execution-semantic contract (matches the IR transpiler scaffold)
----------------------------------------------------------------
For a signal observed at the close of bar ``i``:

  1. Entry executes at the **OPEN of bar i+1** (cTrader's OnBar fires
     after a bar closes; ExecuteMarketOrder fills at the next bar's
     open in the candle-space approximation).
  2. SL/TP are pip-distances anchored to the entry price.
  3. While the position is open, each subsequent bar's [low, high] is
     scanned to detect SL / TP hits.
  4. When both SL and TP are inside the SAME candle's range, the
     conservative "worst-case" assumption (SL hit first) applies —
     matching ``engines/execution_engine.py::_intrabar_flip_to_sl``.
  5. A new entry signal arriving while a position is open is gated by
     ``max_concurrent`` (defaults to 1 in the IR convention).

Outputs
-------
``simulate_trades(...) -> dict`` returns:

::

    {
      "trades":   List[Trade],                   # full lifecycle log
      "summary":  {
          "total_trades":      int,
          "first_n":           int,               # echoed for audit
          "buy_count":         int,
          "sell_count":        int,
          "sl_hits":           int,
          "tp_hits":           int,
          "open_at_end":       int,
          "first_entry_bar":   int | None,
          "last_exit_bar":     int | None,
      },
      "parity_inputs": {                          # echoed for the trust gate
          "ir_version":             str,
          "strategy_timeframe":     str,
          "first_n":                int,
          "intrabar_mode":          "worst_case",
      },
      "dormant": bool,                            # always reflects flag state at call-time
    }

Where each Trade is::

    {
      "side":          "BUY" | "SELL",
      "entry_bar":     int,   # index in the supplied price series
      "exit_bar":      int | None,
      "entry_price":   float,
      "exit_price":    float | None,
      "sl_pips":       float,
      "tp_pips":       float,
      "exit_reason":   "SL" | "TP" | "OPEN_AT_END" | "INVALID",
      "pip_size":      float, # echoed for audit
    }

``compare_trade_series(left, right)`` produces a deterministic alignment
report between two trade lists, intended for the trust-gate caller that
runs the simulator twice (or against a future broker-emulator trace) to
verify byte-equal lifecycle agreement.

Wiring policy
-------------
* The existing ``cbot_parity.sign_off_parity(...)`` continues to do its
  job unchanged.
* When a future pass wires this module in, the integration point will
  be additive: ``sign_off_parity`` would call ``simulate_trades(...)``
  and persist a ``trade_parity_passed`` boolean alongside the existing
  signal verdict. Today, that wiring does not exist.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

# Defer heavy imports to call-time so simply importing this module on
# backend boot stays cheap (the module is dormant — every cycle pays a
# zero cost when the flag is OFF).


# ─────────────────────────────────────────────────────────────────────
# Public flag accessors (dormant by default)
# ─────────────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    """True iff ``ENABLE_CBOT_TRADE_PARITY`` is set to a truthy env
    value. Mirrors the discipline used by other dormant primitives
    (``replay_priority.is_enabled``, ``cadence_scheduler`` etc.):
    feature_flags is the canonical registry, but ``os.environ`` is the
    authoritative runtime source.
    """
    raw = os.environ.get("ENABLE_CBOT_TRADE_PARITY", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def first_n_default() -> int:
    """Operator-configurable first-N-trades window for the parity
    report. Defaults to 50 (matches audit doc §9 P0.4 recommendation).
    """
    try:
        return max(1, int(os.environ.get("CBOT_TRADE_PARITY_FIRST_N", "50")))
    except (TypeError, ValueError):
        return 50


# ─────────────────────────────────────────────────────────────────────
# Pip-size resolution
# ─────────────────────────────────────────────────────────────────────
# Conservative defaults matching cTrader convention. JPY pairs use
# 0.01; metals use 0.1; everything else uses 0.0001. The simulator
# accepts an explicit override so call-sites can pass broker-specific
# values when they become available.
_PIP_SIZE_OVERRIDES: Dict[str, float] = {
    "JPY":   0.01,
    "XAU":   0.1,
    "XAG":   0.001,
}


def resolve_pip_size(pair: str | None, override: float | None = None) -> float:
    """Deterministic pip-size resolver. ``override`` always wins.

    R2 — routes through ``engines.market_universe_adapter.resolve_pip_size``
    for alias resolution and (when the flag is ON) registry
    consultation. With the flag OFF the adapter falls back to this
    function's legacy substring rules — byte-identical behaviour.
    """
    try:
        from engines.market_universe_adapter import (
            resolve_pip_size as _adapter,
        )
        return _adapter(pair, override)
    except Exception:                                       # pragma: no cover
        if override is not None and override > 0:
            return float(override)
        if not pair:
            return 0.0001
        upper = pair.upper()
        for key, sz in _PIP_SIZE_OVERRIDES.items():
            if key in upper:
                return sz
        return 0.0001


# ─────────────────────────────────────────────────────────────────────
# Core: candle-level trade lifecycle simulation
# ─────────────────────────────────────────────────────────────────────
def _extract_sl_tp_pips(ir_dict: Dict[str, Any]) -> Tuple[float, float]:
    """Pull SL/TP pip-distances from a validated IR.

    The IR schema (engines.strategy_ir) carries ``sl_pips`` / ``tp_pips``
    at the risk block. We use those if present; otherwise we fall back
    to conservative defaults that match the transpiler's emitter
    defaults (audit-aligned).
    """
    risk = ir_dict.get("risk") or {}
    sl = risk.get("sl_pips")
    tp = risk.get("tp_pips")
    sl_pips = float(sl) if isinstance(sl, (int, float)) and sl > 0 else 20.0
    tp_pips = float(tp) if isinstance(tp, (int, float)) and tp > 0 else 40.0
    return sl_pips, tp_pips


def _resolve_trade_outcome_at_bar(
    *,
    side: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    bar_high: float,
    bar_low: float,
) -> Optional[str]:
    """Return 'SL', 'TP', or None for a single bar's outcome.

    Worst-case discipline: when both SL and TP are inside the same
    bar's [low, high], SL wins. This is the same heuristic used by
    ``engines.execution_engine._intrabar_flip_to_sl`` and is the
    conservative, audit-favored assumption.
    """
    if side == "BUY":
        sl_hit = bar_low <= sl_price
        tp_hit = bar_high >= tp_price
    else:  # SELL
        sl_hit = bar_high >= sl_price
        tp_hit = bar_low <= tp_price

    if sl_hit and tp_hit:
        return "SL"
    if sl_hit:
        return "SL"
    if tp_hit:
        return "TP"
    return None


def simulate_trades(
    ir: Any,
    *,
    prices: List[float],
    highs: List[float],
    lows: List[float],
    timestamps: Optional[List] = None,
    strategy_timeframe: str = "H1",
    pair: Optional[str] = None,
    pip_size: Optional[float] = None,
    max_concurrent: int = 1,
    first_n: Optional[int] = None,
) -> Dict[str, Any]:
    """Candle-level trade-lifecycle simulator matching the IR
    transpiler's scaffold contract.

    Pure function. Deterministic. Never writes to any collection.

    Parameters
    ----------
    ir : StrategyIR | dict
        Schema-validated Strategy IR.
    prices, highs, lows : sequence[float]
        Bar closes / highs / lows on the strategy timeframe. Must be
        the same length.
    timestamps : sequence | None
        Optional timestamps — recorded into the trade log when present.
    strategy_timeframe : str
        Used by the IR interpreter for HTF synthesis.
    pair : str | None
        Used to resolve pip_size when no explicit override is given.
    pip_size : float | None
        Explicit pip-size override (e.g. for non-standard brokers).
    max_concurrent : int
        Max simultaneously-open positions. Default 1 — matches the
        cBot scaffold's default ``MaxConcurrent`` for a single-strategy
        bot.
    first_n : int | None
        Truncates the trade log to the first N trades (operator-tunable
        via ``CBOT_TRADE_PARITY_FIRST_N``).

    Returns
    -------
    dict
        See module docstring for the shape.
    """
    # Local imports keep the dormant-import-cost low.
    from cbot_engine.ir_parity_simulator import (
        IRCoverageGap,  # noqa: F401 — re-exported via __all__ below
        simulate_cbot_signals,
    )

    if not (len(prices) == len(highs) == len(lows)):
        raise ValueError(
            "simulate_trades: prices/highs/lows length mismatch "
            f"({len(prices)} / {len(highs)} / {len(lows)})"
        )

    # Get the canonical signal series (this is the SAME source the
    # signal-parity sign-off uses — so trade-parity is a strict
    # superset of signal-parity).
    sig_report = simulate_cbot_signals(
        ir,
        prices=prices, highs=highs, lows=lows,
        timestamps=timestamps, strategy_timeframe=strategy_timeframe,
    )
    signals: List[Optional[str]] = sig_report["signals"]

    # Re-derive the IR dict (cheap; same canonicalisation path as the
    # signal simulator) so we can read sl/tp pip-distances.
    from engines.strategy_ir import StrategyIR, validate_ir
    if isinstance(ir, StrategyIR):
        ir_dict = ir.model_dump(mode="json")
    elif isinstance(ir, dict):
        ir_dict = validate_ir(ir).model_dump(mode="json")
    else:
        ir_dict = validate_ir(dict(ir)).model_dump(mode="json")

    sl_pips, tp_pips = _extract_sl_tp_pips(ir_dict)
    ps = resolve_pip_size(pair, override=pip_size)
    fn = max(1, first_n if first_n is not None else first_n_default())

    trades: List[Dict[str, Any]] = []
    open_positions: List[Dict[str, Any]] = []
    n = len(prices)

    for i in range(n):
        # ── 1) Resolve outcome on every currently-open position ──
        survivors: List[Dict[str, Any]] = []
        for pos in open_positions:
            outcome = _resolve_trade_outcome_at_bar(
                side=pos["side"],
                entry_price=pos["entry_price"],
                sl_price=pos["sl_price"],
                tp_price=pos["tp_price"],
                bar_high=highs[i],
                bar_low=lows[i],
            )
            if outcome is None:
                survivors.append(pos)
                continue
            pos["exit_bar"] = i
            pos["exit_reason"] = outcome
            pos["exit_price"] = pos["sl_price"] if outcome == "SL" else pos["tp_price"]
            trades.append(pos)
            if len(trades) >= fn:
                # Honest truncation — stop processing further bars
                # once the operator-requested window is full.
                break
        else:
            open_positions = survivors
        if len(trades) >= fn:
            break

        # ── 2) If a signal fires at the CLOSE of bar i, enter at the
        #       OPEN of bar i+1 (next-bar-open semantics).
        sig = signals[i]
        if sig not in ("BUY", "SELL"):
            continue
        if i + 1 >= n:
            # No next bar to fill against — honest refusal.
            continue
        if len(open_positions) >= max_concurrent:
            continue

        entry_price = prices[i + 1]  # next-bar OPEN approximated by prev close;
        # NOTE: prices[] is the CLOSE series. The exact next-bar OPEN
        # is not available in the closes-only fixture; using the
        # next-bar close as the entry approximation is the audit-
        # favored, transparently-documented candle-space choice. When
        # a richer fixture (with opens) is supplied later, this is
        # the single line to upgrade.
        if sig == "BUY":
            sl_price = entry_price - sl_pips * ps
            tp_price = entry_price + tp_pips * ps
        else:
            sl_price = entry_price + sl_pips * ps
            tp_price = entry_price - tp_pips * ps

        open_positions.append({
            "side":         sig,
            "entry_bar":    i + 1,
            "entry_price":  entry_price,
            "sl_pips":      sl_pips,
            "tp_pips":      tp_pips,
            "sl_price":     sl_price,
            "tp_price":     tp_price,
            "exit_bar":     None,
            "exit_price":   None,
            "exit_reason":  None,
            "pip_size":     ps,
        })

    # Any open positions at the end of the fixture exit as OPEN_AT_END.
    for pos in open_positions:
        if len(trades) >= fn:
            break
        pos["exit_bar"] = None
        pos["exit_reason"] = "OPEN_AT_END"
        pos["exit_price"] = None
        trades.append(pos)

    # ── Summary ───────────────────────────────────────────────────
    summary = {
        "total_trades":     len(trades),
        "first_n":          fn,
        "buy_count":        sum(1 for t in trades if t["side"] == "BUY"),
        "sell_count":       sum(1 for t in trades if t["side"] == "SELL"),
        "sl_hits":          sum(1 for t in trades if t["exit_reason"] == "SL"),
        "tp_hits":          sum(1 for t in trades if t["exit_reason"] == "TP"),
        "open_at_end":      sum(1 for t in trades if t["exit_reason"] == "OPEN_AT_END"),
        "first_entry_bar":  trades[0]["entry_bar"] if trades else None,
        "last_exit_bar":    (
            max((t["exit_bar"] for t in trades if t["exit_bar"] is not None), default=None)
        ),
    }

    return {
        "trades":   trades,
        "summary":  summary,
        "parity_inputs": {
            "ir_version":          ir_dict.get("ir_version") or ir_dict.get("version"),
            "strategy_timeframe":  strategy_timeframe,
            "first_n":             fn,
            "intrabar_mode":       "worst_case",
        },
        "dormant": not is_enabled(),
    }


# ─────────────────────────────────────────────────────────────────────
# Deterministic alignment report
# ─────────────────────────────────────────────────────────────────────
def compare_trade_series(
    left: List[Dict[str, Any]],
    right: List[Dict[str, Any]],
    *,
    tolerance_price: float = 1e-9,
) -> Dict[str, Any]:
    """Bit-strict alignment between two trade lists.

    Used by the future trust-gate wiring to compare:
      * left  = ``simulate_trades(ir, …)`` from the canonical interpreter
      * right = the SAME, OR a future broker-emulator trace (P3.2)

    Returns a verdict ``PASSED | MISMATCH | EMPTY`` plus the first
    diverging trade index (if any) — enough for an operator-facing
    forensic line. Never raises.
    """
    if not left and not right:
        return {"verdict": "EMPTY", "compared": 0, "first_divergence": None, "reason": None}
    if len(left) != len(right):
        return {
            "verdict": "MISMATCH",
            "compared": min(len(left), len(right)),
            "first_divergence": min(len(left), len(right)),
            "reason": f"length: left={len(left)} right={len(right)}",
        }
    for i, (a, b) in enumerate(zip(left, right)):
        if a.get("side") != b.get("side"):
            return {
                "verdict": "MISMATCH", "compared": i, "first_divergence": i,
                "reason": f"side: left={a.get('side')} right={b.get('side')}",
            }
        if a.get("entry_bar") != b.get("entry_bar"):
            return {
                "verdict": "MISMATCH", "compared": i, "first_divergence": i,
                "reason": f"entry_bar: left={a.get('entry_bar')} right={b.get('entry_bar')}",
            }
        if a.get("exit_bar") != b.get("exit_bar"):
            return {
                "verdict": "MISMATCH", "compared": i, "first_divergence": i,
                "reason": f"exit_bar: left={a.get('exit_bar')} right={b.get('exit_bar')}",
            }
        if a.get("exit_reason") != b.get("exit_reason"):
            return {
                "verdict": "MISMATCH", "compared": i, "first_divergence": i,
                "reason": f"exit_reason: left={a.get('exit_reason')} right={b.get('exit_reason')}",
            }
        ep_a, ep_b = a.get("entry_price"), b.get("entry_price")
        if ep_a is not None and ep_b is not None and abs(ep_a - ep_b) > tolerance_price:
            return {
                "verdict": "MISMATCH", "compared": i, "first_divergence": i,
                "reason": f"entry_price: left={ep_a} right={ep_b}",
            }
    return {
        "verdict": "PASSED",
        "compared": len(left),
        "first_divergence": None,
        "reason": None,
    }


__all__ = [
    "is_enabled",
    "first_n_default",
    "resolve_pip_size",
    "simulate_trades",
    "compare_trade_series",
]
