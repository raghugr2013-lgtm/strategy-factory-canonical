# Configuration Contract (A-1)

One configuration contract for all profiles. Dev and prod use **identical
variable names** sourced from `.env`; only the **values** differ.
`CONFIG_VERSION` tracks contract revisions (current: `1`).

## Quick start (development)

```bash
git clone <repo> && cd <repo>
cp .env.example .env
docker compose up -d
```

No edits required — `.env.example` ships working dev values (bundled
MongoDB, recognizable dev JWT secret, admin `admin@strategy-factory.local` / `admin123`).

## The contract

| Variable | Required | Dev value (`.env.example`) | Production value | Consumed by |
|---|---|---|---|---|
| `CONFIG_VERSION` | no (default `1`) | `1` | `1` | backend, runner |
| `SHARED_MONGO_URL` | **yes** | `mongodb://factory-mongo:27017` | `mongodb://factory_user:<pw>@mongo:27017/strategy_factory_v1?authSource=admin` | backend, runner (mapped to internal `MONGO_URL`) |
| `FACTORY_DB_NAME` | no (default `strategy_factory_v1`) | `strategy_factory_v1` | `strategy_factory_v1` | backend, runner (mapped to `DB_NAME`) |
| `SHARED_REDIS_URL` | no (blank = skipped) | *(blank)* | `redis://redis:6379/0` | backend (mapped to `REDIS_URL`) |
| `JWT_SECRET` | **yes** | recognizable dev default | 64-char hex — `openssl rand -hex 32` | backend only (**never** the runner) |
| `JWT_ACCESS_TTL_MIN` | no (default `60`) | `60` | `60` | backend |
| `JWT_REFRESH_TTL_DAYS` | no (default `7`) | `7` | `7` | backend |
| `ADMIN_EMAIL` | no | `admin@strategy-factory.local` | real operator email | backend (idempotent admin seed) |
| `ADMIN_PASSWORD` | no | `admin123` | strong unique password | backend |
| `CORS_ORIGINS` | no (default `*`) | `*` | `https://strategy.coinnike.com` (explicit list) | backend |
| `OPENAI_API_KEY` … `KIMI_API_KEY` | no (blank disables provider) | *(blank)* | real keys as needed | vie |
| `OPENAI_MODEL` … `KIMI_MODEL` | no | sensible defaults | same or pinned | vie |
| `ENABLE_LEGACY_ROUTERS` | no | `true` | `true` | backend, runner |
| `ENABLE_FACTORY_RUNNER` | no | `true` | `true` | backend, runner |
| `ENABLE_DYNAMIC_MARKET_UNIVERSE` | no | `false` | per phase plan | backend |
| `BUILD_VERSION` / `BUILD_COMMIT` / `BUILD_DATE` | no | `1.1.0` / `unknown` / `1970-01-01` | CI-injected | build args + backend |
| `FACTORY_DOMAIN` | prod only | `localhost` (unused in dev) | `strategy.coinnike.com` | Traefik labels |
| `TRAEFIK_WEBSECURE_ENTRYPOINT` | prod only | `websecure` | `websecure` | Traefik labels |
| `TRAEFIK_CERT_RESOLVER` | prod only | `letsencrypt` | `letsencrypt` | Traefik labels |
| `FACTORY_IMAGE_REPO` / `FACTORY_IMAGE_TAG` | prod only | `strategy-factory` / `1.1.0` | pinned release tag | image naming |

Backend containers keep their existing **internal** names (`MONGO_URL`,
`DB_NAME`, `REDIS_URL`); the compose files perform the mapping
(`SHARED_MONGO_URL` → `MONGO_URL`, `FACTORY_DB_NAME` → `DB_NAME`,
`SHARED_REDIS_URL` → `REDIS_URL`). Application code is unchanged by this
contract.

## Fail-fast validation

The backend refuses to start when any required variable is missing or
blank, and reports **all** missing names in one diagnostic:

```
RuntimeError: missing required configuration: JWT_SECRET, MONGO_URL — copy .env.example to .env (see docs/CONFIGURATION.md)
```

