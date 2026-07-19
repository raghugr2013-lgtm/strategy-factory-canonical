# BID Historical Candle Data — Architecture Review
### Multi-Timeframe Storage vs Canonical M1 vs Hybrid (and beyond)

> **Status:** review only — no code changes.
> This review addresses **BID historical candle storage** — the
> long-term OHLCV database used for strategy generation, research,
> and backtesting. **BI5 tick data is out of scope** (it already
> uses canonical-M1 + on-read resample; see §2.3).
>
> Requested by operator on 2026-02-19; supersedes the BID-related
> paragraph in `PHASE_2B_MARKET_DATA_REVIEW.md` §5-6.

---

## 0. Precise problem statement

**What we're deciding:** How the Strategy Factory stores historical
OHLCV candle data downloaded from BID providers (Dukascopy, others)
for use by strategy generation, backtesting, research, and the
knowledge/market/execution domains.

**What we're NOT deciding:**
- BI5 tick storage (settled — canonical M1 + resample-on-read, see §2.3)
- Live streaming quotes (out of scope; Phase 3+)
- Real-time bar aggregation for live execution (COE γ+)

**Scope of use:**
- 20+ instruments (FX majors, minors, exotics; potentially crypto/metals)
- 5–10 year history windows per instrument
- Timeframes consumed by strategies: 1m, 5m, 15m, 30m, 1h, 4h, 1d
  (occasionally 3m, 12h, 1w)

---

## 1. Options catalogue

The operator specified three:

| Option | Mechanism |
|---|---|
| **A** | Download and store each timeframe independently from provider (native multi-TF storage) |
| **B** | Download and store only M1; derive all higher TFs internally by resampling on read |
| **C** | Hybrid — some TFs stored natively, others generated |

I add three more that the codebase and vision make worth considering:

| Option | Mechanism |
|---|---|
| **D** | **Canonical M1 + materialised HTF caches** — store M1 as truth; write pre-computed M5/M15/H1/H4/D1 caches lazily on first read; invalidate on M1 append |
| **E** | **External time-series DB** — offload candles to InfluxDB / TimescaleDB / QuestDB with native on-the-fly aggregation |
| **F** | **Columnar Parquet on disk + Mongo metadata** — store M1 candles as partitioned Parquet files (mirroring the existing on-disk BI5 tick archive); Mongo holds only pointers + coverage metadata |

---

## 2. Current state audit (what exists today)

### 2.1 Storage shape

Single Mongo collection **`market_data`**, keyed by
`(symbol, source, timeframe)`:

```
{
  symbol: "EURUSD",
  source: "bid_1m" | "bi5" | "dukascopy" | "csv" | ...,
  timeframe: "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d",
  timestamp: ISODate,
  o, h, l, c, volume, ...
}
```

`INTERVAL_MINUTES` map in `data_engine/incremental_updater.py` covers
all supported TFs. Every TF is a **separate stream** with its own
gap history, own coverage state.

### 2.2 Existing discipline (KEEP verbatim)

| Component | Verdict |
|---|---|
| `data_manager._merge_rows(append_only=True)` — insert-if-missing only, never overwrite | ✅ Correct — historical data is immutable |
| `gap_analyzer.check_gaps` / `fix_gaps` — market-aware (weekends, holidays) | ✅ Right layer, already market-calendar-aware |
| `bid_1m` vs `bi5` **source-locked** — never merged on disk | ✅ Critical invariant — tick-derived candles and native BID candles have subtly different statistics; conflating them silently would corrupt backtests |
| `dukascopy_downloader.download_and_store` — dedup-safe | ✅ |
| `auto_data_maintainer` — APScheduler top-ups, per-source (BID 15-min, BI5 60-min) | ✅ Live in production |

### 2.3 BI5 side is ALREADY Option B — a proof point

`api/data.py:46-62` comment:
> "only bi5/1m and resamples to the strategy's timeframe on demand"

`legacy/tests/test_bi5_realism_multi_tf_consistency.py:66-98` — the
BI5 realism sweep runs H1 strategies against M1 data resampled to
H1, with the resample provenance persisted. **This is Option B, already
in production for the tick-derived pipeline, with dedicated regression
tests.**

