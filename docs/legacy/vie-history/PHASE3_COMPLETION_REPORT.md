# P0B Phase 3 — Completion Report

**Scope**: BI5 Strategy Certification — orchestrator, persistence
store, admin API. Closes the BI5 gate between Elite Survivor and
Deployable as a **derived flag** (no new lifecycle stage).

**Working dir**: `/app/_review/deployment-ready/source/backend_main/backend/`

**Date**: 2026-01

---

## 1. Files Added

| Path | Purpose |
| --- | --- |
| `engines/persistence_adapters/bi5_certification_store.py` | Strategy-level Mongo store. `StrategyCertRecord` dataclass, `upsert_certification`, `get_latest_certification`, `list_certifications`, `list_certifications_for_strategy`, `is_bi5_certified` (derived flag), `aggregate_stats`. Enforces frozen composite weights at the storage boundary. |
| `engines/bi5_certification.py` | Pure orchestrator. `StrategyCertRequest`, `WindowRef`, `StrategyCertReport`, `compute_composite`, `certify_strategy`. Composes Phase-1 scorers + Phase-2 data-cert lookup → persists strategy cert row. |
| `api/bi5_certification.py` | FastAPI router under `/api/admin/bi5/...`. 8 endpoints. Admin-authenticated via `auth_utils.require_admin`. |
| `tests/test_bi5_certification_store.py` | 17 mongomock tests for the strategy-level store. |
| `tests/test_bi5_certification_orchestrator.py` | 12 mongomock tests for the orchestrator (composite math, short-circuits, happy path). |
| `tests/test_bi5_certification_api.py` | 11 FastAPI TestClient tests covering all 8 endpoints. |
| `PHASE3_COMPLETION_REPORT.md` | This report. |

## 2. Files Modified

| Path | Change |
| --- | --- |
| `engines/db_indexes.py` | Appended 8 new index specs for `bi5_certification` (unique `(strategy_id, certification_timestamp)`, plus pair/tf/style/family/verdict timeseries indexes, composite ranking, global recent list). No TTL. |
| `server.py` | One new import + one `include_router` call wiring `bi5_certification_router` under `/api`. |

No edits to Phase 1 modules, no edits to Phase 2 modules, no edits to
BID-stage modules, no edits to `strategy_lifecycle*`.

## 3. Public surface added

### `engines.persistence_adapters.bi5_certification_store`
- `StrategyCertRecord` (frozen dataclass — mirror of persisted shape)
- `upsert_certification(db, record) -> {matched, upserted, modified, ...}`
- `get_latest_certification(db, *, strategy_id) -> Optional[Dict]`
- `list_certifications_for_strategy(db, *, strategy_id, limit=50)`
- `list_certifications(db, *, pair?, timeframe?, style?, mutation_family?, verdict?, since_dt?, limit=50)`
- `is_bi5_certified(db, *, strategy_id, freshness_days=None, now_dt=None) -> {certified, freshness_days, certified_at?, latest_cert_id?, expires_at?}`
- `aggregate_stats(db, *, group_by, since_dt=None, top_n=100) -> List[{key,total,pass,warn,fail,pass_rate}]`
- Constants: `BI5_CERT_COLL`, `EVALUATOR_VERSION`, `FROZEN_WEIGHTS`, `DEFAULT_FRESHNESS_DAYS`

### `engines.bi5_certification`
- `WindowRef(window_start_utc, window_end_utc)`
- `StrategyCertRequest(strategy_id, pair, timeframe, style, data_cert_window?, fills, signals, ticks, venue_profile, stability_score, assumed_cost_bps, assumed_slippage_bps, tolerance_bps?, adv_per_minute?, mutation_family?, parent_strategy_id?)`
- `StrategyCertReport(record, persist_result, early_fail_reason)`
- `compute_composite(*, integrity, spread, slippage, execution, stability, weights=FROZEN_WEIGHTS)`
- `certify_strategy(db, req, *, now_dt=None) -> StrategyCertReport`

### `api/bi5_certification` (8 endpoints under `/api/admin/bi5`)

| Method | Path |
| --- | --- |
| `POST` | `/admin/bi5/certify-strategy` |
| `GET`  | `/admin/bi5/certifications` |
| `GET`  | `/admin/bi5/certifications/stats` |
| `GET`  | `/admin/bi5/certifications/{strategy_id}` |
| `GET`  | `/admin/bi5/certifications/{strategy_id}/latest` |
| `GET`  | `/admin/bi5/certified/{strategy_id}` |
| `GET`  | `/admin/bi5/data-certifications` |
| `GET`  | `/admin/bi5/data-certifications/latest` |

All routes admin-authenticated (`Depends(require_admin)`).

## 4. Strategy-certification document shape