Required set: `MONGO_URL`, `DB_NAME`, `JWT_SECRET` (internal names, fed by
the contract variables above).

A weak or default `JWT_SECRET` does **not** block startup (dev must work
out of the box) but logs a warning:

- known dev default → `JWT_SECRET is a known development default…`
- shorter than 32 chars → `JWT_SECRET is shorter than 32 characters…`

## Runtime diagnostics — `GET /api/health/config`

Secret-free configuration diagnostics: booleans/presence only, never
secret values. Example response shape:

```json
{
  "config_version": "1",
  "required": {"MONGO_URL": true, "DB_NAME": true, "JWT_SECRET": true},
  "mongo": {"configured": true, "db_name": "strategy_factory_v1"},
  "redis": {"configured": false},
  "jwt": {"secret_set": true, "secret_is_dev_default": true, "secret_length_ok": true,
          "access_ttl_min": 60, "refresh_ttl_days": 7},
  "admin": {"email_set": true, "password_set": true},
  "cors": {"origins": ["*"]},
  "vie": {"url": "http://factory-vie:8100", "timeout_s": 60},
  "build": {"version": "1.1.0", "commit": "local", "date": "2026-02"},
  "flags": {"enable_legacy_routers": true, "enable_factory_runner": true,
            "enable_dynamic_market_universe": false}
}
```

## factory-runner security posture

The runner service receives **no `JWT_SECRET`** in either compose profile.
It is a heartbeat stub (Phase 0) with no auth surface; when Phase 5 wiring
lands, any new secret requirement must be added to this contract first.

## Production prerequisites (values, not names)

Production reuses the exact same `.env` names. Before `docker compose
--env-file .env -f infra/compose/docker-compose.prod.yml up -d`:

1. `SHARED_MONGO_URL` — external authenticated MongoDB on `vqb-network`, e.g.
   `mongodb://factory_user:<password>@mongo:27017/strategy_factory_v1?authSource=admin`
2. `JWT_SECRET` — generate: `openssl rand -hex 32`
3. `ADMIN_EMAIL` / `ADMIN_PASSWORD` — real operator credentials
4. `CORS_ORIGINS` — explicit origins, e.g. `https://strategy.coinnike.com` (never `*`)
5. `FACTORY_DOMAIN` — public hostname, e.g. `strategy.coinnike.com`
6. `SHARED_REDIS_URL` — set if the shared Redis is in use, else leave blank
7. `FACTORY_IMAGE_TAG` / `BUILD_*` — pin to the release being deployed

## Frontend backend-URL resolution (A-2)

The SPA resolves the backend with **one rule**, implemented once in
`frontend/src/services/api.js` and exported as `API_URL` (helper:
`resolveBackendUrl()`). Every frontend API request resolves through it:

1. `REACT_APP_BACKEND_URL` — if baked into the bundle at build time
   (`docker build --build-arg REACT_APP_BACKEND_URL=https://…` or a CRA
   `.env` file), it wins. Trailing slashes are stripped.
2. Hostname `localhost` / `127.0.0.1` → `http://<hostname>:8001`
   (the canonical backend port: uvicorn, `EXPOSE 8001`, dev compose
   `8001:8001`, Traefik `server.port=8001`).
3. Otherwise `''` → **same-origin relative `/api`**. This is the
   production path and depends on Traefik routing
   `Host(FACTORY_DOMAIN) && PathPrefix(/api)` (priority 100) to
   `factory-backend:8001` — the frontend image needs no baked URL.

The default production build intentionally bakes **no** host
(`ARG REACT_APP_BACKEND_URL=""` in `frontend/Dockerfile`); the prod
compose file passes no build-arg. Do not reintroduce per-file URL
logic in `frontend/src` — import `API_URL` from `services/api` instead.

## `CONFIG_VERSION` semantics

- `1` — this contract (A-1).
- Any future addition/rename/removal of a contract variable increments it.
- The value is reported by `GET /api/health/config` so operators can verify
  which contract a running deployment was configured against.
