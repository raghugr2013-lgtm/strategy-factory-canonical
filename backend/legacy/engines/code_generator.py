"""
Phase 12 — Template-based cTrader cBot code generator.

No LLM / free-text generation. The bot is assembled from a fixed C# template
with five placeholder slots that are filled from the strategy's extracted
parameters and indicators:

    {{BOT_NAME}}       — sanitised algo class name
    {{PARAMETERS}}     — [Parameter(...)] attribute block
    {{INDICATORS}}     — OnStart() indicator initialisation
    {{ENTRY_LOGIC}}    — OnBar() buy/sell conditions + ExecuteMarketOrder
    {{EXIT_LOGIC}}     — OnTick() / OnBar() SL/TP management

Public API:
    generate_code(strategy_profile) -> {"code": str, "placeholders_filled": [...],
                                        "bot_name": str, "indicators_used": [...]}

Indicator mapping to cTrader:
    EMA  → Indicators.ExponentialMovingAverage(source, period)
    SMA  → Indicators.SimpleMovingAverage(source, period)
    RSI  → Indicators.RelativeStrengthIndex(source, period)
    ATR  → Indicators.AverageTrueRange(period, MovingAverageType.Simple)
"""
from __future__ import annotations

import re


# ── Template (fixed, no free-text) ────────────────────────────────────

CBOT_TEMPLATE = '''using System;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class {{BOT_NAME}} : Robot
    {
{{PARAMETERS}}

{{INDICATORS_DECL}}

        protected override void OnStart()
        {
{{INDICATORS}}
        }

        protected override void OnBar()
        {
            if (Positions.Find("{{BOT_NAME}}", SymbolName) != null)
                return;

{{ENTRY_LOGIC}}
        }

        protected override void OnTick()
        {
{{EXIT_LOGIC}}
        }
    }
}
'''


# ── Parameter block builder ───────────────────────────────────────────

def _fmt_num(v, is_int=False):
    if v is None:
        return "0"
    if is_int:
        return str(int(v))
    return f"{float(v):g}"


def build_parameters_block(params: dict) -> str:
    """Return the [Parameter(...)] attribute block for the cBot class."""
    fast = int(params.get("fast_period") or 9)
    slow = int(params.get("slow_period") or 21)
    rsi_p = int(params.get("rsi_period") or 14)
    sl = int(params.get("sl_pips") or 20)
    tp = int(params.get("tp_pips") or 40)
    risk = float(params.get("risk_percent") or 1.0)

    lines = [
        f'        [Parameter("Fast EMA Period", DefaultValue = {fast}, MinValue = 2)]',
        '        public int FastPeriod { get; set; }',
        '',
        f'        [Parameter("Slow EMA Period", DefaultValue = {slow}, MinValue = 3)]',
        '        public int SlowPeriod { get; set; }',
        '',
        f'        [Parameter("RSI Period", DefaultValue = {rsi_p}, MinValue = 2)]',
        '        public int RsiPeriod { get; set; }',
        '',
        f'        [Parameter("Stop Loss (pips)", DefaultValue = {sl}, MinValue = 1)]',
        '        public int StopLossPips { get; set; }',
        '',
        f'        [Parameter("Take Profit (pips)", DefaultValue = {tp}, MinValue = 1)]',
        '        public int TakeProfitPips { get; set; }',
        '',
        f'        [Parameter("Risk Percent", DefaultValue = {_fmt_num(risk)}, MinValue = 0.1, MaxValue = 10)]',
        '        public double RiskPercent { get; set; }',
    ]
    return "\n".join(lines)


# ── Indicator mapping + declarations ──────────────────────────────────

def _indicator_decls(indicators: dict) -> str:
    decls = []
    inds = set(_normalize_indicators(indicators))
    if "ema_fast" in inds:
        decls.append("        private ExponentialMovingAverage _emaFast;")
    if "ema_slow" in inds:
        decls.append("        private ExponentialMovingAverage _emaSlow;")
    if "sma" in inds:
        decls.append("        private SimpleMovingAverage _sma;")
    if "rsi" in inds:
        decls.append("        private RelativeStrengthIndex _rsi;")
    if "atr" in inds:
        decls.append("        private AverageTrueRange _atr;")
    return "\n".join(decls) if decls else "        // (no indicators)"


