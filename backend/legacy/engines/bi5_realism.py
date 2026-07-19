"""Phase 27.3 / BI5 — Realism certification gate.

The architecturally-sanctioned BI5 consumer. ALL discovery / mutation /
OOS / validation work continues to run on BID candles (cheaper, dense
coverage). BI5 is consumed ONLY here, as a realism oracle that runs on
strategies which have already cleared seven cheap lifecycle gates
(entry to ``portfolio_worthy``).

What this module does
─────────────────────
For a single strategy hash we:
  1. Resolve the canonical library doc → strategy_text, pair, timeframe,
     and the BID-derived ``profit_factor`` we want to verify.
  2. Try to load BI5 candles via ``data_access.load_with_recovery``
     with ``source="bi5"`` and ``auto_recover=False``. **If BI5 data is
     missing we DO NOT trigger a Dukascopy download** — that is a
     deliberate ops decision the operator has to make. We mark the
     strategy with a ``BI5_DATA_MISSING`` flag and return; the lifecycle
     evaluator's flag-and-allow path then keeps the strategy at
     PORTFOLIO_WORTHY without demoting it.
  3. Re-run ``backtest_engine.run_backtest_logic`` on those BI5 bars.
  4. Compute ``pf_ratio = bi5_pf / cached_library_pf``.
  5. Persist the result onto the lifecycle doc's ``bi5_realism`` block.
  6. Return a compact summary suitable for the API and the orchestrator.

What this module does NOT do
────────────────────────────
* Discovery. Mutation. OOS. Validation. (All BID-only.)
* Auto-download Dukascopy ticks. (Operator-driven.)
* Promote / demote on its own. (Lifecycle gates own all stage flips —
  this module just feeds them better evidence.)

Design constraints honoured
───────────────────────────
* Additive: no existing engine changed; lifecycle_evaluator naturally
  reads the new ``bi5_realism`` block via the existing kwargs.
* Reversible: deleting this module removes BI5 progression but every
  prior gate (validated, stable, prop_safe, elite, portfolio_worthy)
  keeps working unchanged.
* Lightweight: a realism check is one BI5 read + one re-backtest; the
  weekly sweep iterates ~5–20 strategies max in steady state.
* Cached: ``pf_ratio`` is persisted; subsequent ticks read it from the
  lifecycle doc rather than re-running anything.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from engines import data_access, strategy_lifecycle as lc
from engines.backtest_engine import run_backtest_logic
from engines.db import get_db

logger = logging.getLogger(__name__)

# ── Module knobs ────────────────────────────────────────────────────
LIBRARY_COLL = "strategy_library"

# Realism PF ratio thresholds. The lifecycle module owns the gate
# semantics; we mirror the constants here so an operator looking at
# this module knows what each band means without cross-referencing.
PF_RATIO_DEPLOY_FLOOR  = 0.75    # ≥ this → eligible for deployment_ready
PF_RATIO_PARTIAL_FLOOR = 0.50    # below 0.75 but ≥ 0.50 → PARTIAL_REALISM
PF_RATIO_FAIL_FLOOR    = 0.50    # < this → BI5_FAIL + 30-day cool-down

# How long a stored realism reading is considered fresh. Beyond this
# the weekly sweep will refresh it. Default 60 days mirrors the design
# in `STRATEGY_LIFECYCLE_DESIGN_PHASE26_5.md` §6.
REALISM_FRESHNESS_DAYS = 60

# Minimum BI5 candle count for a meaningful re-backtest.
# Phase 27.4 — interpreted in **strategy-timeframe bars** (after
# resampling from the 1m base stream). An H1 strategy needs ≥200 H1
# bars (~12000 raw 1m bars ≈ 8 trading days); an M15 strategy needs
# ≥200 M15 bars (~3000 raw 1m bars ≈ 2 trading days).
MIN_BI5_BARS = 200

# Phase 27.4 — pandas resample alias map. Both representations honour
# left-closed, left-labelled boundary convention to match Dukascopy
# BID candle convention exactly. An H1 bar at 14:00 covers
# [14:00, 15:00).
_TF_TO_PANDAS = {
    "M1":  "1min",
    "M5":  "5min",
    "M15": "15min",
    "M30": "30min",
    "H1":  "1H",
    "H4":  "4H",
    "D1":  "1D",
}

# Stages that are eligible for realism evaluation. Anything below
# `portfolio_worthy` doesn't need BI5 yet (cheaper gates haven't
# converged) and below this threshold a realism reading would be churn.
ELIGIBLE_STAGES = ("portfolio_worthy", "deployment_ready")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _safe_num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# ── Fetch the canonical library doc by hash ─────────────────────────

async def _resolve_library_doc(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """Locate the library row for a strategy hash.

    Library docs are written by ``strategy_memory.record_performance``
    and identified by ``_id`` (ObjectId). We index from
    ``strategy_performance_history`` (which carries the hash) onto the
    library via ``library_id``. Falls back to a direct lookup if the
    hash matches a stored field (defensive — older docs sometimes
    persisted ``strategy_hash`` directly).
    """
    db = get_db()
    if not strategy_hash:
        return None

    # 1. Most recent perf-history row → library_id.
    hist = await db["strategy_performance_history"].find_one(
        {"strategy_hash": strategy_hash, "library_id": {"$ne": None}},
        {"_id": 0, "library_id": 1},
        sort=[("recorded_at", -1)],
    )
    lib_id = (hist or {}).get("library_id")
    if lib_id:
        try:
            doc = await db[LIBRARY_COLL].find_one(
                {"_id": ObjectId(str(lib_id))},
                {"_id": 0, "strategy_text": 1, "pair": 1, "timeframe": 1,
                 "profit_factor": 1, "total_trades": 1, "indicators": 1,
                 "type": 1},
            )
            if doc:
                doc["library_id"] = str(lib_id)
                return doc
        except Exception:                                  # pragma: no cover
            logger.debug("[bi5] ObjectId resolve failed for %s", lib_id)

    # 2. Defensive fallback — older docs.
    return await db[LIBRARY_COLL].find_one(
        {"strategy_hash": strategy_hash},
        {"_id": 0, "strategy_text": 1, "pair": 1, "timeframe": 1,
         "profit_factor": 1, "total_trades": 1, "indicators": 1, "type": 1},
    )


# ── Read BI5 bars (no auto-recover) ─────────────────────────────────

def _resample_1m_to_tf(
    raw_1m: List[Dict[str, Any]], target_tf: str,
) -> tuple[List[Dict[str, Any]], int]:
    """Aggregate 1m bars to ``target_tf`` using BID-aligned boundaries.

    OHLCV aggregation rules:
        open   = first
        high   = max
        low    = min
        close  = last
        volume = sum

    Boundary policy (operator decision Phase 27.4): left-closed,
    left-labelled — matches Dukascopy BID convention. An H1 bar at
    14:00 covers [14:00:00, 15:00:00).

    Returns ``(resampled_bars, partial_bars_dropped)``. Partial bars
    at the trailing edge (incomplete bucket because 1m data ends
    mid-bar) are dropped to avoid PF distortion. Pure function — no
    I/O, no side effects.
    """
    tf_alias = _TF_TO_PANDAS.get(target_tf.upper())
    if not tf_alias or not raw_1m:
        return [], 0

    # Lazy import to keep the module import-cheap when the resampler
    # path isn't exercised (e.g. M1 strategies pass through directly).
    import pandas as pd  # noqa: WPS433 — see docstring.

    df = pd.DataFrame(raw_1m)
    if df.empty or "timestamp" not in df.columns:
        return [], 0

    df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("ts").sort_index()

    grouped = df.resample(
        tf_alias, closed="left", label="left",
    ).agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])

    # Drop the trailing partial bucket when 1m data ends before the
    # bucket would close. The "−1 minute" guard absorbs the natural
    # 1-minute granularity of the source.
    partial_dropped = 0
    if not grouped.empty:
        last_1m_ts = df.index[-1]
        bucket_start = grouped.index[-1]
        bucket_end = bucket_start + pd.Timedelta(tf_alias)
        if last_1m_ts < bucket_end - pd.Timedelta("1min"):
            grouped = grouped.iloc[:-1]
            partial_dropped = 1

    out: List[Dict[str, Any]] = []
    for ts, row in grouped.iterrows():
        out.append({
            "timestamp": ts.isoformat(),
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": float(row["volume"]) if row["volume"] == row["volume"] else 0.0,
        })
    return out, partial_dropped


async def _load_and_resample_bi5(
    pair: str, target_tf: str,
) -> Dict[str, Any]:
    """Load bi5/1m bars and resample to ``target_tf``.

    Returns the same shape as ``data_access.load_with_recovery`` so the
    ``evaluate()`` flow downstream is unchanged:
        {status, bars, count, message, [resample]: {...}}

    Phase 27.4 architectural invariant: this is the ONLY path the
    realism evaluator uses to obtain BI5 bars. The 1m stream is the
    sole on-disk BI5 representation; higher TFs are derived on demand.
    """
    raw_1m = await data_access.load_bi5_1m_bars(pair)
    if not raw_1m:
        return {
            "status": "data_missing",
            "bars": [], "count": 0,
            "message": f"No BI5/1m data stored for {pair}.",
            "resample": {
                "applied": False, "from": "1m", "to": target_tf.upper(),
                "raw_1m_count": 0,
            },
        }

    canonical_tf = target_tf.upper()
    if canonical_tf in ("M1", "1M"):
        # Pass-through — strategies running at 1m use the raw stream
        # directly so no resample artefacts can be introduced.
        return {
            "status": "ok",
            "bars": raw_1m, "count": len(raw_1m),
            "message": "1m realism stream used directly.",
            "resample": {
                "applied": False, "from": "1m", "to": "M1",
                "raw_1m_count": len(raw_1m),
            },
        }

    bars_resampled, dropped_partial = _resample_1m_to_tf(raw_1m, canonical_tf)
    return {
        "status": "ok" if bars_resampled else "data_missing",
        "bars": bars_resampled, "count": len(bars_resampled),
        "message": (
            f"Resampled {len(raw_1m)} 1m bars → "
            f"{len(bars_resampled)} {canonical_tf} bars."
        ),
        "resample": {
            "applied":         True,
            "from":            "1m",
            "to":              canonical_tf,
            "raw_1m_count":    len(raw_1m),
            "boundary":        "left",
            "label":           "left",
            "partial_dropped": dropped_partial,
        },
    }


async def _load_bi5_bars(pair: str, timeframe: str) -> Dict[str, Any]:
    """Backwards-compatible wrapper. Phase 27.4 routes ALL BI5 reads
    through ``_load_and_resample_bi5`` so the realism evaluator only
    ever consumes the canonical 1m stream (resampled on demand).

    Phase 2 Stage 2.η (2026-02-19): when `BI5_CTS_ROUTING=true`, delegate
    to CTS so BI5 realism uses the SAME resampler as BID canonical. This
    closes the "two truths" gap between BI5-derived and BID-derived HTF.
    Zero behaviour change when flag off — legacy `_load_and_resample_bi5`
    path continues.
    """
    import os as _os
    _cts_route = (_os.environ.get("BI5_CTS_ROUTING") or "").strip().lower()
    if _cts_route in ("1", "true", "yes", "y", "on"):
        try:
            from engines.cts import get_cts
            window = await get_cts().load_candles(pair, timeframe)
            bars = [c.to_dict() for c in window.candles]
            return {
                "bars": bars,
                "resample": {
                    "from_tf": "1m",
                    "to_tf": timeframe,
                    "rows_in": 0,
                    "rows_out": len(bars),
                    "engine": "cts",
                    "provenance": window.provenance.__dict__,
                },
            }
        except Exception as e:  # noqa: BLE001
            # Fall through to legacy path on any error
            import logging as _lg
            _lg.getLogger(__name__).warning(
                "[bi5_realism] CTS route failed for %s/%s — falling back to legacy: %s",
                pair, timeframe, e,
            )
    return await _load_and_resample_bi5(pair, timeframe)


def _bars_to_arrays(bars: List[Dict[str, Any]]):
    """Translate the data_access bar shape into the parallel arrays the
    backtest engine expects (closes / highs / lows / timestamps).

    Bars already arrive sorted ascending by `time` from
    ``load_ohlc_bars``, so no resort is needed.
    """
    closes, highs, lows, ts = [], [], [], []
    for b in bars:
        c = _safe_num(b.get("close"))
        if c is None:
            continue
        closes.append(c)
        highs.append(_safe_num(b.get("high")) or c)
        lows.append(_safe_num(b.get("low"))  or c)
        ts.append(b.get("time"))
    return closes, highs, lows, ts


# ── Persist into the lifecycle doc ──────────────────────────────────

async def _persist_realism(
    strategy_hash: str,
    *,
    library_id: Optional[str],
    block: Dict[str, Any],
) -> None:
    """Upsert the ``bi5_realism`` block onto the lifecycle doc.

    We don't open a new collection — realism state lives ON the
    lifecycle doc so the evaluator can pick it up via the existing
    ``compute_lifecycle_state*`` kwargs.
    """
    db = get_db()
    update: Dict[str, Any] = {
        "bi5_realism":  block,
        "bi5_realism_updated_at": _now_iso(),
    }
    if library_id:
        update["library_id"] = library_id
    await db[lc.LIFECYCLE_COLL].update_one(
        {"strategy_hash": strategy_hash},
        {"$set": update},
        upsert=False,   # Do NOT create lifecycle docs from this path —
                        # only enrich rows the lifecycle evaluator already
                        # owns. Keeps responsibilities clean.
    )


# ── Public: evaluate a single strategy ──────────────────────────────

async def evaluate(
    strategy_hash: str,
    *,
    persist: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Run a BI5 realism check for one strategy.

    Returns a compact result dict; persists onto the lifecycle doc when
    ``persist=True`` and the strategy already has a lifecycle row (we
    never create lifecycle rows from here — the evaluator owns that).
    """
    out: Dict[str, Any] = {
        "strategy_hash": strategy_hash,
        "status":         "unknown",
        "pf_ratio":       None,
        "bi5_pf":         None,
        "cached_pf":      None,
        "sample_bars":    0,
        "last_checked_at": _now_iso(),
        "flag":           None,
        "skipped_reason": None,
    }
    if not strategy_hash:
        out["status"] = "skipped"
        out["skipped_reason"] = "missing_strategy_hash"
        return out

    # 1. Resolve library + lifecycle context.
    lib = await _resolve_library_doc(strategy_hash)
    if not lib or not lib.get("strategy_text"):
        out["status"] = "skipped"
        out["skipped_reason"] = "library_doc_not_found"
        return out
    cached_pf = _safe_num(lib.get("profit_factor"))
    if cached_pf is None or cached_pf <= 0:
        out["status"] = "skipped"
        out["skipped_reason"] = "library_pf_unavailable"
        return out
    out["cached_pf"] = cached_pf

    pair = (lib.get("pair") or "").upper()
    timeframe = (lib.get("timeframe") or "").upper()
    if not pair or not timeframe:
        out["status"] = "skipped"
        out["skipped_reason"] = "missing_pair_or_timeframe"
        return out

    # 2. Honour freshness when not forcing a refresh.
    if not force_refresh and persist:
        existing = await lc.get_lifecycle(strategy_hash) or {}
        prior_block = existing.get("bi5_realism") or {}
        last = prior_block.get("last_checked_at")
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                age_days = (_now() - last_dt).total_seconds() / 86400.0
                if age_days < REALISM_FRESHNESS_DAYS:
                    out.update(prior_block)
                    out["status"] = "fresh_cache"
                    return out
            except (TypeError, ValueError):                # pragma: no cover
                pass

    # 3. Load BI5 bars — Phase 27.4: 1m stream → resample to strategy TF.
    # We call through the `_load_bi5_bars` wrapper (rather than
    # `_load_and_resample_bi5` directly) so existing test patches that
    # target `_load_bi5_bars` continue to work — preserving the
    # additive-only architectural promise.
    bars_resp = await _load_bi5_bars(pair, timeframe)
    bars = bars_resp.get("bars") or []
    out["sample_bars"] = int(bars_resp.get("count") or len(bars))
    if (bars_resp.get("status") != "ok") or len(bars) < MIN_BI5_BARS:
        out["status"] = "data_missing"
        out["flag"] = "BI5_DATA_MISSING"
        block = {
            "status":          "data_missing",
            "pf_ratio":        None,
            "bi5_pf":          None,
            "cached_pf":       cached_pf,
            "sample_bars":     out["sample_bars"],
            "last_checked_at": out["last_checked_at"],
            "pair":            pair,
            "timeframe":       timeframe,
            "min_required":    MIN_BI5_BARS,
            "resample":        bars_resp.get("resample"),
        }
        if persist:
            await _persist_realism(
                strategy_hash, library_id=lib.get("library_id"), block=block,
            )
        return out

    # 4. Re-run the backtest on BI5 bars.
    closes, highs, lows, ts = _bars_to_arrays(bars)
    if len(closes) < MIN_BI5_BARS:
        out["status"] = "data_missing"
        out["flag"] = "BI5_DATA_MISSING"
        return out

    try:
        bt = run_backtest_logic(
            strategy_text=lib.get("strategy_text") or "",
            pair=pair, timeframe=timeframe,
            external_prices=closes,
            external_highs=highs,
            external_lows=lows,
            external_timestamps=ts,
            data_source="bi5",
        )
    except Exception as e:                                  # pragma: no cover
        logger.exception("[bi5] backtest failed for %s", strategy_hash)
        out["status"] = "error"
        out["skipped_reason"] = f"backtest_error:{str(e)[:120]}"
        return out

    bi5_pf = _safe_num(bt.get("profit_factor"))
    out["bi5_pf"] = bi5_pf
    if bi5_pf is None:
        out["status"] = "error"
        out["skipped_reason"] = "no_pf_from_backtest"
        return out

    # 5. Compute ratio + classify.
    pf_ratio = bi5_pf / cached_pf if cached_pf > 0 else 0.0
    pf_ratio = round(pf_ratio, 4)
    out["pf_ratio"] = pf_ratio

    if pf_ratio < PF_RATIO_FAIL_FLOOR:
        status = "fail"
        flag = "BI5_FAIL"
    elif pf_ratio < PF_RATIO_DEPLOY_FLOOR:
        status = "partial"
        flag = "PARTIAL_REALISM"
    else:
        status = "ok"
        flag = None
    out["status"] = status
    out["flag"] = flag

    block = {
        "status":          status,
        "pf_ratio":        pf_ratio,
        "bi5_pf":          bi5_pf,
        "cached_pf":       cached_pf,
        "sample_bars":     out["sample_bars"],
        "bi5_total_trades": int(bt.get("total_trades") or 0),
        "last_checked_at": out["last_checked_at"],
        "pair":            pair,
        "timeframe":       timeframe,
        "resample":        bars_resp.get("resample"),
    }
    if persist:
        await _persist_realism(
            strategy_hash, library_id=lib.get("library_id"), block=block,
        )
    return out


