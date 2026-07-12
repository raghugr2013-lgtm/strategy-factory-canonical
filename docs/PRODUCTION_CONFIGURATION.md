# Production Configuration — Strategy Factory v1.0.0

**Target deployment domain:** `https://strategy.coinnike.com`
**VPS:** Contabo, Ubuntu 24.04, 12 vCPU / 48 GB RAM
**Ingress:** existing shared Traefik on the `vqb-network` Docker bridge

Every value below is **environment-driven**. Nothing about the coinnike.com deployment is hardcoded in the application code; the domain, cookies, redirects, CORS, canonical URLs, Traefik labels, and health endpoints all resolve from the `.env` file at deploy time.

---

## 1. Environment variables (canonical `.env` for coinnike production)

Copy `.env.example` → `.env` and set at minimum:

```env
# --- Routing ---
FACTORY_DOMAIN=strategy.coinnike.com
TRAEFIK_WEBSECURE_ENTRYPOINT=websecure
TRAEFIK_CERT_RESOLVER=letsencrypt

# --- Image tagging ---
FACTORY_IMAGE_REPO=strategy-factory
FACTORY_IMAGE_TAG=1.0.0

# --- Data plane (shared) ---
SHARED_MONGO_URL=mongodb://factory_user:<PASSWORD>@mongo:27017/strategy_factory_v1?authSource=admin
FACTORY_DB_NAME=strategy_factory
SHARED_REDIS_URL=redis://redis:6379/0        # optional — leave blank if unused

# --- Auth ---
JWT_SECRET=<openssl rand -hex 32>
JWT_ACCESS_TTL_MIN=60
JWT_REFRESH_TTL_DAYS=7
ADMIN_EMAIL=admin@strategy-factory.local
ADMIN_PASSWORD=<STRONG_PASSWORD>

# --- Web ---
CORS_ORIGINS=https://strategy.coinnike.com

# --- VIE providers (leave blank to disable a given provider) ---
OPENAI_API_KEY=<sk-...>
ANTHROPIC_API_KEY=<sk-ant-...>
GEMINI_API_KEY=<AIz...>
DEEPSEEK_API_KEY=
GROQ_API_KEY=
KIMI_API_KEY=
```

Every remaining value in `.env.example` (model overrides, TTLs, etc.) has sensible defaults. Nothing else needs to be added for a first-run production deploy.

---

## 2. How each production-facing setting derives from the env

| Concern | Source | Notes |
|---|---|---|
| Frontend public URL | `FACTORY_DOMAIN` | Traefik `Host()` rule + `--build-arg REACT_APP_BACKEND_URL=https://${FACTORY_DOMAIN}` on the frontend image (`docker-compose.prod.yml` → `factory-frontend.build.args.REACT_APP_BACKEND_URL`) |
| Backend API base | `REACT_APP_BACKEND_URL` (build-arg) | The frontend calls `${REACT_APP_BACKEND_URL}/api/*` at runtime — resolved to `https://strategy.coinnike.com/api/*` because Traefik routes `PathPrefix(/api)` to `factory-backend` |
| CORS allowed origins | `CORS_ORIGINS` | Read by `backend/app/core/config.py::Settings.cors_origins`; comma-separated list; wildcard `*` supported for dev only |
| TLS certificate | `TRAEFIK_CERT_RESOLVER` | Points at the existing shared Traefik cert resolver (`letsencrypt` by default) |
| Ingress entrypoint | `TRAEFIK_WEBSECURE_ENTRYPOINT` | Which Traefik entryPoint terminates TLS (`websecure` by default) |
| Cookies / auth storage | (n/a — tokens live in localStorage) | Auth is JWT bearer + refresh in headers; no server-set cookies, so no `Domain=` config needed |
| Redirects / canonical URL | (n/a — SPA at root) | The SPA lives at `/`. `/api/*` is Traefik-scoped to the backend. No app-level redirects. |
| Health probe | `/api/health`, `/api/readiness`, `/api/version` | Same paths everywhere; no per-env variation |
| Traefik router names | Fixed (`factory-api`, `factory-ui`) | Router *rules* use `${FACTORY_DOMAIN}` — no other hardcoded hostname anywhere in the compose file |
| Docker image tags | `${FACTORY_IMAGE_REPO}/{backend,vie,frontend}:${FACTORY_IMAGE_TAG}` | Rollback = change `FACTORY_IMAGE_TAG` and rerun `./infra/scripts/deploy.sh --skip-precheck` |
| Version metadata | `BUILD_VERSION`, `BUILD_COMMIT`, `BUILD_DATE` | `deploy.sh` populates these from `VERSION`, `git rev-parse HEAD`, and `date -u`. Surfaced at `/api/version` and in the dashboard footer. |
| Admin bootstrap | `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Idempotent seed on every backend boot (`app/auth/seed.py`) |
| Mongo | `SHARED_MONGO_URL`, `FACTORY_DB_NAME` | Backend uses `MONGO_URL` internally; compose maps `SHARED_MONGO_URL` → `MONGO_URL` |
| Redis (optional) | `SHARED_REDIS_URL` | Backend uses `REDIS_URL`; compose maps `SHARED_REDIS_URL` → `REDIS_URL`. If unset, readiness reports `skipped` (treated as green). |

**No production configuration is hardcoded in the application.** A single-line change in `.env` (`FACTORY_DOMAIN=strategy.coinnike.com` → `factory.acme.com`) is sufficient to redirect the entire stack to a different domain. No code change, no rebuild strictly required beyond re-baking the frontend `REACT_APP_BACKEND_URL` build-arg.

---

## 3. Cleanup performed for the coinnike delivery

Before packaging v1.0.0, the following production-hostility items were removed from the active source tree (see also `docs/AUDIT_REPORT.md §3`):

| Item | Location | Action |
|---|---|---|
| `@emergentbase/visual-edits` dev dependency | `frontend/package.json` | Removed |
| Emergent visual-edits craco plugin wiring | `frontend/craco.config.js` | Removed |
| Meta tag `A product of emergent.sh` | `frontend/public/index.html` | Replaced with `Strategy Factory — internal AI Strategy Engineering Platform` |
| `<script src="https://assets.emergent.sh/scripts/emergent-main.js">` | `frontend/public/index.html` | Removed |
| `#emergent-badge` fixed footer link | `frontend/public/index.html` | Removed |
| PostHog analytics init (`phc_...` project key) | `frontend/public/index.html` | Removed |
| Title `Emergent | Fullstack App` | `frontend/public/index.html` | Changed to `Strategy Factory` |
| `<meta name="robots" content="index,follow">` default | `frontend/public/index.html` | Set to `noindex, nofollow` (internal platform) |
| Emergent preview URL in `frontend/.env` | `frontend/.env` | File removed (production URL comes from Docker build-arg) |
| Placeholder `factory.example.com` in `.env.example` | `.env.example` | Set to `strategy.coinnike.com` |
| Placeholder `CORS_ORIGINS=https://factory.example.com` | `.env.example` | Set to `https://strategy.coinnike.com` |
| Preview-only `backend/.env` and `vie/.env` files | active tree | Removed from delivery — production reads env from Docker Compose env only |

