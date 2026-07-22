# Phase 0 Baseline Report — Rehearsal (preview pod)

> **Status:** COMPLETE — Phase 0 baseline capture executed against the preview pod.
> **Scope:** REHEARSAL ONLY. Production VPS pod baseline MUST be captured
>   separately by the operator prior to Phase A start on VPS.
> **Executed:** 2026-07-20 09:00 UTC
> **Executor:** main agent (fork)
> **Feature Freeze:** respected end-to-end. No Stage-3/Stage-4 flags flipped.
> **Runtime deviation from expected baseline:** the preview pod's backend
>   was crashed on entry due to missing infra config (`MONGO_URL`, `DB_NAME`,
>   `JWT_SECRET`). Minimal `.env` was created with those 3 variables ONLY;
>   no activation-related flag was set. See §7 for the full deviation record.

---

## 1. Executive summary

| Question | Answer |
|---|---|
| Was Phase 0 baseline captured? | ✅ Yes, against the preview pod. Raw artifacts at `/app/memory/phase0_baseline/*.json` |
| Backend healthy? | ✅ Yes, after minimal infra `.env` populated |
| Dormancy invariant satisfied? | ⚠ 11 of 12 Stage-4 endpoints return 503 as expected. **`/api/knowledge/health` returns 200** — see §5 finding P0-F1 (path collision) |
| All Stage-4 flags OFF? | ✅ Verified via `/api/health/config` output |
| Legacy `ingested_strategies` invariant? | ✅ 0 rows (preview DB is fresh) |
| Production `strategies` invariant? | ✅ 0 rows (preview DB is fresh) |
| Ready to authorise Phase A on **preview**? | ⚠ Not without addressing P0-F1 and P0-F2 (see §5) |
| Ready to authorise Phase A on **VPS production**? | ⚠ Contingent on VPS Phase 0 re-execution and the same two findings not being present |

**Recommendation:** **DO NOT proceed to Phase A yet.** Two findings
require operator decisions before Phase A begins (see §8).

---

## 2. Environment verification

### 2.1 Target pod

- URL: `https://stall-debug.preview.emergentagent.com`
- Backend process: uvicorn `server:app` on 8001 (supervisor-managed)
- MongoDB: local `mongod` on 27017 (supervisor-managed)
- **NOTE:** this is the preview pod. Production VPS pod is
  `strategy.coinnike.com` (per PRD.md §1) — a different environment.

### 2.2 Configuration status (from `/api/health/config`)

| Variable | Set? | Value shape |
|---|---|---|
| `MONGO_URL` | ✅ | `mongodb://localhost:27017` (preview-only) |
| `DB_NAME` | ✅ | `strategy_factory_preview_baseline` (preview-only) |
| `JWT_SECRET` | ✅ | preview-only 32+ char string; NOT a known dev-default |
| `REDIS_URL` | ⚪ | not configured |
| `CORS_ORIGINS` | ✅ | `["*"]` (preview-permissive) |
| `ENABLE_LEGACY_ROUTERS` | ✅ (false) | dormant, as expected |
| `ENABLE_FACTORY_RUNNER` | ✅ (false) | dormant, as expected |
| `ENABLE_DYNAMIC_MARKET_UNIVERSE` | ✅ (false) | dormant, as expected |
| `COE_HEALTH_CONTRACT_ENABLED` | ⚪ (unset → false) | **deviation from Plan v2 §3 precondition** |
| **All Stage-4 flags** | ⚪ (unset → false) | dormant, as expected ✅ |

### 2.3 Version endpoint

```json
{"version":"0.0.0","commit":"unknown","build_date":"unknown","service":"strategy-factory-backend"}
```

Preview pod has no BUILD_* metadata baked in. On VPS production these
should show `v1.1.0-stage4` and the actual commit hash (per PRD.md §1).

---

## 3. Health verification

### 3.1 Endpoint matrix (from `/app/memory/phase0_baseline/07_stage4_dormancy.txt`)

