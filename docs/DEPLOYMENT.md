# Strategy Factory — Deployment Guide (VPS, Ubuntu 24.04)

**Target:** Contabo VPS · Ubuntu 24.04 · 12 vCPU / 48 GB RAM.
**Assumptions:** Docker + Docker Compose plugin, an existing **Caddy** reverse proxy on the shared `vqb-network` (terminates TLS on :443), a shared MongoDB reachable on that network, and DNS pointing at the VPS for the target domain. See `infra/caddy/README.md` for the Caddyfile contract.

**Reproducibility contract:** running the steps below from a clean checkout on a clean Ubuntu 24.04 host produces a working stack with zero manual code modifications. If any step fails, `deploy.sh` and `health.sh` will surface the reason — no hidden activation gates exist.

---

## 1. Prerequisites (all automated by `bootstrap-vps.sh`)

On a fresh Ubuntu 24.04 VPS:

```bash
sudo ./infra/scripts/bootstrap-vps.sh
```

That single script installs Docker Engine + Compose plugin (official repo, GPG-verified), enables and starts the daemon, creates the `vqb-network` if missing, and adds the invoking user to the `docker` group. Idempotent — safe to re-run.

**Log out and back in** after the first run so the `docker` group membership takes effect.

Manually, if you prefer:
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git curl jq openssl
sudo usermod -aG docker "$USER" && newgrp docker
docker network inspect vqb-network >/dev/null 2>&1 || docker network create vqb-network
```

---

## 2. Clone + configure

```bash
cd /opt
git clone <your-repo-url> strategy-factory
cd strategy-factory

cp .env.example .env
$EDITOR .env
```

**Minimum values that MUST be changed in `.env`:**
- `FACTORY_DOMAIN` — the FQDN Caddy terminates TLS on
- `JWT_SECRET` — 64-char hex; generate with `openssl rand -hex 32`
- `ADMIN_EMAIL` and `ADMIN_PASSWORD`
- `SHARED_MONGO_URL` — includes user, password, `?authSource=admin`
- `CORS_ORIGINS` — should be `https://${FACTORY_DOMAIN}`
- Any provider API keys you want VIE to use (missing keys → provider disabled, no crash)

Optional:
- `TRAEFIK_CERT_RESOLVER`, `TRAEFIK_WEBSECURE_ENTRYPOINT` — INERT under Caddy (retained only for a future Traefik migration; see `infra/traefik/README.md`)
- Provider model overrides (`OPENAI_MODEL`, `ANTHROPIC_MODEL`, …)

```bash
chmod 600 .env
```

---

## 3. Deploy

Two commands:

```bash
./infra/scripts/precheck.sh   # fail-fast environment validation
./infra/scripts/deploy.sh      # network → build → up → health
```

`deploy.sh` calls `precheck.sh` internally, so you can skip the explicit call. Precheck verifies:

- Every required `.env` variable is set (rejects `CHANGE_ME` placeholders)
- Docker daemon reachable, Compose plugin present
- `vqb-network` exists
- `SHARED_MONGO_URL` reachable via `mongosh` ping
- `SHARED_REDIS_URL` reachable if configured
- DNS resolves `FACTORY_DOMAIN`
- Caddy container detected on `vqb-network` (the actual production reverse proxy — see `infra/caddy/README.md`)

If any check fails, deploy refuses to proceed and prints the exact failure. No half-built state.

Once precheck passes, `deploy.sh`:
1. Verifies `vqb-network` exists (creates if not)
2. Builds `factory-backend`, `factory-vie`, `factory-frontend` images (multi-stage)
3. Brings up the stack (`docker compose up -d`)
4. Runs `health.sh`

Version metadata (VERSION + git commit + build date) is baked into all three images at build time and exposed at `GET /api/version`.

---

## 4. Verify

```bash
./infra/scripts/health.sh
```

Green output = production ready. It checks:
- Container states and Docker healthchecks (backend, VIE, frontend)
- In-cluster `GET /api/health`
- Backend → VIE reachability (`http://factory-vie:8100/health`)
- Frontend nginx `/healthz`
- Aggregated `GET /api/readiness` — reports Mongo, VIE, and **Redis** status separately (`green` / `yellow` / `red` / `skipped`)
- **Public** `https://${FACTORY_DOMAIN}/api/health` (through Caddy + TLS)
- **Public** `https://${FACTORY_DOMAIN}/` (SPA index)

Redis is optional — if `SHARED_REDIS_URL` is not set, readiness reports `skipped` and the overall status stays green.

---

## 5. First login

Visit `https://${FACTORY_DOMAIN}/login`. Sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`. From **Admin → Users** you can create the rest of the team with roles from the RBAC matrix (see `docs/AUTH_AND_RBAC.md`).

The admin seed is idempotent. Re-running `deploy.sh` with a different `ADMIN_PASSWORD` updates the existing account's hash in place.

---

## 6. Backups + restore

```bash
# nightly cron on VPS
./infra/scripts/backup.sh /var/backups/strategy-factory
```

Restore from an archive:

```bash
./infra/scripts/restore.sh /var/backups/strategy-factory/strategy_factory-YYYYMMDD_HHMMSS.archive.gz
```

Both scripts run against the shared MongoDB via `SHARED_MONGO_URL`.

---

## 7. Zero-downtime upgrade

```bash
git pull
./infra/scripts/deploy.sh
```

Docker Compose rebuilds and rolls the containers one-by-one. Caddy drains an unhealthy container automatically once the Docker healthcheck flips (Caddy's `reverse_proxy` treats a container without a healthy answer as unavailable and retries the next attempt).

---

## 8. Rollback

Tag your images with immutable versions (deploy.sh already tags them with `FACTORY_IMAGE_TAG`) and roll back with:

```bash
FACTORY_IMAGE_TAG=1.0.0 ./infra/scripts/rollback.sh
```

---

## 9. Diagnostics

```bash
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml logs -f factory-backend
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml logs -f factory-vie
docker inspect factory-backend --format='{{json .State.Health}}' | jq
curl -fsS https://${FACTORY_DOMAIN}/api/readiness | jq
```

If `readiness` reports VIE `red`, tail `factory-vie` logs and confirm at least one provider env key is set.

If Mongo goes red, verify from a shell:

```bash
docker exec factory-backend python -c "
import os, pymongo
print(pymongo.MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000).admin.command('ping'))
"
```

---

## 10. What we deliberately do NOT ship

- No Mongo container (uses shared)
- No Redis container (unused today; wired through the env variable for future features)
- No Prometheus/Grafana/Loki containers (reused from the shared monitoring stack; our containers carry `prometheus.scrape=true` + `logging=promtail` labels)
- No certbot/letsencrypt (Caddy owns TLS — auto-cert via Let's Encrypt)
- No `factory-runner` sibling scheduler in Phase 1 (Stage 2 module preserved in `backend/legacy/`)
- No Emergent runtime hooks anywhere

**Reproducibility check on a clean VPS:**
1. Fresh Ubuntu 24.04 + Docker
2. `docker network create vqb-network`
3. Shared Mongo + Caddy started separately (Caddy attached to `vqb-network`)
4. Clone repo, `cp .env.example .env`, edit values, run `./infra/scripts/deploy.sh` → green.

No source patches. No hidden ENV activation steps. No documentation-only setup. If it doesn't just work, `health.sh` tells you exactly what failed.
