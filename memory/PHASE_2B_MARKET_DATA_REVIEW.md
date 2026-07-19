# Phase 2B — Market Data / BI5 Architecture Review
### Design before implementation

> **Status:** review only — no code changes.
> This document audits the market-data subsystem that already exists
> at commit `829f31d`, identifies the *specific anti-pattern* the
> question flags (independent per-timeframe downloads), and proposes
> a canonical data model that fixes it without discarding the
> substantial infrastructure already in place.

---

## 0. Current state — what exists today

### 0.1 The subsystem surface (~30 modules, 3 layers)

```
┌─────────────────────────────────────────────────────────────────┐
│  API LAYER (5 routers, ~40 endpoints)                           │
│                                                                 │
│  /api/admin/bi5/*         legacy/api/bi5_ingest.py              │
│  /api/admin/bi5/certify   legacy/api/bi5_certification.py       │
│  /api/data/*              legacy/api/data.py                    │
│  /api/data/health/*       legacy/api/data_health.py             │
│  /api/data/maintenance/*  legacy/api/data_maintenance.py        │
│  /api/bi5-realism/*       legacy/api/bi5_realism.py             │
│  /api/ingestion/*         legacy/api/ingestion.py               │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌─────────────────────────────▼─────────────────────────────────────┐
│  ENGINE LAYER — pure logic + orchestrators                        │
│                                                                   │
│  legacy/engines/tick_validator.py            — validate_hour()    │
│  legacy/engines/bi5_certification.py         — cert orchestrator  │
│  legacy/engines/bi5_cert_sweep.py            — bulk certifier     │
│  legacy/engines/bi5_cert_sweep_scheduler.py  — CronTrigger        │
│  legacy/engines/bi5_maturity.py              — 6-phase roadmap    │
│  legacy/engines/bi5_realism.py               — realism metrics    │
│  legacy/engines/data_access.py               — canonical loader   │
│  legacy/engines/ingestion_health_aggregate.py — health rollup     │
│  legacy/engines/market_intel_engine/          — regime detection  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌─────────────────────────────▼─────────────────────────────────────┐
│  PERSISTENCE LAYER — 4+ Mongo collections                         │
│                                                                   │
│  market_data              — OHLCV candles (per-symbol per-TF)     │
│  bi5_ingest_log           — per-hour download idempotency         │
│  bi5_data_certifications  — Phase-2 cert results                  │
│  bi5_certifications       — Phase-3 cert results                  │
│  market_spread_store      — per-symbol spread series              │
│  market_environment_stats — regime baseline                       │
│                                                                   │
│  BI5 tick files            — on-disk archive (~110 MB seed)       │
│                             stored outside Mongo                  │
└───────────────────────────────────────────────────────────────────┘
```

### 0.2 What is production-grade today (keep)

| Component | Verdict |
|---|---|
| `tick_validator.py` — pure `validate_hour()` + `aggregate_window()` producing a "BI5 Score" | ✅ Excellent. No I/O, no Mongo — testable, composable |
| BID↔BI5 firewall enforced in `bi5_certification.py` header comment | ✅ Correct isolation; certification cannot leak deployment state |
| BI5 cert sweep scheduler (APScheduler `CronTrigger`) | ✅ Right pattern |
| `data_access.py` — the consolidated `load_ohlc_bars(pair, tf, source, limit)` loader that replaced three ad-hoc loaders | ✅ Textbook DRY refactor — proves the team already fixed one instance of the exact fragmentation this review is about |
| `rebuild_higher_tf.py` — up-samples lower-TF candles into a target higher-TF by UTC bucketing | ✅ **The right primitive for a canonical model** — currently used ad-hoc; the recommendation below promotes it to the default path |
| `bi5_maturity.py` — 6-phase roadmap already declares Phase 3 as *"canonical M1"* — the platform's own roadmap agrees with the direction of this review | ✅ Alignment |
| Per-hour download idempotency via `bi5_ingest_log` | ✅ Correct |
| Persistence adapters (`bi5_certification_store`, `market_spread_store`) — thin wrappers, clean writes | ✅ |

### 0.3 What is missing or wrong (the actual work)

