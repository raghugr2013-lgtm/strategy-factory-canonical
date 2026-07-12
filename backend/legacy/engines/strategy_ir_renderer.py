"""Strategy-IR → human-readable text renderer.

Phase 28-A: ``strategy_text`` becomes a derived rendering of the IR, not
the source of truth. Read-only walk over a StrategyIR; never mutates
inputs; deterministic output for the same IR.

NOT a transpiler. No code emission. No backtest interaction.
"""
from __future__ import annotations

from typing import Any

from engines.strategy_ir import StrategyIR


def _op_name(ind_kind: str, period: int | None = None) -> str:
    if period is not None:
        return f"{ind_kind}({period})"
    return ind_kind


def _operand(arg: Any, declared: dict) -> str:
    if isinstance(arg, dict):
        if "ref" in arg:
            ind = declared.get(arg["ref"], {})
            kind = ind.get("kind") or "?"
            p = (ind.get("params") or {}).get("period")
            return _op_name(kind, p)
        if "const" in arg:
            v = arg["const"]
            return f"{v:g}"
        if "price" in arg:
            off = arg.get("bar_offset", 0)
            suffix = "" if off == 0 else f"[-{off}]"
            return f"{arg['price']}{suffix}"
        if "op" in arg:
            return _predicate(arg, declared)
    return repr(arg)


def _predicate(p: dict, declared: dict) -> str:
    op = p["op"]
    args = p.get("args") or []
    extras = {k: v for k, v in p.items() if k not in ("op", "args")}

    if op == "AND":
        return "(" + " AND ".join(_predicate(a, declared) for a in args) + ")"
    if op == "OR":
        return "(" + " OR ".join(_predicate(a, declared) for a in args) + ")"
    if op == "NOT":
        return f"NOT {_predicate(args[0], declared)}"
    if op in ("GT", "LT", "GE", "LE", "EQ", "NEQ"):
        symbol = {"GT": ">", "LT": "<", "GE": ">=", "LE": "<=",
                  "EQ": "==", "NEQ": "!="}[op]
        return f"{_operand(args[0], declared)} {symbol} {_operand(args[1], declared)}"
    if op == "CROSS_UP":
        return f"{_operand(args[0], declared)} crosses ABOVE {_operand(args[1], declared)}"
    if op == "CROSS_DOWN":
        return f"{_operand(args[0], declared)} crosses BELOW {_operand(args[1], declared)}"
    if op == "RANGE_BREAK_UP":
        return (f"close breaks ABOVE [{extras['window_start_gmt']}–"
                f"{extras['window_end_gmt']} GMT] range high")
    if op == "RANGE_BREAK_DOWN":
        return (f"close breaks BELOW [{extras['window_start_gmt']}–"
                f"{extras['window_end_gmt']} GMT] range low")
    if op in ("AT_TIME", "IN_GMT_WINDOW"):
        return f"time in [{extras['after']}–{extras['before']} GMT]"
    if op == "BAND_TOUCH_UPPER":
        return f"high touches upper {extras['indicator']} band"
    if op == "BAND_TOUCH_LOWER":
        return f"low touches lower {extras['indicator']} band"
    if op == "BAND_BREAK_UPPER":
        return f"close breaks ABOVE upper {extras['indicator']} band"
    if op == "BAND_BREAK_LOWER":
        return f"close breaks BELOW lower {extras['indicator']} band"
    if op == "ATR_RATIO_ABOVE":
        return (f"ATR / SMA(ATR, {extras['baseline_period']}) "
                f">= {extras['min_ratio']}")
    if op == "HTF_SLOPE_UP":
        return f"HTF {extras['htf_ema_fast']} > {extras['htf_ema_slow']} (rising)"
    if op == "HTF_SLOPE_DOWN":
        return f"HTF {extras['htf_ema_fast']} < {extras['htf_ema_slow']} (falling)"
    if op == "BB_SQUEEZE_PERCENTILE":
        return (f"{extras['indicator']} bandwidth in bottom "
                f"{extras['percentile']}% of last {extras['lookback']} bars")
    return f"<{op}>"


