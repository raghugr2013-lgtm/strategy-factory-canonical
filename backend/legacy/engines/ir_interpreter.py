"""Strategy-IR Interpreter — Phase 28-B.

Pure-function evaluator over a validated ``StrategyIR``. Produces a
signal series (``"BUY"`` / ``"SELL"`` / ``None``) consumable by
``backtest_engine._run_segment_loop`` via the additive hook introduced
in this phase.

Architectural promise — Phase 28-B scope:
    * Interpreter is INVOKED only when ``strategy_ir`` is present on the
      backtest call. Legacy strategies (no IR) follow the unchanged
      ``_signal_at(i)`` dispatch path. The hook is reversible — remove
      the IR field and the legacy path resumes.
    * Indicator primitives are reused from ``engines.backtest_engine``
      (``_ema``, ``_rsi``, ``_atr`` and the BB/MACD helpers) so the
      indicator arrays are bit-identical to the legacy path. This is
      the foundation of the trust-gate parity.
    * Strict None-semantics: any operand returning None at bar ``i``
      causes its containing comparison to return False (no entry).
      This mirrors the legacy "warmup → no signal" behaviour for the
      common case where the slowest indicator dominates warmup.
    * No I/O, no Mongo, no LLM.

Trust gate (executed by ``tests/test_ir_interpreter_trust_gate.py``):
    * Build a reference IR per legacy strategy_type.
    * Run the same backtest via legacy path AND IR path.
    * Assert PF parity within ±2%, DD parity within ±5%, exact trade-
      count match. If any of the four references fails → halt Phase B
      before Phase C.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.backtest_engine import _atr, _ema, _rsi
from engines.strategy_ir import StrategyIR

Signal = Optional[str]   # "BUY" | "SELL" | None


# ─────────────────────────────────────────────────────────────────────
# Indicator support — reuses backtest_engine primitives for bit-parity.
# ─────────────────────────────────────────────────────────────────────

def _bb_from_prices(prices: List[float], period: int, std_dev: float):
    """Bollinger bands using the same SMA + std formula as
    backtest_engine. Returns (mid, upper, lower) lists aligned with
    ``prices`` (None for warmup bars)."""
    n = len(prices)
    mid: List[Optional[float]] = [None] * n
    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n
    if n < period:
        return mid, upper, lower
    for i in range(period - 1, n):
        window = prices[i - period + 1 : i + 1]
        sma = sum(window) / period
        var = sum((p - sma) ** 2 for p in window) / period
        sd = math.sqrt(var) if var >= 0 else 0.0
        mid[i] = sma
        upper[i] = sma + std_dev * sd
        lower[i] = sma - std_dev * sd
    return mid, upper, lower


def _htf_ema_series(prices: List[float], htf_factor: int,
                     htf_period: int) -> List[Optional[float]]:
    """Replicates the HTF EMA computation in
    ``backtest_engine._compute_indicators_for_segment``: subsample by
    ``htf_factor`` and EMA the coarse series, then upsample by
    repetition. Falls back to None when there isn't enough data."""
    n = len(prices)
    if htf_factor < 2 or n < htf_factor * (htf_period + 5):
        return [None] * n
    coarse = prices[::htf_factor]
    coarse_ema = _ema(coarse, htf_period)
    out: List[Optional[float]] = []
    for v in coarse_ema:
        out.extend([v] * htf_factor)
    out = out[:n]
    while len(out) < n:
        out.append(out[-1] if out else None)
    return out


_HTF_FACTOR = {"M1": 15, "M5": 12, "M15": 4, "M30": 2,
               "H1": 4,  "H4": 6,  "D1": 5}


# ─────────────────────────────────────────────────────────────────────
# Interpreter
# ─────────────────────────────────────────────────────────────────────

