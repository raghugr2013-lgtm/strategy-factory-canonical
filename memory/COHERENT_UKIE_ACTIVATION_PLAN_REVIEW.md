# Coherent UKIE Activation Plan — Operator Readiness Review

> **Status:** Independent critical review — READ-ONLY assessment.
> Reviewed document: `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN.md` (v1 draft, 384 lines).
> Reviewer: main agent (fork), acting as independent second pair of eyes.
> Date: 2026-07-20.
> Backend Feature Freeze respected: **no code changes, no flag flips, no plan edits made during this review.**

---

## 0. TL;DR verdict

**Verdict: APPROVED-WITH-CONDITIONS.**

The plan is structurally sound: phases sequence writers behind readers, every phase has explicit success/abort/rollback, and the plan honours the Freeze doctrine (all Stage-4 surfaces remain OFF until an operator flips them).

Twelve conditions (§10) should be addressed before Phase A begins. Six are documentation-only tweaks to the plan (5–15 minutes each); six are freeze-permitted operational wiring items that are already listed as "deferred to activation" in `BACKEND_FEATURE_FREEZE.md §10`. Nothing found in the review requires lifting the freeze or reworking the architecture.

---

## 1. Grounding — what I cross-referenced

To keep this review evidence-based, I spot-checked plan claims against the codebase:

| Claim in plan | Evidence in code | Status |
|---|---|---|
| 34 Stage-4 flags exist | `grep` found all named flags (34 explicit + 12 Stage-3 pipeline flags = 46 total) | ✅ verified |
| `UKIE_RANKING_V2_ENABLED` (C.4) | `engines/knowledge/ranking.py:41` | ✅ verified |
| `POST /api/knowledge/query` (C.1) | `engines/knowledge/ukie_gamma_router.py:63` | ✅ verified |
| `POST /api/knowledge/dry-run` (D.6) | `engines/knowledge/router.py:165` | ✅ verified |
| `POST /api/knowledge/promote/{id}/rollback` (§5.9) | `engines/knowledge/promote_router.py:79` | ✅ verified |
| `POST /api/knowledge/retro-score/rollback/{run_id}` (§5.9) | `engines/knowledge/retro_score_router.py:94` | ✅ verified |
| `GET /api/knowledge/health` (A.1) | `engines/knowledge/observability_router.py:77` | ✅ verified |
| 6× `ALERT_*_ENABLED` (Phase E) | Present as **YAML labels** in `docs/observability/alertmanager_p4d_rules.yaml`, **NOT** wired as env-consumed flags in Python | ⚠ ambiguity — see §5.6 |
| Aggregator wiring for UKIE + 5 retrofits (A.9) | `engines/health/router.py` uses `collect_all()` — no auto-inclusion of `get_ukie_health_provider()` or 5 retrofit providers | ⚠ deferred wiring — see §5.2 |
| `engines/db_indexes.py` exists | Yes — but it does **not** currently declare TTL specs for `workload_dead_letter`, `lifecycle_events`, `knowledge_endorsement_events`, `knowledge_contradiction_events`, `connector_events` | ⚠ deferred wiring — see §5.3 |
| "323/323 unit tests passing" (precondition §1) | Full-suite run today: `439 passed, 33 failed, 98 errors` — every failure/error is a pre-existing HTTP-integration or legacy suite (`backend_test.py`, `test_strategy_route_split.py`, `test_knowledge_layer.py`, `test_migration.py`, `test_v1_2_0_alpha2_phase_*.py`, `test_provider_hint.py`), unrelated to Stage-3/4 code. The Stage-4 unit test subset (`323`) is a curated selection, not the full suite. | ⚠ ambiguity — see §5.1 |

Everything else in the plan mapped 1:1 to the codebase.

---

## 2. Completeness

**Strengths**
- All ten Phase-A read-only endpoints named with the exact route and expected response shape.
- Every phase (A–E) has: activation sequence, monitoring checkpoints, success criteria, abort criteria, rollback.
- The plan explicitly enumerates the two most consequential cutovers (D.7 governance cutover, D.15 promote-bridge activation) and puts them behind Phase A/B/C stabilisation.
- Post-activation roadmap (§7) is aligned with `BACKEND_FEATURE_FREEZE.md §11`.
- Operator sign-off block is present.

