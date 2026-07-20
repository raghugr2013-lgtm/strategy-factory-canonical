# Phase 2 Stage 3.γ — Implementation Notes

> **Status:** IMPLEMENTED, tested, dormant.
> All feature flags default OFF. Zero production behaviour change.
> Landed: 2026-07-20.
> Preceded by: `PHASE_2_STAGE_3_GAMMA_PLAN.md` (operator-approved).
> Cumulative Phase-2 UKIE unit tests: **181 / 181 passing**
> (143 prior Stage 3.α+β+BI5 + 38 new Stage 3.γ).

---

## 1. What landed

Both components of the operator-approved Stage 3.γ plan shipped in
one increment, in the sequence prescribed by
`PHASE_2_STAGE_3_GAMMA_PLAN.md §4`:

### 1.1 P2C.9 — Promote Bridge

The one-way, audited path from `strategy_knowledge_base.strategies`
(UKIE-KB) → production `strategies` collection.

**New endpoints (all admin-gated + flag-gated):**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/knowledge/promote/{item_id}` | Promote one KB item to production |
| `POST` | `/api/knowledge/promote/{item_id}/rollback` | Per-item demote (idempotent) |

**Files added:**
- `backend/legacy/engines/knowledge/promote.py` — pure precondition
  checker (`evaluate_promote(item, opts, prod_dedup_id) → PromoteVerdict`)
- `backend/legacy/engines/knowledge/promote_bridge.py` — writer + audit
  (`PromoteBridge.promote_item(...)` / `.demote_item(...)`)
- `backend/legacy/engines/knowledge/promote_router.py` — FastAPI endpoints
- `backend/tests/test_promote_bridge.py` — 24 unit tests

**Preconditions (all must hold — plan §2.2, enforced by
`evaluate_promote`):**
1. Item exists and `domain == "strategy"`.
2. `trust_tier ≥ 4` (T4 Curated / T5 Authoritative).
3. `license_verdict.outcome ∈ {permissive, weak_copyleft}`.
4. No production `strategies` row shares the same `content_hash`,
   unless `override_dedup=true` (audited).

**Every refusal returns a specific `refuse_reason` string** (audit
signal). Verbatim list:
`item_not_found`, `item_malformed`, `wrong_domain`,
`trust_tier_too_low`, `license_refused`, `dedup_collision`.

**Hard rails re-stamped at the writer (§2.3):**
Even if the KB row carries `learning_only=false,
eligible_for_deploy=true` (mischievous data), the production row lands
with the safe values. A future Phase-3 approval loop is the only path
that flips `eligible_for_deploy`.

**Audit trail:** every attempt writes one row to
`strategy_knowledge_base.promote_events` — success OR refusal.
Fields: `event_id`, `attempted_at`, `attempted_by`, `item_id`,
`resolved` ∈ {`promoted`, `refused`, `dry_run`, `demoted`,
`already_demoted`, `flag_off`}, `refuse_reason`, `prod_strategy_id`,
`override_dedup`, `dry_run`, `reason`, `verdict`, `pipeline_version`,
`pipeline_contract_version`, `kind` ∈ {`promote`, `demote`}.

**Feature flags:**

| Flag | Default | Effect ON |
|---|---|---|
| `UKIE_PROMOTE_BRIDGE_ENABLED` | `false` | Endpoints served (else HTTP 503); writer callable |
| `UKIE_PROMOTE_DRY_RUN`        | `true`  | Default dry-run when `_ENABLED` on. Per-request override: `?dry_run=0` (commit) / `?dry_run=1` (force dry) |

### 1.2 P2C.11 — Retro-scoring

One-off idempotent backfill of legacy `ingested_strategies` rows into
`strategy_knowledge_base.strategies` via the Stage-3.β pipeline —
**without mutating the legacy collection at all**.

**New endpoints (admin + flag-gated):**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/knowledge/retro-score` | Run a retro-scoring pass (dry-run default) |
| `POST` | `/api/knowledge/retro-score/rollback/{run_id}` | Per-run rollback (idempotent) |

**Files added:**
- `backend/legacy/engines/knowledge/retro_score.py` — batch runner
  (`RetroScoreRunner.run(...)` / `.rollback(run_id, ...)`) +
  `legacy_row_to_item(row)` mapper
- `backend/legacy/engines/knowledge/retro_score_router.py` — endpoints
- `backend/tests/test_retro_score.py` — 14 unit tests

