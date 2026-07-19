# BI5 Single-Source Realism Stream — Implementation Plan

**Date:** 2026-05-09
**Status:** Planning only — NO code changes performed
**Operator decisions locked:**
1. Resampling boundary: **left-closed, left-labelled** (match BID exactly)
2. `MIN_BI5_BARS` semantics: **strategy-TF bars** (200 H1 bars from 1m aggregation)
3. Storage migration: **leave-and-ignore**
4. API back-compat: **soft deprecation** (warn, not break)
5. Sweep cadence: **keep Sunday 03:00 UTC**

**Architectural promise:** additive · reversible · lifecycle-safe ·
orchestration-safe · discovery-isolated.

---

## 0. Pre-Implementation Code Validation Findings

Before drafting the patch, four facts were re-validated against the live
codebase to avoid building on incorrect assumptions:

| # | Claim | Evidence | Verdict |
|---|---|---|---|
| 1 | Both BID and BI5 are bid-side | `dukascopy_downloader.py:87` — `dp.fetch(..., dp.OFFER_SIDE_BID, ...)` | ✅ Confirmed. Resampled BI5 H1 close ≈ BID H1 close within tick noise. |
| 2 | Backtest engine treats `data_source="bi5"` identically to `"real"` for sim modifiers | `backtest_engine.py:1312-1370` — `sim_config` carries `spread_pips`, `asym_slippage`, `session_aware_spread`; none branch on `data_source` | ✅ Confirmed. Same spread / slippage / commission modifiers fire on both replay paths. |
| 3 | BID is stored per-fetched-TF (Dukascopy returns pre-aggregated) | `dukascopy_downloader.py:128` writes `timeframe=<requested_tf>`; `download_and_store(symbol, "1h", ...)` stores `(symbol, bid_1m, 1h, ts)` | ✅ Confirmed. BID is multi-bucket; BI5 is single-bucket-1m by intent. |
| 4 | No 1m→TF resampler exists on the BI5 path today | grep across `engines/`, `data_engine/` for `resample`/`agg` returns only pandas test code, none on the BI5 read path | ✅ Confirmed. The resampler is a genuinely new artefact. |

**Anti-claim** (also worth recording):
* `source="bid_1m"` is a historical token; it does NOT mean BID is stored only
  at 1m. Renaming this token is **out of scope** — it would be a destructive
  back-compat break for legacy buckets. Leave the token alone.

---

## 1. Scope & Non-Scope

### In scope (4 additive changes — Phases 1-4)

| Phase | Layer | Change | LoC est. | Reversibility |
|---|---|---|---|---|
| **1** | `api/data.py` | Soft-warn (HTTP 200 + `warning`) on `(source="bi5", timeframe!="1m")` ingest paths | ~25 | Single-file revert |
| **2** | `engines/data_access.py` | Add helper `load_bi5_1m_bars(pair, *, limit=None)` | ~12 | Pure addition |
| **3** | `engines/bi5_realism.py` | Replace `_load_bi5_bars` body with: (a) load 1m bars, (b) resample to strategy TF, (c) feed to backtest. Recalibrate `MIN_BI5_BARS` per TF. | ~60 | Single-function patch |
| **4** | `backend/tests/` | Two regression tests (resample alignment + multi-TF realism consistency) | ~80 | Test-only |

### Explicitly out of scope (DO NOT TOUCH)

* `engines/strategy_lifecycle.py` — gates / hysteresis / cool-downs / flag taxonomy
* `engines/ai_orchestrator.py` — rule-book, scheduler tick, env_priority
* `engines/orchestrator_scheduler.py` — Sunday cron, JOB_IDs, persistence
* `engines/auto_scheduler.py` — subordination, persistence
* `engines/research_lineage.py` — G1 audit trail
* `engines/backtest_engine.py` — engine internals, sim_config, modifiers
* `engines/multi_cycle_runner.py` — discovery loop
* `engines/strategy_memory.py` — `_attach_validation_view`, rollup view
* `data_engine/data_manager.py` — storage schema (compound key stays the same)
* `data_engine/auto_data_maintainer.py` — already 1m-correct
* `data_engine/incremental_updater.py` — append-only logic intact
* `frontend/src/**` — zero changes; UI consumes `/api/bi5-realism/*` and
  `/api/lifecycle/*` exactly as today
