# Sprint 2 · VPS Deployment Package

> **Prepared:** 2026-07-21
> **Target tag:** `v1.3.0-sprint2-complete`
> **Deployment cadence:** ONE coherent update (per operator's post-N1 strategy)
> **Freeze status at time of packaging:** Backend Feature Freeze v1.1.0-stage4 ACTIVE · Design Freeze v1.0 ACTIVE

---

## 1. Package identity

| Field | Value |
|---|---|
| Product | Strategy Factory (`raghugr2013-lgtm/strategy-factory-canonical`) |
| Sprint | 2 |
| Tag to deploy | `v1.3.0-sprint2-complete` |
| Predecessor tag | `v1.2.0-sprint1-complete` |
| Frontend delta | Sprint 1 → 2: `+2 surfaces · +1 adapter · streaming · QA infrastructure` |
| Backend delta | **None** — `v1.1.0-stage4` remains in production |

## 2. Artifacts included

### 2.1 Frontend (React CRA5 · Craco)

- Static build output: `/app/frontend/build/` (produced by `CI=false yarn build`)
  - Main bundle: `build/static/js/main.<hash>.js`
  - CSS: `build/static/css/main.<hash>.css`
  - HTML: `build/index.html`
- Reproducible build: single command `CI=false yarn build`
- Bundle size: **~166.5 kB gzipped** (main.js) — matches Sprint 1 baseline within 1% (streaming + passport additions were offset by legacy v01 purge)
- Node runtime target: **20.20.2**
- Env at build time: only `REACT_APP_BACKEND_URL` (production VPS backend URL)
  - **Optional:** `REACT_APP_WSS_URL` (leave unset until backend exposes WSS)
  - **Optional:** `REACT_APP_STRICT_LIVE=1` (dev diagnostic; leave unset in production)

### 2.2 Backend (unchanged)

- Existing `v1.1.0-stage4` production build remains authoritative.
- **Do not redeploy the backend during this update.** The frontend is fully backwards-compatible with the current backend surface (only `POST /api/auth/login` and `GET /api/strategies` + `GET /api/strategies/{id}` are hit live; everything else stays on fixture fallback).

### 2.3 Storybook artefact (optional · staging only)

- Output: `/app/frontend/storybook-static/` (produced by `yarn build-storybook`)
- Serve at `/design/` on the VPS as a design-review-only preview (behind basic auth if desired).
- Contains 69 stories across 17 components.

## 3. Environment variables

**Required at VPS frontend host:**
```env
REACT_APP_BACKEND_URL=https://<production-backend-domain>
```

**Optional / off by default:**
```env
# Leave unset until backend exposes /api/stream/<channel>.
# REACT_APP_WSS_URL=wss://<production-backend-domain>

# Development diagnostic — surfaces adapter errors instead of fixture fallback.
# REACT_APP_STRICT_LIVE=1
```

**Backend `.env` (unchanged from v1.1.0-stage4):**
```env
MONGO_URL=<existing>
DB_NAME=<existing>
JWT_SECRET=<existing>
```

## 4. Deployment procedure

1. **Tag on Git**
   ```bash
   git tag -a v1.3.0-sprint2-complete -m "Sprint 2 complete · N1-N5 · Backend Feature Freeze preserved"
   git push origin v1.3.0-sprint2-complete
   ```

2. **On the VPS (frontend host)**
   ```bash
   cd /var/www/strategy-factory
   git fetch --tags && git checkout v1.3.0-sprint2-complete
   cd frontend
   yarn install --frozen-lockfile
   CI=false yarn build
   # Serve the fresh `build/` behind nginx / caddy / whatever the VPS uses.
   # If a static server is running with reload watchers, no restart is needed.
   sudo systemctl reload nginx    # or: sudo systemctl restart <frontend-unit>
   ```

3. **Do NOT touch the backend host.** Backend Feature Freeze v1.1.0-stage4 remains in production.

## 5. Rollback plan

- If the smoke test fails, revert to the previous tag:
   ```bash
   git checkout v1.2.0-sprint1-complete
   cd frontend && yarn install --frozen-lockfile && CI=false yarn build
   sudo systemctl reload nginx
   ```
- Because the backend is untouched, rollback is frontend-only and takes <2 minutes.

## 6. Smoke-test checklist (to execute post-deployment)

*Full details in the Production Candidate Report (`SPRINT_2_PRODUCTION_CANDIDATE_REPORT.md`).*

1. VPS URL responds `200` on `/`
2. Login screen renders with the pre-auth stream postmark visible
3. Sign in with `operator@coinnike.com` / `prototype123` → Mission Control loads
4. Left rail shows MASTER BOT entry; navigating there renders identity + plan + decisions
5. `/c/timeline` and `/c/approvals` show a stream postmark that increments its tick attribute within 20 s
6. `/c/strategies` table row click navigates to `/c/strategies/:id`; passport renders all seven sections
7. `⌘K` (or `Ctrl+K` on Linux) opens the palette; focus stays trapped when Tab-cycling
8. Any random unknown route under `/c/*` (e.g., `/c/legacy`) redirects to `/c/mission`
9. Browser console shows only expected `[adapter] … unavailable under Backend Feature Freeze` breadcrumbs; **no uncaught errors**

## 7. Freeze-preservation checks (post-deployment)

- `git diff v1.1.0-stage4 -- backend/` must be **empty** in the production repo.
- `curl -I <VPS_BACKEND>/api/health` must return the same signature as before Sprint 2.
- No new `/api/*` routes must have appeared on the backend.

## 8. Post-deployment monitoring (first 24 h)

- Watch nginx access log for `/c/masterbot`, `/c/strategies/:id`, `/c/timeline` — all should return 200 (deep URLs served via SPA fallback).
- Watch backend for any unexpected 5xx bursts (should be zero because the frontend never calls new endpoints).
- If `sf-auth-unauthorized` events fire in browsers (visible via `RequireAuth` redirect), inspect JWT expiry policy — this is the new N4 401 interceptor and behaves correctly under the current backend.

---

*End of Sprint 2 Deployment Package.*
