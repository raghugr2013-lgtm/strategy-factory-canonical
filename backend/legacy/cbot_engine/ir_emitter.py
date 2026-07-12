"""Phase 28-C — per-operator C# emitters + IR walker.

The emitter is intentionally narrow: one Python function per IR
operator, each returning a C# boolean expression string. The walker
composes them recursively. Composition NEVER touches raw strings
outside these functions.

Unsupported operators raise ``UnsupportedIROperatorError`` — honest
refusal is preferable to semantic corruption (operator directive #7).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from cbot_engine import ir_templates as T

# ── Supported vocabulary (anything outside this fails loudly) ──────
SUPPORTED_OPERATORS = frozenset({
    "AND", "OR", "NOT",
    "GT", "LT", "GE", "LE", "EQ", "NEQ",
    "CROSS_UP", "CROSS_DOWN",
    "RANGE_BREAK_UP", "RANGE_BREAK_DOWN",
    "AT_TIME", "IN_GMT_WINDOW",
    "BAND_TOUCH_UPPER", "BAND_TOUCH_LOWER",
    "BAND_BREAK_UPPER", "BAND_BREAK_LOWER",
    "ATR_RATIO_ABOVE",
    "HTF_SLOPE_UP", "HTF_SLOPE_DOWN",
    "BB_SQUEEZE_PERCENTILE",
})

SUPPORTED_INDICATORS = frozenset({"EMA", "RSI", "ATR", "BOLLINGER", "HTF_EMA"})

SUPPORTED_SL_KINDS = frozenset({"pips", "atr_mult", "range_fraction", "band_mid"})
SUPPORTED_TP_KINDS = frozenset({
    "pips", "atr_mult", "range_fraction", "band_mid", "indicator_cross",
})

_COMPARE_C_OP = {"GT": ">", "LT": "<", "GE": ">=", "LE": "<=",
                  "EQ": "==", "NEQ": "!="}

# Map IR HTF-string → cAlgo TimeFrame token. Restricted to the set
# the IR htf resolver produces.
_HTF_TO_CALGO_TIMEFRAME = {
    "M1": "TimeFrame.Minute",
    "M5": "TimeFrame.Minute5",
    "M15": "TimeFrame.Minute15",
    "M30": "TimeFrame.Minute30",
    "H1": "TimeFrame.Hour",
    "H4": "TimeFrame.Hour4",
    "D1": "TimeFrame.Daily",
    "W1": "TimeFrame.Weekly",
}


# ── Custom error ───────────────────────────────────────────────────


class UnsupportedIROperatorError(Exception):
    """Raised when the IR contains an operator / indicator / exit kind
    outside the transpiler's stable vocabulary. Loud refusal — never
    silently emit a placeholder."""


# ── Operand resolution → C# expression ─────────────────────────────


def _csharp_field_name(iid: str) -> str:
    """IR id → C# private field name. IR ids are validated by Pydantic
    so they're safe identifiers; we just prefix with ``_``."""
    return f"_{iid}"


def _indicator_csharp_series(ind: dict, bar_offset: int) -> str:
    """Return the C# expression for the indicator's value at offset
    ``bar_offset`` (0=current/forming; signal logic always uses ≥1)."""
    kind = ind["kind"]
    field = _csharp_field_name(ind["id"])
    last = 1 + bar_offset                   # i ↔ Last(1), i-1 ↔ Last(2)
    if kind == "EMA":
        return f"{field}.Result.Last({last})"
    if kind == "RSI":
        return f"{field}.Result.Last({last})"
    if kind == "ATR":
        return f"{field}.Result.Last({last})"
    if kind == "HTF_EMA":
        return f"{field}.Result.Last({last})"
    if kind == "BOLLINGER":
        # BB referenced as an operand directly is unusual — we expose
        # the .Main series. The band-specific predicates use their own
        # emitters and skip this path.
        return f"{field}.Main.Last({last})"
    raise UnsupportedIROperatorError(
        f"Indicator kind '{kind}' is not in the v1 transpiler vocabulary."
    )


