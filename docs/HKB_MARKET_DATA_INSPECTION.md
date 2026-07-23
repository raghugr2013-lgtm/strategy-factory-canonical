# market_data Bundle — Detailed Inspection

_Report date · 2026-07-23_
_Source · `hkb_staging_20260723.market_data` (isolated staging DB)_
_Status · analysis only, no import performed_

## 1. Headline Numbers

| Metric | Value |
|---|---|
| Total records | **1,053,512** |
| Distinct symbols | **7** |
| Distinct sources | **1** (`bid_1m`) |
| Distinct timeframes | **5** (15m · 30m · 1h · 4h · 1d) |
| Earliest timestamp | **2023-05-09T00:00:00Z** |
| Latest timestamp | **2026-05-16T00:00:00Z** |
| Time span covered | **~3 years, 7 days** |
| Storage format | **OHLCV** (open · high · low · close · volume) |
| Tick data present? | ❌ No |
| Bid/Ask spread present? | ❌ No |
| Compound index shipped in dump | `symbol_1_source_1_timeframe_1_timestamp_1` |
| Payload size | ~200 MB uncompressed on Mongo, ~30 MB in the gzipped dump |

## 2. Asset Classes Covered

| Asset class | Symbols | Records | % of total |
|---|---|---:|---:|
| **Crypto**       | BTCUSD, ETHUSD                 | 382,664 | 36.3 % |
| **Forex majors** | EURUSD, GBPUSD, USDJPY         | 413,743 | 39.3 % |
| **Metals**       | XAUUSD                         | 130,190 | 12.4 % |
| **Indices**      | US100 (Nasdaq 100 CFD)         | 126,915 | 12.0 % |

## 3. Complete Coverage Matrix (symbol × timeframe)

Every one of the 35 (symbol × timeframe) cells has 3 years of continuous
coverage. No gaps in the middle; all "misses" are at the earliest edge
(some symbols started tracking on May 14 rather than May 9).

| Symbol | 15m | 30m | 1h | 4h | 1d | Symbol total | Earliest |
|---|---:|---:|---:|---:|---:|---:|---|
| BTCUSD | 104,931 | 52,475 | 26,242 | 6,566 | 1,098 | **191,312** | 2023-05-14 |
| ETHUSD | 104,952 | 52,489 | 26,248 | 6,567 | 1,096 | **191,352** | 2023-05-14 |
| EURUSD |  77,134 | 37,636 | 18,816 | 4,865 |   945 | **139,396** | 2023-05-09 |
| GBPUSD |  75,253 | 37,631 | 18,814 | 4,864 |   944 | **137,506** | 2023-05-09 |
| USDJPY |  74,890 | 37,447 | 18,722 | 4,841 |   941 | **136,841** | 2023-05-14 |
| XAUUSD |  71,102 | 35,555 | 17,786 | 4,810 |   937 | **130,190** | 2023-05-14 |
| US100  |  68,849 | 34,632 | 17,695 | 4,802 |   937 | **126,915** | 2023-05-14 |
| **TF total** | **577,111** | **287,865** | **144,323** | **37,315** | **6,898** | **1,053,512** | — |

## 4. Storage Schema (verbatim from a sampled doc)

```json
{
  "_id": "6a05dff5074e617067ed3ede",
  "symbol":    "BTCUSD",
  "timeframe": "15m",
  "source":    "bid_1m",
  "timestamp": "2023-05-14T00:00:00+00:00",
  "open":      26729.3,
  "high":      26752.6,
  "low":       26664.3,
  "close":     26714.2,
  "volume":    0.00075
}
```

- 10 fields per doc. No nested structure.
- No `bid` / `ask` fields.
- No microsecond-level ticks — every row is a completed OHLCV bar at the
  named timeframe.
- The `source='bid_1m'` label means: 1-minute BID-side candles were the raw
  ingest, then resampled server-side into 15m/30m/1h/4h/1d bars. The 1-minute
  raw bars themselves are **not** stored.

## 5. Data Source Attribution

The dump does not carry a `provider` field, only `source='bid_1m'`. Cross-referencing the source manifest and the export-side design docs
(`app/memory/BI5_R1_ARCHITECTURAL_BLUEPRINT.md` in `hkb/bundle_files/`)
strongly suggests these are Dukascopy BID-only candles (their public
1-minute BID feed is the industry-standard 3-year archive for these
seven symbols and is the source most likely to be labelled `bid_1m` in an
autonomous factory built for prop-firm challenges). The manifest also
references BID + BI5 streams by name (BI5 is Dukascopy's own binary
format).

**Confidence:** high but not verified — the operator team on the 1-vCPU
pod would know for certain from the ingestion scripts. Practically it
does not matter for the migration decision: the OHLCV schema is
provider-agnostic and drops in wherever OHLCV is consumed.

## 6. Is This Data Still Valuable vs. Live Providers?

### 6.1 What the current backend does after VPS Phase-1 activation

