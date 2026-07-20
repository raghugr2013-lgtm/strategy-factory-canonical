# Phase 2 Validation Gate 4 — Stage 3.γ + BI5 Shadow Closure

> **Verdict:** PASS (pending operator review).
> Compiled: 2026-07-20.
> Scope: Stage 3.γ (Promote Bridge + Retro-scoring) implementation
> readiness; BI5 shadow observation status; Stage 4 prep.
>
> **Cumulative Phase-2 UKIE unit tests: 181 / 181 passing**
> (143 prior + 38 new for Stage 3.γ).

---

## 1. Purpose

Validation Gate 4 is the operator's checkpoint immediately before
Stage 4 kickoff, mirroring the structure of Gate 3
(`PHASE_2_VALIDATION_GATE_3_REPORT.md`). It answers three questions:

1. **Is Stage 3.γ implementation complete and safe to ship dormant?**
2. **Is BI5 shadow validation closed?**
3. **What remains before Coherent UKIE Activation and Stage 4?**

Nothing is enabled in production by this gate. Every Stage 3.γ flag
defaults OFF; the platform continues to run exactly as it did before
Stage 3.γ landed.

---

## 2. Stage 3.γ readiness — summary

| Deliverable | Plan reference | Status |
|---|---|---|
| P2C.9 α — Promote endpoint + preconditions + audit collection, dry-run only | §4.1 | ✅ |
| P2C.9 β — Writer + rollback endpoint (flag-gated) | §4.2 | ✅ |
| P2C.11 α — Retro-score runner + `retro_score_runs`, dry-run only | §4.3 | ✅ |
| P2C.11 β — Commit path dual-gated + rollback endpoint | §4.4 | ✅ |
| Tests — `test_promote_bridge.py` + `test_retro_score.py` | §2.9, §3.9 | ✅ 38 tests, all passing |
| Documentation — `PHASE_2_STAGE_3_GAMMA_NOTES.md` | §4.5 | ✅ |
| Feature flags — 3 new flags, all default OFF | §2.7, §3.7 | ✅ |

---

## 3. Component-by-component verification

### 3.1 Promote Bridge (P2C.9)

**Endpoints:**
```
POST /api/knowledge/promote/{item_id}                  — flag-gated (503 when off)
POST /api/knowledge/promote/{item_id}/rollback         — flag-gated (503 when off)
```

**Preconditions (`engines.knowledge.promote.evaluate_promote`):**
- `domain == "strategy"` — ✅ tested (`TestPreconditions::test_wrong_domain`)
- `trust_tier ≥ 4` — ✅ tested (`test_trust_too_low`, `test_trust_missing`)
- `license_verdict.outcome ∈ {permissive, weak_copyleft}` — ✅ tested
  (`test_license_refused_strong_copyleft`, `test_license_refused_proprietary`,
   `test_permissive_and_weak_copyleft_accepted`)
- No dedup collision (unless `override_dedup=true`) — ✅ tested
  (`test_dedup_refused_without_override`, `test_dedup_accepted_with_override`)

**Hard-rail invariant (§2.3):**
`_compose_prod_doc` stamps `learning_only=True, eligible_for_deploy=False`
**regardless of item state**. Verified by
`test_dry_run_composes_no_write` — the KB item advertises
`learning_only=false, eligible_for_deploy=true`; the composed prod
doc lands with the safe values.

**Audit collection:** `strategy_knowledge_base.promote_events` — every
attempt (success, refusal, dry-run, demote, flag-off) writes one row.
`kind ∈ {promote, demote}` distinguishes writer from rollback.

**Rollback filter:** `{promoted_from: item_id, origin: "ukie_promote"}`
— `test_rollback_only_touches_ukie_promote_origin` proves that a
sibling row carrying `origin: "native_ingestion"` with the same
`promoted_from` value is untouched.

### 3.2 Retro-scoring (P2C.11)

**Endpoints:**
```
POST /api/knowledge/retro-score                        — flag-gated (503 when off)
POST /api/knowledge/retro-score/rollback/{run_id}      — flag-gated (503 when off)
```