**Gaps**
- **G1.** No named owner/on-call rotation format. §1 says "operator + on-call identified" but doesn't specify hand-off protocol (who signs, who receives paging alerts, escalation ladder).
- **G2.** No explicit **"Phase 0 — baseline snapshot"** step. Before Phase A begins, someone needs to capture `platform_health_score`, `/api/coe/metrics`, `/api/coe/state`, Mongo collection counts, so that "no regression" (§2.3) is measurable.
- **G3.** No **communication cadence** during 24 h observation windows (hourly? on-anomaly only? scheduled check-ins?).
- **G4.** Phase B references `Emergent LLM key` availability (§1) but doesn't say which of the eight COE components actually exercise LLM traffic. In practice only `COE_PROVIDER_AWARE_ADMISSION` needs the key path healthy (to observe breaker states) — the other seven can be verified with synthetic fixtures. This should be explicit so activation doesn't stall on a missing key it doesn't need.
- **G5.** Phase D.9 (`internal_mongo` connector) assumes a `db_getter` is wired but does not specify **which database / collection** the connector reads from. This is one of the "deferred to activation" wiring items and needs a concrete answer (source DB name, source collection name, source schema mapping) before Phase D begins.
- **G6.** No **preview vs production** distinction. The plan reads as if it could be executed against either. A one-line preamble specifying "this plan is executed against the VPS production pod, not the preview" (or the reverse) would remove ambiguity.

---

## 3. Internal consistency

**Strengths**
- Flag names in the plan match the code (verified above).
- Phase ordering respects dependencies: observability → resilience → retrieval → writers → alerts.
- The two data-preservation invariants (`ingested_strategies` READ-ONLY, production `strategies` write only via promote bridge) are called out consistently in D.6 and D.8.

**Inconsistencies**
- **I1.** §2.1 A.9 "Add UKIE + 5 retrofits to `/api/health/system` composition" is described as a **step**, not a **flag flip**. But the phase is otherwise entirely flag-driven. This wiring is a one-time code change; it should either be relabelled as an **operational-wiring precondition** (moved to §1) or the plan should acknowledge it's a code deploy step gated by `COE_HEALTH_CONTRACT_ENABLED=true` (which is itself missing from the flag list — see I2).
- **I2.** `COE_HEALTH_CONTRACT_ENABLED` is not listed anywhere in the plan. Yet A.9 (aggregator composition) and every subsystem `GET /api/health/{name}` endpoint depend on that flag being ON (`engines/health/router.py:38-46`). Either the plan should list it as a precondition (assumed already on in production) or it should appear as step A.0.
- **I3.** Phase A.10 says "Provision `docs/observability/grafana_p4d_dashboard.json`" — provisioning is an infrastructure task, not a flag flip. Same category as I1: should be re-labelled as ops-wiring, or moved to §1.
- **I4.** §4.1 C.2 says "Apply TTL indexes" as a **plan step**, but the referenced code (`engines/db_indexes.py`) currently does **not** contain TTL specs for the Stage-4 collections. So C.2 has two dependencies:
  1. Code change: add specs to `db_indexes.py` (freeze-permitted operational wiring).
  2. Runtime: startup hook re-executes on next boot.
  The plan reads as if C.2 is a single-shot operation. It's actually a two-step deploy.
- **I5.** §5.2 D.7 says the governance cutover produces "first real writes to `strategy_knowledge_base`. Monitor for 24 h with connectors STILL disabled — writes should be zero." This is correct in intent but subtle: writes should be zero **because no connector is enabled**, not because the flag is doing anything unusual. Newcomers reading D.7 could interpret it as "the cutover flag by itself produces writes worth monitoring", which it doesn't. A one-line clarification would prevent misinterpretation.
- **I6.** §5.6 monitoring checkpoint says "Zero writes to legacy `ingested_strategies` (verify via Mongo audit)". Elsewhere the plan (D.6 fixture) and Freeze doc both call `ingested_strategies` **READ-ONLY**. Both phrasings are correct but the plan uses two verbs for the same invariant ("legacy read-only" vs "zero writes"). Standardise to one form.

