# P0B Phase 2 — Completion Report

**Scope**: BI5 Certification, Phase 2 — Persistence & Adapters.
Translates Phase 1 pure-function outputs into idempotent Mongo writes
against two new collections (`market_spread`, `bi5_certification`),
and wires per-minute spread persistence into the existing
`bi5_ingest_runner` hour loop.

**Working directory**: `/app/_review/deployment-ready/source/backend_main/backend/`

**Date**: 2026-01

---

## 1. Files Added

| Path | Purpose |
| --- | --- |
| `engines/persistence_adapters/__init__.py` | Adapter package — re-exports the public adapter surface. |
| `engines/persistence_adapters/market_spread_store.py` | `upsert_spread_bars`, `find_spread_bars`. Persists `SpreadBar` → `market_spread` (idempotent on `(symbol, minute_utc)`). |
| `engines/persistence_adapters/bi5_certification_store.py` | `upsert_certification`, `get_certification`, `get_latest_certification`, `find_by_verdict`. Persists `BI5ScoreReport` → `bi5_certification` (idempotent on `(symbol, window_start_utc, window_end_utc)`). |
| `tests/test_market_spread_store.py` | 7 mongomock-backed tests for the spread adapter. |
| `tests/test_bi5_certification_store.py` | 10 mongomock-backed tests for the certification adapter. |
| `tests/test_bi5_ingest_spread_wiring.py` | 3 integration tests proving the runner writes BOTH `market_data` rows AND `market_spread` rows when a Mongo handle is injected. |
| `PHASE2_COMPLETION_REPORT.md` | This report. |

## 2. Files Modified

| Path | Change |
| --- | --- |
| `engines/db_indexes.py` | Added 6 new index specs (4 for `bi5_certification`, 2 for `market_spread`) and 1 TTL spec for `market_spread.created_at_dt`. Added env-tunable `MARKET_SPREAD_TTL_DAYS` (default 180). Surfaced `market_spread` TTL in the `ensure_indexes` return value. |
| `data_engine/bi5_ingest_runner.py` | (a) New imports: `rollup_spread_minutes`, `upsert_spread_bars`. (b) `BI5IngestRunner.__init__` now accepts optional `db=None`. (c) `_process_one_hour` derives `SpreadBar`s from the same decoded tick stream used for 1m bars and, when `db is not None`, upserts them via the new adapter. (d) `HourResult` + `IngestReport` gained `spread_bars_emitted[_total]` and `spread_bars_upserted[_total]`. (e) `run_bi5_ingest` accepts `db=None` and forwards it. |

**No other production files were touched.** No edits to BID-stage modules, no edits to `engines/tick_validator.py` / `spread_analyzer.py` / `slippage_model.py` / `execution_simulator.py` (Phase 1 surface is frozen). No edits to lifecycle / market_universe / scheduler / activation matrix.

## 3. Public Functions Added

### `engines.persistence_adapters.market_spread_store`
- `upsert_spread_bars(db, bars, *, now_dt=None) -> {matched, upserted, modified}`
- `find_spread_bars(db, *, symbol, start_utc, end_utc) -> List[Dict]`
- Constant: `MARKET_SPREAD_COLL = "market_spread"`

### `engines.persistence_adapters.bi5_certification_store`
- `upsert_certification(db, report, *, weights=DEFAULT_WEIGHTS, certified_at_dt=None) -> {matched, upserted, modified, key}`
- `get_certification(db, *, symbol, window_start_utc, window_end_utc) -> Optional[Dict]`
- `get_latest_certification(db, *, symbol) -> Optional[Dict]`
- `find_by_verdict(db, *, verdict, limit=50, since_dt=None) -> List[Dict]`
- Constant: `BI5_CERT_COLL = "bi5_certification"`

### `data_engine.bi5_ingest_runner` (extended)
- `BI5IngestRunner(*, adapter=None, archive=None, own_adapter=True, db=None)` — new kw-only `db` parameter.
- `run_bi5_ingest(symbol, *, start_utc, end_utc, use_cache=True, adapter=None, archive=None, db=None)` — new kw-only `db` parameter.