**Files modified:**
- `backend/legacy/engines/knowledge/repository.py` — added optional
  `retro_score_run_id` kwarg to `insert_ingested(...)`. Backward-compat:
  when None (non-retro writes), no field is added to the document; when
  supplied, the doc carries `retro_score_run_id` enabling per-run
  rollback via a single `deleteMany` filter.
- `backend/legacy/engines/knowledge/__init__.py` — exports for the new
  surface.
- `backend/legacy/engines/knowledge/router.py` — mounts the two new
  sub-routers on the same `/api/knowledge` prefix.

**Legacy → canonical mapping (plan §3.2)** — implemented by
`legacy_row_to_item`. Missing `content_hash` is recomputed as SHA-256
over the utf-8 encoded strategy text; missing `domain` defaults to
`STRATEGY`; missing `connector_name` defaults to `"github"`.

**Two-flag gating on write (§3.2, §3.7):**
1. `UKIE_RETRO_SCORE_ENABLED=true` — this router
2. `UKIE_GOVERNANCE_CUTOVER=true` — repository layer (Stage 3.β)

If (2) is off, a `dry_run=false` request still runs the full pipeline
but the repository returns `status="dormant"` for every row —
retro-scoring cannot bypass the governance cutover by design.

**Physical safety catch:** `confirm_write="yes_write_the_kb"` in the
request body is required when `dry_run=false`. Muscle-memory
protection layered on top of the two flags.

**Idempotency:** repo upsert on `(content_hash, domain)`. Re-running
retro-scoring yields `status="updated"` on the second run — never a
duplicate insert. Verified by
`test_retro_score.py::TestRunner::test_idempotent_second_run`.

**Batch report:** every run persists a `RetroScoreSummary` row into
`strategy_knowledge_base.retro_score_runs` — dry-run OR commit.
Fields: `run_id`, `started_at`, `finished_at`, `dry_run`,
`requested_by`, `input_row_count`, `inserted`, `updated`, `rejected`,
`dormant`, `errored`, `trust_tier_counts`, `license_outcome_counts`,
`domain_counts`, `pipeline_version`, `pipeline_contract_version`,
`per_row_outcomes`, and (on rollback) an appended `rollbacks[]` entry.

### 1.3 Repository modification (backward-compatible)

Signature change:
```
KnowledgeRepository.insert_ingested(
    item,
    *,
    license_verdict=None,
    trust_score=None,
    retro_score_run_id=None,     # NEW — optional, default None
) -> InsertResult
```

Non-retro callers pass no `retro_score_run_id`; the written document
does NOT carry the field (no shape change to Stage 3.β writes).
Retro callers pass the run's uuid; the document carries
`retro_score_run_id=<uuid>` and can be removed by a single
`deleteMany({retro_score_run_id: <uuid>})`.

---

## 2. Feature-flag matrix

| Flag | Default | Purpose | Component |
|---|---|---|---|
| `UKIE_DOMAIN_REGISTRY_ENABLED` | `false` | Stage 3.α — exposes `/api/knowledge/*` foundation | Prerequisite |
| `ENABLE_DOMAIN_ROUTING`        | `false` | Stage 3.β stage flag | Prerequisite |
| `ENABLE_DEDUP_CHECK`           | `false` | Stage 3.β stage flag | Prerequisite |
| `ENABLE_LICENSE_GATE`          | `false` | Stage 3.β stage flag | Prerequisite |
| `ENABLE_TRUST_SCORER`          | `false` | Stage 3.β stage flag | Prerequisite |
| `UKIE_GOVERNANCE_CUTOVER`      | `false` | **Critical cutover** — gates Mongo writes to `strategy_knowledge_base` | Prerequisite (also required by retro-score) |
| **`UKIE_PROMOTE_BRIDGE_ENABLED`** | `false` | **Stage 3.γ** — mounts promote endpoints; HTTP 503 when off | Promote Bridge |
| **`UKIE_PROMOTE_DRY_RUN`**        | `true`  | **Stage 3.γ** — default dry-run when `_ENABLED` on | Promote Bridge |
| **`UKIE_RETRO_SCORE_ENABLED`**    | `false` | **Stage 3.γ** — mounts retro-score endpoints; HTTP 503 when off | Retro-scoring |

**Every Stage 3.γ flag defaults OFF.** Zero behaviour change until an
operator flips a flag.

---

## 3. Rollback SLA (plan §5.2)

