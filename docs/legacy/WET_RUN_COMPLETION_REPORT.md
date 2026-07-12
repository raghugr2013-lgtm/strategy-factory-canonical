# WET_RUN_COMPLETION_REPORT.md — 1-vCPU Migration Wet-Run

**Executed:** 2026-02 (this session) via
`POST /api/asf/import/migration { dry_run: false, operator_overrides: {pf_floor: 1.20, wr_floor: 0.38, stage_locked_until_days: 30, lineage_depth_cap: 5} }`
**Operator:** `admin@strategyfactory.dev` (admin token used end-to-end)
**Authorisation source:** explicit operator GO after dry-run review.
**Constraints honoured:** No BI5 R3 work · no Phase 13 · no Phase 14 · no marketplace · no 12-vCPU deployment · no new roadmap branch opened.

---

## 1. Final inserted counts by collection

| Collection | Wet-run inserts | Cumulative count after wet-run | Tier |
|---|---:|---:|:--:|
| `strategy_library` | **14** | 14 | T1 |
| `strategy_library_archive` | **126** | 126 | T2 |
| `mutation_events` | **10,430** | 10,430 | T2 |
| `mutation_stability_log` | **1,042** | 1,042 | T2 |
| `strategy_lifecycle_history` | **878** | 878 | T3 |
| `strategy_performance_history` | **1,047** | 1,047 | T3 |
| `auto_factory_alert_log` | **13** | 13 | T3 |
| **TOTAL** | **13,550** | — | — |
| `asf_import_log` | +1 | 2 (1 dry-run + 1 wet-run) | audit |
| `asf_import_actions` | +13,550 | 27,100 (audit copies of both runs' staged actions) | audit |

**All counts match the dry-run forecast exactly.** Wet-run duration: 26.36 s (well inside the 60–120 s budget in `MIGRATION_PRIORITY.md §6`).

---

## 2. Final `strategy_library` count

| Metric | Value |
|---|---:|
| `strategy_library` total rows | **14** |
| Rows tagged `provenance.source="1vcpu_migration"` | **14** |
| Rows tagged `provenance.cohort_id="1vcpu_2026_migration"` | **14** |
| Rows with `lifecycle.stage="IMPORTED_SEED"` | **14** |
| Pre-existing rows (any other provenance) | **0** |

The 14 imported strategies are the **only** rows in the live `strategy_library` collection.

---

## 3. T1 / T2 / T3 imported counts

```json
{
  "T1": 14,
  "T2": 11598,
  "T3": 1938
}
```

### T2 sub-breakdown (actual strategies vs lineage/stability)
| Sub-bucket | Count |
|---|---:|
| Strategies in archive | **126** |
| Lineage edges (`mutation_events`) | **10,430** |
| Stability/sweep rows (`mutation_stability_log`) | **1,042** |
| **T2 total** | **11,598** |

### T3 sub-breakdown (lifecycle vs performance vs alert evidence)
| Sub-bucket | Count |
|---|---:|
| Lifecycle history rows | **878** |
| Performance history rows | **1,047** |
| Alert log rows | **13** |
| **T3 total** | **1,938** |

All T3 rows are tagged `imported=true` and `source_export_id=<package_id>` per the locked Tier-3 policy (un-joined to live library).

---

## 4. Verification results

```json
{
  "rows_checked":         14,
  "identity_drift":       0,
  "missing_inserts":      0,
  "cert_replay_mismatch": 0,
  "duplicate_count":      0,
  "status":               "verified",
  "warnings":             []
}
```

| Check | Result |
|---|:--:|
| Identity drift (fingerprint round-trip) | **0** ✅ |
| Missing inserts (post-commit re-read) | **0** ✅ |
| Cert replay mismatch | **0** (no source cert windows; nothing to replay) ✅ |
| Duplicate fingerprints (`strategy_library`) | **0** ✅ |
| Calibration drift detected | **false** ✅ |
| Warnings (top-level) | **[]** ✅ |
| Verifier status | **`verified`** ✅ |

---

## 5. Rollback procedure and rollback verification

### 5.1 Rollback procedure (NOT executed — operator authorisation required)

The adapter writes are partitioned by two precise keys:
* `provenance.cohort_id = "1vcpu_2026_migration"` (set on every strategy doc — T1 + T2 archive)
* `source_export_id = "0c934166-440f-4f01-bf80-d590805ad2c1"` (set on every lineage / T3 row — the wet-run package_id)

Rollback is a 7-statement targeted delete. Each statement is **idempotent** and **safe to re-run**:

```javascript
// /app/scripts/rollback_1vcpu_wetrun.js — ROLLBACK SCRIPT (DO NOT RUN WITHOUT OPERATOR GO)
const PKG = "0c934166-440f-4f01-bf80-d590805ad2c1";
const COHORT = "1vcpu_2026_migration";

db.strategy_library.deleteMany({ "provenance.cohort_id": COHORT });
db.strategy_library_archive.deleteMany({ "provenance.cohort_id": COHORT });
db.mutation_events.deleteMany({ "source_export_id": PKG });
db.mutation_stability_log.deleteMany({ "source_export_id": PKG });
db.strategy_lifecycle_history.deleteMany({ "source_export_id": PKG, "imported": true });
db.strategy_performance_history.deleteMany({ "source_export_id": PKG, "imported": true });
db.auto_factory_alert_log.deleteMany({ "source_export_id": PKG, "imported": true });

// asf_import_log + asf_import_actions are PRESERVED — they are the
// permanent audit trail per ASF_BACKEND_ARCHITECTURE.md §4.1.
// The rolled-back import_id stays queryable for post-mortem.
```

### 5.2 Rollback dry-count (executed — read-only verification, no deletes)

| Statement | Rows it WOULD delete | Rows it WOULD leave alone |
|---|---:|---|
| `strategy_library.deleteMany({cohort_id: "1vcpu_2026_migration"})` | **14** | 0 other-source survivors |
| `strategy_library_archive.deleteMany({cohort_id: "1vcpu_2026_migration"})` | **126** | 0 |
| `mutation_events.deleteMany({source_export_id: PKG})` | **10,430** | 0 |
| `mutation_stability_log.deleteMany({source_export_id: PKG})` | **1,042** | 0 |
| `strategy_lifecycle_history.deleteMany({source_export_id: PKG, imported: true})` | **878** | 0 native-source rows touched |
| `strategy_performance_history.deleteMany({source_export_id: PKG, imported: true})` | **1,047** | 0 native-source rows touched |
| `auto_factory_alert_log.deleteMany({source_export_id: PKG, imported: true})` | **13** | 0 native-source rows touched |
| **TOTAL** | **13,550** (matches wet-run insert count exactly) | — |
| `asf_import_log` | **0** (audit trail preserved) | 2 receipts intact |
| `asf_import_actions` | **0** (audit trail preserved) | 27,100 action rows intact |

### 5.3 Post-rollback expected state (verified analytically; not executed)
* `strategy_library` → 0 rows
* `strategy_library_archive` → 0 rows
* `mutation_events` → 0 rows
* `mutation_stability_log` → 0 rows
* `strategy_lifecycle_history` → 0 rows
* `strategy_performance_history` → 0 rows
* `auto_factory_alert_log` → 0 rows
* `asf_import_log` → 2 rows (both retained; wet-run receipt marked `rolled_back=true` if operator additionally invokes `POST /api/asf/import/{id}/abort`)
* `asf_import_actions` → 27,100 rows (retained)

### 5.4 Rollback can be re-imported (idempotent)

After rollback, re-invoking the wet-run reproduces an identical state (the adapter is
deterministic and the new `package_id` simply gets a fresh UUID). This is asserted by
`tests/test_asf_migration_adapter.py::test_idempotent_re_run` — verified PASS.

---

## 6. Imported T1 breakdown — by symbol, timeframe, strategy family

### 6.1 By (symbol, timeframe)

| Pair | Timeframe | Count | Avg PF | Avg WR | Avg trades |
|---|---|---:|:---:|:---:|---:|
| ETHUSD | H1 | **6** | 1.280 | 0.3910 | 174 |
| ETHUSD | H4 | **5** | 1.280 | 0.3920 | 189 |
| XAUUSD | H4 | **3** | 1.247 | 0.3920 | 213 |
| **TOTAL** | — | **14** | — | — | — |

### 6.2 By strategy family (`lineage.mutation_family`)

| Family | Count | Notes |
|---|---:|---|
| `trend_pullback` | **6** | All 6 ETHUSD/H1 |
| `mtf_htf_confirmation` | **5** | All 5 ETHUSD/H4 |
| `risk_reward_1_2` | **1** | XAUUSD/H4 |
| `filter_remove_rsi` | **1** | XAUUSD/H4 |
| `volatility_atr_breakout` | **1** | XAUUSD/H4 |
| **TOTAL** | **14** | — |

### 6.3 Style classification

| `fingerprint_inputs.style` | Count |
|---|---:|
| `unknown` | **14** (all) |

Legacy `style` field was never populated in the 1-vCPU pod; ASF spec accepts any
string, and downstream Phase 13 Dossier Engine is responsible for re-classifying
imported survivors. `unknown` is **not** a deployability blocker.

### 6.4 Per-row inventory of the 14 T1 survivors

| # | Fingerprint (first 12) | Pair | TF | PF | WR (legacy %) | Trades |
|---|---|---|---|---:|---:|---:|
| 1 | `455f09c9648c` | XAUUSD | H4 | 1.28 | 40.0 | 230 |
| 2 | `0bed627d6906` | XAUUSD | H4 | 1.23 | 39.4 | 251 |
| 3 | `bbf034812c26` | XAUUSD | H4 | 1.23 | 38.2 | 157 |
| 4 | `0db33f33895b` | ETHUSD | H4 | 1.28 | 39.2 | 189 |
| 5 | `8579a7495fb7` | ETHUSD | H4 | 1.28 | 39.2 | 189 |
| 6 | `84806e0356ef` | ETHUSD | H4 | 1.28 | 39.2 | 189 |
| 7 | `bb8aa20f1ece` | ETHUSD | H4 | 1.28 | 39.2 | 189 |
| 8 | `c1f1ebbb7fdf` | ETHUSD | H4 | 1.28 | 39.2 | 189 |
| 9 | `99dc818947a3` | ETHUSD | H1 | 1.28 | 39.1 | 174 |
| 10 | `00cae3914bde` | ETHUSD | H1 | 1.28 | 39.1 | 174 |
| 11 | `388e74a92911` | ETHUSD | H1 | 1.28 | 39.1 | 174 |
| 12 | `3b12e9629fa3` | ETHUSD | H1 | 1.28 | 39.1 | 174 |
| 13 | `9dcfeb944025` | ETHUSD | H1 | 1.28 | 39.1 | 174 |
| 14 | `dbd37f01f7bf` | ETHUSD | H1 | 1.28 | 39.1 | 174 |

`metrics.win_rate` is stored as **0..1** on every row (e.g. `0.40`, `0.392`, `0.391`)
after the `÷100` normalisation. All 14 have `metrics.max_drawdown_pct = 0` (legacy
data anomaly preserved with quality flag — see §3 of inspection report).

---

## 7. Confirmation: re-validation flags applied to all 14 imported survivors

Verified via `mongosh` count:

```
provenance.requires_revalidation = true : 14 / 14   ✅
provenance.requires_rescoring    = true : 14 / 14   ✅
provenance.requires_rematching   = true : 14 / 14   ✅
```

Sample doc (`fingerprint=455f09c9…`, the highest-PF T1 survivor):

```jsonc
{
  "lifecycle": {
    "stage": "IMPORTED_SEED",
    "stage_locked_until": "2026-07-13T17:12:16.334566+00:00"  // +30 d from wet-run
  },
  "provenance": {
    "source":               "1vcpu_migration",
    "source_pod":           "1vcpu",
    "tier_class":           "T1",
    "cohort_id":            "1vcpu_2026_migration",
    "relaxation_reason":    "pf_floor_1.20+wr_floor_0.38",
    "requires_revalidation": true,
    "requires_rescoring":    true,
    "requires_rematching":   true,
    "historical_scores": {
      "score":             50.0,
      "pass_probability":  35.0,
      "confidence":        60.0,
      "consistency_score": 65.0,
      "expected_value":    { /* … */ },
      "decision":          { /* … */ },
      "prop_firm_panel":   { /* … */ },
      "oos_holdout":       { /* … */ }
    }
  },
  "bi5_cert": null,   // forced null — receiver MUST re-derive
  "explorer": null    // forced null — receiver MUST re-derive
}
```

---

## 8. Confirmation: no imported strategy is currently deployable

All three gates close around every imported survivor:

| Gate | Per-row state | Pass condition for deployability |
|---|---|---|
| **G1 — Lifecycle stage** | `stage="IMPORTED_SEED"` on all 14 | Stage must NOT be in `{IMPORTED_SEED, DEMOTED, RETIRED, BANNED}` |
| **G2 — Lock window** | `stage_locked_until=2026-07-13T17:12:16+00:00` (≈ 5 months in the future) on all 14 | `stage_locked_until <= now()` |
| **G3 — Required revalidation** | All three `requires_*` flags = `true` on all 14 | ALL three flags must be `false` |

A strategy becomes deployable ONLY when **all three gates open simultaneously**. As of
wet-run completion, **zero** imported survivors meet that condition.

This is enforceable in one Mongo expression:

```javascript
db.strategy_library.countDocuments({
  "lifecycle.stage": { $nin: ["IMPORTED_SEED", "DEMOTED", "RETIRED", "BANNED"] },
  "lifecycle.stage_locked_until": { $lte: new Date().toISOString() },
  "provenance.requires_revalidation": { $ne: true },
  "provenance.requires_rescoring":    { $ne: true },
  "provenance.requires_rematching":   { $ne: true },
  "provenance.cohort_id": "1vcpu_2026_migration"
}) // → 0
```

Result: **0 deployable imported survivors.** ✅

---

## 9. Confirmation: Auto-Selection AND Master Bot Ranker ignore IMPORTED_SEED until flags clear

### 9.1 Auto-Selection guard — verified empirically

The `_is_imported_seed_locked()` helper in `engines/auto_selection_engine.py` runs as
the **first statement** inside the candidate loop of `run_auto_selection()`. It
returns `true` if any of:
* `lifecycle.stage == "IMPORTED_SEED"`, OR
* `stage_locked_until > now()`, OR
* any of `requires_revalidation / requires_rescoring / requires_rematching` is `true`.

Live verification result (Python → live Mongo against the 14 wet-run survivors):

```
Imported survivors: 14
Blocked by guard via strategy_hash: 14/14   ← all 14 SHA-256 hashes blocked
Blocked by guard via fingerprint:   14/14   ← all 14 SHA-1 fingerprints blocked
Non-imported sentinel blocked?      False   ← guard does not over-block
```

**Both join paths (SHA-256 strategy_hash AND SHA-1 fingerprint) correctly block all 14
survivors. No false positives.** ✅

### 9.2 Master Bot Ranker — verified empirically

The Master Bot Ranker (`engines/master_bot_ranker.fetch_candidate_pool`) sources its
candidate pool from `survivor_runner.fetch_survivor_universe()`, which reads from the
`strategy_lifecycle` collection — **NOT** directly from `strategy_library`. The
migration adapter **does not write** to `strategy_lifecycle` (only to
`strategy_lifecycle_history` for T3 audit), therefore the imported survivors are
**structurally invisible** to the ranker.

Live verification:

```
Master Bot candidate pool size: 0
Imported survivors surfaced by Master Bot ranker: 0
```

**Master Bot Ranker returned 0 imported survivors.** ✅

Even in the hypothetical case that an imported strategy were promoted to
`strategy_lifecycle` prematurely, the ranker would compute a near-zero candidate
score because:
* `bi5_cert.verdict = null` → `_norm_bi5_verdict()` returns 0.0 → BI5 weight × 0 = 0
* `explorer = null` → `pass_probability` falls back to library, which lives under
  `provenance.historical_scores.*` (NOT `pass_probability` at root) → 0.0
* `deploy_score = null` → 0.0
* Net contribution from imported survivors approaches 0.0 — they would rank dead last
  regardless of which other strategies are in the pool.

---

## 10. Live state — final post-wet-run snapshot

```
RECEIVER DB (test_database):
  strategy_library:                     14 rows   (14 IMPORTED_SEED · all gated)
  strategy_library_archive:            126 rows   (T2 cold-storage)
  mutation_events:                  10,430 rows   (T2 lineage)
  mutation_stability_log:            1,042 rows   (T2 lineage)
  strategy_lifecycle_history:          878 rows   (T3 · imported=true · un-joined)
  strategy_performance_history:      1,047 rows   (T3 · imported=true · un-joined)
  auto_factory_alert_log:               13 rows   (T3 · imported=true · un-joined)

ASF AUDIT TRAIL (preserved):
  asf_import_log:                        2 rows   (1 dry-run + 1 wet-run)
  asf_import_actions:               27,100 rows   (audit copies of both runs)
```

**Total wet-run inserts: 13,550** — equals the wet-run insert count predicted in the
dry-run report.

---

## 11. Operator-locked exclusions honoured

| Activity | Status |
|---|---|
| BI5 R3 (B-3 / B-6 / B-7) | ❌ Not started |
| Phase 13 Dossier Engine | ❌ Not started |
| Phase 14 Valuation Engine | ❌ Not started |
| Marketplace surfaces | ❌ Not started |
| 12-vCPU deployment / cutover / 72-h soak | ❌ Not started |
| Any new roadmap branch | ❌ Not opened |

---

**End of WET_RUN_COMPLETION_REPORT.md.**
**Status: Wet-run COMPLETE & VERIFIED. 14 imported survivors at rest in `strategy_library`, fully gated. Stopping here per operator decree.**
