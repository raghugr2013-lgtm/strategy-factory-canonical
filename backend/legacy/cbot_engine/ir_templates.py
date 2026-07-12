"""Phase 28-C — IR transpiler templates.

Hand-written C# scaffolds and per-operator expression templates.
Every C# token in a generated cBot originates here. No Jinja2, no
LLM, no external template engine.

Timing-semantic convention (first-class concern):
    Python interpreter      ↔  cAlgo cBot
    -----------------------    ----------------------------------
    bar index ``i``         ↔  ``Bars.ClosePrices.Last(1)``
                               (the just-closed bar at OnBar() time)
    bar index ``i - 1``     ↔  ``Bars.ClosePrices.Last(2)``
                               (the previous closed bar)

This is the canonical mapping used by every emitter. Mixing
``Last(0)`` (the currently-forming bar) into a signal expression
would create intrabar divergence; the transpiler must never emit
``Last(0)`` for signal logic.

HTF parity mode (documented divergence — operator-approved):
    Interpreter HTF EMA is a subsample-and-replay Python approximation.
    cBot HTF EMA uses ``MarketData.GetBars(htfTimeframe)`` — cTrader's
    real higher-timeframe feed. They will not match bit-for-bit on
    live cTrader. The generated cBot carries ``HTF_PARITY_MODE =
    APPROXIMATE`` metadata so this is loudly visible to operators.
"""
from __future__ import annotations

# Stable versioning — bump when the emission format changes.
TRANSPILER_VERSION = "1.1.0"