| # | Gap | Severity | Evidence |
|---|---|---|---|
| G1 | **Every timeframe is downloaded independently** (H1 pulled separately from H4 pulled separately from M15) → cross-TF gaps are structural, not accidental | Critical | Header comment in `rebuild_higher_tf.py:5-9` states this outright |
| G2 | **No canonical M1 store** — the platform has candles, not ticks; the "tick_data" collection is referenced but empty | Major | `data_health.py:1-5` says "tick_data (when present)" |
| G3 | **Fragmented storage** — 4+ Mongo collections carry overlapping shape (`market_data`, `bi5_ingest_log`, `bi5_data_certifications`, `bi5_certifications`, `market_spread_store`) | Major | See §0.1 persistence layer |
| G4 | **No coverage-driven scheduler** — the auto-maintenance backfill loop doesn't consult the coverage report to decide what to fetch next | Major | `data_maintenance.py` uses a fixed lookback window |
| G5 | **Higher-TF rebuild is a one-shot script**, not a triggered pipeline that fires when M1 updates | Major | `legacy/scripts/rebuild_higher_tf.py` runs manually |
| G6 | **No compression on the largest collection** — 1M+ `market_data` docs at the previous pod would benefit from ~10× compression | Minor | Prior-pod DB restored 1,053,512 raw market_data docs |
| G7 | **No archive tier** — old M1 candles for delisted or dormant symbols still sit in the hot Mongo | Minor | Not observed in code |
| G8 | **Parallelism is single-threaded** — the download orchestrator processes symbols sequentially | Major | `bi5_ingest.py` orchestrator entry point takes one symbol + range |
| G9 | **No tick integrity index** — post-download validation is done but the validation *result* isn't queryable by time-range (only by cert record) | Minor | Certification store keyed by cert_id |
| G10 | **Timestamp validation is per-hour**, not cross-hour — cannot detect a 30-minute gap that spans two BI5 hour blobs | Minor | `validate_hour(...)` signature |

---

## 1. BI5 Pipeline — current + recommended

### 1.1 Current pipeline (implicit)

```
   admin trigger  →  POST /api/admin/bi5/run  →  download BI5 hour file
                                              →  decode ticks
                                              →  validate_hour() → BI5 Score
                                              →  bi5_ingest_log write
                                              →  aggregate to (symbol, TF) candles
                                              →  market_data write
                                              →  bi5_data_certification write
                                                    (per-window score)
```

Repeat per timeframe. Cross-TF gaps arise because the aggregation is
done inside the same call as the download, and the download is
scoped to (symbol, timeframe, hour) rather than (symbol, hour).

### 1.2 Recommended pipeline

```
   scheduler tick  →  coverage_planner.next_windows()
                        (reads coverage_report; returns list of
                         (symbol, hour_utc) that lack CERTIFIED M1)
                        │
                        ▼
   parallel workers  →  download BI5 hour                    ← unchanged primitive
                     →  validate_hour() → BI5 Score          ← reuse tick_validator
                     →  write to canonical_ticks[symbol,hour]
                        (append-only, hour-partitioned)
                     →  aggregate_hour_to_m1()               ← new pure function
                     →  upsert canonical_m1[symbol,minute]
                     │
                     ▼
   TF-rebuild trigger →  for tf in (M5, M15, H1, H4, D1):
                            aggregate_m1_to_tf(hour_window)
                            upsert market_data_tf[symbol,tf,ts]
                     │
                     ▼
   coverage_report writer →  update coverage_report[symbol,tf]
                             with new coverage extent
```

Only the top of the pipeline (download + validate) is time-consuming
and rate-limited by Dukascopy. Everything below M1 becomes cheap
in-process aggregation — never a separate download.

### 1.3 What changes for callers

**Nothing.** `data_access.load_ohlc_bars(pair, tf, ...)` keeps the
same signature. Underneath, it now reads from `market_data_tf` for
higher TFs (deterministically rebuilt from M1) instead of a
per-TF-downloaded copy that might diverge.

---

## 2. Canonical Data Model — recommended (Phase 2B core)

### 2.1 The four-layer contract

