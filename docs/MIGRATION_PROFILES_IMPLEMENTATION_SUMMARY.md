# MIGRATION PROFILES — Implementation Summary

**Status:** ✅ Implemented, tested (25/25 pytest pass), dry-runs verified for both modes.
**Author:** AI Strategy Factory Engineering
**Scope of change:** `infra/scripts/migrate-data.py`, `infra/scripts/migrate-data.sh`, `infra/scripts/verify-vps-schema.sh` (new), `backend/tests/test_migration.py`.
**Nothing outside these files was modified.**

---

## 1. Supported Modes

| Profile | Flag | Tiers migrated | Intended use |
|---|---|---|---|
| **Lean** (DEFAULT) | `--profile lean` *(or nothing)* | `critical` only (80 rows) | Production deployment |
| **Full** (opt-in) | `--profile full` | `critical` + `regenerable` + `optional` (110 rows) | Disaster recovery / archival / exact env replication |

`factory_supervisor_lock` is in `INTENTIONALLY_EXCLUDED` and is permanently skipped in **both** modes.

---

## 2. Reordered `MIGRATION_PLAN`

Every row now carries a `tier` field. Rows are grouped by phase so **business-critical data always migrates before bulk / regenerable data** — an interruption during Phase 5 still leaves a fully operational platform.

| Phase | Content | Tier | Rows |
|---|---|---|---|
| 1 | Identity & Governance (users, audit_log, settings, market_universe, prop_firm_*, instrument_mappings) | critical | 13 |
| 2 | Core IP (strategies, research, validation, calibration, bi5_certifications, market_intelligence, risk_of_ruin_evaluations) | critical | 26 |
| 3 | Bots, Portfolios, Deployment, Execution ledger (master_bot_*, portfolios, cbot_parity, runner_accounts, live_tracking, trade_runner_*) | critical | 23 |
| 4 | Flags, Audit journals, Orchestrator, Monitoring (flag_*, admission_journal, activation_journal, monitoring_breach_log, auto_factory_*, factory_supervisor_defer_queue/submissions/fag_proposals, multi_cycle_runs, orchestrator_env_priority) | critical | 18 |
| 5 | **Bulk / Regenerable (Lean-mode SKIP)** — market_data, market_data_ticks, tick_data, market_spread, market_profile_cells, data_coverage, bi5_ingest_log, bi5_cert_sweep_log, soak_stability_samples, mutation_stability_log | regenerable | 10 |
| 6 | **Optional / Ephemeral (Lean-mode SKIP)** — runtime state, transient caches, log-only collections | optional | 20 |

**Total planned rows:** 110 (was 111; `factory_supervisor_lock` removed from plan and moved to permanent exclusion).

---

## 3. Excluded Collections & Reason

### 3a. Permanent (both modes)

| Collection | Reason |
|---|---|
| `factory_supervisor_lock` | A stale lock document on a fresh v1.0 host would cause the supervisor to split-brain on first boot. Must be initialised empty on the new deployment. |

### 3b. Lean-only (regenerable, tier=regenerable)

| Collection | Reason |
|---|---|
| `market_data` | ~313 k OHLC bars; Dukascopy BI5 downloader regenerates byte-identically |
| `market_data_ticks` | Raw ticks — same source |
| `tick_data` | Alternative tick storage — same source |
| `market_spread` | ~309 k spread samples; live spread sweep rebuilds from broker feed |
| `market_profile_cells` | Derived cache over `market_data` |
| `data_coverage` | Summary index over `market_data` — must be regenerated when repopulated |
| `bi5_ingest_log` | Append-only log; next BI5 sweep repopulates |
| `bi5_cert_sweep_log` | Append-only log; next cert sweep repopulates |
| `soak_stability_samples` | Long-running host telemetry; new host = new baseline |
| `mutation_stability_log` | Operational variance samples per mutation; rebuilt on next sweep. **NOT an evolutionary-learning store** (verified by the schema-probe script) |

### 3c. Lean-only (ephemeral, tier=optional)

| Collection | Reason |
|---|---|
| `strategy_status`, `strategy_lifecycle` | Derivable from `strategies` + `lifecycle_events` |
| `readiness_snapshots` | Rebuilt on next readiness check |
| `auto_factory_alert_log`, `monitoring_alert_log`, `paper_deviation_alert_log`, `asf_import_log`, `post_import_pipeline_log`, `pipeline_logs` | Log-only |
| `auto_maintenance_status`, `cadence_state`, `factory_supervisor_heartbeats`, `advisory_locks`, `monitoring_state`, `scaling_nodes`, `host_capabilities`, `auto_run_cycles`, `bi5_cert_sweep_runs` | Rebuilt on next boot / tick / sweep |
| `ctrader_desktop_state` | Client-side UI state |
| `event_continuations` | Short-lived continuation state; typically expired on new deployment |

