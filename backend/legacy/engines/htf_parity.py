"""
P1.4 — Dormant HTF parity validation suite.

Status
------
* DORMANT BY DEFAULT. Gated by ``ENABLE_HTF_PARITY_VALIDATION``
  (default ``False``). Even when the flag is ON, **no production
  code path consults this module**. Activation requires BOTH the
  flag flip AND a deliberate future code change to wire a call-site
  (most likely into the existing trust gate in
  ``engines/cbot_parity.py`` once a soak window of evidence has
  accumulated).
* No tick engine. No tick infrastructure. No framework expansion.
* Read-only with respect to Mongo at import time; never writes to
  any collection on its own.

Why this exists
---------------
The audit (``memory/EXECUTION_REALISM_AUDIT.md`` §3.1, §3.2) made
the honest call: the existing ``cbot_parity.sign_off_parity(...)``
proves SIGNAL parity, NOT TRADE parity. P0.4 / P1.3 introduced the
trade-lifecycle simulator. There remains one further institutional
gap that blocks the promotion of trade-parity to a hard gate (P1.5):

  **HTF parity is currently APPROXIMATE.**

The canonical Python interpreter (``engines/ir_interpreter.py``)
synthesises Higher-Timeframe EMA series by SUBSAMPLING the LTF close
series (``prices[::htf_factor]``) and then EMAing the coarse series.
That is the audit-documented "APPROXIMATE" path: it preserves bar
alignment (cheap, deterministic, identical across interpreter and
backtest engine), but it does NOT match the way cTrader's runtime
produces HTF bars at execution time.

cTrader's runtime calls ``MarketData.GetBars(htfTimeframe)`` which
returns properly time-bucketed OHLC HTF bars whose closes are the
LAST close inside each HTF window — not a stride-N subsample.

For HTF-trend strategies the two approaches typically agree on the
**sign of the slope** (HTF_SLOPE_UP / HTF_SLOPE_DOWN) at most bars
because the EMA is a low-pass filter and the subsample is a
stochastic but unbiased approximation of the time-bucketed series.
But they diverge — sometimes significantly — at the moments the
HTF slope flips. The institutional question is: HOW MUCH do they
diverge, and is the divergence bounded enough to call the parity
"PASSED" within a stated tolerance?

This module is the deterministic, candle-space machinery that —
when activated — answers that question per (IR × fixture). It is
the natural P1.4 follow-up to P0.4/P1.3 and the natural pre-cursor
to P1.5 (trade-parity-as-hard-gate).

Determinism
-----------
``validate_htf_parity(...)`` is a pure function of
``(ir, prices, highs, lows, timestamps, strategy_timeframe)``.
No randomness, no clock reads, no I/O. The baseline arm calls the
canonical ``IRInterpreter`` exactly the way today's trust gate
does. The true-HTF arm constructs a parallel IR + LTF price series
in which every HTF_EMA indicator is replaced by its TRUE
time-bucketed synthesis, then runs the same interpreter against
that derivative — so the divergence signal is isolated to the HTF
synthesis step alone (no other source of variation).

HTF aggregation rule
--------------------
For an LTF bar series with ``timestamps[i]`` aligned to UTC, the
HTF bar containing bar ``i`` is identified by floor-flooring
``timestamps[i]`` to the start of the HTF window. The HTF close is
the LTF close of the LAST LTF bar in that window. The HTF high /
low are aggregated as needed. This matches the audit-favored
candle-space approximation of cTrader's true HTF feed.

Outputs
-------
``validate_htf_parity(...) -> dict`` returns:

::

    {
      "verdict":           "NOT_APPLICABLE" | "EXACT"
                           | "WITHIN_TOLERANCE" | "DIVERGENT"
                           | "ERROR",
      "htf_present":       bool,
      "ltf":               str,
      "htf":               str,   # derived: e.g. "H1" -> "H4"
      "compared_bars":     int,
      "diverging_bars":    int,
      "divergence_pct":    float, # 0..100
      "tolerance_pct":     float, # echoed for audit
      "first_divergence":  int | None,
      "baseline_summary":  {long:int, short:int, none:int},
      "true_htf_summary":  {long:int, short:int, none:int},
      "advisory_only":     True,
      "dormant":           bool,
    }

NEVER raises in production usage; on any unexpected exception the
verdict is ``"ERROR"`` and the ``details`` carry the message.

Wiring policy
-------------
* The existing ``cbot_parity.sign_off_parity(...)`` continues
  unchanged. Today its HTF metadata stamp is ``APPROXIMATE``
  whenever ``HTF_EMA`` is in the IR — this module exists to
  prove a quantified divergence figure, NOT to replace that stamp.
* When a future pass wires this module in, the integration point
  will be additive: ``sign_off_parity`` would call
  ``validate_htf_parity(...)`` and persist
  ``htf_parity_verdict`` + ``htf_divergence_pct`` alongside the
  existing signal verdict. Today, that wiring does not exist.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Public flag accessors (dormant by default)
# ─────────────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    """True iff ``ENABLE_HTF_PARITY_VALIDATION`` is set to a truthy
    env value. Mirrors the discipline used by other dormant primitives
    (``replay_priority.is_enabled``, ``cbot_trade_parity.is_enabled``
    etc.): feature_flags is the canonical registry, but ``os.environ``
    is the authoritative runtime source.
    """
    raw = os.environ.get("ENABLE_HTF_PARITY_VALIDATION", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def max_divergence_pct() -> float:
    """Operator-configurable tolerance for the ``WITHIN_TOLERANCE``
    verdict band. Defaults to 5.0 (i.e. up to 5% of compared bars
    may disagree before the verdict steps down to ``DIVERGENT``).
    """
    try:
        return max(0.0, float(os.environ.get("HTF_PARITY_MAX_DIVERGENCE_PCT", "5.0")))
    except (TypeError, ValueError):
        return 5.0


# ─────────────────────────────────────────────────────────────────────
# Timeframe table
# ─────────────────────────────────────────────────────────────────────
# Map each LTF to (true-HTF label, htf-factor matching the canonical
# ``_HTF_FACTOR`` used by ``engines.ir_interpreter._htf_ema_series``).
# Keeping the factor identical guarantees the baseline arm of the
# validator matches today's production HTF synthesis byte-for-byte.
_LTF_TO_HTF: Dict[str, Tuple[str, int]] = {
    "M1":  ("M15", 15),
    "M5":  ("H1",  12),
    "M15": ("H1",  4),
    "M30": ("H1",  2),
    "H1":  ("H4",  4),
    "H4":  ("D1",  6),
    "D1":  ("W1",  5),
}


def htf_for(ltf: str) -> Optional[Tuple[str, int]]:
    """Return ``(htf_label, htf_factor)`` for the supplied LTF, or
    ``None`` if the LTF is outside the validator's vocabulary.
    """
    return _LTF_TO_HTF.get((ltf or "").upper())


# ─────────────────────────────────────────────────────────────────────
# IR introspection helpers
# ─────────────────────────────────────────────────────────────────────
def is_htf_ir(ir_dict: Dict[str, Any]) -> bool:
    """True iff the IR references any HTF-flavoured indicator. Today
    the validator targets HTF_EMA — the only HTF primitive emitted by
    the v1 transpiler (per ``ir_transpiler.HTF_PARITY_MODE`` stamp).
    """
    inds = ir_dict.get("indicators") or []
    for ind in inds:
        if (ind.get("kind") or "").upper() == "HTF_EMA":
            return True
    return False


def _ir_dict(ir: Any) -> Dict[str, Any]:
    """Best-effort IR-to-dict canonicalisation (matches the seam used
    by ``cbot_trade_parity.simulate_trades`` and
    ``cbot_parity.sign_off_parity``).
    """
    from engines.strategy_ir import StrategyIR, validate_ir
    if isinstance(ir, StrategyIR):
        return ir.model_dump(mode="json")
    if isinstance(ir, dict):
        return validate_ir(ir).model_dump(mode="json")
    return validate_ir(dict(ir)).model_dump(mode="json")


# ─────────────────────────────────────────────────────────────────────
# True time-bucketed HTF synthesis
# ─────────────────────────────────────────────────────────────────────
_TF_SECONDS: Dict[str, int] = {
    "M1": 60,   "M5": 300,   "M15": 900,  "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800,
}


def _parse_ts(ts: Any) -> Optional[datetime]:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None
    return None


def _floor_to_htf(dt: datetime, htf_seconds: int) -> int:
    """Return the unix-epoch seconds at the start of the HTF bucket
    containing ``dt``. Pure integer arithmetic — deterministic.
    """
    epoch = int(dt.timestamp())
    return epoch - (epoch % htf_seconds)


def aggregate_htf_closes(
    prices: List[float],
    timestamps: List[Any],
    *,
    ltf: str,
    htf: str,
) -> List[Optional[float]]:
    """Construct a LENGTH-N array of HTF closes aligned to the LTF
    series. The HTF close at LTF bar ``i`` is the LTF close of the
    LAST LTF bar in the HTF bucket containing ``i`` that is at or
    before ``i``.

    This is the candle-space approximation of cTrader's
    ``MarketData.GetBars(htfTimeframe).ClosePrices.Last(1)`` semantic:
    the most-recently-CLOSED HTF bar's close, as seen at the moment
    LTF bar ``i`` ticks.

    Bars before the first complete HTF bucket return ``None`` — the
    interpreter treats that as "warmup, no signal" by convention.
    """
    n = len(prices)
    if n == 0 or not timestamps or len(timestamps) != n:
        return [None] * n
    htf_secs = _TF_SECONDS.get((htf or "").upper())
    if not htf_secs:
        return [None] * n

    out: List[Optional[float]] = [None] * n
    # First pass: bucket each LTF bar into its HTF bucket, computing
    # the running close within each bucket.
    bucket_of: List[Optional[int]] = [None] * n
    last_close_in_bucket: Dict[int, float] = {}
    bucket_order: List[int] = []
    for i, raw in enumerate(timestamps):
        dt = _parse_ts(raw)
        if dt is None:
            continue
        b = _floor_to_htf(dt, htf_secs)
        bucket_of[i] = b
        last_close_in_bucket[b] = float(prices[i])
        if not bucket_order or bucket_order[-1] != b:
            bucket_order.append(b)

    if len(bucket_order) < 2:
        # Not enough HTF history to expose a CLOSED HTF bar.
        return out

    # Second pass: for each LTF bar i, find the most-recent CLOSED
    # HTF bucket (i.e. NOT the bucket bar i belongs to) and project
    # its final close. This matches cTrader's "Last(1)" semantic.
    # Pre-compute the final close of every bucket so the second
    # pass is O(n).
    final_close: Dict[int, float] = last_close_in_bucket  # already complete
    # bucket_seen_complete[b] = True once we've moved PAST that bucket
    completed: set = set()
    last_completed_bucket: Optional[int] = None
    last_b: Optional[int] = None
    for i in range(n):
        b = bucket_of[i]
        if b is None:
            # Carry-forward the previous completed value (or None).
            if last_completed_bucket is not None:
                out[i] = final_close[last_completed_bucket]
            continue
        if last_b is not None and b != last_b:
            # We crossed an HTF boundary — the prior bucket is now
            # closed and visible to the runtime.
            completed.add(last_b)
            last_completed_bucket = last_b
        if last_completed_bucket is not None:
            out[i] = final_close[last_completed_bucket]
        last_b = b
    return out


def _ema(series: List[Optional[float]], period: int) -> List[Optional[float]]:
    """EMA over a series that may contain leading None warmup. The
    EMA starts at the first non-None value and uses the standard
    2 / (period + 1) weighting. None propagates as warmup.
    """
    n = len(series)
    out: List[Optional[float]] = [None] * n
    if period <= 0:
        return out
    alpha = 2.0 / (period + 1.0)
    ema_val: Optional[float] = None
    seen: int = 0
    for i, v in enumerate(series):
        if v is None:
            out[i] = ema_val if seen >= period else None
            continue
        if ema_val is None:
            ema_val = float(v)
        else:
            ema_val = alpha * float(v) + (1.0 - alpha) * ema_val
        seen += 1
        out[i] = ema_val if seen >= period else None
    return out


def true_htf_ema_series(
    prices: List[float],
    timestamps: List[Any],
    *,
    ltf: str,
    htf: str,
    period: int,
) -> List[Optional[float]]:
    """Return an LTF-aligned HTF EMA series computed via time-bucketed
    aggregation (the cTrader-faithful candle-space path).

    Contrast with ``engines.ir_interpreter._htf_ema_series`` which
    subsamples the LTF close series. This function preserves the
    runtime semantic (HTF EMA = EMA over the closes of properly
    time-bucketed HTF bars) at the cost of needing timestamps —
    which is precisely the input the runtime trust gate must supply
    when it consults this validator.
    """
    htf_closes = aggregate_htf_closes(prices, timestamps, ltf=ltf, htf=htf)
    return _ema(htf_closes, period)


# ─────────────────────────────────────────────────────────────────────
# Build a derivative IR + interpreter with HTF series overridden
# ─────────────────────────────────────────────────────────────────────
def _build_interpreter_with_overrides(
    ir_dict: Dict[str, Any],
    *,
    prices: List[float],
    highs: List[float],
    lows: List[float],
    timestamps: List[Any],
    strategy_timeframe: str,
    htf_overrides: Dict[str, List[Optional[float]]],
):
    """Construct an ``IRInterpreter`` against the supplied IR and then
    REPLACE the HTF_EMA indicator series with the supplied overrides.

    The interpreter's own ``_precompute_indicators`` runs unchanged
    against the IR. We then surgically swap each HTF_EMA indicator's
    series in-place. This is the smallest possible touch to isolate
    the HTF-synthesis-path variable.
    """
    from engines.ir_interpreter import IRInterpreter
    interp = IRInterpreter(
        ir_dict,
        prices=prices, highs=highs, lows=lows,
        timestamps=timestamps,
        strategy_timeframe=strategy_timeframe,
    )
    for ind in ir_dict.get("indicators") or []:
        if (ind.get("kind") or "").upper() != "HTF_EMA":
            continue
        iid = ind.get("id")
        if iid not in interp._indicator_data:           # pragma: no cover
            continue
        new_series = htf_overrides.get(iid)
        if new_series is None:
            continue
        interp._indicator_data[iid] = {
            "series": new_series,
            "kind":   "HTF_EMA",
        }
    return interp


def _signal_series(interp) -> List[Optional[str]]:
    return [interp.signal_at(i) for i in range(interp.n)]


def _signal_summary(signals: List[Optional[str]]) -> Dict[str, int]:
    return {
        "long":  sum(1 for s in signals if s == "BUY"),
        "short": sum(1 for s in signals if s == "SELL"),
        "none":  sum(1 for s in signals if s is None),
    }


# ─────────────────────────────────────────────────────────────────────
# Public: validate_htf_parity
# ─────────────────────────────────────────────────────────────────────
def validate_htf_parity(
    ir: Any,
    *,
    prices: List[float],
    highs: List[float],
    lows: List[float],
    timestamps: List[Any],
    strategy_timeframe: str = "H1",
    tolerance_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Compare the canonical interpreter's HTF synthesis (subsample
    of LTF closes) against a true time-bucketed HTF synthesis on
    the same IR + price fixture.

    Pure function. Deterministic. Never writes to any collection.
    Never raises in production usage — exceptions are captured into
    ``verdict="ERROR"`` and ``details``.

    Parameters
    ----------
    ir : StrategyIR | dict
        Schema-validated Strategy IR.
    prices, highs, lows : sequence[float]
        LTF bar series. Same length.
    timestamps : sequence
        LTF bar timestamps (datetime or ISO-8601 string). Required —
        the true-HTF synthesis cannot work without them.
    strategy_timeframe : str
        LTF label (e.g. ``"H1"``).
    tolerance_pct : float | None
        Override of the operator-configurable
        ``HTF_PARITY_MAX_DIVERGENCE_PCT``. The validator returns
        ``WITHIN_TOLERANCE`` when the diverging-bar percentage is at
        or below this value, ``DIVERGENT`` otherwise.

    Returns
    -------
    dict
        See module docstring for the shape.
    """
    out: Dict[str, Any] = {
        "verdict":           "ERROR",
        "htf_present":       False,
        "ltf":               (strategy_timeframe or "").upper(),
        "htf":               None,
        "compared_bars":     0,
        "diverging_bars":    0,
        "divergence_pct":    0.0,
        "tolerance_pct":     (
            tolerance_pct if tolerance_pct is not None
            else max_divergence_pct()
        ),
        "first_divergence":  None,
        "baseline_summary":  None,
        "true_htf_summary":  None,
        "advisory_only":     True,
        "dormant":           not is_enabled(),
        "details":           None,
    }

    try:
        if not (len(prices) == len(highs) == len(lows)):
            out["details"] = (
                f"length mismatch: prices={len(prices)} "
                f"highs={len(highs)} lows={len(lows)}"
            )
            return out
        if not timestamps or len(timestamps) != len(prices):
            out["details"] = (
                f"timestamps required and aligned: got {len(timestamps)} "
                f"for prices={len(prices)}"
            )
            return out

        ir_dict = _ir_dict(ir)

        # ── 1) NOT_APPLICABLE early exit when the IR has no HTF use.
        if not is_htf_ir(ir_dict):
            out.update({
                "verdict":     "NOT_APPLICABLE",
                "htf_present": False,
                "details":     "IR contains no HTF_EMA indicator; "
                               "HTF parity is trivially exact.",
            })
            return out
        out["htf_present"] = True

        ltf = (strategy_timeframe or "H1").upper()
        htf_pair = htf_for(ltf)
        if htf_pair is None:
            out["details"] = (
                f"strategy_timeframe={ltf!r} is outside the validator's "
                "vocabulary (M1/M5/M15/M30/H1/H4/D1)."
            )
            return out
        htf_label, _factor = htf_pair
        out["htf"] = htf_label

        # ── 2) Baseline arm — today's interpreter (subsample path) ─
        from engines.ir_interpreter import IRInterpreter
        baseline_interp = IRInterpreter(
            ir_dict,
            prices=prices, highs=highs, lows=lows,
            timestamps=timestamps,
            strategy_timeframe=ltf,
        )
        baseline_signals = _signal_series(baseline_interp)

        # ── 3) True-HTF arm — same IR, HTF_EMA series replaced ────
        htf_overrides: Dict[str, List[Optional[float]]] = {}
        for ind in ir_dict.get("indicators") or []:
            if (ind.get("kind") or "").upper() != "HTF_EMA":
                continue
            iid = ind.get("id")
            period = int((ind.get("params") or {}).get("period", 20))
            htf_overrides[iid] = true_htf_ema_series(
                prices, timestamps,
                ltf=ltf, htf=htf_label, period=period,
            )

        true_interp = _build_interpreter_with_overrides(
            ir_dict,
            prices=prices, highs=highs, lows=lows,
            timestamps=timestamps,
            strategy_timeframe=ltf,
            htf_overrides=htf_overrides,
        )
        true_signals = _signal_series(true_interp)

        # ── 4) Comparison ─────────────────────────────────────────
        n_compared = min(len(baseline_signals), len(true_signals))
        diverging = 0
        first_div: Optional[int] = None
        for i in range(n_compared):
            if baseline_signals[i] != true_signals[i]:
                diverging += 1
                if first_div is None:
                    first_div = i
        pct = (diverging / n_compared * 100.0) if n_compared > 0 else 0.0

        tol = out["tolerance_pct"]
        if diverging == 0:
            verdict = "EXACT"
        elif pct <= tol:
            verdict = "WITHIN_TOLERANCE"
        else:
            verdict = "DIVERGENT"

        out.update({
            "verdict":           verdict,
            "compared_bars":     n_compared,
            "diverging_bars":    diverging,
            "divergence_pct":    round(pct, 4),
            "first_divergence":  first_div,
            "baseline_summary":  _signal_summary(baseline_signals),
            "true_htf_summary":  _signal_summary(true_signals),
            "details":           (
                f"baseline={out['ltf']} subsample-HTF vs "
                f"true {htf_label} time-bucketed HTF; "
                f"{diverging}/{n_compared} bars diverged "
                f"({pct:.4f}% vs tolerance {tol:.4f}%)."
            ),
        })
        return out
    except Exception as e:                                  # noqa: BLE001
        logger.debug("[htf_parity] validate_htf_parity failed: %s", e)
        out["verdict"] = "ERROR"
        out["details"] = str(e)[:400]
        return out


__all__ = [
    "is_enabled",
    "max_divergence_pct",
    "htf_for",
    "is_htf_ir",
    "aggregate_htf_closes",
    "true_htf_ema_series",
    "validate_htf_parity",
]