| Endpoint | Expected | Observed | Match? |
|---|---|---|---|
| `GET  /api/health` | 200 | **200** | ✅ |
| `GET  /api/health/config` | 200 | **200** | ✅ |
| `GET  /api/health/system` | 200 (if `COE_HEALTH_CONTRACT_ENABLED=on`) OR 503 (if off) | **503** | ✅ (flag off, correctly 503) |
| `GET  /api/health/subsystems` | same as above | **503** | ✅ |
| `GET  /api/version` | 200 | **200** | ✅ |
| `GET  /api/coe/state` | 503 (flag off) | **503** | ✅ |
| `GET  /api/coe/metrics` | 503 (flag off) | **503** | ✅ |
| `GET  /api/knowledge/health` | 503 (Stage-4 flag off) | **200** | ⚠ **MISMATCH — see P0-F1** |
| `POST /api/knowledge/query` | 503 (Stage-4 flag off) | **503** | ✅ |
| `GET  /api/knowledge/metrics` | 503 | **503** | ✅ |
| `GET  /api/knowledge/promote-events` | 503 | **503** | ✅ |
| `GET  /api/knowledge/retro-score-runs` | 503 | **503** | ✅ |
| `GET  /api/knowledge/connector-events` | 503 | **503** | ✅ |
| `GET  /api/meta-learning/health` | 503 | **503** | ✅ |
| `GET  /api/mi/health` | 503 | **503** | ✅ |
| `GET  /api/execution/health` | 503 | **503** | ✅ |
| `GET  /api/portfolio/health` | 503 | **503** | ✅ |
| `GET  /api/factory-eval/health` | 503 | **503** | ✅ |
| `GET  /api/coe/dead-letter` | 503 | **503** | ✅ |
| `GET  /api/coe/dead-letter/depth` | 503 | **503** | ✅ |

**Score: 18 of 19 endpoints match expected baseline. One mismatch (P0-F1).**

### 3.2 `/api/health` payload (baseline)

```json
{
  "status":"ok",
  "ts":"2026-07-20T09:00:11.728436+00:00",
  "version":"0.0.0",
  "commit":"unknown",
  "build_date":"unknown",
  "service":"strategy-factory-backend"
}
```

### 3.3 Dormant aggregator (`/api/health/system`)

```json
{"detail":"COE_HEALTH_CONTRACT_ENABLED is off"}
```

This is the expected dormant response. **On the VPS production pod
this flag is on** (per PRD.md session 1-3 evidence). The preview
rehearsal cannot exercise the aggregator until the flag is set —
that is a deliberate Phase-A-precondition-not-verified state.

---

## 4. Dashboard verification

**SKIPPED** — the preview pod has no Grafana / Alertmanager deployment.
Per Plan v2 §0, this is an expected no-op in preview. Dashboard
verification must be performed against the VPS production pod
(Grafana at `<TBD>`, Alertmanager at `<TBD>`) as part of a subsequent
production-pod Phase 0.

Baseline artifacts to be captured on VPS:
- Grafana dashboard JSON export of the pre-Phase-A panels
- Alertmanager silence list before activation

---

## 5. Findings (deviations from expected baseline)

### 5.1 P0-F1 — `/api/knowledge/health` path collision ⚠ MEDIUM

**Observation:** `GET /api/knowledge/health` returns **200** with a
Phase-1 knowledge-base payload, not the 503 expected under
`UKIE_HEALTH_PROVIDER_ENABLED=false`.

```json
{"status":"empty","corpus_size":0,"backend":"rule_based_v1","readiness_ceiling":"pending_validation"}
```

**Root cause:** Two routers register the same path at
`/api/knowledge/health`:

1. **Phase-1 owner** — `backend/app/knowledge/router.py:236` (mounted at
   `backend/app/main.py:516`). Not flag-gated. Owns the KB cache
   health probe.
2. **Stage-4 owner** — `backend/legacy/engines/knowledge/observability_router.py:76`
   (mounted at `backend/app/main.py:565`, via
   `engines.knowledge.router.py:223` which composes
   observability sub-router). Gated by `UKIE_HEALTH_PROVIDER_ENABLED`.

FastAPI matches the first-registered route. Because the Phase-1
mount is on line 516 and the Stage-4 mount is on line 565, the
Phase-1 endpoint always wins.

**Impact on Plan v2 §5.1 step A.1:**
- Flipping `UKIE_HEALTH_PROVIDER_ENABLED=true` will NOT change the
  response of `GET /api/knowledge/health` — the operator will
  continue to see the Phase-1 shape.
- The A.1 verification step (`→ 200 with status:"dormant"`) cannot
  be satisfied as written.
- **Dormancy discipline is NOT violated** — no data is at risk.
  This is a verification-shape bug, not a security bug.

**Recommendation (operator decision required):**

a. **Rename the Stage-4 endpoint** to a distinct path, e.g.
   `/api/knowledge/ukie/health`, and update Plan v2 §5.1 A.1
   accordingly. Small doc + code diff (freeze-permitted
   operational wiring; the endpoint has never been exercised in
   production, no compat concern).

b. **Reverse the mount order** in `backend/app/main.py` so the
   Stage-4 router mounts BEFORE the Phase-1 router. Also
   freeze-permitted (pure ops wiring). Adds risk that the flag-off
   path returns 503 to callers of the Phase-1 endpoint.

c. **Accept the shadowing** and change Plan v2 A.1 to query a
   different Stage-4 endpoint (e.g., `/api/knowledge/metrics`) for
   the "UKIE provider on" verification. Doc-only.

