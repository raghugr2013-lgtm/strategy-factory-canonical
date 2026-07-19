# Coverage API — Contract Preview
### `GET /api/data/coverage` — proposed response schema (Sub-stage 2.θ)

> **Status:** preview only — no implementation yet.
> Requested by operator on 2026-02-19 before Sub-stage 2.θ.
> This document defines the API contract; implementation lands after
> operator sign-off.
> Depends on: Sub-stages 2.ε (CTS) and 2.ζ (HTF cache) landing first.

---

## 1. Purpose

Give operators and downstream consumers (backtesting engines, meta-learning,
UI dashboards) a single JSON view of the market-data plane. Answers:

- What symbols do we have? Which timeframes? What date ranges?
- Where are the gaps, and how bad are they?
- Is the canonical source (M1) complete for each symbol?
- Which HTF cache buckets are materialised? Which are stale? Which are missing?
- When did we last synchronise with the provider?
- Is any subsystem's data health degraded, and why?

---

## 2. Endpoint

```
GET /api/data/coverage
GET /api/data/coverage?symbol=EURUSD
GET /api/data/coverage?symbol=EURUSD&timeframe=H1
GET /api/data/coverage?since=2025-01-01
GET /api/data/coverage?include=gaps,cache,provider
```

**Query parameters:**

| Param | Type | Default | Meaning |
|---|---|---|---|
| `symbol` | string | *(all)* | Filter to a single symbol |
| `timeframe` | string | *(all)* | Filter to a single derived TF (`1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`) |
| `since` | ISO date | *(none)* | Only report data + gaps at or after this date |
| `include` | comma list | `all` | Subset of blocks to include: `summary,symbols,gaps,cache,provider,health` |
| `format` | `json` \| `prometheus` | `json` | Response format |

**Auth:** requires admin bearer token (Phase-1 pattern).

---

## 3. Response schema

### 3.1 Top-level shape

```json
{
  "ts": "2026-02-19T14:30:00+00:00",
  "canonical_mode": "m1",
  "summary": { ... },
  "symbols": [ ... ],
  "gaps": [ ... ],
  "cache": { ... },
  "provider": { ... },
  "health": { ... }
}
```

- `ts` — response generation time (UTC ISO)
- `canonical_mode` — the platform-wide canonical mode: `"m1"` (Option D from `BID_CANDLE_STORAGE_REVIEW.md`) or `"mixed"` (some instruments in `native_tf` fallback)

### 3.2 `summary` — one-line answer to "how are we doing?"

```json
"summary": {
  "symbol_count":                  20,
  "canonical_symbol_count":        19,   // symbols on M1 canonical mode
  "native_tf_symbol_count":         1,   // symbols on native-TF fallback
  "m1_row_count_total":       120345678,
  "cache_bucket_count":          1440,
  "cache_bucket_stale_count":       3,
  "cache_bucket_missing_count":    24,
  "coverage_completeness_pct":   99.87,  // (present ÷ expected) × 100
  "gap_count":                     47,
  "gap_severity_max":         "moderate",
  "provider_sync_last_at": "2026-02-19T14:15:00+00:00",
  "provider_sync_lag_seconds":     900,
  "cts_health_score":              98
}
```

- `coverage_completeness_pct` — treating any bar missing from M1 that would be expected during a market session as a gap, this is the total-across-all-symbols completeness percentage
- `gap_severity_max` — the worst gap tier observed across the whole window: `informational`, `warning`, `governance_review`, or `null`
- `provider_sync_lag_seconds` — how long ago we last successfully appended data from the provider

### 3.3 `symbols` — one row per symbol

```json
"symbols": [
  {
    "symbol": "EURUSD",
    "canonical_mode": "m1",              // "m1" | "native_tf" (per-instrument override)
    "provider": "dukascopy",
    "m1_first_ts": "2003-05-04T21:00:00+00:00",
    "m1_last_ts":  "2026-02-19T14:29:00+00:00",
    "m1_row_count": 8123456,
    "expected_row_count": 8125402,
    "completeness_pct": 99.98,
    "gap_count": 3,
    "gap_severity_max": "informational",
    "cache_status": {
      "buckets_total":  72,
      "buckets_fresh":  70,
      "buckets_stale":   1,
      "buckets_missing": 1
    },
    "last_topup_at": "2026-02-19T14:15:00+00:00",
    "last_topup_rows": 15,
    "last_gap_repair_at": "2026-02-18T02:00:00+00:00"
  },
  { "symbol": "GBPUSD", ... }
]
```

