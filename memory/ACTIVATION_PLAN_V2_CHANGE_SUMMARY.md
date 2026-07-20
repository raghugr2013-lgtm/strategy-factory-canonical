# Activation Plan v2 — Change Summary

> Author: main agent (fork). Date: 2026-07-20.
> Scope: Batches 1, 2, and 3(a) as approved by operator.
> Freeze status: **respected end to end.** No new features, no new
> endpoints, no new flags, no production behaviour changes.

---

## 1. Deliverables

| Artefact | Path | Status |
|---|---|---|
| Activation Plan v2 | `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN.md` | Rewritten (681 lines) |
| Review Memo v2 | `/app/memory/COHERENT_UKIE_ACTIVATION_PLAN_REVIEW.md` | Rewritten (222 lines) |
| Change Summary | `/app/memory/ACTIVATION_PLAN_V2_CHANGE_SUMMARY.md` | This file |
| Code — W1 | `/app/backend/legacy/engines/db_indexes.py` | 5 new TTL specs + cross-DB loop |
| Code — W2 | `/app/backend/legacy/engines/subsystem_health_router.py` | Auto-register 5 retrofit providers |
| Code — W2 | `/app/backend/legacy/engines/health/router.py` | Async UKIE composition in `/api/health/system` |
| Tests | `/app/backend/tests/test_activation_wiring_w1_w2.py` | 8 new regression tests |

---

## 2. Batch 1 — Documentation edits (COMPLETE)

The v1 plan (384 lines) has been rewritten to v2 (681 lines). No
sequences or thresholds were relaxed. Every finding from the v1
review memo has a resolution reference in the v2 review's finding-
by-finding table.

**Structural additions**:
- **§0** Target environment (preview vs production scope + which
  steps become no-ops in preview)
- **§2** Total activation timeline table (~40 days at conservative
  cadence)
- **§4** Phase 0 baseline snapshot (mandatory pre-Phase-A curl
  playbook)
- **§10** Assumptions list (10 items)
- **§11** Risk register (R1–R6)
- **Appendix A** Canonical `promote_policies` seed JSON

**Structural rewrites**:
- Every monitoring section now has an explicit sampling cadence.
- D.7 cutover rewritten to prevent the "flag flip produces writes"
  misreading.
- D.17/D.18 retro-score paragraph rewritten to make the read-legacy/
  write-KB direction explicit; legacy `ingested_strategies` invariant
  preserved throughout.
- Sequencing rationale line added for B-before-C ordering.
- Every immediate-escalation invariant (legacy write, non-promote
  origin, auto-promote) now has explicit "halt, page, do not
  proceed" language.
- Precondition "323/323 unit tests" reworded to make clear it refers
  to the Stage-4 targeted subset, not the full `tests/` directory
  (which contains pre-existing HTTP-integration suites).

---

## 3. Batch 2 — Freeze-permitted operational wiring (COMPLETE)

### W1 — TTL specs (`engines/db_indexes.py`)

Additive only. Follows the pre-existing `audit_log` `*_dt` pattern
(see file lines 292–295 for the reference precedent).

**Main DB TTL_SPECS additions:**
- `workload_dead_letter.first_failed_at_dt` — 90 d
  (env: `COE_DEAD_LETTER_TTL_DAYS`)

**New `KB_TTL_SPECS` list targeting `strategy_knowledge_base` DB:**
- `lifecycle_events.at_dt` — 180 d
  (env: `UKIE_LIFECYCLE_EVENTS_TTL_DAYS`)
- `knowledge_endorsement_events.at_dt` — 90 d
  (env: `UKIE_ENDORSEMENT_EVENTS_TTL_DAYS`)
- `knowledge_contradiction_events.at_dt` — 365 d
  (env: `UKIE_CONTRADICTION_EVENTS_TTL_DAYS`)
- `connector_events.at_dt` — 180 d
  (env: `UKIE_CONNECTOR_EVENTS_TTL_DAYS`)

`ensure_indexes()` extended with a best-effort cross-DB loop
against `get_db().client[KNOWLEDGE_DB_NAME]`. Best-effort semantics
preserved — failures log at WARNING and never raise.

**Field-type discipline note**: writers currently emit
`at` / `first_failed_at` as ISO strings, which Mongo's TTL monitor
cannot reap. The `*_dt` companion pattern makes the TTL a safe
no-op until writers are upgraded. This matches the existing
`audit_log` precedent and is documented inline in `db_indexes.py`
and in Plan v2 §B.2, §C.2, R6.

### W2 — Aggregator wiring

**Retrofit providers auto-register** (`subsystem_health_router.py`):

