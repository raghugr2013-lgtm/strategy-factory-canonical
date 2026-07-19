# Phase 2 Stage 3.γ — Implementation Plan
### Promote Bridge (P2C.9) + Retro-scoring (P2C.11)

> **Status:** planning only — awaiting operator review + approval.
> No implementation until this plan is signed off.
> Assembled: 2026-02-19.
> Precondition: Validation Gate 3 approved (2026-02-19).

---

## 0. Guiding principles (unchanged from Stages 1 – 3.β)

1. **Feature-flagged.** Every new capability defaults OFF.
2. **Dry-run first.** Both P2C.9 and P2C.11 ship a dry-run path
   ahead of any Mongo write, mirroring the Stage-3.β discipline.
3. **Idempotent.** Re-running any admin action produces the same
   state — no accidental duplicates, no orphan rows.
4. **Full audit trail.** Every mutation records provenance
   (`origin`, `promoted_by`, `pipeline_version`,
   `pipeline_contract_version`, `processed_at`) so the operator can
   trace any row back to a single decision.
5. **Rollback strategy.** Every promoted / retro-scored row has an
   explicit, tested demotion / removal path.
6. **No mutation of legacy data.** Retro-scoring writes to the
   isolated `strategy_knowledge_base` DB; the legacy
   `ingested_strategies` collection is READ-ONLY.
7. **No production activation** until this plan is reviewed and
   approved, and until the coherent UKIE activation sequence
   completes (§ post-Gate-3 sequence in `PHASE_2_VALIDATION_GATE_3_REPORT.md §13`).

---

## 1. Scope

Two components, planned separately, deliverable in one Stage-3.γ
increment:

- **P2C.9 — Promote Bridge.** The one-way audited path from
  `strategy_knowledge_base.strategies` → production `strategies`.
  Individual promotion; no bulk sweep.
- **P2C.11 — Retro-scoring.** One-off backfill of the ~55 rows in
  the legacy `ingested_strategies` collection so they carry the
  Stage-3.β envelope (`domain=STRATEGY`, `trust_tier`, `license`,
  version stamps). Writes to `strategy_knowledge_base.strategies`;
  never mutates legacy rows.

**Not in scope for Stage 3.γ:**
- New connectors (Stage 4)
- Retrieval / query API from the knowledge DB (Stage 4)
- Health-provider retrofit for UKIE (Stage 4)
- Bulk auto-promote sweep (deliberate — every promote is per-item)

---

## 2. P2C.9 — Promote Bridge

### 2.1 Contract

A single audited HTTP endpoint that promotes ONE item from
`strategy_knowledge_base.strategies` (the UKIE-owned KB) into the
production `strategies` collection.

```
POST /api/knowledge/promote/{item_id}
  auth:  admin (existing dependency)
  body: {
    "reason":               "operator-provided free-text",
    "requested_by":         "operator identifier",
    "override_dedup":       false                          (optional; default false)
  }
```

### 2.2 Preconditions (all must hold)

- The item exists in `strategy_knowledge_base.strategies` and its
  `domain == "strategy"`.
- `trust_tier ≥ 4` (T4 Curated or T5 Authoritative).
- `license_verdict.outcome ∈ {"permissive", "weak_copyleft"}` —
  `strong_copyleft` and `proprietary` are refused.
- No existing production `strategies` row shares the same
  `content_hash` (unless `override_dedup=true` supplied — even then,
  we log an `admin_override` audit reason).
- `UKIE_PROMOTE_BRIDGE_ENABLED=true` (default OFF).

Every precondition returns HTTP 4xx with a specific `reason`.

### 2.3 Write shape

A promoted row lands in production `strategies` with:

```
strategy_id:            <derived from item.content_hash>
strategy_text:          <item.content_bytes decoded to utf-8>
pair, timeframe:        <parsed from item.extras where possible; else null>
source:                 "ukie_promote"
origin:                 "ukie_promote"
learning_only:          true            # HARD RAIL — even promoted rows
eligible_for_deploy:    false           # HARD RAIL — human loop still required
promoted_from:          item._id
promoted_by:            body.requested_by
promoted_at:            <UTC ISO>
promoted_reason:        body.reason
promote_pipeline_version:          <PIPELINE_VERSION>
promote_pipeline_contract_version: <PIPELINE_CONTRACT_VERSION>
trust_tier:             <copied>
license:                <copied>
```

The two hard rails (`learning_only`, `eligible_for_deploy`) are
stamped in the writer regardless of the item's own state. A future
Phase-3 approval loop is the ONLY path that flips
`eligible_for_deploy=true`.

### 2.4 Audit trail

Every promote — whether it succeeds or is refused — writes one row
to a new `strategy_knowledge_base.promote_events` collection:

```
event_id:               <uuid4>
attempted_at:           <UTC ISO>
attempted_by:           body.requested_by
item_id:                <requested>
resolved:               "promoted" | "refused"
refuse_reason:          <str or null>
prod_strategy_id:       <populated when resolved="promoted", else null>
override_dedup:         <bool>
pipeline_version:       <PIPELINE_VERSION>
pipeline_contract_version: <PIPELINE_CONTRACT_VERSION>
```

Every attempt is retained; refusal reasons are the primary audit
signal.

### 2.5 Rollback

Per-item demotion via `POST /api/knowledge/promote/{item_id}/rollback`:

- Requires the same admin auth.
- Deletes the `strategies` row with matching
  `promoted_from == item_id`. If multiple exist (edge case:
  duplicate promotes), demotes ALL of them; audit event records the
  count.
- Writes a `demoted_event` row with `resolved="demoted"` and reason.
- Idempotent: repeat calls after all copies are removed return
  `resolved="already_demoted", count=0`.
- Never mutates the UKIE-KB row (source of truth remains intact).

### 2.6 Files to add / modify

New:
- `engines/knowledge/promote.py` — pure precondition checker
  `evaluate_promote(item, opts) → PromoteVerdict`
- `engines/knowledge/promote_bridge.py` — the writer + audit
  `promote_item(...)` / `demote_item(...)` + `PromoteEvent` shape
- `engines/knowledge/promote_router.py` — endpoint (extension of
  `router.py`)
- `tests/test_promote_bridge.py` — dry-run, refusal, hard-rail
  enforcement, audit-event shape, rollback, idempotency,
  `override_dedup` audit stamp

Modified:
- `engines/knowledge/__init__.py` — export the new surface
- `engines/knowledge/router.py` — mount `promote_router` (kept in
  the same router prefix)

### 2.7 Feature flags

| Flag | Default | Effect ON |
|---|---|---|
| `UKIE_PROMOTE_BRIDGE_ENABLED` | `false` | Endpoint mounted; preconditions run; on satisfaction writes to production `strategies` |
| `UKIE_PROMOTE_DRY_RUN` | `true` | When set alongside `_ENABLED`, endpoints evaluate preconditions + build the target document but do NOT commit; response returns `resolved="dry_run"` |

### 2.8 Dry-run

Same three-input pattern as Stage-3.β's dry-run:
- `POST /api/knowledge/promote/{item_id}?dry_run=1` — evaluates
  preconditions + composes the target `strategies` shape + returns
  it in the response body without any Mongo write. Useful for
  operator preview before the actual mutation.

### 2.9 Test plan

1. **Precondition suite** — every one of §2.2's conditions produces
   a specific refusal reason.
2. **Hard-rail enforcement** — even a mischievous UKIE row with
   `learning_only=false, eligible_for_deploy=true` produces a
   production row with the safe values.
3. **Idempotency** — promoting the same item twice: the second
   attempt is refused with `reason="already_promoted"` and produces
   an audit event.
4. **Dedup-override audit** — `override_dedup=true` produces an
   audit event stamped with `override_dedup=true` even on success.
5. **Rollback** — demotes cleanly; re-demote is idempotent; audit
   count is correct.
