# ASF_BACKEND_ARCHITECTURE.md — Strategy Archive Framework Backend Architecture

**Status:** **LOCKED — planning lock-in only. No code implements this yet.**
**Locked on:** 2026-06-13
**Locked by:** receiving agent, on operator authorisation
**Companion docs:**
* `ASF_PACKAGE_V1_SPEC.md` — wire-format spec (v1.0 contract).
* `MIGRATION_EXPORT_PLAN.md` — 1-vCPU → ASF export-format contract.
* `MIGRATION_PRIORITY.md` — T1/T2/T3 tier policy.
* `POST_IMPORT_PIPELINE.md` — 6-stage pipeline that runs after the importer.

**Authority:** This document is the **single source of truth for the ASF backend module layout, API surface, persistence schema, and scheduler placeholder.** When ASF work is authorised (post-12-vCPU-deployment per the prior audits), the implementation MUST follow this layout. The 1-vCPU migration importer MUST land at `backend/engines/asf/importer/migration_adapter.py` — NOT in a throwaway `backend/scripts/migration_import.py`.

---

## 1. Architectural principles

1. **Permanent, not throwaway.** Every line of ASF code is written to live for years. The 1-vCPU migration is the *first concrete user* of the framework — not the only one. Disaster recovery, server-to-server transfer, portfolio portability, and marketplace delivery all reuse the same modules.
2. **Schema-driven.** `engines/asf/schema.py` defines Pydantic models for every artefact in `ASF_PACKAGE_V1_SPEC.md`. All readers and writers go through these models — no raw-dict serialisation.
3. **Producer / consumer symmetry.** For every exporter module under `engines/asf/exporter/<X>.py` there is a structurally-analogous importer under `engines/asf/importer/<X>.py`. Round-trip (export → import → export) MUST be byte-faithful on `package_sha256`.
4. **Idempotent at the persistence layer.** Imports never fail on duplicates — they `skip` / `merge` / `replace` per `dedup_policy`. Exports never modify the source collections.
5. **Calibration-honest.** Every package includes the producer's `cert_calibration/` snapshot. Receivers compare to their current calibration and surface drift — they never blind-trust exported scores.
6. **No silent magic.** Every short-circuit, dedup, drift, or partial-closure case surfaces a structured warning in the import receipt — never logged-and-forgotten.

---

## 2. Module layout (locked file tree)

```
backend/engines/asf/
├── __init__.py
├── schema.py                          ← Pydantic models for the v1 manifest + strategy doc
├── package_writer.py                  ← Build .asfpkg (ZIP) from a subject set
├── package_reader.py                  ← Validate + unpack .asfpkg
├── manifest_validator.py              ← SHA-256 + schema + cross-ref checks
├── calibration_snapshot.py            ← Build cert_calibration/ block from live state
├── dedup_policy.py                    ← Apply "skip" / "merge" / "replace" semantics
│
├── exporter/                          ← (DEFERRED — post-importer authorisation)
│   ├── __init__.py
│   ├── _walker.py                     ← shared subject-graph walker
│   ├── single_strategy.py             ← export 1 fingerprint with full closure
│   ├── portfolio.py                   ← export N strategies + portfolio metadata
│   ├── master_bot.py                  ← export MB definition + members + .cs/.cbotpack
│   └── full_pod.py                    ← entire `strategy_library` + lineage + evidence
│
├── importer/                          ← FIRST AUTHORISED MODULE (migration adapter)
│   ├── __init__.py
│   ├── walker.py                      ← walk a .asfpkg, classify rows (incl. T1/T2/T3 for migration)
│   ├── upserter.py                    ← apply rows to canonical collections idempotently
│   ├── verifier.py                    ← post-import cross-check vs. manifest
│   └── migration_adapter.py           ← *** 1-vCPU specific adapter — GATE 3 importer lives here ***
│
└── disaster_recovery/                 ← (DEFERRED — post-export authorisation)
    ├── __init__.py
    ├── snapshot_runner.py             ← scheduled full-pod export (e.g. daily 04:00 UTC)
    └── restore_runner.py              ← restore from snapshot (operator-gated)
```