New `_register_aggregator_providers()` function iterates the
existing `SUBSYSTEMS` list and calls
`engines.health.providers.register_provider(name, provider)` for
each of the 5 retrofits. Each provider is a sync closure that:
- Reads its `<SUB>_HEALTH_PROVIDER_ENABLED` env flag,
- Returns `empty_snapshot(name)` with `reason="dormant"` when off,
- Returns `empty_snapshot(name)` with `reason="opted_in"` when on.

Called once at module import. No behaviour change for pre-Stage-4
consumers: with all flags off (default), the retrofit providers
appear in `/api/health/system` as dormant `subsystems[]` entries
with `health_score=100`, `state=ok`.

**UKIE async composition** (`health/router.py`):

`system_health()` extended with an async post-`collect_all()` block:
1. Import guard — if `engines.knowledge.health_provider` is not
   loadable (e.g. Phase 2 Stage 1 boot without Stage 4 mounted),
   silently skip.
2. Check `is_ukie_health_provider_enabled()`.
3. `await get_ukie_health_provider().snapshot()`.
4. If snapshot is not None, attach under top-level `"ukie"` key.

**Invariant**: when `UKIE_HEALTH_PROVIDER_ENABLED=false` (default),
the `"ukie"` key is omitted entirely — verified in
`test_w2_ukie_block_omitted_when_flag_off`.

### Regression coverage

New file: `backend/tests/test_activation_wiring_w1_w2.py` — 8 tests.

| Test | Verifies |
|---|---|
| `test_w1_workload_dead_letter_ttl_declared` | `workload_dead_letter` TTL is in `TTL_SPECS` with 90 d + `first_failed_at_dt` field |
| `test_w1_kb_ttl_specs_declared` | All 4 KB collections have correct TTL + `at_dt` field |
| `test_w1_env_override_honoured` | Env overrides applied on module reload |
| `test_w2_retrofit_providers_auto_register` | All 5 retrofits registered on module import |
| `test_w2_dormant_snapshot_when_flag_off` | Flag off → `reason=dormant`, `health=100`, `state=ok` |
| `test_w2_opted_in_snapshot_when_flag_on` | Flag on → `reason=opted_in`, others still dormant |
| `test_w2_ukie_block_omitted_when_flag_off` | `/api/health/system` response has NO `ukie` key when flag off |
| `test_w2_health_contract_off_returns_503` | Aggregator still respects `COE_HEALTH_CONTRACT_ENABLED` |

**Result: 8/8 passing.**

### Full Stage-4 test bundle

Ran the extended Stage-4 subset (10 files, 181 tests) after all
changes: **181/181 passing**, zero regressions.

```
tests/test_observability_p4d.py      ✅
tests/test_ukie_gamma.py             ✅
tests/test_coe_gamma.py              ✅
tests/test_promote_bridge.py         ✅
tests/test_retro_score.py            ✅
tests/test_health_contract.py        ✅
tests/test_activation_wiring_w1_w2.py ✅ (new)
tests/test_domain_router.py          ✅
tests/test_knowledge_domains.py      ✅
tests/test_knowledge_pipeline.py     ✅
```

---

## 4. Batch 3(a) — Phase E native Alertmanager silences (COMPLETE)

Plan v2 §9 replaced entirely. Key differences vs v1:

- **v1** described flipping `ALERT_*_ENABLED=true` in `.env` per rule.
- **v2** describes `amtool silence expire <id>` per rule.

Rationale: the `ALERT_*_ENABLED` labels exist only inside
`docs/observability/alertmanager_p4d_rules.yaml` as decorative
`flag:` labels. No Python code consumes them. Enabling an alert in
practice means removing the Alertmanager silence that keeps it
quiet, not flipping an env flag.

**No new backend code was added for Phase E.** Freeze respected.

Plan v2 §9.6 explicitly documents what is NOT changing to prevent
future confusion.

---

## 5. Deferred (Batch 4, low-priority polish)

Per operator direction:

- Rollback ordering guidance for B.4↔B.7
- Armed-but-silent alerts during A–D
- Per-connector activation checklist as companion doc
- `.env` per-phase checkpoint files

None of these block Phase A start.

---

## 6. What is now ready

- Activation Plan v2 is APPROVED-quality per the operator-review
  memo v2 (all High + Medium findings resolved).
- The two freeze-permitted wiring items are landed, tested, and
  will take effect at the next backend boot without any additional
  deploy step.
- Phase E mechanism is defined and does not depend on any new
  backend feature.
- Test coverage is stronger than before this remediation began
  (181 tests vs 134 baseline in the Stage-4 subset).

## 7. What is now required from you

- **Final review of `COHERENT_UKIE_ACTIVATION_PLAN.md` v2.**
- Sign-off block at Plan v2 §14 (checklist + signature).
- Optionally: authorise Phase A start.

Until then:
- All Stage-4 feature flags remain OFF.
- No production deployment.
- No `.env` changes.
- No supervisor restart.
- Backend Feature Freeze remains fully in effect.

---

*End of change summary.*