def _emit_operand(op: Any, indicators_by_id: Dict[str, dict],
                  bar_offset: int = 0) -> str:
    if not isinstance(op, dict):
        raise UnsupportedIROperatorError(
            f"Operand must be a dict; got {type(op).__name__}: {op!r}"
        )
    if "ref" in op:
        ind = indicators_by_id.get(op["ref"])
        if ind is None:
            raise UnsupportedIROperatorError(
                f"Operand references undeclared indicator id '{op['ref']}'"
            )
        return _indicator_csharp_series(ind, bar_offset)
    if "const" in op:
        v = float(op["const"])
        # Render integer constants as such for cleaner C#.
        if v == int(v):
            return f"{int(v)}.0"
        return f"{v}"
    if "price" in op:
        stream_map = {
            "open": "Bars.OpenPrices",
            "high": "Bars.HighPrices",
            "low": "Bars.LowPrices",
            "close": "Bars.ClosePrices",
        }
        stream = stream_map.get(op["price"])
        if stream is None:
            raise UnsupportedIROperatorError(
                f"Operand price stream '{op['price']}' is unsupported"
            )
        ir_offset = int(op.get("bar_offset", 0))
        # Combine the predicate-level offset (now/prev) with the
        # operand-level bar_offset stored in the IR.
        last = 1 + bar_offset + ir_offset
        return f"{stream}.Last({last})"
    raise UnsupportedIROperatorError(f"Unrecognised operand shape: {op!r}")


# ── Predicate walker ────────────────────────────────────────────────


def _emit_predicate(node: Any, indicators_by_id: Dict[str, dict],
                    helpers_used: set, bar_offset: int = 0) -> str:
    if not isinstance(node, dict):
        raise UnsupportedIROperatorError(
            f"Predicate node must be a dict; got {type(node).__name__}"
        )
    op = node.get("op")
    if op is None or op not in SUPPORTED_OPERATORS:
        raise UnsupportedIROperatorError(
            f"Operator '{op}' is not in the v1 transpiler vocabulary."
        )
    args = node.get("args") or []

    if op == "AND":
        parts = [_emit_predicate(a, indicators_by_id, helpers_used, bar_offset)
                 for a in args]
        return T.OP_AND.format(args=" && ".join(parts))
    if op == "OR":
        parts = [_emit_predicate(a, indicators_by_id, helpers_used, bar_offset)
                 for a in args]
        return T.OP_OR.format(args=" || ".join(parts))
    if op == "NOT":
        return T.OP_NOT.format(
            inner=_emit_predicate(args[0], indicators_by_id, helpers_used, bar_offset)
        )

    if op in _COMPARE_C_OP:
        a = _emit_operand(args[0], indicators_by_id, bar_offset)
        b = _emit_operand(args[1], indicators_by_id, bar_offset)
        return T.OP_COMPARE.format(a=a, op=_COMPARE_C_OP[op], b=b)

    if op in ("CROSS_UP", "CROSS_DOWN"):
        a_now = _emit_operand(args[0], indicators_by_id, bar_offset)
        b_now = _emit_operand(args[1], indicators_by_id, bar_offset)
        a_prev = _emit_operand(args[0], indicators_by_id, bar_offset + 1)
        b_prev = _emit_operand(args[1], indicators_by_id, bar_offset + 1)
        tmpl = T.OP_CROSS_UP if op == "CROSS_UP" else T.OP_CROSS_DOWN
        return tmpl.format(a_now=a_now, b_now=b_now,
                            a_prev=a_prev, b_prev=b_prev)

    if op in ("BAND_TOUCH_UPPER", "BAND_TOUCH_LOWER",
              "BAND_BREAK_UPPER", "BAND_BREAK_LOWER"):
        band_id = node["indicator"]
        if band_id not in indicators_by_id or indicators_by_id[band_id]["kind"] != "BOLLINGER":
            raise UnsupportedIROperatorError(
                f"{op} references non-Bollinger indicator '{band_id}'"
            )
        field = _csharp_field_name(band_id)
        tmpl = {
            "BAND_TOUCH_UPPER": T.OP_BAND_TOUCH_UPPER,
            "BAND_TOUCH_LOWER": T.OP_BAND_TOUCH_LOWER,
            "BAND_BREAK_UPPER": T.OP_BAND_BREAK_UPPER,
            "BAND_BREAK_LOWER": T.OP_BAND_BREAK_LOWER,
        }[op]
        return tmpl.format(band=field)

    if op == "ATR_RATIO_ABOVE":
        helpers_used.add("ATR_RATIO")
        atr_id = node["indicator"]
        if atr_id not in indicators_by_id or indicators_by_id[atr_id]["kind"] != "ATR":
            raise UnsupportedIROperatorError(
                f"ATR_RATIO_ABOVE references non-ATR indicator '{atr_id}'"
            )
        return T.OP_ATR_RATIO_ABOVE.format(
            atr=_csharp_field_name(atr_id),
            baseline=int(node["baseline_period"]),
            min_ratio=float(node["min_ratio"]),
        )

    if op in ("HTF_SLOPE_UP", "HTF_SLOPE_DOWN"):
        fast_id = node["htf_ema_fast"]
        slow_id = node["htf_ema_slow"]
        for iid in (fast_id, slow_id):
            ind = indicators_by_id.get(iid)
            if ind is None or ind["kind"] != "HTF_EMA":
                raise UnsupportedIROperatorError(
                    f"{op} references non-HTF_EMA indicator '{iid}'"
                )
        tmpl = T.OP_HTF_SLOPE_UP if op == "HTF_SLOPE_UP" else T.OP_HTF_SLOPE_DOWN
        return tmpl.format(fast=_csharp_field_name(fast_id),
                            slow=_csharp_field_name(slow_id))

    if op == "BB_SQUEEZE_PERCENTILE":
        helpers_used.add("BB_SQUEEZE")
        band_id = node["indicator"]
        return T.OP_BB_SQUEEZE.format(
            band=_csharp_field_name(band_id),
            lookback=int(node["lookback"]),
            percentile=float(node["percentile"]),
        )

    if op in ("RANGE_BREAK_UP", "RANGE_BREAK_DOWN"):
        helpers_used.add("SESSION_RANGE")
        s_h, s_m = (int(x) for x in node["window_start_gmt"].split(":"))
        e_h, e_m = (int(x) for x in node["window_end_gmt"].split(":"))
        tmpl = T.OP_RANGE_BREAK_UP if op == "RANGE_BREAK_UP" else T.OP_RANGE_BREAK_DOWN
        return tmpl.format(start_h=s_h, start_m=s_m, end_h=e_h, end_m=e_m)

    if op in ("AT_TIME", "IN_GMT_WINDOW"):
        helpers_used.add("IN_GMT_WINDOW")
        a_h, a_m = (int(x) for x in node["after"].split(":"))
        b_h, b_m = (int(x) for x in node["before"].split(":"))
        return T.OP_IN_GMT_WINDOW.format(
            after_h=a_h, after_m=a_m, before_h=b_h, before_m=b_m,
        )

    raise UnsupportedIROperatorError(
        f"Operator '{op}' has no emitter (internal coverage gap)."
    )


