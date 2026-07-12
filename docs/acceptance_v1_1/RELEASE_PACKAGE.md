# Strategy Factory v1.1 — Canonical Release Package

**Repository state:** frozen candidate as of Feb 15 2026.
**Verdict:** ✅ Accepted pending reviewer sign-off on the acceptance pack.

---

## What is included in the freeze package

Everything listed below is present at repository HEAD.

### Source code
- `/app/backend/` — FastAPI backend
  - `app/` — Phase-1 core (auth, DB, VIE bridge, dynamic legacy mount)
  - `legacy/` — 83 v01 routers + 169 engines + config + tests, verbatim
- `/app/frontend/` — v01 React SPA
  - `src/App.js` — `GatedCommandModuleApp` (v01 verbatim)
  - `src/command/` — full Command OS shell
  - `src/components/` — 66 v01 operator components + shadcn ui
  - `src/services/`, `hooks/`, `stores/`, `styles/`, `routes/`, `pages/Welcome/`, `i18n/`, `constants/`, `lib/`, `a11y/`, `assets/`
- `/app/vie/` — Vendor Independent Engine service (OpenAI / Anthropic / Gemini / DeepSeek / Groq / Kimi)

### Docker
- `backend/Dockerfile` — python:3.12-slim, uvicorn, `/api/health` healthcheck
- `frontend/Dockerfile` — node:20-alpine build → nginx:alpine runtime, `/healthz` healthcheck, SPA fallback
- `vie/Dockerfile` — python:3.12-slim, uvicorn, `/health` healthcheck
- `docker-compose.yml` — local/dev stack with bundled MongoDB (`ENABLE_LEGACY_ROUTERS=true` default)
- `infra/compose/docker-compose.prod.yml` — production overlay (external Traefik + external MongoDB on `vqb-network`)
- `.env.example` — every required knob, safe defaults

### VIE integration
- `vie/router.py`, `vie/registry.py`, `vie/providers/*.py`
- Backend bridge: `backend/legacy/engines/llm_config.py` + `llm_runner.py` route all AI calls through VIE
- **Zero `EMERGENT_LLM_KEY` references** in the codebase

### JWT / RBAC
- `backend/app/auth/routes.py` — login, refresh, logout, me (dual-shape response)
- `backend/app/auth/security.py` — bcrypt + JWT + refresh rotation
- Roles: `admin`, `developer`, `researcher`, `operator`, `viewer`
- Admin-approval workflow preserved from v01

### Mongo migration
- `backup/v01_mongodump.archive` — full v01 dump (57 collections, 313k market bars, 14 strategies, 10k mutation events, etc.)
- Restore instructions in `docs/acceptance_v1_1/DEPLOYMENT_GUIDE.md#3-v01-data-restore`
- `ruff.toml` at repo root — per-file ignore rules for `backend/legacy/**` to keep the lint hook green without altering v01 code

### Documentation
| Path | Purpose |
|------|---------|
| `docs/acceptance_v1_1/BACKEND_ACCEPTANCE_REPORT.md` | 21-module × field-by-field acceptance report |
| `docs/acceptance_v1_1/API_INVENTORY.md` | 497-endpoint × method × auth × status table |
| `docs/acceptance_v1_1/ENGINE_INVENTORY.md` | 169-engine × source × API × UI × status |
| `docs/acceptance_v1_1/FRONTEND_RESTORATION_REPORT.md` | Per-file restoration classification + parity audit |
| `docs/acceptance_v1_1/E2E_WORKFLOW_LOG.md` | Full 31-step curl+JWT workflow evidence |
| `docs/acceptance_v1_1/DEPLOY_VERIFY_RUN.log` | Live output of `scripts/deploy_verify.sh` (31/31 PASS) |
| `docs/acceptance_v1_1/DEPLOYMENT_GUIDE.md` | One-page deploy guide (local + VPS) |
| `docs/acceptance_v1_1/ARCHITECTURE_DIAGRAM.md` | ASCII architecture + request lifecycle |
| `docs/acceptance_v1_1/RELEASE_NOTES_v1.1.md` | Feature summary + statistics + known limitations |
| `docs/acceptance_v1_1/screenshots_original/` | 12 v01 baseline screenshots |
| `docs/acceptance_v1_1/screenshots_recovered/` | 10 recovered-live screenshots |
| `docs/FINAL_RECOVERY_REPORT.md` | Recovery narrative from Phase 0 onward |
| `docs/openapi.json` | Full OpenAPI 3.1 spec snapshot |
| `memory/PRD.md` | Canonical product requirements |
| `memory/test_credentials.md` | Admin credentials + token storage keys |