**Verification (run against the delivery tarball after extraction):**
```bash
grep -RIn --exclude-dir={legacy,__pycache__,node_modules,build,.pytest_cache} \
  -e 'emergent' -e 'EMERGENT_LLM_KEY' -e 'emergentagent\.com' -e 'emergent\.sh' \
  -e 'preview\.emergentagent' -e 'posthog' -e 'localhost' -e 'factory\.example\.com' \
  backend/app backend/server.py backend/requirements.txt backend/Dockerfile \
  frontend/src frontend/package.json frontend/craco.config.js frontend/public \
  frontend/Dockerfile frontend/nginx.conf vie infra .env.example README.md
# → empty output
```

The only remaining `example.com` in the active source is `placeholder="you@example.com"` in `LoginPage.jsx` — that is the placeholder text hint inside the email `<Input>` field, not a functional reference. Kept intentionally for UX; irrelevant to the production hostname.

---

## 4. Traefik integration (existing shared instance on the VPS)

Our stack does **not** run Traefik. It joins the shared `vqb-network` and exposes routing labels that the existing Traefik picks up automatically:

- `factory-backend` — routes `Host(${FACTORY_DOMAIN}) && PathPrefix(/api)` to internal port `8001`, priority `100`
- `factory-frontend` — routes `Host(${FACTORY_DOMAIN})` to internal port `80`, priority `10` (SPA fallback)
- `factory-vie` — no routing labels, in-cluster only (`http://factory-vie:8100`)

TLS is issued by whatever cert resolver name lives in `TRAEFIK_CERT_RESOLVER` (default `letsencrypt`). Ensure DNS for `strategy.coinnike.com` points at the VPS BEFORE bringing the stack up so Let's Encrypt can complete the HTTP-01 challenge.

---

## 5. Confirming the coinnike deployment before Stage 2

After `./infra/scripts/deploy.sh` and `./infra/scripts/health.sh` both pass, do the following one-time browser checks:

1. `https://strategy.coinnike.com/` → Strategy Factory SPA loads
2. `https://strategy.coinnike.com/api/health` → `{"status":"ok", ...}` with `version: 1.0.0`
3. `https://strategy.coinnike.com/api/version` → `{"version": "1.0.0", "commit": "<sha>", "build_date": "<iso>"}`
4. Log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` — dashboard loads
5. Providers page → all 6 provider cards render; probe each one you configured a key for

Sign-off criteria: all 5 above green + `health.sh` reports "All checks passed".
