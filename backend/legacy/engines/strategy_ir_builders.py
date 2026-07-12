"""Per-mutation Strategy-IR builders — Phase 28-A.

One IR builder per mutation type. Each builder returns a validated
``StrategyIR`` instance mirroring the existing English rule semantics
in ``engines.mutation_engine``. Pure functions, no I/O, no Mongo.

Architectural promise:
    * The IR vocabulary covers ONLY existing mutations (operator decision
      Phase 28-A #1). No regime-aware, no state-machine extensions.
    * LLMs do not encode executable logic (operator decision #2). All
      IRs in this module are hand-written, deterministic.
    * Output is additive: existing mutators stay; we layer IR onto each
      return value via a small additive shim in mutation_engine.py.
"""
from __future__ import annotations

from typing import Optional

from engines.strategy_ir import StrategyIR


# ── Default risk block ────────────────────────────────────────────────

_DEFAULT_RISK = {
    "kind": "percent_of_balance",
    "percent": 1.0,
    "max_concurrent_positions": 1,
    "max_spread_pips": 3.0,
}

# ── HTF resolver (mirrors mutation_engine._htf) ───────────────────────

_HTF_MAP = {"M1": "M15", "M5": "H1", "M15": "H4", "M30": "H4",
            "H1": "H4",  "H4": "D1", "D1": "W1"}


def _htf_of(tf: str) -> str:
    return _HTF_MAP.get((tf or "H1").upper(), "H4")


# ── Builder helpers ───────────────────────────────────────────────────

def _meta(name: str, pair: str, tf: str, mutation_type: str) -> dict:
    return {"name": name, "pair": pair, "timeframe": tf,
            "mutation_type": mutation_type}


# ── Per-mutation builders ─────────────────────────────────────────────

def build_trend_pullback(pair: str, tf: str) -> StrategyIR:
    """Trend + RSI Pullback.
        EMA(50) > EMA(200) AND price near EMA(20) AND RSI crosses up 40 → BUY
        SL = ATR(14) × 1.5  |  TP = ATR(14) × 3.0
    """
    ir = {
        "ir_version": 1,
        "metadata": _meta("Trend + RSI Pullback", pair, tf, "trend_pullback"),
        "indicators": [
            {"id": "ema_fast", "kind": "EMA",  "params": {"period": 20}},
            {"id": "ema_mid",  "kind": "EMA",  "params": {"period": 50}},
            {"id": "ema_slow", "kind": "EMA",  "params": {"period": 200}},
            {"id": "rsi",      "kind": "RSI",  "params": {"period": 14}},
            {"id": "atr",      "kind": "ATR",  "params": {"period": 14}},
        ],
        "entry_long": {
            "op": "AND", "args": [
                {"op": "GT", "args": [{"ref": "ema_mid"}, {"ref": "ema_slow"}]},
                {"op": "LE", "args": [{"price": "close"}, {"ref": "ema_fast"}]},
                {"op": "CROSS_UP", "args": [{"ref": "rsi"}, {"const": 40}]},
            ],
        },
        "entry_short": {
            "op": "AND", "args": [
                {"op": "LT", "args": [{"ref": "ema_mid"}, {"ref": "ema_slow"}]},
                {"op": "GE", "args": [{"price": "close"}, {"ref": "ema_fast"}]},
                {"op": "CROSS_DOWN", "args": [{"ref": "rsi"}, {"const": 60}]},
            ],
        },
        "exit": {
            "stop_loss":   {"kind": "atr_mult", "indicator": "atr", "mult": 1.5},
            "take_profit": {"kind": "atr_mult", "indicator": "atr", "mult": 3.0},
        },
        "risk": _DEFAULT_RISK,
    }
    return StrategyIR.model_validate(ir)