# ── cBot scaffold ────────────────────────────────────────────────────
# Placeholders are replaced by string formatting (str.format). Curly
# braces in actual C# code are doubled to escape them.
SCAFFOLD: str = """// ==================================================================
// AI Strategy Factory — cBot (deterministic IR transpiler)
// ------------------------------------------------------------------
// IR_VERSION             : {ir_version}
// TRANSPILER_VERSION     : {transpiler_version}
// STRATEGY_HASH          : {strategy_hash}
// GENERATED_AT           : {generated_at}
// HTF_PARITY_MODE        : {htf_parity_mode}
// PARITY_STATUS          : {parity_status}
// PARITY_FIXTURES_PASSED : {parity_fixtures_passed}
// ==================================================================
// MUTATION_TYPE          : {mutation_type}
// PAIR                   : {pair}
// TIMEFRAME              : {timeframe}
// ==================================================================

using System;
using System.Linq;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class {bot_name} : Robot
    {{
        // ── Parameters (tunable execution surface) ─────────────────
{parameters}

        // ── Diagnostics (P0.2) — structured Print per gated return ─
        [Parameter("Log verbosity (0=silent, 1=concise, 2=verbose)", DefaultValue = 1, MinValue = 0, MaxValue = 2)]
        public int LogVerbosity {{ get; set; }}

        // ── In-bot risk controls (P0.3) — duplicate critical protections locally ─
        [Parameter("Max daily loss % of starting equity (0 = disabled)", DefaultValue = 0.0, MinValue = 0.0, MaxValue = 100.0)]
        public double MaxDailyLossPct {{ get; set; }}

        [Parameter("Max consecutive losses before cooldown (0 = disabled)", DefaultValue = 0, MinValue = 0, MaxValue = 100)]
        public int MaxConsecutiveLosses {{ get; set; }}

        [Parameter("Cooldown bars after consecutive-loss trip", DefaultValue = 6, MinValue = 0, MaxValue = 1000)]
        public int CoolDownBars {{ get; set; }}

        [Parameter("Max trades per UTC day (0 = disabled)", DefaultValue = 0, MinValue = 0, MaxValue = 1000)]
        public int MaxTradesPerDay {{ get; set; }}

        [Parameter("Emergency trading halt (true = no new entries; existing positions remain)", DefaultValue = false)]
        public bool EmergencyHalt {{ get; set; }}

        // ── Indicator fields ───────────────────────────────────────
{indicator_fields}

        // ── HTF resources ──────────────────────────────────────────
{htf_fields}

        // ── Risk-control state (P0.3) ─────────────────────────────
        private int      _consecutiveLosses = 0;
        private int      _cooldownBarsLeft = 0;
        private int      _tradesToday = 0;
        private double   _dailyStartEquity = 0.0;
        private DateTime _dailyDate = DateTime.MinValue;
        private bool     _dailyLockout = false;

        private const string Label = "{bot_name}";

        protected override void OnStart()
        {{
{indicator_init}
            _dailyStartEquity = Account.Equity;
            _dailyDate = Server.Time.Date;
            Positions.Closed += OnPositionClosed_Internal;
            if (LogVerbosity >= 1) Print("[BotStart] label={{0}} pair={{1}} tf={{2}}", Label, SymbolName, TimeFrame);
        }}

        protected override void OnBar()
        {{
            // ── P0.3 · Daily rollover + risk controls ─────────────
            CheckDailyRollover();
            if (!RiskControlsOk()) return;

            // Force-flat (time_exit + force_flat_at) — runs before
            // any entry logic so a position is never carried past its
            // operator-declared boundary.
{force_flat_check}

            // Indicator-based exits (band_mid / indicator_cross) —
            // bar-checked because cAlgo's ExecuteMarketOrder only
            // accepts pip SL/TP.
{indicator_exits}

            // Entry preconditions (each gate logs WHY it skipped when
            // LogVerbosity >= 1 — P0.2 institutional diagnostics).
            if (!SessionOk()) {{ LogGate("session", "outside operator-declared GMT window"); return; }}
            double currentSpreadPips = Symbol.Spread / Symbol.PipSize;
            if (currentSpreadPips > MaxSpreadPips) {{ LogGate("spread", string.Format("spread={{0:F2}} > MaxSpreadPips={{1:F2}}", currentSpreadPips, MaxSpreadPips)); return; }}
            if (!VolatilityOk()) {{ LogGate("volatility", "VolatilityOk() returned false"); return; }}
            if (OwnedPositions().Length >= MaxConcurrent) {{ LogGate("max_concurrent", string.Format("owned={{0}} >= MaxConcurrent={{1}}", OwnedPositions().Length, MaxConcurrent)); return; }}

            // Entry signals
            if (EvalEntryLong())  TryEnter(TradeType.Buy);
            else if (EvalEntryShort()) TryEnter(TradeType.Sell);
        }}

        // ── Entry predicates ────────────────────────────────────────
        private bool EvalEntryLong()
        {{
            return {entry_long_expr};
        }}

        private bool EvalEntryShort()
        {{
            return {entry_short_expr};
        }}

        // ── Session / volatility / helpers ──────────────────────────
        private bool SessionOk()
        {{
{session_body}
        }}

        private bool VolatilityOk()
        {{
{volatility_body}
        }}

        private Position[] OwnedPositions()
        {{
            return Positions.FindAll(Label, SymbolName);
        }}

        private void TryEnter(TradeType type)
        {{
            double slPips = {sl_pips_expr};
            double tpPips = {tp_pips_expr};
            if (slPips <= 0 || tpPips <= 0) {{ LogGate("sl_tp_invalid", string.Format("slPips={{0}} tpPips={{1}}", slPips, tpPips)); return; }}

            double riskAmount = Account.Balance * (RiskPercent / 100.0);
            double pipValue = Symbol.PipValue;
            if (pipValue <= 0) {{ LogGate("symbol_metadata", "Symbol.PipValue <= 0 — broker metadata gap"); return; }}
            double rawVolume = riskAmount / (slPips * pipValue);
            long volume = (long)Symbol.NormalizeVolumeInUnits(rawVolume, RoundingMode.Down);
            if (volume < Symbol.VolumeInUnitsMin) {{ LogGate("volume_min", string.Format("volume={{0}} < VolumeInUnitsMin={{1}} (raw={{2:F2}})", volume, Symbol.VolumeInUnitsMin, rawVolume)); return; }}

            var result = ExecuteMarketOrder(type, SymbolName, volume, Label, slPips, tpPips);
            if (result != null && result.IsSuccessful)
            {{
                _tradesToday++;
                if (LogVerbosity >= 1) Print("[Entry] side={{0}} vol={{1}} slPips={{2:F1}} tpPips={{3:F1}} tradesToday={{4}}", type, volume, slPips, tpPips, _tradesToday);
            }}
            else if (LogVerbosity >= 1 && result != null)
            {{
                Print("[EntryFailed] side={{0}} error={{1}}", type, result.Error);
            }}
        }}

        private void CloseAllOwned()
        {{
            foreach (var p in OwnedPositions())
            {{
                ClosePosition(p);
            }}
        }}

        // ── P0.2 · Structured gate logging ───────────────────────────
        private void LogGate(string reason, string detail)
        {{
            if (LogVerbosity <= 0) return;
            if (LogVerbosity >= 2)
                Print("[Gate] reason={{0}} bar_time={{1:o}} spread_pips={{2:F2}} owned={{3}} {{4}}",
                      reason, Bars.OpenTimes.Last(1), Symbol.Spread / Symbol.PipSize,
                      OwnedPositions().Length, detail);
            else
                Print("[Gate] {{0}}: {{1}}", reason, detail);
        }}

        // ── P0.3 · Daily rollover + risk controls ───────────────────
        private void CheckDailyRollover()
        {{
            DateTime today = Server.Time.Date;
            if (today != _dailyDate)
            {{
                if (LogVerbosity >= 1)
                    Print("[DailyRollover] prev={{0:yyyy-MM-dd}} trades={{1}} losses_streak={{2}} new={{3:yyyy-MM-dd}}",
                          _dailyDate, _tradesToday, _consecutiveLosses, today);
                _dailyDate = today;
                _dailyStartEquity = Account.Equity;
                _tradesToday = 0;
                _dailyLockout = false;
                // Consecutive-loss streak persists across days deliberately
                // — a streak is a streak regardless of calendar boundary.
            }}
            if (_cooldownBarsLeft > 0) _cooldownBarsLeft--;
        }}

        private bool RiskControlsOk()
        {{
            if (EmergencyHalt) {{ LogGate("emergency_halt", "operator EmergencyHalt=true"); return false; }}
            if (_dailyLockout) {{ LogGate("daily_lockout", "daily loss/trade limit already breached today"); return false; }}
            if (_cooldownBarsLeft > 0) {{ LogGate("cooldown", string.Format("bars_left={{0}}", _cooldownBarsLeft)); return false; }}
            if (MaxTradesPerDay > 0 && _tradesToday >= MaxTradesPerDay) {{
                LogGate("max_trades_day", string.Format("tradesToday={{0}} >= MaxTradesPerDay={{1}}", _tradesToday, MaxTradesPerDay));
                _dailyLockout = true; return false;
            }}
            if (MaxDailyLossPct > 0 && _dailyStartEquity > 0)
            {{
                double dailyPnlPct = ((Account.Equity - _dailyStartEquity) / _dailyStartEquity) * 100.0;
                if (dailyPnlPct <= -MaxDailyLossPct)
                {{
                    LogGate("daily_loss_cutoff", string.Format("dailyPnl={{0:F2}}% <= -{{1}}%; closing all and locking out", dailyPnlPct, MaxDailyLossPct));
                    CloseAllOwned();
                    _dailyLockout = true;
                    return false;
                }}
            }}
            return true;
        }}

        private void OnPositionClosed_Internal(PositionClosedEventArgs args)
        {{
            var p = args.Position;
            if (p == null || p.Label != Label) return;
            if (p.NetProfit < 0) _consecutiveLosses++;
            else if (p.NetProfit > 0) _consecutiveLosses = 0;
            if (MaxConsecutiveLosses > 0 && _consecutiveLosses >= MaxConsecutiveLosses)
            {{
                _cooldownBarsLeft = Math.Max(_cooldownBarsLeft, CoolDownBars);
                if (LogVerbosity >= 1)
                    Print("[ConsecLossCutoff] streak={{0}} >= {{1}}; cooldown_bars={{2}}",
                          _consecutiveLosses, MaxConsecutiveLosses, _cooldownBarsLeft);
                _consecutiveLosses = 0;   // reset so the cooldown isn't re-armed every bar
            }}
        }}

{helpers}
    }}
}}
"""

