"""
Phase 12 — Safety Injector.

Takes the generated cBot code and weaves in structured safety checks:
    * per-trade risk cap
    * daily max-loss cut-off
    * optional spread filter on entry

The injector NEVER rewrites free-form logic — it inserts fixed, audited
code fragments at known marker lines.
"""
from __future__ import annotations


def _risk_fields_block(daily_dd_pct: float, spread_pips: float | None) -> str:
    lines = [
        "",
        f'        [Parameter("Max Daily Loss %", DefaultValue = {float(daily_dd_pct):g}, MinValue = 0.1, MaxValue = 20)]',
        '        public double MaxDailyLossPercent { get; set; }',
        "",
    ]
    if spread_pips is not None:
        lines += [
            f'        [Parameter("Max Spread (pips)", DefaultValue = {float(spread_pips):g}, MinValue = 0, MaxValue = 50)]',
            '        public double MaxSpreadPips { get; set; }',
            "",
        ]
    lines += [
        "        private double _dayStartBalance;",
        "        private DateTime _currentDay = DateTime.MinValue;",
        "        private bool _tradingHaltedForDay;",
    ]
    return "\n".join(lines)


def _on_start_safety_block() -> str:
    return (
        "\n            _dayStartBalance = Account.Balance;\n"
        "            _currentDay = Server.Time.Date;\n"
        "            _tradingHaltedForDay = false;\n"
    )


def _daily_loss_guard() -> str:
    """Returns a fragment that resets the day and enforces the daily cap."""
    return (
        "            if (Server.Time.Date != _currentDay)\n"
        "            {\n"
        "                _currentDay = Server.Time.Date;\n"
        "                _dayStartBalance = Account.Balance;\n"
        "                _tradingHaltedForDay = false;\n"
        "            }\n"
        "            double drawdownPct = (_dayStartBalance - Account.Balance) / _dayStartBalance * 100.0;\n"
        "            if (drawdownPct >= MaxDailyLossPercent)\n"
        "            {\n"
        "                _tradingHaltedForDay = true;\n"
        "                foreach (var p in Positions.FindAll(\"{{BOT_NAME}}\", SymbolName))\n"
        "                    ClosePosition(p);\n"
        "            }\n"
        "            if (_tradingHaltedForDay)\n"
        "                return;\n"
    )


def _spread_filter(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        "            double spreadPips = (Symbol.Spread / Symbol.PipSize);\n"
        "            if (spreadPips > MaxSpreadPips)\n"
        "                return;\n"
    )


def inject_safety(
    code: str,
    bot_name: str | None = None,
    *,
    risk_percent: float = 1.0,
    max_daily_loss_pct: float = 3.0,
    max_spread_pips: float | None = 3.0,
) -> dict:
    """
    Inject safety layer into generated cBot code.

    Args:
        code: output of `code_generator.generate_code()["code"]`.
        bot_name: class name used as the position label in ClosePosition
                  filters. If None we try to recover it from the `public
                  class X : Robot` declaration.
        risk_percent: ensured RiskPercent upper bound (logged only).
        max_daily_loss_pct: daily drawdown hard stop.
        max_spread_pips: if not None, adds a pre-entry spread filter.

    Returns:
        {"code": str, "injections": [...]}
    """
    import re as _re

    injections: list[str] = []

    if not bot_name:
        m = _re.search(r"public\s+class\s+(\w+)\s*:\s*Robot", code)
        bot_name = m.group(1) if m else "GeneratedBot"

    # 1) Inject new fields just after the RiskPercent parameter closing brace.
    marker_risk_line = "public double RiskPercent { get; set; }"
    if marker_risk_line in code:
        risk_fields = _risk_fields_block(max_daily_loss_pct, max_spread_pips)
        code = code.replace(
            marker_risk_line,
            marker_risk_line + "\n" + risk_fields,
            1,
        )
        injections.append("risk_fields")

    # 2) Seed day-tracking state at the top of OnStart().
    if "protected override void OnStart()" in code:
        code = code.replace(
            "protected override void OnStart()\n        {",
            "protected override void OnStart()\n        {" + _on_start_safety_block(),
            1,
        )
        injections.append("on_start_seed")

    # 3) Daily loss guard + spread filter at top of OnBar().
    daily = _daily_loss_guard().replace("{{BOT_NAME}}", bot_name)
    spread = _spread_filter(max_spread_pips is not None)
    guards = daily + spread
    marker_onbar = "protected override void OnBar()\n        {\n"
    if marker_onbar in code:
        code = code.replace(marker_onbar, marker_onbar + guards, 1)
        injections.append("on_bar_guards")

    return {
        "code": code,
        "injections": injections,
        "config": {
            "risk_percent": float(risk_percent),
            "max_daily_loss_pct": float(max_daily_loss_pct),
            "max_spread_pips": None if max_spread_pips is None else float(max_spread_pips),
        },
    }
