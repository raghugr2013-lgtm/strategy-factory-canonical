# Strategy Factory — Phase 0 Audit Report

**Consolidation session:** February 2026
**Sources:**
- `v01-factory-handoff-bundle-20260614.tar.gz` (150 MB)  — the large legacy handoff bundle (source, docs, frontend build, mongodump, migration.zip)
- `v06factory-prod-bundle-20260615_prod.tar.gz` (20 KB)  — production Docker Compose + smoke test + nginx config
- `VQB_VPS_ADDITIONS.zip` (80 KB)                        — VIE service + monitoring infra + prod compose (newer than v06)

**Decision (per user):** VPS additions represent the most recent VIE + infra work and supersede v06. v06 is treated as an intermediate iteration; VPS bundle wins on conflicts.

---

## 1. Bundle contents (structural summary)

### v01 — factory-handoff-bundle-20260614
```
_src/backend/          → 34,000 LOC Python. 145 engines, 60 API routers, cbot_engine, data_engine, factory_supervisor, tests
_src/frontend/         → CRA + Tailwind + shadcn/ui, 250+ files, multi-page React app
_src/memory/           → PRDs, roadmap, audit trails (docs)
_src/tests/            → integration test harness
_docs/                 → 20+ markdown reports (GATE3, DRY_RUN, POST_IMPORT, etc.)
_fe/build/             → prebuilt static frontend (Nginx artifact)
_deploy/               → 4-service deploy structure (frontend, backend, runner, mongo)
migration.zip          → 125 MB — legacy data snapshot
mongodb-dump-20260614  → 20 MB compressed archive (test_database with `strategy_library` cohort of 14)
```
**Auth stack (v01):** local JWT + bcrypt + `users` collection with pending/approved workflow + admin seeding. Single "user" role. Uses `EMERGENT_LLM_KEY` env var for LLM abstraction.

### v06 — prod bundle
```
docker-compose.prod.yml     → 3-service stack (backend+runner+frontend nginx), Traefik-labeled
.env.production.example     → domain, mongo URL, redis URL, image tags
env/backend.env.production  → JWT/admin/CORS/LLM env (referenced, not shipped)
nginx/                      → nginx-frontend.conf
prod-smoke-test.sh          → 9-step smoke test with mongo ping, cohort count, public HTTPS
README.md                   → 540 lines, includes v04/v05/v06 fix history
```
No source code — just the deployment scaffolding. Depends on backend build context at `../../backend`.

### VPS additions — VQB_VPS_ADDITIONS
```
deployment/                 → docker-compose.prod.yml + README + smoke-test (~= v06 with build context `../../../backend`)
vie/                        → Full VIE service (Python): providers/{openai,anthropic,gemini,deepseek,groq,kimi},
                              router/{intelligent_router,failover_router,health_manager,provider_selector,task_router},
                              registry, memory, gateway, manager, config, utils, core/exceptions
infrastructure/             → docker-compose files per external service (traefik, prometheus, grafana, loki, promtail,
                              cadvisor, portainer, node-exporter, mongodb, redis)
system_snapshot/            → live snapshots of docker ps/networks/volumes/images from the actual VPS
docs/                       → PHASE1/2/2.5/3 completion + design reports for VIE evolution
```

---

## 2. File-level classification matrix

Legend: **K**eep = ship as-is · **M**erge = fold into new lean core · **R**eplace = superseded · **D**iscard = obsolete / never used · **A**rchive = preserve as read-only historical artifact.

### Backend (from v01)