def _indicator_init(indicators: dict) -> str:
    lines = []
    inds = set(_normalize_indicators(indicators))
    if "ema_fast" in inds:
        lines.append("            _emaFast = Indicators.ExponentialMovingAverage(Bars.ClosePrices, FastPeriod);")
    if "ema_slow" in inds:
        lines.append("            _emaSlow = Indicators.ExponentialMovingAverage(Bars.ClosePrices, SlowPeriod);")
    if "sma" in inds:
        lines.append("            _sma = Indicators.SimpleMovingAverage(Bars.ClosePrices, SlowPeriod);")
    if "rsi" in inds:
        lines.append("            _rsi = Indicators.RelativeStrengthIndex(Bars.ClosePrices, RsiPeriod);")
    if "atr" in inds:
        lines.append("            _atr = Indicators.AverageTrueRange(14, MovingAverageType.Simple);")
    return "\n".join(lines) if lines else "            // (no indicators)"


def _normalize_indicators(indicators) -> list[str]:
    """
    Accept a dict like {"ema_fast": true, "rsi": true} OR a list ["EMA","RSI"]
    OR a plain string. Return a canonical list of ids used by the builders.
    """
    if not indicators:
        return ["ema_fast", "ema_slow"]
    out: list[str] = []
    if isinstance(indicators, dict):
        for k, v in indicators.items():
            if v:
                out.append(str(k).lower())
    elif isinstance(indicators, (list, tuple, set)):
        for v in indicators:
            out.append(str(v).lower())
    else:
        out = [str(indicators).lower()]
    # Map common aliases
    mapped = []
    for t in out:
        t = t.strip()
        if t in ("ema_fast", "emafast", "fast_ema", "fast"):
            mapped.append("ema_fast")
        elif t in ("ema_slow", "emaslow", "slow_ema", "slow"):
            mapped.append("ema_slow")
        elif t in ("ema",):
            mapped.extend(["ema_fast", "ema_slow"])
        elif t in ("sma", "moving_average", "ma"):
            mapped.append("sma")
        elif t in ("rsi", "relative_strength"):
            mapped.append("rsi")
        elif t in ("atr",):
            mapped.append("atr")
    return mapped or ["ema_fast", "ema_slow"]


# ── Entry / Exit logic blocks ─────────────────────────────────────────

def _entry_logic(strategy_type: str, indicators: dict) -> str:
    """
    Build entry conditions based on strategy type. Purely template-driven;
    no LLM involvement.
    """
    style = (strategy_type or "trend_following").lower()
    inds = set(_normalize_indicators(indicators))
    has_rsi = "rsi" in inds

    if style == "mean_reversion":
        long_cond  = "_rsi.Result.LastValue < 30" if has_rsi else "Bars.ClosePrices.Last(1) < _emaSlow.Result.Last(1)"
        short_cond = "_rsi.Result.LastValue > 70" if has_rsi else "Bars.ClosePrices.Last(1) > _emaSlow.Result.Last(1)"
    elif style == "breakout":
        long_cond  = "Bars.ClosePrices.Last(1) > _emaSlow.Result.Last(1) && Bars.HighPrices.Last(1) > Bars.HighPrices.Last(2)"
        short_cond = "Bars.ClosePrices.Last(1) < _emaSlow.Result.Last(1) && Bars.LowPrices.Last(1) < Bars.LowPrices.Last(2)"
    else:  # trend_following default
        long_cond  = "_emaFast.Result.Last(1) > _emaSlow.Result.Last(1)"
        short_cond = "_emaFast.Result.Last(1) < _emaSlow.Result.Last(1)"
        if has_rsi:
            long_cond  += " && _rsi.Result.LastValue > 50"
            short_cond += " && _rsi.Result.LastValue < 50"

    lines = [
        "            var volumeInUnits = Symbol.QuantityToVolumeInUnits(CalculateVolume());",
        "",
        f"            if ({long_cond})",
        "            {",
        '                ExecuteMarketOrder(TradeType.Buy, SymbolName, volumeInUnits,',
        '                    "{{BOT_NAME}}", StopLossPips, TakeProfitPips);',
        "            }",
        f"            else if ({short_cond})",
        "            {",
        '                ExecuteMarketOrder(TradeType.Sell, SymbolName, volumeInUnits,',
        '                    "{{BOT_NAME}}", StopLossPips, TakeProfitPips);',
        "            }",
    ]
    return "\n".join(lines)


