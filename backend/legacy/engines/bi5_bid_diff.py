"""Phase 2 Stage 2 — BI5 ↔ BID Shadow-Diff Harness.

Runs the legacy BI5 realism resampler (`bi5_realism._resample_1m_to_tf`)
AND the CTS resampler (`cts.resampler.resample_m1_to`) over the SAME
M1 window for a given symbol and target timeframe, joins the resulting
HTF bars on bucket timestamp, computes per-bucket deviation (basis
points), and buckets each comparison into one of three tiers per
`BID_CANDLE_STORAGE_REVIEW.md §10.3`:

    informational      — max_deviation_bps < 10
    warning            — 10 ≤ max_deviation_bps < 50
    governance_review  — ≥ 50

Two artifacts are produced per run:
  * summary — tier distribution, pass/fail, statistics
  * detail — every comparison bucket with timestamps, OHLCV, deviation, tier

Read-only. Zero writes. No side effects on `market_data`, on the
`market_data_htf_cache`, or on any other collection.

Feature-gated by `BI5_BID_DIFF_ENABLED` (default OFF).
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_enabled() -> bool:
    return _flag("BI5_BID_DIFF_ENABLED", False)


# ── Pass criteria (operator's declared thresholds) ────────────────────

# Bps tier thresholds
TIER_INFORMATIONAL_MAX_BPS: float = 10.0
TIER_WARNING_MAX_BPS:       float = 50.0

# Pass criterion — ≥ 99% of comparisons must land in `informational`
PASS_INFORMATIONAL_RATIO:  float = 0.99


# ── Bucket comparison record (detailed audit artifact) ────────────────

@dataclass(frozen=True)
class BucketDiff:
    """One HTF-bucket comparison — the detailed audit artifact row."""

    bucket_ts:            str          # ISO — left-closed bucket start
    bi5_open:             Optional[float]
    bi5_high:             Optional[float]
    bi5_low:              Optional[float]
    bi5_close:            Optional[float]
    bi5_volume:           Optional[float]
    cts_open:             Optional[float]
    cts_high:             Optional[float]
    cts_low:              Optional[float]
    cts_close:            Optional[float]
    cts_volume:           Optional[float]
    delta_open_bps:       Optional[float]
    delta_high_bps:       Optional[float]
    delta_low_bps:        Optional[float]
    delta_close_bps:      Optional[float]
    max_deviation_bps:    Optional[float]
    tier:                 str          # "informational" | "warning" | "governance_review" | "bi5_only" | "cts_only"
    only_in:              Optional[str] = None   # "bi5" | "cts" | None when both present

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Summary aggregate ────────────────────────────────────────────────

@dataclass
class DiffSummary:
    """Aggregate outcome + pass/fail against the operator's thresholds."""

    started_at:                  str
    finished_at:                 str
    symbol:                      str
    timeframe:                   str
    m1_row_count:                int
    bi5_bar_count:               int
    cts_bar_count:               int
    total_comparisons:           int        = 0
    both_present:                int        = 0
    bi5_only:                    int        = 0
    cts_only:                    int        = 0
    tier_counts:                 Dict[str, int]         = field(default_factory=dict)
    max_deviation_bps_observed:  Optional[float]        = None
    p50_deviation_bps:           Optional[float]        = None
    p95_deviation_bps:           Optional[float]        = None
    p99_deviation_bps:           Optional[float]        = None
    pass_informational_ratio:    Optional[float]        = None
    pass_ok:                     Optional[bool]         = None
    reason:                      str                    = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Core diff (pure) ─────────────────────────────────────────────────