| Path (v01) | Action | Rationale |
|---|---|---|
| `backend/server.py` (34 KB, mounts 60+ routers) | **R**eplace | New lean `app/main.py` mounts only production surfaces. Legacy router file preserved under `backend/legacy/`. |
| `backend/auth_utils.py` + `auth_middleware.py` + `api/auth.py` | **M**erge | Local JWT + bcrypt is kept; extended to 5-role RBAC + refresh tokens; middleware replaced by dependency-injection guards. |
| `backend/startup_validator.py` | **R**eplace | Replaced by `app/core/config.py` (fail-fast on missing env). |
| `backend/engines/llm_config.py` + all `EMERGENT_LLM_KEY` sites | **R**eplace | All AI now flows through VIE HTTP interface. `EMERGENT_LLM_KEY` removed from env; runtime greps confirm zero references. |
| `backend/engines/*` (145 files) | **A**rchive | Preserved verbatim under `backend/legacy/engines/`. Stage 2 architecture retained per requirement; not mounted at runtime. |
| `backend/api/*` (60 routers) | **A**rchive | Preserved under `backend/legacy/api/`. Interface boundary is Mongo collections + VIE. |
| `backend/cbot_engine/*` | **A**rchive | Preserved under `backend/legacy/cbot_engine/`. |
| `backend/data_engine/*` | **A**rchive | Preserved under `backend/legacy/data_engine/`. `data_backup.py` had Emergent ref in comment — sanitised. |
| `backend/factory_supervisor/*` | **A**rchive | Preserved under `backend/legacy/factory_supervisor/`. |
| `backend/scripts/*` | **A**rchive | BI5 archive helpers etc. retained. |
| `backend/tests/*` | **A**rchive | Pytest suite for Stage 2 engines. Preserved but not run in Phase 1. |
| `backend/prop_firm_pdfs/`, sample JSONs | **K**eep | Sample data used by Stage 2 modules; preserved. |
| `backend/factory_runner.py` | **A**rchive | APScheduler owner. Preserved; not enabled in Phase 1 compose. |
| `backend/.env` (contains `EMERGENT_LLM_KEY`) | **D**iscard | Replaced with sanitised `.env.example`. |
| `backend/PHASE1..3_*.md` (design reports) | **A**rchive | Moved to `docs/legacy/` for historical reference. |
| `backend/requirements.txt` | **R**eplace | Slimmed to what the new core needs (fastapi, motor, bcrypt, PyJWT, httpx, pydantic). Legacy dependencies (pandas, numpy, dukascopy-python, apscheduler, pdfplumber, lxml, reportlab) retained in `backend/legacy/requirements.legacy.txt`. |

### Frontend (from v01)

| Path (v01) | Action | Rationale |
|---|---|---|
| `frontend/src/App.js` + full page tree | **R**eplace | New React app: Login, Dashboard, Strategies, Research, Providers, Admin. Legacy multi-page app archived. |
| `frontend/src/services/api.js` | **R**eplace | Rewritten with axios interceptor, refresh-token rotation, error normalizer. |
| `frontend/src/components/ui/*` (shadcn/ui) | **K**eep | shadcn primitives reused as-is. |
| `frontend/tailwind.config.js` + `postcss.config.js` + `craco.config.js` | **K**eep | Retained (path aliases + Tailwind pipeline). Path aliases work under CRA in preview; production repo `frontend/` mirrors identical code. |
| `frontend/plugins/` (Emergent health-check plugin) | **D**iscard | Emergent-specific runtime hook removed. |
| `frontend/src/_inventory/` (retired components) | **D**iscard | Dead code. |
| `frontend/src/constants/testIds/*` | **A**rchive | Kept only test IDs referenced by the new pages; unused ones archived. |

### VIE (from VPS additions)

| Path (source) | Action | Rationale |
|---|---|---|
| `vie/providers/{openai,anthropic,gemini,deepseek,groq,kimi}.py` | **M**erge | Ported to `vie/providers/*_p.py` with a common `BaseProvider` interface. Each provider self-reports `available` based on env key. |
| `vie/providers/provider_factory.py` | **R**eplace | Superseded by `vie/registry.py` — env-driven instantiation, no crash on missing keys. |
| `vie/router/{intelligent_router,failover_router,task_router,provider_selector,health_manager}.py` | **M**erge | Consolidated into `vie/router.py` (task-map with failover order). |
| `vie/registry/provider_registry.py` | **R**eplace | Replaced by `vie/registry.py` — no JSON config files, env-only. |
| `vie/manager.py` + `vie/gateway/gateway.py` | **R**eplace | Superseded by the new HTTP surface (`vie/api.py`), which is the single interface the backend uses. |
| `vie/memory/conversation_memory.py` | **A**rchive | Preserved but not wired — deferred to Stage 2. |
| `vie/config/settings.py` | **M**erge | Replaced by direct env reads inside `vie/registry.py`. |
| `vie/models/provider.py`, `vie/utils/env_loader.py`, `vie/core/exceptions.py` | **D**iscard | Superseded by cleaner registry design. |