```
Raw BI5              ←  immutable download cache (disk or S3)
    ↓
Validated Ticks      ←  Mongo: canonical_ticks (per-symbol, hour-partitioned)
    ↓
Canonical M1         ←  Mongo: canonical_m1 (per-symbol, minute-partitioned)
    ↓
Generated Higher TFs ←  Mongo: market_data_tf (per-symbol × TF, in-process rebuild)
```

The user's proposed model, unchanged. The value is in **enforcing it
as the only path**, not just documenting it as an aspiration.

### 2.2 Schema sketches

**`canonical_ticks`** (append-only, per-hour):
```
{
  _id: {symbol, hour_utc},              # compound PK
  symbol: "EURUSD",
  hour_utc: 2026-01-19T14:00:00Z,
  tick_count: 12847,
  bi5_score: 0.94,                      # from validate_hour()
  session: "london",
  ticks: BinData(compressed_ticks),     # zstd-compressed BSON blob
  ingested_at, ingested_from, checksum
}
```
Storage: ~1 KB overhead + 8-16 KB compressed ticks per hour.
Retention: hot (Mongo) for the last 6 months; older → tiered archive.

**`canonical_m1`** (per-minute):
```
{
  _id: {symbol, ts},                    # compound PK
  symbol, ts (UTC minute),
  o, h, l, c, v,
  tick_count, spread_avg,
  source_bi5_score,                     # inherits from the hour
  derived_at
}
```
Storage: ~250 bytes per minute × 60 × 24 × 365 = ~130 MB/symbol/year.
Manageable for 20 symbols × 10 years = ~26 GB total.

**`market_data_tf`** (per higher-TF candle):
```
{
  _id: {symbol, tf, ts},
  symbol, tf (M5|M15|H1|H4|D1), ts,
  o, h, l, c, v,
  m1_source_hash,                       # hash of source M1 rows
  rebuilt_at
}
```
Storage: dominated by M5 (~30 MB/symbol/year), rest is trivial.
Deterministic — can be rebuilt from M1 at any time.

### 2.3 Migration from today's `market_data`

The existing `market_data` collection is a mixed bag of downloaded
candles from various TFs. The migration:

1. **Freeze `market_data` writes** (feature flag `USE_CANONICAL_M1`).
2. **Import M1 candles** from `market_data` where TF=M1 (they already
   exist from the prior pod backfill) into `canonical_m1` — pure copy
   with schema mapping.
3. **Discard higher-TF `market_data` rows** — regenerate them from
   `canonical_m1` via `aggregate_m1_to_tf()`. Deterministic.
4. **Backfill `canonical_ticks`** from disk BI5 archive where present
   (~110 MB seed). For gaps in the archive, mark hours as
   `bi5_score: null` — the M1 in `canonical_m1` came from candles,
   not from ticks, so downstream realism scores know they're operating
   on lower-fidelity data.
5. **Cutover:** switch `data_access.load_ohlc_bars()` to read
   `market_data_tf` instead of `market_data`. Zero API change.

Migration is idempotent and reversible. Both collections coexist
during the transition; a feature flag decides which the loader reads.

---

## 3. Storage

### 3.1 Compression

**Recommendation:** enable Mongo WiredTiger `zstd` compression on the
three big collections (`canonical_ticks`, `canonical_m1`,
`market_data_tf`). Default `snappy` compression achieves ~2×; `zstd`
at level 6 achieves ~10× on OHLC-ish data. For a 10-year, 20-symbol
production dataset, the delta is ~26 GB → ~10 GB.

Zero code change — a collection-creation-time option. Requires drop +
recreate on migration.

### 3.2 Partitioning

MongoDB doesn't natively partition collections, but the schema above
uses **compound primary keys** (`{symbol, hour_utc}`, `{symbol, ts}`,
`{symbol, tf, ts}`) that let the query planner prune aggressively.
Combined with the following indexes, this is functionally equivalent
to partitioning:

```
canonical_ticks:   {symbol: 1, hour_utc: -1}  (primary)
canonical_m1:      {symbol: 1, ts: -1}        (primary)
                   {ts: -1}                    (cross-symbol scans)
market_data_tf:    {symbol: 1, tf: 1, ts: -1} (primary)
                   {tf: 1, ts: -1}            (cross-symbol views)
coverage_report:   {symbol: 1, tf: 1}         (primary)
```

