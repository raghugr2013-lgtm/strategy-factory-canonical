"""
Pass 9 — cBot log diagnostic: closes the "compiled but non-trading" loop.

Background
----------
The IR transpiler scaffold has six silent ``OnBar`` return paths that,
collectively, are the largest behavioural-reliability gap the audit
identified (memory/EXECUTION_REALISM_AUDIT.md §2.2 / §7.1):

  * spread too tight at run-time
  * session window too restrictive
  * volatility floor too aggressive
  * volume below ``Symbol.VolumeInUnitsMin``
  * ``MaxConcurrent`` gate (prior position still open)
  * symbol metadata missing / SL-TP invalid

P0.2 closed the **emission side** by instrumenting every gate with a
structured ``LogGate(reason, detail)`` call. From cTrader's perspective
every silent return is now accompanied by a deterministic
``[GATE] reason=… detail=… verbosity=…`` line in the cBot's
``Print(...)`` log.

This module closes the **consumption side**. Given a captured log blob
(stdout from cTrader Cloud, a local backtest, or an exported log file),
it produces a structured forensic verdict:

::

    {
      "lines_scanned":    int,
      "gate_lines_found": int,
      "by_reason":        {"spread": 412, "session": 0, ...},
      "top_blocker":      "spread",
      "top_blocker_pct":  98.5,
      "trade_lines":      int,
      "verdict":          "trading" | "dead_bot" | "log_empty" | "no_gates_seen",
      "recommendation":   str,         # operator-readable next step
      "sample_lines":     [str, ...],  # up to 5 verbatim lines per top reason
    }

Pure function. No I/O. Deterministic. Safe to call from anywhere.
Dormant flag-gated activation is not required — this is a forensic
tool, not a behavioural surface.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Sequence

# The scaffold's LogGate line shapes (see cbot_engine/ir_templates.py
# lines 200-209). Two forms — both must parse cleanly:
#
#   LogVerbosity=1 (default):
#     Print("[Gate] {0}: {1}", reason, detail);
#       → "[Gate] spread: spread=2.30 > MaxSpreadPips=2.00"
#
#   LogVerbosity=2 (verbose):
#     Print("[Gate] reason={0} bar_time={1:o} spread_pips={2:F2} owned={3} {4}",
#            reason, ..., detail);
#       → "[Gate] reason=spread bar_time=2026-01-01T10:00:00 spread_pips=2.30 owned=0 spread=2.30 > MaxSpreadPips=2.00"
#
# cTrader Cloud often prefixes Print(...) output with a timestamp and
# bot identifier, so we anchor on the [Gate] marker (case-insensitive)
# rather than line-start.
_GATE_VERBOSE_RE = re.compile(
    r"\[Gate\]\s*reason=(?P<reason>[A-Za-z0-9_\-]+)"
    r"(?:\s+bar_time=\S+)?"
    r"(?:\s+spread_pips=\S+)?"
    r"(?:\s+owned=\S+)?"
    r"(?:\s+(?P<detail>.*))?$",
    re.IGNORECASE,
)
_GATE_CONCISE_RE = re.compile(
    r"\[Gate\]\s+(?P<reason>[A-Za-z0-9_\-]+)\s*:\s*(?P<detail>.*)$",
    re.IGNORECASE,
)

# A scaffold trade-line emission marker. Matches both the cBot's
# default ExecuteMarketOrder result print AND the scaffold's optional
# "[TRADE] side=… result=…" line. Conservative — we'd rather under-count
# trades than mis-classify a chatty log as "trading".
_TRADE_RE = re.compile(
    r"\[TRADE\]|ExecuteMarketOrder|OnPositionOpened|OnPositionClosed",
    re.IGNORECASE,
)

# Per-reason operator recommendation. The advice is intentionally
# conservative and aligned with the scaffold's parameter names so the
# operator can copy-paste the field name into the cBot configuration UI.
_RECOMMENDATIONS: Dict[str, str] = {
    "spread": (
        "Spread is the dominant blocker. Raise MaxSpreadPips on this "
        "cBot, OR test on a tighter-spread broker / quieter session. "
        "Confirm by re-running with the broker's spread schedule."
    ),
    "session": (
        "The session gate is rejecting every bar. Verify the IR's "
        "session_start_gmt / session_end_gmt matches your broker's "
        "GMT offset; widen the window or remove the session filter "
        "if the strategy is session-agnostic."
    ),
    "volatility": (
        "Volatility floor is too aggressive for the current regime. "
        "Lower MinAtrPips / MinBbSqueezePct, or relax the ATR/BB "
        "thresholds in the IR. Confirm by checking ATR(14) values on "
        "recent bars."
    ),
    "volume_min": (
        "Trade size falls below the broker's Symbol.VolumeInUnitsMin. "
        "Either raise RiskPercent, fund the account, or relax the SL "
        "(small SL with low risk produces sub-minimum lot sizes)."
    ),
    "max_concurrent": (
        "An existing position is open and MaxConcurrent=1. This is "
        "EXPECTED for a single-position strategy that hit TP/SL "
        "infrequently. Confirm by checking position lifecycle in "
        "cTrader; only an issue if no exit is occurring."
    ),
    "sl_tp_invalid": (
        "SL/TP calculation returned an invalid value (NaN / <=0). "
        "Common cause: ATR-based SL with insufficient ATR history. "
        "Verify the strategy has enough warm-up bars; consider "
        "switching to fixed-pip SL/TP."
    ),
    "symbol_metadata": (
        "Symbol metadata (pip_size, volume_min, volume_step) was "
        "missing or zero at runtime. Verify the symbol is supported "
        "by the broker and configured in /api/latent/market-universe."
    ),
    "daily_lockout": (
        "Risk control fired: daily loss exceeded MaxDailyLossPct. "
        "EXPECTED behaviour when this protection is enabled — the "
        "lockout clears at the next UTC day rollover."
    ),
    "daily_loss_cutoff": (
        "Risk control TRIGGERED: today's drawdown breached "
        "MaxDailyLossPct and the bot closed all positions + locked "
        "out further entries until the next UTC day rollover. "
        "EXPECTED behaviour when this protection is enabled."
    ),
    "cooldown": (
        "Risk control fired: cool-down after consecutive losses. "
        "EXPECTED when MaxConsecutiveLosses is enabled — the bot "
        "resumes after CoolDownBars elapse."
    ),
    "emergency_halt": (
        "EmergencyHalt is set to true. Operator-flippable kill switch. "
        "Set EmergencyHalt=false to resume entries."
    ),
    "max_trades_day": (
        "Risk control fired: per-day trade cap reached. EXPECTED when "
        "MaxTradesPerDay is enabled — resumes at next UTC day rollover."
    ),
}

# Default recommendation when the top blocker isn't in the table.
_DEFAULT_RECOMMENDATION = (
    "Top blocker is not in the known-reason table. Read sample_lines "
    "verbatim and consult the IR scaffold contract."
)


# ─────────────────────────────────────────────────────────────────────
# Public surface
# ─────────────────────────────────────────────────────────────────────
def parse_log(
    text: str,
    *,
    max_sample_lines_per_reason: int = 5,
) -> Dict[str, object]:
    """Parse a captured cBot log into a forensic verdict.

    Pure function. Linear-time in input length. Safe to call on
    operator-supplied blobs up to ~10 MB without buffering issues.

    Parameters
    ----------
    text : str
        The captured log blob (cTrader stdout, exported file content,
        local backtest Print output — anything containing the scaffold's
        ``[GATE]`` markers).
    max_sample_lines_per_reason : int
        Maximum verbatim sample lines retained per reason in
        ``sample_lines`` (default 5; capped at 50).

    Returns
    -------
    dict
        See module docstring for the shape.
    """
    text = text or ""
    cap = max(1, min(int(max_sample_lines_per_reason), 50))

    lines = text.splitlines()
    by_reason: Counter = Counter()
    samples: Dict[str, List[str]] = {}
    trade_count = 0
    gate_count = 0

    for raw in lines:
        # Trade-line detection FIRST (cTrader sometimes embeds the
        # word "ExecuteMarketOrder" in summary lines that also carry
        # a [GATE] marker — count both, but treat trade-presence as
        # the dominant signal).
        if _TRADE_RE.search(raw):
            trade_count += 1

        m = _GATE_VERBOSE_RE.search(raw) or _GATE_CONCISE_RE.search(raw)
        if not m:
            continue
        reason = (m.group("reason") or "unknown").strip().lower()
        by_reason[reason] += 1
        gate_count += 1
        bucket = samples.setdefault(reason, [])
        if len(bucket) < cap:
            bucket.append(raw.strip())

    # Top blocker selection — highest-count gate reason.
    top_blocker: Optional[str] = None
    top_pct: float = 0.0
    if by_reason:
        top_blocker, top_n = by_reason.most_common(1)[0]
        top_pct = (top_n / gate_count) * 100.0 if gate_count else 0.0

    # Verdict.
    if not lines:
        verdict = "log_empty"
    elif trade_count > 0 and gate_count > 0:
        # Trades AND gates — healthy: the gates are filtering and the
        # bot is still firing trades. Recommend nothing.
        verdict = "trading"
    elif trade_count > 0 and gate_count == 0:
        # Trades present, no gates seen — either the operator hasn't
        # enabled gate logging (LogVerbosity=0) or every bar was eligible.
        verdict = "trading"
    elif trade_count == 0 and gate_count == 0:
        # Neither — log is too short or the bot never reached OnBar.
        verdict = "no_gates_seen"
    else:
        # gate_count > 0 and trade_count == 0 — the classic dead-bot.
        verdict = "dead_bot"

    recommendation = (
        _RECOMMENDATIONS.get(top_blocker or "", _DEFAULT_RECOMMENDATION)
        if verdict == "dead_bot"
        else (
            "Bot is firing trades. Gate counts are advisory; no "
            "operator action required."
            if verdict == "trading"
            else (
                "No [GATE] markers and no trade markers found. "
                "Enable LogVerbosity>=1 on the cBot and re-capture, "
                "OR verify the captured log covers a period when "
                "OnBar actually fires (cTrader emits OnBar only when "
                "the strategy timeframe ticks over)."
            )
        )
    )

    return {
        "lines_scanned":     len(lines),
        "gate_lines_found":  gate_count,
        "by_reason":         dict(by_reason),
        "top_blocker":       top_blocker,
        "top_blocker_pct":   round(top_pct, 2),
        "trade_lines":       trade_count,
        "verdict":           verdict,
        "recommendation":    recommendation,
        "sample_lines":      {k: v for k, v in samples.items()},
    }


def known_reasons() -> Sequence[str]:
    """Enumerate the gate-reason vocabulary the parser understands.

    Operators can use this list to verify that a captured log uses
    canonical reason names — any unknown reason flagged in
    ``by_reason`` is a hint that the scaffold has emitted a new gate
    type without the diagnostic catalogue being updated.
    """
    return tuple(_RECOMMENDATIONS.keys())


__all__ = ["parse_log", "known_reasons"]