def _render_exit(exit_block: dict) -> str:
    sl = exit_block.get("stop_loss") or {}
    tp = exit_block.get("take_profit") or {}
    parts = []
    sl_kind = sl.get("kind")
    if sl_kind == "pips":
        parts.append(f"SL = {sl['pips']:g} pips")
    elif sl_kind == "atr_mult":
        parts.append(f"SL = ATR × {sl['mult']:g}")
    elif sl_kind == "range_fraction":
        parts.append(f"SL = {sl['ratio']:g} × session range")
    elif sl_kind == "band_mid":
        parts.append(f"SL = {sl['indicator']} middle band")

    tp_kind = tp.get("kind")
    if tp_kind == "pips":
        parts.append(f"TP = {tp['pips']:g} pips")
    elif tp_kind == "atr_mult":
        parts.append(f"TP = ATR × {tp['mult']:g}")
    elif tp_kind == "range_fraction":
        parts.append(f"TP = {tp['ratio']:g} × session range")
    elif tp_kind == "band_mid":
        parts.append(f"TP = {tp['indicator']} middle band")
    elif tp_kind == "indicator_cross":
        parts.append(f"TP = exit when {tp['indicator']} crosses {tp['level']:g}")

    if exit_block.get("time_exit"):
        parts.append(f"Close-all at {exit_block['time_exit']['close_all_gmt']} GMT")
    if exit_block.get("reverse_exit"):
        parts.append("Exit on reverse signal")
    return "  |  ".join(parts)


def render_ir_to_text(ir: dict | StrategyIR) -> str:
    """Render a StrategyIR (or dict equivalent) as multi-line, human-
    readable text. Output is deterministic and side-effect-free."""
    if isinstance(ir, StrategyIR):
        ir_dict = ir.model_dump()
    elif isinstance(ir, dict):
        ir_dict = ir
    else:
        raise TypeError("render_ir_to_text expects StrategyIR or dict")

    md = ir_dict.get("metadata") or {}
    declared = {ind["id"]: ind for ind in (ir_dict.get("indicators") or [])}

    lines = []
    name = md.get("name") or "Untitled Strategy"
    pair = md.get("pair") or "—"
    tf = md.get("timeframe") or "—"
    lines.append(f"STRATEGY: {name} ({pair} {tf})")
    lines.append("")

    if ir_dict.get("session_filter"):
        sf = ir_dict["session_filter"]
        s = f"SESSION FILTER: trade only between {sf['open']}–{sf['close']} GMT"
        if sf.get("force_flat_at"):
            s += f"; force-flat at {sf['force_flat_at']} GMT"
        lines.append(s)

    if ir_dict.get("volatility_filter"):
        vf = ir_dict["volatility_filter"]
        lines.append(
            f"VOLATILITY FILTER: ATR / SMA(ATR, {vf['baseline_period']}) "
            f">= {vf['min_ratio']:g}"
        )

    lines.append(f"ENTRY LONG:  {_predicate(ir_dict['entry_long'], declared)}")
    lines.append(f"ENTRY SHORT: {_predicate(ir_dict['entry_short'], declared)}")
    lines.append(f"EXIT:        {_render_exit(ir_dict['exit'])}")

    risk = ir_dict.get("risk") or {}
    if risk:
        lines.append(
            f"RISK:        {risk.get('percent', 1.0):g}% per trade; "
            f"max {risk.get('max_concurrent_positions', 1)} concurrent; "
            f"max spread {risk.get('max_spread_pips', 3.0):g} pips"
        )

    if declared:
        ind_summaries = []
        for ind in declared.values():
            params = ind.get("params") or {}
            if ind["kind"] == "BOLLINGER":
                ind_summaries.append(
                    f"{ind['id']}=BB({params.get('period', 20)}, "
                    f"{params.get('std_dev', 2.0):g})"
                )
            elif ind["kind"] == "HTF_EMA":
                ind_summaries.append(
                    f"{ind['id']}={params.get('htf', '?')}-EMA({params.get('period', '?')})"
                )
            else:
                ind_summaries.append(
                    f"{ind['id']}={ind['kind']}({params.get('period', '?')})"
                )
        lines.append("INDICATORS:  " + ", ".join(ind_summaries))

    return "\n".join(lines)


__all__ = ["render_ir_to_text"]