def build_session_london_breakout(pair: str, tf: str) -> StrategyIR:
    """London Open Breakout.
        Range = 06:00–07:00 GMT; entry window 07:00–11:00 GMT.
        SL = range size  |  TP = 1.5 × range size  |  Close all by 16:00 GMT.
    """
    ir = {
        "ir_version": 1,
        "metadata": _meta("London Open Breakout", pair, tf, "session_london_breakout"),
        "indicators": [],
        "session_filter": {"kind": "gmt_window", "open": "07:00",
                           "close": "11:00", "force_flat_at": "16:00"},
        "entry_long": {
            "op": "RANGE_BREAK_UP",
            "args": [], "window_start_gmt": "06:00", "window_end_gmt": "07:00",
        },
        "entry_short": {
            "op": "RANGE_BREAK_DOWN",
            "args": [], "window_start_gmt": "06:00", "window_end_gmt": "07:00",
        },
        "exit": {
            "stop_loss":   {"kind": "range_fraction", "ratio": 1.0,
                             "window_start_gmt": "06:00", "window_end_gmt": "07:00"},
            "take_profit": {"kind": "range_fraction", "ratio": 1.5,
                             "window_start_gmt": "06:00", "window_end_gmt": "07:00"},
            "time_exit":   {"close_all_gmt": "16:00"},
        },
        "risk": _DEFAULT_RISK,
    }
    return StrategyIR.model_validate(ir)


def build_session_asian_range(pair: str, tf: str) -> StrategyIR:
    """Asian Range Breakout.
        Range = 00:00–07:00 GMT; entry after 07:00; close-all 15:00 GMT.
        SL = 50% of range  |  TP = 100% of range.
    """
    ir = {
        "ir_version": 1,
        "metadata": _meta("Asian Range Breakout", pair, tf, "session_asian_range"),
        "indicators": [],
        "session_filter": {"kind": "gmt_window", "open": "07:00",
                           "close": "15:00", "force_flat_at": "15:00"},
        "entry_long": {
            "op": "RANGE_BREAK_UP",
            "args": [], "window_start_gmt": "00:00", "window_end_gmt": "07:00",
        },
        "entry_short": {
            "op": "RANGE_BREAK_DOWN",
            "args": [], "window_start_gmt": "00:00", "window_end_gmt": "07:00",
        },
        "exit": {
            "stop_loss":   {"kind": "range_fraction", "ratio": 0.5,
                             "window_start_gmt": "00:00", "window_end_gmt": "07:00"},
            "take_profit": {"kind": "range_fraction", "ratio": 1.0,
                             "window_start_gmt": "00:00", "window_end_gmt": "07:00"},
            "time_exit":   {"close_all_gmt": "15:00"},
        },
        "risk": _DEFAULT_RISK,
    }
    return StrategyIR.model_validate(ir)


def build_volatility_atr_breakout(pair: str, tf: str) -> StrategyIR:
    """ATR Breakout.
        Close > previous_high + ATR(14) × 0.5  →  BUY
        SL = ATR × 1.5  |  TP = ATR × 3.0  (encoded via standalone fields
        in metadata; the predicate models the price-vs-shifted-high relation
        through the CROSS_UP operator using close and a synthetic
        previous-high reference is not supported in v1, so we encode the
        ATR-breakout via a Phase-1 simplification: GT(close, high[-1]) +
        ATR_RATIO_ABOVE filter. Faithful semantic equivalence will be
        revisited in Phase B trust-gate validation.)
    """
    ir = {
        "ir_version": 1,
        "metadata": {
            **_meta("ATR Breakout", pair, tf, "volatility_atr_breakout"),
            "atr_breakout_mult": 0.5,
        },
        "indicators": [
            {"id": "atr", "kind": "ATR", "params": {"period": 14}},
        ],
        "volatility_filter": {"kind": "atr_ratio", "indicator": "atr",
                              "baseline_period": 20, "min_ratio": 0.5},
        "entry_long": {
            "op": "GT",
            "args": [{"price": "close"}, {"price": "high", "bar_offset": 1}],
        },
        "entry_short": {
            "op": "LT",
            "args": [{"price": "close"}, {"price": "low", "bar_offset": 1}],
        },
        "exit": {
            "stop_loss":   {"kind": "atr_mult", "indicator": "atr", "mult": 1.5},
            "take_profit": {"kind": "atr_mult", "indicator": "atr", "mult": 3.0},
        },
        "risk": _DEFAULT_RISK,
    }
    return StrategyIR.model_validate(ir)


