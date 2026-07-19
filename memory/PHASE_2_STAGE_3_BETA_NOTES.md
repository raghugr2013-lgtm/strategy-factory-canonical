# Phase 2 — Stage 3.β Foundation Notes
### UKIE Pipeline (domain_router · license_gate · trust_scorer · dedup_check) + KnowledgeRepository + Dry-Run Harness

> **Status:** review pending operator approval.
> Assembled: 2026-02-19.
> Scope: Phase 2 Stage 3.β as authorised on 2026-02-19 — pipeline
> stages + governance cutover integration + dry-run harness. No
> promotion bridge, no retro-scoring, no additional connectors.

---

## 1. Executive summary

| Dimension | Result |
|---|---|
| Sub-steps implemented (P2C.4 → P2C.8) | ✅ Complete |
| New Stage-3.β tests | **66 / 66 passing** |
| Cumulative Phase-2 tests | **224 / 224 passing** (Stages 1 + 2 + 3.α + 3.β) |
| Live surface | `/api/knowledge/pipeline/{status,last-run}`, `/api/knowledge/dry-run` verified |
| Feature-flag gating | 5 new flags, all default OFF; verified by unit + live smoke |
| Backward compatibility | Zero legacy behaviour change — flags OFF returns byte-identical state to Stage 3.α |
| Data integrity | Governance cutover flag is the ONLY path to production Mongo writes; hard rails (`learning_only=True`, `eligible_for_deploy=False`) enforced at repository layer regardless of item state |
| Recommendation | ✅ **PASS — Stage 3.β ready; proceed to Validation Gate 3 planning on approval** |

---

## 2. What was built

### 2.1 `constants.py` — pipeline versioning

Two independent version streams stamped on every outcome:
- `PIPELINE_VERSION` (`"0.1.0"`) — bumps on **implementation** changes
- `PIPELINE_CONTRACT_VERSION` (`"0.1.0"`) — bumps ONLY on **semantic** changes
- `KNOWLEDGE_DB_NAME` (`"strategy_knowledge_base"`) — the isolated DB;
  collection names derived from the domain registry (single source of truth)

Rationale (operator directive): retro-processing, audit, and replay
must distinguish "rerun" from "semantic shift". Bump policy is
documented in the module.

### 2.2 `domain_router.py` — pipeline dispatch (P2C.4)

- `route(item) → RoutingDecision` — pure fn; resolves the item's
  `KnowledgeDomain` through `KNOWLEDGE_DOMAIN_REGISTRY` (no
  hard-coded enum values at decision sites).
- Flag: `ENABLE_DOMAIN_ROUTING` (default OFF → pass-through with
  `routed=False`).

### 2.3 `license_gate.py` — 5-outcome classifier (P2C.5)

Outcomes: `PERMISSIVE` (MIT / Apache / BSD / MPL / ISC),
`WEAK_COPYLEFT` (LGPL), `STRONG_COPYLEFT` (GPL / AGPL),
`PROPRIETARY`, `UNKNOWN`.

Two-tier detection:
1. **SPDX-id direct match** — checks `item.license` and
   `item.extras["spdx_id"]`. Confidence = 1.0.
2. **Heuristic** — regex sweep over first 32 KB of `content_bytes`
   for "X License" phrases and rights-reserved markers. Confidence
   0.5–0.75 depending on match strength.

Flag: `ENABLE_LICENSE_GATE` (default OFF → `outcome=UNKNOWN, gated=False`).

### 2.4 `trust_scorer.py` — 5-tier ladder (P2C.6)

Deterministic scoring from four inputs:
- Connector's `default_trust_tier` (seed)
- `LicenseVerdict` outcome (permissive: 0 · weak_copyleft: 0 ·
  strong_copyleft: -1 · proprietary: -2 · unknown: -1)
- `parser_confidence` (< 0.5: -1 · ≥ 0.95: +1 · else: 0). Default
  applied when absent: **0.8** (per operator directive; configurable
  via `RawKnowledgeItem.extras["parser_confidence"]`).
- Source-authority signals from `extras` — `curated=True` or
  `stars ≥ 1000` or `citations ≥ 50` → +1 boost.
- Dedup: `duplicate_same_domain` → hard clamp to **T1 Quarantine**;
  `duplicate_cross_domain` allowed (no adjustment).

All tiers clamped to 1..5. Adjustments returned as an ordered list
for full audit traceability.

Flag: `ENABLE_TRUST_SCORER` (default OFF → `tier=None, scored=False`).

### 2.5 `dedup_check.py` — within-domain hash uniqueness (P2C.7)

- Reads `strategy_knowledge_base.<storage_collection>` for the
  item's domain.
- Same-domain hash collision → `duplicate_same_domain`.
- Cross-domain hash presence → `duplicate_cross_domain` (advisory
  only; allowed by design).
