# Strategy Factory — Production Deployment (canonical repo)

## Problem statement (verbatim scope)
Complete production deployment ONLY of the canonical repository
`raghugr2013-lgtm/strategy-factory-canonical` (branch `main`) to
`https://strategy.coinnike.com` on VPS `144.91.78.175` (Ubuntu 24.04,
Docker installed, images build, DNS live).

Blockers on entry:
1. Production MongoDB not configured (backend still points at dev
   `mongodb://factory-mongo:27017` bundled Mongo).
2. Reverse proxy (Caddy) not configured.
3. Production `.env` at repo root missing.

Do **not** merge the new UI from the other repo until this stack is
green.

## User choices captured (session #1)
- Deployment location: work on VPS through connected repo; I provide
  files + commands, user executes them.
- MongoDB: self-hosted container on same VPS, persistent Docker volume,
  attached to `vqb-network` with DNS alias `factory-mongo`, root auth.
- Reverse proxy: Caddy 2 (`caddy:2-alpine`) with automatic Let's
  Encrypt HTTPS, attached to `vqb-network`.
  - `/api/*` → `factory-backend:8001`
  - `/` → `factory-frontend:80`
- DNS: confirmed live for `strategy.coinnike.com → 144.91.78.175`.
- Let's Encrypt email: user left `<YOUR EMAIL ADDRESS>` placeholder —
  must be replaced in `/opt/caddy/Caddyfile` before Caddy starts.

## Architecture confirmed against repo
- `infra/compose/docker-compose.prod.yml` deliberately has NO Mongo
  and NO reverse proxy — both are expected as "externally managed
  shared services" on `vqb-network` (see `infra/caddy/README.md`).
- Precheck (`infra/scripts/precheck.sh`) requires: `SHARED_MONGO_URL`
  reachable via `docker exec`, DNS resolution of `FACTORY_DOMAIN`, and
  a `Caddy` (or Traefik) container on `vqb-network`.
- Deploy (`infra/scripts/deploy.sh`) is the single entry point: it
  runs precheck → builds images → `docker compose up -d` → attaches
  factory-backend + factory-runner to `vqb-network` → runs `health.sh`.

## What was implemented in session #1

**No code / no repo changes.** Only external infra artifacts + a
production `.env`, per the repo's own contract:

1. `/opt/factory-mongo/docker-compose.yml`  — Mongo 7 with `--auth`,
   attached to `vqb-network` (alias `factory-mongo`), volumes
   `factory_mongo_data` (data) and `factory_mongo_backup` (dumps),
   NOT published to host.
2. `/opt/factory-mongo/.env`  — root user + freshly generated
   password (`AhF8sW5jLFkITuzDQzrWSLRC`).
3. `/opt/caddy/docker-compose.yml`  — `caddy:2-alpine`, ports 80/443
   TCP + 443 UDP (HTTP/3), `vqb-network`, persistent volumes for
   `caddy_data` / `caddy_config` / `caddy_logs`.
4. `/opt/caddy/Caddyfile`  — verbatim reverse-proxy contract from
   `infra/caddy/README.md`, with `email` placeholder for ACME.
5. `/opt/strategy-factory/.env`  — production values:
   - `FACTORY_DOMAIN=strategy.coinnike.com`
   - `CORS_ORIGINS=https://strategy.coinnike.com`
   - `SHARED_MONGO_URL=mongodb://root:AhF8sW5jLFkITuzDQzrWSLRC@factory-mongo:27017/?authSource=admin`
   - `JWT_SECRET` = fresh 64-char hex
   - `ADMIN_EMAIL=admin@coinnike.com`, `ADMIN_PASSWORD=Tmn0SECEyDxV1KqfbHMw`
6. `/opt/factory-bootstrap.sh` — idempotent one-shot script that
   spins up Mongo → Caddy → runs `./infra/scripts/deploy.sh` → runs
   `./infra/scripts/health.sh`.
7. `DEPLOY_RUNBOOK.md` — step-by-step + troubleshooting.

All artifacts bundled at `/app/deploy-artifacts/` and
`/app/deploy-artifacts.tar.gz`.

## Verification gates (to be run by user on VPS)
- `./infra/scripts/precheck.sh` → precheck OK
- `./infra/scripts/health.sh` → all checks passed
- `curl -fsS https://strategy.coinnike.com/api/health` → HTTP 200
- `curl -fsS https://strategy.coinnike.com/` → HTTP 200
- `/api/readiness` → `mongo=green`, `vie=green`, `redis=skipped`

## Backlog (out-of-scope for this session; queued for session #2)
- Controlled migration of the newer UI from the separate repo
  (deferred until this stack is green).
- Optional: Redis addition for the "skipped" readiness signal.
- Optional: monitoring stack (Prometheus/Grafana/Loki/Promtail — the
  labels are already in the prod compose).
- Rotate `ADMIN_PASSWORD` after first successful login.

## Files touched
- Zero changes to the canonical repo (compose / scripts / code).
- New files under `/app/deploy-artifacts/` — to be copied to the VPS.

## Session log
- 2026-01: session #1 — production infra artifacts prepared; awaiting
  user to execute the runbook on `144.91.78.175`.