### 3.4 `gaps` — enumerated per-gap detail

```json
"gaps": [
  {
    "symbol": "EURUSD",
    "timeframe": "1m",                  // always "1m" — HTF gaps derive from M1
    "start": "2025-11-24T22:03:00+00:00",
    "end":   "2025-11-24T22:07:00+00:00",
    "missing_bars": 4,
    "severity": "informational",       // informational | warning | governance_review
    "reason": "session_gap_extension",  // known holiday / rollover / provider outage / unknown
    "provider_confirmed_absent": false, // did we ask provider and confirm no data exists?
    "repair_attempted_at": "2025-11-25T00:12:00+00:00",
    "repair_result": "no_data_available",
    "manual_flag_ignored": false        // operator has explicitly accepted this gap
  }
]
```

- `severity` mirrors the tiered policy from `BID_CANDLE_STORAGE_REVIEW.md §10.3`
- Response caps the list at the top 500 gaps by severity+size; a `gaps_truncated: true` field appears if more exist
- Query with `include=gaps` for the enumerated list; without it, only `summary.gap_count` is populated

### 3.5 `cache` — HTF materialisation state

Per the sharding in `BID_CANDLE_STORAGE_REVIEW.md §10.2`: buckets keyed by `symbol|timeframe|yyyy-mm`.

```json
"cache": {
  "bucket_count":        1440,
  "bucket_fresh_count":  1413,
  "bucket_stale_count":     3,
  "bucket_missing_count":  24,
  "bytes_used":     524288000,
  "hit_ratio_last_hour":   0.947,
  "hit_ratio_last_day":    0.912,
  "aggregation_ms_p50":       15,
  "aggregation_ms_p95":       78,
  "aggregation_ms_p99":      210,
  "recent_invalidations_last_hour": 12,
  "recent_rebuilds_last_hour":       4
}
```

For debug: `?include=cache_detail` adds a per-bucket enumeration
(capped at 500 stale/missing buckets).

### 3.6 `provider` — synchronisation status

```json
"provider": {
  "sources": [
    {
      "source": "dukascopy",
      "kind": "bid_1m",                          // bid_1m | bi5 | csv | ...
      "last_sync_at":     "2026-02-19T14:15:00+00:00",
      "last_sync_ok":     true,
      "last_sync_rows":   324,
      "consecutive_failures":  0,
      "next_sync_estimated_at": "2026-02-19T14:30:00+00:00",
      "rate_limit_state": "ok"                    // ok | approaching | throttled
    },
    { "source": "dukascopy", "kind": "bi5", ... }
  ],
  "verification_status": {
    "last_htf_diff_at":     "2026-02-01T00:00:00+00:00",
    "next_htf_diff_at":     "2026-03-01T00:00:00+00:00",
    "last_htf_diff_tier":   "informational",
    "last_bid_bi5_diff_at": "2026-02-01T00:00:00+00:00",
    "last_bid_bi5_diff_tier": "informational"
  }
}
```

- Advisory only — this endpoint reports state; **never triggers rewrites**
- `verification_status` mirrors the monthly-check discipline from `BID_CANDLE_STORAGE_REVIEW.md §10.3` + §10.6

### 3.7 `health` — CTS's own `HealthSnapshot`

Reuses the Universal Health Contract (§4 of `PHASE_2_VALIDATION_GATE_1_REPORT.md`):

```json
"health": {
  "subsystem": "cts",
  "ts": "2026-02-19T14:30:00+00:00",
  "health_score": 98,
  "readiness_score": 100,
  "confidence_score": 97,
  "resource_usage": {
    "cpu_percent": 4.2,
    "mem_mb": 342,
    "in_flight": 1,
    "queue_depth": 0,
    "budget_headroom": null
  },
  "last_successful_run": {
    "at": "2026-02-19T14:29:53+00:00",
    "duration_ms": 42,
    "ref": "EURUSD|H1|2026-02"
  },
  "failure_count": {
    "last_hour": 0,
    "last_day": 0,
    "since_boot": 0
  },
  "recovery_status": {
    "state": "ok",
    "reason": "",
    "action_required": "none",
    "last_recovery_at": null
  }
}
```

`GET /api/health/cts` returns just this block; the coverage endpoint
embeds it for cross-reference.