- Missing hash → `no_hash`.
- Mongo failure → **fail-open** (returns `unique` with diagnostic
  reason) so a DB blip cannot block ingestion.

Flag: `ENABLE_DEDUP_CHECK` (default OFF).

### 2.6 `repository.py` — the audited write path (P2C.8)

`KnowledgeRepository.insert_ingested(item, *, license_verdict,
trust_score) → InsertResult` — the ONE write endpoint for UKIE.

Guarantees enforced at every call:
- **Hard rails** — `learning_only=True`, `eligible_for_deploy=False`
  stamped on every write regardless of item state (tested).
- **Domain partitioning** — writes to
  `strategy_knowledge_base.<storage_collection_for(domain)>`.
- **Provenance stamps** — `pipeline_version`,
  `pipeline_contract_version`, `inserted_at`, `updated_at`,
  `processed_at`.
- **Idempotent** — upsert on `(content_hash, domain)` composite key.
  Re-insert = update (preserves `inserted_at`).
- **Fail-safe** — dormant when `UKIE_GOVERNANCE_CUTOVER=false`
  (returns `status="dormant"` without touching Mongo); rejects empty
  hash; errors when DB unavailable.

Flag: `UKIE_GOVERNANCE_CUTOVER` (default OFF — the CRITICAL cutover).

### 2.7 `pipeline.py` — ordered composition

`run_one(item, *, dry_run, repository) → PipelineOutcome` and
`run_batch(items, *, dry_run, repository) → PipelineSummary`.

Stage order:
1. `domain_router` — resolve destination
2. `dedup_check` — Mongo read (own DB)
3. `license_gate` — SPDX + heuristic
4. `trust_scorer` — 5-tier + adjustments audit
5. `repository.insert_ingested()` — write (or bypass in dry-run)

**Same-domain hash collision short-circuits the write** with
`status="rejected"` and `trust_tier=1`. Cross-domain matches
proceed.

Every outcome carries `pipeline_version` / `pipeline_contract_version`
/ `processed_at` + per-stage outcome dicts + repository result +
`duration_ms`.

### 2.8 `dry_run.py` — shadow-mode harness

`run_dry(items=..., last_n_from_ingestion_runs=..., synthetic_fixture_name=...)` —
concatenates the three input sources and runs the full pipeline
with `dry_run=True` so writes are always bypassed.

Deterministic fixture `stage_3_beta_default` covers:
- All 6 canonical domains
- All 5 license outcomes (permissive · weak_copyleft ·
  strong_copyleft · proprietary · unknown)
- A within-domain hash collision candidate (so dedup fires)

Result cached in-memory for the `/api/knowledge/pipeline/last-run`
endpoint.

### 2.9 `router.py` — additive endpoints

New endpoints (all guarded by `UKIE_DOMAIN_REGISTRY_ENABLED`):

| Endpoint | Purpose |
|---|---|
| `GET /api/knowledge/pipeline/status` | Enabled stages + version stamps |
| `GET /api/knowledge/pipeline/last-run` | Most recent pipeline summary |
| `POST /api/knowledge/dry-run` | Shadow-mode pipeline run (body: `items`/`last_n_from_ingestion_runs`/`synthetic_fixture`) |

Zero disturbance to the Stage 3.α surface — all pre-existing
endpoints (`/api/knowledge/domains/*`, `/api/knowledge/connectors/*`)
untouched.

---

## 3. Feature flags introduced

| Flag | Default | Effect when ON | Data-loss risk |
|---|---|---|---|
| `ENABLE_DOMAIN_ROUTING` | `false` | `domain_router` stage active | ZERO — decision-only |
| `ENABLE_DEDUP_CHECK` | `false` | `dedup_check` performs Mongo read | ZERO — read-only |
| `ENABLE_LICENSE_GATE` | `false` | `license_gate` classifies (SPDX + heuristic) | ZERO — decision-only |
| `ENABLE_TRUST_SCORER` | `false` | `trust_scorer` assigns 5-tier label | ZERO — decision-only |
| **`UKIE_GOVERNANCE_CUTOVER`** | `false` | **`KnowledgeRepository.insert_ingested()` performs Mongo writes** — the critical cutover | LOW — writes land in `strategy_knowledge_base` (isolated); production `strategies` is untouched |

**Rollback** is a flag flip. `UKIE_GOVERNANCE_CUTOVER=false` returns
the repository to dormant mode within one supervisor restart cycle
(~30 s).

---

## 4. Governance guarantees

The cutover was designed under `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md
§7.3`: **nothing in Phase 2 modifies the production `strategies`
collection except via the audited promote bridge (Stage 3 follow-up).**

Stage 3.β preserves this by:

1. **Isolated DB.** UKIE writes go to `strategy_knowledge_base`, not
   the main app DB. `KNOWLEDGE_DB_NAME` is the single source of
   truth.