Recommend against sharding at current scale (~26 GB total). Revisit
when the corpus crosses ~500 GB.

### 3.3 Retention

Tiered:

- **Hot** (Mongo): all M1 + higher-TF; last 6 months of `canonical_ticks`
- **Warm** (Mongo, separate collection `canonical_ticks_archive`):
  ticks older than 6 months, still queryable but not indexed on
  `hour_utc DESC` (only on `symbol`)
- **Cold** (disk / S3): raw BI5 hour blobs — the original files, kept
  forever for regulatory / audit / rebuild

M1 is the retention floor. Higher-TF and tick storage are re-derivable
from M1 + cold BI5 respectively.

### 3.4 Rebuild capability

Two rebuild paths must be first-class operations:

1. **Higher-TF from M1** (fast, ~seconds/symbol/year). Endpoint:
   `POST /api/data/rebuild/tf` with `{symbol, tf, start, end}`.
   Idempotent — upsert by primary key.

2. **M1 from ticks** (slower, ~minutes/symbol/year). Endpoint:
   `POST /api/data/rebuild/m1` with `{symbol, start, end}`.
   Reads `canonical_ticks`, aggregates to M1, upserts.

Both are triggered automatically after any successful ingestion
window. Manual invocation is for disaster recovery.

---

## 4. Scheduler

### 4.1 Current state
- APScheduler `AsyncIOScheduler` in use (`bi5_cert_sweep_scheduler.py`, `ingestion_runner.py`).
- CronTrigger for the cert sweep.
- Data-maintenance loop with a fixed lookback window.

### 4.2 Recommended

**R4.1 — Coverage-driven planner.**
A new pure function `coverage_planner.next_windows()`:
```
def next_windows(now_utc, max_windows) -> list[(symbol, hour_utc)]:
    # 1. Read coverage_report for every (symbol, TF=M1) in the universe
    # 2. For each symbol, find the newest gap:
    #    - Missing hours since last recorded window
    #    - Weekend gaps handled (no BI5 on Sat-Sun)
    # 3. Prioritise: freshest gaps first, then oldest gaps
    # 4. Return up to max_windows tuples
```
Every scheduler tick calls this, gets ~50 windows, dispatches them to
parallel workers. Once coverage is complete, the planner returns
`[]` and the scheduler naturally idles.

**R4.2 — Parallel worker pool.**
```
async def worker(queue):
    while True:
        symbol, hour = await queue.get()
        try:
            await ingest_and_certify(symbol, hour, timeout=30s)
        except (DownloadFailed, RateLimited, ...):
            await backoff.wait(retries=n)
            queue.put_nowait((symbol, hour))  # requeue
        finally:
            queue.task_done()
```
Concurrency: 4–8 workers. Dukascopy tolerates parallel requests
across symbols but rate-limits per-symbol.

**R4.3 — Retry + backoff.**
- Transient (network, 5xx): exponential backoff, max 5 retries.
- Rate-limited (429): wait `Retry-After` header, requeue.
- Not-found (weekend gap, delisted): mark as `known_gap` in
  `coverage_report`, never retry.
- Corrupted (checksum mismatch): mark as `poisoned`, alert operator.

**R4.4 — Failure recovery.**
State lives in Mongo (`coverage_report` + `bi5_ingest_log`) —
crashing the scheduler at any point loses at most 1 hour's worth of
in-flight work; the planner picks up where it left off on the next
tick.

**R4.5 — Cadence.**
- Live catch-up: every 5 minutes (fresh hour usually available ~1
  minute after hour close).
- Historical backfill: continuous during off-peak hours, throttled
  during trading hours.
- Certification sweep: current cron (daily) unchanged.

---

## 5. Performance

### 5.1 CPU
- **Bottleneck today:** BI5 decoding (LZMA + tick decoding) is
  CPU-bound. Per-hour CPU: ~10-50 ms on modern hardware.
- **Recommendation:** offload decoding to a `ProcessPoolExecutor` (not
  ThreadPoolExecutor — Python GIL). 4 processes give ~4× throughput.
  Budget: 1 CPU core reserved for the pool.

