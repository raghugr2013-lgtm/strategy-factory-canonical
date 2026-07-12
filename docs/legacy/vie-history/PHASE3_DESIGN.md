# P0B Phase 3 — Design Memo (Orchestrator & API)

**Status**: design only. No code change in this document.

**Working directory**: `/app/_review/deployment-ready/source/backend_main/backend/`

**Hard constraints (from approved handoff)**
- BI5 Certification is a **derived flag**, not a new lifecycle stage.
- Existing lifecycle is immutable: Discovery → Mutation → Validation → Pass Probability → Challenge Matching → Portfolio Selection → Elite Survivor → **BI5 Certified (derived)** → Deployable.
- `engines/*` BI5 modules MUST NOT import from BID stages.
- `stability_score` arrives **as a float** from Validation / Pass Probability; the BI5 layer only records it.
- `style` is a free-form string; no enum validation.
- Composite weights (frozen): Integrity 0.30, Spread 0.20, Slippage 0.20, Execution 0.15, Stability 0.15. No second weighting model.
- Audit-trail key: `(strategy_id, certification_timestamp)`.

---

## 1. Orchestrator flow

### 1.1 Component layout (where each piece lives)

```
                            ┌────────────────────────────────────────────┐
                            │  api/bi5_certification.py            (NEW) │
                            │  HTTP seam. Allowed to read from anywhere  │
                            │  (strategy_library, validation results,    │
                            │  pass_probability, fills, signals).        │
                            │  Builds a StrategyCertRequest and calls    │
                            │  the orchestrator. NO scoring logic here.  │
                            └────────────────────┬───────────────────────┘
                                                 │  StrategyCertRequest
                                                 ▼
                            ┌────────────────────────────────────────────┐
                            │  engines/bi5_certification.py        (NEW) │
                            │  Pure orchestrator. Composes:              │
                            │   - data-cert lookup (Phase 2 adapter)     │
                            │   - spread_score (Phase 1)                 │
                            │   - slippage_score (Phase 1)               │
                            │   - execution_score (Phase 1)              │
                            │   - stability_score (PASSED IN)            │
                            │   - integrity_score (mirrored from data    │
                            │     cert)                                  │
                            │   - composite_score (weighted geom mean)   │
                            │   - verdict thresholding                   │
                            │  Then calls the strategy-cert store.       │
                            │  Imports: Phase 1 engines, Phase 2 adapter,│
                            │  Phase 3 strategy-cert adapter, stdlib.    │
                            │  NO imports from BID stages.               │
                            └────────────────────┬───────────────────────┘
                                                 │
                                                 ▼
              ┌─────────────────────────────────────────────────────────┐
              │ engines/persistence_adapters/                           │
              │   bi5_certification_store.py                       (NEW)│
              │ Strategy-level audit store. (symbol-side data cert     │
              │ store remains separate: bi5_data_certification_store).  │
              └────────────────────┬────────────────────────────────────┘
                                   ▼
                                [ Mongo: bi5_certification ]
```

### 1.2 Step-by-step execution

Given a `StrategyCertRequest` (built by the API seam):

```python
@dataclass(frozen=True)
class StrategyCertRequest:
    strategy_id:      str
    pair:             str           # symbol the strategy trades
    timeframe:        str           # "M1" | "M5" | "H1" | …
    style:            str           # free-form
    # Data-cert window the strategy will be judged against:
    data_cert_window: WindowRef      # (window_start_utc, window_end_utc)
    # Inputs to Phase-1 evaluators (already gathered by the seam):
    fills:            Sequence[FillRecord]      # for spread + slippage scoring
    signals:          Sequence[SignalRecord]    # for execution simulation
    ticks:            Sequence[Tick]            # certified BI5 ticks for the window
    venue_profile:    str           # ECN | retail | prop_firm
    # Inputs passed in (NOT computed here):
    stability_score:  float         # from validation / pass_probability
    # Optional learning-system context:
    mutation_family:    Optional[str] = None
    parent_strategy_id: Optional[str] = None
    adv_per_minute:     Optional[float] = None  # rolled from BI5 by the seam
```

Orchestrator steps:

1. **Look up data-cert** for `(pair, data_cert_window)` via
   `bi5_data_certification_store.get_data_certification`.
   - If missing → return `FAIL` with reason `DATA_CERT_MISSING`. No write.
   - If `verdict != "PASS"` → return `FAIL` with reason `DATA_CERT_NOT_PASS`. No write.
   - Mirror its `subscores.integrity` as `integrity_score`.

2. **spread_score** ← `engines.spread_analyzer.spread_score_from_fills(
       fills, symbol=pair, assumed_cost_bps=…)`.

3. **slippage_score** ← `engines.slippage_model.slippage_score(
       fills=fills, assumed_slippage_bps=…)`.

4. **execution_score** ← `engines.execution_simulator.simulate_fills(
       signals, ticks=ticks,
       profile=get_profile(venue_profile),
       adv_per_minute=adv_per_minute).execution_score`.

5. **stability_score** ← `req.stability_score` (passed in; clamped to `[0,1]`).

6. **composite_score** ← weighted geometric mean:
   ```
   composite = ∏ score_i ^ weight_i      (weights are the frozen split)
             = integrity^0.30 · spread^0.20 · slippage^0.20
             · execution^0.15 · stability^0.15
   ```
   Any 0 collapses the composite to 0 — consistent with the BI5 firewall ethos.

7. **verdict** ← reuse the BI5 thresholds already in
   `engines.tick_validator` (frozen for consistency):

   | composite | verdict |
   | --- | --- |
   | ≥ `PASS_THRESHOLD` (0.90) | `PASS` |
   | ≥ `WARN_THRESHOLD` (0.70) | `WARN` |
   | otherwise                  | `FAIL` |

8. **Persist** via
   `bi5_certification_store.upsert_certification(db, ...)`. Audit-trail
   semantics: `(strategy_id, certification_timestamp)` is unique →
   every call inserts a new audit row (no in-place mutation).

9. **Return** a `StrategyCertReport` dataclass = exact mirror of the
   persisted document (so the API can return it directly).

### 1.3 Derived "BI5 Certified" flag (no lifecycle stage)

A strategy is BI5-Certified iff a `find_one`:
```python
db.bi5_certification.find_one(
    {"strategy_id": sid, "certification_verdict": "PASS"},
    sort=[("certification_timestamp", DESCENDING)],
)
```
returns a non-`None` doc whose `certification_timestamp` is within an
operator-tunable freshness window (default `BI5_CERT_FRESHNESS_DAYS=30`,
env-overridable). The deployable gate runs exactly this query. **No
edits to `strategy_lifecycle*`. No new stage.**

A one-call read helper will be exposed by the strategy-cert store:
`is_bi5_certified(db, *, strategy_id, freshness_days=30) -> bool`.

---

## 2. Strategy-certification schema

Collection: **`bi5_certification`** (strategy-level — distinct from
`bi5_data_certification` which is feed-level).

```json
{
  "_id": ObjectId,

  // ── identity (all 13 required fields, flat for easy aggregation) ──
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

  // ── provenance for learning / debugging ──────────────────────────
  "data_cert_ref": {
    "symbol":           "EURUSD",
    "window_start_utc": ISODate,
    "window_end_utc":   ISODate,
    "data_cert_id":     ObjectId            // _id of the bi5_data_certification doc
  },
  "mutation_family":    "trend.ema_cross.v2",   // nullable
  "parent_strategy_id": "EM-abc456",            // nullable

  // ── reproducibility ──────────────────────────────────────────────
  "weights_used":   {"integrity":0.30,"spread":0.20,"slippage":0.20,
                     "execution":0.15,"stability":0.15},
  "thresholds_used":{"pass":0.90,"warn":0.70},
  "venue_profile":  "ECN",
  "reason":         null                           // populated on FAIL
}
```

### 2.1 Validation rules (in the strategy-cert store)

- All five scores must be in `[0, 1]` (clamped on the way in).
- `certification_verdict ∈ {PASS, WARN, FAIL}`.
- `strategy_id` and `pair` non-empty strings; `timeframe` non-empty.
- `weights_used` MUST match the frozen split exactly (mismatch → `ValueError`). This
  enforces "no second weighting model" at the store level.
- `style` accepted as free-form string (no enum check, per approval).