**Implication:** the resample plumbing exists, is tested, and is proven.
Adopting the same discipline for BID candles is not a leap.

### 2.4 BID side is currently Option A

Every strategy backtest today reads whichever `timeframe` row set it
needs directly from `market_data`. `download_and_store` pulls each
TF as a separate provider call. Gap analysis runs independently per
TF. No cross-TF consistency check exists between BID candle TFs.

---

## 3. Evaluation matrix — the 13 criteria

Scoring: ✅ strong · ○ acceptable · ⚠ weak · ✗ blocker. Rationale below the table.

| # | Criterion | A: Multi-TF native | B: Canonical M1 | C: Hybrid | D: M1 + materialised | E: External TSDB | F: Parquet on disk |
|---|---|---|---|---|---|---|---|
| 1 | Data integrity | ⚠ | ✅ | ○ | ✅ | ✅ | ✅ |
| 2 | Storage footprint | ⚠ (~+30%) | ✅ | ○ | ⚠ (~+30%) | ✅ | ✅ |
| 3 | Download bandwidth | ⚠ | ✅ | ○ | ✅ | ✅ | ✅ |
| 4 | Update/maintenance complexity | ⚠ (N pipelines) | ✅ (1 pipeline) | ⚠ | ✅ | ⚠ (new dep) | ○ |
| 5 | Rebuild / recovery capability | ⚠ | ✅ | ○ | ✅ | ○ | ✅ |
| 6 | Gap detection & repair | ⚠ (per-TF) | ✅ (one truth) | ○ | ✅ | ✅ | ✅ |
| 7 | Strategy-gen performance | ○ | ○ | ✅ | ✅ | ✅ | ✅ |
| 8 | Backtest performance | ✅ (native) | ⚠ (resample cost) | ✅ | ✅ | ✅ | ✅ |
| 9 | Query performance | ✅ | ○ | ✅ | ✅ | ✅ | ✅ |
| 10 | Long-term scalability | ⚠ | ✅ | ○ | ✅ | ✅ | ✅ |
| 11 | BI5 interaction | ✗ (asymmetric) | ✅ (parallel) | ○ | ✅ | ○ | ✅ |
| 12 | COE interaction | ⚠ | ✅ | ○ | ✅ | ⚠ (new node type) | ✅ |
| 13 | KB / Meta-Learning fit | ○ | ✅ | ○ | ✅ | ○ | ✅ |

### 3.1 Data integrity

- **A (⚠):** Provider-delivered HTF bars can silently differ from what an M1→HTF resample would produce. If Dukascopy's 15m server-side bar is computed slightly differently (e.g. session cut-off), our M15 backtest and our M1-based tick backtest disagree. There's no cross-TF consistency test today.
- **B (✅):** One source of truth. If M1 is correct, every HTF derived from it is provably correct. If M1 is wrong, every HTF is wrong the same way — errors are visible, not hidden.
- **D (✅):** Same as B, plus caches are recomputable at will.

### 3.2 Storage footprint

- Rough estimate for 20 pairs × 10 years continuous FX:
  - M1 alone: ~130 GB uncompressed / ~30 GB with Mongo compression (WT snappy)
  - All HTF combined (m5+m15+m30+h1+h4+d1): ~40 GB uncompressed / ~9 GB compressed
- **Total under Option A: ~170 GB / ~39 GB compressed.**
- **Under Option B: ~130 GB / ~30 GB compressed.**
- **Savings ≈ 24%.** Not the main argument, but non-trivial at 10-year horizons.

### 3.3 Download bandwidth

- Option A: N (=7) provider calls per top-up window per instrument. Multiplied across 20+ pairs and 24 top-ups/day → ~3,360 provider calls/day.
- Option B: 1 provider call per top-up window per instrument → ~480 calls/day.
- **≈ 7× reduction in provider bandwidth + rate-limit surface.** Also means fewer opportunities for a provider outage to leave one TF stale and another current — a known Option-A pain point today.

### 3.4 Update / maintenance complexity

- **A:** `auto_data_maintainer` maintains N per-TF pipelines. Each has its own last_ts, its own gap history, its own catch-up window. Failure modes multiply.
- **B:** One pipeline (M1). Every HTF is a pure function over M1.