### 5.2 RAM
- **Bottleneck today:** loading a full symbol's `market_data` into
  memory for aggregation. Current pod would need ~500 MB for one
  symbol × 10 years of M1.
- **Recommendation:** streaming aggregation via Mongo `$bucket` +
  `$project` pipeline. RAM budget: <100 MB regardless of range.

### 5.3 Disk
- Current: ~26 GB projected for 20 symbols × 10 years across three
  tiers. With `zstd` compression: ~10 GB.
- BI5 cold archive: ~1 GB per symbol × 10 years = ~20 GB. Keep on
  a separate volume so hot Mongo isn't affected by archive growth.

### 5.4 Caching
- **In-process LRU** for the last 200 (symbol, tf, ts_range) queries.
  ~50 MB cache holds a working set for typical dashboard reads.
- **No Redis needed at this scale.**
- **Cache invalidation:** on any `market_data_tf` upsert, invalidate
  by `(symbol, tf)` — coarse but correct.

### 5.5 Parallel aggregation
- M1→higher-TF aggregation is embarrassingly parallel across
  symbols. Trigger 4 rebuild workers, one per CPU.
- Aggregation window is 1 hour (matches ingestion cadence); rebuilds
  are always small, always fast.

### 5.6 Scalability
- Current design scales cleanly to ~100 symbols × 10 years without
  architectural changes.
- Beyond that: consider a per-symbol collection (`canonical_m1_EURUSD`,
  `canonical_m1_XAUUSD`, ...) — Mongo handles thousands of collections
  well. Trivial migration when the day comes.

---

## 6. Recovery Model

### 6.1 Data-corruption recovery

Every persisted row carries provenance:
- `canonical_ticks.checksum` — verified on read
- `canonical_m1.source_bi5_score` — traces back to the hour
- `market_data_tf.m1_source_hash` — traces back to M1

If a corruption is detected on read, the loader:
1. Marks the row `poisoned=True`
2. Triggers a rebuild request for that (symbol, range)
3. Returns HTTP 503 with `retry_after`

The scheduler picks up the rebuild request within one tick.

### 6.2 Cold-start recovery

Fresh production DB → coverage_report empty → planner returns every
(symbol, hour) since inception → workers ingest at ~4-8 hours per
minute → 20 symbols × 10 years × 24 × 365 = 1.75M hours ÷ 480/hr
= ~150 hours (~6 days) of continuous ingestion.

Acceptable for a one-time backfill. Can be shortened by pointing
the seed at an existing S3 archive of decoded ticks if you have one.

### 6.3 Partial-outage recovery

If only, say, `canonical_m1` gets corrupted:
- `canonical_ticks` is intact → rebuild M1 from ticks (fast)
- `market_data_tf` rebuilds from the new M1 (very fast)
- Coverage report re-derives itself from the rebuild

No re-download from Dukascopy is required unless `canonical_ticks`
itself is lost.

---

## 7. Alignment with the review's success criteria

| Criterion | Section | Status |
|---|---|---|
| BI5 pipeline (download, storage, integrity, gap, dup, timestamp, recovery, incremental) | §1 + §6 | ✅ Designed |
| Canonical data model (Raw → Ticks → M1 → Higher TFs) | §2 | ✅ Designed as the ONLY path |
| Storage (compression, partitioning, indexing, retention, archive, rebuild) | §3 | ✅ Designed |
| Scheduler (download, cadence, retry, failure, parallel) | §4 | ✅ Designed with a coverage-driven planner |
| Performance (CPU, RAM, disk, cache, parallel, scale) | §5 | ✅ Designed with concrete budgets |
| Recovery model | §6 | ✅ Provenance-anchored, three-tier |

---

## 8. Roadmap — sequenced, reversible

Same discipline as Phase 2A: each step behind a feature flag,
independently reversible, no step depends on a later step.

