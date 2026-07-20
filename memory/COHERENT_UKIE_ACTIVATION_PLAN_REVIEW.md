# Coherent UKIE Activation Plan — Operator Readiness Review (v2 — post-remediation)

> **Status:** Independent critical review — RESOLVED.
> Reviewed document: `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN.md` (v2 draft, published 2026-07-20).
> Reviewer: main agent (fork), acting as independent second pair of eyes.
> Date: 2026-07-20 (v2 update).
> Backend Feature Freeze respected throughout: no new features, no
> new endpoints, no new flags, no runtime behaviour changes.

---

## 0. TL;DR verdict

**Verdict update: APPROVED (no conditions) after Batches 1, 2, and 3(a).**

The v1 review identified 12 conditions. Batches 1, 2, and 3(a) have
now been applied. Every "High" and "Medium" finding is closed. Two
low-priority items were consciously **deferred** to Batch 4 by
operator direction; they remain acceptable as-is for Phase A start.

Phase A activation may proceed once the operator signs off the v2
activation plan.

---

## 1. What was applied — summary

### Batch 1 — Documentation edits to the activation plan (COMPLETE)
Applied via full rewrite of `COHERENT_UKIE_ACTIVATION_PLAN.md` to v2.
Preserves all sequences from v1 while adding the resolution items
below.

### Batch 2 — Freeze-permitted operational wiring (COMPLETE)
Two code diffs landed, each fully additive, each accompanied by
regression tests.

**W1 — TTL specs in `engines/db_indexes.py`:**
- Extended `TTL_SPECS` with `workload_dead_letter.first_failed_at_dt`
  (90 d) in the main DB.
- Added `KB_TTL_SPECS` list with 4 entries targeting the
  `strategy_knowledge_base` DB: `lifecycle_events.at_dt` (180 d),
  `knowledge_endorsement_events.at_dt` (90 d),
  `knowledge_contradiction_events.at_dt` (365 d),
  `connector_events.at_dt` (180 d).
- Extended `ensure_indexes()` with a best-effort cross-DB loop.
- Followed the existing `audit_log` `*_dt` convention (documented at
  db_indexes.py lines 283–303). Because writers currently emit
  `at` / `first_failed_at` as ISO strings, the new TTL indexes are
  a safe no-op until writers populate the `*_dt` companion field —
  identical discipline to the pre-existing `audit_log` TTL. This is
  called out explicitly in the code comments and in the activation
  plan (§B.2, §C.2, and Risk R6).
- 5 env overrides added:
  `COE_DEAD_LETTER_TTL_DAYS`, `UKIE_LIFECYCLE_EVENTS_TTL_DAYS`,
  `UKIE_ENDORSEMENT_EVENTS_TTL_DAYS`,
  `UKIE_CONTRADICTION_EVENTS_TTL_DAYS`,
  `UKIE_CONNECTOR_EVENTS_TTL_DAYS`.

**W2 — Aggregator wiring:**
- `engines/subsystem_health_router.py`: added
  `_register_aggregator_providers()`, executed at module import. It
  registers 5 sync HealthSnapshot providers (`meta-learning`, `mi`,
  `execution`, `portfolio`, `factory-eval`) with the central
  `engines.health.providers.register_provider()`. Each provider
  reads its `<SUB>_HEALTH_PROVIDER_ENABLED` flag and returns:
  - `empty_snapshot(name)` with `reason="dormant"` when off,
  - `empty_snapshot(name)` with `reason="opted_in"` when on.
- `engines/health/router.py::system_health`: added a post-`collect_all()`
  async block that (a) checks `is_ukie_health_provider_enabled()`,
  (b) awaits `get_ukie_health_provider().snapshot()`, and (c)
  attaches the returned dict under the top-level `"ukie"` key of the
  aggregator response. When the flag is off, the `"ukie"` key is
  **omitted entirely** — preserving the "no shape change to
  pre-Stage-4 consumers" invariant documented in the UKIE health
  provider's own docstring.
- 8 regression tests added in
  `backend/tests/test_activation_wiring_w1_w2.py`, all passing.

### Batch 3 — Phase E mechanism (Option a chosen, COMPLETE)
Native Alertmanager silences.
- Phase E of the plan has been fully rewritten (v2 §9).
- No new backend delivery layer written; freeze respected.
- The YAML `flag: ALERT_<NAME>_ENABLED` labels remain as
  informational tags only.
- Activation mechanism is `amtool silence add/expire`.

### Batch 4 — Deferred (per operator direction)
- Rollback ordering guidance for B.4↔B.7
- Armed-but-silent alerts during Phases A–D
- Per-connector activation checklist as companion doc
- `.env` per-phase checkpoint files

These may be revisited if operational experience during Phase A
suggests they are beneficial.

---

## 2. Finding-by-finding resolution table