class IRInterpreter:
    """Evaluates a validated Strategy-IR against a precomputed bar
    series. Single-threaded; one instance per backtest segment."""

    def __init__(
        self,
        ir: dict | StrategyIR,
        *,
        prices: List[float],
        highs: List[float],
        lows: List[float],
        timestamps: List | None = None,
        strategy_timeframe: str = "H1",
    ):
        if isinstance(ir, StrategyIR):
            self.ir: dict = ir.model_dump(mode="json")
        elif isinstance(ir, dict):
            self.ir = ir
        else:
            raise TypeError("ir must be StrategyIR or dict")

        self.prices = prices
        self.highs = highs
        self.lows = lows
        self.timestamps = timestamps or []
        self.n = len(prices)
        self._tf = strategy_timeframe.upper()

        self._indicator_data: Dict[str, Any] = {}
        self._precompute_indicators()

    # ── Indicator precomputation ─────────────────────────────────

    def _precompute_indicators(self) -> None:
        for ind in self.ir.get("indicators") or []:
            kind = ind["kind"]
            params = ind.get("params") or {}
            iid = ind["id"]
            if kind == "EMA":
                self._indicator_data[iid] = {
                    "series": _ema(self.prices, int(params["period"])),
                    "kind": "EMA",
                }
            elif kind == "RSI":
                self._indicator_data[iid] = {
                    "series": _rsi(self.prices, int(params.get("period", 14))),
                    "kind": "RSI",
                }
            elif kind == "ATR":
                self._indicator_data[iid] = {
                    "series": _atr(self.highs, self.lows, self.prices,
                                   int(params.get("period", 14))),
                    "kind": "ATR",
                }
            elif kind == "BOLLINGER":
                mid, up, lo = _bb_from_prices(
                    self.prices,
                    int(params.get("period", 20)),
                    float(params.get("std_dev", 2.0)),
                )
                self._indicator_data[iid] = {
                    "mid": mid, "upper": up, "lower": lo,
                    "kind": "BOLLINGER",
                }
            elif kind == "HTF_EMA":
                # Compute HTF EMA per the backtest engine's convention.
                htf_factor = _HTF_FACTOR.get(self._tf, 4)
                period = int(params["period"])
                self._indicator_data[iid] = {
                    "series": _htf_ema_series(self.prices, htf_factor, period),
                    "kind": "HTF_EMA",
                }
            else:
                # Unknown indicator kind — store empty series; predicates
                # referencing it will evaluate False.
                self._indicator_data[iid] = {"series": [None] * self.n,
                                              "kind": kind}

    # ── Operand resolution ───────────────────────────────────────

    def _resolve_operand(self, op: Any, i: int) -> Optional[float]:
        if isinstance(op, dict):
            if "ref" in op:
                ind = self._indicator_data.get(op["ref"])
                if ind is None:
                    return None
                series = ind.get("series")
                if series is None:
                    return None
                if i < 0 or i >= len(series):
                    return None
                return series[i]
            if "const" in op:
                return float(op["const"])
            if "price" in op:
                stream = {
                    "open": self.prices,   # close as proxy for open in 1-stream feeds
                    "close": self.prices,
                    "high": self.highs,
                    "low": self.lows,
                }.get(op["price"])
                if stream is None:
                    return None
                offset = int(op.get("bar_offset", 0))
                idx = i - offset
                if idx < 0 or idx >= len(stream):
                    return None
                return stream[idx]
        return None

    # ── Predicate evaluation ─────────────────────────────────────

    def _eval(self, node: dict, i: int) -> bool:
        if not isinstance(node, dict):
            return False
        op = node.get("op")
        args = node.get("args") or []

        # ── Logical operators ──
        if op == "AND":
            return all(self._eval(a, i) for a in args)
        if op == "OR":
            return any(self._eval(a, i) for a in args)
        if op == "NOT":
            return not self._eval(args[0], i)

        # ── Comparison operators ──
        if op in ("GT", "LT", "GE", "LE", "EQ", "NEQ"):
            a = self._resolve_operand(args[0], i)
            b = self._resolve_operand(args[1], i)
            if a is None or b is None:
                return False
            if op == "GT":
                return a > b
            if op == "LT":
                return a < b
            if op == "GE":
                return a >= b
            if op == "LE":
                return a <= b
            if op == "EQ":
                return a == b
            if op == "NEQ":
                return a != b

        # ── Cross detection ──
        if op in ("CROSS_UP", "CROSS_DOWN"):
            if i < 1:
                return False
            a_now = self._resolve_operand(args[0], i)
            b_now = self._resolve_operand(args[1], i)
            a_prev = self._resolve_operand(args[0], i - 1)
            b_prev = self._resolve_operand(args[1], i - 1)
            if any(v is None for v in (a_now, b_now, a_prev, b_prev)):
                return False
            if op == "CROSS_UP":
                return a_now > b_now and a_prev <= b_prev
            return a_now < b_now and a_prev >= b_prev

        # ── Range break (session range) ──
        if op in ("RANGE_BREAK_UP", "RANGE_BREAK_DOWN"):
            hi, lo = self._session_range_at(i, node["window_start_gmt"],
                                            node["window_end_gmt"])
            if hi is None or lo is None:
                return False
            close_now = self.prices[i] if i < self.n else None
            close_prev = self.prices[i - 1] if i >= 1 else None
            if close_now is None or close_prev is None:
                return False
            if op == "RANGE_BREAK_UP":
                return close_now > hi and close_prev <= hi
            return close_now < lo and close_prev >= lo

        # ── Time predicates ──
        if op in ("AT_TIME", "IN_GMT_WINDOW"):
            return self._in_window(i, node["after"], node["before"])

        # ── Bollinger band predicates ──
        if op in ("BAND_TOUCH_UPPER", "BAND_TOUCH_LOWER",
                  "BAND_BREAK_UPPER", "BAND_BREAK_LOWER"):
            bb_ind = self._indicator_data.get(node["indicator"])
            if not bb_ind or bb_ind.get("kind") != "BOLLINGER":
                return False
            upper = bb_ind["upper"]
            lower = bb_ind["lower"]
            if i >= len(upper):
                return False
            up = upper[i]
            lo = lower[i]
            if up is None or lo is None:
                return False
            if op == "BAND_TOUCH_UPPER":
                return self.highs[i] >= up
            if op == "BAND_TOUCH_LOWER":
                return self.lows[i] <= lo
            if op == "BAND_BREAK_UPPER":
                return self.prices[i] > up
            if op == "BAND_BREAK_LOWER":
                return self.prices[i] < lo

        # ── ATR ratio above ──
        if op == "ATR_RATIO_ABOVE":
            atr_ind = self._indicator_data.get(node["indicator"])
            if not atr_ind:
                return False
            series = atr_ind.get("series") or []
            if i >= len(series) or series[i] is None:
                return False
            baseline = int(node.get("baseline_period", 20))
            if i < baseline:
                return False
            window = [v for v in series[i - baseline + 1 : i + 1]
                      if v is not None]
            if not window:
                return False
            avg = sum(window) / len(window)
            if avg == 0:
                return False
            return (series[i] / avg) >= float(node.get("min_ratio", 0.8))

        # ── HTF slope ──
        if op in ("HTF_SLOPE_UP", "HTF_SLOPE_DOWN"):
            fast = self._indicator_data.get(node["htf_ema_fast"])
            slow = self._indicator_data.get(node["htf_ema_slow"])
            if not fast or not slow:
                return False
            fs = (fast.get("series") or [])
            ss = (slow.get("series") or [])
            if i >= len(fs) or i >= len(ss):
                return False
            if fs[i] is None or ss[i] is None:
                return False
            if op == "HTF_SLOPE_UP":
                return fs[i] > ss[i]
            return fs[i] < ss[i]

        # ── BB squeeze percentile ──
        if op == "BB_SQUEEZE_PERCENTILE":
            bb_ind = self._indicator_data.get(node["indicator"])
            if not bb_ind or bb_ind.get("kind") != "BOLLINGER":
                return False
            upper = bb_ind["upper"]
            lower = bb_ind["lower"]
            lookback = int(node["lookback"])
            pct = float(node["percentile"])
            if i < lookback or upper[i] is None or lower[i] is None:
                return False
            widths = []
            for k in range(i - lookback + 1, i + 1):
                if upper[k] is not None and lower[k] is not None:
                    widths.append(upper[k] - lower[k])
            if not widths:
                return False
            current = upper[i] - lower[i]
            # Percentile threshold: bottom pct% of widths.
            widths_sorted = sorted(widths)
            cutoff_idx = max(0, int(len(widths_sorted) * pct / 100) - 1)
            cutoff = widths_sorted[cutoff_idx]
            return current <= cutoff

        return False

    # ── Helpers ──────────────────────────────────────────────────

    def _session_range_at(self, i: int, start_gmt: str, end_gmt: str):
        """Compute the (high, low) of the GMT window for the trading
        day that contains bar ``i``. Requires ``timestamps``."""
        if not self.timestamps or i >= len(self.timestamps):
            return None, None
        ts_now = self._parse_ts(self.timestamps[i])
        if ts_now is None:
            return None, None
        # Walk backwards to find bars within today's [start, end] window.
        s_h, s_m = (int(x) for x in start_gmt.split(":"))
        e_h, e_m = (int(x) for x in end_gmt.split(":"))
        day = ts_now.date()
        win_start = datetime(day.year, day.month, day.day, s_h, s_m,
                              tzinfo=timezone.utc)
        win_end = datetime(day.year, day.month, day.day, e_h, e_m,
                           tzinfo=timezone.utc)
        hi = None
        lo = None
        for k in range(i - 1, max(-1, i - 500) - 1, -1):
            ts_k = self._parse_ts(self.timestamps[k])
            if ts_k is None:
                break
            if ts_k < win_start:
                break
            if win_start <= ts_k < win_end:
                hk = self.highs[k] if k < len(self.highs) else None
                lk = self.lows[k] if k < len(self.lows) else None
                if hk is None or lk is None:
                    continue
                hi = hk if hi is None else max(hi, hk)
                lo = lk if lo is None else min(lo, lk)
        return hi, lo

    def _in_window(self, i: int, after: str, before: str) -> bool:
        if not self.timestamps or i >= len(self.timestamps):
            return False
        ts = self._parse_ts(self.timestamps[i])
        if ts is None:
            return False
        a_h, a_m = (int(x) for x in after.split(":"))
        b_h, b_m = (int(x) for x in before.split(":"))
        minute_now = ts.hour * 60 + ts.minute
        a_min = a_h * 60 + a_m
        b_min = b_h * 60 + b_m
        return a_min <= minute_now < b_min

    @staticmethod
    def _parse_ts(ts) -> Optional[datetime]:
        if isinstance(ts, datetime):
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        if isinstance(ts, str):
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None

    # ── Public surface ───────────────────────────────────────────

    def signal_at(self, i: int) -> Signal:
        """Return ``"BUY"``, ``"SELL"`` or ``None`` for bar ``i``."""
        if i < 1 or i >= self.n:
            return None
        # Session/volatility filters short-circuit.
        sf = self.ir.get("session_filter")
        if sf and not self._in_window(i, sf["open"], sf["close"]):
            return None
        vf = self.ir.get("volatility_filter")
        if vf:
            vf_node = {"op": "ATR_RATIO_ABOVE", "args": [],
                       "indicator": vf["indicator"],
                       "baseline_period": vf["baseline_period"],
                       "min_ratio": vf["min_ratio"]}
            if not self._eval(vf_node, i):
                return None
        if self._eval(self.ir["entry_long"], i):
            return "BUY"
        if self._eval(self.ir["entry_short"], i):
            return "SELL"
        return None