## 4. Mongo Schemas Persisted

### `market_spread`
```json
{
  "symbol":            "EURUSD",
  "minute_utc":        ISODate,                // BSON Date (queryable)
  "minute_iso":        "2026-02-03T09:00:00+00:00",
  "spread_open":       0.00010,
  "spread_high":       0.00030,
  "spread_low":        0.00010,
  "spread_close":      0.00010,
  "spread_mean":       0.00018,
  "tick_count":        412,
  "src":               "bi5",
  "evaluator_version": "spread_analyzer@P0B-v1",
  "created_at_dt":     ISODate                  // TTL field (set on insert only)
}
```
Domain key: `(symbol, minute_utc)` — unique compound index.

### `bi5_certification`
```json
{
  "symbol":               "EURUSD",
  "window_start_utc":     ISODate,
  "window_end_utc":       ISODate,
  "hours_expected":       24,
  "hours_present":        23,
  "hours_missing":        0,
  "hours_expected_empty": 0,
  "hours_decode_fail":    1,
  "ticks_total":          542019,
  "non_monotonic_ticks":  0,
  "price_outlier_ticks":  2,
  "zero_vol_ticks":       0,
  "sparse_hours":         0,
  "low_density_hours":    3,
  "max_silent_gap_s":     18.4,
  "subscores":            {"cov":..., "integrity":..., "price":..., "density":..., "continuity":...},
  "bi5_score":            0.0,
  "verdict":              "FAIL",
  "weights_used":         {...},
  "evaluator_version":    "tick_validator@P0B-v1",
  "certified_at_dt":      ISODate                // set on insert only
}
```
Domain key: `(symbol, window_start_utc, window_end_utc)` — unique compound index.

## 5. Indexes & TTLs Declared (idempotent, in `db_indexes.py`)

| Collection | Name | Keys | Unique | TTL |
| --- | --- | --- | :-: | :-: |
| `market_spread` | `ix_spread_sym_min` | `(symbol ↑, minute_utc ↑)` | ✅ | — |
| `market_spread` | `ix_spread_min` | `(minute_utc ↓)` | | — |
| `market_spread` | `ttl_market_spread` | `created_at_dt` | | **180 d** (env `MARKET_SPREAD_TTL_DAYS`) |
| `bi5_certification` | `ix_bi5cert_sym_window` | `(symbol ↑, window_start_utc ↑, window_end_utc ↑)` | ✅ | — |
| `bi5_certification` | `ix_bi5cert_sym_ts` | `(symbol ↑, certified_at_dt ↓)` | | — |
| `bi5_certification` | `ix_bi5cert_verdict` | `(verdict ↑, certified_at_dt ↓)` | | — |
| `bi5_certification` | `ix_bi5cert_ts` | `(certified_at_dt ↓)` | | — |

`bi5_certification` has **no TTL** by design — certifications are audit/compliance evidence.

Verified by running `engines.db_indexes.ensure_indexes()` against a mongomock client: all 6 indexes + 1 TTL register without error, no spec conflicts with existing entries.

## 6. Tests Added (Phase 2)

| File | Tests | Notes |
| --- | --: | --- |
| `tests/test_market_spread_store.py` | 7 | Insert, idempotent re-upsert (in-place update), `$setOnInsert` `created_at_dt` immutability, empty-input no-op, minute-floor normalisation, time-range `find` ordering, symbol filtering. |
| `tests/test_bi5_certification_store.py` | 10 | Insert, idempotent re-upsert, `certified_at_dt` immutability, verdict validation, point lookup (`get_certification`), `get_latest_certification` ordering + missing-symbol → None, `find_by_verdict` filtering, `since_dt` filter, verdict validation on read. |
| `tests/test_bi5_ingest_spread_wiring.py` | 3 | Integration: runner writes both `market_data` (via `_merge_rows` spy) AND `market_spread` (via mongomock) when `db` is injected; `db=None` leaves the P0A path untouched (zero Mongo dependency); re-runs are idempotent (no duplicate spread rows). |

