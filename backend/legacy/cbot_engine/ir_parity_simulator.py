"""Phase 28-C — IR parity simulator.

Execution-semantic infrastructure (NOT merely a test helper — operator
directive #2). Codifies the contract: "if the emitted C# were executed
on cTrader with the same indicator primitives and the same bar feed,
what signal would it produce at OnBar() for each bar?"

For non-HTF operators, the simulator delegates to the canonical
``IRInterpreter`` — because both the cBot and the interpreter use
identical primitives (EMA/RSI/ATR/BB), identical bar indexing
(Last(1)↔i, Last(2)↔i-1), and identical predicate semantics.

For HTF operators, the parity is APPROXIMATE by operator decision
(documented in PHASE_28_TELEMETRY_COMPLETE and stamped into every
generated cBot's metadata). The simulator continues to use the
interpreter's HTF synthesis; the cBot in production will use
cTrader's real HTF feed. The divergence is loudly surfaced via the
``HTF_PARITY_MODE = APPROXIMATE`` metadata — never silently masked.

The simulator's PRIMARY job in the trust gate is therefore:
    1. Verify every IR operator / indicator / exit kind referenced
       has a deterministic C# emitter (honest refusal on gaps).
    2. Produce the canonical signal series for parity comparison.
    3. Report whether HTF semantics participate (so the trust gate
       can tag the parity status accordingly).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from cbot_engine import ir_emitter as E
from engines.ir_interpreter import IRInterpreter
from engines.strategy_ir import StrategyIR, validate_ir


class IRCoverageGap(Exception):
    """Raised when the IR contains semantics the transpiler cannot
    render. Identical contract to ``UnsupportedIROperatorError``
    (same hierarchy), exposed under a name that reads naturally in
    parity-simulator contexts."""


def simulate_cbot_signals(
    ir: Any,
    *,
    prices: List[float],
    highs: List[float],
    lows: List[float],
    timestamps: Optional[List] = None,
    strategy_timeframe: str = "H1",
) -> Dict[str, Any]:
    """Produce the signal series the transpiled cBot would emit on the
    supplied fixture, and report v1 coverage status.

    Returns ``{"signals": [..., "BUY", None, "SELL", ...],
                "operators_used": [...],
                "indicator_kinds_used": [...],
                "sl_kind": str, "tp_kind": str,
                "htf_present": bool}``.

    Raises ``IRCoverageGap`` if any referenced operator / indicator /
    exit kind is outside the v1 transpiler vocabulary — honest refusal
    so the trust gate can flag the IR before any C# is emitted.
    """
    # ── Schema + coverage validation ────────────────────────────
    if isinstance(ir, StrategyIR):
        ir_dict = ir.model_dump(mode="json")
    else:
        ir_obj = validate_ir(ir if isinstance(ir, dict) else dict(ir))
        ir_dict = ir_obj.model_dump(mode="json")

    ops, kinds, sl_kinds, tp_kinds = E.collect_operators_and_indicators(ir_dict)
    unsupported_ops = ops - E.SUPPORTED_OPERATORS
    unsupported_inds = kinds - E.SUPPORTED_INDICATORS
    unsupported_sl = sl_kinds - E.SUPPORTED_SL_KINDS
    unsupported_tp = tp_kinds - E.SUPPORTED_TP_KINDS
    if unsupported_ops or unsupported_inds or unsupported_sl or unsupported_tp:
        raise IRCoverageGap(
            "Transpiler v1 coverage gap. "
            f"operators={sorted(unsupported_ops)} "
            f"indicators={sorted(unsupported_inds)} "
            f"sl_kinds={sorted(unsupported_sl)} "
            f"tp_kinds={sorted(unsupported_tp)}"
        )

    # ── Run the canonical interpreter ───────────────────────────
    interp = IRInterpreter(
        ir_dict, prices=prices, highs=highs, lows=lows,
        timestamps=timestamps or [], strategy_timeframe=strategy_timeframe,
    )
    signals = [interp.signal_at(i) for i in range(len(prices))]

    return {
        "signals": signals,
        "operators_used": sorted(ops),
        "indicator_kinds_used": sorted(kinds),
        "sl_kind": sorted(sl_kinds)[0] if sl_kinds else None,
        "tp_kind": sorted(tp_kinds)[0] if tp_kinds else None,
        "htf_present": "HTF_EMA" in kinds,
    }


__all__ = ["simulate_cbot_signals", "IRCoverageGap"]