# ── Operator templates (C# expression fragments) ─────────────────────
# Returned strings are SELF-CONTAINED boolean expressions. Composition
# is handled by the walker (ir_emitter._emit_predicate).

OP_AND: str = "({args})"               # joined by " && "
OP_OR: str = "({args})"                # joined by " || "
OP_NOT: str = "(!({inner}))"

OP_COMPARE: str = "(({a}) {op} ({b}))"  # op in {>, <, >=, <=, ==, !=}

OP_CROSS_UP: str = "(({a_now}) > ({b_now}) && ({a_prev}) <= ({b_prev}))"
OP_CROSS_DOWN: str = "(({a_now}) < ({b_now}) && ({a_prev}) >= ({b_prev}))"

OP_BAND_TOUCH_UPPER: str = "(Bars.HighPrices.Last(1) >= ({band}.Top.Last(1)))"
OP_BAND_TOUCH_LOWER: str = "(Bars.LowPrices.Last(1) <= ({band}.Bottom.Last(1)))"
OP_BAND_BREAK_UPPER: str = "(Bars.ClosePrices.Last(1) > ({band}.Top.Last(1)))"
OP_BAND_BREAK_LOWER: str = "(Bars.ClosePrices.Last(1) < ({band}.Bottom.Last(1)))"