```json
{
  "_id": ObjectId,

  "strategy_id":             "EM-xyz123",
  "pair":                    "EURUSD",
  "timeframe":               "M5",
  "style":                   "trend",
  "certification_timestamp": ISODate,
  "certification_verdict":   "PASS",                  // PASS | WARN | FAIL
  "certification_version":   "bi5_cert@P0B-v1",
  "integrity_score":         0.98,
  "spread_score":            0.95,
  "slippage_score":          0.91,
  "execution_score":         0.93,
  "stability_score":         0.88,
  "composite_score":         0.93,

  "data_cert_ref": {
    "symbol":           "EURUSD",
    "window_start_utc": ISODate,
    "window_end_utc":   ISODate,
    "data_cert_id":     "..."
  },
  "mutation_family":    "trend.ema_cross.v2",
  "parent_strategy_id": "EM-abc456",
  "reason":             null,
  "venue_profile":      "ECN",
  "weights_used":   {"integrity":0.30,"spread":0.20,"slippage":0.20,
                     "execution":0.15,"stability":0.15},
  "thresholds_used":{"pass":0.90,"warn":0.70}
}
```

All requested fields present. `weights_used` deviation from the
frozen split is **rejected at the store boundary** — guarantees "no
second weighting model" architecturally.

**Reason codes accepted** (when `verdict == "FAIL"`):
`DATA_CERT_MISSING`, `DATA_CERT_NOT_PASS`, `LOW_COMPOSITE`,
`MISSING_FILLS`, `MISSING_SIGNALS`, **`STALE_CERTIFICATION`** (added per approval).

## 5. Composite scoring

Weighted geometric mean using the frozen split:

```
composite = integrity^0.30 · spread^0.20 · slippage^0.20
          · execution^0.15 · stability^0.15
```

Any zero collapses the composite to 0 (mirrors the BI5 firewall ethos
already used in `engines.tick_validator.aggregate_window`). Verdict
thresholds reuse the BI5 constants:

| composite | verdict |
| --- | --- |
| ≥ `PASS_THRESHOLD` (0.90) | `PASS` |
| ≥ `WARN_THRESHOLD` (0.70) | `WARN` |
| otherwise | `FAIL` |

## 6. Indexes added (idempotent, in `db_indexes.py`)

| Name | Keys | Unique | Notes |
| --- | --- | :-: | --- |
| `ix_bi5cert_strategy_ts` | `(strategy_id ↑, certification_timestamp ↓)` | ✅ | audit-trail key |
| `ix_bi5cert_pair_ts` | `(pair ↑, certification_timestamp ↓)` | | learning: pair survival |
| `ix_bi5cert_tf_ts` | `(timeframe ↑, certification_timestamp ↓)` | | learning: timeframe survival |
| `ix_bi5cert_style_ts` | `(style ↑, certification_timestamp ↓)` | | learning: style survival |
| `ix_bi5cert_family_ts` | `(mutation_family ↑, certification_timestamp ↓)` | partial: `{mutation_family: {$type:"string"}}` | learning: family survival; partial keeps the index lean when many docs lack `mutation_family` |
| `ix_bi5cert_verdict_ts` | `(certification_verdict ↑, certification_timestamp ↓)` | | trends / alerting |
| `ix_bi5cert_composite` | `(composite_score ↓)` | | top-N rankings |
| `ix_bi5cert_ts` | `(certification_timestamp ↓)` | | global recent list |

**No TTL** (audit/research evidence). Verified registering cleanly on
mongomock; zero errors.

## 7. Derived "BI5 Certified" flag

```python
db.bi5_certification.find_one(
    {
        "strategy_id": sid,
        "certification_verdict": "PASS",
        "certification_timestamp": {"$gte": now - timedelta(days=fresh)},
    },
    sort=[("certification_timestamp", DESCENDING)],
)
```

Freshness window: `BI5_CERT_FRESHNESS_DAYS = 30` (env-overridable).
**No new lifecycle stage written.** `strategy_lifecycle*`
collections untouched. Surfaced via
`GET /api/admin/bi5/certified/{strategy_id}` for the deployable gate
and downstream consumers.

## 8. Orchestrator execution path

```
StrategyCertRequest
  │
  ├─ Step 1: resolve data-cert ──┐
  │  (Phase-2 lookup)             │
  │   ↳ MISSING   → audit FAIL row, reason="DATA_CERT_MISSING"
  │   ↳ NOT_PASS  → audit FAIL row, reason="DATA_CERT_NOT_PASS"
  │
  ├─ Step 2: input guards
  │   ↳ no fills   → audit FAIL row, reason="MISSING_FILLS"
  │   ↳ no signals → audit FAIL row, reason="MISSING_SIGNALS"
  │
  ├─ Step 3: Phase-1 pure scoring
  │   ├─ spread_score_from_fills(...)
  │   ├─ slippage_score(...)
  │   └─ simulate_fills(...)  → execution_score
  │
  ├─ Step 4: compose
  │   ├─ integrity := mirror data_cert.subscores.integrity
  │   ├─ stability := passed-in float (clamped)
  │   ├─ composite := weighted geom mean (frozen weights)
  │   └─ verdict   := threshold lookup
  │
  └─ Step 5: persist via bi5_certification_store
       ↳ audit row written in every code path (including all early-FAIL)
```

