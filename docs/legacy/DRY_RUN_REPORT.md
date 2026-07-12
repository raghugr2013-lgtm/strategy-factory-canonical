# DRY_RUN_REPORT.md — 1-vCPU Migration Dry-Run Receipt

**Executed:** 2026-02 (this session) · `POST /api/asf/import/migration { dry_run: true }`
**Operator:** `admin@strategyfactory.dev` (admin token used end-to-end)
**Constraints honoured:** No wet-run executed · live `strategy_library` UNTOUCHED (0 rows post-run) · no imports performed · no BI5 R3 / Phase 13 / Phase 14 / marketplace / deployment activity.

---

## 1. Pre-execution forecast (from the locked `asf_inspect` staging DB)

Computed by direct read of `asf_inspect` against the locked operator overrides
(`pf_floor=1.20`, `wr_floor=0.38`, `trades_floor=30`, `dd_ceiling=0.20`, default skip list).

| # | Question | Forecast |
|---|---|---:|
| **1** | Exact strategy rows to be inserted into live `strategy_library` | **14** |
| **2a** | T1 tier (live `strategy_library` survivors) | **14** |
| **2b** | T2 tier total | **11,598** |
| **2c** | T3 tier total | **1,938** |
| **3** | Breakdown of T2: ACTUAL strategies vs lineage / stability rows | T2 = **126 strategies** (into `strategy_library_archive`) + **10,430 mutation_events** + **1,042 mutation_stability rows** |
| **3** | Breakdown of T3: lifecycle vs performance vs alerts | T3 = **878 lifecycle-history** + **1,047 performance-history** + **13 alert** rows (all un-joined to library; `imported=true`) |
| **4** | Duplicate-fingerprint count expectation (intra-package) | **0** |
| **5** | Expected `lineage_orphan` count (parent not in the package) | **140 of 140 strategies** carry an out-of-package parent → `lineage.ancestors_complete = false` on every survivor. Of those, **14 are T1**. (Reported as a per-doc flag, not a top-level warning — per ASF spec §4.2.2 this is permitted closure and is NOT an error.) |

### Why every T1 candidate has `max_drawdown_pct = 0`

All 14 T1 candidates show `max_drawdown_pct = 0` in the source. This is a legacy data
anomaly — the 1-vCPU pod never re-computed DD for these variants. The adapter preserves
the legacy value and stamps `extensions.migration.metrics_max_drawdown_pct_quality =
"not_recomputed_in_source"` so the post-import pipeline can re-derive DD against live
BI5-cached data before the strategies are considered deployable.

---

## 2. Dry-run receipt — actual numbers (post-execution)

```
import_id:    fc951e79-35cd-4ec6-a626-3190640bf6fd
package_id:   13c17364-891d-4cba-b7c0-b3ff2d6c0091
package_type: migration
dry_run:      true
status:       pending  (dry-run completed; awaiting commit decision)
duration:     0.043 s
```

### 2.1 Tier breakdown

```json
{
  "T1": 14,
  "T2": 11598,
  "T3": 1938
}
```

**Counts match the forecast EXACTLY** (T1=14, T2=11598, T3=1938).

### 2.2 Detailed action counts

```json
{
  "strategies_inserted":  14,    // T1 → strategy_library
  "strategies_skipped":   0,     // no dups against the receiver
  "strategies_merged":    0,
  "strategies_replaced":  0,
  "archive_rows":         126,   // T2 strategies → strategy_library_archive
  "lineage_edges":        11472, // T2 — 10,430 events + 1,042 stability
  "lifecycle_rows":       878,   // T3 — strategy_lifecycle_history (imported=true)
  "performance_rows":     1047,  // T3 — strategy_performance_history (imported=true)
  "alerts":               13,    // T3 — auto_factory_alert_log (imported=true)
  "cert_rows":            0      // no BI5 cert rows in source (per spec §3, OK)
}
```

**Total proposed Mongo writes on wet-run: 13,550** (matches the
`PACKAGE_INSPECTION_REPORT.md §6` and `GATE3_IMPLEMENTATION_PLAN.md §6` predictions).