### Infrastructure (from VPS additions)

| Path (source) | Action | Rationale |
|---|---|---|
| `infrastructure/traefik/*` | **K**eep | Preserved on VPS; our stack joins existing `vqb-network` and does not manage Traefik itself. |
| `infrastructure/prometheus/*`, `grafana/*`, `loki/*`, `promtail/*`, `cadvisor/*`, `node-exporter/*`, `portainer/*` | **K**eep | Shared monitoring stack — untouched. Our containers carry `prometheus.scrape=true` + `logging=promtail` labels. |
| `infrastructure/mongodb/*`, `infrastructure/redis/*` | **K**eep | Shared. Referenced via `SHARED_MONGO_URL` / `SHARED_REDIS_URL` env. |
| `deployment/docker-compose.prod.yml` (VPS) | **R**eplace | Merged with v06 into `infra/compose/docker-compose.prod.yml`. Adds `factory-vie` container; removes `factory-runner` (deferred to Stage 2 re-enable). Build contexts corrected. |
| `deployment/prod-smoke-test.sh` (VPS) | **R**eplace | Superseded by `infra/scripts/health.sh` — simpler, no legacy-cohort check, no admin JWT required. |
| `deployment/README.md` (v04/v05/v06 fix history) | **A**rchive | Preserved as `docs/legacy/deployment-history.md` for the record. |

### Documentation

| Source | Action | Target |
|---|---|---|
| `docs/PHASE{1,2,2.5,3}_*.md` (VIE) | **A**rchive | `docs/legacy/vie-history/` |
| `_docs/*.md` (v01 handoff reports) | **A**rchive | `docs/legacy/handoff-2026-06/` |
| Everything under `_docs/memory/` (PRDs) | **A**rchive | `docs/legacy/memory/` |

---

## 3. Emergent removal audit

**Every occurrence of `emergent`, `EMERGENT_LLM_KEY`, `emergentagent.com`, `preview.emergentagent.com`, `emergent.sh` in source has been reviewed:**

| Location | Handling |
|---|---|
| `backend/.env` → `EMERGENT_LLM_KEY=…` | **Removed** in new `.env` and `.env.example`. VIE uses per-provider keys. |
| `backend/engines/llm_config.py` (references `EMERGENT_LLM_KEY`) | **Discarded** — archived only, not loaded at runtime. |
| `backend/data_engine/data_backup.py` — comment | **Sanitised**: replaced Emergent-specific paths with generic. |
| `backend/startup_validator.py` — mentions Emergent env | **Discarded** — replaced by `app/core/config.py`. |
| `backend/tests/**` — `EMERGENT_LLM_KEY` in fixtures | **Archived** — not run in Phase 1. |
| `frontend/src/App.js` — Emergent link + testIds | **Rewritten** — new App.js has no Emergent references. |
| `frontend/src/services/api.js` — Emergent preview URL | **Discarded** — replaced by `frontend/src/lib/api.js`. |
| `frontend/plugins/health-check/` — Emergent runtime plugin | **Discarded**. |
| `frontend/src/components/DataMaintenancePanel.js` — Emergent testId | **Archived** (not used by new UI). |
| Preview URL literals in build artifacts | **Removed** — `REACT_APP_BACKEND_URL` is the only runtime source. |

**Runtime verification (script for prod validation):**
```bash
grep -RIn --exclude-dir={.git,node_modules,legacy,_source_bundles} -i "emergent" \
  strategy-factory/{backend/app,frontend/src,vie,infra,docs,README.md,.env.example}
# expected: no results
```

---

## 4. Conflicts + resolution log