# ── Coverage walk (used by parity simulator's "fail-loud" check) ────


def collect_operators_and_indicators(ir: dict) -> Tuple[set, set, set, set]:
    """Walk the IR; return (operators_used, indicator_kinds_used,
    sl_kinds_used, tp_kinds_used). Used to verify v1 coverage before
    any C# is emitted — supports honest refusal on unsupported IR."""
    ops: set = set()
    kinds: set = set()

    def _walk_pred(n):
        if not isinstance(n, dict):
            return
        op = n.get("op")
        if op:
            ops.add(op)
        for a in (n.get("args") or []):
            if isinstance(a, dict):
                _walk_pred(a)

    for ind in ir.get("indicators") or []:
        if isinstance(ind, dict):
            kinds.add(ind.get("kind"))

    _walk_pred(ir.get("entry_long") or {})
    _walk_pred(ir.get("entry_short") or {})

    sl_kinds = set()
    tp_kinds = set()
    ex = ir.get("exit") or {}
    if isinstance(ex.get("stop_loss"), dict):
        sl_kinds.add(ex["stop_loss"].get("kind"))
    if isinstance(ex.get("take_profit"), dict):
        tp_kinds.add(ex["take_profit"].get("kind"))
    return ops, kinds, sl_kinds, tp_kinds


# ── Indicator declarations + initialisations ───────────────────────