6. **Empty / malformed item_id** — HTTP 400 with clear reason.
7. **Endpoint 503 when flag off** — every route.
8. **Dry-run** — no Mongo write; response body has the composed
   document; `resolved="dry_run"`.

### 2.10 Rollback plan (Stage-3.γ level)

- Any promoted rows are per-item; each carries `promoted_from` and
  `origin="ukie_promote"`. The operator can `db.strategies.deleteMany({origin:"ukie_promote"})`
  as a nuclear rollback that cleanly removes ALL Stage-3.γ writes
  from production `strategies` — this is the platform-wide undo.
- On flag flip (`UKIE_PROMOTE_BRIDGE_ENABLED=false`), the endpoints
  return HTTP 503 and no future promotes can occur. Existing rows
  remain in place (they carry their audit provenance).

---

## 3. P2C.11 — Retro-scoring

### 3.1 Contract

A one-off idempotent script (also exposed as an admin endpoint) that
walks the ~55 rows currently in the legacy `ingested_strategies`
collection and produces canonical Stage-3.β
`RawKnowledgeItem`-shaped rows in
`strategy_knowledge_base.strategies` — WITHOUT mutating the legacy
collection at all.

```
POST /api/knowledge/retro-score
  auth:  admin
  body: {
    "dry_run":       true,          # default true — the caller MUST opt in to a real run
    "batch_size":    100,           # optional; default 100
    "confirm_write": "yes_write_the_kb"    # required when dry_run=false
  }
```

The `confirm_write` field is a physical safety catch — a
copy-paste-only string that prevents an accidental live-run.

### 3.2 Mapping

Each legacy row → one canonical `strategy_knowledge_base.strategies`
row via the full Stage-3.β pipeline **in dry-run mode**, then
committed if `dry_run=false`. Mapping details:

| Legacy field | Canonical field |
|---|---|
| `strategy_text` | `content_bytes` (utf-8 encoded) |
| `pair`, `timeframe` | `extras.pair`, `extras.timeframe` |
| `source_url` | `source_url` |
| `source_ref` | `source_ref` (else `source_url` if absent) |
| `created_at` | `fetched_at` |
| `content_hash` | recomputed via SHA-256 over `content_bytes` |
| Missing `domain` | inferred as `STRATEGY` |
| Missing `connector_name` | defaults to `"github"` (legacy origin) |

Each row runs through:
- `domain_router` → `RoutingDecision`
- `dedup_check` → `DedupResult`
- `license_gate` → `LicenseVerdict`
- `trust_scorer` → `TrustScore`
- `KnowledgeRepository.insert_ingested(...)` (with
  `UKIE_GOVERNANCE_CUTOVER` gating the actual write; retro-scoring
  MUST honour it)

**Retro-scoring is NOT gated by `UKIE_RETRO_SCORE_ENABLED` alone.**
An actual write also requires `UKIE_GOVERNANCE_CUTOVER=true`.
Rationale: retro-scoring is a special case of the normal pipeline
write path; it must not bypass the governance cutover.

### 3.3 Idempotency

- Repo upsert is keyed on `(content_hash, domain)`. Running
  retro-scoring twice yields `status="updated"` on the second run,
  never a duplicate insert.
- The script emits a summary of `inserted / updated / rejected /
  dormant / errored` counts so the operator can diff runs.

### 3.4 Batch report

Every retro-scoring run produces a `RetroScoreSummary` row in a new
`strategy_knowledge_base.retro_score_runs` collection:

```
run_id:                <uuid4>
started_at, finished_at
dry_run:               <bool>
requested_by
input_row_count
inserted, updated, rejected, dormant, errored
trust_tier_counts:     { T1..T5 counts }
license_outcome_counts
pipeline_version, pipeline_contract_version
```

### 3.5 Rollback

- `POST /api/knowledge/retro-score/rollback/{run_id}` — deletes
  rows in `strategy_knowledge_base.strategies` where
  `retro_score_run_id == run_id`. Idempotent; audit-event stamped.
