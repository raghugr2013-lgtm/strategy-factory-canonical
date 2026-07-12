# Strategy Factory v1.1 — Deployment Guide

**Goal:** stand up the canonical Strategy Factory on a fresh machine using **only** this repository — no manual recovery, no missing pieces.

## Options

| Target | Compose file | Notes |
|--------|--------------|-------|
| Local / laptop dev | `docker-compose.yml` (repo root) | Bundled MongoDB, ports published on the host |
| VPS / production   | `infra/compose/docker-compose.prod.yml` | External Traefik + external MongoDB (`vqb-network`), Prometheus/Loki labels |

Both compose files build the same three images (`factory-backend`, `factory-vie`, `factory-frontend`) plus the `factory-runner` scheduler sibling.

---

## 1 · Local / laptop bring-up (5 minutes)

Prerequisites: Docker Engine ≥ 24 with the Compose plugin, ~4 GB RAM available.

```bash
# 1) Clone
git clone <this-repo> strategy-factory && cd strategy-factory

# 2) Configure environment
cp .env.example .env
# Edit .env at minimum:
#   ADMIN_EMAIL=you@example.com
#   ADMIN_PASSWORD=<strong>
#   JWT_SECRET=$(openssl rand -hex 32)
#   (optional) one of OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY / DEEPSEEK_API_KEY / GROQ_API_KEY / KIMI_API_KEY
#
# Verify ENABLE_LEGACY_ROUTERS=true (default in v1.1).

# 3) Build & boot
docker compose --env-file .env up -d --build

# 4) Verify health (all four should be healthy in <60 s)
docker compose ps
curl -fsS http://localhost:8001/api/health   # -> {"ok":true,...}
curl -fsS http://localhost:8001/api/version  # -> {"version":"1.1.0",...}
curl -fsS http://localhost:3000/healthz      # -> "ok"

# 5) (First-run only) restore the v01 mongodump
#     Skip this step if you already have a database. See §3.
docker exec -i factory-mongo mongorestore --archive < backup/v01_mongodump.archive
```

Open http://localhost:3000 and sign in with the admin credentials from `.env`.

---

## 2 · VPS / production bring-up

Prerequisites:
- Ubuntu 24.04 with Docker + Compose plugin.
- External Traefik reachable on the `vqb-network` docker network.
- External MongoDB reachable at `SHARED_MONGO_URL` (or point at a self-hosted `mongo` service).
- DNS `A` record for `${FACTORY_DOMAIN}` pointing to the VPS.

```bash
git clone <this-repo> /opt/strategy-factory && cd /opt/strategy-factory
cp .env.example .env
# Edit .env — set FACTORY_DOMAIN, SHARED_MONGO_URL, admin creds, JWT_SECRET, provider keys.

docker compose --env-file .env -f infra/compose/docker-compose.prod.yml build
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml up -d

# Health
./infra/scripts/health.sh                                # (if present) or curl the health URLs
curl -fsS https://${FACTORY_DOMAIN}/api/health
```

Traefik picks up the routing labels automatically — the operator UI is served at `https://${FACTORY_DOMAIN}/`, the API at `https://${FACTORY_DOMAIN}/api/*`.

---

## 3 · v01 data restore (optional but recommended)

The v01 mongodump ships in `backup/v01_mongodump.archive` (313k `market_data`, 14 `strategy_library`, 10k `mutation_events`, plus governance/lifecycle history).

```bash
docker exec -i factory-mongo mongorestore \
    --nsInclude "${FACTORY_DB_NAME}.*" \
    --archive < backup/v01_mongodump.archive
```

For the production compose (no bundled mongo), stream the archive into the external Mongo host:

```bash
mongorestore --uri "${SHARED_MONGO_URL}" \
    --nsInclude "${FACTORY_DB_NAME}.*" \
    --archive < backup/v01_mongodump.archive
```

---

## 4 · Post-boot verification checklist

| Check | Command | Expected |
|-------|---------|----------|
| Backend health | `curl -fsS $BASE/api/health` | `{"ok":true}` |
| Version | `curl -fsS $BASE/api/version` | `{"version":"1.1.0",...}` |
| OpenAPI count | `curl -fsS $BASE/api/openapi.json \| jq '.paths \| keys \| length'` | 497 |
| Login | POST `/api/auth/login` with admin creds | `{token, access_token, user, ...}` |
| VIE status | `curl -fsS $BASE/api/llm/diagnostics` (with JWT) | `providers_total: 6` |
| Frontend | `curl -fsS $BASE/healthz` (via Traefik) | `ok` |
| Command OS | Open `/` in browser | AuthGate → sign-in → `/c/dashboard` renders |

---

## 5 · Roll back / reset

```bash
# Stop everything and drop volumes (destroys local data!)
docker compose down -v

# Or, for production (keeps external Mongo intact):
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml down
```

---

## 6 · One-click smoke test (built into the repo)

```bash
./scripts/deploy_verify.sh  # (see /app/scripts/deploy_verify.sh)
```

Runs the full 31-step E2E workflow (`docs/acceptance_v1_1/E2E_WORKFLOW_LOG.md`) against a live stack and prints a pass/fail summary.