def emit_indicator_fields_and_init(
    indicators: List[dict],
    htf_param_map: Dict[str, str],
) -> Tuple[str, str, str]:
    """Return (field_decls, htf_fields, init_body) C# fragments.

    HTF_EMA indicators reference a per-HTF ``Bars`` field (declared
    once per distinct HTF). Initialised via ``MarketData.GetBars`` in
    ``OnStart``.
    """
    declared_htfs: List[str] = []
    field_lines: List[str] = []
    htf_field_lines: List[str] = []
    init_lines: List[str] = []
    for ind in indicators:
        kind = ind["kind"]
        iid = ind["id"]
        field = _csharp_field_name(iid)
        params = ind.get("params") or {}
        if kind == "EMA":
            field_lines.append(f"        private ExponentialMovingAverage {field};")
            period = int(params["period"])
            init_lines.append(
                f"            {field} = Indicators.ExponentialMovingAverage(Bars.ClosePrices, {period});"
            )
        elif kind == "RSI":
            field_lines.append(f"        private RelativeStrengthIndex {field};")
            period = int(params.get("period", 14))
            init_lines.append(
                f"            {field} = Indicators.RelativeStrengthIndex(Bars.ClosePrices, {period});"
            )
        elif kind == "ATR":
            field_lines.append(f"        private AverageTrueRange {field};")
            period = int(params.get("period", 14))
            init_lines.append(
                f"            {field} = Indicators.AverageTrueRange({period}, MovingAverageType.Simple);"
            )
        elif kind == "BOLLINGER":
            field_lines.append(f"        private BollingerBands {field};")
            period = int(params.get("period", 20))
            std = float(params.get("std_dev", 2.0))
            init_lines.append(
                f"            {field} = Indicators.BollingerBands(Bars.ClosePrices, {period}, {std}, MovingAverageType.Simple);"
            )
        elif kind == "HTF_EMA":
            htf = params["htf"]
            if htf not in _HTF_TO_CALGO_TIMEFRAME:
                raise UnsupportedIROperatorError(
                    f"HTF '{htf}' has no cAlgo TimeFrame mapping."
                )
            htf_bars_field = f"_bars_{htf.lower()}"
            if htf not in declared_htfs:
                declared_htfs.append(htf)
                htf_field_lines.append(f"        private Bars {htf_bars_field};")
                init_lines.append(
                    f"            {htf_bars_field} = MarketData.GetBars({_HTF_TO_CALGO_TIMEFRAME[htf]});"
                )
            field_lines.append(f"        private ExponentialMovingAverage {field};")
            period = int(params["period"])
            init_lines.append(
                f"            {field} = Indicators.ExponentialMovingAverage({htf_bars_field}.ClosePrices, {period});"
            )
        else:
            raise UnsupportedIROperatorError(
                f"Indicator kind '{kind}' is not in the v1 transpiler vocabulary."
            )

    return ("\n".join(field_lines), "\n".join(htf_field_lines),
            "\n".join(init_lines))


# ── Exit logic emission ────────────────────────────────────────────