---

## 4. Sequencing

**Strengths**
- Read-before-write ordering (Phase A → B → C → D → E) is correct and safest.
- Retry (B.1) precedes dead-letter (B.2), which precedes work recovery (B.3) — matches dependency graph in `PHASE_4_P4B_COE_GAMMA_NOTES.md §6`.
- Stage-3 pipeline flags (D.1–D.5) precede the governance cutover (D.7), matching Stage 3.β/γ design.
- Promote-bridge (D.15) requires the cutover (D.7) plus at least one connector producing rows (D.8–D.13). The ordering respects this.

**Sequencing concerns**
- **SEQ1.** Phase B (COE γ) is placed **before** Phase C (UKIE retrieval). Rationale is unclear — retrieval is safer (read-only against an empty KB) than resilience (which touches live workload paths). Reversing B and C would extend the "no writer active" window from 4 phases to 5. **However**, the current ordering is defensible if the operator wants COE γ battle-tested against pre-existing pre-Stage-4 workload traffic. The plan should state that rationale, not leave it implicit.
- **SEQ2.** The 24 h observation window is stated as "adjustable per operator judgement, never below 4 h without documented reason" (§0). But between B.1 → B.8, that's **8 × 24 h = 8 days** of activation for COE γ alone. Total wall clock for A–E is at least (10 + 8 + 6 + ~10 + 6) × 24 h ≈ **40 days**. The operator should know this up front. Consider adding a "total expected activation duration" line to §1.
- **SEQ3.** D.15 (promote-bridge, dry-run first) precedes D.17 (retro-score, dry-run first). Both write to legacy `ingested_strategies` via a retro path, which is READ-ONLY. Need to verify retro-score writes only to `strategy_knowledge_base.*` collections, never to legacy — the Freeze doc §3.2 confirms this. But the plan should re-state that invariant explicitly at D.17/D.18, because the plain phrase "backfilling legacy `ingested_strategies`" (§5.5) is ambiguous — the retro-score writes **based on** legacy data, into the **new KB**, without touching legacy. Rephrase to avoid misreading.
- **SEQ4.** Phase E (alerts) is last, meaning during Phases A–D the operator is doing **manual visual monitoring** without paging. If Phase D discovers a latent connector storm, the operator finds out via dashboard eyeball, not an alert. For a 40-day activation, that's a high-cognitive-load ask. Consider armed-but-silent alerts (severity: `notice`) during A–D, with production severity kicking in at Phase E.

---

## 5. Individual dimensions

### 5.1 Preconditions (§1)

- **Issue P1** — "Cumulative unit tests 323/323 passing in preview" is a curated subset. Full-suite run today produced 33 failures + 98 errors, **all** in pre-existing HTTP-integration or legacy test suites unrelated to Stage 3/4 code. This is a documentation ambiguity: the precondition should read "Stage-4 targeted test subset 323/323 passing" or point to a named `pytest -k` selector / marker.
- **Issue P2** — "Grafana + Alertmanager deployed (skeleton configs applied, alerts silent)" is a hard prerequisite that assumes VPS infrastructure exists. If activation happens against the preview pod (per G6), Grafana + Alertmanager are not deployed and this precondition cannot be satisfied. Add a preview vs production tag.
- **Issue P3** — Phase 0 baseline snapshot missing (G2).

### 5.2 Phase A — observability first

- **A.1–A.7 (7 flags flipped one at a time)** — safe. Each endpoint is 503-gated and returns a well-defined dormant shape.
- **A.8** — `/api/knowledge/promote-events`, `/retro-score-runs`, `/connector-events` gated by `UKIE_AUDIT_VISIBILITY_ENABLED`. Verified against `observability_router.py:128-159`. Safe.
- **A.9** — **wiring step, not a flag** (I1). Aggregator (`engines/health/router.py`) currently uses `collect_all()` from `.providers`. To include the `ukie` block + 5 retrofits, `get_ukie_health_provider().snapshot()` must be added to `collect_all()`'s composition or the retrofit providers must be `register`'d at import time. This is the "deferred to activation" wiring item in `BACKEND_FEATURE_FREEZE.md §10`. The plan should explicitly reference the file and function that must change (`engines/health/providers.py` — the `register` interface), so the on-call knows what "add UKIE + 5 retrofits" concretely means. **Freeze-permitted operational wiring, ~30 minutes to author + unit-test.**
- **A.10** — provisioning step (I3). Depends on infrastructure. Same preview-vs-production question as P2.