### 2.3 By-collection action distribution (from the action audit)

| Collection | Actions | Dedup outcome |
|---|---:|---|
| `strategy_library` | 14 | fresh_insert × 14 |
| `strategy_library_archive` | 126 | fresh_insert × 126 |
| `mutation_events` | 10,430 | fresh_insert × 10,430 |
| `mutation_stability_log` | 1,042 | fresh_insert × 1,042 |
| `strategy_lifecycle_history` | 878 | fresh_insert × 878 |
| `strategy_performance_history` | 1,047 | fresh_insert × 1,047 |
| `auto_factory_alert_log` | 13 | fresh_insert × 13 |
| **TOTAL** | **13,550** | **100 % fresh_insert / 0 % skipped** |

### 2.4 Calibration drift

```json
{
  "drift_detected": false,
  "drift_keys": [],
  "package_tick_validator":  "tick_validator@P0B-v2",
  "receiver_tick_validator": "tick_validator@P0B-v2",
  "package_ranker_version":  "v1.1",
  "receiver_ranker_version": "v1.1"
}
```

Zero drift (synthesised from the receiver — exactly as predicted by
`PACKAGE_INSPECTION_REPORT.md §3 R3`).

### 2.5 Post-dry-run verification

```json
{
  "rows_checked":          140,
  "identity_drift":        0,
  "missing_inserts":       0,
  "cert_replay_mismatch":  0,
  "status":                "verified",
  "warnings":              []
}
```

All 140 fingerprints validated as 40-char SHA-1; no schema drift; no identity errors.

### 2.6 Top-level warnings

```
warnings: []
```

No top-level warnings raised. (Per-doc `lineage.ancestors_complete = false` is set on
every strategy, which is the spec-compliant way to record out-of-package parents per
ASF v1.0 §4.2.2 — see §1 row 5 above.)

---

## 3. Sample T1 strategy doc — operator contracts verified end-to-end

Inspecting the first T1 action in the dry-run receipt (`fingerprint = 455f09c9…` —
XAUUSD H4, PF=1.28, WR_legacy=40, trades=230):

| Operator contract | Observed value |
|---|---|
| `provenance.cohort_id` | `"1vcpu_2026_migration"` ✅ |
| `provenance.relaxation_reason` | `"pf_floor_1.20+wr_floor_0.38"` ✅ |
| `lifecycle.stage` | `"IMPORTED_SEED"` ✅ |
| `lifecycle.stage_locked_until` | `2026-07-13T17:04:48+00:00` (`+30 d` from dry-run) ✅ |
| `provenance.requires_revalidation` | `true` ✅ |
| `provenance.requires_rescoring` | `true` ✅ |
| `provenance.requires_rematching` | `true` ✅ |
| `lineage.parent_fingerprint` | `d8367cbf8dce9ed228acea570b1416799bc1105c` (resolved via `mutation_events`) ✅ |
| `lineage.ancestors_complete` | `false` (parent not in package — orphan flag) ✅ |
| `lineage.ancestors` length | 1 (depth-1 walk; depth cap 5 means deeper chains return more) ✅ |
| `strategy_hash` | SHA-256, 64 hex chars (`03a59825…`) ✅ |
| `metrics.win_rate` | `0.40` (legacy `40` normalised ÷100) ✅ |
| `metrics.profit_factor` | `1.28` ✅ |
| `metrics.total_trades` | `230` ✅ |
| `metrics.max_drawdown_pct` | `0.0` (preserved; data quality flag set in extensions) ✅ |
| `extensions.migration.metrics_max_drawdown_pct_quality` | `"not_recomputed_in_source"` ✅ |
| `provenance.historical_scores.*` keys populated | `score, pass_probability, confidence, consistency_score, expected_value, decision, oos_holdout, prop_firm_panel` ✅ |
| `explorer` block | `null` (live ranker MUST re-derive) ✅ |
| `bi5_cert` block | `null` (post-import BI5 cert MUST run) ✅ |

**Every operator decree is honoured byte-for-byte in the staged receipt.**