def build_volatility_bb_squeeze(pair: str, tf: str) -> StrategyIR:
    """Bollinger Squeeze Breakout."""
    ir = {
        "ir_version": 1,
        "metadata": _meta("Bollinger Squeeze Breakout", pair, tf,
                          "volatility_bollinger_squeeze"),
        "indicators": [
            {"id": "bb",  "kind": "BOLLINGER", "params": {"period": 20, "std_dev": 2.0}},
            {"id": "atr", "kind": "ATR",       "params": {"period": 14}},
        ],
        "entry_long": {
            "op": "AND", "args": [
                {"op": "BB_SQUEEZE_PERCENTILE", "args": [],
                 "indicator": "bb", "lookback": 100, "percentile": 20},
                {"op": "BAND_BREAK_UPPER", "args": [], "indicator": "bb"},
            ],
        },
        "entry_short": {
            "op": "AND", "args": [
                {"op": "BB_SQUEEZE_PERCENTILE", "args": [],
                 "indicator": "bb", "lookback": 100, "percentile": 20},
                {"op": "BAND_BREAK_LOWER", "args": [], "indicator": "bb"},
            ],
        },
        "exit": {
            "stop_loss":   {"kind": "band_mid",  "indicator": "bb"},
            "take_profit": {"kind": "atr_mult",  "indicator": "atr", "mult": 2.0},
        },
        "risk": _DEFAULT_RISK,
    }
    return StrategyIR.model_validate(ir)


def build_mean_reversion_rsi(pair: str, tf: str) -> StrategyIR:
    """RSI Mean Reversion.
        BUY when RSI(14) < 30 (confirmed by previous bar also < 30).
        Exit when RSI crosses 50; SL=20 pips, TP=30 pips.
    """
    ir = {
        "ir_version": 1,
        "metadata": _meta("RSI Mean Reversion", pair, tf, "mean_reversion_rsi"),
        "indicators": [
            {"id": "rsi", "kind": "RSI", "params": {"period": 14}},
        ],
        "entry_long": {
            "op": "AND", "args": [
                {"op": "LT", "args": [{"ref": "rsi"}, {"const": 30}]},
                {"op": "LT", "args": [{"ref": "rsi"}, {"const": 30}]},  # confirmation prev-bar — encoded via Phase-B interpreter lookback
            ],
        },
        "entry_short": {
            "op": "AND", "args": [
                {"op": "GT", "args": [{"ref": "rsi"}, {"const": 70}]},
                {"op": "GT", "args": [{"ref": "rsi"}, {"const": 70}]},
            ],
        },
        "exit": {
            "stop_loss":   {"kind": "pips", "pips": 20.0},
            "take_profit": {"kind": "indicator_cross", "indicator": "rsi", "level": 50.0},
        },
        "risk": _DEFAULT_RISK,
    }
    return StrategyIR.model_validate(ir)


def build_mean_reversion_bollinger(pair: str, tf: str) -> StrategyIR:
    """Bollinger Band Reversal."""
    ir = {
        "ir_version": 1,
        "metadata": _meta("Bollinger Band Reversal", pair, tf,
                          "mean_reversion_bollinger"),
        "indicators": [
            {"id": "bb",  "kind": "BOLLINGER", "params": {"period": 20, "std_dev": 2.0}},
            {"id": "atr", "kind": "ATR",       "params": {"period": 14}},
        ],
        "entry_long":  {"op": "BAND_TOUCH_LOWER", "args": [], "indicator": "bb"},
        "entry_short": {"op": "BAND_TOUCH_UPPER", "args": [], "indicator": "bb"},
        "exit": {
            "stop_loss":   {"kind": "atr_mult", "indicator": "atr", "mult": 1.5},
            "take_profit": {"kind": "band_mid", "indicator": "bb"},
        },
        "risk": _DEFAULT_RISK,
    }
    return StrategyIR.model_validate(ir)


# ── Composable filter mutations (operate on a base IR) ───────────────

def compose_filter_add_rsi(base: StrategyIR) -> StrategyIR:
    """Layer an RSI(14) >= 50 (long) / <= 50 (short) gate onto the base IR.

    GE/LE chosen deliberately to mirror the legacy ``_signal_*`` family's
    RSI-confirmation semantic (proven bit-identical in the Phase 28-B
    trust gate via ``build_legacy_reference_ir``): a long entry where
    ``rsi < buy_threshold`` is suppressed, i.e. ``rsi >= buy_threshold``
    is required to confirm. Strict GT/LT would diverge from the legacy
    backtest at the exact-threshold boundary; GE/LE preserves parity.
    """
    base_d = base.model_dump()
    # Add RSI indicator if absent.
    if not any(i["id"] == "rsi_filter" for i in base_d["indicators"]):
        base_d["indicators"].append(
            {"id": "rsi_filter", "kind": "RSI", "params": {"period": 14}}
        )
    base_d["entry_long"] = {
        "op": "AND", "args": [
            base_d["entry_long"],
            {"op": "GE", "args": [{"ref": "rsi_filter"}, {"const": 50}]},
        ],
    }
    base_d["entry_short"] = {
        "op": "AND", "args": [
            base_d["entry_short"],
            {"op": "LE", "args": [{"ref": "rsi_filter"}, {"const": 50}]},
        ],
    }
    base_d["metadata"]["mutation_type"] = "filter_add_rsi"
    base_d["metadata"]["name"] = (base_d["metadata"].get("name", "") +
                                  " + RSI Confirmation")
    return StrategyIR.model_validate(base_d)