All tests are mongomock-backed (`mongomock-motor`) — they require no real Mongo and no network.

## 7. Phase 2 Tests — Pass / Fail

```text
collected 20 items
tests/test_market_spread_store.py        7 passed
tests/test_bi5_certification_store.py   10 passed
tests/test_bi5_ingest_spread_wiring.py   3 passed
============================== 20 passed in 0.58s ==============================
```

## 8. Full Suite (Phase 1 + Phase 2 + P0A regression)

```text
collected 121 items
tests/test_tick_validator.py             23 passed
tests/test_spread_analyzer.py            12 passed
tests/test_slippage_model.py             23 passed
tests/test_execution_simulator.py        20 passed
tests/test_market_spread_store.py         7 passed
tests/test_bi5_certification_store.py    10 passed
tests/test_bi5_ingest_spread_wiring.py    3 passed
tests/test_bi5_ingest_runner_e2e.py      12 passed       (P0A regression)
tests/test_tick_aggregator.py             6 passed       (P0A regression)
tests/test_tick_archive.py                5 passed       (P0A regression)
============================ 121 passed in 1.44s ============================
```

**Zero regressions** in the P0A pipeline.

## 9. Dependency Diagram

```
                          ┌─────────────────────────────┐
                          │ engines/tick_validator.py   │  (Phase 1 — pure)
                          └─────────────────────────────┘
                                         ▲
                                         │  BI5ScoreReport, DEFAULT_WEIGHTS
                          ┌──────────────┴──────────────────────────┐
                          │ engines/persistence_adapters/           │
                          │   bi5_certification_store.py            │
                          └─────────────────────────────────────────┘
                                         │
                                         ▼
                                     [ Mongo ]                            (Phase 2 boundary)
                                         ▲
                                         │
                          ┌──────────────┴──────────────────────────┐
                          │ engines/persistence_adapters/           │
                          │   market_spread_store.py                │
                          └─────────────────────────────────────────┘
                                         ▲
                                         │  SpreadBar
                          ┌──────────────┴──────────────┐
                          │ engines/spread_analyzer.py  │  (Phase 1 — pure)
                          └─────────────────────────────┘
                                         ▲
                                         │  rollup_spread_minutes(ticks)
                          ┌──────────────┴──────────────┐
                          │ data_engine/                │  (existing — P0A)
                          │   bi5_ingest_runner.py      │
                          └─────────────────────────────┘
                                         │
                                         ├──→ _merge_rows → market_data (P0A path, unchanged)
                                         └──→ upsert_spread_bars → market_spread (NEW)
```

External deps added in Phase 2: `mongomock-motor` (test-only), `pytest-asyncio` (test-only).
Production deps: unchanged — adapters use `pymongo` (already pinned).

## 10. Firewall Confirmation

| Check (Phase 2 modules: 3 adapter files + bi5_ingest_runner changes) | Status |
| --- | :-: |
| No imports from `engines/` BID-stage modules (`discovery`, `mutation`, `validation`, `pass_probability`, `challenge_matching_engine`, `matching_engine`, `portfolio_*`, `phase30_*`, `gem_factory_*`) | ✅ |
| No imports from `engines/market_universe.py` (preserves the R0–R5 lock) | ✅ |
| No imports from `api/*` in the adapters (one-way: server can import adapters, adapters cannot import server) | ✅ |
| No HTTP / network clients (`requests`, `httpx`, `urllib`, `aiohttp`) | ✅ |
| No filesystem writes from adapters (`open`, `Path`, `read_text`, `write_text`) | ✅ |
| Phase 1 pure modules still pure — no Mongo / no I/O added | ✅ |
| `bi5_ingest_runner` only added a *call-out* to the Phase 1 pure `rollup_spread_minutes` and to the new adapter; no new BID-stage imports | ✅ |