### 2.2 Indexes (declared idempotently in `db_indexes.py`)

| Name | Keys | Unique | Purpose |
| --- | --- | :-: | --- |
| `ix_bi5cert_strategy_ts` | `(strategy_id ↑, certification_timestamp ↓)` | ✅ | audit-trail key; "latest cert per strategy" lookups |
| `ix_bi5cert_pair_ts` | `(pair ↑, certification_timestamp ↓)` | | learning: pair survival counts |
| `ix_bi5cert_tf_ts` | `(timeframe ↑, certification_timestamp ↓)` | | learning: timeframe survival |
| `ix_bi5cert_style_ts` | `(style ↑, certification_timestamp ↓)` | | learning: style survival |
| `ix_bi5cert_family_ts` | `(mutation_family ↑, certification_timestamp ↓)` | partial: `{mutation_family: {$type:"string"}}` | learning: mutation-family survival |
| `ix_bi5cert_verdict_ts` | `(certification_verdict ↑, certification_timestamp ↓)` | | trends over time / FAIL alerting |
| `ix_bi5cert_composite` | `(composite_score ↓)` | | top-N rankings |
| `ix_bi5cert_ts` | `(certification_timestamp ↓)` | | global recent list |

**No TTL** (audit/research evidence).

Footprint: ~800 B/doc × ~5–10 k docs/year ≈ **< 10 MB/year**. Trivial.

---

## 3. API endpoints

All under the existing admin auth umbrella (same pattern as
`api/admin_execution_realism.py`). All paths start with `/api/admin/bi5`.

### 3.1 Strategy certification

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/admin/bi5/certify-strategy` | Run a fresh cert for one strategy. Body: `{strategy_id, data_cert_window?}` — defaults to the latest PASS data-cert for the strategy's pair. Returns the persisted cert doc. |
| `GET` | `/api/admin/bi5/certifications` | List recent certs. Query: `pair?`, `style?`, `timeframe?`, `verdict?`, `mutation_family?`, `since?` (ISO), `limit?` (default 50). |
| `GET` | `/api/admin/bi5/certifications/{strategy_id}` | Audit-trail for one strategy, newest first. Query: `limit?`. |
| `GET` | `/api/admin/bi5/certifications/{strategy_id}/latest` | Latest cert only. |
| `GET` | `/api/admin/bi5/certified/{strategy_id}` | **The derived flag.** Returns `{certified: bool, latest_cert_id, certified_at, expires_at}`. Used by the deployable gate. |
| `GET` | `/api/admin/bi5/certifications/stats` | Aggregations for learning systems. Query: `since?`, `group_by ∈ {pair, style, timeframe, mutation_family, verdict, day}`. Returns `[{key, total, pass, warn, fail, pass_rate}]`. |

### 3.2 Data certification (existing Phase-2 adapter exposed read-only)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/admin/bi5/data-certifications` | List recent data certs. Query: `symbol?`, `verdict?`, `since?`, `limit?`. |
| `GET` | `/api/admin/bi5/data-certifications/latest` | Latest per symbol. Query: `symbol`. |

No write endpoint for data certs in Phase 3 — they continue to be produced
by `bi5_ingest_runner` (Phase 2). Wiring a "manual recertify-window" endpoint
is deferred to a later phase if needed.

### 3.3 Response shape

All endpoints return the canonical strategy-cert doc shape from §2 (with
ObjectId stringified). Errors use the project-standard
`{"error": "...", "code": "..."}` envelope.

---

## 4. Firewall verification (plan)

Phase 3 introduces three new files. Their permitted-imports lattice:

```
   api/bi5_certification.py    (NEW, server layer)
      │
      │ permitted: strategy_library readers, validation/pass_probability
      │            readers, fills/signals readers, FastAPI, …
      ▼
   engines/bi5_certification.py   (NEW, orchestrator)
      │
      │ permitted: pymongo (via db), datetime/typing/stdlib,
      │            engines.tick_validator, engines.spread_analyzer,
      │            engines.slippage_model, engines.execution_simulator,
      │            engines.persistence_adapters.bi5_data_certification_store,
      │            engines.persistence_adapters.bi5_certification_store
      │ FORBIDDEN: discovery, mutation, validation, pass_probability,
      │            challenge_matching, matching_engine, portfolio_*,
      │            phase30_*, gem_factory*, market_universe, api/*,
      │            http clients, filesystem
      ▼
   engines/persistence_adapters/bi5_certification_store.py   (NEW)
      │
      │ permitted: pymongo, datetime/typing/stdlib
      │ FORBIDDEN: same forbidden list as above + Phase-1 engines
      │            (cert store should not need them; weights live as
      │            a const in this module so the orchestrator imports
      │            from here, not the other way around).
```