# ── Public: run a sweep over the eligible cohort ────────────────────

async def sweep_realism(
    *,
    force_refresh: bool = False,
    limit: int = 200,
) -> Dict[str, Any]:
    """Iterate ``portfolio_worthy ∪ deployment_ready`` and refresh
    realism for any row whose last reading is missing or stale.

    Cheap by design — at steady state the eligible cohort is small
    (per the design's convergence math, ~5–20 strategies). The weekly
    cron in ``orchestrator_scheduler`` calls this once on Sunday
    03:00 UTC.

    ``force_refresh=True`` ignores freshness and re-checks every row.
    """
    db = get_db()
    started_at = _now_iso()
    cur = db[lc.LIFECYCLE_COLL].find(
        {"current_stage": {"$in": list(ELIGIBLE_STAGES)}},
        {"_id": 0, "strategy_hash": 1, "current_stage": 1, "bi5_realism": 1},
        limit=int(limit),
    )
    rows = [d async for d in cur]

    summary = {
        "started_at":       started_at,
        "finished_at":      None,
        "force_refresh":    bool(force_refresh),
        "scanned":          len(rows),
        "evaluated":        0,
        "data_missing":     0,
        "ok":               0,
        "partial":          0,
        "fail":             0,
        "fresh_cache":      0,
        "skipped":          0,
        "errors":           0,
        "results":          [],
    }
    for r in rows:
        h = r.get("strategy_hash")
        try:
            res = await evaluate(
                h, persist=True, force_refresh=force_refresh,
            )
        except Exception as e:                              # pragma: no cover
            logger.exception("[bi5] sweep eval failed for %s", h)
            summary["errors"] += 1
            summary["results"].append({
                "strategy_hash": h, "status": "error", "error": str(e)[:200],
            })
            continue
        summary["evaluated"] += 1
        st = res.get("status") or "unknown"
        bucket = {
            "ok":            "ok",
            "partial":       "partial",
            "fail":          "fail",
            "data_missing":  "data_missing",
            "fresh_cache":   "fresh_cache",
        }.get(st, "skipped")
        summary[bucket] = summary.get(bucket, 0) + 1
        summary["results"].append({
            "strategy_hash": h,
            "stage":         r.get("current_stage"),
            "status":        st,
            "pf_ratio":      res.get("pf_ratio"),
            "flag":          res.get("flag"),
        })

    summary["finished_at"] = _now_iso()
    return summary


async def get_realism(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """Read the persisted ``bi5_realism`` block from the lifecycle doc."""
    if not strategy_hash:
        return None
    doc = await lc.get_lifecycle(strategy_hash)
    if not doc:
        return None
    return doc.get("bi5_realism") or None


# ── Stale-rows helper used by the sweep job (for visibility) ────────

async def stale_realism_count(
    freshness_days: int = REALISM_FRESHNESS_DAYS,
) -> int:
    """Count rows in the eligible cohort whose realism reading is older
    than ``freshness_days`` (or absent). Used by ops health checks."""
    db = get_db()
    cutoff_iso = (_now() - timedelta(days=int(freshness_days))).isoformat()
    n = await db[lc.LIFECYCLE_COLL].count_documents({
        "current_stage": {"$in": list(ELIGIBLE_STAGES)},
        "$or": [
            {"bi5_realism": {"$exists": False}},
            {"bi5_realism.last_checked_at": {"$lt": cutoff_iso}},
            {"bi5_realism.last_checked_at": {"$exists": False}},
        ],
    })
    return int(n)