| Rollback path | Mechanism | Target SLA | Status |
|---|---|---|---|
| Individual promote demote | `POST /api/knowledge/promote/{item_id}/rollback` — deletes prod `strategies` rows where `promoted_from == item_id AND origin == "ukie_promote"` | ~30 s | ✅ Tested |
| Nuclear promote rollback | `db.strategies.deleteMany({origin:"ukie_promote"})` — manual Mongo op | ~seconds | ✅ Filter targeted |
| Retro-score per-run rollback | `POST /api/knowledge/retro-score/rollback/{run_id}` — deletes KB rows where `retro_score_run_id == run_id` (sweeps every domain sub-collection) | ~30 s per batch | ✅ Tested |
| Nuclear retro-score rollback | `db.strategy_knowledge_base.strategies.deleteMany({retro_score_run_id: {$ne: null}})` — manual Mongo op | ~seconds | ✅ Filter targeted |
| Flag-flip rollback of the whole surface | Set `UKIE_PROMOTE_BRIDGE_ENABLED=false` / `UKIE_RETRO_SCORE_ENABLED=false` + supervisor restart | ~30 s | ✅ Every endpoint self-guards |

All continue to meet the 60-s platform SLA
(`PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §3 invariant #2`).

---

## 4. Test plan coverage (plan §2.9, §3.9)

**Promote Bridge — 24 unit tests, all passing:**

| Plan test | Test file location |
|---|---|
| §2.9.1 Precondition suite | `TestPreconditions::test_item_not_found`, `test_wrong_domain`, `test_trust_too_low`, `test_trust_missing`, `test_license_refused_strong_copyleft`, `test_license_refused_proprietary`, `test_permissive_and_weak_copyleft_accepted`, `test_dedup_refused_without_override` |
| §2.9.2 Hard-rail enforcement | `TestWriter::test_dry_run_composes_no_write` (item carries unsafe flags → prod doc lands safe) |
| §2.9.3 Idempotency | `TestWriter::test_idempotent_second_promote_rejected` |
| §2.9.4 Dedup-override audit | `TestPreconditions::test_dedup_accepted_with_override` + `TestWriter::test_dedup_override_writes_and_audits` |
| §2.9.5 Rollback | `TestRollback::test_rollback_deletes_and_audits`, `test_rollback_only_touches_ukie_promote_origin` |
| §2.9.6 Empty / malformed item_id | `TestPreconditions::test_malformed_item` + `TestRouter::test_empty_item_id_returns_400` |
| §2.9.7 Endpoint 503 when flag off | `TestRouter::test_all_promote_endpoints_503_when_flag_off` |
| §2.9.8 Dry-run | `TestWriter::test_dry_run_composes_no_write` (composed doc returned, no write) + `TestRouter::test_promote_dry_run_via_endpoint` |
| — Flag-off writer refusal (defence-in-depth) | `TestWriter::test_flag_off_returns_flag_off_result` |
| — Commit path via endpoint | `TestRouter::test_promote_commit_via_endpoint` |

**Retro-scoring — 14 unit tests, all passing:**

| Plan test | Test file location |
|---|---|
| §3.9.1 Empty legacy collection | `TestRunner::test_empty_legacy_produces_zero_summary` |
| §3.9.2 Populated legacy — dry-run | `TestRunner::test_populated_dry_run_no_writes` |
| §3.9.3 Commit run — run_id stamped | `TestRunner::test_commit_writes_and_stamps_run_id` |
| §3.9.4 Idempotency | `TestRunner::test_idempotent_second_run` |
| §3.9.5 `confirm_write` guard | `TestRouter::test_commit_requires_confirm_write_token`, `test_commit_accepts_correct_token` |
| §3.9.6 Rollback | `TestRollback::test_rollback_deletes_and_is_idempotent` |
| §3.9.7 Malformed rows | `TestRunner::test_malformed_row_recorded_as_errored` + `TestMapping::test_missing_text_returns_none` |
| §3.9.8 Governance cutover off | `TestRunner::test_governance_cutover_off_yields_dormant` |
| — Mapping — valid row / missing hash | `TestMapping::test_valid_row_produces_item`, `test_missing_content_hash_recomputed` |
| — Router 503 when flag off | `TestRouter::test_endpoints_503_when_flag_off` |
| — Router dry-run default | `TestRouter::test_dry_run_default` |

**Cumulative UKIE unit-test count: 181 / 181 passing.**

---

## 5. Live-verification checklist (operator, pre-production)

Preview pod, `UKIE_DOMAIN_REGISTRY_ENABLED=true` (only) — all Stage 3.γ
flags OFF:

- [ ] `POST /api/knowledge/promote/kb-1` → HTTP 503
      `detail=UKIE_PROMOTE_BRIDGE_ENABLED is off`
