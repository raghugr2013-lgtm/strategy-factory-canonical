# PRD — Strategy Trading Platform (Living Document)

## Original problem statement
The user provided a 1-vCPU migration snapshot and requested a strict restore → validate → BI5 R2 calibration → R2 batch (B-4/B-5/B-8) → ASF planning → GATE 3 implementation sequence. Each gate is operator-authorised; no unilateral code changes outside the locked plans.

## Current status (as of 2026-02 GATE 3 build)
- Migration snapshot restored. `MIGRATION_VALIDATION_REPORT.md` delivered.
- BI5 R2 Step-0 calibration (Option A) shipped.
- R2 Batch B-4 (Auto Certification Sweep), B-5 (Master Bot Ranker), B-8 (UI surfacing) shipped + tested.
- ASF v1.0 wire-format spec + backend architecture LOCKED:
  - `/app/memory/ASF_PACKAGE_V1_SPEC.md`
  - `/app/memory/ASF_BACKEND_ARCHITECTURE.md`
- 1-vCPU `migration_bundle.tar.gz` inspected → `/app/PACKAGE_INSPECTION_REPORT.md` (verdict 🟡 AMBER).
- **GATE 3 IMPLEMENTATION COMPLETE** → `/app/GATE3_BUILD_COMPLETION_REPORT.md`
- **GATE 3 DRY-RUN EXECUTED + GREEN** → `/app/DRY_RUN_REPORT.md`
- **GATE 3 WET-RUN EXECUTED + VERIFIED** → `/app/WET_RUN_COMPLETION_REPORT.md`
- **POST-IMPORT COHORT VALIDATION RUN** → `/app/POST_IMPORT_COHORT_VALIDATION_REPORT.md`
- **DEPLOYMENT READINESS AUDIT (read-only)** → `/app/DEPLOYMENT_READINESS_REPORT.md`
- **M1–M5 DEPLOYMENT PACKAGING COMPLETE** → `/app/M1_TO_M5_COMPLETION_REPORT.md`
- **ROADMAP READINESS AUDIT (read-only)** → `/app/ROADMAP_READINESS_AUDIT.md`
  - Per-phase % complete: BI5 R3 B-3 ~25% · B-6 ~70% · B-7 ~60% · Shadow Mode ~5% · Phase 13 0% · Phase 14 0% · ASF Exporter ~30% (schema reusable) · VPS bring-up ~85%
  - Decision matrix: only **1 item** in Tier-A (the VPS bring-up itself). All phase work is Tier-C/D — safe to build post-deploy. Phase 14 deferred to Tier-D.
  - 3 paths analysed: ⚡ FASTEST (6 ops-h, 0 dev-h, lowest risk) · 💰 LOWEST-CREDIT (same as ⚡) · 🏆 HIGHEST-QUALITY (3 pre-deploy + 7 post-deploy dev-days)
  - **Top recommendation: ⚡ FASTEST path.** Bundle is built; all functional capabilities already shipped; cohort is gated until 2026-07-13.

## Pending operator decisions
1. Provision 12-vCPU VPS and authorise bring-up sequence (~6 ops-hours)
2. Transfer bundle via scp and run `install.sh` → `docker compose up -d` → `mongorestore` → `certbot` → `startup_probe.sh`
3. After 72-h soak, authorise shadow-mode trade capture / ETHUSD source data / Phase 13
  - 14 new files (~2,208 LOC) + 3 modified files
  - 28/28 ASF tests passing; 19/19 strategy_library regression tests passing
  - 4 admin-gated endpoints under `/api/asf/*` registered and probed (401 confirmed)
  - Operator decisions wired: PF≥1.20, WR≥0.38, lock=+30d, depth=5, cohort_id=`1vcpu_2026_migration`, relaxation_reason=`pf_floor_1.20+wr_floor_0.38`
  - Imported scores treated as historical metadata only (`provenance.historical_scores.*`); auto-selection guard blocks until all `requires_*` flags flip

## Pending operator decisions
1. Authorise dry-run: `POST /api/asf/import/migration { dry_run: true, operator_overrides: {...} }`
2. Review dry-run receipt; if acceptable, authorise wet-run with `dry_run: false`
3. Proceed to post-import pipeline → 12-vCPU cutover → 72-h soak

## Roadmap
### P0 — Awaiting authorisation
- GATE 3 ASF importer build (~3–4 dev-days):
  - `engines/asf/{__init__,schema,package_reader,calibration_snapshot,dedup_policy}.py`
  - `engines/asf/importer/{__init__,walker,upserter,verifier,migration_adapter}.py`
  - `engines/auto_selection_engine.py` 5-line guard
  - `engines/strategy_library.py` index pre-create one-liner
  - `api/asf.py` (4 admin endpoints)
  - 3 test files

### P1 — Post-GATE-3
- Dry-run sweep against actual package
- Wet-run import (operator-gated)
- 12-vCPU cutover/deployment
- 72-hour deployment soak

### P2 — Future / Backlog
- BI5 R3 (B-3 tick-replay, B-6 simulate_fills, B-7 Trade Runner consolidation)
- Phase 13 Dossier Engine
- Phase 14 Valuation Engine
- ASF Exporter side (`engines/asf/exporter/*`)
- ASF Disaster-Recovery scheduler
- ASF UI panels under `frontend/src/components/asf/`
- Marketplace-readiness (PKI signing, licence envelope)

## Architecture notes
- Backend: FastAPI + MongoDB (Motor) + APScheduler for cron jobs
- Frontend: React.js + shadcn/ui
- All ASF code lives at `backend/engines/asf/` per the LOCKED layout in `ASF_BACKEND_ARCHITECTURE.md §2`.
- 1-vCPU migration adapter lives at `backend/engines/asf/importer/migration_adapter.py` — NOT in a throwaway script.

## Key documents
- `MIGRATION_VALIDATION_REPORT.md` (root)
- `BI5_R2_STEP0_COMPLETION_REPORT.md` (root)
- `R2_COMPLETION_REPORT.md` (root)
- `PACKAGE_INSPECTION_REPORT.md` (root) ← latest
- `memory/ASF_PACKAGE_V1_SPEC.md`
- `memory/ASF_BACKEND_ARCHITECTURE.md`
- `memory/MIGRATION_PRIORITY.md`
- `memory/MIGRATION_EXPORT_PLAN.md`
- `memory/POST_IMPORT_PIPELINE.md`