def emit_exit_logic(
    ir: dict, indicators_by_id: Dict[str, dict], helpers_used: set,
) -> Tuple[str, str, str, str]:
    """Return (sl_pips_expr, tp_pips_expr, indicator_exits_body,
    force_flat_body) — used by the scaffold.

    Pip-based and ATR-mult exits flow into SL/TP at entry time.
    Band-mid and indicator-cross exits flow into a bar-checked
    ``ManageExits`` body. ``time_exit.close_all_gmt`` becomes a
    force-flat check that runs before any entry on each bar.
    """
    ex = ir.get("exit") or {}
    sl = ex.get("stop_loss") or {}
    tp = ex.get("take_profit") or {}

    sl_kind = sl.get("kind")
    tp_kind = tp.get("kind")
    if sl_kind not in SUPPORTED_SL_KINDS:
        raise UnsupportedIROperatorError(
            f"Exit stop_loss kind '{sl_kind}' is not in the v1 transpiler vocabulary."
        )
    if tp_kind not in SUPPORTED_TP_KINDS:
        raise UnsupportedIROperatorError(
            f"Exit take_profit kind '{tp_kind}' is not in the v1 transpiler vocabulary."
        )

    def _pip_expr(spec: dict) -> str:
        k = spec["kind"]
        if k == "pips":
            return f"{float(spec['pips'])}"
        if k == "atr_mult":
            iid = spec["indicator"]
            field = _csharp_field_name(iid)
            mult = float(spec["mult"])
            return f"(({field}.Result.Last(1) / Symbol.PipSize) * {mult})"
        if k == "range_fraction":
            helpers_used.add("SESSION_RANGE")
            s_h, s_m = (int(x) for x in spec["window_start_gmt"].split(":"))
            e_h, e_m = (int(x) for x in spec["window_end_gmt"].split(":"))
            ratio = float(spec["ratio"])
            return (f"(SessionRangePips({s_h}, {s_m}, {e_h}, {e_m}) * {ratio})")
        if k == "band_mid":
            # Bar-checked exit (not a fixed pip distance). Return 1.0
            # as a placeholder so ExecuteMarketOrder gets a finite SL
            # while the band-mid manager closes positions on band
            # cross.
            helpers_used.add("BAND_MID_SL")
            return "BandMidSlPips()"
        if k == "indicator_cross":
            # Same handling — flow into a bar-checked manager.
            return "9999.0"
        raise UnsupportedIROperatorError(f"Exit kind '{k}' unsupported.")

    # range_fraction helper emitter (pip version distinct from the
    # bool helper used by RANGE_BREAK_*).
    if sl_kind == "range_fraction" or tp_kind == "range_fraction":
        helpers_used.add("SESSION_RANGE_PIPS")

    sl_pips_expr = _pip_expr(sl)
    tp_pips_expr = _pip_expr(tp)

    # Bar-checked exits.
    exits_body: List[str] = []
    if tp_kind == "band_mid":
        band_id = tp["indicator"]
        field = _csharp_field_name(band_id)
        exits_body.append(f"""            foreach (var p in OwnedPositions())
            {{
                double mid = {field}.Main.Last(1);
                if (p.TradeType == TradeType.Buy && Bars.ClosePrices.Last(1) >= mid) ClosePosition(p);
                else if (p.TradeType == TradeType.Sell && Bars.ClosePrices.Last(1) <= mid) ClosePosition(p);
            }}""")
    if tp_kind == "indicator_cross":
        iid = tp["indicator"]
        level = float(tp["level"])
        field = _csharp_field_name(iid)
        exits_body.append(f"""            foreach (var p in OwnedPositions())
            {{
                double v = {field}.Result.Last(1);
                double vp = {field}.Result.Last(2);
                if (p.TradeType == TradeType.Buy  && vp < {level} && v >= {level}) ClosePosition(p);
                else if (p.TradeType == TradeType.Sell && vp > {level} && v <= {level}) ClosePosition(p);
            }}""")
    if sl_kind == "band_mid":
        band_id = sl["indicator"]
        field = _csharp_field_name(band_id)
        exits_body.append(f"""            foreach (var p in OwnedPositions())
            {{
                double mid = {field}.Main.Last(1);
                if (p.TradeType == TradeType.Buy  && Bars.ClosePrices.Last(1) <= mid) ClosePosition(p);
                else if (p.TradeType == TradeType.Sell && Bars.ClosePrices.Last(1) >= mid) ClosePosition(p);
            }}""")

    # Force-flat (time_exit) gate.
    force_flat = ex.get("time_exit") or {}
    force_flat_body = ""
    if force_flat.get("close_all_gmt"):
        helpers_used.add("IN_GMT_WINDOW")
        ff_h, ff_m = (int(x) for x in force_flat["close_all_gmt"].split(":"))
        force_flat_body = (
            f"            {{ DateTime _ft = Bars.OpenTimes.Last(1); "
            f"if (_ft.Hour * 60 + _ft.Minute >= {ff_h} * 60 + {ff_m}) CloseAllOwned(); }}"
        )

    return sl_pips_expr, tp_pips_expr, "\n".join(exits_body), force_flat_body


# ── Session / volatility gates ─────────────────────────────────────