**Critical placement rule:** the 1-vCPU migration importer (~180 LOC per `IMPORT_DRYRUN_VALUE_REPORT.md §3`) is implemented inside `engines/asf/importer/migration_adapter.py`. It is a **thin adapter** (~40-60 LOC) that:

1. Detects a `mongodump --archive --gzip` package (Format A) or a JSON/ZIP package (Format B/C) in `/app/_migration_inbox/`.
2. Converts it into the canonical `.asfpkg` v1.0 wire-format **in memory** (no intermediate filesystem write).
3. Hands the converted package to the shared `engines/asf/importer/walker.py` + `upserter.py` — which is exactly the same code path every future ASF import uses.
4. Applies T1/T2/T3 tier classification via the filter knobs in `MIGRATION_PRIORITY.md §2`.

This file placement guarantees the GATE 3 work is **net-zero throwaway**: every line written for the migration is a line ASF will use again on every subsequent import.

### 2.1 Frontend placement (NOT TO BE BUILT NOW)

```
frontend/src/components/asf/                ← reserved namespace; NO files yet
```

UI surfaces are deferred per the operator's directive. The namespace is reserved so future panels (Explorer "Export bundle" button, Portfolio "Export", MasterBotDashboard "Export", Admin "ASF Snapshots") land in a predictable location.

---

## 3. Module contracts

### 3.1 `schema.py`

* Exports Pydantic models matching every JSON shape in `ASF_PACKAGE_V1_SPEC.md`:
  * `Manifest`, `IntegrityFile`, `ExporterInfo`, `SubjectSummary`, `PreservesFlags`, `SelfCheck`
  * `StrategyDoc`, `FingerprintInputs`, `Metrics`, `Lineage`, `Bi5Cert`, `Bi5CertWindow`, `Explorer`, `PortfolioAssignment`, `MasterBotMembership`, `Lifecycle`, `Provenance`
  * `MutationEvent`, `MutationStability`, `LifecycleStage`, `LifecycleHistoryEntry`, `PerformanceSnapshot`, `Alert`, `AuditExcerpt`
  * `Bi5StrategyCert`, `Bi5DataCert`, `ExplorerScore`, `RankerContribution`
  * `PortfolioDoc`, `PortfolioAssignment`, `MasterBotDefinition`, `MasterBotMember`, `RankerWeightsSnapshot`
* Each model exposes `to_canonical()` and `from_canonical()` for round-trip with the live Mongo schema.
* Unknown-key preservation: all models use `model_config = ConfigDict(extra="allow")` so `extensions.*` blocks survive round-trip.

### 3.2 `package_writer.py`

Public API:

```python
async def write_package(
    *,
    package_type: Literal["strategy","portfolio","master_bot","full_pod","migration"],
    subject_ids:  list[str],
    output_path:  Path,
    db:           AsyncIOMotorDatabase,
    dedup_policy_default: Literal["skip","merge","replace"] = "skip",
    extensions:   dict | None = None,
) -> WritePackageResult: ...
```

Responsibilities:
* Walk subjects + closure (lineage ancestors up to operator-configured depth).
* Snapshot calibration (`cert_calibration/`).
* Build all JSONL files via `engines/asf/exporter/_walker.py`.
* Compute SHA-256 per file + the package-level `package_sha256` per `ASF_PACKAGE_V1_SPEC.md §10.2`.
* Stream to ZIP at `output_path`.
* Insert one row into `asf_export_log` (see §4).

Pure-function (no global state). Reusable from any HTTP handler, CLI, or scheduled job.

### 3.3 `package_reader.py`

Public API:

```python
async def read_package(
    *,
    package_path: Path,
) -> PackageReadResult:
    """
    Validates manifest + sha256s + schema. Returns a parsed, in-memory
    representation. Does NOT touch Mongo.
    """
```

Returns a `PackageReadResult` with parsed Pydantic models per file. Receivers operate on this in-memory structure — they never re-read the ZIP.

### 3.4 `README.md` template

Every package includes a `README.md` generated at write time with this template:

```markdown
# ASF Package · <package_type>

- Package ID         : <UUIDv4>
- Subject            : <human description, e.g. "Strategy EURUSD/H1/trend_follow fp=3f2a51ec">
- Created at         : <UTC ISO>
- Created by         : <operator email>
- Pod                : <host_id> · build <BUILD_LABEL> · git <git_sha[:8]>
- Schema             : v<asf_schema_version>
- Package SHA-256    : <package_sha256>

## Contents

- Strategies         : <N>
- Lineage edges      : <N>
- Cert windows       : <N>
- Performance rows   : <N>
- Master Bot         : <yes/no>
- Portfolios         : <N>

## Restore instructions

1. Place this `.asfpkg` file in `/app/_migration_inbox/` on the destination pod.
2. Invoke `POST /api/asf/import` with `{ "package_path": "<path>", "dry_run": true }`.
3. Review the dry-run receipt.
4. If acceptable, invoke `POST /api/asf/import/{import_id}/commit`.

## Calibration snapshot

- tick_validator     : <e.g. P0B-v2>
- master_bot_ranker  : <e.g. v1.1>
- PASS / WARN        : <e.g. 0.85 / 0.70>

Calibration drift between this snapshot and the destination pod will be
surfaced as a `calibration_drift_warning` in the import receipt. Imports
proceed regardless; scores are advisory and will be re-derived against
the destination pod's calibration.
```

### 3.5 `dedup_policy.py`

Implements the three dedup policies from `ASF_PACKAGE_V1_SPEC.md §13`:
* `skip`    — canonical row wins; incoming ignored if any match.
* `merge`   — incoming fills only NULL fields of canonical.
* `replace` — incoming overwrites canonical, preserving `_id` + `provenance.discovered_at`.

Single entry point:

```python
async def apply_dedup(
    *,
    incoming:    StrategyDoc,
    canonical:   dict | None,            # existing strategy_library doc, or None
    policy:      Literal["skip","merge","replace"],
    match_kind:  Literal["fingerprint","strategy_hash","none"],
) -> DedupOutcome: ...
```

### 3.6 `importer/walker.py`

Iterates a `PackageReadResult` and yields one **`ApplyAction`** per row, classified by:
* Collection target (one of the 20 canonical collections from `ASF_PACKAGE_V1_SPEC.md §3`).
* Dedup outcome (`skip` / `merge` / `replace` / `fresh_insert`).
* Tier class (for migration packages only — T1/T2/T3 per `MIGRATION_PRIORITY.md §2`).

Pure-function. Does not write to Mongo.

### 3.7 `importer/upserter.py`