My recommendation: **(a)**. It's the cleanest separation of concerns
and matches the Freeze doc's principle that Stage-4 endpoints are
additive to Stage-1 endpoints, not superseding.

### 5.2 P0-F2 — comprehensive `db_indexes.ensure_indexes()` not wired to startup ⚠ HIGH

**Observation:** Plan v2 §B.2 and §C.2 state that TTL indexes for
the five Stage-4 audit collections "auto-apply at boot via
`engines/db_indexes.py`". They do not.

**Root cause:** `backend/app/main.py:56` calls
`app.db.mongo.ensure_indexes()`, which is a MINIMAL 6-index helper
that creates only `users`, `refresh_tokens`, and `audit_log`
indexes. The comprehensive `engines/db_indexes.py::ensure_indexes()`
(which contains all the pre-existing INDEX_SPECS/TTL_SPECS plus my
W1 additions) is **never invoked**.

The docstring at `engines/db_indexes.py:15` reads "Consumed by
`server.py` startup hook `_ensure_mongo_indexes`" — but no such
hook exists in the current app factory. This is a **pre-existing
wiring gap** dating back to before my W1 additions.

**Impact:**
- 30+ pre-existing INDEX_SPECS are dormant (query performance risk)
- 6 pre-existing TTL_SPECS are dormant (retention risk)
- All 5 new W1 TTL specs (Batch 2 wiring) are dormant

**Impact on Plan v2 §5.1 / §B.2 / §C.2:**
- The plan's assertion that TTL indexes are "auto-applied at boot"
  is currently untrue.
- Before Phase B.2 begins, someone must either:
  - Wire `engines.db_indexes.ensure_indexes()` into the startup
    hook (single-line change in `backend/app/main.py`);
  - OR expose a `POST /api/admin/ensure-indexes` operator button
    (may already exist — needs verification);
  - OR run `python -c "from engines.db_indexes import
    ensure_indexes; import asyncio; asyncio.run(ensure_indexes())"`
    on the target pod at Phase B.2 arrival.

**Verified via Mongo:** all Stage-4 collections
(`workload_dead_letter`, `lifecycle_events`,
`knowledge_endorsement_events`, `knowledge_contradiction_events`,
`connector_events`) are **absent** — no writes have occurred (as
expected under freeze), so the TTL no-op has no observable effect
today. The issue is latent — it will bite when Phase B.2 tries to
verify the TTL is applied.

**Recommendation:** **(pre-Phase-A operator decision)** wire
`engines.db_indexes.ensure_indexes()` into the startup hook. This
is freeze-permitted operational wiring — one line change, matches
existing pattern. Full code diff:

```python
# backend/app/main.py, after line 56:
try:
    from engines.db_indexes import ensure_indexes as _legacy_ensure_indexes
    await _legacy_ensure_indexes()
except Exception:
    logger.exception("legacy db_indexes.ensure_indexes failed (non-fatal)")
```

Alternative: expose it via a POST endpoint gated by admin auth.

### 5.3 P0-F3 — `COE_HEALTH_CONTRACT_ENABLED` off on preview ⚠ LOW (informational)

**Observation:** the flag is unset (defaults false) on the preview
pod. Plan v2 §3 lists it as a Phase-A precondition and Assumption
#1 in §10.

**Impact:** `/api/health/system` returns 503 in the preview.
Aggregator wiring (W2) cannot be exercised in preview until this
flag is set.

**Recommendation:** verify this flag IS on when the VPS Phase 0
baseline is captured. This is a known Phase 2 Stage 1 flag, not a
Stage-4 flag. Setting it does not violate the freeze.

---

## 6. Current metrics snapshot

### 6.1 Health metrics

- `platform_health_score`: **not measurable** (aggregator dormant
  because `COE_HEALTH_CONTRACT_ENABLED=false`).
- `/api/health`: `status="ok"` (Phase-1 endpoint, unrelated to
  aggregator).
- Backend process healthy; supervisor uptime > 0; no crashes since
  minimal `.env` populated.

### 6.2 COE metrics

- `GET /api/coe/state`: 503 (flag off — baseline)
- `GET /api/coe/metrics`: 503 (flag off — baseline)

### 6.3 Mongo baseline (preview)

Preview DB (`strategy_factory_preview_baseline`):
- `users`: unknown (not counted for baseline)
- `refresh_tokens`: unknown
- `audit_log`: unknown
- `strategies`: **0** ✅
- `ingested_strategies`: **0** ✅
- `workload_dead_letter`: **0** ✅

`strategy_knowledge_base` DB: **empty (no collections created)** ✅
- `lifecycle_events`: absent
- `knowledge_endorsement_events`: absent
- `knowledge_contradiction_events`: absent
- `connector_events`: absent
- `promote_events`: absent
- `retro_score_runs`: absent