### 3.5 Rebuild / recovery capability

- **A:** If a TF's rows corrupt, we re-download JUST that TF. But we cannot **verify** the corruption was corrected — the "correct" bar shape comes from the provider, and providers are not always consistent across time (revisions happen).
- **B:** Any HTF can be regenerated bit-for-bit from M1 in seconds. Backfills replay in one pass.

### 3.6 Gap detection & repair

- **A:** Per-TF gap analysis. A 15m gap without a matching 1h gap in the same instant would be surprising — but nothing enforces it. Silent divergence risk.
- **B:** One gap surface. HTF gaps are derived, not detected.

### 3.7 Strategy-gen performance

- All strategies read a TF window. In A/D/E/F this is a range query on a pre-materialised store. In B this is a range query + resample. Resample of M1→H1 for 5 years × 1 pair = ~2.6M rows aggregated to ~44K rows in <0.5 s using pandas / polars.
- **Verdict:** B pays a real but bounded cost; D/E/F eliminate it.

### 3.8 Backtest performance

- Same as §3.7 — but backtests read HTF windows repeatedly (per-mutation, per-parameter-sweep). A **cache** amortises the resample cost.
- Under Option D, first read materialises; every subsequent backtest of the same window reads the cached HTF directly. Under Option B without cache, every backtest resamples.
- Given the mutation/optimisation loops read the same HTF windows thousands of times, **D is materially faster than pure B** for backtesting.

### 3.9 Query performance

- A/D/E/F: direct range query on a pre-computed store.
- B: range query + resample every time.

### 3.10 Long-term scalability

- A: Mongo `market_data` grows with **every TF × every symbol × every year**. Hot indexes bloat linearly with N (=TF count).
- B: Grows with **every symbol × every year** only.
- D: Same footprint as A, but the HTF caches are cold-storage (only touched on read; can be evicted).
- E: External TSDB scales independently of Mongo; but adds an operational dependency (a second production database).
- F: Parquet is columnar, splittable, cheap to scan; scales to petabytes. But introduces a filesystem-based read path alongside Mongo.

### 3.11 Interaction with BI5 tick data

- **Critical asymmetry today:** BI5 already uses canonical-M1 + resample (Option B). If BID stays on Option A, we have **two subtly different truths** for the same instrument. A H1 backtest using BID candles and a H1 realism sweep using BI5-derived candles disagree — and there's no automated check to catch it.
- **B (or D):** BID candles and BI5-derived candles both live at M1 and both resample the same way. Cross-source consistency becomes checkable via a straightforward diff.
- **E:** Consistency achievable but requires the same instrument in two stores.

### 3.12 Interaction with the Compute Orchestration Engine