def _exit_logic() -> str:
    # Built-in SL/TP are managed by ExecuteMarketOrder args (StopLossPips,
    # TakeProfitPips). OnTick is kept minimal as a hook for trailing logic.
    return (
        "            // SL/TP are set via ExecuteMarketOrder; nothing per-tick by default.\n"
        "            // Safety filters (if injected) will run here."
    )


# ── Helpers ───────────────────────────────────────────────────────────

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9]")


def sanitise_bot_name(pair: str, timeframe: str, style: str) -> str:
    parts = [
        _SAFE_NAME_RE.sub("", (pair or "Bot")),
        _SAFE_NAME_RE.sub("", (timeframe or "")),
        _SAFE_NAME_RE.sub("", (style or "")).title(),
    ]
    name = "".join(p for p in parts if p)
    if not name or not name[0].isalpha():
        name = "Bot" + name
    return name[:48] or "GeneratedBot"


def _calc_volume_helper() -> str:
    return (
        "\n        private long CalculateVolume()\n"
        "        {\n"
        "            double riskAmount = Account.Balance * (RiskPercent / 100.0);\n"
        "            double slDistance = StopLossPips * Symbol.PipValue;\n"
        "            if (slDistance <= 0) return Symbol.VolumeInUnitsMin;\n"
        "            double units = riskAmount / slDistance;\n"
        "            long stepped = (long)(Math.Floor(units / Symbol.VolumeInUnitsStep) * Symbol.VolumeInUnitsStep);\n"
        "            return Math.Max(Symbol.VolumeInUnitsMin, Math.Min(stepped, Symbol.VolumeInUnitsMax));\n"
        "        }\n"
    )


# ── Public: assemble the final code ───────────────────────────────────

def generate_code(strategy_profile: dict) -> dict:
    """
    Fill the template with placeholders derived from `strategy_profile`.
    Expected keys on input (all optional with safe defaults):
        pair, timeframe, style, strategy_type, parameters, indicators
    """
    pair = strategy_profile.get("pair", "EURUSD")
    timeframe = strategy_profile.get("timeframe", "H1")
    style = strategy_profile.get("style") or strategy_profile.get("strategy_type") or "trend_following"
    parameters = strategy_profile.get("parameters") or {}
    indicators = strategy_profile.get("indicators") or {}

    bot_name = sanitise_bot_name(pair, timeframe, style)

    code = CBOT_TEMPLATE
    code = code.replace("{{PARAMETERS}}", build_parameters_block(parameters))
    code = code.replace("{{INDICATORS_DECL}}", _indicator_decls(indicators))
    code = code.replace("{{INDICATORS}}", _indicator_init(indicators))
    code = code.replace("{{ENTRY_LOGIC}}", _entry_logic(style, indicators))
    code = code.replace("{{EXIT_LOGIC}}", _exit_logic())
    # BOT_NAME last — the entry-logic fragment also embeds {{BOT_NAME}}
    # as a position label, so replace across the whole assembled code.
    code = code.replace("{{BOT_NAME}}", bot_name)

    # Append the volume-sizing helper (still template-driven)
    code = code.rstrip() + "\n"
    # Insert helper right before final closing brace of the class: we rely on
    # a marker — find the last "        }" (end of OnTick) and then class end.
    # Simpler: inject before the first top-level "    }" (end of class).
    insert_at = code.rfind("    }\n}")
    if insert_at > 0:
        code = code[:insert_at] + _calc_volume_helper() + "    }\n}\n"

    return {
        "code": code,
        "bot_name": bot_name,
        "indicators_used": sorted(set(_normalize_indicators(indicators))),
        "placeholders_filled": [
            "{{BOT_NAME}}", "{{PARAMETERS}}", "{{INDICATORS_DECL}}",
            "{{INDICATORS}}", "{{ENTRY_LOGIC}}", "{{EXIT_LOGIC}}",
        ],
    }