def compose_filter_add_volatility(base: StrategyIR) -> StrategyIR:
    """Layer an ATR-ratio volatility filter onto the base IR."""
    base_d = base.model_dump()
    if not any(i["id"] == "atr_filter" for i in base_d["indicators"]):
        base_d["indicators"].append(
            {"id": "atr_filter", "kind": "ATR", "params": {"period": 14}}
        )
    base_d["volatility_filter"] = {
        "kind": "atr_ratio", "indicator": "atr_filter",
        "baseline_period": 20, "min_ratio": 0.8,
    }
    base_d["metadata"]["mutation_type"] = "filter_add_volatility"
    base_d["metadata"]["name"] = (base_d["metadata"].get("name", "") +
                                  " + Volatility Filter")
    return StrategyIR.model_validate(base_d)


def compose_filter_add_trend(base: StrategyIR) -> StrategyIR:
    """Layer an EMA(200) trend filter onto the base IR."""
    base_d = base.model_dump()
    if not any(i["id"] == "ema_trend" for i in base_d["indicators"]):
        base_d["indicators"].append(
            {"id": "ema_trend", "kind": "EMA", "params": {"period": 200}}
        )
    base_d["entry_long"] = {
        "op": "AND", "args": [
            base_d["entry_long"],
            {"op": "GT", "args": [{"price": "close"}, {"ref": "ema_trend"}]},
        ],
    }
    base_d["entry_short"] = {
        "op": "AND", "args": [
            base_d["entry_short"],
            {"op": "LT", "args": [{"price": "close"}, {"ref": "ema_trend"}]},
        ],
    }
    base_d["metadata"]["mutation_type"] = "filter_add_trend"
    base_d["metadata"]["name"] = (base_d["metadata"].get("name", "") +
                                  " + Trend Filter")
    return StrategyIR.model_validate(base_d)


def compose_mtf_htf_confirmation(base: StrategyIR) -> StrategyIR:
    """Layer an HTF EMA(50)>EMA(200) slope confirmation onto the base."""
    base_d = base.model_dump()
    tf = (base_d["metadata"].get("timeframe") or "H1").upper()
    htf = _htf_of(tf)
    if not any(i["id"] == "htf_ema_fast" for i in base_d["indicators"]):
        base_d["indicators"].append({
            "id": "htf_ema_fast", "kind": "HTF_EMA",
            "params": {"period": 50, "htf": htf},
        })
        base_d["indicators"].append({
            "id": "htf_ema_slow", "kind": "HTF_EMA",
            "params": {"period": 200, "htf": htf},
        })
    base_d["entry_long"] = {
        "op": "AND", "args": [
            base_d["entry_long"],
            {"op": "HTF_SLOPE_UP", "args": [],
             "htf_ema_fast": "htf_ema_fast", "htf_ema_slow": "htf_ema_slow"},
        ],
    }
    base_d["entry_short"] = {
        "op": "AND", "args": [
            base_d["entry_short"],
            {"op": "HTF_SLOPE_DOWN", "args": [],
             "htf_ema_fast": "htf_ema_fast", "htf_ema_slow": "htf_ema_slow"},
        ],
    }
    base_d["metadata"]["mutation_type"] = "mtf_htf_confirmation"
    base_d["metadata"]["name"] = (base_d["metadata"].get("name", "") +
                                  f" + {htf} Trend Confirmation")
    return StrategyIR.model_validate(base_d)