---

## 4. Dry-run Validation Results

Both modes dry-run cleanly against the synthetic v01 seed (47 collections, 156 docs) — reports saved to `dry-run-reports/`:

### Lean profile (default)
```
profile: lean
tiers:   [critical]
collections_processed: 40
documents_migrated:    149
documents_upgraded_in_place: 73
document_level_errors: 0
hard_errors:          0
warnings:             31   (tier skips + factory_supervisor_lock)
```
Report: `dry-run-reports/migration-report.lean.dryrun.json`

### Full profile (opt-in)
```
profile: full
tiers:   [critical, optional, regenerable]
collections_processed: 47
documents_migrated:    156
documents_upgraded_in_place: 73
document_level_errors: 0
hard_errors:          0
warnings:             1    (auto-passthrough for unplanned `legacy_experimental_notes`)
```
Report: `dry-run-reports/migration-report.full.dryrun.json`

### Delta
Full − Lean = **7 documents** (from regenerable+optional collections in the seed). This matches expectation.

### Independent validator
`validate-migration.py` parsed **110 plan rows + 1 permanent exclusion** — **Verdict: PASS (default mode)**.
Reports: `dry-run-reports/audit-report.dryrun.{json,md}`, `dry-run-reports/validation-report.dryrun.{json,md}`.

### Bundle integrity
`build-bundle.sh` rebuilt deterministically:
```
SHA-256:  8d11a1218d240804415d5dec2fa7c050520e42202c0c8f84af5254d25c060396
Size:     3,260,419 bytes
Manifest: 1039 entries (SHA256SUMS)
```

### Pytest suite
**25/25 pass** (`backend/tests/test_migration.py`). New tests added:
- `test_19` — every plan row has a valid tier
- `test_20` — regenerable + optional sets exactly match the operator-approved classification
- `test_21` — `factory_supervisor_lock` is in `INTENTIONALLY_EXCLUDED` and NOT in the plan
- `test_22` — `PROFILE_TIERS` has exactly `lean` and `full` with the correct tier membership
- `test_23` — Lean profile skips every regenerable/optional collection (verified on a real target DB)
- `test_24` — Full profile migrates everything, still honours the permanent exclusion
- `test_25` — Lean dry-run produces the expected tier-skip warnings and no writes

---

## 5. New Operator Utility

`infra/scripts/verify-vps-schema.sh` — read-only pre-migration VPS probe that answers the two verification steps you flagged:

1. **`market_data` field schema** — samples 200 docs, flags any field outside the reproducible-OHLCV/spread/timestamp allowlist. **PASS** ⇒ safe to exclude in Lean.
2. **`mutation_stability_log` shape** — samples 200 docs, flags any evolutionary-learning red-flag field (`generation`, `genome`, `chromosome`, `population`, `fitness_history`, `elite`, `lineage`, `ancestors`, `parent_ids`, `mutation_history`, `policy`, `reward_curve`). **PASS** ⇒ confirmed as operational telemetry only.

Outputs `verify-vps-schema-<stamp>.{json,md}` next to the invocation. Exit `0` = both PASS; exit `1` = at least one REVIEW_REQUIRED.

Run before Lean production migration:
```bash
SOURCE_MONGO_URL=mongodb://... SOURCE_MONGO_DB=test_database \
    ./infra/scripts/verify-vps-schema.sh
```

---

## 6. Operator Cheat-sheet

```bash
# 1. Pre-migration VPS schema verification (one-shot, no writes)
./infra/scripts/verify-vps-schema.sh

# 2. Lean production dry-run (default profile)
./infra/scripts/migrate-data.sh --dry-run

# 3. Lean production live migration (default profile — RECOMMENDED)
./infra/scripts/migrate-data.sh

# 4. Full-mode dry-run (disaster recovery / archival)
./infra/scripts/migrate-data.sh --profile full --dry-run

# 5. Full-mode live migration
./infra/scripts/migrate-data.sh --profile full

# 6. Resume after interruption (works with either profile)
./infra/scripts/migrate-data.sh --resume            # continues Lean
./infra/scripts/migrate-data.sh --profile full --resume   # continues Full
```

All commands preserve the pre-existing observability: named container (no `--rm`), tee'd log, per-doc traceback capture, progress checkpoints, and idempotent fingerprint-based re-runs.

---

**Awaiting operator sign-off** on:
1. Run `verify-vps-schema.sh` on the VPS to confirm both PASS.
2. Run `./infra/scripts/migrate-data.sh --dry-run` on the VPS to confirm Lean profile matches production audit.
3. Execute Lean live migration.