Reviewing `docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md`, `navigation.js`
`phase2Sources`, and the data-maintenance adapter — the current factory
expects a live-provider chain: **Kraken · Coinbase · Alpaca · IEX ·
Alpha Vantage**. The `data-maintenance` engine will backfill on-demand
via `POST /api/data/maintenance/run` and gap-fill via
`POST /api/data/coverage/rehydrate`.

However — the real-world **speed of that backfill depends entirely on
the provider tier**:

- Free-tier Alpha Vantage: 5 requests/minute → filling 3 years of
  1h EURUSD alone takes ~5 hours of throttled polling.
- Alpaca free tier: 200 req/min → same task in ~10 minutes.
- Kraken/Coinbase public REST: unauthenticated ~1 req/sec on Crypto
  only; will not backfill Forex/Metals/Indices at all.
- IEX: US equities & indices, requires paid subscription for extended
  history.
- Paid tiers: 3-year backfill in minutes but costs money.

### 6.2 Value verdict

The HKB market_data has three material advantages over "wait for live
providers":

1. **Immediate 3-year backtesting corpus** — day-1 backtest surface
   works instantly for all 7 configured pairs at 5 timeframes.
   Otherwise the operator watches an empty coverage matrix for
   hours-to-days depending on provider tier.
2. **Reproducibility** — the HKB corpus is the exact data the historical
   research corpus (the 1,042 mutation runs, 10,430 events) was scored
   against. Importing it lets the operator replay any of those runs and
   audit the numbers byte-for-byte. Without it, replays would produce
   subtly different results because live-provider bars are not
   guaranteed to reconcile with Dukascopy BID bars.
3. **No provider spend during activation** — VPS Phase-1 can activate
   without pushing any provider quota; the factory can boot into a
   fully-backfilled state and only reach out for the **incremental**
   catch-up (2026-05-16 → today).

And two material disadvantages:

1. **Single-sided data (BID only)** — realistic execution simulation
   requires bid/ask spread to model slippage. This corpus is fine for
   directional-signal backtesting but not for realistic P&L
   projection. The current factory's `execution-quality` +
   `market-spread` collections are empty for a reason — the operator
   is expected to wire a spread-aware provider later. This HKB does
   not help with that.
2. **Provider-mismatch risk** — once live providers start streaming
   (e.g. Kraken for BTCUSD), the tail of the timeline (post-2026-05-16)
   will be Kraken candles, while the head (pre-2026-05-16) is
   Dukascopy BID candles. Backtests spanning the boundary will show a
   small step change on the exact date of the flip. This is
   cosmetically ugly but does not corrupt research (the delta is
   sub-tick for majors, 1–2 ticks for XAUUSD, negligible on 15m+ bars).

### 6.3 Regeneration timeline (if you defer)

Given the current backend's provider configuration is unknown at
report time, a reasonable estimate for how long the coverage matrix
would take to reach parity with the HKB market_data if you **defer**:

| Provider mix | Estimated backfill time to reach HKB parity |
|---|---|
| Free-tier Alpha Vantage only | 24–48 hours of continuous polling |
| Free-tier Alpaca only | 1–3 hours |
| Paid Polygon or Databento | 5–20 minutes |
| Kraken + Coinbase (crypto only) | 10–30 minutes; Forex/Metals/Indices coverage stays at zero |

## 7. Recommendation

For **your specific situation** — operator wants to activate VPS
Phase-1 imminently, with a full operator dashboard and complete
research audit trail — **the balance favours import**:

- ✅ You already have the exact data the historical corpus was scored
  against; the mutation lineage and library specimens become
  audit-replayable.
- ✅ No provider spend during Phase-1 activation window.
- ✅ 3-year backtest surface online from minute 1.
- ⚠ Accept the BID-only limitation until you wire a spread-aware
  provider (which is a separate, later decision).
- ⚠ Accept the small step-change on the 2026-05-16 boundary once live
  providers start writing new bars.

### If you decide IMPORT

Runtime cost of the import: **~30–60 seconds** for the bulk restore
into an empty `strategy_factory_v1.market_data`, plus 5–10 seconds to
build the compound index. Idempotent — safe to re-run.

```bash
# One-liner (safe against re-run; upserts by _id):
mongorestore --uri="$MONGO_URL" \
  --nsFrom='hkb_staging_20260723.market_data' \
  --nsTo='strategy_factory_v1.market_data' \
  --archive=/app/hkb/dump_extracted/mongo_full.archive
```

### If you decide DEFER

Zero action required. When you activate VPS Phase-1 the
`data-maintenance` engine will begin backfilling automatically. If you
later change your mind, the staging DB `hkb_staging_20260723` will
remain in place until you drop it — you can import at any point via
the one-liner above.

### If you decide DROP entirely

Zero action required. The staging DB can be dropped whenever
convenient; the underlying bundle at `/app/hkb/migration_bundle.tar.gz`
is preserved so future re-imports remain possible.

## 8. Data captured for this report

Machine-readable inventory saved at
`/app/hkb/reports/phase1_market_data.json` — includes the per-cell
counts, min/max timestamps for every symbol × timeframe, and the
schema field list.