### 5.3 Phase B — COE γ resilience

- **B.1–B.8** — flag names, wire-ups, and abort thresholds all verified against `PHASE_4_P4B_COE_GAMMA_NOTES.md`. Safe.
- **B.2 dead-letter** — "Apply TTL index on `workload_dead_letter.first_failed_at` (90 d)". Currently `engines/db_indexes.py` does not carry this TTL spec. Adding it is freeze-permitted operational wiring (5 minutes: one TTL_SPEC tuple + reboot).
- **B.4** — `COE_PROVIDER_AWARE_ADMISSION`. Wire-up requires `breaker_state_lookup` connection to `engines.ai_workforce.circuit_breaker`. This IS live code today (used in Phase 1). Should verify the interface signature has not drifted since P4B landed.
- **B.5–B.7** — pure scoring / cap operations. Safe.
- **B.8** — audit sink to `coe_operator_events`. Verify no TTL policy is applied (freeze doc §3.1 recommends 180 d, but does not commit).

### 5.4 Phase C — UKIE γ retrieval

- **C.1** — verified endpoint. Safe.
- **C.2** — "Apply TTL indexes" — same pattern as B.2. Freeze-permitted wiring: 4 TTL_SPEC tuples added to `db_indexes.py` (lifecycle_events / endorsement_events / contradiction_events / connector_events). Prerequisite for C.3.
- **C.3–C.5** — verified endpoints. Safe.
- **C.6** — `promote_policies` collection is documented in Freeze doc §3.2 but does not carry a seed policy. Plan step says "seed a policy in `promote_policies`; evaluate endpoint returns advisory tags". Need: a canonical **example policy JSON** in the plan (or in a companion file under `/app/memory/`) so the operator doesn't have to author one from scratch under time pressure. Freeze-permitted operational documentation.

### 5.5 Phase D — connectors + cutover

Most consequential phase; deserves extra scrutiny.

- **D.1–D.5** — pipeline flags. Verified against `PHASE_2_STAGE_3_BETA_NOTES.md`. Safe.
- **D.6** — dry-run endpoint verified. Safe.
- **D.7** — the cutover. Plan text correct (I5 fix aside). Safe as a flag flip; risk is entirely operator-error on subsequent steps.
- **D.8–D.13** — each connector wire-up. Every one of these is a "deferred network wiring" item from Freeze doc §10. Each needs:
  * Secrets/keys in `.env` (per-connector — `ARXIV_API_KEY`, `PROPFIRM_*`, `INTERNAL_MONGO_BEARER_TOKEN`)
  * Live client instantiation (aiohttp session, PDF fetcher, curated seed list)
  * Per-connector allow-list (spec discipline).
  Plan mentions all of this in passing; a **per-connector activation checklist** as a companion doc would materially reduce cognitive load.