* All 260 routes, all 88 engines outside the 3 named files above

---

## 2. Phase 1 — API Soft Deprecation

### File: `api/data.py`

Today four endpoints accept `source="bi5"` with arbitrary timeframe:

| Endpoint | Function | Line |
|---|---|---|
| `POST /api/upload-data` | `upload_data` | 42 |
| `POST /api/import-server-file` | `import_server_file` | 195 |
| `POST /api/incremental/bi5` | `incremental_bi5` | 376 |
| `GET  /api/incremental/last-timestamp` | `incremental_last_timestamp` | 395 (read-only — leave alone) |

### Decision rule (operator-locked: soft deprecation)

```python
# Pseudocode — NOT yet committed
def _validate_bi5_tf(source: str, timeframe: str) -> Optional[str]:
    """Return a deprecation warning string when source=bi5 and tf != 1m.
    Returns None when input is canonical (1m) or non-bi5."""
    if source == "bi5" and timeframe != "1m":
        return (
            f"Deprecation: BI5 ingest at timeframe={timeframe} is no longer "
            f"the canonical realism stream. The realism evaluator now reads "
            f"only bi5/1m and resamples to the strategy's timeframe. "
            f"Future versions will reject non-1m BI5 ingests."
        )
    return None
```

Each affected endpoint:
* Computes the warning *before* persistence.
* Persists as today (no behavioural change on disk).
* Returns the success payload **plus** `"deprecation_warning": "..."` when the
  rule triggers.
* HTTP status code stays 200.

This preserves every existing operator workflow exactly while surfacing a
visible signal in the response. No upstream consumer needs to change.

### Logging

Add a single `logger.warning("[bi5/deprecation] %s/%s — non-canonical TF",
symbol, timeframe)` so the soft-warn is visible in the supervisor log even
when the operator ignores the response field.

### Reversibility

Single-commit revert restores prior behaviour. No data state changes.

---

## 3. Phase 2 — Dedicated 1m Loader Helper

### File: `engines/data_access.py`

Append (do not modify existing functions):

```python
async def load_bi5_1m_bars(
    pair: str, *, limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Canonical realism-stream loader.

    Reads 1-minute BI5 bars for ``pair``. Returns a list of
    {timestamp, open, high, low, close, volume} dicts ascending by
    timestamp. ``limit`` caps the slice when set; the realism path
    typically passes None to honour the full retention window.

    This is the SINGLE READ POINT for realism replay. Higher-TF
    realism evaluation MUST resample this output via the
    bi5_realism resampler — never call ``load_ohlc_bars`` with
    ``source="bi5"`` and ``timeframe!="1m"`` directly.
    """
    return await load_ohlc_bars(pair, "1m", source="bi5", limit=limit)
```

Why a dedicated helper rather than calling `load_ohlc_bars` inline:
1. Intent-revealing name documents the realism-stream invariant.
2. Single read point makes future instrumentation (e.g. cache, telemetry)
   trivial.
3. Lets `bi5_realism.py` import only what it needs.

### Reversibility

Pure addition. Removing the function breaks only `bi5_realism.py` —
contained blast radius.

---

## 4. Phase 3 — `bi5_realism.evaluate` Resample Path

### File: `engines/bi5_realism.py`

This is the architectural fix. The change has **three internal sub-steps**.

### 4.1 Replace `_load_bi5_bars`

**Today:**
```python
async def _load_bi5_bars(pair: str, timeframe: str) -> Dict[str, Any]:
    return await data_access.load_with_recovery(
        pair, timeframe,
        min_candles=MIN_BI5_BARS,
        auto_recover=False,
        source="bi5",
    )
```