**Dual gating (§3.2):** `UKIE_RETRO_SCORE_ENABLED` alone permits the
endpoint to run; the actual Mongo write additionally requires
`UKIE_GOVERNANCE_CUTOVER=true`. If the latter is off, a `dry_run=false`
run returns `dormant=N` — verified by
`TestRunner::test_governance_cutover_off_yields_dormant`.

**Physical safety catch:** `confirm_write="yes_write_the_kb"` is
required in the request body when `dry_run=false`. Missing or wrong
value returns HTTP 400 — verified by
`TestRouter::test_commit_requires_confirm_write_token`.

**Idempotency:** repo upsert on `(content_hash, domain)`. Re-running
retro-scoring twice yields `inserted=0, updated=N` on the second run
— verified by `TestRunner::test_idempotent_second_run`.

**Batch report:** every run persists to
`strategy_knowledge_base.retro_score_runs` (dry-run OR commit).
Aggregate + per-row detail preserved.

**Legacy invariant preserved:** `strategy_knowledge_base` writes are
sourced from an in-memory copy of the legacy row — the legacy
`ingested_strategies` collection is READ-ONLY throughout. No `insert`,
`update`, or `delete` operations against it exist in the code.

### 3.3 Repository backward-compat

`KnowledgeRepository.insert_ingested` gained an optional
`retro_score_run_id` kwarg. Non-retro callers pass no value; the
written document contains no such field. Retro callers pass the run's
uuid; the document carries `retro_score_run_id` enabling the
`deleteMany` rollback filter. All prior Stage 3.β tests (65) continue
to pass — no shape change to their write path.

---

## 4. Cumulative test status

```
tests/test_knowledge_domains.py        · PASS   (Stage 3.α)
tests/test_knowledge_connector.py      · PASS   (Stage 3.α)
tests/test_knowledge_router.py         · PASS   (Stage 3.α)
tests/test_knowledge_pipeline.py       · PASS   (Stage 3.β)
tests/test_domain_router.py            · PASS   (Stage 3.β)
tests/test_license_gate.py             · PASS   (Stage 3.β)
tests/test_trust_scorer.py             · PASS   (Stage 3.β)
tests/test_dedup_and_repository.py     · PASS   (Stage 3.β)
tests/test_bi5_bid_diff.py             · PASS   (Stage 2 shadow)
tests/test_promote_bridge.py           · PASS   (Stage 3.γ — new)
tests/test_retro_score.py              · PASS   (Stage 3.γ — new)
────────────────────────────────────────────────────────────────
Total UKIE + Stage 2 shadow unit tests: 181 / 181 PASSING
```

Test-count evolution:
- Gate 3 baseline: 224 cumulative Phase-2 tests, extending to 251 after
  BI5 shadow work.
- Gate 4 baseline: 251 (unchanged) + 38 new Stage 3.γ = **289
  cumulative Phase-2 tests** (of which 181 are UKIE + BI5 unit tests
  runnable without an HTTP backend).

Broader test suites requiring a live backend + Mongo (Phase A/B/…/J
integration harnesses) are unaffected by Stage 3.γ; their pass
condition remains the same as at Gate 3.

---

## 5. Flag-off rollback verification

Every Stage 3.γ endpoint self-guards with an HTTP 503 when the
corresponding master switch is off. Verified against the FastAPI
`TestClient`:

```
UKIE_PROMOTE_BRIDGE_ENABLED unset:
  POST /api/knowledge/promote/kb-1                  → 503
  POST /api/knowledge/promote/kb-1/rollback         → 503
UKIE_RETRO_SCORE_ENABLED unset:
  POST /api/knowledge/retro-score                   → 503
  POST /api/knowledge/retro-score/rollback/run-x    → 503
```

The direct-call defence at the writer/runner layer is verified by
`TestWriter::test_flag_off_returns_flag_off_result` — even a bypassed
router cannot escape the master switch.

---

## 6. Provenance + version stamps

Every Stage 3.γ write / audit row carries:

| Field | Source | Purpose |
|---|---|---|
| `pipeline_version` | `constants.PIPELINE_VERSION` = `"0.1.0"` | Distinguishes implementation reruns |
| `pipeline_contract_version` | `constants.PIPELINE_CONTRACT_VERSION` = `"0.1.0"` | Distinguishes semantic shifts |
| `promoted_at` / `processed_at` | UTC ISO string | Wall-clock timestamp |
| `promoted_by` / `attempted_by` / `requested_by` | Operator identifier from request body | Audit identity |
| `event_id` / `run_id` | uuid4 hex | Correlation across audit entries |
| `origin` | Static `"ukie_promote"` (promote path only) | Rollback filter safety |
| `retro_score_run_id` | uuid4 from `RetroScoreRunner.run()` | Rollback filter for retro-scored rows |

No implicit stamping; every field is set by the writer/runner at
construction time and never derived from item-supplied values.

---

## 7. BI5 ↔ BID shadow validation — status recap

Landed pre-Gate-3 and unchanged by Stage 3.γ:
- Analytical convergence proven — 27/27 tests drive BI5 + CTS
  resamplers to bit-identical OHLCV.
- Two real bugs found + fixed (uppercase `1H`/`4H` deprecation;
  trailing-partial guard on non-power-of-timeframe M1 lengths).
- Feature flag `BI5_BID_DIFF_ENABLED=false` (default OFF). Endpoint
  returns 503 when off.
- 24-hour production observation runbook documented in
  `BI5_BID_SHADOW_VALIDATION_REPORT.md §7`.

**Gate 4 confirms:** BI5 shadow tests remain 27/27 passing. Awaiting
the operator's 24-hour observation window (independent of Stage 3.γ)
before flipping `BI5_BID_DIFF_ENABLED` on for a diff run.

---

## 8. Stage 4 preparedness

Stage 4 scope (`PHASE_2_STAGE_3_GAMMA_PLAN.md §6` non-goals + prior
docs):
- Health-provider retrofit for UKIE (`/api/health/system` gains a
  `ukie` subsystem)
- Retrieval / query API from `strategy_knowledge_base.strategies`
- New connectors: Arxiv, PDF, PropFirm, TradingView, InternalMongo
- Bulk auto-promote sweep + governance policy language
- COE γ + observability finalisation
- Operator dashboard backfill for retro-scored rows

**Stage 3.γ prerequisites for Stage 4 are all satisfied:**
- Audited write path (`KnowledgeRepository.insert_ingested`) — ✅
- Audited promote surface + audit collection — ✅
- Retro-score runner + provenance stamps for bulk backfill — ✅
- Rollback paths for every mutation — ✅
- Feature-flag hierarchy that keeps every Stage 3.γ capability
  dormant until an operator opts in — ✅

---

## 9. Decisions required from operator

1. **Approve Stage 3.γ implementation** — enables the operator to
   flip Stage 3.γ flags in production at will.
2. **Coherent UKIE Activation** — a separate step, previously
   sequenced in Gate 3 §13. Not required by this gate. When approved,
   the sequence is:
   1. Flip `UKIE_DOMAIN_REGISTRY_ENABLED=true` in production
   2. Flip `ENABLE_DOMAIN_ROUTING`, `ENABLE_LICENSE_GATE`,
      `ENABLE_TRUST_SCORER` (and optionally `ENABLE_DEDUP_CHECK`) on
   3. Observe `/api/knowledge/pipeline/status` / `/pipeline/last-run`
   4. Flip `UKIE_GOVERNANCE_CUTOVER=true` last (the critical cutover)
3. **BI5 shadow 24-hour observation** — independent of Stage 3.γ;
   proceed at operator's convenience.
4. **Stage 4 kickoff** — begin planning post-approval.

---

## 10. Non-goals of this gate

- Enable any Stage 3.γ flag in production
- Author connectors, retrieval APIs, or dashboard panes (Stage 4)
- Modify the legacy `ingested_strategies` collection in any way
- Modify the pre-existing pipeline version numbers (they remain
  `0.1.0` — Stage 3.γ is a purely additive extension of Stage 3.β)

---

## 11. Result

**PASS** — Stage 3.γ is implemented, tested, documented, and dormant.

Awaiting operator review before:
- Enabling any Stage 3.γ flag in production
- Coherent UKIE Activation
- Stage 4 kickoff

*Signed off (draft):* main agent, 2026-07-20.