---

## 4. Response for `format=prometheus`

Same information, Prometheus text-exposition. Metric names align with
the `Metric` catalogue in `engines/metrics.py`:

```
# HELP cts_coverage_completeness_pct Percentage of expected bars present in canonical M1
# TYPE cts_coverage_completeness_pct gauge
cts_coverage_completeness_pct{symbol="EURUSD"} 99.98
cts_coverage_completeness_pct{symbol="GBPUSD"} 99.71
...
# HELP cts_m1_row_count Total M1 rows stored per symbol
# TYPE cts_m1_row_count gauge
cts_m1_row_count{symbol="EURUSD"} 8123456
...
# HELP cts_cache_bucket_count Cache bucket counts by state
# TYPE cts_cache_bucket_count gauge
cts_cache_bucket_count{symbol="EURUSD",state="fresh"} 70
cts_cache_bucket_count{symbol="EURUSD",state="stale"} 1
cts_cache_bucket_count{symbol="EURUSD",state="missing"} 1
...
# HELP cts_cache_hit_ratio Cache hit ratio (rolling)
# TYPE cts_cache_hit_ratio gauge
cts_cache_hit_ratio{window="hour"} 0.947
cts_cache_hit_ratio{window="day"} 0.912
...
# HELP cts_aggregation_ms_bucket Aggregation latency histogram
# TYPE cts_aggregation_ms_bucket histogram
cts_aggregation_ms_bucket{le="10"} 8412
cts_aggregation_ms_bucket{le="50"} 9871
cts_aggregation_ms_bucket{le="100"} 9990
cts_aggregation_ms_bucket{le="500"} 9999
cts_aggregation_ms_bucket{le="+Inf"} 10000
cts_aggregation_ms_sum 145238.2
cts_aggregation_ms_count 10000
```

---

## 5. Related endpoints (implemented alongside)

| Endpoint | Purpose |
|---|---|
| `GET /api/data/coverage` | The main endpoint (this document) |
| `GET /api/data/coverage/gaps` | Full gap enumeration; unbounded pagination via `?cursor=` |
| `GET /api/data/coverage/{symbol}` | Single-symbol detail, always includes gaps + cache |
| `GET /api/cts/state` | CTS snapshot without coverage data (fast, cheap) |
| `GET /api/cts/cache/{symbol}/{timeframe}` | Per-bucket detail for one symbol×TF |
| `POST /api/cts/cache/rebuild` | Force rebuild of specific buckets (admin only) |
| `POST /api/cts/verify/{symbol}` | Trigger provider-HTF verification (admin only) |
| `GET /api/health/cts` | Universal Health Contract snapshot for CTS |

---

## 6. Design invariants (must hold at implementation)

1. **Read-only.** The coverage endpoint never triggers writes, backfills, or rebuilds. It reports state.
2. **Fast.** Full response for 20 symbols × 7 TFs should be < 500 ms. Coverage state is pre-aggregated by the CTS in a small `coverage_report` collection updated on cache events.
3. **Cache-friendly.** Response carries `ETag` + `Last-Modified` headers so dashboards can poll cheaply.
4. **Governance-safe.** No secrets in response (no API keys, no auth tokens, no internal file paths).
5. **Distribution-ready.** In γ+, the endpoint aggregates across nodes; the shape stays identical.

---

## 7. Open questions (for operator approval)

1. **Auth:** admin-only, or should read-only researchers see coverage too? Recommend **admin OR researcher role** (write endpoints stay admin-only).
2. **Rate limit:** coverage aggregates are fast — no rate limit needed. Confirm?
3. **Historical windows:** should the response include a moving-window subset (e.g. last 30 days only) as default, with `?full=true` for the entire history?
4. **Prometheus format naming:** we follow `cts_*` prefix conventions here. Any alternative naming convention preferred?
5. **UI integration:** we expect this endpoint to back a "Market Data" panel on the operator dashboard. Do you want a mockup of that panel before implementation?

---

## 8. Sign-off

Pending operator approval before implementation lands as Sub-stage 2.θ.

*Depends on:* Sub-stage 2.ε (CTS foundation), 2.ζ (HTF cache) — implementation blocked until those two land.
*Reviewed against:* `BID_CANDLE_STORAGE_REVIEW.md §10`, `PHASE_2_CONSOLIDATED_REVIEW.md §5.1`, `engines/metrics.py`.
