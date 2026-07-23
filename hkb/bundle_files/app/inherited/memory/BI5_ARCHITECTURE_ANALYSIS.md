# BI5 Realism Stream — Architectural Analysis

**Date:** 2026-05-09
**Mode:** Inspection only — no code changes proposed for this phase
**Scope:** Verify whether BI5 ingestion is timeframe-fragmented and whether the
realism path can be cleanly reframed as a single 1-minute realism stream.

---

## 1. TL;DR — Your Diagnosis Is Correct

The BI5 layer is **physically separated from BID at the storage level** (the
`(symbol, source, timeframe, timestamp)` compound key guarantees no row-level
overlap), **but it is logically fragmented by `timeframe`**. The intent —
"BI5 = single realism stream" — is reflected only partially:

* The auto-maintainer hard-codes `incremental_update_bi5(symbol, "1m")` ✅
* The alignment health check hard-codes `bi5_timeframe="1m"` ✅
* But the realism evaluator (`engines/bi5_realism.evaluate`) reads the
  **strategy's library timeframe** (e.g. `H1`) and asks for `bi5/1h` rows
  directly — bypassing any 1m base stream. ❌
* And the API surface still lets BI5 be uploaded / downloaded under any of the
  7 timeframes, so an operator can inadvertently fragment storage. ❌

The "duplicates skipped" symptom is consistent with this: when an H1 strategy
is realism-checked, the loader finds zero rows in the `bi5/1h` bucket, and any
operator-driven attempt to "fix" it by re-downloading or re-uploading hits the
`bi5_ingest_log` idempotency layer (or the `(symbol, source, timeframe, ts)`
upsert key) — surfacing as `already_ingested` / "matched" preservation rather
than fresh rows.

**No rewrites recommended yet** — first step is to socialise the proposed
architecture, then make additive, reversible changes in a separate phase.

---

## 2. Current State — Inspected

### 2.1 Storage uniqueness (data_manager.py)

```python
# data_engine/data_manager.py:135
UpdateOne(
    {"symbol": symbol, "source": source, "timeframe": timeframe, "timestamp": r["timestamp"]},
    {update_op: r},
    upsert=True,
)
```

* Compound key: **(symbol, source, timeframe, timestamp)**.
* `bid_1m` and `bi5` rows therefore live in disjoint partitions ✅ — BID/BI5
  separation IS preserved on disk.
* But within `source="bi5"`, the `timeframe` segment fragments the stream
  across as many buckets as the operator chooses to upload into.

### 2.2 Ingestion API surface (api/data.py)

```python
ALLOWED_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALLOWED_SOURCES = ["bid_1m", "bi5"]
```

Affected endpoints:
* `POST /api/upload-data`
* `POST /api/import-server-file`
* `POST /api/incremental/bi5` (default `timeframe="1m"`, but accepts any)
* `POST /api/data/download-data` (no `source` field — only fetches BID, but
  the symmetric BI5 path inherits the same TF list when wired)
* `GET  /api/data-coverage` (timeframes_to_scan = ALLOWED_TIMEFRAMES for BI5
  too)

**The API does not enforce "BI5 ⇒ timeframe == 1m"**. An operator pointing
the upload form at `(EURUSD, bi5, H1)` will succeed and create a fragmented
`bi5/1h` bucket that no other code path is responsible for keeping consistent
with `bi5/1m`.

### 2.3 Auto-maintainer (data_engine/auto_data_maintainer.py)

```python
# Lines 207, 240
result = await incremental_update_bi5(symbol, "1m")
await update_coverage(symbol, "1m", source="bi5")
```

The automated track is **already 1m-only** ✅ — implicitly treats BI5 as a
single-resolution stream. But because the API is permissive, manual operations
can drift from this convention.

### 2.4 Alignment health check (data_engine/incremental_updater.py)

```python
# Line 549
async def validate_bid_bi5_alignment(
    symbol: str, bid_timeframe: str = "1m", bi5_timeframe: str = "1m",
) -> Dict[str, Any]:
```

Defaults to `bi5_timeframe="1m"` ✅ — the design intent of "BI5 lives at 1m"
is documented here but not enforced anywhere upstream.

### 2.5 Realism evaluator (engines/bi5_realism.py) — **the architectural mismatch**

```python
# Lines 257–262
pair = (lib.get("pair") or "").upper()
timeframe = (lib.get("timeframe") or "").upper()    # ← H1 / M15 / etc.
if not pair or not timeframe:
    out["status"] = "skipped"
    out["skipped_reason"] = "missing_pair_or_timeframe"
    return out

# Line 281 — uses the strategy's TF directly
bars_resp = await _load_bi5_bars(pair, timeframe)
```