OP_HTF_SLOPE_UP: str = "(({fast}.Result.Last(1)) > ({slow}.Result.Last(1)))"
OP_HTF_SLOPE_DOWN: str = "(({fast}.Result.Last(1)) < ({slow}.Result.Last(1)))"

OP_ATR_RATIO_ABOVE: str = (
    "(AtrRatioAbove({atr}, {baseline}, {min_ratio}))"
)

OP_BB_SQUEEZE: str = (
    "(BbSqueezePct({band}, {lookback}, {percentile}))"
)

OP_RANGE_BREAK_UP: str = (
    "(SessionRangeBreak({start_h}, {start_m}, {end_h}, {end_m}, true))"
)
OP_RANGE_BREAK_DOWN: str = (
    "(SessionRangeBreak({start_h}, {start_m}, {end_h}, {end_m}, false))"
)

OP_IN_GMT_WINDOW: str = (
    "(InGmtWindow({after_h}, {after_m}, {before_h}, {before_m}))"
)

# ── Reusable helper methods (emitted only when referenced) ───────────
# Each helper is a (name, body) tuple. The emitter selects the set
# needed by the IR and renders them deterministically in fixed order.
HELPER_ATR_RATIO: str = """
        private bool AtrRatioAbove(AverageTrueRange atr, int baseline, double minRatio)
        {
            if (atr.Result.Count < baseline + 1) return false;
            double sum = 0; int n = 0;
            for (int k = 1; k <= baseline; k++)
            {
                double v = atr.Result.Last(k);
                if (double.IsNaN(v)) return false;
                sum += v; n++;
            }
            if (n == 0) return false;
            double avg = sum / n;
            if (avg <= 0) return false;
            return (atr.Result.Last(1) / avg) >= minRatio;
        }
"""

HELPER_BB_SQUEEZE: str = """
        private bool BbSqueezePct(BollingerBands bb, int lookback, double percentile)
        {
            if (bb.Top.Count < lookback + 1) return false;
            double[] widths = new double[lookback];
            for (int k = 0; k < lookback; k++)
            {
                widths[k] = bb.Top.Last(k + 1) - bb.Bottom.Last(k + 1);
            }
            Array.Sort(widths);
            int cutoffIdx = Math.Max(0, (int)(widths.Length * percentile / 100.0) - 1);
            double cutoff = widths[cutoffIdx];
            double current = bb.Top.Last(1) - bb.Bottom.Last(1);
            return current <= cutoff;
        }
"""

HELPER_SESSION_RANGE: str = """
        private bool SessionRangeBreak(int sH, int sM, int eH, int eM, bool up)
        {
            double? hi = null; double? lo = null;
            DateTime today = Bars.OpenTimes.Last(1).Date;
            DateTime winStart = new DateTime(today.Year, today.Month, today.Day, sH, sM, 0, DateTimeKind.Utc);
            DateTime winEnd   = new DateTime(today.Year, today.Month, today.Day, eH, eM, 0, DateTimeKind.Utc);
            int scan = Math.Min(Bars.Count - 1, 500);
            for (int k = 2; k <= scan; k++)
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
            if (!hi.HasValue || !lo.HasValue) return false;
            double cNow = Bars.ClosePrices.Last(1);
            double cPrev = Bars.ClosePrices.Last(2);
            if (up)   return cNow > hi.Value && cPrev <= hi.Value;
            else      return cNow < lo.Value && cPrev >= lo.Value;
        }
"""

HELPER_IN_GMT_WINDOW: str = """
        private bool InGmtWindow(int afterH, int afterM, int beforeH, int beforeM)
        {
            DateTime t = Bars.OpenTimes.Last(1);
            int now = t.Hour * 60 + t.Minute;
            int a = afterH * 60 + afterM;
            int b = beforeH * 60 + beforeM;
            return a <= now && now < b;
        }
"""


# ── Parameter [Parameter] declaration templates ──────────────────────
PARAM_DOUBLE: str = '        [Parameter("{label}", DefaultValue = {default}, MinValue = {min}, MaxValue = {max})]\n        public double {name} {{ get; set; }}\n'
PARAM_INT: str = '        [Parameter("{label}", DefaultValue = {default}, MinValue = {min}, MaxValue = {max})]\n        public int {name} {{ get; set; }}\n'