| # | Type | Location | v1 severity | Status | Resolution reference |
|---|------|----------|-------------|--------|----------------------|
| G1 | Owner/on-call rotation format | §1 preconditions | LOW | RESOLVED | Plan v2 §3 last-two lines (operator + on-call identified per window; escalation ladder). |
| G2 | Phase 0 baseline snapshot | Preconditions | MEDIUM | RESOLVED | Plan v2 §4 (dedicated section with concrete curl invocations). |
| G3 | Communication cadence | 24 h windows | LOW | PARTIAL | Sampling cadences added per phase (§5.2, §6.2, §7.2, §8.6, §9.3). Named escalation ladder deferred to Batch 4. |
| G4 | LLM key which component needs it | Phase B | LOW | RESOLVED | Plan v2 §6.1 row B.4 explicitly labels this as the only Phase-B component requiring LLM path healthy. |
| G5 | InternalMongo connector DB/collection | D.9 | MEDIUM | RESOLVED | Plan v2 §8.3 row D.9 flags this as the last "deferred to activation" wiring item; operator must confirm source before Phase D begins. |
| G6 | Preview vs production ambiguity | Cover | HIGH | RESOLVED | Plan v2 §0 dedicated section identifies target environment and lists which steps become no-ops in preview. |
| I1 | Phase A.9 is wiring, not a flag | Phase A | MEDIUM | RESOLVED | Wiring landed as W2. Plan v2 §5.1 row A.9 now reads "no flag — verify aggregator wiring lands automatically". |
| I2 | `COE_HEALTH_CONTRACT_ENABLED` missing | Phase A / §1 | MEDIUM | RESOLVED | Plan v2 §3 preconditions explicitly requires it be on; Assumption #1 in §10. |
| I3 | Phase A.10 provisioning vs flag flip | Phase A | LOW | RESOLVED | Plan v2 §5.1 row A.10 explicitly says "production only; no-op in preview". |
| I4 | Phase C.2 TTL as single-shot | Phase C | MEDIUM | RESOLVED | W1 landed. Plan v2 §7.1 row C.2 now reads "no flag — TTL indexes land automatically". |
| I5 | D.7 cutover wording | Phase D | LOW | RESOLVED | Plan v2 §8.2 D.7 rewritten to explain the flag itself unblocks a code path but produces no writes until connectors run. |
| I6 | `ingested_strategies` phrasing | Phase D | LOW | RESOLVED | Plan v2 uses "READ-ONLY" consistently (§8.5, §8.6). |
| SEQ1 | Rationale for B-before-C | Sequencing | LOW | RESOLVED | Plan v2 §6 opens with an explicit rationale paragraph. |
| SEQ2 | Total activation duration | §1 | MEDIUM | RESOLVED | Plan v2 §2 is a dedicated timeline table (~40 days at conservative cadence). |
| SEQ3 | Retro-score wording | D.17/18 | MEDIUM | RESOLVED | Plan v2 §8.5 rewrites the intro paragraph: retro-score READS legacy, WRITES to new KB, does NOT mutate legacy. |
| SEQ4 | Armed-but-silent alerts | Phase E | LOW | DEFERRED (Batch 4) | See §14 for rationale. |
| P1 | "323/323" curated subset | §1 | LOW | RESOLVED | Plan v2 §3 explicitly clarifies: "323/323 refers to this subset — not the full `tests/` directory, which contains pre-existing HTTP-integration suites". |
| P2 | Preview vs production preconditions | §1 | HIGH | RESOLVED | Plan v2 §0 + §3 make target-environment explicit. |
| W1 | TTL specs in db_indexes.py | Ops wiring | HIGH | LANDED | Code diff + 3 regression tests. |
| W2 | Aggregator wiring | Ops wiring | HIGH | LANDED | Code diff + 5 regression tests. |
| Seed policy | Canonical `promote_policies` seed | Phase C.6 | LOW | RESOLVED | Plan v2 Appendix A. |
| Sampling cadence | All phases | LOW | RESOLVED | Plan v2 adds a "Sampling cadence" line to every monitoring section. |
| §5.6 alert flags | Ambiguity | Phase E | HIGH | RESOLVED (Option a) | Plan v2 §9 rewritten around native Alertmanager silences. Freeze clean. |
| R1 | Index build blocks writes | Cross-cutting | LOW | RESOLVED | Plan v2 §11 R1: TTL indexes precede first writes by design. |
| R2 | Health-contract flag drift | Cross-cutting | MED | RESOLVED | Plan v2 §11 R2 + Phase 0 verification. |
| R3 | .env drift | Cross-cutting | MED | RESOLVED | Plan v2 §11 R3: post-phase snapshotting. |
| R4 | LLM key expiry | Cross-cutting | LOW | RESOLVED | Plan v2 §11 R4. |
| R5 | Preview pod transient DB | Cross-cutting | LOW | RESOLVED | Plan v2 §11 R5 + §0 rehearsal semantics. |
| R6 | TTL no-op on ISO fields | Cross-cutting | LOW | RESOLVED | New risk documented explicitly; W1 comments; Assumption implicit. |
| Rollback ordering | B.4↔B.7 | Phase B | LOW | DEFERRED (Batch 4) | See §14. |
| Nuclear-rollback xref | §8 | LOW | RESOLVED | Plan v2 §8.9 last bullet cross-references `BACKEND_FEATURE_FREEZE.md §7`. |
| Per-connector checklist | D | LOW | DEFERRED (Batch 4) | See §14. |
| `.env` checkpoints | Cross-cutting | LOW | DEFERRED (Batch 4) | See §14. |