### 4.1 Mechanical check (will be run + reported in the Phase-3
completion report)

```bash
grep -nE "^(import|from) +(engines\.(discovery|mutation|validation|
        pass_probability|challenge|matching_engine|portfolio|phase30|
        gem_factory|market_universe)|api|fastapi|sqlalchemy|requests|
        httpx|urllib|aiohttp)" \
  engines/bi5_certification.py \
  engines/persistence_adapters/bi5_certification_store.py
```
Required result: zero matches.

For the API seam (`api/bi5_certification.py`) FastAPI / strategy reads
are permitted; we will *positively* assert: no imports of Phase-1
engines (forcing all scoring to go through the orchestrator).

### 4.2 Why this is firewall-safe

- `stability_score` enters as a **float** at the API seam; the
  orchestrator never imports validation / pass_probability.
- `strategy_id, pair, timeframe, style, mutation_family,
  parent_strategy_id` enter as plain strings via
  `StrategyCertRequest`; the orchestrator never imports
  `strategy_library`.
- All scoring uses Phase-1 pure functions; no Mongo I/O inside scoring.
- Only the cert store and the data-cert store touch Mongo.

---

## 5. Tests (planned for Phase 3)

| File | What it proves |
| --- | --- |
| `tests/test_bi5_certification_store.py` (NEW) | Idempotency on `(strategy_id, certification_timestamp)`; score range validation; weights validator (rejects deviation from frozen split); `pair/style/timeframe/family/verdict` filter queries; `is_bi5_certified` freshness logic. |
| `tests/test_bi5_certification_orchestrator.py` (NEW) | Short-circuit FAIL when data cert is missing / not PASS. Weighted-geom-mean math is correct. Verdict thresholds correct at PASS/WARN/FAIL boundaries. stability=0 collapses composite. All-perfect inputs → PASS. |
| `tests/test_bi5_certification_api.py` (NEW, FastAPI TestClient + mongomock) | One happy-path certify-strategy; list with each filter; stats endpoint returns the expected aggregations; `bi5/certified/{strategy_id}` reflects the derived-flag freshness window. |
| Re-run existing 121-test suite to confirm no regression. |

---

## 6. Out-of-scope (deferred to Phase 4 or later)

- E2E run against the live FastAPI service with real Mongo (Phase 4).
- Wiring `VENUE_PROFILES` admin upsert into the orchestrator's profile
  resolution (today the seam reads the env / a constant).
- Slippage calibration loop (refit `k_impact`, `alpha`).
- R0–R5 `market_universe` promotion (still locked).

---

## 7. Open confirmations before implementation

1. **`engines/bi5_certification.py`** as the file path for the
   orchestrator (alongside Phase 1/2 modules). OK?
2. **`is_bi5_certified` freshness default** = 30 days, env
   `BI5_CERT_FRESHNESS_DAYS`. OK or different default?
3. **`reason` field on FAIL** — short enum-ish string (e.g.
   `DATA_CERT_MISSING`, `DATA_CERT_NOT_PASS`, `LOW_COMPOSITE`,
   `MISSING_FILLS`, `MISSING_SIGNALS`). OK?
4. **API auth** — adopt the same admin auth dependency that
   `api/admin_execution_realism.py` already uses, i.e. no new auth
   stack. OK?
5. **Stats endpoint cardinality limit** — cap `group_by=mutation_family`
   results at top-N (default 100) to avoid unbounded payloads on a
   year-of-mutations slice. OK?

Once these five are confirmed I will implement Phase 3 end-to-end
(orchestrator + strategy-cert store + API endpoints + tests), then
stop again for the Phase-4 (E2E & firewall audit) approval.
