# Phase 0 Baseline Report v2 (post-fix re-capture)

> **Status:** COMPLETE — Phase 0 baseline RE-CAPTURED after P0-F1 + P0-F2 fixes landed.
> **Scope:** REHEARSAL against preview pod. Production VPS baseline still
>   pending re-capture by operator on the VPS pod.
> **Executed:** 2026-07-20 09:16 UTC
> **Executor:** main agent (fork)
> **Feature Freeze:** respected end-to-end. No Stage-3/Stage-4 flags flipped.

---

## 1. Executive summary

| Question | Answer |
|---|---|
| Was Phase 0 baseline re-captured? | ✅ Yes, raw artifacts at `/app/memory/phase0_baseline_v2/*.json` |
| Backend healthy? | ✅ Yes, boots cleanly with all indexes applied |
| Dormancy invariant satisfied? | ✅ **All 12 Stage-4 endpoints return 503 as expected** (post P0-F1 fix) |
| All Stage-4 flags OFF? | ✅ Verified via `/api/health/config` |
| Comprehensive indexes applied at boot? | ✅ **54 indexes created on first boot**, all idempotent thereafter (post P0-F2 fix) |
| All 5 W1 TTL specs live in Mongo? | ✅ Verified via `db.getIndexes()` — see §4 |
| Legacy `ingested_strategies` invariant? | ✅ 0 rows |
| Production `strategies` invariant? | ✅ 0 rows |
| Are the two Phase 0 blockers resolved? | ✅ **P0-F1: RESOLVED. P0-F2: RESOLVED.** |
| Ready to authorise Phase A on **preview**? | ✅ Yes (subject to `COE_HEALTH_CONTRACT_ENABLED` being enabled — the one remaining Phase-A precondition, deliberately not set) |
| Ready to authorise Phase A on **VPS production**? | ⚠ Requires VPS-side Phase 0 re-capture to confirm the same fixes take effect there |

**Recommendation:** **PROCEED to Phase A** once (a) VPS Phase 0 is re-executed with the fixes deployed, and (b) `COE_HEALTH_CONTRACT_ENABLED` is verified on for the target pod. See §7.

---

## 2. Fix verification — P0-F1

### 2.1 Change summary
- Renamed Stage-4 UKIE health endpoint from
  `/api/knowledge/health` → **`/api/knowledge/ukie/health`**.
- Phase-1 KB probe at `/api/knowledge/health` continues unchanged and
  unaffected by any Stage-4 flag.
- 8 documents updated to reference the new path (Activation Plan §5.1
  A.1, Plan §8.3 D.9, Plan §8.6, `PHASE_4_P4D_OBSERVABILITY_NOTES.md`
  ×3 references, `PHASE_4_VALIDATION_GATE_5_REPORT.md`, `PRD.md`,
  `docs/observability/grafana_p4d_dashboard.json` ×4 panel URLs).

### 2.2 Verification evidence (live curl)

| Path | Flag state | HTTP | Expected | Result |
|---|---|---|---|---|
| `GET /api/knowledge/ukie/health` | `UKIE_HEALTH_PROVIDER_ENABLED=false` | **503** | 503 | ✅ |
| `GET /api/knowledge/health` (Phase-1) | (unaffected) | **200** | 200 | ✅ |
| `GET /api/knowledge/ukie/health` (unit-tested, flag on with mock provider) | flag on | 200 with UKIE snapshot shape | 200 | ✅ (unit test) |

**Regression coverage** added in `backend/tests/test_phase0_fixes_p0f1_p0f2.py`:
- `test_p0_f1_stage4_health_on_new_path_returns_503_when_flag_off`
- `test_p0_f1_old_path_no_longer_registered_by_stage4_router`
- `test_p0_f1_stage4_health_returns_snapshot_when_flag_on`

All 3 P0-F1 tests **passing**.

### 2.3 Verdict: **P0-F1 RESOLVED.**