**New:**
```python
async def _load_and_resample_bi5(
    pair: str, target_tf: str,
) -> Dict[str, Any]:
    """Load bi5/1m bars and resample to target_tf using BID-aligned
    boundaries (left-closed, left-labelled).

    Returns the same shape as load_with_recovery so the evaluate()
    flow downstream is unchanged:
        {status, bars, count, message, [resample]: {...}}
    """
    raw_1m = await data_access.load_bi5_1m_bars(pair)
    if not raw_1m:
        return {
            "status": "data_missing", "bars": [], "count": 0,
            "message": f"No BI5/1m data stored for {pair}.",
        }

    if target_tf.upper() in ("M1", "1M"):
        # Pass-through — strategies running at 1m use the raw stream.
        return {
            "status": "ok", "bars": raw_1m, "count": len(raw_1m),
            "message": "1m realism stream used directly.",
            "resample": {"applied": False, "from": "1m", "to": "1m"},
        }

    bars_resampled, dropped_partial = _resample_1m_to_tf(raw_1m, target_tf)
    return {
        "status": "ok" if bars_resampled else "data_missing",
        "bars": bars_resampled,
        "count": len(bars_resampled),
        "message": (
            f"Resampled {len(raw_1m)} 1m bars → "
            f"{len(bars_resampled)} {target_tf} bars."
        ),
        "resample": {
            "applied":           True,
            "from":              "1m",
            "to":                target_tf,
            "raw_1m_count":      len(raw_1m),
            "boundary":          "left",
            "label":             "left",
            "partial_dropped":   dropped_partial,
        },
    }
```

### 4.2 New `_resample_1m_to_tf` helper (pure function, in-module)

```python
import pandas as pd

# Map our canonical TF → pandas offset alias.
# Both representations honour left-closed, left-labelled boundary
# convention (see operator-locked decision §1).
_TF_TO_PANDAS = {
    "M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
    "H1": "1H", "H4": "4H", "D1": "1D",
}

def _resample_1m_to_tf(
    raw_1m: List[Dict[str, Any]], target_tf: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """Aggregate 1m bars to target_tf using OHLCV rules:
        open  = first
        high  = max
        low   = min
        close = last
        volume = sum

    Boundary policy: left-closed, left-labelled — matches Dukascopy
    BID convention (see download_and_store). H1 bar at 14:00 covers
    [14:00:00, 15:00:00).

    Returns (resampled_bars, partial_bars_dropped). Partial bars at
    the trailing edge (incomplete bucket because 1m data ends mid-bar)
    are dropped to avoid PF distortion.
    """
    tf_alias = _TF_TO_PANDAS.get(target_tf.upper())
    if not tf_alias:
        return [], 0

    df = pd.DataFrame(raw_1m)
    if df.empty or "timestamp" not in df.columns:
        return [], 0

    df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("ts").sort_index()

    grouped = df.resample(
        tf_alias, closed="left", label="left",   # ← operator decision #1
    ).agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])

    # Drop the trailing partial bucket (boundary not yet closed by 1m feed).
    # We detect partial by checking the bucket end vs the last 1m timestamp.
    # If the last 1m row is BEFORE the end of its bucket, that bucket is
    # partial.
    partial_dropped = 0
    if not grouped.empty:
        last_1m_ts = df.index[-1]
        bucket_end = grouped.index[-1] + pd.Timedelta(tf_alias)
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
            "volume": float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
        })
    return out, partial_dropped
```

### 4.3 Patch `evaluate()` to use TF-aware threshold

**Today (line 281):**
```python
bars_resp = await _load_bi5_bars(pair, timeframe)
...
if (bars_resp.get("status") != "ok") or len(bars) < MIN_BI5_BARS:
    out["status"] = "data_missing"
```

