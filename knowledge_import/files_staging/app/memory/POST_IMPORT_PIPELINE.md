# POST-IMPORT PIPELINE
**Purpose:** Deterministic, idempotent re-hydration of the 12-vCPU deployment after a migration import of 1-vCPU artifacts.
**Discipline:** Additive only. No mutation of imported source rows beyond appending derived fields. All stages must be rerunnable.

---

## 0. PIPELINE OVERVIEW

```
[ IMPORT ]
     │
     ▼
[ STAGE 0 ] Schema & index validation     ← halts on schema mismatch
     │
     ▼
[ STAGE 1 ] Identity & fingerprint reconciliation
     │
     ▼
[ STAGE 2 ] Re-profile (per-strategy market profile refresh)
     │
     ▼
[ STAGE 3 ] Re-score (Quality v2, Evidence, Market, Trust, Pass-Prob v2)
     │
     ▼
[ STAGE 4 ] Re-rank (survivor pool ordering)
     │
     ▼
[ STAGE 5 ] Re-match (per-firm prop firm matching)
     │
     ▼
[ STAGE 6 ] Re-portfolio (Portfolio Builder regeneration)
     │
     ▼
[ STAGE 7 ] Re-masterbot (Master Bot generation from survivors)
     │
     ▼
[ STAGE 8 ] Marketplace-ready gating
     │
     ▼
[ READY ] Operator decree required before any autonomous loop is enabled.
```

Each stage MUST emit:
- a structured `pipeline_logs` entry
- a checkpoint document in `post_import_checkpoints` (collection seeded on first run)
- an idempotency key (`stage_name:input_hash`) — if checkpoint exists with matching hash, stage is a no-op.

Operator may resume at any stage. Default cadence: serial, manual confirmation between stages 1→4, automatic 5→8 once decreed.

---

## STAGE 0 — Schema & Index Validation

**Inputs:** Imported Mongo collections.

**Checks:**
1. Required Tier-1 collections present and non-empty (see MIGRATION_COMPATIBILITY_AUDIT §1).
2. Required indexes recreated (see audit §5).
3. `governance_universe` config doc has `_id="config"` and required fields.
4. `users` collection has at least one admin (or skip and re-seed on target).

**On failure:** Halt. Emit `migration_blocker` alert. No mutations.

**Success criteria:** All required collections + indexes confirmed.

---

## STAGE 1 — Identity & Fingerprint Reconciliation

**Goal:** Ensure no `strategy_library.fingerprint` collisions exist, and that every `strategy_lifecycle.library_id` resolves.

**Operations (read-only first; write only on conflict):**
1. Build set of imported `fingerprint`s from `strategy_library`.
2. Verify uniqueness; on duplicate, keep the row with the highest `created_at` (latest validation) and write the discarded row to `strategy_library_conflicts`.
3. For each `strategy_lifecycle` doc, verify `library_id` points to an existing `strategy_library._id`. Orphans are written to `lifecycle_orphans` and excluded from later stages.

**Idempotency key:** `stage1:hash(sorted(fingerprints))`.

**Outputs:**
- `post_import_checkpoints` entry
- (optional) `strategy_library_conflicts`, `lifecycle_orphans`

---

## STAGE 2 — Re-profile

**Goal:** Refresh per-strategy market profile against any newly arrived market_data (none expected immediately after import, but the stage is required for idempotency).

**Operations:**
1. For each survivor in `strategy_library`, recompute `strategy_market_profile` row using current market_data coverage.
2. Refresh `market_environment_stats` for each (pair, timeframe) cell in `governance_universe.allowed`.

**Concurrency:** Throttled to N workers (N = min(8, vCPU/2)).

**Idempotency key:** `stage2:hash(fingerprint+market_data_max_ts)`.

---

## STAGE 3 — Re-score

This is the heaviest stage. Each score is independent and idempotent.

