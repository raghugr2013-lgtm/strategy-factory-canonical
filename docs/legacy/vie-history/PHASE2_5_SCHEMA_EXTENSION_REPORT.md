# P0B Phase 2.5 — Schema Extension Delta Report

**Scope**: Surgical rename of the Phase-2 data-feed certification
collection to disambiguate it from the strategy-level certification
that the Phase-3 orchestrator will own.

**Date**: 2026-01

**Reason**: Two distinct artefacts share the *name* "BI5 certification"
but represent different concerns:

| Artefact | Owns | Key | Owner |
| --- | --- | --- | --- |
| **BI5 data-feed certification** | "Is the BI5 feed for `symbol` over this window of certifiable quality?" | `(symbol, window_start_utc, window_end_utc)` | Phase 2 persistence (this report) |
| **BI5 strategy certification** | "Does Elite-Survivor strategy `strategy_id` pass the BI5 gate?" | `(strategy_id, certification_timestamp)` | **Phase 3 orchestrator** (NOT created in this delta) |

Persisting strategy-level fields in the storage layer *before* the
orchestrator exists would leak `strategy_id`, `pair`, `timeframe`,
`style`, `mutation_family`, `parent_strategy_id`, and `stability_score`
into a module that has no business knowing them. We avoid that
leakage here.

---

## 1. Files Renamed

| Old → New |
| --- |
| `engines/persistence_adapters/bi5_certification_store.py` → `bi5_data_certification_store.py` |
| `tests/test_bi5_certification_store.py` → `tests/test_bi5_data_certification_store.py` |

## 2. Public-Surface Renames (in the renamed module)

| Old symbol | New symbol |
| --- | --- |
| `BI5_CERT_COLL = "bi5_certification"` | `BI5_DATA_CERT_COLL = "bi5_data_certification"` |
| `upsert_certification` | `upsert_data_certification` |
| `get_certification` | `get_data_certification` |
| `get_latest_certification` | `get_latest_data_certification` |
| `find_by_verdict` | `find_data_certs_by_verdict` |

Function signatures, semantics, idempotency contract, and the
`_VERDICTS` validator are **unchanged**.

## 3. Files Modified

| Path | Change |
| --- | --- |
| `engines/persistence_adapters/__init__.py` | Rewritten to re-export the renamed symbols. Docstring updated to spell out the data-cert vs. strategy-cert separation and to declare why the strategy collection is intentionally absent at this layer. |
| `engines/db_indexes.py` | Renamed 4 entries: `bi5_certification` → `bi5_data_certification`. Index names: `ix_bi5cert_*` → `ix_bi5datacert_*`. No new indexes; no removed indexes; no change to keys / options / TTL. |
| `tests/test_bi5_data_certification_store.py` | Import path + symbol names updated to match the rename. Test logic identical. |

## 4. Files Unchanged

| | Reason |
| --- | --- |
| `engines/persistence_adapters/market_spread_store.py` | Unrelated to the cert rename. |
| `engines/tick_validator.py`, `spread_analyzer.py`, `slippage_model.py`, `execution_simulator.py` | Phase-1 surface frozen. |
| `data_engine/bi5_ingest_runner.py` | Only consumes Phase-2 spread-store today; not the cert store. |
| `engines/db.py`, `server.py`, `api/*` | Not yet wired to the cert store; nothing to update. |
| All BID-stage modules | Untouched (firewall preserved). |
| `strategy_lifecycle*` | Untouched — BI5 Certified remains a derived flag. |

## 5. Tests

```text
collected 121 items
tests/test_tick_validator.py                     23 passed
tests/test_spread_analyzer.py                    12 passed
tests/test_slippage_model.py                     23 passed
tests/test_execution_simulator.py                20 passed
tests/test_market_spread_store.py                 7 passed
tests/test_bi5_data_certification_store.py      10 passed   (renamed)
tests/test_bi5_ingest_spread_wiring.py            3 passed
tests/test_bi5_ingest_runner_e2e.py              12 passed
tests/test_tick_aggregator.py                     6 passed
tests/test_tick_archive.py                        5 passed
============================ 121 passed in 2.00s ============================
```

Zero regressions. Ruff: clean on all touched files.

## 6. Index Registration Verified

Ran `engines.db_indexes.ensure_indexes()` against a fresh mongomock client:

```text
old bi5_certification entries:        0   ✓
new bi5_data_certification entries:   4   ✓
created indexes:
    bi5_data_certification.ix_bi5datacert_sym_window   (unique)
    bi5_data_certification.ix_bi5datacert_sym_ts
    bi5_data_certification.ix_bi5datacert_verdict
    bi5_data_certification.ix_bi5datacert_ts
errors: []
```

## 7. Firewall Confirmation (unchanged from Phase 2)

```text
$ grep -nE "engines\.(discovery|mutation|validation|pass_probability|
   challenge|matching_engine|portfolio|phase30|gem_factory|market_universe)
   |api|fastapi|sqlalchemy|requests|httpx|urllib|aiohttp" \
     engines/persistence_adapters/*.py
(no matches)
```

Adapters still depend only on Phase-1 dataclasses + `pymongo` + stdlib.

## 8. Migration Note (for live Mongo, when deployed)

Phase 2 was approved with zero production data. If at any point a
`bi5_certification` collection materialised in a long-lived
environment between the two approvals, the one-shot rename is:

```javascript
db.bi5_certification.renameCollection("bi5_data_certification");
// indexes rebuilt by the next ensure_indexes() boot call;
// old ix_bi5cert_* names will be dropped/recreated as ix_bi5datacert_*
```

No data transformation is needed — the documents are identical.

---

## Phase 2.5 — APPROVED FOR HANDOFF

- [x] Rename `bi5_certification` → `bi5_data_certification` (collection, module, tests, indexes, symbols).
- [x] No strategy-level cert collection introduced — that is Phase 3's job.
- [x] All 121 tests pass; ruff clean; firewall intact.
- [x] No lifecycle stage added; no BID-stage imports added; no scheduler / VPS / `market_universe` changes.

**Next step**: deliver the **Phase 3 design memo** before any
implementation. See `PHASE3_DESIGN.md` (separate document).