**Summary counts:** RESOLVED 27 · LANDED 2 · PARTIAL 1 (G3) · DEFERRED 4 (all Batch-4 low-priority polish).

---

## 3. Grounding — evidence for the post-remediation state

I re-ran the same evidence-based checks used in the v1 review:

| Check | Result |
|---|---|
| Plan v2 exists at `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN.md` | ✅ 578 lines (was 384) |
| v2 §0 preview-vs-production preamble present | ✅ |
| v2 §2 timeline table present | ✅ (~40 day headline) |
| v2 §4 Phase 0 baseline section present | ✅ |
| v2 §9 Phase E rewritten around Alertmanager silences | ✅ (no env-flag flip instructions remain) |
| v2 §10 Assumptions section (10 items) | ✅ |
| v2 §11 Risk register (R1–R6) | ✅ |
| v2 Appendix A `promote_policies` seed | ✅ |
| `engines/db_indexes.py` extended with `KB_TTL_SPECS` list | ✅ 4 entries |
| `engines/db_indexes.py` extended with `workload_dead_letter` TTL | ✅ 1 entry |
| `engines/db_indexes.py::ensure_indexes` iterates cross-DB TTLs | ✅ |
| `engines/subsystem_health_router.py::_register_aggregator_providers` present | ✅ auto-invoked at import |
| `engines/health/router.py::system_health` composes `ukie` block async | ✅ (omitted when flag off) |
| Stage-4 test subset passes | ✅ 134/134 (before) → 142/142 (after, incl. 8 new W1+W2 tests) |
| Shape invariant: `ukie` key absent when `UKIE_HEALTH_PROVIDER_ENABLED=false` | ✅ verified via `test_w2_ukie_block_omitted_when_flag_off` |
| Aggregator returns 503 when `COE_HEALTH_CONTRACT_ENABLED=false` | ✅ verified via `test_w2_health_contract_off_returns_503` |
| Retrofit providers dormant when flags off (health=100, state=ok, reason=dormant) | ✅ verified in `test_w2_dormant_snapshot_when_flag_off` |

No regressions introduced. No feature added. No runtime behaviour
change under the default (all-off) configuration.

---

## 4. What remains open (Batch 4, deferred by operator direction)

| Item | Why deferred | When to revisit |
|---|---|---|
| Rollback ordering guidance for B.4↔B.7 | Operator judgement suffices for a single-node backend; ordering matters only under multi-replica contention which is not in scope. | Revisit if multi-replica activation is planned. |
| Armed-but-silent alerts during A–D | Phase E's Alertmanager-native mechanism supports this trivially (silence with future expiry); Batch 3 (a) makes this cheap to add later. | Revisit if Phases A–D observation reveals a latent issue that alerts would have caught earlier. |
| Per-connector activation checklist | Freeze doc §10 already lists these as "deferred to activation" wiring; each connector's activation is a single flag flip + secret injection. | Revisit during Phase D if operational cognitive load becomes an issue. |
| `.env` per-phase checkpoint files | Ops hygiene practice; can be added as a git branching convention (`activation/phase-a-complete`, `activation/phase-b-complete`, …) without touching the plan. | Set up before Phase A begins if the operator wants an audit trail. |

None of these items block Phase A. Each is genuinely optional given
the current state of the plan.

---

## 5. Recommended sign-off

I recommend **APPROVED (no conditions)** for the v2 activation plan.

The Phase-A checklist (Plan v2 §14) is the operator's final gate.
Once signed, Phase 0 baseline capture (§4) is the first
executable action; no code deploy is required between sign-off and
Phase A because W1 and W2 have already landed.

---

## 6. What was changed during this remediation

- `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN.md` — full rewrite to v2
  (Batch 1 + Batch 3 documentation).
- `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN_REVIEW.md` — this file
  (v2 update).
- `/app/backend/legacy/engines/db_indexes.py` — W1 additions
  (5 TTL specs + cross-DB loop + env overrides).
- `/app/backend/legacy/engines/subsystem_health_router.py` — W2
  additions (`_register_aggregator_providers` at module load).
- `/app/backend/legacy/engines/health/router.py` — W2 additions
  (async `ukie` composition inside `/api/health/system`).
- `/app/backend/tests/test_activation_wiring_w1_w2.py` — new
  regression suite (8 tests, all passing).

What was NOT changed:
- No feature flag enabled or defaulted-on.
- No production database written to.
- No supervisor restart executed.
- No `.env` modified.
- No new endpoint added.
- No `BACKEND_FEATURE_FREEZE.md` clause modified.

Backend Feature Freeze fully respected.

---

*End of v2 review.*
*Awaiting final operator sign-off on the v2 activation plan.*