def emit_session_body(ir: dict, helpers_used: set) -> str:
    sf = ir.get("session_filter")
    if not sf:
        return "            return true;"
    helpers_used.add("IN_GMT_WINDOW")
    o_h, o_m = (int(x) for x in sf["open"].split(":"))
    c_h, c_m = (int(x) for x in sf["close"].split(":"))
    return f"            return InGmtWindow({o_h}, {o_m}, {c_h}, {c_m});"


def emit_volatility_body(ir: dict, indicators_by_id: Dict[str, dict],
                          helpers_used: set) -> str:
    vf = ir.get("volatility_filter")
    if not vf:
        return "            return true;"
    helpers_used.add("ATR_RATIO")
    atr_id = vf["indicator"]
    if atr_id not in indicators_by_id or indicators_by_id[atr_id]["kind"] != "ATR":
        raise UnsupportedIROperatorError(
            f"volatility_filter references non-ATR indicator '{atr_id}'"
        )
    return (
        f"            return AtrRatioAbove({_csharp_field_name(atr_id)}, "
        f"{int(vf['baseline_period'])}, {float(vf['min_ratio'])});"
    )


# ── Parameter block ────────────────────────────────────────────────


def emit_parameters(ir: dict) -> str:
    """Universal parameter surface. Indicator periods/thresholds are
    semantic — hardcoded in C# from IR (operator-locked decision 28-C
    #6). Tunable execution surface only is exposed here."""
    risk = ir.get("risk") or {}
    lines = []
    lines.append(T.PARAM_DOUBLE.format(
        label="Risk Percent", name="RiskPercent",
        default=float(risk.get("percent", 1.0)),
        min=0.01, max=10.0,
    ))
    lines.append(T.PARAM_DOUBLE.format(
        label="Max Spread Pips", name="MaxSpreadPips",
        default=float(risk.get("max_spread_pips", 3.0)),
        min=0.1, max=50.0,
    ))
    lines.append(T.PARAM_INT.format(
        label="Max Concurrent Positions", name="MaxConcurrent",
        default=int(risk.get("max_concurrent_positions", 1)),
        min=1, max=10,
    ))
    return "".join(lines)


# ── Helper assembly ─────────────────────────────────────────────────


def emit_helpers(helpers_used: set) -> str:
    """Emit only the helpers referenced by the IR. Fixed order, fixed
    content → byte-identical output for identical inputs."""
    fragments: List[str] = []
    if "ATR_RATIO" in helpers_used:
        fragments.append(T.HELPER_ATR_RATIO)
    if "BB_SQUEEZE" in helpers_used:
        fragments.append(T.HELPER_BB_SQUEEZE)
    if "SESSION_RANGE" in helpers_used or "SESSION_RANGE_PIPS" in helpers_used:
        fragments.append(T.HELPER_SESSION_RANGE)
    if "SESSION_RANGE_PIPS" in helpers_used:
        fragments.append("""
        private double SessionRangePips(int sH, int sM, int eH, int eM)
        {
            double? hi = null; double? lo = null;
            DateTime today = Bars.OpenTimes.Last(1).Date;
            DateTime winStart = new DateTime(today.Year, today.Month, today.Day, sH, sM, 0, DateTimeKind.Utc);
            DateTime winEnd   = new DateTime(today.Year, today.Month, today.Day, eH, eM, 0, DateTimeKind.Utc);
            int scan = Math.Min(Bars.Count - 1, 500);
            for (int k = 1; k <= scan; k++)
            {
                DateTime t = Bars.OpenTimes.Last(k);
                if (t < winStart) break;
                if (t >= winStart && t < winEnd)
                {
                    double h = Bars.HighPrices.Last(k);
                    double l = Bars.LowPrices.Last(k);
                    hi = hi.HasValue ? Math.Max(hi.Value, h) : h;
                    lo = lo.HasValue ? Math.Min(lo.Value, l) : l;
                }
            }
            if (!hi.HasValue || !lo.HasValue) return 0.0;
            return (hi.Value - lo.Value) / Symbol.PipSize;
        }
""")
    if "IN_GMT_WINDOW" in helpers_used:
        fragments.append(T.HELPER_IN_GMT_WINDOW)
    if "BAND_MID_SL" in helpers_used:
        fragments.append("""
        private double BandMidSlPips() { return 9999.0; }
""")
    return "".join(fragments)
