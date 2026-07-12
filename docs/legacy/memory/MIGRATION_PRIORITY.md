# MIGRATION_PRIORITY.md

**Purpose:** Order of import operations and the rationale for each tier.
**Status:** Plan only. No import has occurred.
**Companion:** `MIGRATION_EXPORT_PLAN.md` (what), `POST_IMPORT_PIPELINE.md` (re-process).

The operator has stated emphatically: **the imported strategies are reference intelligence — NOT deployable.** They serve as mutation lineage, validation evidence, survivor seeds, and portfolio / master-bot seed candidates.

This document encodes that policy as concrete import ordering.

---

## 1. Three-tier classification

Every row in the export is classified into one of three tiers at import time. Tier governs both order and behaviour.

| Tier | Collection scope | Action |
|---|---|---|
| **T1 — Survivor seed** | `strategy_library` rows passing T1 filter (see §2) | Insert into `strategy_library` with `stage="IMPORTED_SEED"`, `provenance.source="1vcpu_migration"`, `stage_locked_until=ISO_date(+30 days)`. Cannot be auto-deployed by Auto-Selection until re-scored. |
| **T2 — Reference intelligence** | All other `strategy_library` rows + `mutation_events` + `mutation_stability_log` | Insert read-only into `strategy_library_archive` (new collection) — preserves DNA + lineage, does not pollute the live survivor universe. |
| **T3 — Audit context** | `strategy_lifecycle_history`, `strategy_performance_history`, `auto_factory_alert_log` | Insert into matching collections with `imported=true` flag. Read-only references for the dossier engine when it lands. |

---

## 2. T1 filter — what qualifies as a survivor seed

A `strategy_library` row from the 1-vCPU export is classified T1 ONLY when ALL of the following hold:

| # | Filter | Source field |
|---|---|---|
| 1 | `metrics.total_trades >= 30` | row.metrics.total_trades |
| 2 | `metrics.profit_factor >= 1.30` | row.metrics.profit_factor |
| 3 | `metrics.win_rate >= 0.40` | row.metrics.win_rate |
| 4 | `metrics.max_drawdown_pct <= 0.20` | row.metrics.max_drawdown_pct |
| 5 | `validation_report.walk_forward.passed == True` | row.validation_report (if present) |
| 6 | `stage` NOT IN `{"DEMOTED", "RETIRED", "BANNED"}` | row.stage |
| 7 | `created_at` within last 365 days | row.created_at |
| 8 | `fingerprint` not already present in canonical `strategy_library` seed | computed |

Rows failing any of #1–#4 go to T2 (still preserved). Rows failing #5–#6 by design (e.g. validation never ran in legacy) get a soft pass and go to T1 with `requires_revalidation=true`.

---

## 3. Import order (sequential — single transaction-per-collection)

```
┌─ Step 1  T3 audit collections    (additive, low risk, low value)
│
├─ Step 2  T2 archive              (read-only intelligence preservation)
│
├─ Step 3  T1 survivor seed        (the operator-critical insert)
│
├─ Step 4  lineage backfill        (mutation_events parent ↔ child relinking)
│
└─ Step 5  index rebuild + count audit (verify in == out)
```

Each step writes a checkpoint to a new collection `migration_checkpoints` (created at import time). The pipeline can resume from any checkpoint if interrupted.

### Order rationale

1. T3 first because it's lowest-risk — pure append, no foreign keys touched.
2. T2 next because it's append to a brand-new collection — collision impossible.
3. T1 last because it inserts into a LIVE collection (`strategy_library`) that the operator UI consumes; running it last minimises operator-visible churn.
4. Lineage backfill last among writes — it needs both T1 and T2 to be in place to resolve fingerprints.

---

## 4. Conflict handling

| Scenario | Resolution |
|---|---|
| Imported fingerprint already in canonical `strategy_library` (e.g. coincidentally same SHA1) | **Skip import; log to `migration_skipped` collection.** Canonical wins. |
| Imported strategy refers to a `parent_fingerprint` not in either canonical or T2 archive | Mark as `lineage_orphan=true`; do not delete. Allows operator review. |
| Imported strategy has corrupt or missing `strategy_text` AND `strategy_ir` | **Skip; log to `migration_rejected`.** Cannot recompute without the source. |
| Imported strategy validation report is malformed | Strip the validation report; mark `requires_revalidation=true`. The post-import pipeline will revalidate. |
| Import fingerprint collides with a Mongo unique-index entry | Catch DuplicateKeyError; treat as "already present"; skip. |

All conflict resolutions are logged to `migration_log` (new collection at import time). The operator gets a summary report after each tier.

---

## 5. The "do not deploy" guarantee

Every T1 strategy inserted into `strategy_library` carries:

```json
{
  ...,
  "stage": "IMPORTED_SEED",
  "stage_locked_until": "<import_date + 30 days>",
  "provenance": {
    "source": "1vcpu_migration",
    "imported_at": "<ISO>",
    "operator": "<email from .env>",
    "requires_revalidation": true,
    "requires_rematching": true
  }
}
```

The Auto-Selection engine refuses to deploy any strategy with `stage="IMPORTED_SEED"` until:
1. `stage_locked_until` has passed, AND
2. The post-import pipeline (`POST_IMPORT_PIPELINE.md`) has produced a fresh `validation_report`, AND
3. `provenance.requires_revalidation` flips to `false` after revalidation completes, AND
4. Operator explicitly promotes via the existing Auto-Selection UI.

This is implemented by adding a guard in `engines/auto_selection_engine.py` at deploy decision time — **a 5-line change**, queued as a P0 task once the operator authorises POST_IMPORT_PIPELINE execution.

---

## 6. Estimated import durations

| Tier | 500 docs | 2,000 docs |
|---|---|---|
| T3 | < 30 s | ~1 min |
| T2 | ~30 s | ~2 min |
| T1 (with revalidation gate flag set) | ~1 min | ~3 min |
| Lineage backfill | ~30 s | ~2 min |
| Index rebuild + count audit | ~10 s | ~30 s |
| **TOTAL import-only** | **< 3 min** | **< 10 min** |

Re-processing (the actual operator-valuable work) happens in the post-import pipeline and is bounded by market-data availability + LLM budget, NOT by import speed.

---

## 7. Roll-back

Each tier is reversible via:

```
db.strategy_library.deleteMany({"provenance.source": "1vcpu_migration"})
db.strategy_library_archive.drop()
db.<lifecycle/performance/alert>.deleteMany({"imported": true})
db.migration_checkpoints.drop()
db.migration_log.drop()
db.migration_skipped.drop()
db.migration_rejected.drop()
```

Roll-back is **safe at any tier boundary** because each tier's writes are tagged. No tier modifies existing canonical rows in-place (no `update` operations on canonical data — only `insert`).

---

## 8. Operator decisions still required

* Confirm `total_trades >= 30` floor (§2.1) — adjust if the 1-vCPU pod ran shorter backtests.
* Confirm `created_at` 365-day window (§2.7) — extend if any keeper-strategies pre-date that.
* Confirm 30-day `stage_locked_until` (§5) — shorten if operator wants to revalidate-and-deploy faster.
* Confirm 5-line `auto_selection_engine.py` guard is acceptable (§5) — this is the only backend code change required.

None of these block writing this plan. All are revisited in `IMPORT_READINESS_REPORT.md` before any import runs.

---

## 9. Status

* Plan only.
* No collection created.
* No `strategy_library` write performed.
* Awaiting operator delivery of the export + green `IMPORT_READINESS_REPORT.md`.