2. **Hard-rail enforcement.** Even if a mischievous item arrives
   with `learning_only=False, eligible_for_deploy=True`, the
   repository re-stamps both to their safe values before writing
   (tested).
3. **Dormant-by-default.** With `UKIE_GOVERNANCE_CUTOVER=false`, no
   Mongo write ever occurs, regardless of every other stage flag.
4. **Audit stamps.** Every stored document carries
   `pipeline_version` + `pipeline_contract_version` + timestamps +
   per-stage outcome so any downstream investigation can trace how
   an item ended up in the KB.

---

## 5. Test evidence

Runbook:
```
cd /app/backend && python3 -m pytest \
  tests/test_domain_router.py tests/test_license_gate.py \
  tests/test_trust_scorer.py tests/test_dedup_and_repository.py \
  tests/test_knowledge_pipeline.py -q
```

Result: **66 passed in 0.86 s**.

| Test file | Tests | Coverage |
|---|---|---|
| `test_domain_router.py` | 6 | Flag on/off; every-domain routing; outcome shape; pass-through reason |
| `test_license_gate.py` | 12 | Disabled by default; all 5 outcomes via SPDX; extras SPDX fallback; 3 heuristic outcomes; unknown case; confidence bounded [0,1]; to_outcome shape |
| `test_trust_scorer.py` | 16 | Disabled by default; permissive holds seed; strong_copyleft/proprietary/unknown demote; parser_confidence high/low/default; curated/stars/citations boosts; same-domain dedup → quarantine; cross-domain dedup allowed; tier bounded to [1,5]; adjustments ordered and traceable; deterministic |
| `test_dedup_and_repository.py` | 16 | Dedup: 5 status paths (unique/no_hash/same/cross/fail-open). Repository: dormant when flag off; insert when flag on; per-domain routing; hard rails override attempted false-flag item; empty-hash rejection; DB-unavailable error; version stamps present; upsert idempotency; license+trust carried onto stored doc |
| `test_knowledge_pipeline.py` | 16 | End-to-end: all flags off → dormant; all flags on → inserted; same-domain hash collision → rejected + T1; batch summary shape; pipeline_status shape; dry-run: synthetic fixture + explicit items + dict coercion + replay-empty; dry-run never writes even with cutover on; router endpoints 503-off + status shape + default fixture + last-run reporting + cached-after-run |

Full Phase-2 regression: **224 / 224 passing** (Stage 1: 34 · Stage
2: 74 · Stage 3.α: 50 · Stage 3.β: 66). Stages 1 + 2 + 3.α tests
unchanged.

---

## 6. Live verification

Preview pod, `UKIE_DOMAIN_REGISTRY_ENABLED=true`, all other stage
flags default OFF:

```
GET /api/knowledge/pipeline/status
→ {pipeline_version: "0.1.0", pipeline_contract_version: "0.1.0",
   stages: {domain_router:off, dedup_check:off, license_gate:off, trust_scorer:off},
   governance_cutover: {enabled: false}}

POST /api/knowledge/dry-run  (default fixture)
→ total=7 · dry_run=true · dormant=7
  domain_counts: strategy=2, research=1, indicator=1, market=1, execution=1, internal_history=1
  license_outcome_counts: unknown=7   (license gate off → all UNKNOWN)
  pipeline_version=0.1.0 · pipeline_contract_version=0.1.0

GET /api/knowledge/pipeline/last-run
→ same summary cached

GET /api/health/system
→ platform_score=100 · subsystems=[coe, vie, cts]   (unchanged)
```

With stage flags ON (verified in isolated Python session):
```
ENABLE_DOMAIN_ROUTING=true ENABLE_LICENSE_GATE=true ENABLE_TRUST_SCORER=true
→ trust distribution: T5=1, T3=3, T2=2, T1=1
→ license distribution: permissive=4, strong_copyleft=1, proprietary=1, unknown=1
```

Demonstrates the ladder + gate work end-to-end on the deterministic
corpus.

---

## 7. Pre-cutover checklist

Before flipping `UKIE_GOVERNANCE_CUTOVER=true` in production:

- [ ] Enable the four stage flags first (`ENABLE_DOMAIN_ROUTING`,
      `ENABLE_DEDUP_CHECK`, `ENABLE_LICENSE_GATE`,
      `ENABLE_TRUST_SCORER`) — they are decision-only, zero data risk.
- [ ] Run `POST /api/knowledge/dry-run` with `last_n_from_ingestion_runs=10`
      to reproduce the last 10 real ingestions in shadow mode.
      Verify the produced normalised items match what the legacy
      injector produced, MINUS the deliberate change:
      `eligible_for_deploy` is now `False` on every UKIE row (this
      is intended — production `strategies` must never receive
      `True` through UKIE).