Verification commands (run from `backend/`):
```bash
grep -nE "^(import|from) +(engines\.(discovery|mutation|validation|pass_probability|challenge|matching_engine|portfolio|phase30|gem_factory|market_universe)|api|fastapi|sqlalchemy|requests|httpx|urllib|aiohttp)" \
  engines/persistence_adapters/*.py
grep -nE "(open\(|Path\(|os\.path|pathlib|read_text|write_text|requests\.|urlopen)" \
  engines/persistence_adapters/*.py
```
Both grep commands return zero matches.

## 11. Confirmations (vs. the design review)

| | Status |
| --- | :-: |
| **No duplication with existing collections** — `market_spread` and `bi5_certification` are NEW. Derived BI5 1m bars continue to flow into `market_data` with `source="bi5", timeframe="1m"` (P0A path, untouched). | ✅ |
| **No lifecycle changes** — `strategy_lifecycle`, `strategy_lifecycle_history`, Elite Survivor selection, BID stage gates all untouched. Phase 2 is pure additive persistence. | ✅ |
| **No BID-stage dependencies introduced** — adapters only depend on Phase 1 dataclasses and `pymongo`. `bi5_ingest_runner` is in `data_engine/` and was already permitted to touch Mongo. | ✅ |
| **No scheduler changes** — preserves the locked "no fixed 15-minute scheduler" decision. Spread upserts piggyback the existing hour-by-hour ingest loop. | ✅ |
| **No VPS / worker sizing changes** — preserves the future VPS-aware scaling lock. | ✅ |

## 12. Open TODO(P0B Phase 3) — Orchestrator & API

Phase 3 is the next planned step (awaiting approval). Items intentionally deferred from Phase 2:

1. **`engines/bi5_certification.py` orchestrator** — composes:
   - `data_engine.bi5_ingest_runner` (already wired) for raw → 1m bars + spread bars,
   - `engines.tick_validator.validate_hour` + `aggregate_window` for hour & window scoring,
   - `engines.persistence_adapters.bi5_certification_store.upsert_certification` for persistence.
2. **Admin API endpoints** — e.g. `POST /api/admin/bi5/certify` (run a certification window), `GET /api/admin/bi5/certifications` (list), `GET /api/admin/bi5/certifications/latest?symbol=` (point lookup). These expose the read paths already implemented by the adapter.
3. **Wire `VENUE_PROFILES` defaults** into `api/admin_execution_realism.py` upsert path.
4. **Slippage calibration loop** — read paper-trading fills, re-fit `k_impact`/`alpha` per symbol, persist into a new `slippage_calibration` collection. Out of scope here.

## 13. Open TODO(P1) — unchanged from Phase 1

Symbol-registry promotion items remain frozen until R0–R5 `market_universe` lands:
- `engines/tick_validator.py` — `DENSITY_TABLE`, `SESSION_BOUNDS_UTC`
- `engines/spread_analyzer.py` — `DEFAULT_TOLERANCE_BPS`, `SYMBOL_DEFAULT_BPS`
- `engines/slippage_model.py` — `K_IMPACT`, `ALPHA`, `TOLERANCE_BPS`
- `engines/execution_simulator.py` — `VENUE_PROFILES`

---

## Phase 2 — APPROVED FOR HANDOFF

All Phase 2 acceptance criteria met:

- [x] Two new collections declared with schemas + unique-key idempotency: `market_spread`, `bi5_certification`.
- [x] Indexes + TTL declared in `db_indexes.py` (verified registering cleanly via mongomock).
- [x] Adapters import only Phase-1 dataclasses + pymongo + stdlib.
- [x] `bi5_ingest_runner` wired to derive + persist spread bars, with `db=None` opt-out preserving P0A tests.
- [x] **20/20 Phase 2 tests pass**.
- [x] **Full 121-test suite passes** — zero regressions in P0A pipeline.
- [x] Firewall: zero BID-stage / API / network / forbidden-domain imports anywhere in Phase 2.
- [x] No duplication, no lifecycle changes, no scheduler changes.

**Per the handoff brief: stop here and wait for approval before
beginning P0B Phase 3 (Orchestrator & API).**