| # | Step | Prereq | Effort | Reversible? |
|---|---|---|---|---|
| **P2B.1** | Introduce `coverage_report` collection + coverage-driven planner (§4.1). Read-only for existing scheduler — writes the report but nothing consumes it yet | none | 1 day | Yes — planner disabled |
| **P2B.2** | Backfill `coverage_report` from existing `market_data` + `bi5_ingest_log`. One-time script; idempotent | P2B.1 | 0.5 day | Yes |
| **P2B.3** | New `canonical_ticks` + `canonical_m1` collections with schemas from §2.2. Empty on creation. `USE_CANONICAL_M1=false` flag keeps the old path active | P2B.1 | 1 day | Yes |
| **P2B.4** | New ingestion path that writes to `canonical_ticks` + derives `canonical_m1` in the same transaction. Runs alongside the old path (double-write, feature-flagged) | P2B.3 | 2 days | Yes — disable new path |
| **P2B.5** | Migrate M1 candles from `market_data` (TF=M1) into `canonical_m1`. Import script | P2B.4 | 0.5 day | Yes — new collection is separate |
| **P2B.6** | Rebuild `market_data_tf` from `canonical_m1` for M5/M15/H1/H4/D1. New collection; existing `market_data` untouched | P2B.5 | 1 day | Yes |
| **P2B.7** | Flip `USE_CANONICAL_M1=true` — `data_access.load_ohlc_bars` reads from `market_data_tf` instead of `market_data`. **This is the cutover** | P2B.6 | 0.5 day | Yes — flip flag back |
| **P2B.8** | Parallel worker pool + retry/backoff (§4.2, §4.3). Replaces the sequential ingest loop | P2B.4 | 1.5 days | Yes — worker count 1 = sequential |
| **P2B.9** | `zstd` compression on the three big collections (drop + recreate migration) | P2B.7 | 0.5 day | Yes but destructive — snapshot first |
| **P2B.10** | Tiered retention (`canonical_ticks_archive` warm tier + S3 cold archive) | P2B.9 | 1 day | Yes |
| **P2B.11** | Rebuild endpoints (`POST /api/data/rebuild/tf`, `POST /api/data/rebuild/m1`) — first-class operator surface | P2B.7 | 0.5 day | Yes |
| **P2B.12** | Retire `market_data` (rename to `market_data_deprecated`, keep for 90 days, then drop). Cleanup | P2B.7 stable ≥ 30 days | 1 hr | Yes during grace period |

**Approx effort:** ~10 focused days end-to-end. Steps P2B.1–P2B.4
can run in parallel with Phase 2A implementation (they touch
different code paths).

**Critical cutover point:** P2B.7. Before flipping the flag,
`market_data_tf` must be fully rebuilt (~1 hour of processing for
the current corpus). A dry-run comparing `market_data` (old) vs
`market_data_tf` (new) for the top 10 backtest jobs is a mandatory
gate.

---

## 9. What is deliberately NOT in this phase

- **No implementation.** Review only.
- **No schema drops.** All new tables coexist with old ones until
  the cutover in P2B.7, then a 30-day grace period before P2B.12.
- **No changes to `data_access.load_ohlc_bars` signature.** Callers
  are unaffected.
- **No changes to the tick_validator, bi5_certification, or
  bi5_realism modules.** They already do the right thing.
- **No changes to the BI5 cert-sweep scheduler.** It stays on its
  current cadence.

---

## 10. Interaction with Phase 2A (AI architecture)

Two points where the AI layer will benefit from this work:

1. The **coverage_report** collection becomes an ideal input for the
   `market_intelligence` capability the AI layer will call — "which
   symbols/timeframes have the most reliable data right now?" is a
   one-doc read post-P2B.1.

2. The **BI5 Score** already produced by `tick_validator` becomes a
   first-class *confidence signal* the AI can consume when reasoning
   about a strategy — "this strategy's backtest is against M1 with a
   BI5 score of 0.62, treat conclusions cautiously." Zero new
   engineering — just plumbing the existing score into VIE prompts.

---

## 11. Recommended next call

Approve or amend §2 (canonical data model) and §8 (roadmap sequencing),
then execute **P2B.1** — a 1-day step that introduces the
coverage_report collection and the planner function *without changing
any existing behaviour*. That gives us the observability substrate
that everything downstream depends on.

The rest can then unfold in whatever order fits your operational
calendar — the roadmap is designed so no step blocks another.