- COE ships a `MARKET_DATA` workload class with a reservation of 1 (per Stage-1 conservative floors). Under Option A, a full top-up runs N pipelines → N MARKET_DATA workload submissions per instrument per tick. Under Option B, one submission per instrument per tick. **B is ~7× fewer MARKET_DATA jobs → smaller queue depth, easier reservation sizing.**
- Distribution-ready invariant (§3 principle #11): whichever driver holds `WorkloadQueue` also gets fewer messages under B — friendlier to the future Redis / RabbitMQ γ+ driver.

### 3.13 Interaction with Knowledge Engine + Meta-Learning

- The Knowledge Engine's `market` domain wants a stable, canonical, provenance-anchored view of instrument behaviour. Under A, a paper written about "EURUSD H1 mean reversion" must specify **which H1 source** — provider-native or derived-from-M1 — because they differ. Under B/D, no such disambiguation is needed; H1 is unambiguously "M1 resampled to H1".
- Meta-Learning evaluates factory decisions across historical windows. Deterministic reproducibility of "what did the H1 chart look like on 2024-06-15?" is only possible if the H1 is a **pure function** of an immutable M1 store. That's B/D — not A.

---

## 4. Additional considerations

### 4.1 Provider availability of M1

The whole B/D thesis rests on M1 being consistently available from
providers for the required history. Dukascopy: **M1 back to 2003 for
majors, 2010+ for most minors**. Some exotic instruments (rare
crypto pairs, some commodities) may only be published at HTF for
older history. This is where **Option C (hybrid) has legitimate
merit** for those instruments — but as an *edge case exception*,
not the base architecture.

### 4.2 Provider-native HTF as a validation reference

Even under Option B/D, provider-native HTF has value as a **check**:
periodically download 1 week of provider-native H1 and diff against
M1-resampled H1. Any large discrepancy is either a provider bug or
an M1 gap. This is **cheap** (~1 KB per instrument per week) and
turns Option A's "silent divergence risk" into an active signal.

### 4.3 Resample cost budget

Pandas / polars M1→H1 resample of 5 years × 1 pair ≈ 300 ms on
commodity hardware. For a backtest that iterates 500 mutations, this
is 150 seconds of pure resample overhead if uncached — real but
bounded. **Under Option D, the first backtest pays 300 ms; every
subsequent one pays a Mongo range query (~20 ms).** This is why D is
strongly preferred over pure B for the backtest hot path.

### 4.4 Cache invalidation for materialised HTF

Under Option D, when M1 gains new rows, the HTF caches for those
windows become stale. Two disciplines available:
1. **Timestamp-based invalidation:** every HTF cache row carries the
   max M1 timestamp it covers; a read that finds the M1 has advanced
   past that timestamp re-materialises.
2. **Trailing-edge exclusion:** never cache the current (in-progress)
   HTF bar; always resample the trailing edge on read.

Both are cheap. Recommend (2) as the default because it's stateless.

### 4.5 Backwards compatibility

The existing `market_data` collection with per-TF rows must remain
readable for one release cycle to avoid breaking any legacy
consumer. Migration path:
1. Populate M1 canonical rows (either freshly downloaded or
   backfilled from existing M1 rows in `market_data`).
2. Add `data_access.load_candles(symbol, timeframe)` that reads M1
   and resamples (Option B).
3. Optional: materialise HTF caches into a **separate collection**
   `market_data_htf_cache` so the existing `market_data` stays
   untouched (Option D).
4. Keep parallel legacy TF rows in `market_data` **read-only** for
   one release.
5. Deprecate legacy TF rows in a separate, later Phase-3 decision.

**Nothing in this migration deletes data.**

---

## 5. Trade-off summary

| Aspect | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| **Best-in-class:** query speed | ✅ | | | ✅ | ✅ | ✅ |
| **Best-in-class:** integrity + reproducibility | | ✅ | | ✅ | ○ | ✅ |
| **Best-in-class:** operational simplicity | | ✅ | | ✅ | | |
| **Best-in-class:** minimum footprint | | ✅ | | | ✅ | ✅ |
| **Best-in-class:** future-proof (scale, distribute) | | ✅ | | ✅ | ✅ | ✅ |
| **Best-in-class:** implementation cost (near-term) | ✅ (already built) | | ○ | | ✗ (new dep) | ✗ (new format) |
| **Worst pain point** | silent divergence between TFs and vs BI5 | resample latency on every read | 2 pipelines to maintain | cache invalidation discipline | external service to operate | dual storage backend to reason about |

---

## 6. Recommendation

### **Adopt Option D — Canonical M1 storage + on-demand materialised HTF caches — as the primary BID candle architecture.**

This is Option B in principle, with a materialisation cache layered
on top to eliminate the one real Option-B downside (resample latency
on hot-path backtest reads).

### 6.1 Why D over B

Pure B is intellectually clean but pays resample cost on every
backtest. Given the factory runs thousands of mutations per cycle
and each mutation is a backtest, the resample overhead accumulates.
D amortises it to first-touch only.

### 6.2 Why D over A

D preserves every Option-A benefit (fast HTF reads via materialised
cache) while removing every Option-A pain point (silent divergence,
bandwidth waste, 7× more pipelines, storage bloat).

### 6.3 Why D over C

C is Option A's problems shrunk to a subset of TFs. No architectural
gain — just complexity of "which TFs go where". The one exception
where C makes sense is **exotic instruments where M1 isn't available**
— and D can absorb that case with a per-instrument `native_only=True`
override without becoming C wholesale.

### 6.4 Why D over E (external TSDB)

Adds a production database (InfluxDB / TimescaleDB) with its own
backup, monitoring, and operational surface. Distribution-ready
invariant (§3.11) is achievable within Mongo + a driver-swap on the
`market_data_htf_cache` collection later. Bringing in a second DB
for a problem Mongo can solve is a step down in operational
simplicity.

### 6.5 Why D over F (Parquet on disk)

Parquet is genuinely excellent for cold storage of M1, and the BI5
tick archive already lives on disk in a similar pattern. But candles
are read in overlapping ranges by many concurrent backtests —
Mongo's range-query index is a better fit for that access pattern
than filesystem seeks. Reconsider F for Phase 3+ if candle count
crosses 10B+ rows.

### 6.6 Full recommended design (BID candles)

```
┌──────────────────────────────────────────────────────────────────┐
│  Provider (Dukascopy, others)                                    │
└──────────────────────────┬───────────────────────────────────────┘
                           │  M1 only (COE class = MARKET_DATA)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  incremental_updater (append-only, one pipeline per instrument)  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  market_data (Mongo)                                             │
│    ├── source="bid_1m"     timeframe="1m"    ← canonical         │
│    └── (legacy per-TF rows retained read-only during migration)  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  data_access.load_candles(symbol, timeframe)                     │
│    1. Read M1 window from market_data                            │
│    2. If materialised cache exists AND is fresh → return it      │
│    3. Else resample M1 → HTF using pandas/polars                 │
│    4. Write to market_data_htf_cache (fire-and-forget)           │
│    5. Return HTF                                                 │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  market_data_htf_cache (Mongo — new collection)                  │
│    keyed by (symbol, timeframe, window_start, max_source_ts)     │
│    trailing-edge always resampled; historical windows cached     │
│    driver-agnostic — future replacement with Redis/Parquet OK    │
└──────────────────────────────────────────────────────────────────┘
```

### 6.7 Governance & invariants

- **`data_access.load_candles()` is the sole read of market data**
  (existing invariant, unchanged; PHASE_2_CONSOLIDATED §5, invariant 7).
- **Provider-native HTF check** — a weekly `MARKET_DATA` task diffs a
  provider-native H1 sample against M1-resampled H1. Discrepancies
  are alerts, not fixes.
- **Cross-source consistency check** — a monthly `META_LEARNING`
  task diffs BI5-derived candles against BID candles for the last 30
  days. Discrepancies are recorded in `outcome_events` and
  surfaced in the platform-health dashboard.

### 6.8 Feature flags for reversibility

Every capability lands behind a flag; default OFF; rollback = flag flip.

| Flag | Default | Effect when ON |
|---|---|---|
| `BID_CANONICAL_M1_READ_MODE` | `false` | `data_access.load_candles()` reads M1 and resamples (Option B) |
| `BID_HTF_CACHE_ENABLED` | `false` | Materialise HTF caches into `market_data_htf_cache` (Option D) |
| `BID_LEGACY_TF_ROWS_READ_ONLY` | `false` | Deprecate per-TF rows in `market_data` to read-only |
| `BID_PROVIDER_HTF_CHECK_ENABLED` | `false` | Weekly provider-native HTF diff task |
| `BID_CROSS_SOURCE_CHECK_ENABLED` | `false` | Monthly BID↔BI5 consistency task |

### 6.9 Where this lands in the Phase 2 plan

**PHASE_2B stated: "BI5 read-side refactor" in Stage 2.** That
refactor already assumes the resample discipline. This review
extends it: **the same refactor now covers BID candles as well,
with the additional cache layer (Option D) making backtest
performance strictly better than today.**

**No net calendar impact** — Stage 2 already scoped BI5 read-side +
BID canonical M1. This review confirms the design of that step and
adds the HTF cache and cross-source consistency guarantees.

### 6.10 One-line summary

> **Store M1 as truth. Derive HTFs on read. Cache them lazily.
> Never trust two truths for the same bar.**

---

## 7. Non-recommendations (kept for completeness)

- **Do not** delete existing per-TF rows in `market_data` in Stage 2. Keep them read-only for at least one release cycle. Deletion is a Phase 3+ decision that requires cross-verified equivalence.
- **Do not** introduce InfluxDB / TimescaleDB / QuestDB in Phase 2. Reconsider only if Mongo's range-query performance becomes a demonstrated bottleneck AND `market_data_htf_cache` doesn't fix it.
- **Do not** move to Parquet on disk in Phase 2. Reserve F for Phase 3+ if row count exceeds ~10B or Mongo storage grows beyond ~500 GB.
- **Do not** attempt cross-provider consolidation (merging Dukascopy-M1 with, say, OANDA-M1) in Phase 2. Source-locking (per §2.2) remains a hard invariant.

---

## 8. Open questions (for operator approval)

1. **Cache TTL policy** — full 10-year history cached indefinitely, or windowed to the last N years (rebuild on demand)? Recommend indefinite for hot instruments (~100 MB total), windowed for cold.
2. **Cache collection sharding** — `market_data_htf_cache` on a separate Mongo cluster in future? Not needed for β; call out for γ.
3. **Provider-native HTF check frequency** — weekly (recommended) or daily (higher confidence, more bandwidth)?
4. **Cross-source consistency threshold** — what percentage divergence is an alert vs a hard-stop?
5. **Are there instruments today where M1 is unavailable for the desired history?** — if yes, they enter the C-exception path with `native_only=true`; if no, D is universal.

---

## 9. Sign-off

- ✅ **This review** — approved by operator on 2026-02-19 with refinements (see §10)
- On approval: **the Phase 2 Stage 2 plan folds this in as-is** (the BI5 read-side refactor extends to cover BID candles under Option D).
- No Phase-1 code changes.
- No BI5 tick behaviour change.
- No production `market_data` rows deleted or modified.

*Reviewed against:*
`data_engine/incremental_updater.py`, `data_engine/auto_data_maintainer.py`,
`data_engine/dukascopy_downloader.py`, `data_engine/gap_analyzer.py`,
`data_engine/data_manager.py`, `engines/data_access.py`,
`legacy/api/data.py`, `legacy/api/bi5_realism.py`,
`legacy/tests/test_bi5_realism_multi_tf_consistency.py`,
`PHASE_2B_MARKET_DATA_REVIEW.md`,
`PHASE_2_CONSOLIDATED_REVIEW.md`,
`PHASE_2_IMPLEMENTATION_MASTER_PLAN.md`.

*Status:* **Option D approved 2026-02-19. Design now supersedes the BID paragraph in PHASE_2B. Implementation deferred until Phase 2 Stage 2.**

---

## 10. Approved refinements (operator, 2026-02-19)

### 10.1 Cache invalidation — event-driven, not time-driven

Cache freshness is triggered by observable events, not TTL. Time-based
expiry is a **safety fallback only**.

**Invalidation events:**
| Event | Effect |
|---|---|
| New M1 candles arrive (append-only insert) | Invalidate HTF cache windows overlapping the appended range |
| Historical repair (`fix_gaps`, `data_manager.repair`) | Invalidate all HTF cache windows overlapping the repair range |
| Gap-repair completion (`gap_analyzer` fills a hole) | Same as above |
| Provider correction detected (weekly HTF diff exceeds `major` threshold) | Governance alert + mark HTF cache windows `stale=true` (no auto-rebuild) |
| Operator forces rebuild (admin API) | Truncate + rebuild specified windows |
| Secondary safety: cache age > `BID_HTF_CACHE_MAX_AGE_DAYS` (default 365) | Re-materialise on next read |

**Consequence for `market_data_htf_cache` schema:**
Each cache row now carries `source_range: {first_ts, last_ts}` +
`generated_at` + `stale: bool`. Invalidation is a metadata flip, not
a delete — the row stays readable until the re-materialised row lands
(hot-swap discipline).

### 10.2 Cache sharding — three-axis composite key

Shard by **(symbol, timeframe, date_range_bucket)** — where
`date_range_bucket` is a monthly or quarterly window (recommend
monthly for M15 and below, quarterly for H1+).

**Benefits:**
- Rebuilds are per-bucket → small, bounded work units
- Distribution-ready: buckets are natural units of parallel work
- Cache miss on the trailing edge doesn't invalidate historical buckets
- Cross-node placement in COE γ+ is trivial (bucket-hash routing)

**Mongo shape:**
```
market_data_htf_cache {
    _id: "<symbol>|<tf>|<yyyy-mm>",   # e.g. "EURUSD|H1|2025-06"
    symbol, timeframe, bucket_start, bucket_end,
    source_range: { first_ts, last_ts },
    generated_at, stale: false,
    candles: [ { ts, o, h, l, c, v }, ... ]
}
```

Bucket boundaries are aligned to natural session cut-offs (Sunday
17:00 ET open for FX) to avoid straddling.

### 10.3 Provider HTF verification — periodic, advisory, tiered

**Cadence:** monthly (not weekly, not continuous). One
`MARKET_DATA` task per instrument-TF pair per month, running during
a low-traffic window.

**Never automatically overwrites** the canonical M1 or the derived
HTF cache. Divergence outcomes are **governance alerts**, not
corrective actions.

**Tiered divergence classifier:**
| Tier | Meaning | Action |
|---|---|---|
| `informational` | Divergence below the minor threshold | Record in `provider_htf_check_log`; no alert |
| `warning` | Divergence between minor and moderate thresholds | Alert operator dashboard; do not touch data |
| `governance_review` | Divergence exceeds moderate threshold | Mark cache bucket `stale=true` for the affected range; require operator sign-off before rebuild |

**Threshold values are DELIBERATELY unspecified in this document.** They
will be calibrated using production observation once the check runs
for one full month against real provider drift. Placeholders:
`BID_HTF_DIVERGENCE_MINOR_BPS`, `BID_HTF_DIVERGENCE_MODERATE_BPS`
(env-overridable).

### 10.4 M1-fallback for instruments without M1 history

Support both models under one architecture. Per-instrument opt-out
via the `instrument_registry` collection (new — Phase-2 scope):

```
instrument_registry {
    symbol:              "EURUSD",
    canonical_mode:      "m1" | "native_tf",
    native_only_reason:  "no_m1_history_before_2015" | "provider_limit" | null,
    fallback_tfs:        [ "15m", "1h" ],     # only when canonical_mode="native_tf"
    added_at, notes
}
```

**Default:** every instrument is `canonical_mode="m1"`. The `native_tf`
mode is the explicit exception, documented per instrument, requiring
operator approval to add.

`data_access.load_candles()` becomes:
```
if instrument.canonical_mode == "m1":
    → M1 canonical read + resample + cache (Option D)
else:
    → native TF row read from market_data (legacy Option A path)
```

**No exotic-instrument case blocks the primary architecture.** The
canonical path stays clean.

### 10.5 The Canonical Timeframe Service (CTS) — new dedicated component

The operator-introduced abstraction that centralises aggregation
logic. Rather than sprinkling resample calls across `data_access.py`,
backtest engines, and knowledge domains, all HTF derivation goes
through **one** service.

**Responsibilities (per operator directive):**
1. Aggregate M1 into higher timeframes (single canonical resampler)
2. Materialise HTF caches (write to `market_data_htf_cache`)
3. Validate aggregation integrity (checksum M1 window ↔ derived HTF row)
4. Rebuild caches after repairs / invalidation events
5. Serve historical timeframe requests (the sole `load_candles()` implementer)
6. Report cache health (via `HealthSnapshot` — Universal Health Contract)

**Interface (Protocol — driver-agnostic per distribution invariant §11):**
```python
class CanonicalTimeframeService(Protocol):
    async def load_candles(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime, *,
        use_cache: bool = True,
    ) -> List[Candle]: ...

    async def invalidate(
        self, symbol: str, timeframe: Optional[str] = None,
        start: Optional[datetime] = None, end: Optional[datetime] = None,
        reason: str = "manual",
    ) -> InvalidationReport: ...

    async def rebuild_bucket(
        self, symbol: str, timeframe: str, bucket_key: str,
    ) -> RebuildReport: ...

    async def verify_against_provider(
        self, symbol: str, timeframe: str, window_days: int = 7,
    ) -> VerificationReport: ...

    def health_snapshot(self) -> HealthSnapshot: ...
```

**Placement:** `backend/engines/cts/` (new module, Phase 2 Stage 2).
Registered as a subsystem in `engines.health.providers` on boot.

**Governance:** the CTS is the **sole implementer** of
`data_access.load_candles()` once Stage 2 lands. This becomes
platform invariant #16 (extends §5 of `PHASE_2_CONSOLIDATED_REVIEW.md`):
> **Invariant #16 (2026-02-19):** All historical candle reads for any
> timeframe go through the Canonical Timeframe Service. No engine
> reads `market_data` directly for HTF data.

**Failure isolation:** CTS runs entirely on the `MARKET_DATA` COE
workload class (with reservation ≥ 1 per Stage-1 conservative
floors) — a backtesting burst cannot starve CTS reads.

### 10.6 Cross-source consistency check — advisory only

Per operator directive: monthly BID ↔ BI5-derived candle diff, run
as a `META_LEARNING` task (heavy, monthly, non-blocking). Outputs
recorded in `outcome_events` with severity tier. **Never auto-overwrites.**

Governance dashboard surface: a single card showing "Cross-source
divergence — last 30 days" with severity breakdown. Operator
inspects; operator decides.

### 10.6b Traceability invariant (operator directive, 2026-02-19)

Every historical candle returned by CTS MUST be traceable. Each
returned dataset (a `CandleWindow`) carries a `Provenance` record
that identifies:

| Field | Meaning |
|---|---|
| `canonical_source` | Which storage the M1 rows came from (e.g. `market_data.bid_1m`) |
| `aggregation_path` | Pure fn identifier: `m1_native` \| `m1_resampled_to_H1` \| `cache:H1` \| `error` |
| `cache_generated_at` | UTC ISO of the cache write; `null` when served from resample |
| `cache_version` | Schema version — bumped on breaking changes to the cache row shape |
| `cache_bucket_key` | 3-axis shard key (`EURUSD\|H1\|2026-02`) when applicable |
| `repair_status` | `none` \| `gaps_backfilled` \| `manual_override` |
| `data_quality_state` | `ok` \| `degraded` \| `reconstructed` \| `stale` \| `unknown` |
| `gap_count` | Number of expected bars missing from the window |
| `generated_at` | UTC ISO of THIS response |
| `cts_version` | CTS module version (semver) |

This becomes **platform invariant #17**:
> **Invariant #17 (2026-02-19):** Every `CandleWindow` returned by CTS
> carries a fully populated `Provenance` record. No caller may
> discard, replace, or synthesise provenance metadata.

Rationale: as the platform grows, backtests must be reproducible from
provenance alone — given the same `canonical_source + aggregation_path
+ cache_generated_at + cache_version`, the same input produces the
same output. Any drift becomes an audit trail that operators can
walk backwards.

Implementation: `engines/cts/types.py::Provenance` — a `@dataclass`
attached to every `CandleWindow`. Enforced by the CTS Protocol's
return type; downstream logging includes provenance dict via
`window.to_dict()`.

### 10.7 Updated feature-flag catalogue (supersedes §6.8)

| Flag | Default | Owner | Effect when ON |
|---|---|---|---|
| `BID_CANONICAL_M1_READ_MODE` | `false` | CTS | Route `load_candles()` through M1 + resample path |
| `BID_HTF_CACHE_ENABLED` | `false` | CTS | Materialise `market_data_htf_cache` on demand |
| `BID_CACHE_EVENT_INVALIDATION` | `false` | CTS | Enable event-driven cache invalidation (default) |
| `BID_HTF_CACHE_MAX_AGE_DAYS` | `365` | CTS | Secondary safety time-based expiry |
| `BID_LEGACY_TF_ROWS_READ_ONLY` | `false` | Migration | Deprecate per-TF rows in `market_data` |
| `BID_PROVIDER_HTF_CHECK_ENABLED` | `false` | CTS | Monthly provider-native HTF diff task |
| `BID_HTF_DIVERGENCE_MINOR_BPS` | *TBD* | CTS | Threshold — informational tier |
| `BID_HTF_DIVERGENCE_MODERATE_BPS` | *TBD* | CTS | Threshold — warning → governance-review tier |
| `BID_CROSS_SOURCE_CHECK_ENABLED` | `false` | Meta-Learning | Monthly BID↔BI5 consistency check |
| `INSTRUMENT_REGISTRY_ENABLED` | `false` | Data | Enable per-instrument `canonical_mode` (m1 / native_tf) |

Every flag is default OFF; rollback = flag flip.