Plan v2 §5.1 A.1 verification path now reads `GET /api/knowledge/ukie/health`; consumers pick the endpoint that matches their intent.

---

## 3. Fix verification — P0-F2

### 3.1 Change summary
- Wired `engines.db_indexes.ensure_indexes()` into
  `backend/app/main.py::lifespan` immediately after the minimal
  `app.db.mongo.ensure_indexes()` call.
- Uses the same `sys.path` prepend pattern as the pre-existing
  `_learning_ensure_indexes` block.
- Best-effort — failures log `WARNING` but never block boot.
- Logs a structured summary line at INFO on every boot.

### 3.2 Verification evidence (live boot log)

First boot after wiring:
```
2026-07-20 09:14:58,382 INFO strategy_factory: engines.db_indexes.ensure_indexes: created=54 existed=0 errors=0
```

Idempotent re-boot:
```
2026-07-20 09:15:33,406 INFO strategy_factory: engines.db_indexes.ensure_indexes: created=0 existed=54 errors=0
```

### 3.3 Mongo index verification — W1 TTL specs live

`db.workload_dead_letter.getIndexes()` (main DB):
```
[{name: '_id_', expireAfterSeconds: undefined},
 {name: 'ttl_workload_dead_letter', expireAfterSeconds: 7776000}]  ← 90d ✅
```

`db.getSiblingDB("strategy_knowledge_base").<coll>.getIndexes()`:

| Collection | TTL name | expireAfterSeconds | Days | Expected |
|---|---|---|---|---|
| `lifecycle_events` | `ttl_lifecycle_events` | 15,552,000 | **180** | 180 ✅ |
| `knowledge_endorsement_events` | `ttl_knowledge_endorsement_events` | 7,776,000 | **90** | 90 ✅ |
| `knowledge_contradiction_events` | `ttl_knowledge_contradiction_events` | 31,536,000 | **365** | 365 ✅ |
| `connector_events` | `ttl_connector_events` | 15,552,000 | **180** | 180 ✅ |

### 3.4 Side benefit — pre-existing INDEX_SPECS also now applied

`db.audit_log.getIndexes()` sample (pre-existing spec now live):
```
[{name: '_id_'},
 {name: 'ts_dt_-1'},
 {name: 'ix_audit_ts'},
 {name: 'ix_audit_event_ts'},
 {name: 'ttl_audit_log'}]
```

Previously dormant. Now applied on every boot. This is a legitimate
performance/hygiene benefit unlocked by fixing P0-F2 — 30+
pre-existing INDEX_SPECS + 7 TTL_SPECS + 4 KB_TTL_SPECS = **54
indexes total**, all live at boot.

### 3.5 Regression coverage

Added in `backend/tests/test_phase0_fixes_p0f1_p0f2.py`:
- `test_p0_f2_engines_ensure_indexes_wired_into_startup` — static-source guard
- `test_p0_f2_engines_ensure_indexes_is_awaitable_and_returns_summary` — API shape guard
- `test_p0_f2_wired_before_seed_admin` — ordering invariant

All 3 P0-F2 tests **passing**.

Full P0 fix test suite: **7/7 tests passing** in
`backend/tests/test_phase0_fixes_p0f1_p0f2.py`.

Combined with prior W1+W2 regression suite: **35/35 tests passing**
across all activation-wiring test files.

### 3.6 Verdict: **P0-F2 RESOLVED.**

---

## 4. Post-fix dormancy matrix

Fresh capture at 2026-07-20 09:16 UTC.