- Global escape: `db.strategy_knowledge_base.strategies.deleteMany({
  retro_score_run_id: {$ne: null} })` removes ALL retro-scored rows.

### 3.6 Files to add / modify

New:
- `engines/knowledge/retro_score.py` — the batch runner
  `run_retro_score(dry_run, batch_size) → RetroScoreSummary`
- `engines/knowledge/retro_score_router.py` — endpoints (mounted via
  the existing knowledge router)
- `tests/test_retro_score.py` — mapping correctness; idempotency;
  dry-run vs commit; rollback; batch summary shape;
  `confirm_write` guard

Modified:
- `engines/knowledge/__init__.py` — exports
- `engines/knowledge/router.py` — mount retro-score endpoints
- `engines/knowledge/repository.py` — add optional
  `retro_score_run_id` field to write path (opt-in kwarg; default
  None; no shape change to non-retro writes)

### 3.7 Feature flags

| Flag | Default | Effect ON |
|---|---|---|
| `UKIE_RETRO_SCORE_ENABLED` | `false` | Endpoint mounted; `run_retro_score(...)` callable |
| `UKIE_GOVERNANCE_CUTOVER` | `false` (existing) | ALSO required for any real write |

### 3.8 Dry-run

Default mode. `POST /api/knowledge/retro-score` with default body
runs the pipeline in shadow mode, reports counts, and produces a
`retro_score_runs` row with `dry_run=true`. Zero writes to
`strategy_knowledge_base.strategies`.

### 3.9 Test plan

1. **Empty legacy collection** → run completes cleanly, all counts 0.
2. **Populated legacy collection (stub Mongo)** → dry-run produces
   expected `RetroScoreSummary`, no writes.
3. **Commit run** → each row in `strategy_knowledge_base.strategies`
   carries `retro_score_run_id`, `pipeline_version`,
   `pipeline_contract_version`.
4. **Idempotency** — second run returns `inserted=0, updated=N`.
5. **`confirm_write` guard** — HTTP 400 when `dry_run=false` but the
   string is missing or wrong.
6. **Rollback** — deletes the run's rows cleanly; second rollback
   is idempotent.
7. **Malformed legacy rows** — a row missing `strategy_text` is
   recorded in `errored`, not silently skipped.
8. **Governance cutover off** — real run returns `dormant=N` and
   writes NOTHING (mirrors Stage-3.β pipeline semantics).

### 3.10 Rollback plan (Stage-3.γ level)

- Every retro-scored row carries `retro_score_run_id`. Global
  rollback via the `deleteMany` filter above.
- Flag flip (`UKIE_RETRO_SCORE_ENABLED=false`) prevents future runs;
  existing retro-scored rows remain (with audit provenance).

---

## 4. Sequenced deliverables (planning only — no implementation)

If approved, the implementation order would be:

1. **P2C.9 α**: promote endpoint + preconditions + audit event
   collection, `dry_run` only. Feature flag off.
2. **P2C.9 β**: writer path (behind `UKIE_PROMOTE_BRIDGE_ENABLED`);
   rollback endpoint.
3. **P2C.11 α**: retro-score runner + `retro_score_runs` collection,
   `dry_run` only. Feature flag off.
4. **P2C.11 β**: commit path (behind `UKIE_RETRO_SCORE_ENABLED` +
   `UKIE_GOVERNANCE_CUTOVER`); rollback endpoint.
5. **Documentation**: `PHASE_2_STAGE_3_GAMMA_NOTES.md` (post-impl).
6. **Validation Gate 4**: covers Stage 3.γ + BI5 shadow observation
   closure + prep for Stage 4 (which contains the remaining
   connector fleet + COE γ + observability finalisation).

Each step ships behind flags. Each step lands with pytest coverage.
Backend regression is required to remain 100% clean across every
step.

---

## 5. Cross-cutting requirements

### 5.1 Backward compatibility

- Legacy `ingested_strategies` collection: **untouched** — Stage 3.γ
  only READS it. No fields added; no rows updated; no rows deleted.