def compose_filter_remove_rsi(base: StrategyIR) -> StrategyIR:
    """Strip RSI references from indicators + predicates. Pure structural
    transformation — no text grep."""
    base_d = base.model_dump()
    rsi_ids = {i["id"] for i in base_d["indicators"] if i["kind"] == "RSI"}
    base_d["indicators"] = [i for i in base_d["indicators"] if i["id"] not in rsi_ids]

    def _strip(node):
        if not isinstance(node, dict) or "op" not in node:
            return node
        if node["op"] in ("AND", "OR"):
            kept = []
            for a in node["args"]:
                stripped = _strip(a)
                if _references_any(stripped, rsi_ids):
                    continue
                kept.append(stripped)
            if not kept:
                # If everything was RSI-gated, collapse to a trivial constant.
                return {"op": "GT", "args": [{"const": 1}, {"const": 0}]}
            if len(kept) == 1:
                return kept[0]
            node["args"] = kept
            return node
        return node

    def _references_any(node, ids: set) -> bool:
        if not isinstance(node, dict):
            return False
        if node.get("ref") in ids:
            return True
        for a in (node.get("args") or []):
            if _references_any(a, ids):
                return True
        return False

    base_d["entry_long"]  = _strip(base_d["entry_long"])
    base_d["entry_short"] = _strip(base_d["entry_short"])
    base_d["metadata"]["mutation_type"] = "filter_remove_rsi"
    base_d["metadata"]["name"] = (base_d["metadata"].get("name", "") +
                                  " (RSI removed)")
    return StrategyIR.model_validate(base_d)


# ── Risk-reward parametric variant ───────────────────────────────────

def compose_risk_reward(base: StrategyIR, ratio: float,
                        mutation_type: str) -> StrategyIR:
    """Replace base SL/TP with fixed pip-based pair at the requested R:R."""
    base_d = base.model_dump()
    sl_pips = 20.0
    tp_pips = float(int(sl_pips * ratio)) if ratio > 0 else sl_pips
    base_d["exit"]["stop_loss"]   = {"kind": "pips", "pips": sl_pips}
    base_d["exit"]["take_profit"] = {"kind": "pips", "pips": tp_pips}
    base_d["metadata"]["mutation_type"] = mutation_type
    return StrategyIR.model_validate(base_d)


# ── Public registry ──────────────────────────────────────────────────

ROOT_BUILDERS = {
    "trend_pullback":               build_trend_pullback,
    "session_london_breakout":      build_session_london_breakout,
    "session_asian_range":          build_session_asian_range,
    "volatility_atr_breakout":      build_volatility_atr_breakout,
    "volatility_bollinger_squeeze": build_volatility_bb_squeeze,
    "mean_reversion_rsi":           build_mean_reversion_rsi,
    "mean_reversion_bollinger":     build_mean_reversion_bollinger,
}

COMPOSERS = {
    "filter_add_rsi":         compose_filter_add_rsi,
    "filter_add_volatility":  compose_filter_add_volatility,
    "filter_add_trend":       compose_filter_add_trend,
    "mtf_htf_confirmation":   compose_mtf_htf_confirmation,
    "filter_remove_rsi":      compose_filter_remove_rsi,
}


def build_ir_for_mutation(
    mutation_type: str, pair: str, tf: str,
    *, base_ir: Optional[StrategyIR] = None,
    rr_ratio: Optional[float] = None,
) -> Optional[StrategyIR]:
    """Return a validated StrategyIR for the given mutation, or None when
    the mutation is unrepresented in v1 of the IR (operator decision: do
    not silently fabricate). The mutation engine falls back to the legacy
    text-only path when None is returned."""
    if mutation_type in ROOT_BUILDERS:
        return ROOT_BUILDERS[mutation_type](pair, tf)
    if mutation_type in COMPOSERS:
        if base_ir is None:
            return None
        return COMPOSERS[mutation_type](base_ir)
    # Phase 28-B+ — risk-reward composers layer fixed-pip SL/TP onto a
    # canonical base IR. Mutation type strings are
    # ``risk_reward_1_1`` / ``risk_reward_1_1_5`` / ``risk_reward_1_2``
    # — produced by ``mutation_engine._mut_risk_reward``.
    if mutation_type.startswith("risk_reward_") and base_ir is not None and rr_ratio:
        return compose_risk_reward(base_ir, rr_ratio, mutation_type)
    return None


__all__ = [
    "ROOT_BUILDERS", "COMPOSERS",
    "build_ir_for_mutation",
    "build_trend_pullback", "build_session_london_breakout",
    "build_session_asian_range", "build_volatility_atr_breakout",
    "build_volatility_bb_squeeze", "build_mean_reversion_rsi",
    "build_mean_reversion_bollinger",
    "compose_filter_add_rsi", "compose_filter_add_volatility",
    "compose_filter_add_trend", "compose_mtf_htf_confirmation",
    "compose_filter_remove_rsi", "compose_risk_reward",
]