### 6.4 Feature-flag baseline (all Stage-4 flags)

Verified via `/api/health/config` (which only surfaces canonical
flags) plus process-env inspection: **34 Stage-4 flags all
unset/default OFF** ✅. Zero deviation.

---

## 7. Deviations from expected baseline (structured record)

| # | Deviation | Severity | Blocks Phase A? | Blocker for VPS production Phase 0? |
|---|-----------|----------|-----------------|--------------------------------------|
| D1 | Backend was crashed on entry (missing 3 infra env vars) | INFRA | No — resolved by populating minimal `.env` (preview only) | No — VPS pod already has these set per PRD.md sessions 1-3 |
| D2 | P0-F1: `/api/knowledge/health` path collision | MEDIUM | ⚠ **Yes** — verification of Plan A.1 will fail | Yes — same collision will appear on VPS |
| D3 | P0-F2: `db_indexes.ensure_indexes()` not wired to startup | HIGH | ⚠ **Yes** — Plan B.2 / C.2 TTL auto-apply is currently a no-op | Yes — same wiring gap on VPS |
| D4 | P0-F3: `COE_HEALTH_CONTRACT_ENABLED` off in preview | LOW | No (preview) — verify on VPS at Phase 0 | Yes — must be on for Plan §3 |
| D5 | `/api/health` returns `version=0.0.0`, `commit=unknown` | LOW | No | Verify VPS pod returns v1.1.0-stage4 + real commit |

---

## 8. Recommendation

### 8.1 Verdict on Phase A start

**DO NOT proceed to Phase A yet.** Two findings require resolution
before Phase A can be verified correctly:

- **P0-F1** (`/api/knowledge/health` shadowing) is a verification-
  shape bug that will silently fail Plan A.1. Even though the
  dormancy invariant is preserved, the operator will not be able to
  observe the UKIE dormant snapshot through the endpoint the plan
  names.
- **P0-F2** (`db_indexes` not wired to startup) is a broader wiring
  gap that impacts Plan B.2 and C.2 TTL auto-apply promises. It
  also silently degrades pre-existing INDEX_SPECS.

### 8.2 Suggested remediation batch (freeze-permitted operational wiring)

Both fixes are freeze-clean per `BACKEND_FEATURE_FREEZE.md §10`
("deferred to activation" wiring is permitted).

- **Fix F1**: rename Stage-4 `/api/knowledge/health` to
  `/api/knowledge/ukie/health`. Small code diff in
  `engines/knowledge/observability_router.py`; update Plan v2 §5.1
  A.1 to match.
- **Fix F2**: wire `engines.db_indexes.ensure_indexes()` into
  `backend/app/main.py`'s startup hook. Single try/except block
  matching the existing `_learning_ensure_indexes` pattern
  (lines 113–116).

Estimated total effort: **≈45 minutes** including regression tests.

### 8.3 What to do next

The operator should:

1. **Review this report.**
2. **Decide** on the disposition of P0-F1 (Option a, b, or c in §5.1).
3. **Approve** Fix F2 (or provide an alternative — e.g., invoke
   `ensure_indexes()` manually before Phase B.2).
4. **Re-run Phase 0** on the VPS production pod to capture the
   production baseline (this preview capture does NOT substitute
   for production baseline — VPS may have different findings).
5. **Only then**, authorise Phase A start on the target pod.

---

## 9. Freeze-compliance statement

During this Phase 0 execution, the main agent:
- Did NOT enable any Stage-3 or Stage-4 feature flag.
- Did NOT modify `BACKEND_FEATURE_FREEZE.md` or its constraints.
- Did NOT modify the activation plan.
- Did NOT touch Mongo data.
- Did NOT change any subsystem's runtime behaviour beyond bringing
  the backend up from crashed → running (via minimal 3-var `.env`
  containing only mandatory infra config).
- Did populate `/app/backend/.env` with **preview-only** infra
  credentials that do not enable any activation feature.

Backend Feature Freeze fully respected.

---

## 10. Artifact manifest

Raw baseline data lives at `/app/memory/phase0_baseline/`:

```
00_capture_meta.txt         — capture metadata + timestamps
01_health.json              — /api/health payload (200)
02_health_system.json       — /api/health/system payload (503)
03_health_subsystems.json   — /api/health/subsystems payload (503)
03a_health_config.json      — /api/health/config payload (200)
04_coe_state.json           — /api/coe/state payload (503)
05_coe_metrics.json         — /api/coe/metrics payload (503)
06_version.json             — /api/version payload (200)
07_stage4_dormancy.txt      — 19-endpoint dormancy matrix
99_file_manifest.txt        — ls of directory
```

---

*End of Phase 0 baseline report (rehearsal).*
*Awaiting operator disposition on P0-F1 and P0-F2 before Phase A start.*