- Legacy `strategies` collection: **written only via the promote
  bridge**, with `origin="ukie_promote"` and both hard rails at
  their safe values. Existing rows are unaffected.
- Legacy `strategy_ingestion` code path: **untouched.** UKIE runs
  alongside; the coherent activation retires the legacy write path
  in a later phase (not Stage 3.γ).

### 5.2 Rollback SLA

- Individual promote → 1 API call (~30 s including audit).
- Bulk promote demotion → 1 `deleteMany` query (~seconds).
- Retro-score run rollback → 1 API call (~30 s per batch of rows).
- Flag flip rollback of the whole surface → supervisor restart (~30 s).

All continue to meet the 60-s platform SLA
(`PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §3 invariant #2`).

### 5.3 Observability

- Promote-events and retro-score-runs are additive read surfaces.
- A future Stage-4 dashboard pane can render `promote_events` +
  `retro_score_runs` counts; no code from Stage 3.γ is required for
  that.

### 5.4 Distribution readiness

- Both P2C.9 and P2C.11 rely on the existing shared Mongo
  connection pool (`engines.db.get_db`). No new client, no new
  driver. Safe under any deployment model chosen for Phase 3.

### 5.5 Hard-rail invariants (preserved)

Every Stage-3.γ write has `learning_only=True`,
`eligible_for_deploy=False`. Even the promote bridge does NOT flip
those bits — human-loop deploy approval remains a separate Phase-3
gate.

---

## 6. Non-goals — deferred to Stage 4

- Health-provider retrofit for UKIE (`/api/health/system` gaining a
  `ukie` subsystem)
- Retrieval / query API from the isolated
  `strategy_knowledge_base.strategies` collection
- New connectors (Arxiv, PDF, PropFirm, TradingView, InternalMongo)
- Bulk promote-sweep (auto-promote all T5 items)
- Governance policy language (rule-based promote acceptance beyond
  the T4+/permissive/dedup gate)
- Backfill for the operator dashboard once retro-scored rows exist

---

## 7. Risks (planning-time)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Promote bridge accidentally writes to production `strategies` with `eligible_for_deploy=true` | LOW | Hard rails re-stamped at the writer regardless of item state; tested |
| R2 | Retro-scoring re-writes and inflates the KB by processing the same legacy row twice | LOW | Repo upsert is idempotent on `(content_hash, domain)` |
| R3 | Rollback endpoints could be misused to bulk-delete production `strategies` | LOW | Rollback filters ONLY match `origin="ukie_promote"` / `retro_score_run_id=...`; legacy-origin rows are untouched by design |
| R4 | `override_dedup=true` on the promote endpoint could permit intentional duplicates | LOW | Every override writes an audit event with `override_dedup=true`; operator retains visibility |
| R5 | The `confirm_write="yes_write_the_kb"` guard could be muscle-memory-typed | LOW | Guard is one layer; the flag `UKIE_RETRO_SCORE_ENABLED=false` is the other; both must be intentional |

**No CRITICAL or HIGH.**

---

## 8. Ask-of-operator

Please confirm the plan is approved before any code lands. If
approved, next-turn output would be:

1. Implement P2C.9 (promote bridge) + tests
2. Implement P2C.11 (retro-scoring) + tests
3. Live-verify all endpoints (flag off → 503; flag on → dry-run
   default; explicit commit only with guards)
4. Produce `PHASE_2_STAGE_3_GAMMA_NOTES.md`
5. Await approval before enabling any Stage-3.γ flags in production

**No code changes will be made until this plan is signed off.**

---

*Reviewed against:*
- `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §7 P2C.9, P2C.11`
- `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §7 (governance rails), §10.3 (Stage 3 backlog)`
- `PHASE_2_STAGE_3_ALPHA_NOTES.md`, `PHASE_2_STAGE_3_BETA_NOTES.md`,
  `PHASE_2_VALIDATION_GATE_3_REPORT.md`

*Status:* **Awaiting operator approval to begin Stage 3.γ implementation.**