### Deployment guide
- `docs/acceptance_v1_1/DEPLOYMENT_GUIDE.md` — 5-minute local, VPS bring-up, restore, verification checklist, rollback
- `scripts/deploy_verify.sh` — one-click 31-step E2E acceptance workflow (exit 0 on green)

### Architecture diagram
- `docs/acceptance_v1_1/ARCHITECTURE_DIAGRAM.md`

### Recovery report
- `docs/FINAL_RECOVERY_REPORT.md`
- `audit_workspace/reports/PHASE_0_COMPLETION_REPORT.md`, `PHASE_1A_COMPLETION_REPORT.md`, `PHASE_1B_COMPLETION_REPORT.md`
- `docs/acceptance_v1_1/FRONTEND_RESTORATION_REPORT.md` (recovery of the frontend specifically)

### Acceptance reports
- Backend: `docs/acceptance_v1_1/BACKEND_ACCEPTANCE_REPORT.md`
- Frontend: `docs/acceptance_v1_1/FRONTEND_RESTORATION_REPORT.md`
- E2E: `docs/acceptance_v1_1/E2E_WORKFLOW_LOG.md`
- Deploy verify live run: `docs/acceptance_v1_1/DEPLOY_VERIFY_RUN.log`

### Release notes
- `docs/acceptance_v1_1/RELEASE_NOTES_v1.1.md`

---

## Freeze policy — effective on sign-off

Once the reviewer signs off on this package, `main @ HEAD` becomes the **canonical `strategy-factory@1.1.0` release**. From that point:

1. **Do not** modify `backend/legacy/**`, `frontend/src/**` (v01 tree), or the v01 Command OS surface.
2. **Do not** re-introduce `EMERGENT_LLM_KEY` or vendor-locked LLM clients.
3. **ArbiCore X**, **GemHunter**, and future intelligence modules must ship as **separate modules mounted on this frozen base**:
   - New routers under `backend/modules/<name>/api/`
   - New engines under `backend/modules/<name>/engines/`
   - New UI under `frontend/src/modules/<name>/`
   - New Mongo collections under a namespaced prefix (`arbicorex_*`, `gemhunter_*`)
   - New Compose services alongside `factory-*`
4. Non-breaking backend augmentations (new routers, new providers, new collections) are permitted under the `v1.x` line via minor version bumps.
5. Any deviation from the above requires a new release train (v2.x) with its own recovery + acceptance pack.

---

## Sign-off block

| Deliverable | Status |
|-------------|:------:|
| Backend Acceptance Report | ✅ |
| Complete API Inventory | ✅ |
| Engine Inventory | ✅ |
| Frontend Restoration Report | ✅ |
| End-to-End workflow (31/31) | ✅ |
| One-click deployment verification | ✅ |
| Docker Compose (local + prod) | ✅ |
| VIE integration (no EMERGENT_LLM_KEY) | ✅ |
| JWT + RBAC | ✅ |
| Mongo migration (v01 dump) | ✅ |
| Documentation | ✅ |
| Deployment Guide | ✅ |
| Architecture Diagram | ✅ |
| Recovery Report | ✅ |
| Release Notes | ✅ |

**Reviewer sign-off:** _pending_

Once approved, tag: `git tag strategy-factory@1.1.0 && git push --tags`