Every code path produces an audit row — research/learning systems
get a complete trail of attempts, not just successes.

## 9. Tests — Phase 3 alone

```text
collected 40 items
tests/test_bi5_certification_store.py         17 passed
tests/test_bi5_certification_orchestrator.py  12 passed
tests/test_bi5_certification_api.py           11 passed
======================== 40 passed in ~0.7s ========================
```

## 10. Full suite (Phase 1 + 2 + 2.5 + 3 + P0A regression)

```text
collected 161 items
tests/test_tick_validator.py                       23 passed
tests/test_spread_analyzer.py                      12 passed
tests/test_slippage_model.py                       23 passed
tests/test_execution_simulator.py                  20 passed
tests/test_market_spread_store.py                   7 passed
tests/test_bi5_data_certification_store.py        10 passed
tests/test_bi5_ingest_spread_wiring.py              3 passed
tests/test_bi5_certification_store.py              17 passed
tests/test_bi5_certification_orchestrator.py       12 passed
tests/test_bi5_certification_api.py                11 passed
tests/test_bi5_ingest_runner_e2e.py                12 passed   (P0A regression)
tests/test_tick_aggregator.py                       6 passed   (P0A regression)
tests/test_tick_archive.py                          5 passed   (P0A regression)
============================ 161 passed in 1.64s ============================
```

**Zero regressions.** Ruff: clean.

## 11. Firewall verification

### 11.1 BID ↔ BI5 firewall

```text
$ grep -nE "^(import|from) +(engines\.(discovery|mutation|validation|
    pass_probability|challenge|matching_engine|portfolio|phase30|
    gem_factory|market_universe)|api|fastapi|sqlalchemy|requests|
    httpx|urllib|aiohttp)" \
    engines/bi5_certification.py \
    engines/persistence_adapters/bi5_certification_store.py
   → (no matches)
```

Phase-3 BI5 modules import only:
- `pymongo` (store only)
- stdlib (`math`, `logging`, `datetime`, `typing`, `dataclasses`, `os`)
- Phase-1 evaluators (`tick_validator`, `spread_analyzer`,
  `slippage_model`, `execution_simulator`) — orchestrator only
- Phase-2/3 adapters — orchestrator only

### 11.2 API seam discipline

```text
$ grep -nE "^(import|from) +engines\.(tick_validator|spread_analyzer|
    slippage_model|execution_simulator)" api/bi5_certification.py
   → (no matches)
```

The API seam does **not** import Phase-1 engines directly. All scoring
flows through the orchestrator — this prevents any code path that
mixes the HTTP layer with raw evaluator calls.

### 11.3 The single BID-side input

`stability_score` enters the orchestrator as a **float** on the
request dataclass. Nothing else from validation / pass-probability /
challenge-matching / portfolio-selection crosses the boundary.
Verified by inspection + by the orchestrator's import set.

### 11.4 Lifecycle isolation

No writes anywhere in Phase 3 touch `strategy_lifecycle` or
`strategy_lifecycle_history`. BI5 Certified remains a **derived
read** via `is_bi5_certified`.

## 12. Open TODO(P0B Phase 4)

Phase 4 is the final BI5 phase and is intentionally deferred:

1. **E2E suite** against the live FastAPI service with real Mongo:
   admin auth + ingest → data-cert → certify-strategy → derived flag
   → deployable check, all over HTTP.
2. **Firewall audit pass**: scripted scan of *every* `engines/` and
   `api/` module (not just Phase 3 additions) for any reverse import
   from BI5 into BID stages.
3. **Performance smoke**: 1 000-cert burst into `bi5_certification`
   with index hit checks (`explain()`-based) for each indexed query.

## 13. Open TODO(P1) — unchanged

Symbol-registry promotion items remain frozen until R0–R5
`market_universe` lands.

---

## Phase 3 — APPROVED FOR HANDOFF

- [x] `engines/bi5_certification.py` orchestrator — pure, no BID-stage imports.
- [x] `engines/persistence_adapters/bi5_certification_store.py` strategy-level audit store with frozen-weights enforcement.
- [x] `api/bi5_certification.py` — 8 admin endpoints, reuse of existing `require_admin` dependency.
- [x] `STALE_CERTIFICATION` reason added per approval.
- [x] All requested fields present in persisted shape, all flat for easy aggregation.
- [x] Composite weights frozen at 0.30/0.20/0.20/0.15/0.15 — second weighting model rejected at storage boundary.
- [x] Audit-trail key `(strategy_id, certification_timestamp)` enforced by unique index.
- [x] BI5 Certified remains a derived flag via `is_bi5_certified`; **no new lifecycle stage**.
- [x] Tests: 40/40 Phase 3, 161/161 full suite, zero regressions.
- [x] Firewall: BID ↔ BI5 clean; API seam free of direct Phase-1 imports; only `stability_score` (float) crosses the boundary.

**Per the handoff brief: stop here and wait for approval before
beginning P0B Phase 4 (E2E & Firewall Audit).**