Then `_load_bi5_bars` calls:

```python
# Lines 157–162
return await data_access.load_with_recovery(
    pair, timeframe,                # ← H1
    min_candles=MIN_BI5_BARS,       # 200
    auto_recover=False,
    source="bi5",
)
```

Which lands in `data_access.load_ohlc_bars`:

```python
# engines/data_access.py:98–103
data_tf = TIMEFRAME_MAP.get(timeframe, timeframe.lower())   # H1 → 1h
cursor = db.market_data.find(
    {"symbol": pair, "source": source, "timeframe": data_tf},
    ...
)
```

**Outcome:**
* For an H1 strategy, the evaluator asks Mongo for `(EURUSD, bi5, 1h)` rows.
* The auto-maintainer / incremental ingest only ever wrote `(EURUSD, bi5, 1m)`.
* The query returns 0 → `status="data_missing"` → strategy gets the
  `BI5_DATA_MISSING` flag → realism gate is permanently un-evaluable.
* The 1m BI5 data we DID ingest sits unused.

**There is NO 1m → higher-TF resampler anywhere on the BI5 path.** The
realism layer assumes BI5 is pre-bucketed at the same TF as the strategy.

### 2.6 Backtest engine consumption (engines/backtest_engine.py)

`run_backtest_logic` accepts `external_prices`, `external_highs`, `external_lows`,
`external_timestamps` plus `data_source="bi5"` — it consumes whatever bars you
hand it. So the engine itself is **TF-agnostic**: if the realism path resampled
1m → strategy-TF before passing in, the engine would replay correctly. The
mismatch is upstream of the engine, in the loader.

---

## 3. Why the "Duplicates Skipped" Symptom Appears

Three reinforcing layers cause the misleading message:

1. **`bi5_ingest_log` idempotency** (`incremental_updater.py:425–447`):
   ```python
   file_key = f"{fname}:{st.st_size}:{int(st.st_mtime)}"
   if file_key in ingested_hashes:
       per_file.append({"file": fname, "status": "already_ingested"})
       continue
   ```
   A second ingest of the same chunk reports `already_ingested` per file.

2. **Append-only merge** (`data_manager._merge_rows` with `append_only=True`):
   ```python
   update_op = "$setOnInsert" if append_only else "$set"
   ```
   On overlap, the existing row is **preserved** and counted in `matched`,
   surfacing as `rows_preserved_existing` in the response.

3. **Realism path looks at the WRONG bucket.** Because the 1m data is correct
   but invisible to the H1 realism reader, an operator interpreting a
   `BI5_DATA_MISSING` flag as "I need to upload more BI5" will retry — and
   each retry returns "already_ingested" / "preserved", reinforcing the
   illusion that the stream is duplicated rather than mis-keyed.

The duplicates message is not a real duplication problem — it's the
idempotency log doing its job, masked by a misaligned consumer.

---

## 4. Proposed Architecture: BI5 = Single 1-Minute Realism Stream

### 4.1 Invariants to encode

| Invariant | Where | Status today |
|---|---|---|
| Discovery / mutation / OOS / lifecycle progression read **only** `source="bid_1m"` | All discovery engines | ✅ enforced |
| BI5 storage is one bucket per pair: `(symbol, "bi5", "1m")` | `data_manager._merge_rows` | ⚠ permissive — relies on caller discipline |
| BI5 ingestion is 1m-only — anything else is rejected at the API boundary | `api/data.py` | ❌ not enforced |
| BI5 realism evaluation reads 1m bars and **resamples** to the strategy's TF | `engines/bi5_realism._load_bi5_bars` | ❌ no resampler — reads strategy-TF directly |
| BID/BI5 row-level isolation | `(symbol, source, timeframe, ts)` compound key | ✅ enforced |
| Coverage reporting separates bid_1m and bi5 | `data_manager.get_data_summary` | ✅ enforced |

### 4.2 Minimal additive changes (NOT IMPLEMENTED — proposal only)

All four steps are **reversible** and **additive** — none rewrite existing
engines or move data:

1. **Lock BI5 ingest to 1m at the API boundary.**
   In `api/data.py`, when `source="bi5"`, force `timeframe="1m"` (or 400 if
   the caller passes anything else). Auto-maintainer is already compliant.
   *Effort:* ~6 lines per affected endpoint, 4 endpoints.
   *Risk:* very low — would only reject what is currently silently fragmenting
   storage.