# ─────────────────────────────────────────────────────────────────────
# Legacy-equivalent reference IRs (used by the trust-gate)
# ─────────────────────────────────────────────────────────────────────

def build_legacy_reference_ir(
    strategy_type: str,
    *,
    fast_period: int,
    slow_period: int,
    rsi_cfg: dict | None = None,
    bb_cfg: dict | None = None,
    macd_cfg: dict | None = None,
    pair: str = "EURUSD",
    timeframe: str = "H1",
) -> StrategyIR:
    """Build a Strategy-IR whose ``signal_at(i)`` matches the legacy
    ``_signal_<strategy_type>`` function bit-for-bit, given identical
    indicator parameters."""

    rsi_period = (rsi_cfg or {}).get("period", 14)
    buy_th = (rsi_cfg or {}).get("buy_threshold", 50)
    sell_th = (rsi_cfg or {}).get("sell_threshold", 50)
    bb_period = (bb_cfg or {}).get("period", 20)
    bb_std = float((bb_cfg or {}).get("std_dev", 2.0))

    if strategy_type == "trend_following":
        ir = {
            "ir_version": 1,
            "metadata": {"name": "Legacy TF Reference", "pair": pair,
                         "timeframe": timeframe,
                         "mutation_type": "_legacy_trend_following"},
            "indicators": [
                {"id": "ema_fast", "kind": "EMA",
                 "params": {"period": fast_period}},
                {"id": "ema_slow", "kind": "EMA",
                 "params": {"period": slow_period}},
            ],
            "entry_long": {
                "op": "CROSS_UP",
                "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}],
            },
            "entry_short": {
                "op": "CROSS_DOWN",
                "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}],
            },
            "exit": {"stop_loss": {"kind": "pips", "pips": 20.0},
                     "take_profit": {"kind": "pips", "pips": 40.0}},
        }
        if rsi_cfg:
            ir["indicators"].append({"id": "rsi", "kind": "RSI",
                                     "params": {"period": rsi_period}})
            ir["entry_long"] = {"op": "AND", "args": [
                ir["entry_long"],
                {"op": "GE", "args": [{"ref": "rsi"}, {"const": buy_th}]},
            ]}
            ir["entry_short"] = {"op": "AND", "args": [
                ir["entry_short"],
                {"op": "LE", "args": [{"ref": "rsi"}, {"const": sell_th}]},
            ]}
        return StrategyIR.model_validate(ir)

    if strategy_type == "breakout":
        # Legacy: close crosses fast_ma + RSI filter (default 55/45).
        ir = {
            "ir_version": 1,
            "metadata": {"name": "Legacy Breakout Reference", "pair": pair,
                         "timeframe": timeframe,
                         "mutation_type": "_legacy_breakout"},
            "indicators": [
                {"id": "ema_fast", "kind": "EMA",
                 "params": {"period": fast_period}},
            ],
            "entry_long": {
                "op": "CROSS_UP",
                "args": [{"price": "close"}, {"ref": "ema_fast"}],
            },
            "entry_short": {
                "op": "CROSS_DOWN",
                "args": [{"price": "close"}, {"ref": "ema_fast"}],
            },
            "exit": {"stop_loss": {"kind": "pips", "pips": 20.0},
                     "take_profit": {"kind": "pips", "pips": 40.0}},
        }
        if rsi_cfg:
            ir["indicators"].append({"id": "rsi", "kind": "RSI",
                                     "params": {"period": rsi_period}})
            ir["entry_long"] = {"op": "AND", "args": [
                ir["entry_long"],
                {"op": "GE", "args": [{"ref": "rsi"}, {"const": buy_th}]},
            ]}
            ir["entry_short"] = {"op": "AND", "args": [
                ir["entry_short"],
                {"op": "LE", "args": [{"ref": "rsi"}, {"const": sell_th}]},
            ]}
        return StrategyIR.model_validate(ir)

    if strategy_type == "mean_reversion":
        # Legacy:
        #   if bb available AND rsi < buy AND price <= bb_lower → BUY
        #   if bb available AND rsi > sell AND price >= bb_upper → SELL
        #   else if rsi < buy → BUY
        #        elif rsi > sell → SELL
        ir = {
            "ir_version": 1,
            "metadata": {"name": "Legacy MR Reference", "pair": pair,
                         "timeframe": timeframe,
                         "mutation_type": "_legacy_mean_reversion"},
            "indicators": [
                {"id": "rsi", "kind": "RSI",
                 "params": {"period": rsi_period}},
            ],
            "entry_long":  {"op": "LT", "args": [{"ref": "rsi"}, {"const": buy_th}]},
            "entry_short": {"op": "GT", "args": [{"ref": "rsi"}, {"const": sell_th}]},
            "exit": {"stop_loss": {"kind": "pips", "pips": 20.0},
                     "take_profit": {"kind": "pips", "pips": 40.0}},
        }
        if bb_cfg:
            ir["indicators"].append({
                "id": "bb", "kind": "BOLLINGER",
                "params": {"period": bb_period, "std_dev": bb_std},
            })
            # Replace primary entries with the BB-confirmed forms.
            # Legacy: tries BB first, then RSI-only fallback. The
            # OR captures that exact precedence: BB-confirmed branch
            # also implies RSI condition; RSI-only fallback alone.
            ir["entry_long"] = {
                "op": "OR", "args": [
                    {"op": "AND", "args": [
                        {"op": "LT", "args": [{"ref": "rsi"}, {"const": buy_th}]},
                        {"op": "BAND_TOUCH_LOWER", "args": [], "indicator": "bb"},
                    ]},
                    {"op": "LT", "args": [{"ref": "rsi"}, {"const": buy_th}]},
                ],
            }
            ir["entry_short"] = {
                "op": "OR", "args": [
                    {"op": "AND", "args": [
                        {"op": "GT", "args": [{"ref": "rsi"}, {"const": sell_th}]},
                        {"op": "BAND_TOUCH_UPPER", "args": [], "indicator": "bb"},
                    ]},
                    {"op": "GT", "args": [{"ref": "rsi"}, {"const": sell_th}]},
                ],
            }
        return StrategyIR.model_validate(ir)

    if strategy_type == "momentum":
        # Legacy momentum uses MACD which is not in IR v1 vocabulary.
        # Phase B intentionally documents this gap — momentum will be
        # added to IR v1.1 (or v2) before any reference is built.
        raise NotImplementedError(
            "Legacy momentum strategy_type uses MACD which is not in "
            "IR v1 vocabulary. Add a MACD indicator + cross operators "
            "before introducing a momentum reference IR."
        )

    raise ValueError(f"Unknown legacy strategy_type: {strategy_type}")


__all__ = [
    "IRInterpreter", "build_legacy_reference_ir",
]