- [ ] Confirm `pipeline_status` reports all four stages `enabled: true`.
- [ ] Confirm no anomalies in the trust-tier distribution (expected
      shape: a majority in T3–T4; T1 only for genuine
      quarantine-worthy cases).
- [ ] Confirm license distribution matches the operator's
      expectation for the current corpus (expect PERMISSIVE-heavy
      given the curated GitHub allow-list).
- [ ] Flip `UKIE_GOVERNANCE_CUTOVER=true` and observe:
      `/api/knowledge/pipeline/last-run` should show `dormant=0` and
      `inserted > 0` on the next ingestion run.
- [ ] Continuous audit query: `db.strategies.count({source: {$ne: null}})`
      before + after — MUST NOT CHANGE. UKIE writes go to
      `strategy_knowledge_base.strategies`, not `main.strategies`.

Rollback = set `UKIE_GOVERNANCE_CUTOVER=false` + restart backend
(~30 s). Any data already written to `strategy_knowledge_base` is
preserved and safe (isolated DB, hard rails enforced).

---

## 8. Non-goals honoured

- ❌ No `POST /api/knowledge/promote/{item_id}` (Stage 3.γ / promote bridge)
- ❌ No retro-scoring of 55 existing rows (follow-up)
- ❌ No new connectors (Stage 4)
- ❌ No `KnowledgeRepository` read / query surface (write-only)
- ❌ No changes to legacy `strategy_ingestion/*` behaviour
- ❌ No writes to production `strategies` or main app DB

---

## 9. Files delivered

### New files
- `/app/backend/legacy/engines/knowledge/constants.py` (46 lines)
- `/app/backend/legacy/engines/knowledge/domain_router.py` (100 lines)
- `/app/backend/legacy/engines/knowledge/license_gate.py` (200 lines)
- `/app/backend/legacy/engines/knowledge/trust_scorer.py` (200 lines)
- `/app/backend/legacy/engines/knowledge/dedup_check.py` (170 lines)
- `/app/backend/legacy/engines/knowledge/repository.py` (230 lines)
- `/app/backend/legacy/engines/knowledge/pipeline.py` (240 lines)
- `/app/backend/legacy/engines/knowledge/dry_run.py` (200 lines)
- `/app/backend/tests/test_domain_router.py` (6 tests)
- `/app/backend/tests/test_license_gate.py` (12 tests)
- `/app/backend/tests/test_trust_scorer.py` (16 tests)
- `/app/backend/tests/test_dedup_and_repository.py` (16 tests)
- `/app/backend/tests/test_knowledge_pipeline.py` (16 tests)

### Modified (additive, surgical)
- `/app/backend/legacy/engines/knowledge/__init__.py` — Stage 3.β exports
- `/app/backend/legacy/engines/knowledge/router.py` — pipeline + dry-run endpoints

**No files deleted. No production data modified. Zero changes to any
Stage 1 / 2 / 3.α file.**

---

## 10. Recommendation

### ✅ **PASS — Stage 3.β foundation ready for Validation Gate 3 planning.**

Justification:
1. **All five sub-steps** (P2C.4, P2C.5, P2C.6, P2C.7, P2C.8) shipped and verified.
2. **66 / 66 Stage 3.β tests pass**; **224 / 224 cumulative Phase-2 tests pass**.
3. **Governance guarantee preserved.** Isolated DB + hard-rail
   enforcement + dormant-by-default cutover flag + audit stamps on
   every write.
4. **Pipeline is version-aware** from day one — `PIPELINE_VERSION`
   for reruns, `PIPELINE_CONTRACT_VERSION` for semantic shifts.
5. **Dry-run harness** enables safe pre-cutover validation with
   three input sources.
6. **Zero legacy behaviour change.** Legacy `strategy_ingestion` +
   Stage 1 / 2 / 3.α surfaces are untouched.
7. **Rollback is 30 s.** Flag flip returns the system to a Stage-3.α-equivalent state.

### Recommended pre-Validation-Gate-3 actions

1. Draft Validation Gate 3 report using this document as evidence.
2. Plan Stage 3.γ (promote bridge + retro-scoring) as a follow-up —
   NOT part of Gate 3; separate operator approval.
3. Continue holding `UKIE_DOMAIN_REGISTRY_ENABLED` and every Stage-3
   flag OFF in production until the coherent UKIE activation
   sequence begins.

---

*Reviewed against:*
- `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §7 P2C.4–P2C.8`
- `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §6.3 / §7 / §10.3.2`
- `PHASE_2_STAGE_3_ALPHA_NOTES.md`
- Live pod responses at `http://localhost:8001/api/knowledge/{pipeline/status,pipeline/last-run,dry-run}`
- pytest output from `/app/backend/tests/`

*Status:* **Awaiting operator sign-off. Validation Gate 3 planning may begin immediately after approval.**