2. **Add a dedicated 1m loader for the realism path.**
   New helper in `engines/data_access.py` (or scoped to `engines/bi5_realism.py`):
   ```python
   async def load_bi5_1m_bars(pair: str, *, limit: Optional[int] = None) -> list:
       return await load_ohlc_bars(pair, "1m", source="bi5", limit=limit)
   ```
   *Effort:* ~10 lines.
   *Risk:* zero — pure addition, no existing caller affected.

3. **Insert a 1m → strategy-TF resampler in `bi5_realism.evaluate`.**
   Replace the direct `_load_bi5_bars(pair, timeframe)` call with:
   * Load 1m bars via the new helper.
   * If `timeframe != "M1"`, resample with `pandas.resample` (OHLC aggregation
     rules: open=first, high=max, low=min, close=last, volume=sum).
   * Hand the resampled arrays to `run_backtest_logic` exactly as today.
   *Effort:* ~25 lines + a helper. Pandas already in `requirements.txt`.
   *Risk:* low — `bi5_realism` is the only consumer; lifecycle gates remain
   unchanged because they consume the `bi5_realism` block, not the bars.

4. **Update `MIN_BI5_BARS` per strategy TF.**
   Today `MIN_BI5_BARS = 200` is a constant suitable for H1+. If we resample
   from 1m, we'd have ~60× more bars at 1m than at H1 — keep the threshold at
   the **strategy's TF** (so an H1 strategy still wants ≥200 H1 bars after
   resampling, which equals ~12000 raw 1m bars). Either:
   * Express `MIN_BI5_BARS` as a function of TF (e.g. reuse
     `data_access.min_candles_for(timeframe)`), or
   * Multiply by the TF-to-1m ratio for the underlying-bar budget check.
   *Effort:* ~5 lines.
   *Risk:* low — only affects the data-sufficiency threshold gate.

### 4.3 What stays untouched

* `engines/strategy_lifecycle.py` — gates consume `bi5_realism.pf_ratio` /
  `status`, not raw bars. No change needed.
* `engines/backtest_engine.run_backtest_logic` — already TF-agnostic; receives
  parallel arrays.
* `engines/ai_orchestrator.py` — Rule 8 (`LIFECYCLE_EVALUATE`) and Sunday
  realism sweep stay identical.
* `data_engine/data_manager.py` — storage schema unchanged; the compound key
  remains `(symbol, source, timeframe, ts)`. We're not changing the schema —
  we're constraining the values that flow into it.
* `data_engine/incremental_updater.incremental_update_bi5` — already accepts
  `timeframe="1m"` as default; signature stays.
* All 260 routes and 88 engines.

---

## 5. Storage Migration Considerations

Because the compound-key invariant is `(symbol, source, timeframe, ts)`, any
legacy `bi5/<non-1m>` rows (if any exist) live in their own buckets and would
be silently ignored by the new realism reader.

**Inspection of current state:** the database has 0 rows total (fresh restore),
so no migration is needed in this environment. In a populated environment the
options would be (in increasing rigour):

1. **Leave-and-ignore.** The new reader only looks at `bi5/1m`; legacy
   `bi5/<other>` buckets sit harmlessly. Minimal effort.
2. **Soft warn.** A one-shot ops query on backend startup that counts
   `bi5/<non-1m>` rows and logs a warning so operators know to audit them.
3. **Hard purge.** A new `POST /api/data/bi5/normalize` that aggregates any
   `bi5/<non-1m>` rows back down to `bi5/1m` (when sub-1m granularity exists)
   or deletes them (when the bucket is a downsample of 1m and therefore
   redundant). Higher risk; would need explicit operator confirmation.

For this codebase the **leave-and-ignore** path is sufficient — it composes
cleanly with the additive changes.

---

## 6. Operational Implications

### What operators would see AFTER the proposed changes

* **One BI5 dataset per pair**, displayed as `EURUSD / bi5 / 1m`,
  `XAUUSD / bi5 / 1m`, `GBPUSD / bi5 / 1m`. Three buckets total for the
  current focus universe.
* **Storage budget** (rough): ~6 months of 1m FX data per pair ≈ 130k bars
  ≈ ~25 MB compressed in Mongo per pair. ~75 MB total for 3 pairs at 6
  months. Trivial.
* **No per-TF BI5 download buttons.** The Market Data UI's BI5 row would only
  expose 1m. (Reduces operator confusion.)
* **Realism evaluation** automatically replays an H1 strategy against
  resampled-from-1m H1 bars, an M15 strategy against resampled-from-1m M15
  bars, etc. Single source of truth.
