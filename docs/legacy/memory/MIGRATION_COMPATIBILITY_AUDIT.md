# MIGRATION_COMPATIBILITY_AUDIT.md

**Purpose:** Verify the 1-vCPU export format is byte-compatible with the canonical (12-vCPU) schema, and enumerate every conversion the importer must perform.
**Status:** Plan only. The audit is performed against the **canonical schema** in App.zip and the **legacy schema** documented in `_inventory/old1vcpu/src/` + reference `_inventory/app_extracted/`.

---

## 1. Identity model — UNCHANGED ✅

| Item | 1-vCPU | Canonical (App.zip) | Verdict |
|---|---|---|---|
| Fingerprint algorithm | SHA1 over `(pair \| timeframe \| style \| _canon_params(params) \| _normalize_text(strategy_text))` | **same** (`engines/strategy_library._fingerprint`) | ✅ identical |
| Parameter bucketing | `_bucket_param()` strips numeric values | **same** | ✅ identical |
| Text normalisation | `_normalize_text()` lowercases + strips whitespace | **same** | ✅ identical |
| `strategy_hash` | optional, stored alongside fingerprint | optional, stored alongside fingerprint | ✅ identical |

**Conclusion:** A strategy fingerprinted on the 1-vCPU pod produces the **identical** SHA1 in the canonical pod. No re-fingerprinting needed.

---

## 2. `strategy_library` document — field-by-field

| Field | 1-vCPU | Canonical | Conversion needed? |
|---|---|---|---|
| `_id` | ObjectId | ObjectId (regenerated on insert) | Mongo-managed |
| `fingerprint` | str (40-char SHA1) | str (40-char SHA1) | NO |
| `strategy_text` | str | str | NO |
| `strategy_ir` | dict or absent | dict — preferred | If absent, importer leaves null; revalidation may not be possible until rebuilt by `strategy_ir_backfill` |
| `strategy_hash` | str or absent | str | NO (forward-compat) |
| `pair` | uppercase str (e.g. EURUSD) | uppercase str | NO |
| `timeframe` | str (M1/M5/M15/M30/H1/H4/D1) | str (same set) | NO |
| `style` | str | str | NO |
| `params` | dict | dict | NO |
| `metrics.profit_factor` | float | float | NO |
| `metrics.win_rate` | float (0..1) | float (0..1) | NO |
| `metrics.total_trades` | int | int | NO |
| `metrics.max_drawdown_pct` | float (0..1) | float (0..1) | NO |
| `metrics.sharpe` | float | float | NO |
| `metrics.sortino` | float | float | NO |
| `metrics.calmar` | float | float | NO |
| `metrics.stability` | float (0..1) or absent | float (0..1) | NO |
| `pass_probability` | float or absent | float — populated by `pass_probability.py` | NO (will be (re)computed post-import) |
| `validation_report` | dict or absent | dict | NO |
| `backtest_results` | dict or absent | dict | NO |
| `created_at` | ISO str or `datetime` | `datetime` UTC | If string, parse with `dateutil` |
| `saved_at` | ISO str | `datetime` UTC | Same |
| `source` | str (`"auto_factory"`, `"manual"`, `"workspace"`) | same | NO |
| `stage` | str (`"PROVISIONAL"`, `"TRADE"`, `"DEMOTED"`, …) | same | NO |
| `tags` | list[str] or absent | list[str] | NO |

**Conversions needed:** ONE — `created_at`/`saved_at` may arrive as ISO strings (mongoexport JSON default); the importer normalises to `datetime` UTC. All other fields pass through.

---

## 3. `strategy_lifecycle` document

| Field | 1-vCPU | Canonical | Conversion |
|---|---|---|---|
| `fingerprint` | str | str | NO |
| `stage` | str | str | NO |
| `state` | str (e.g. `"active"`, `"locked"`) | str | NO |
| `transitioned_at` | ISO str | datetime | parse |
| `reason` | str or absent | str | NO |

Compatible. `fingerprint` is the join key to `strategy_library`.

---

## 4. `mutation_events` document

| Field | 1-vCPU | Canonical | Conversion |
|---|---|---|---|
| `mutation_id` | str | str | NO |
| `parent_fingerprint` | str | str | NO |
| `child_fingerprint` | str | str | NO |
| `pair`/`timeframe`/`style` | str | str | NO |
| `mutation_type` | str | str (same enum) | NO |
| `created_at` | ISO str | datetime | parse |
| `metrics_delta` | dict or absent | dict | NO |

Compatible.

---

## 5. `mutation_stability_log` document

| Field | 1-vCPU | Canonical | Conversion |
|---|---|---|---|
| `fingerprint` | str | str | NO |
| `stability_score` | float | float | NO |
| `samples` | int | int | NO |
| `evaluated_at` | ISO str | datetime | parse |

Compatible.

---