- [ ] `POST /api/knowledge/promote/kb-1/rollback` → HTTP 503
- [ ] `POST /api/knowledge/retro-score` → HTTP 503
      `detail=UKIE_RETRO_SCORE_ENABLED is off`
- [ ] `POST /api/knowledge/retro-score/rollback/run-x` → HTTP 503
- [ ] `/api/health/system` unchanged: `platform_score=100 ·
      [coe, vie, cts]`

With `UKIE_PROMOTE_BRIDGE_ENABLED=true`, `UKIE_PROMOTE_DRY_RUN=true`:
- [ ] `POST /api/knowledge/promote/<real-kb-id>` returns
      `{"resolved":"dry_run","composed_doc":{...}}` — no prod write
- [ ] Audit event in `strategy_knowledge_base.promote_events`

With `UKIE_RETRO_SCORE_ENABLED=true`, `UKIE_GOVERNANCE_CUTOVER=false`:
- [ ] `POST /api/knowledge/retro-score {"dry_run":false,
      "confirm_write":"yes_write_the_kb"}` returns
      `{"dormant":<N>,"inserted":0}` — no KB write (repository dormant)

With BOTH `UKIE_RETRO_SCORE_ENABLED=true` AND
`UKIE_GOVERNANCE_CUTOVER=true`:
- [ ] `POST /api/knowledge/retro-score {"dry_run":true}` → summary
      shows `dormant=<N>`, no KB write
- [ ] Enable commit: `{"dry_run":false,
      "confirm_write":"yes_write_the_kb"}` → summary shows
      `inserted=<N>`; KB rows carry `retro_score_run_id`
- [ ] Re-run same body → `updated=<N>`, `inserted=0` (idempotent)
- [ ] `POST /api/knowledge/retro-score/rollback/<run_id>` →
      `{"resolved":"rolled_back","deleted_count":<N>}`

---

## 6. Non-goals honoured (plan §6)

Explicitly NOT in Stage 3.γ — deferred to Stage 4:

- Health-provider retrofit for UKIE
- Retrieval / query API from `strategy_knowledge_base.strategies`
- New connectors (Arxiv, PDF, PropFirm, TradingView, InternalMongo)
- Bulk auto-promote sweep
- Governance policy language beyond `T4+/permissive/dedup`
- Operator dashboard backfill for retro-scored rows

---

## 7. Risks — post-implementation review

Every planning-time risk from `PHASE_2_STAGE_3_GAMMA_PLAN.md §7`
remains at LOW severity after implementation. Additional risk
observations from the build:

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Promote bridge writes prod `strategies` with `eligible_for_deploy=true` | LOW | Hard rails re-stamped at `PromoteBridge._compose_prod_doc`; verified by `TestWriter::test_dry_run_composes_no_write` where item carries `learning_only=false, eligible_for_deploy=true` in the KB row |
| R2 | Retro-scoring duplicates rows on second run | LOW | Repo upsert is idempotent on `(content_hash, domain)`; verified by `TestRunner::test_idempotent_second_run` |
| R3 | Rollback deletes non-UKIE prod `strategies` rows | LOW | Rollback filter is `{promoted_from: item_id, origin: "ukie_promote"}` — verified by `TestRollback::test_rollback_only_touches_ukie_promote_origin` |
| R4 | `override_dedup=true` produces unaudited duplicates | LOW | Every override writes an audit event with `override_dedup=true` (verified by `TestWriter::test_dedup_override_writes_and_audits`) |
| R5 | `confirm_write` string typed from muscle memory | LOW | Guard is one layer; `UKIE_RETRO_SCORE_ENABLED=false` is the other; both must be intentional |

**No CRITICAL or HIGH after implementation.**

---

## 8. Post-Stage-3.γ next steps

Per operator directive: Stage 3.γ is complete and dormant. Awaiting
review before any of the following:

1. **Coherent UKIE Activation** (Gate 3 §13 / PRD line 321-325) —
   flip `UKIE_DOMAIN_REGISTRY_ENABLED` + stage flags in production.
2. **Stage 4 kickoff** — connector fleet + COE γ + observability
   finalisation.

Neither will begin until this Stage-3.γ implementation is reviewed
and approved.

---

*Reviewed against:*
- `PHASE_2_STAGE_3_GAMMA_PLAN.md` (§§2, 3, 4, 5, 6, 7)
- `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §7 P2C.9, P2C.11`
- `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §7 (governance rails), §10.3`
- `PHASE_2_VALIDATION_GATE_3_REPORT.md` (post-Gate-3 sequence)

*Status:* **IMPLEMENTED — awaiting operator review + Validation Gate 4.**