def _percentile(sorted_vals: Sequence[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * q
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return float(sorted_vals[lo])
    return float(sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo))


def _bps(delta: float, base: float) -> float:
    """Signed basis-point deviation."""
    if base is None or base == 0:
        return 0.0
    return (delta / base) * 10_000.0


def _tier_for(bps: float) -> str:
    if bps < TIER_INFORMATIONAL_MAX_BPS:
        return "informational"
    if bps < TIER_WARNING_MAX_BPS:
        return "warning"
    return "governance_review"


def _bi5_tf_key(tf: str) -> str:
    """Normalise any of `"1h" / "H1" / "1H"` into BI5's canonical `"H1"`.

    BI5's `_TF_TO_PANDAS` keys are `M1/M5/M15/M30/H1/H4/D1`. Callers
    who supply the CTS-style `"1h"` form must not silently miss the
    map.
    """
    t = (tf or "").strip()
    if not t:
        return t
    aliases = {
        "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
        "1h": "H1", "4h": "H4", "1d": "D1",
    }
    return aliases.get(t.lower(), t.upper())


def _index_by_ts(bars: Iterable[Any], *, is_candle: bool) -> Dict[str, Dict[str, float]]:
    """Normalise BI5-dict or CTS-Candle bars into `{ts: OHLCV dict}`."""
    out: Dict[str, Dict[str, float]] = {}
    for b in bars:
        if is_candle:
            ts = b.timestamp
            out[ts] = {
                "open":   float(b.open),
                "high":   float(b.high),
                "low":    float(b.low),
                "close":  float(b.close),
                "volume": float(b.volume),
            }
        else:
            ts = str(b.get("timestamp"))
            out[ts] = {
                "open":   float(b.get("open") or 0.0),
                "high":   float(b.get("high") or 0.0),
                "low":    float(b.get("low")  or 0.0),
                "close":  float(b.get("close") or 0.0),
                "volume": float(b.get("volume") or 0.0),
            }
    return out


def compare_bars(bi5_bars: List[Dict[str, Any]], cts_bars: List[Any]) -> List[BucketDiff]:
    """Deterministic bucket-by-bucket comparison. Pure fn.

    Args:
        bi5_bars: Output of `bi5_realism._resample_1m_to_tf(...)` —
            list of dicts with `timestamp`, `open`, `high`, `low`,
            `close`, `volume`.
        cts_bars: Output of `cts.resampler.resample_m1_to(...)[0]` —
            list of `Candle` dataclass objects.

    Returns:
        List of `BucketDiff` — one per unique timestamp across BOTH inputs.
        Sorted by `bucket_ts`.
    """
    bi5 = _index_by_ts(bi5_bars, is_candle=False)
    cts = _index_by_ts(cts_bars, is_candle=True)
    all_ts = sorted(set(bi5.keys()) | set(cts.keys()))
    out: List[BucketDiff] = []
    for ts in all_ts:
        a = bi5.get(ts)
        b = cts.get(ts)
        if a and b:
            # Base for bps: the average of open+close (prevents /0 on
            # weird synthetic prices and stays symmetric).
            base_a = (a["open"] + a["close"]) / 2.0
            base_b = (b["open"] + b["close"]) / 2.0
            base = (base_a + base_b) / 2.0 if base_a and base_b else max(base_a, base_b, 1e-12)
            d_o = _bps(a["open"]  - b["open"],  base)
            d_h = _bps(a["high"]  - b["high"],  base)
            d_l = _bps(a["low"]   - b["low"],   base)
            d_c = _bps(a["close"] - b["close"], base)
            mx  = max(abs(d_o), abs(d_h), abs(d_l), abs(d_c))
            out.append(BucketDiff(
                bucket_ts=ts,
                bi5_open=a["open"],  bi5_high=a["high"],  bi5_low=a["low"],  bi5_close=a["close"],  bi5_volume=a["volume"],
                cts_open=b["open"],  cts_high=b["high"],  cts_low=b["low"],  cts_close=b["close"],  cts_volume=b["volume"],
                delta_open_bps=d_o,  delta_high_bps=d_h,  delta_low_bps=d_l,  delta_close_bps=d_c,
                max_deviation_bps=mx,
                tier=_tier_for(mx),
                only_in=None,
            ))
        elif a:
            out.append(BucketDiff(
                bucket_ts=ts,
                bi5_open=a["open"], bi5_high=a["high"], bi5_low=a["low"], bi5_close=a["close"], bi5_volume=a["volume"],
                cts_open=None, cts_high=None, cts_low=None, cts_close=None, cts_volume=None,
                delta_open_bps=None, delta_high_bps=None, delta_low_bps=None, delta_close_bps=None,
                max_deviation_bps=None,
                tier="bi5_only",
                only_in="bi5",
            ))
        else:
            out.append(BucketDiff(
                bucket_ts=ts,
                bi5_open=None, bi5_high=None, bi5_low=None, bi5_close=None, bi5_volume=None,
                cts_open=b["open"], cts_high=b["high"], cts_low=b["low"], cts_close=b["close"], cts_volume=b["volume"],
                delta_open_bps=None, delta_high_bps=None, delta_low_bps=None, delta_close_bps=None,
                max_deviation_bps=None,
                tier="cts_only",
                only_in="cts",
            ))
    return out


def summarise(
    diffs: Sequence[BucketDiff],
    *,
    started_at: str,
    finished_at: str,
    symbol: str,
    timeframe: str,
    m1_row_count: int,
    bi5_bar_count: int,
    cts_bar_count: int,
) -> DiffSummary:
    """Aggregate a list of `BucketDiff` into a `DiffSummary` + pass/fail."""
    tier_counts: Dict[str, int] = {}
    max_dev = None
    both = 0
    bi5_only = 0
    cts_only = 0
    devs: List[float] = []
    for d in diffs:
        tier_counts[d.tier] = tier_counts.get(d.tier, 0) + 1
        if d.max_deviation_bps is not None:
            both += 1
            devs.append(d.max_deviation_bps)
            if max_dev is None or d.max_deviation_bps > max_dev:
                max_dev = d.max_deviation_bps
        elif d.only_in == "bi5":
            bi5_only += 1
        elif d.only_in == "cts":
            cts_only += 1
    devs_sorted = sorted(devs)
    informational = tier_counts.get("informational", 0)
    if both > 0:
        pass_ratio = informational / both
        pass_ok = pass_ratio >= PASS_INFORMATIONAL_RATIO and (
            tier_counts.get("governance_review", 0) == 0
        )
        reason = "ok" if pass_ok else _fail_reason(pass_ratio, tier_counts)
    else:
        pass_ratio = None
        pass_ok = None
        reason = "no_overlapping_buckets"
    return DiffSummary(
        started_at=started_at, finished_at=finished_at,
        symbol=symbol, timeframe=timeframe,
        m1_row_count=m1_row_count,
        bi5_bar_count=bi5_bar_count, cts_bar_count=cts_bar_count,
        total_comparisons=len(diffs),
        both_present=both, bi5_only=bi5_only, cts_only=cts_only,
        tier_counts=tier_counts,
        max_deviation_bps_observed=max_dev,
        p50_deviation_bps=_percentile(devs_sorted, 0.50),
        p95_deviation_bps=_percentile(devs_sorted, 0.95),
        p99_deviation_bps=_percentile(devs_sorted, 0.99),
        pass_informational_ratio=pass_ratio,
        pass_ok=pass_ok,
        reason=reason,
    )


def _fail_reason(ratio: float, tier_counts: Dict[str, int]) -> str:
    gov = tier_counts.get("governance_review", 0)
    warn = tier_counts.get("warning", 0)
    if gov > 0:
        return f"governance_review count>0 (n={gov})"
    if ratio < PASS_INFORMATIONAL_RATIO:
        return f"informational_ratio={ratio:.4f} < {PASS_INFORMATIONAL_RATIO}"
    if warn > 0:
        return f"warning count={warn}"
    return "ratio_below_threshold"


# ── Mongo replay entry point (production tool) ───────────────────────

async def run_diff_for_symbol(
    symbol: str,
    *,
    timeframe: str = "1h",
    days_back:  int = 30,
    db_getter=None,
) -> Tuple[DiffSummary, List[BucketDiff]]:
    """Run a full BI5 ↔ CTS diff for one symbol over the last `days_back` days.

    Reads canonical M1 from `market_data.bid_1m`, runs both resamplers,
    returns the summary + detailed per-bucket audit list.

    Never writes. Zero side effects on any collection.
    """
    started = datetime.now(timezone.utc).isoformat()
    # Resolve DB
    if db_getter is not None:
        db = db_getter()
    else:
        try:
            from engines.db import get_db
            db = get_db()
        except Exception as e:                                # pragma: no cover
            logger.warning("[bi5_bid_diff] db resolve failed: %s", e)
            return (
                DiffSummary(
                    started_at=started, finished_at=started,
                    symbol=symbol, timeframe=timeframe,
                    m1_row_count=0, bi5_bar_count=0, cts_bar_count=0,
                    reason="db_unavailable",
                ),
                [],
            )

    # Read M1 window
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=int(days_back))).isoformat()
    m1_rows: List[Dict[str, Any]] = []
    try:
        cur = db.market_data.find(
            {"symbol": symbol, "source": "bid_1m", "timeframe": "1m",
             "timestamp": {"$gte": since}},
            {"_id": 0, "timestamp": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        ).sort("timestamp", 1)
        async for row in cur:
            m1_rows.append({
                "timestamp": str(row.get("timestamp")),
                "open": float(row.get("open") or 0.0),
                "high": float(row.get("high") or 0.0),
                "low":  float(row.get("low")  or 0.0),
                "close": float(row.get("close") or 0.0),
                "volume": float(row.get("volume") or 0.0),
            })
    except Exception as e:                                    # noqa: BLE001
        logger.warning("[bi5_bid_diff] m1 read failed: %s", e)
        return (
            DiffSummary(
                started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                symbol=symbol, timeframe=timeframe,
                m1_row_count=0, bi5_bar_count=0, cts_bar_count=0,
                reason=f"m1_read_failed:{str(e)[:120]}",
            ),
            [],
        )
    if not m1_rows:
        return (
            DiffSummary(
                started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                symbol=symbol, timeframe=timeframe,
                m1_row_count=0, bi5_bar_count=0, cts_bar_count=0,
                reason="empty_m1_window",
            ),
            [],
        )

    # Resample via both paths — lazy imports to keep this module cheap
    from engines.bi5_realism import _resample_1m_to_tf
    from engines.cts.resampler import resample_m1_to
    from engines.cts.types import Candle

    bi5_bars, _partial = _resample_1m_to_tf(m1_rows, _bi5_tf_key(timeframe))

    m1_candles = [
        Candle(
            timestamp=r["timestamp"],
            open=r["open"], high=r["high"], low=r["low"],
            close=r["close"], volume=r["volume"],
        )
        for r in m1_rows
    ]
    cts_bars, _rep = resample_m1_to(m1_candles, timeframe.upper())

    diffs = compare_bars(bi5_bars, cts_bars)
    finished = datetime.now(timezone.utc).isoformat()
    summary = summarise(
        diffs,
        started_at=started, finished_at=finished,
        symbol=symbol, timeframe=timeframe,
        m1_row_count=len(m1_rows),
        bi5_bar_count=len(bi5_bars),
        cts_bar_count=len(cts_bars),
    )
    return summary, diffs


# ── CSV helpers for the detailed audit artifact ──────────────────────

CSV_HEADER = (
    "bucket_ts,tier,only_in,"
    "bi5_open,bi5_high,bi5_low,bi5_close,bi5_volume,"
    "cts_open,cts_high,cts_low,cts_close,cts_volume,"
    "delta_open_bps,delta_high_bps,delta_low_bps,delta_close_bps,max_deviation_bps"
)


def _fmt(v: Optional[float]) -> str:
    return "" if v is None else f"{v:.10g}"


def diffs_to_csv_rows(diffs: Iterable[BucketDiff]) -> List[str]:
    """Return the CSV rows (excluding header) for the detailed artifact."""
    rows: List[str] = []
    for d in diffs:
        rows.append(
            f"{d.bucket_ts},{d.tier},{d.only_in or ''},"
            f"{_fmt(d.bi5_open)},{_fmt(d.bi5_high)},{_fmt(d.bi5_low)},{_fmt(d.bi5_close)},{_fmt(d.bi5_volume)},"
            f"{_fmt(d.cts_open)},{_fmt(d.cts_high)},{_fmt(d.cts_low)},{_fmt(d.cts_close)},{_fmt(d.cts_volume)},"
            f"{_fmt(d.delta_open_bps)},{_fmt(d.delta_high_bps)},{_fmt(d.delta_low_bps)},{_fmt(d.delta_close_bps)},"
            f"{_fmt(d.max_deviation_bps)}"
        )
    return rows


def diffs_to_csv(diffs: Iterable[BucketDiff]) -> str:
    """Render the detailed audit artifact as a CSV document with header."""
    return "\n".join([CSV_HEADER, *diffs_to_csv_rows(diffs)]) + "\n"
