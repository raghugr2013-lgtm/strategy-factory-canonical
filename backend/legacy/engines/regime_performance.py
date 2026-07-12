"""Phase 29.0 — Regime-Conditioned Performance Evidence.

Pure function. Zero I/O. Zero side effects. Zero lifecycle mutation.

Reads the ``regime`` field stamped onto each ``strategy_performance_history``
row by ``strategy_memory.record_performance`` and aggregates per-regime
PF / DD / WR / return statistics into an advisory evidence block.

Operator-decided constants (Phase 29.0):
    MIN_TRADES_PER_REGIME = 10
    MIN_RUNS_PER_REGIME   = 2
    PF_FLOOR_PER_REGIME   = 1.0

Operator guarantees (Phase 29.0):
    1. Observational truth, NOT authoritative truth. Output NEVER alters
       deploy_score, lifecycle stage, PF history, historical rankings, or
       existing promotion outcomes.
    2. ``unknown`` is a refusal state — "insufficient classification
       confidence", NOT "bad regime behaviour". It is bucketed separately
       and NEVER contributes to ``breadth_count`` / ``regimes_breadth`` /
       ``fragile``.
    3. The output JSON shape is STABLE: every canonical regime is always
       present. Missing observations yield ``n_runs=0,
       sample_adequate=false, pf_mean=null`` — never a missing key.

Public surface:
    REGIMES_CANONICAL              : ("trending", "ranging",
                                       "high_volatility", "low_volatility")
    REGIME_UNKNOWN                 : "unknown"
    ALL_REGIMES                    : REGIMES_CANONICAL + (REGIME_UNKNOWN,)
    MIN_TRADES_PER_REGIME          : 10
    MIN_RUNS_PER_REGIME            : 2
    PF_FLOOR_PER_REGIME            : 1.0
    PHASE_VERSION                  : "29.0"
    empty_regime_stats(regime)     : dict   — zero-observation baseline
    compute_regime_performance(rows) : dict  — pure aggregator

Reversibility:
    Drop this module → no caller in the orchestrator / lifecycle /
    BI5 / transpiler path breaks. Only consumers are ``api/regime.py``
    and Phase-29 trust-gate tests.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

# ── Operator-decided constants (Phase 29.0) ─────────────────────────

REGIMES_CANONICAL = ("trending", "ranging", "high_volatility", "low_volatility")
REGIME_UNKNOWN = "unknown"
ALL_REGIMES = REGIMES_CANONICAL + (REGIME_UNKNOWN,)

# Operator decision #2 — sample-adequacy floor.
MIN_TRADES_PER_REGIME = 10
MIN_RUNS_PER_REGIME = 2
# Additional internal floor — a regime must be profitable (PF ≥ 1.0) to
# count toward breadth. An adequate-but-losing regime is honest evidence
# of fragility, NOT evidence of breadth.
PF_FLOOR_PER_REGIME = 1.0

PHASE_VERSION = "29.0"


# ── Helpers (pure, internal) ────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and v == v:  # filter NaN
        return float(v)
    return None


def _safe_int(v: Any) -> Optional[int]:
    n = _safe_float(v)
    return int(n) if n is not None else None


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _cov(values: List[float]) -> Optional[float]:
    """Coefficient of variation = std / |mean|. None when fewer than two
    samples or |mean| is essentially zero."""
    if len(values) < 2:
        return None
    m = _mean(values)
    if m is None or abs(m) < 1e-9:
        return None
    var = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(var) / abs(m)


def _max(values: List[float]) -> Optional[float]:
    return max(values) if values else None


def _round_or_none(v: Optional[float], ndigits: int = 4) -> Optional[float]:
    if v is None:
        return None
    return round(v, ndigits)


# ── Public schema helpers ───────────────────────────────────────────

def empty_regime_stats(regime: str) -> Dict[str, Any]:
    """Zero-observation baseline for one regime. Used to keep the JSON
    shape stable when a regime has no rows."""
    return {
        "regime":            regime,
        "n_runs":            0,
        "trades_total":      0,
        "pf_mean":           None,
        "pf_cov":            None,
        "dd_pct_max":        None,
        "win_rate_mean":     None,
        "return_pct_mean":   None,
        "sample_adequate":   False,
        "edge_positive":     False,
    }


def _classify_row_regime(row: Dict[str, Any]) -> str:
    """Bucket a history row to a regime key.

    Operator guarantee #2:
        Anything that is not one of the four canonical regimes — None,
        empty string, the literal ``"unknown"``, a typo, or a future
        classifier label — buckets under ``REGIME_UNKNOWN``. It NEVER
        contributes to breadth, fragility, or any negative signal.
    """
    raw = row.get("regime")
    if raw in REGIMES_CANONICAL:
        return raw  # type: ignore[return-value]
    return REGIME_UNKNOWN


# ── Core aggregator ─────────────────────────────────────────────────

def compute_regime_performance(
    history_rows: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate per-regime evidence from raw history rows.

    Args:
        history_rows: any iterable of dicts shaped like rows from the
            ``strategy_performance_history`` collection. The function
            reads only ``regime``, ``pf``, ``dd_pct``, ``trades``,
            ``win_rate``, ``return_pct``. Other fields are ignored.

    Returns:
        A stable-shape dict:
            {
              "per_regime": {
                  "trending":        { ...stats... },
                  "ranging":         { ...stats... },
                  "high_volatility": { ...stats... },
                  "low_volatility":  { ...stats... },
                  "unknown":         { ...stats... }    # always present
              },
              "regimes_seen":     [str, ...]     # alphabetical, no duplicates
              "regimes_adequate": [str, ...]     # canonical only
              "regimes_breadth":  [str, ...]     # adequate AND pf_mean ≥ 1.0
              "breadth_count":    int            # len(regimes_breadth)
              "fragile":          bool           # breadth_count < 2
              "computed_at":      iso str,
              "phase":            "29.0",
              "advisory_only":    True,
            }

    Honest refusal contract:
        * Empty input → all five regimes zero-stat, regimes_seen=[],
          breadth_count=0, fragile=True. (Operator decision #1 — a
          strategy with zero evidence IS fragile by default; this is
          advisory, never a stage cap in 29.0.)
        * Rows with ``regime`` that is None / missing / non-canonical →
          bucketed under ``unknown``; NEVER counted toward fragility or
          breadth (operator guarantee #2).
        * Rows with missing PF → counted in n_runs only when ``trades``
          is present; ``pf_mean`` honest-Null when no PFs available.
    """
    rows: List[Dict[str, Any]] = [r for r in (history_rows or []) if isinstance(r, dict)]

    # Bucket rows by regime
    buckets: Dict[str, List[Dict[str, Any]]] = {r: [] for r in ALL_REGIMES}
    for row in rows:
        buckets[_classify_row_regime(row)].append(row)

    per_regime: Dict[str, Dict[str, Any]] = {}
    regimes_seen: List[str] = []
    regimes_adequate: List[str] = []
    regimes_breadth: List[str] = []

    for regime in ALL_REGIMES:
        bucket = buckets[regime]
        if not bucket:
            per_regime[regime] = empty_regime_stats(regime)
            continue

        regimes_seen.append(regime)

        pfs: List[float] = []
        dds: List[float] = []
        wrs: List[float] = []
        returns: List[float] = []
        trades_total = 0

        for row in bucket:
            pf = _safe_float(row.get("pf"))
            dd = _safe_float(row.get("dd_pct"))
            wr = _safe_float(row.get("win_rate"))
            rt = _safe_float(row.get("return_pct"))
            tr = _safe_int(row.get("trades"))
            if pf is not None:
                pfs.append(pf)
            if dd is not None:
                dds.append(dd)
            if wr is not None:
                wrs.append(wr)
            if rt is not None:
                returns.append(rt)
            if tr is not None:
                trades_total += tr

        pf_mean = _mean(pfs)
        pf_cov = _cov(pfs)
        dd_max = _max(dds)
        wr_mean = _mean(wrs)
        rt_mean = _mean(returns)

        # Sample adequacy — operator decision #2.
        # An UNKNOWN-regime bucket NEVER reports sample_adequate=True,
        # by operator guarantee #2 (unknown is a refusal state).
        n_runs = len(bucket)
        if regime == REGIME_UNKNOWN:
            sample_adequate = False
            edge_positive = False
        else:
            sample_adequate = (
                n_runs >= MIN_RUNS_PER_REGIME
                and trades_total >= MIN_TRADES_PER_REGIME
            )
            edge_positive = (
                sample_adequate
                and pf_mean is not None
                and pf_mean >= PF_FLOOR_PER_REGIME
            )

        per_regime[regime] = {
            "regime":          regime,
            "n_runs":          n_runs,
            "trades_total":    trades_total,
            "pf_mean":         _round_or_none(pf_mean, 4),
            "pf_cov":          _round_or_none(pf_cov, 4),
            "dd_pct_max":      _round_or_none(dd_max, 4),
            "win_rate_mean":   _round_or_none(wr_mean, 4),
            "return_pct_mean": _round_or_none(rt_mean, 4),
            "sample_adequate": sample_adequate,
            "edge_positive":   edge_positive,
        }
        if regime != REGIME_UNKNOWN:
            if sample_adequate:
                regimes_adequate.append(regime)
            if edge_positive:
                regimes_breadth.append(regime)

    # Stable alphabetical ordering for list payloads — guarantees
    # bit-identical output regardless of input row order.
    regimes_seen.sort()
    regimes_adequate.sort()
    regimes_breadth.sort()

    breadth_count = len(regimes_breadth)
    fragile = breadth_count < 2

    return {
        "per_regime":       per_regime,
        "regimes_seen":     regimes_seen,
        "regimes_adequate": regimes_adequate,
        "regimes_breadth":  regimes_breadth,
        "breadth_count":    breadth_count,
        "fragile":          fragile,
        "computed_at":      _now_iso(),
        "phase":            PHASE_VERSION,
        "advisory_only":    True,
    }