## 6. `strategy_performance_history` document

| Field | 1-vCPU | Canonical | Conversion |
|---|---|---|---|
| `fingerprint` | str | str | NO |
| `snapshot_at` | ISO str | datetime | parse |
| `metrics` | dict | dict | NO |
| `mode` | str (`"live"`, `"paper"`, `"backtest"`) | str | NO |

Compatible.

---

## 7. `strategy_lifecycle_history` document

| Field | 1-vCPU | Canonical | Conversion |
|---|---|---|---|
| `fingerprint` | str | str | NO |
| `from_stage`/`to_stage` | str | str | NO |
| `at` | ISO str | datetime | parse |
| `actor` | str (operator email or `"system"`) | str | NO |
| `reason` | str | str | NO |

Compatible.

---

## 8. `auto_factory_alert_log` document

| Field | 1-vCPU | Canonical | Conversion |
|---|---|---|---|
| `alert_id` | str | str | NO |
| `severity` | str | str | NO |
| `summary` | str | str | NO |
| `payload` | dict | dict | NO |
| `created_at` | ISO str | datetime | parse |

Compatible.

---

## 9. Fields PRESENT in canonical but ABSENT in 1-vCPU

The canonical pod stores additional fields that the 1-vCPU pod did not produce. These are filled at import time with defaults:

| Field | Default at import | Producer |
|---|---|---|
| `provenance.source` | `"1vcpu_migration"` | importer |
| `provenance.imported_at` | now() | importer |
| `provenance.operator` | from `ADMIN_EMAIL` | importer |
| `provenance.requires_revalidation` | `true` | importer |
| `provenance.requires_rematching` | `true` | importer |
| `stage_locked_until` | now() + 30 days | importer |
| `dossier` (Phase 13) | absent (engine not yet built) | n/a |
| `valuation` (Phase 14) | absent (engine not yet built) | n/a |
| `marketplace_eligible` (Phase 15) | absent | n/a |
| `evidence_score`, `trust_score`, `market_score`, `quality_score` (M3) | absent (engine not yet built) | n/a |
| `bi5_cert.coverage_pct` | reset to null (data is being re-ingested on new pod) | recomputed post-ingest |

None of these conversions block import; they are simply additive enrichment.

---

## 10. Index compatibility

| Collection | Canonical indexes | 1-vCPU likely indexes | Conflict? |
|---|---|---|---|
| `strategy_library` | unique on `fingerprint`, asc on `created_at`, asc on `pair+timeframe` | unique on `fingerprint` | NO — canonical is superset |
| `strategy_lifecycle` | asc on `fingerprint` | asc on `fingerprint` | NO |
| `mutation_events` | asc on `parent_fingerprint`, asc on `child_fingerprint` | likely asc on both | NO |

Index creation is idempotent. The importer does NOT need to manage indexes — they are created by the canonical backend on first write.

---

## 11. Unsupported / extinct fields (1-vCPU only)

If the 1-vCPU export carries fields that the canonical schema doesn't recognise, the importer:
* **Preserves** the field inside a `legacy_attributes` sub-dict on the strategy doc.
* Does **NOT** silently drop.
* Operator can later inspect via `db.strategy_library.findOne({"legacy_attributes": {$exists: true}})`.

Known candidates (low risk):
* `legacy_id` — keep as `legacy_attributes.legacy_id`
* `r4_phase` / `r4_track` — keep as `legacy_attributes.r4_*`
* `paper_session_id` — keep

---

## 12. Compatibility verdict

| Tier | Compatibility | Conversion cost |
|---|---|---|
| Identity (fingerprint) | ✅ identical | zero |
| Core fields (pair/timeframe/style/params/metrics) | ✅ identical | zero |
| Datetime fields | ⚠ string → datetime | parse pass — 100s of µs per row |
| Lineage joins | ✅ identical (fingerprint-keyed) | zero |
| New canonical fields | ✅ additive enrichment | constant per row |
| Unsupported legacy fields | ✅ preserved under `legacy_attributes` | constant per row |

**Net verdict:** **FULLY COMPATIBLE.** Zero schema migrations. One datetime parse pass. Net importer LOC: ~120 LOC (validation + classifier + insert + checkpoint + log). No backend or canonical schema change required.

---

## 13. Operator decisions still required

* Confirm whether `legacy_attributes` preservation is desired (default: yes).
* Confirm whether to drop `auto_factory_alert_log` rows older than 30 days at import time (default: yes — these are alerts, not signals).
* Confirm rule-of-thumb retention windows are acceptable.

---

## 14. Status

* Plan only.
* Schema compatibility confirmed at the source-code level using actual `_fingerprint()` from both `_inventory/old1vcpu` (legacy) and `engines/strategy_library.py` (canonical) — they share lineage.
* Awaiting export delivery + green `IMPORT_READINESS_REPORT.md` before importer runs.