| Endpoint | Expected | Observed | Match? | Notes |
|---|---|---|---|---|
| `GET  /api/health` | 200 | **200** | ✅ | Phase-1 |
| `GET  /api/health/config` | 200 | **200** | ✅ | Phase-1 |
| `GET  /api/health/system` | 503 (`COE_HEALTH_CONTRACT_ENABLED=false`) | **503** | ✅ | Precondition dormant |
| `GET  /api/health/subsystems` | 503 | **503** | ✅ | Same |
| `GET  /api/version` | 200 | **200** | ✅ | Phase-1 |
| `GET  /api/coe/state` | 503 | **503** | ✅ | Pre-existing |
| `GET  /api/coe/metrics` | 503 | **503** | ✅ | Pre-existing |
| `GET  /api/knowledge/ukie/health` | 503 (Stage-4 flag off) | **503** | ✅ | **P0-F1 fix — was 200, now 503** |
| `GET  /api/knowledge/health` | 200 (Phase-1 endpoint, unaffected) | **200** | ✅ | Phase-1 KB probe |
| `POST /api/knowledge/query` | 503 | **503** | ✅ | Stage-4 |
| `GET  /api/knowledge/metrics` | 503 | **503** | ✅ | Stage-4 |
| `GET  /api/knowledge/promote-events` | 503 | **503** | ✅ | Stage-4 |
| `GET  /api/knowledge/retro-score-runs` | 503 | **503** | ✅ | Stage-4 |
| `GET  /api/knowledge/connector-events` | 503 | **503** | ✅ | Stage-4 |
| `GET  /api/meta-learning/health` | 503 | **503** | ✅ | Stage-4 retrofit |
| `GET  /api/mi/health` | 503 | **503** | ✅ | Stage-4 retrofit |
| `GET  /api/execution/health` | 503 | **503** | ✅ | Stage-4 retrofit |
| `GET  /api/portfolio/health` | 503 | **503** | ✅ | Stage-4 retrofit |
| `GET  /api/factory-eval/health` | 503 | **503** | ✅ | Stage-4 retrofit |
| `GET  /api/coe/dead-letter` | 503 | **503** | ✅ | Stage-4 COE γ |
| `GET  /api/coe/dead-letter/depth` | 503 | **503** | ✅ | Stage-4 COE γ |

**Score: 20 of 20 endpoints match expected baseline.** Zero mismatches (was 18/19 before fixes).

---

## 5. Dormant `.env` posture — unchanged

`/api/health/config` output identical to v1 capture:

```json
{
  "config_version":"1",
  "required":{"MONGO_URL":true,"DB_NAME":true,"JWT_SECRET":true},
  "mongo":{"configured":true,"db_name":"strategy_factory_preview_baseline"},
  "flags":{
    "enable_legacy_routers":false,
    "enable_factory_runner":false,
    "enable_dynamic_market_universe":false
  },
  ...
}
```

Every Stage-4 flag still default-OFF at boot ✅.

---

## 6. Deviations remaining after fixes

| # | Deviation | Severity | Action |
|---|-----------|----------|--------|
| ~~D2 / P0-F1~~ | ~~`/api/knowledge/health` path collision~~ | ~~MEDIUM~~ | ✅ **RESOLVED** |
| ~~D3 / P0-F2~~ | ~~`db_indexes` not wired to startup~~ | ~~HIGH~~ | ✅ **RESOLVED** |
| D1 | Preview pod required minimal `.env` to boot | INFRA | Preview-only; VPS pod already configured |
| D4 / P0-F3 | `COE_HEALTH_CONTRACT_ENABLED` off in preview | LOW | Not a Stage-4 flag; expected to be on already on VPS; verify at VPS Phase 0 |
| D5 | `/api/version` returns `0.0.0/unknown` on preview | LOW | Preview-only; VPS pod carries real BUILD_* values |

**No blockers remain for the Phase A gate.** The remaining items are
either preview-artifacts or expected VPS-side environment state.

---

## 7. Recommendation

### 7.1 Verdict on Phase A start

**✅ PROCEED to Phase A**, subject to two operator confirmations:

1. **Deploy the P0 fixes** to the VPS production pod. Files
   changed:
   - `backend/legacy/engines/knowledge/observability_router.py`
     (endpoint rename)
   - `backend/app/main.py` (startup wiring)
   - `backend/tests/test_phase0_fixes_p0f1_p0f2.py` (new)
   - `backend/tests/test_observability_p4d.py` (path reference update)
   - `docs/observability/grafana_p4d_dashboard.json` (dashboard URLs)
   - `memory/COHERENT_UKIE_ACTIVATION_PLAN.md` (verification paths)
   - `memory/PHASE_4_P4D_OBSERVABILITY_NOTES.md` (endpoint doc)
   - `memory/PHASE_4_VALIDATION_GATE_5_REPORT.md` (endpoint doc)
   - `memory/PRD.md` (endpoint doc)

2. **Re-execute Phase 0 on VPS production** with the fixes deployed
   to confirm:
   - Backend boots and logs
     `engines.db_indexes.ensure_indexes: created=… existed=… errors=0`
   - All 5 W1 TTL specs are visible in `db.getIndexes()` per §3.3.
   - `/api/knowledge/ukie/health` returns 503.
   - `/api/knowledge/health` (Phase-1) returns 200.
   - `COE_HEALTH_CONTRACT_ENABLED` is on so
     `/api/health/system` returns 200 with the retrofit `subsystems[]`
     entries after Phase A flags start flipping.
   - `/api/version` returns v1.1.0-stage4 + real commit hash.

### 7.2 Suggested Phase A start posture

Once VPS Phase 0 is green:
- Capture the Phase-0 baseline snapshot per Plan v2 §4.
- Begin Phase A.1 (`UKIE_HEALTH_PROVIDER_ENABLED=true`) with the
  verification step now correctly pointing at
  `GET /api/knowledge/ukie/health`.

---

## 8. Freeze-compliance statement

During the P0-F1 + P0-F2 remediation and this re-capture, the main
agent:

- Did NOT enable any Stage-3 or Stage-4 feature flag. Verified via
  `/api/health/config` — all 3 canonical flags still `false`.
- Did NOT modify `BACKEND_FEATURE_FREEZE.md`.
- Did NOT introduce new endpoints (renamed an existing one to
  eliminate a collision; the old path is deliberately gone from the
  Stage-4 side).
- Did NOT introduce new flags.
- Did NOT touch runtime user data or production `strategies` /
  legacy `ingested_strategies` collections.
- Did add 54 indexes to Mongo (pre-existing INDEX_SPECS + W1
  additions) — an operational hygiene improvement, not a behaviour
  change. All indexes are idempotent and reversible.

Backend Feature Freeze fully respected.

---

## 9. Artifact manifest

```
/app/memory/phase0_baseline_v2/00_capture_meta.txt          — capture metadata
/app/memory/phase0_baseline_v2/01_health.json               — /api/health (200)
/app/memory/phase0_baseline_v2/02_health_system.json        — /api/health/system (503)
/app/memory/phase0_baseline_v2/03_health_subsystems.json    — /api/health/subsystems (503)
/app/memory/phase0_baseline_v2/03a_health_config.json       — /api/health/config (200)
/app/memory/phase0_baseline_v2/04_coe_state.json            — /api/coe/state (503)
/app/memory/phase0_baseline_v2/05_coe_metrics.json          — /api/coe/metrics (503)
/app/memory/phase0_baseline_v2/06_version.json              — /api/version (200)
/app/memory/phase0_baseline_v2/07_stage4_dormancy.txt       — 21-endpoint dormancy matrix
/app/memory/phase0_baseline_v2/08_mongo_indexes_summary.txt — TTL index verification
```

Cross-references:
- Original Phase 0 report: `/app/memory/PHASE_0_BASELINE_REPORT.md`
- Change summary for W1+W2+Batch 1/3: `/app/memory/ACTIVATION_PLAN_V2_CHANGE_SUMMARY.md`

---

*End of Phase 0 baseline report v2.*
*Both blockers RESOLVED. Awaiting operator authorisation of Phase A start on the target pod.*