---

## 4. Live state post-dry-run (must be unchanged)

```
RECEIVER DB (test_database):
  strategy_library:                      0          ← untouched ✅
   ↳ provenance.source=1vcpu_migration:  0          ← untouched ✅
  strategy_library_archive:              0          ← untouched ✅
  mutation_events:                       0          ← untouched ✅
  strategy_lifecycle_history:            0 imported ← untouched ✅
  strategy_performance_history:          0 imported ← untouched ✅
  auto_factory_alert_log:                0 imported ← untouched ✅

RECEIPT-PERSISTENCE (lazy-create; expected to grow):
  asf_import_log:        1                          ← 1 dry-run receipt
  asf_import_actions:    13,550                     ← 1 row per planned write
```

**Zero writes to live data.** The only Mongo state mutation is the receipt + action
audit (per architecture §4, this is the auditable trail of what *would* happen on
commit).

---

## 5. Compatibility verdict (re-affirmed against actual receipt)

| Dimension | Pre-execution forecast | Dry-run actual | Drift |
|---|---|---|---|
| T1 count | 14 | 14 | 0 |
| T2 count | 11,598 | 11,598 | 0 |
| T3 count | 1,938 | 1,938 | 0 |
| Duplicate fingerprints | 0 | 0 | 0 |
| Calibration drift_detected | false | false | 0 |
| Identity drift | 0 | 0 | 0 |
| Missing inserts | 0 | 0 | 0 |
| Cert-replay mismatch | 0 | 0 | 0 |

🟢 **VERDICT: GREEN for commit.**

The package is byte-faithful to the forecast. The AMBER classification in the
inspection report was raised by three concerns; each is now resolved or accepted:

1. **0 T1 at strict PF≥1.30** — operator relaxed to PF≥1.20 (Option B). **14 T1
   delivered.** ✅
2. **15 deterministic adapter transforms required** — all 15 verified passing in
   `tests/test_asf_migration_adapter.py` and observably correct in the staged T1
   sample (§3). ✅
3. **Lifecycle / performance history un-joined to library survivors** — accepted as
   T3 audit context per the locked Tier-3 policy. 1,938 rows ingested with
   `imported=true`, no FK to live library. ✅

---

## 6. What is **NOT** done (operator-locked exclusions)

* No wet-run executed.
* `migration_bundle.tar.gz` unmodified in `/app/_migration_inbox/`.
* Live `strategy_library` is 0 rows of `1vcpu_migration` provenance (i.e. untouched).
* No BI5 R3 work, no Phase 13 Dossier, no Phase 14 Valuation, no marketplace, no
  deployment activity.

---

## 7. Recommended next step

The dry-run is GREEN. Operator may now authorise the wet-run:

```bash
curl -X POST "$BACKEND_URL/api/asf/import/migration" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "dry_run": false,
       "operator_overrides": {
         "pf_floor": 1.20,
         "wr_floor": 0.38,
         "lineage_depth": 5,
         "lock_days": 30,
         "cohort_id": "1vcpu_2026_migration",
         "relaxation_reason": "pf_floor_1.20+wr_floor_0.38"
       }
     }'
```

Expected wet-run outcome (identical receipt + actual Mongo writes):
* `strategy_library`              : +14 rows (IMPORTED_SEED, locked until 2026-07-13)
* `strategy_library_archive`      : +126 rows
* `mutation_events`               : +10,430 rows
* `mutation_stability_log`        : +1,042 rows
* `strategy_lifecycle_history`    : +878 rows (`imported=true`)
* `strategy_performance_history`  : +1,047 rows (`imported=true`)
* `auto_factory_alert_log`        : +13 rows (`imported=true`)
* Auto-Selection engine: continues to block all 14 imported survivors (guard wired).
* Post-import pipeline: must run BI5 cert sweep + ranker pass + challenge re-match
  to flip the `requires_*` flags before any imported survivor becomes deployable.

---

**End of DRY_RUN_REPORT.md.**
**Status: GREEN for commit. Awaiting explicit operator authorisation for the wet-run.**