Consumes `ApplyAction`s and applies them to Mongo. Atomic per-collection (best-effort; the underlying collections do not require multi-collection transactions because every collection's identity key is independent).

Responsibilities:
* Apply each action via the canonical collection's existing primitives (`engines/strategy_library.save_strategy()` for `strategy_library`, etc.) — never bypass them. This guarantees that any side-effect (lifecycle hooks, fingerprint uniqueness, audit log emission) fires identically to a "native" insert.
* Emit one `audit_log` entry per action (`event_type="asf_import"`).
* Emit one `strategy_lifecycle_history` row per inserted strategy (`event_type="asf_import"`, additive — same pattern as R2's `event_type="bi5_cert"` rows).
* Write one `asf_import_log` row per import (see §4).

### 3.8 `importer/verifier.py`

Post-import sweep. Re-reads every inserted row from canonical collections and compares against the package's `integrity.files[]` SHA-256s **at the field-by-field level for identity fields** (`fingerprint`, `strategy_hash`, `params_canon`). Detects:
* Missing inserts (action said `fresh_insert` but row not found).
* Identity drift (canonical fingerprint != package fingerprint).
* Cert replay mismatch (re-running aggregate_window against the cached BI5 archive yields a score differing from the package's by more than 0.005).

Emits a structured `ImportVerification` report; any mismatch flips the import status to `verified_with_warnings`.

### 3.9 `importer/migration_adapter.py` *** (GATE 3 importer lives here) ***

The 1-vCPU-specific adapter. Thin wrapper, ~40-60 LOC. Behaviour:

```python
async def adapt_1vcpu_to_asf_v1(
    *,
    inbox_dir: Path,            # /app/_migration_inbox/
    db:        AsyncIOMotorDatabase,
) -> PackageReadResult:
    """
    Detects the package format in `inbox_dir` (Format A, B, or C per
    MIGRATION_EXPORT_PLAN.md §3) and converts it in-memory to an ASF
    Package v1.0 representation.

    Tier classification: applies the T1/T2/T3 filter from
    MIGRATION_PRIORITY.md §2 to each `strategy_library` row, sets:
        - stage = "IMPORTED_SEED"
        - provenance.source = "1vcpu_migration"
        - provenance.tier_class = "T1" | "T2" | "T3"
        - lifecycle.stage_locked_until = ISO(today + 30 days)
        - requires_revalidation = (T1 row passed filter #5-#6 by default)

    Returns an in-memory PackageReadResult. The caller hands this to
    engines.asf.importer.walker → upserter → verifier exactly as if it
    came from a real .asfpkg file. No intermediate ZIP is written.
    """
```

GATE 3 work, when authorised, ships as:
1. `engines/asf/__init__.py`         (empty)
2. `engines/asf/schema.py`           (only the models the migration adapter touches)
3. `engines/asf/package_reader.py`   (in-memory variant; no ZIP read needed for migration)
4. `engines/asf/calibration_snapshot.py`
5. `engines/asf/dedup_policy.py`
6. `engines/asf/importer/__init__.py`
7. `engines/asf/importer/walker.py`
8. `engines/asf/importer/upserter.py`
9. `engines/asf/importer/verifier.py`
10. `engines/asf/importer/migration_adapter.py`
11. The auto-selection 5-line guard at `engines/auto_selection_engine.py` (separate edit; documented in `MIGRATION_PRIORITY.md §6`).
12. The strategy_library unique-fingerprint-index pre-create (one-line edit to `engines/strategy_library.py`).
13. API surface: `POST /api/asf/import/migration` + `GET /api/asf/import/{import_id}` + `POST /api/asf/import/{import_id}/commit` (admin-only). See §3.10.
14. Tests: `tests/test_asf_schema.py`, `tests/test_asf_dedup_policy.py`, `tests/test_asf_migration_adapter.py`.

What is **NOT** built during GATE 3 (deferred per operator directive):
* `engines/asf/exporter/*` (the entire export side).
* `engines/asf/disaster_recovery/*` (snapshot scheduler + restore).
* `engines/asf/package_writer.py` (only the *reader* side is needed for migration).
* Frontend UI under `frontend/src/components/asf/*`.
* The non-migration import endpoints (`POST /api/asf/import` for arbitrary `.asfpkg` files). Operator can still trigger them via the migration endpoint later when full ASF is authorised.

### 3.10 `api/asf.py` (GATE 3 endpoint scope)

GATE 3 ships these endpoints **only**:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/asf/import/migration` | admin | Read `/app/_migration_inbox/`, run `migration_adapter` + `walker`, return dry-run receipt. |
| `GET`  | `/api/asf/import/{import_id}` | admin | Fetch import receipt + verifier report. |
| `POST` | `/api/asf/import/{import_id}/commit` | admin | Apply the staged actions via `upserter`. |
| `POST` | `/api/asf/import/{import_id}/abort` | admin | Discard the staged actions; emits one `audit_log` row. |

All other `/api/asf/*` endpoints (export, snapshots, generic import) are reserved and return `503 Not Implemented` if invoked under GATE-3-only scope. The endpoint URLs are locked so future ASF phases never collide.

---

## 4. Persistence schema (new collections)

| Collection | Indexed by | Created by | Purpose |
|---|---|---|---|
| `asf_export_log` | `(export_id)` unique · `(created_at)` desc | `engines/asf/package_writer.py` | One row per export. Stores `package_id`, `package_type`, `subject_ids`, `package_sha256`, `file_path`, `expires_at`. (DEFERRED — created when export ships.) |
| `asf_import_log` | `(import_id)` unique · `(created_at)` desc | `engines/asf/importer/upserter.py` | One row per import. Stores `package_id`, `package_sha256`, `dry_run`, `dedup_policy`, per-collection counts, status, warnings. **CREATED IN GATE 3.** |
| `asf_import_actions` | `(import_id, action_idx)` unique | `engines/asf/importer/walker.py` | Per-action audit row for resumable / inspectable imports. Stores incoming doc, dedup outcome, match kind, target collection. **CREATED IN GATE 3.** |
| `asf_artifact_registry` | `(package_sha256)` unique · `(package_root_fingerprint)` | `engines/asf/disaster_recovery/snapshot_runner.py` | Discoverability index for produced packages. (DEFERRED — created when DR ships.) |
| `asf_snapshot_runs` | `(run_id)` unique · `(started_at)` desc | `engines/asf/disaster_recovery/snapshot_runner.py` | Daily DR snapshot history. (DEFERRED — created when DR ships.) |

GATE 3 creates only `asf_import_log` and `asf_import_actions`. Both follow the lazy-create-on-first-write convention used elsewhere (e.g. `bi5_cert_sweep_runs`).

### 4.1 `asf_import_log` schema

```jsonc
{
  "import_id":         "<uuid>",
  "package_id":        "<from manifest>",
  "package_sha256":    "<from manifest>",
  "package_type":      "migration" | "strategy" | "portfolio" | "master_bot" | "full_pod",
  "dry_run":           true | false,
  "dedup_policy":      "skip" | "merge" | "replace",
  "status":            "pending" | "verified" | "verified_with_warnings"
                       | "committed" | "aborted" | "failed",
  "started_at":        "<UTC ISO>",
  "finished_at":       "<UTC ISO> | null",
  "duration_seconds":  0.0,

  "counts": {
    "strategies_inserted":   0,
    "strategies_skipped":    0,
    "strategies_merged":     0,
    "strategies_replaced":   0,
    "lineage_edges":         0,
    "lifecycle_rows":        0,
    "performance_rows":      0,
    "cert_rows":             0,
    "portfolio_rows":        0,
    "master_bot_rows":       0
  },
  "tier_breakdown": {            // present iff package_type == "migration"
    "T1":  0,
    "T2":  0,
    "T3":  0
  },
  "warnings": [
    {
      "kind": "calibration_drift" | "text_match_no_fp_match"
              | "cert_replay_mismatch" | "lineage_orphan"
              | "schema_unknown_keys" | "partial_closure",
      "subject": "<fingerprint or other identifier>",
      "detail":  "<human-readable detail>"
    }
  ],

  "calibration_snapshot": {
    "package_tick_validator": "tick_validator@P0B-v2",
    "package_ranker_version": "v1.1",
    "receiver_tick_validator":"tick_validator@P0B-v2",
    "receiver_ranker_version":"v1.1",
    "drift_detected":          false
  }
}
```

### 4.2 `asf_import_actions` schema

```jsonc
{
  "import_id":      "<uuid>",
  "action_idx":     0,
  "target_collection": "strategy_library" | "mutation_events" | "...",
  "dedup_outcome":  "skip" | "merge" | "replace" | "fresh_insert",
  "match_kind":     "fingerprint" | "strategy_hash" | "none",
  "incoming_id":    "<fingerprint or composite key>",
  "canonical_id":   "<existing _id, if any>",
  "tier_class":     "T1" | "T2" | "T3" | null,
  "applied_at":     "<UTC ISO> | null  (null iff dry_run)"
}
```

---

## 5. Scheduler placeholder

The disaster-recovery scheduler is **NOT built in GATE 3.** This section reserves its placement only:

```
engines/asf/disaster_recovery/snapshot_scheduler.py    (DEFERRED)

  • Job ID  : asf_full_pod_snapshot_daily
  • Trigger : CronTrigger(day="*", hour=4, minute=0, second=0, timezone="UTC")
  • Misfire grace : 1800 s
  • Coalesce: True
  • Max instances : 1
  • Retention : last 7 daily + last 4 weekly + last 12 monthly (configurable)

  Wired by an APScheduler startup hook in server.py, structurally
  identical to bi5_cert_sweep_scheduler@R2-v1.
```

The startup hook itself is also deferred. When DR ships, the hook lands alongside the existing R2 `_start_bi5_cert_sweep_scheduler` hook in `server.py`.

---

## 6. Integration contracts (existing surfaces ASF must honour)

### 6.1 Mongo collections (read-only from ASF's perspective, until import commit)

`engines/asf/exporter/_walker.py` reads from the 20 canonical collections enumerated in `ASF_PACKAGE_V1_SPEC.md §3`. It NEVER writes during export. It uses the existing read-side primitives where they exist (e.g. `get_latest_data_certification`, `aggregate_stats` from `engines/persistence_adapters/bi5_data_certification_store.py`).

### 6.2 Existing primitives ASF reuses (no rewrite)

* `engines/strategy_library._fingerprint()` — identity primitive. ASF reuses verbatim.
* `engines/strategy_library.save_strategy()` — single-strategy upsert. ASF importer calls this for every fresh insert and every `merge` outcome so all native side-effects fire.
* `engines/tick_validator.aggregate_window()` — cert replay during `verifier.cert_replay_check()`.
* `engines/master_bot_ranker._compute_candidate_score()` — score replay (advisory; surfaces drift only).
* `engines/master_bot_pack.build_pack()` — Master Bot `.cbotpack` building, reused inside `engines/asf/exporter/master_bot.py` when that phase ships.

### 6.3 Auto-selection 5-line guard (GATE 3 edit)

`engines/auto_selection_engine.py` — early `continue` in the selection loop, gated on:

```python
if candidate.get("stage") == "IMPORTED_SEED" \
   and candidate.get("stage_locked_until", "") > _now_iso():
    continue
```

Behaviour: any strategy carrying `stage="IMPORTED_SEED"` and an unexpired `stage_locked_until` is invisible to auto-deploy. Operator-readable; surfaced in audit logs.

### 6.4 Strategy library index hardening (GATE 3 edit)

`engines/strategy_library.py` — explicit `ensure_index()` call on the unique-fingerprint index, invoked from `engines/asf/importer/upserter.py` BEFORE any bulk insert. Replaces the current lazy-on-first-write contract for bulk-import paths. Live single-insert path (`save_strategy()`) keeps its current lazy create as a defence-in-depth measure.

---

## 7. Phased build-out — what ships when

### 7.1 Pre-12-vCPU-departure (NOW)

* **THIS DOCUMENT.** Spec lock-in only. No code.
* `ASF_PACKAGE_V1_SPEC.md`. Spec lock-in only. No code.

### 7.2 GATE 3 (post-deployment, operator-authorised)

* `engines/asf/__init__.py`
* `engines/asf/schema.py` (subset — only models the migration adapter needs)
* `engines/asf/package_reader.py` (in-memory variant for migration; ZIP variant deferred)
* `engines/asf/calibration_snapshot.py`
* `engines/asf/dedup_policy.py`
* `engines/asf/importer/{__init__,walker,upserter,verifier,migration_adapter}.py`
* `engines/auto_selection_engine.py` — 5-line guard
* `engines/strategy_library.py` — index pre-create one-line edit
* `api/asf.py` — 4 migration endpoints
* `server.py` — router include
* `tests/test_asf_*.py` — 3 test files
* Mongo collections: `asf_import_log` + `asf_import_actions` (lazy-create)

Effort estimate: **~3-4 dev-days** (~180 LOC migration adapter + ~50 LOC walker/upserter/verifier glue + ~150 LOC schema models + ~80 LOC tests + ~10 LOC API + integration). Higher than the bespoke "throwaway importer" estimate of ~2 d, lower than the standalone "permanent archive backend" estimate of ~9 d — because we ship only what GATE 3 needs and reserve the rest of the namespace for later.

### 7.3 Post-GATE-3 (separately authorised)

* `engines/asf/package_writer.py` — ZIP writer.
* `engines/asf/exporter/{_walker,single_strategy,portfolio,master_bot,full_pod}.py`
* `api/asf.py` — export endpoints + generic import endpoint.
* `tests/test_asf_exporter_*.py`

Effort estimate: **~4-5 dev-days**.

### 7.4 DR phase (separately authorised)

* `engines/asf/disaster_recovery/{snapshot_runner,restore_runner,snapshot_scheduler}.py`
* `api/asf.py` — snapshot management endpoints.
* `server.py` — DR scheduler startup hook.
* Mongo collections: `asf_snapshot_runs` + `asf_artifact_registry`.

Effort estimate: **~1-2 dev-days**.

### 7.5 UI phase (separately authorised)

* `frontend/src/components/asf/` — 5 panels: Strategy Explorer "Export", Portfolio "Export", MasterBotDashboard "Export", Admin "ASF Snapshots", Admin "Import (with dry-run preview)".
* `frontend/src/command/shell/modulesRegistry.js` — section registrations.

Effort estimate: **~3-4 dev-days**.

### 7.6 Marketplace-readiness extras (separately authorised, post-marketplace decision)

* PKI signing (`manifest.json.integrity.package_signature`).
* `extensions.marketplace.*` envelope validators.
* Optional package signature verification on import.

Effort estimate: **~2-3 dev-days**.

---

## 8. Non-goals (locked OUT of v1.0)

To prevent scope creep at lock-in time:

* **No streaming / chunked package format.** v1.0 packages fit in memory.
* **No cryptographic signing in GATE 3.** Reserved for marketplace phase.
* **No encryption.** Operators encrypt the `.asfpkg` file at the filesystem layer if needed.
* **No differential / incremental packages.** Always self-contained.
* **No n-way merge tooling.** Pairwise dedup is the limit.
* **No CLI tooling.** All flow goes through API + (later) UI.
* **No automatic post-import pipeline trigger** from the importer itself. The 6-stage post-import pipeline (`POST_IMPORT_PIPELINE.md`) is a separate operator-gated trigger, not auto-invoked by `migration_adapter.py`. This preserves the operator's "import-then-review-then-pipeline" workflow.
* **No retroactive re-export of pre-ASF strategies.** Strategies discovered before ASF exists can still be exported, but their `provenance.source_export_id` will be `null` and their `provenance.discovered_at` will be the inferred created_at — not perfectly historically accurate.

---

## 9. Acceptance criteria for GATE 3 (when work is authorised)

1. ✅ `engines/asf/importer/migration_adapter.py` exists and imports.
2. ✅ Running migration on the 1-vCPU package via `POST /api/asf/import/migration` with `dry_run=true` produces a non-empty receipt classifying every row into T1/T2/T3.
3. ✅ The receipt distinguishes `fingerprint` matches from `strategy_hash`-only matches.
4. ✅ Calibration drift between the source pod and the receiving pod surfaces a `calibration_drift` warning — non-fatal.
5. ✅ Committing the import via `POST /api/asf/import/{import_id}/commit` writes rows to the canonical collections through `save_strategy()` (NEVER bypassing native primitives).
6. ✅ T1 rows are tagged `stage="IMPORTED_SEED"`, `stage_locked_until = ISO(today + 30 days)`.
7. ✅ The 5-line auto-selection guard prevents `IMPORTED_SEED` candidates from auto-deploying.
8. ✅ The unique-fingerprint index is pre-created before bulk insert.
9. ✅ The post-import verifier re-reads every row and reports drift / mismatches.
10. ✅ Tests cover: schema validity · dedup policies · adapter format detection (A/B/C) · T1/T2/T3 classification · calibration drift detection.

---

## 10. Lock-in scope

**This document locks the backend architecture decisions.** Specifically:

1. Module file tree (§2).
2. Module API surfaces (§3).
3. Persistence schema for new collections (§4).
4. Scheduler placement (§5).
5. Integration contracts with existing engines (§6).
6. Phased build-out order (§7).
7. v1.0 non-goals (§8).
8. GATE 3 acceptance criteria (§9).

**What this document does NOT lock:**

* Per-function internal implementation (left to authoring author at GATE 3 time).
* Test fixture data (will be derived from the actual 1-vCPU package).
* UI surfaces (deferred entirely).
* Marketplace integration details (deferred entirely).

**Authority to change:** Operator-only. Any deviation from the locked file tree (§2) or the GATE 3 acceptance criteria (§9) requires explicit operator authorisation. The receiving agent MUST NOT relocate `migration_adapter.py` or convert it to a throwaway script under any circumstance — that is a hard contract.

---

**End of ASF_BACKEND_ARCHITECTURE.md.**