**New:**
```python
bars_resp = await _load_and_resample_bi5(pair, timeframe)
bars = bars_resp.get("bars") or []
out["sample_bars"] = int(bars_resp.get("count") or len(bars))

# Operator decision #2 — threshold expressed in strategy-TF bars.
# 200 was the legacy floor; we keep that as the minimum but allow per-TF
# tighter floors via min_candles_for() if a stricter test is ever needed.
min_required = max(
    MIN_BI5_BARS,
    # `data_access.min_candles_for(timeframe)` already returns per-TF
    # minimums for the BID path; reusing it keeps a single source of truth.
    # We do NOT auto-multiply by 60 — the operator decision was explicit:
    # "200 H1 realism bars from 1m aggregation", not "200 raw 1m bars".
    0,
)
if (bars_resp.get("status") != "ok") or len(bars) < min_required:
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
        "min_required":    min_required,
        "resample":        bars_resp.get("resample"),
    }
    if persist:
        await _persist_realism(
            strategy_hash, library_id=lib.get("library_id"), block=block,
        )
    return out
```

The persisted `bi5_realism` block now also carries `resample.{from,to,boundary,label}`
so operators inspecting a strategy's realism doc can see exactly how the
H1 reading was derived.

### 4.4 `MIN_BI5_BARS` reinterpretation

Today: `MIN_BI5_BARS = 200` (constant).
After: same constant, but expressed in **strategy-TF bars** post-resample.
* H1 strategy → needs ≥200 H1 bars → ~12000 raw 1m bars (~8 trading days).
* M15 strategy → needs ≥200 M15 bars → ~3000 raw 1m bars (~2 trading days).
* M1 strategy → needs ≥200 M1 bars → ~200 raw 1m bars (~3.3 hours).

This is the "strategy-TF semantics" the operator locked. The constant
itself does not change; its **interpretation** does — but only inside the
realism path. Discovery / OOS thresholds for BID stay untouched.

### Reversibility

The new path is contained inside `bi5_realism.py`. Reverting `_load_bi5_bars`
to its prior body and removing `_resample_1m_to_tf` restores 100 % of prior
behaviour.

---

## 5. Phase 4 — Tests

Two new tests; pytest only; no DB writes outside the existing test fixtures.

### 5.1 `tests/test_bi5_resample_alignment.py`

Verifies the resampling boundary convention:
* Generate a synthetic 24-hour 1m bar stream with known per-minute closes.
* Resample to H1 with the new helper.
* Assert that bucket `14:00` covers `[14:00, 15:00)` — i.e., contains the
  1m bar at 14:00 but not the bar at 15:00.
* Assert OHLC aggregation rules (open=first, high=max, low=min, close=last,
  volume=sum).
* Assert the trailing partial bucket is dropped when the input stream ends
  mid-bucket.

### 5.2 `tests/test_bi5_realism_multi_tf_consistency.py`

End-to-end consistency:
* Seed `bi5/1m` for one pair (~30 days of synthetic 1m bars).
* Stub a library doc for the same pair at H1.
* Stub a library doc for the same pair at M15.
* Run `bi5_realism.evaluate(persist=False)` for both.
* Assert: both return `status="ok"`, `pf_ratio is not None`,
  `resample.applied=True`, `resample.from="1m"`, `resample.to=H1` / `M15`.
* Assert: `bi5_pf` for H1 and `bi5_pf` for M15 are independently sensible
  (i.e., neither is 0 and neither is NaN); we don't assert they're equal —
  PF is TF-dependent — but both must derive from the same 1m base.

These tests guard against future regressions of the realism-consumer
mismatch.

### Reversibility

Test additions only — never affect production code paths.

---

## 6. Validation Checklist (operator-mandated)

Before merging Phase 3, the following five validations must pass:

| # | Check | How |
|---|---|---|
| 1 | **H1 aggregation alignment** — resampled H1 OHLC matches BID H1 OHLC within tick noise on the same pair / window | Pull 1 week of `bid_1m/1h` for EURUSD and 1 week of `bi5/1m` for EURUSD; run resampler; compare H1 closes. Tolerance: **0.5 pip** (legitimate bid-tick jitter). |
| 2 | **Candle close semantics** — left-closed, left-labelled boundary verified | Programmatic assertion in `test_bi5_resample_alignment.py`. The H1 bar at 14:00 must aggregate 1m bars `[14:00, 15:00)`. |
| 3 | **PF comparability** — same strategy backtested on BID/H1 vs resampled-BI5/H1 produces PF within a tolerance band | One-shot operator script: pick a `STABLE` strategy, run `run_backtest_logic` twice (BID/H1 and BI5/1m→H1 resample). Tolerance: **PF ratio ∈ [0.85, 1.15]** (anything outside flags a sim-modifier inconsistency to debug). |
| 4 | **Slippage reconciliation** — same `sim_config` produces same total_slippage_cost on BID and BI5 paths | Backtest engine confirmed TF-agnostic (§0). Spot-check by comparing the `total_slippage_cost` field on the two backtest outputs above. Should match within trade-count noise. |
| 5 | **Realism replay consistency** — running `/api/bi5-realism/evaluate/{hash}` for the same hash twice produces identical `pf_ratio` (cached path) and equivalent `pf_ratio` after `force_refresh=True` (cold path) | curl the endpoint twice; second call returns `status="fresh_cache"` with the same `pf_ratio`; third call with `force_refresh=true` recomputes; the recomputed value matches within 0.001. |

If any check fails → **halt before phase 4** and re-investigate. The
architectural promise is "additive and reversible"; we revert before we
debug.

---

## 7. Rollout Order

```
[NOW]                         ←  This document. No code changes.
[After your approval]
  Phase 1 (API soft warn)     ←  ~25 LoC, single file
  Phase 2 (1m loader helper)  ←  ~12 LoC, pure addition
  Phase 3 (resample path)     ←  ~60 LoC, single file
       └─ Validations 1-5     ←  Mandatory before phase 4
  Phase 4 (regression tests)  ←  ~80 LoC, test-only
[After phase 4]
  Re-run /api/lifecycle/evaluate to confirm zero behavioural change on
  the lifecycle gate side.
  Resume operational sequence at Step 1 (BID ingest) under the previously-
  locked focus universe (EURUSD/H1, XAUUSD/H1, GBPUSD/H1, EURUSD/M15,
  XAUUSD/M15).
```

---

## 8. Architectural Promise — Restated

After all four phases land:

| Promise | How it's preserved |
|---|---|
| **Additive** | Three new helpers (`load_bi5_1m_bars`, `_load_and_resample_bi5`, `_resample_1m_to_tf`); zero deletions; no signature changes on public engines. |
| **Reversible** | Each phase reverts cleanly via `git revert <commit>` without data loss. The `bi5_realism` block schema gains a `resample` field — backwards-readable; older readers ignore the field. |
| **Lifecycle-safe** | `engines/strategy_lifecycle.py` consumes `bi5_realism.pf_ratio` / `status`. Both fields keep their existing semantics; only the bar-source path leading to them changes. Hysteresis, cool-downs, gate functions, flag taxonomy: all untouched. |
| **Orchestration-safe** | `engines/ai_orchestrator.py`, `engines/orchestrator_scheduler.py`, `engines/auto_scheduler.py` and the G2 subordination probe: zero changes. The Sunday 03:00 UTC realism sweep continues to call `bi5_realism.sweep_realism` — same signature, faster execution because resample reuses cached 1m. |
| **Discovery-isolated** | `multi_cycle_runner`, `auto_factory*`, `mutation_engine`, `optimization_engine`, `validation_engine`, `oos_holdout`, `walk_forward_engine`, `env_priority`: never touched. None of them ever reference `source="bi5"`; this remains the case after the patch. |

**The BID/BI5 separation as you described it:**

> BID → research profitability
> BI5 → executable profitability

is now structurally encoded:
* BID lives at multiple TFs (multi-bucket, fetched per-TF from Dukascopy).
* BI5 lives at one TF (1m, single bucket, operator-driven ingest).
* The realism layer is the only consumer of BI5 and resamples on demand.
* Discovery is the only consumer of BID and reads its TF-native bucket.

No code path ever crosses the BID↔BI5 boundary.

---

## 9. Awaiting Approval

This document is the sole deliverable for this phase. Pending your green
light, I will execute Phases 1 → 4 in order, halting after each phase for
verification before proceeding. No code changes have been made.