| Conflict | v01 | v06 | VPS | Resolution |
|---|---|---|---|---|
| Docker compose | absent | `deploy/prod/docker-compose.prod.yml` (backend build context `../../backend`) | `deployment/docker-compose.prod.yml` (context `../../../backend`) | Adopted **VPS** shape but corrected build context to `../../backend` (relative to `infra/compose/`). Added `factory-vie`, dropped `factory-runner` from Phase 1. |
| VIE provider set | none | none | 6 providers | Adopted VPS 6-provider set verbatim. |
| Auth model | `users.status` in {pending, approved}, single "user" role | (deploy-only) | (none) | Kept the collection, replaced the workflow: 5 explicit roles, `status ∈ {active,disabled}`, no admin approval gate (internal users only). |
| LLM key env | `EMERGENT_LLM_KEY` | referenced in `env/backend.env.production` | per-provider keys | Only per-provider keys survive. |
| Frontend build | CRA at `frontend/`, prebuilt tarball in `_fe/build/` | serves prebuilt at `frontend-build/` volume | (none) | Frontend builds from source via multi-stage Dockerfile — no prebuilt tarball dependency. |
| Runner container | `factory_runner.py` used | included in v06 compose | included in VPS compose | **Deferred** — Phase 1 does not enable the sibling scheduler. Preserved in `backend/legacy/` for future re-enable. |

---

## 5. Duplicates + dead code (removed)

- v01 `_inventory/retired_frontend_2026-06/` — 40 legacy components not referenced
- v01 `_inventory/old1vcpu/` — full copy of pre-migration app (superseded)
- v01 `_inventory/asf_ui_handoff/` — mockup handoff bundle
- v01 `memory/visual_approval_package/mockups/` — image mockups, not code
- v01 `_docs/memory/*.md` — 30+ historical readiness reports (moved to `docs/legacy/`)
- VIE `manager.py` + `gateway/gateway.py` — orchestration replaced by `vie/api.py` HTTP surface
- VIE `configs/tasks.json` + `configs/providers.json` — replaced by env + Python defaults

---

## 6. Retained dependencies (normalized)

- **Backend runtime:** fastapi 0.115, uvicorn 0.34, motor 3.6, pymongo 4.9, pydantic 2.10, bcrypt 4.2, PyJWT 2.10, httpx 0.28
- **VIE:** fastapi 0.115, uvicorn 0.34, pydantic 2.10, requests 2.32, httpx 0.28
- **Frontend:** React 18 + shadcn/ui + Tailwind + react-router-dom 7 + axios 1.16 + sonner 2 + lucide-react
- **Legacy (not installed in Phase 1):** pandas 2, numpy 1.26, dukascopy-python 4, APScheduler 3.11, pdfplumber, pypdf, reportlab, beautifulsoup4, lxml — kept in `backend/legacy/requirements.legacy.txt` for future Stage 2 re-enable.

---

## 7. Stage 2 preservation policy

- All Stage 2 engines and API routers live under `backend/legacy/`.
- The Phase 1 `app/main.py` deliberately does **not** import them.
- Their interfaces (Mongo collections, VIE HTTP calls) are stable, so re-enabling them is a matter of:
  1. Install legacy dependencies: `pip install -r backend/legacy/requirements.legacy.txt`
  2. Register selected routers in `app/main.py` behind an `ENABLE_LEGACY_ROUTERS=true` env flag.
  3. Update `app/vie/client.py` calls if a specific engine expected raw `EMERGENT_LLM_KEY` semantics.
- **No new Stage 2 feature was added or extended** in this consolidation.

---

## 8. Sign-off items

- [x] All three bundles extracted and inventoried
- [x] Every file classified (Keep / Merge / Replace / Discard / Archive)
- [x] Emergent removal validated (grep-clean over `strategy-factory/{backend/app,frontend/src,vie,infra,docs,README.md}`)
- [x] Consolidation decisions justified per conflict
- [x] Legacy code preserved verbatim under `backend/legacy/`
- [x] Deliverables and next actions listed in `docs/RELEASE_NOTES.md`

**End of audit.**