* **`BI5_DATA_MISSING` flag** clears as soon as 1m data is present for the
  strategy's pair, regardless of the strategy's TF.

### Convergence-phase consequences

1. **Cleaner heartbeat.** Lifecycle transitions reach `deployment_ready`
   under the same realism source for every survivor — pf_ratio is
   directly comparable across H1 / M15 strategies.
2. **No early-emergence stalls.** The first portfolio-worthy survivor's
   realism check no longer depends on the operator having pre-uploaded BI5
   at the survivor's exact TF.
3. **G7 design surface stays simple.** Deployment artefacts can quote
   `bi5_realism.bi5_pf_ratio` knowing it always derives from the same
   1m base.

---

## 7. Risks / Edge Cases to Validate Before Implementation

1. **Resampling boundary alignment.** Pandas `resample("1H").agg(...)` uses
   left-closed, left-labelled by default — needs to match the BID candle
   convention used in discovery so PF ratios are comparable. Should snapshot
   a known BID/BI5 pair after first ingest and verify the H1 close prices
   match across BID and resampled-1m-BI5 within a small tolerance.
2. **Bid/Ask vs trade prices.** BI5 ticks are typically bid-side; BID 1m
   candles are typically OHLC of bid-side ticks too. Need to confirm
   Dukascopy `.bi5` parser already produces bid-side OHLC at 1m so the
   resampled higher-TF bars compare like-for-like with BID. Quick to verify
   from `data_engine/dukascopy_downloader.py`.
3. **Slippage / spread modelling.** `run_backtest_logic` with `data_source="bi5"`
   may apply realism modifiers (slippage assumptions, spread). Need to confirm
   the 1m-resampled path still triggers those modifiers correctly.
4. **`MIN_BI5_BARS` semantics.** A 200-1m-bar floor (~3 hours) is too lax;
   a 200-H1-bar floor (~8 trading days) is reasonable. Resampling math
   matters here — see §4.2 step 4.
5. **API back-compat.** Any external tooling that uploads BI5 with a non-1m
   timeframe today (we should grep for evidence first) would start receiving
   400. Need to audit `tests/` and any operator-facing docs.

None of the risks block the proposal — all are addressable inside the same
4-step additive change set.

---

## 8. Recommendation

**Adopt the "BI5 = single 1m realism stream" architecture.** The current
codebase is 70 % of the way there:

* ✅ Storage isolation already enforced.
* ✅ Auto-maintainer already 1m-only.
* ✅ Alignment health check already 1m-only.
* ✅ Backtest engine already TF-agnostic.
* ❌ API still permissive.
* ❌ Realism reader bypasses the 1m base.

The four additive changes outlined in §4.2 close the remaining 30 % without
touching lifecycle gates, the orchestrator, or the discovery pipeline.
Combined diff size: estimated **< 80 lines across 3 files**, all reversible
by reverting the patches.

**Phase staging recommended:**
1. **Inspection report** ← we are here. No code changes.
2. **Lock the API** (§4.2 step 1) — smallest, lowest-risk patch.
3. **Add the 1m loader + resampler in `bi5_realism`** (§4.2 steps 2–4) —
   verify with a single-strategy realism check on freshly ingested BI5/1m.
4. **Tighten the lifecycle test suite** to assert that an H1 + an M15
   strategy realism-checked against the same 1m BI5 bucket produces
   internally-consistent pf_ratios.

After phase 4, the BI5 layer is genuinely "single-source realism stream
architecture" and the architectural mismatch is closed.

---

## 9. Open Questions for the Operator

Before any code change, please confirm:

1. **Resampling rule alignment.** Should H1 / M15 / D1 resampled-from-1m bars
   use the same boundary convention as BID? (Default = yes.)
2. **Threshold semantics.** Should `MIN_BI5_BARS` be expressed in
   strategy-TF bars (consistent with `min_candles_for()`) or in raw 1m
   bars? (Default = strategy-TF.)
3. **Storage migration.** Leave-and-ignore for any legacy `bi5/<non-1m>`
   buckets, or add the soft-warn / hard-purge surfaces? (Recommended:
   leave-and-ignore for now; revisit when populated environments need it.)
4. **Sweep cadence change.** Today the Sunday 03:00 UTC sweep runs
   `force_refresh=False`. With a single-stream architecture the sweep will
   be cheaper and faster — no change needed, but worth noting.
5. **API back-compat tolerance.** OK to return HTTP 400 on
   `(source="bi5", timeframe!="1m")` immediately, or do we want a soft
   deprecation period?

No code action will be taken until the operator confirms the proposal. This
document is the sole deliverable for this phase.