### 3.1 Quality Score v2
- Input: `strategy_library` validation_report + perf metrics.
- Output: `strategy_library.quality_score_v2` (additive field).
- Formula: target deployment formula (do not invent here; load from target's `scoring/quality_v2.py`).

### 3.2 Evidence Score
- Input: `strategy_lifecycle.evidence`, `strategy_lifecycle_history`, `strategy_performance_history`.
- Output: `strategy_library.evidence_score`.

### 3.3 Market Score
- Input: `strategy_market_profile`, `market_environment_stats`.
- Output: `strategy_library.market_score`.

### 3.4 Trust Score
- Input: deploy_score history derived from `strategy_lifecycle_history.evidence_snapshot`, OOS pass count from `oos_holdout`, stability from `mutation_stability_log`.
- Output: `strategy_library.trust_score`.

### 3.5 Pass Probability v2 (per firm)
- For each strategy × each firm in `prop_firm_rules`, compute pass probability.
- Write to `strategy_pass_analysis` (one doc per pair).
- Also write per-strategy risk envelope to `strategy_risk_profile`.

**Idempotency key:** `stage3.{score}:hash(fingerprint+inputs_version)`.

**Failure mode:** Per-strategy failures isolated; stage emits `pipeline_logs` row, does not halt batch.

---

## STAGE 4 — Re-rank

**Goal:** Produce a fresh survivor pool ordering using newly computed composite scores.

**Operations:**
1. Compute global rank using target weighting (e.g., `0.3*quality + 0.3*evidence + 0.2*market + 0.2*trust` — load from target config).
2. Update `survivor_registry` with `rank`, `pf_ratio`, and `tier` (elite / candidate / probation).
3. Update `strategy_lifecycle.flags.in_survivor_pool` based on new tier.

**Idempotency key:** `stage4:hash(all_composite_scores)`.

---

## STAGE 5 — Re-match (Prop Firm Matching)

**Goal:** For each survivor × each firm, produce a `strategy_challenge_match` record.

**Operations:**
1. Use `prop_firm_rules` snapshots (3 firms imported).
2. Use `strategy_pass_analysis` from Stage 3.5.
3. Use `firm_challenge_types` (regenerated from target's seed if empty).
4. Write `strategy_challenge_match` rows.

**Idempotency key:** `stage5:hash(strategy_hash+firm_slug+rule_version)`.

---

## STAGE 6 — Re-portfolio

**Goal:** Regenerate portfolios from imported survivors.

**Operations:**
1. Run `portfolio_builder_engine` over elite-tier survivors.
2. Write `portfolio_builder_runs`.
3. Compute portfolio-level correlation matrix and diversification metrics.

**Concurrency:** Single-writer per portfolio_id (avoids 409s).

**Idempotency key:** `stage6:hash(elite_survivor_set)`.

---

## STAGE 7 — Re-masterbot

**Goal:** Generate Master Bot families from portfolio-clear survivors.

**Operations:**
1. Group survivors by family (style, asset class, correlation cluster).
2. Generate Master Bot artifacts (target's master_bot_engine).
3. Emit `master_bot_id` on each member `strategy_library` doc.
4. Write `master_bot_registry`.

**Concurrency:** Throttled (LLM-heavy); honor target's `LLM_TASK_*` rate caps.

**Idempotency key:** `stage7:hash(family_id+member_set)`.

---

## STAGE 8 — Marketplace-Ready Gating

**Goal:** Identify which Master Bots pass the marketplace readiness gate.

**Operations:**
1. Apply target's marketplace gate: deploy_score ≥ threshold, OOS pass count ≥ N, prop-firm clearance ≥ M, equity curve smoothness criterion.
2. Set `strategy_library.marketplace_status ∈ {pending, listed, blocked}`.
3. Generate `strategy_dossier` for listed entries (LLM description, evidence summary).
4. Write `marketplace_listings`.

**Idempotency key:** `stage8:hash(master_bot_id+gate_version)`.

---

## CROSS-STAGE INVARIANTS

1. **No source rows are modified destructively.** Derived fields are *added*; original fields untouched.
2. **All stages are idempotent.** Re-running stage N must produce identical outputs given identical inputs.
3. **Per-stage checkpoints recorded.** `post_import_checkpoints` collection allows resume.
4. **Pipeline does NOT auto-enable autonomy.** `AUTONOMOUS_DISCOVERY_ENABLED`, `auto_replace_enabled`, `AutoMutationRunner`, ingestion loops remain OFF until operator decree.
5. **LLM concurrency caps.** Stages 3.1, 7, 8 (LLM-touching) honor a global semaphore — default 4 concurrent calls per provider; exponential backoff with jitter on 429.
6. **Mutation write protection.** Stage 6/7 write paths use upsert with `strategy_hash` + a monotonic `revision` field to prevent the 409 conflicts observed pre-migration.

---

## RECOMMENDED EXECUTION ORDER ON TARGET

1. Import (mongorestore + file payloads per DOWNLOAD_MANIFEST.md).
2. Run Stage 0 (validation).
3. Operator confirms; run Stages 1 → 4 serially with checkpoints inspected.
4. Operator confirms; run Stages 5 → 6 serially.
5. Operator confirms; run Stage 7 (LLM-heavy, slow).
6. Operator decrees; run Stage 8.
7. **Only after Stage 8 success** does operator consider enabling autonomous loops on target.

---

## FAILURE / ROLLBACK SEMANTICS

- Any stage failure halts the pipeline at that boundary; previous stages remain valid.
- Rollback = drop derived collections (`strategy_pass_analysis`, `strategy_challenge_match`, `portfolio_builder_runs`, `master_bot_registry`, `marketplace_listings`, derived `*_score` fields) and re-run from the failed stage.
- Imported Tier-1 collections are NEVER touched by rollback.

---

## OBSERVABILITY

Every stage emits:
- `pipeline_logs` rows with `stage`, `status`, `duration_sec`, `error`
- A summary row in `post_import_checkpoints`
- (Optional) Webhook alert via existing alert_engine on failure

This gives operators a full provenance chain from imported survivor → marketplace listing.