- **D.14** — `UKIE_CONNECTOR_EVENTS_PERSIST_ENABLED`. Wires observer callback to `connector_events` writes. Freeze-permitted wiring.
- **D.15–D.16** — promote-bridge activation with `UKIE_PROMOTE_DRY_RUN=true` first, then per-item dry_run=0. Correct discipline; matches `PHASE_2_STAGE_3_GAMMA_NOTES.md §7`. Safe.
- **D.17–D.18** — retro-scoring one-shot. Wording ambiguity (SEQ3 above) needs a rewrite: the confirm-token `"yes_write_the_kb"` must be spelled EXACTLY (it's a discriminator) — matches `retro_score_router.py`.

### 5.6 Phase E — alerts

- **Critical ambiguity ⚠**. The plan describes flipping `ALERT_PLATFORM_HEALTH_ENABLED=true` etc. "in `.env`". Investigation shows these strings currently exist **only** as YAML labels inside `alertmanager_p4d_rules.yaml`. The YAML comment states they are "checked by the alert delivery layer, NOT by Prometheus itself". No such delivery layer exists in the current backend. Consequently:
  * If activation targets Alertmanager: the rule fires from `expr`, and the `ALERT_*_ENABLED` labels are decorative. Setting them in `.env` does nothing.
  * If activation targets a custom delivery layer: that layer must be authored (this would violate the freeze — it's a new feature).
  * The current-state honest answer: Phase E rules will fire based on `expr` matches only, regardless of env vars, once Alertmanager is deployed.
  This needs a decision: either
   1. Alertmanager's built-in silence/inhibit mechanism replaces the env flags (recommended, freeze-clean), OR
   2. A tiny delivery-layer proxy is authored (violates freeze), OR
   3. The env flag names are removed from the plan and replaced with the actual Alertmanager silence commands.

### 5.7 Success criteria (per phase)

- Numeric where sensible (§2.3, §3.3, §4.3, §5.7). Good.
- One softness — §2.3 "Zero regression in pre-existing `platform_health_score`" — should specify measurement window (5 min p50? p95 over the whole 24 h?). Currently ambiguous.
- §5.7 "Each connector's `health.state` transitions to `healthy`" — good. But no per-connector row-count success threshold is set. If Arxiv connector produces 1 row in 24 h, is that healthy or failing? The plan should either (a) accept "healthy state + zero errors" as sufficient, or (b) set a per-connector minimum throughput target.

### 5.8 Abort criteria

- Numeric across the board. Good.
- §5.8 "Any write to legacy `ingested_strategies` observed" is a hard invariant break — should also include an immediate escalation directive ("halt activation, page operator, do NOT continue to next phase"). Currently reads as "just an abort trigger" — the correct response is stronger than a rollback.
- §5.8 "Any production `strategies` row without `origin='ukie_promote'`" — same invariant class; same escalation ask.

### 5.9 Rollback logic

- Per-phase rollback SLA of ≤ 60 s is realistic (flag flip + supervisor restart).
- Data rollback per component listed (§5.9, §7 of Freeze doc). Good.
- **Missing:** rollback ORDERING guidance. If two flags need rolling back mid-phase, is order important? For B.4 (`PROVIDER_AWARE_ADMISSION`) + B.7 (`BUDGET_HARD_CAP`), rolling back budget first while admission is still gating could produce a spike. Order-sensitive rollbacks should be documented.
- **Missing:** "nuclear rollback" already exists in Freeze doc §7 — a cross-reference from the activation plan §8 to that section would be helpful.

### 5.10 Monitoring checkpoints

- Every phase names concrete metrics/endpoints. Good.
- Missing: **sampling frequency**. "During 24 h window: `/api/health/system` continues returning 200" — sampled every 30 s? Every 5 min? Same for latency p95 checks. The plan gives thresholds without cadences.
- Missing: **who owns which dashboard panel**. In a 40-day activation, on-call rotation matters. Not the plan's job to schedule rotations, but a one-line placeholder ("dashboards owner: <team>") would prompt the right ops conversation.

### 5.11 Operational risks not called out

- **R1.** Mongo hot-path index build. TTL indexes are declared with `background=True` in the existing `db_indexes.py`, so they're safe. But `create_index` on collections that already contain rows can take non-trivial time. Currently the Stage-4 collections are empty, so first activation is cheap — but if activation is retried after some rows land, index-build time becomes non-trivial. Document that TTL indexes should be applied BEFORE first writes to a collection, not after.
- **R2.** `COE_HEALTH_CONTRACT_ENABLED` bootstrap dependency (I2). If this flag is off in production, half of Phase A is dead-air. Verify the state of this flag on the target pod as part of Phase 0 baseline.
- **R3.** `.env` drift. In a 40-day activation with dozens of flag flips, `.env` is edited many times. Recommend: version-control `.env` per phase completion (checkpoint files) so any accidental flip can be diffed. Not a blocker; a hygiene practice.
- **R4.** Emergent LLM key expiry. If activation spans 30–40 days, the key may need re-issuance. No mitigation guidance in the plan.
- **R5.** Preview pod database is transient. If activation is executed in preview and the pod restarts, all Stage-4 audit collections vanish. Clarify preview vs production early (G6).

### 5.12 Assumptions that should be made explicit

The plan makes several implicit assumptions:

1. **`COE_HEALTH_CONTRACT_ENABLED=true` in the target environment.** (I2)
2. **Grafana + Alertmanager are already deployed** on the target environment. (P2)
3. **Aggregator wiring** (`engines/health/providers.py` composes UKIE + 5 retrofits into `collect_all()`) happens BEFORE Phase A.9. (I1, §5.2)
4. **TTL specs** in `db_indexes.py` are extended to cover 5 Stage-4 audit collections BEFORE Phase C.2 / D. (I4, §5.4)
5. **Per-connector secrets/wire-ups** are landed BEFORE the corresponding D.9–D.13 flag flip. (§5.5)
6. **Retro-score's `confirm_write` token is exactly `"yes_write_the_kb"`** — matches code, but only fair to spell out in the plan.
7. **`.env` is the authoritative flag surface.** No process-manager overrides, no k8s ConfigMap override, no `os.environ` mutations in test setup.
8. **The target environment has one backend replica.** Multi-replica activation requires all replicas to see the same `.env` at the same time — the plan implicitly assumes single-node.
9. **`Emergent LLM key`** is optional at boot (per Freeze doc §6) but required for Phase B.4 verification. Confirm live in Phase 0 baseline.
10. **The Freeze remains in effect** during the entire 40-day activation. If a bug fix is required (permitted per Freeze §11), it must not introduce new endpoints or new flags.

---

## 6. Findings summary

| # | Type | Where | Severity | Fix effort |
|---|------|-------|----------|------------|
| G1 | Gap | §1 preconditions | LOW | 5 min doc |
| G2 | Gap | §1 preconditions | MEDIUM | 5 min doc |
| G3 | Gap | §1 preconditions | LOW | 5 min doc |
| G4 | Gap | Phase B | LOW | 5 min doc |
| G5 | Gap | Phase D.9 | MEDIUM | 20 min doc |
| G6 | Gap | Cover / §1 | HIGH | 2 min doc |
| I1 | Consistency | Phase A.9 | MEDIUM | 5 min doc |
| I2 | Consistency | Phase A / §1 | MEDIUM | 5 min doc |
| I3 | Consistency | Phase A.10 | LOW | 5 min doc |
| I4 | Consistency | Phase C.2 | MEDIUM | 5 min doc |
| I5 | Consistency | Phase D.7 | LOW | 2 min doc |
| I6 | Consistency | Phase D | LOW | 2 min doc |
| SEQ1 | Sequencing | Phase B vs C | LOW | 5 min doc (rationale line) |
| SEQ2 | Sequencing | §1 | MEDIUM | 5 min doc (total duration) |
| SEQ3 | Sequencing | Phase D.17/18 | MEDIUM | 5 min doc (rewrite paragraph) |
| SEQ4 | Sequencing | Phase E | LOW | Optional — armed-but-silent alerts |
| P1 | Precondition | §1 | LOW | 5 min doc (rename "323/323") |
| P2 | Precondition | §1 | HIGH | 2 min doc (preview vs prod tag) |
| §5.2 wiring | Ops wiring | Phase A.9 | HIGH | 30 min code (freeze-permitted) |
| §5.4 TTL | Ops wiring | Phase B.2, C.2 | MEDIUM | 15 min code (freeze-permitted) |
| §5.5 seed policy | Ops doc | Phase C.6 | LOW | 15 min doc |
| §5.6 alert flags | Ambiguity | Phase E | HIGH | Decision required — see §5.6 |
| §5.10 sampling | Gap | All phases | LOW | 5 min doc |
| R1–R5 | Risks | Cross-cutting | LOW-MED | 15 min doc (risk register section) |

**Highs (block Phase A start):** G6, P2, §5.2 wiring, §5.6 alert flags decision.
**Mediums (should fix before Phase A):** G2, G5, I1, I2, I4, SEQ2, SEQ3, §5.4 TTL, R1–R2.
**Lows (recommend, not blocking):** everything else.

---

## 7. Recommendations (grouped, so operator can decide in batches)

### Batch 1 — Documentation-only edits to the plan (≈45 min total, freeze-clean)
Fixes G1–G6, I1–I6, SEQ1–SEQ3, P1–P2, §5.5 seed policy, §5.10 sampling, R1–R5.

* Add a preamble line: **"Target environment: <VPS production pod | preview pod>. If preview, Grafana + Alertmanager provisioning steps become no-ops."** (G6, P2)
* Add a **Phase 0 baseline snapshot** section listing 8–10 exact curl invocations + Mongo counts to capture before Phase A. (G2, R2)
* Add an **"Assumptions"** section covering the ten items in §5.12 above.
* Rename precondition line "323/323" to "Stage-4 targeted test subset 323/323". (P1)
* Add total expected activation duration (§SEQ2) as a headline number in §1.
* Rewrite D.7, D.17–D.18 paragraphs to remove the `ingested_strategies` phrasing ambiguity (I5, I6, SEQ3).
* Add rationale line for B-before-C ordering (SEQ1).
* Add **monitoring sampling cadence** as a subsection to each phase (§5.10).
* Add short **risk register** section covering R1–R5.
* Add a **canonical `promote_policies` seed** as an appendix (§5.5).

### Batch 2 — Freeze-permitted operational wiring (≈2 h total)
Not new features; explicitly listed as "deferred to activation" in Freeze doc §10.

* **W1.** Extend `engines/db_indexes.py` with 5 new TTL_SPECS covering `workload_dead_letter`, `lifecycle_events`, `knowledge_endorsement_events`, `knowledge_contradiction_events`, `connector_events`. Idempotent, safe (§5.4).
* **W2.** Wire `get_ukie_health_provider()` and the 5 retrofit providers into `engines/health/providers.py` so `collect_all()` includes them when the corresponding `*_HEALTH_PROVIDER_ENABLED` flag is on. Single edit + unit test (§5.2).
* **W3.** Add a preview-vs-production toggle to the plan preamble that documents which "provisioning" steps are no-ops.

### Batch 3 — Decision required (§5.6 alerts)
Operator to choose:
* **(a)** Accept that `ALERT_*_ENABLED` env vars are decorative and rely on Alertmanager's native silence/inhibit mechanism. Preferred; freeze-clean.
* **(b)** Author a delivery-layer proxy that consumes those env vars. **Requires lifting the freeze** — not recommended.
* **(c)** Remove the env flag names from Phase E of the plan and replace them with the actual Alertmanager silence commands / rule-inclusion labels.

### Batch 4 — Optional polish (defer if time-pressed)
* Rollback ordering guidance for B.4↔B.7 (§5.9).
* Armed-but-silent alerts during Phases A–D (SEQ4).
* Per-connector activation checklist as a companion doc (§5.5).
* `.env` per-phase checkpoint files (R3).

---

## 8. Do the improvements justify updating the plan?

**Yes, but selectively.**

- Batches 1 + 3 should be applied before Phase A begins — they clarify ambiguities the operator will hit within the first two hours of activation.
- Batch 2 (operational wiring) is genuinely required — the plan cannot be executed as written without it. Freeze-permitted per Freeze doc §10.
- Batch 4 is polish; skip if the operator wants to start Phase A within the week.

**Effort estimate to reach "APPROVED (no conditions)":** ≈3 h of documentation + code work (Batches 1, 2, 3) by one operator.

---

## 9. What was NOT changed during this review

- `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN.md` — unchanged (0 edits).
- `/app/memory/BACKEND_FEATURE_FREEZE.md` — unchanged.
- Any code file under `/app/backend/` — unchanged.
- Any feature flag — no flips, no toggles, no `.env` modifications.
- Any deployed service — no restarts.
- Any Mongo document — no reads outside of code inspection, no writes.

Backend Feature Freeze fully respected.

---

*End of independent review.*
*Prepared for operator decision on whether to apply Batch 1, 2, and/or 3.*
