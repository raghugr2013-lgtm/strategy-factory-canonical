# Strategy Factory v1.1 — Release Notes

**Tag:** `strategy-factory@1.1.0`
**Freeze date candidate:** Feb 15 2026
**Codename:** *Canonical Recovery*

Strategy Factory v1.1 is the **canonical recovery** of the v0.1 platform, unified under a single reproducible repository. This is a recovery + modernization release; **no product redesign**.

---

## Highlights

- **Original v01 Command OS is the primary UI.** Full Phase U-1 CommandShell/CommandModuleApp/AuthGate/TopTabBar/LifecycleRail/StatusRail restored from source. Interim Phase-1 sidebar shell removed.
- **470 legacy backend endpoints** re-mounted alongside the Phase-1 auth core → **497 total endpoints, 21 modules, 169 engines.**
- **VIE (Vendor Independent Engine) replaces Emergent LLM.** Six providers supported (OpenAI, Anthropic, Gemini, DeepSeek, Groq, Kimi); **zero `EMERGENT_LLM_KEY` references** in the codebase.
- **JWT + RBAC** auth issued by the Phase-1 backend; response schema is dual-shape (Phase-1 flat + v01 nested `{token, user}`) so the v01 client works unchanged.
- **v01 MongoDB dump restored**: 313,777 market bars · 14 strategy_library docs · 10,430 mutation events · 892 lifecycle history rows.
- **Deployment**: single-command Docker Compose for both local (`docker-compose.yml`) and VPS (`infra/compose/docker-compose.prod.yml`); `ENABLE_LEGACY_ROUTERS` defaults to `true`.
- **One-click verify**: `scripts/deploy_verify.sh` runs a 31-step E2E workflow and returns exit-code 0 on green.
- **Lint hooks green**: `ruff` clean on backend; `eslint` zero blocking errors on frontend (per-file ignores only for v01 legacy idioms).

## Compatibility

- Backward compatible with the v01 frontend client — no v01 code was modified for auth or fetch.
- `/api/auth/login` now returns **both** the Phase-1 flat shape (`access_token`, `refresh_token`, `expires_in_min`) **and** the v01 nested alias (`token`, `user`).
- `/api/auth/me` returns both flat and nested (`{...flat, user: {...}}`).

## What's included

- **Source code**: `/app/backend/`, `/app/frontend/`, `/app/vie/`
- **Docker**: `Dockerfile` (backend, frontend, vie), `docker-compose.yml`, `infra/compose/docker-compose.prod.yml`
- **Auth**: JWT + RBAC (admin/developer/researcher/operator/viewer) with refresh rotation, admin-approve signup
- **VIE**: dedicated FastAPI service on `:8100`, provider registry, dispatch API
- **Mongo migration**: `backup/v01_mongodump.archive` + restore instructions
- **Docs**: `docs/acceptance_v1_1/*` (Backend Acceptance, Frontend Restoration, API Inventory, Engine Inventory, E2E Workflow, Deployment Guide, Architecture Diagram, this file)
- **Deploy verifier**: `scripts/deploy_verify.sh`

## Acceptance evidence

| Deliverable | Location |
|---|---|
| Backend Acceptance Report (module × module) | `docs/acceptance_v1_1/BACKEND_ACCEPTANCE_REPORT.md` |
| Complete API Inventory (497 endpoints) | `docs/acceptance_v1_1/API_INVENTORY.md` |
| Engine Inventory (169 engines) | `docs/acceptance_v1_1/ENGINE_INVENTORY.md` |
| Frontend Restoration Report | `docs/acceptance_v1_1/FRONTEND_RESTORATION_REPORT.md` |
| E2E Workflow evidence (31/31 pass) | `docs/acceptance_v1_1/E2E_WORKFLOW_LOG.md` |
| Deployment Guide | `docs/acceptance_v1_1/DEPLOYMENT_GUIDE.md` |
| Architecture Diagram | `docs/acceptance_v1_1/ARCHITECTURE_DIAGRAM.md` |
| Recovery Report | `docs/FINAL_RECOVERY_REPORT.md` |
| Live deploy verification log | `docs/acceptance_v1_1/DEPLOY_VERIFY_RUN.log` |

## Statistics

| Metric | Value |
|--------|-------|
| Frontend files (src/) | 215 tracked · **202 byte-identical to v01**, 13 with a single `/* eslint-disable */` prepend |
| Backend engine files | 169 (`backend/legacy/engines/`) |
| Legacy router files mounted | 83 (`backend/legacy/api/`) |
| Total API endpoints | 497 |
| Total Mongo collections | 57 |
| VIE providers supported | 6 (OpenAI, Anthropic, Gemini, DeepSeek, Groq, Kimi) |
| E2E acceptance workflow | 31 / 31 PASS |
| `EMERGENT_LLM_KEY` references | 0 |

## Known limitations

- **VIE requires provider keys.** Populate any of `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `KIMI_API_KEY` in `.env` (or `/app/vie/.env`). Without at least one, the AI Workforce section renders in “no key” state — this is not a defect.
- **Live broker execution** for cTrader/Windows VPS requires broker credentials outside the platform (Master Bot deployment step).
- **`/api/auto-factory/saved`** filters by `source=auto_factory`; the 14 v01 dump strategies come from an ASF import (no `source` field), so they show `count=0` in that filter but remain queryable via `/api/legacy/strategies` and downstream engines.
- **Auto-factory / gem-factory runs** require at least one VIE provider seeded.

## Upgrade / freeze policy

- This is the **stable, frozen base** for future modules.
- **ArbiCore X**, **GemHunter**, and any additional intelligence modules must be integrated as **separate mounts** on this frozen base — do not modify `backend/legacy/**`, `frontend/src/**`, or the v01 Command OS surface.
- Non-breaking backend augmentations (adding new routers, new VIE providers, new Mongo collections) are allowed under the v1.x line.

## Deploy

```bash
git clone <repo> && cd strategy-factory
cp .env.example .env   # edit admin creds + JWT_SECRET + at least one provider key
docker compose --env-file .env up -d --build
./scripts/deploy_verify.sh   # 31/31 PASS
open http://localhost:3000
```
