# Strategy Factory — Deployment Operations Manual

**Single source of truth for production deployment, updates, health,
rollback, disaster recovery, and troubleshooting.**

- Version: 1.0
- Applies to: `strategy-factory-canonical` @ `main` (v1.1.0+)
- Supersedes: `docs/DEPLOYMENT.md` (kept for historical reference),
  `docs/DEPLOYMENT_ASSUMPTIONS.md`, `docs/POST_FREEZE_DEPLOYMENT_CHECKLIST.md`,
  `memory/VPS_DEPLOYMENT_RUNBOOK.md`.
- Companion documents: `docs/DEPLOYMENT_ARCHITECTURE_REVIEW.md` ·
  `docs/DEPLOYMENT_MIGRATION_PLAN.md`.

---

## Table of contents

1. [Canonical paths & inventory](#1--canonical-paths--inventory)
2. [Architecture](#2--architecture)
3. [Docker operations](#3--docker-operations)
4. [Container lifecycle & recovery](#4--container-lifecycle--recovery)
5. [MongoDB — backup, restore, upgrade](#5--mongodb--backup-restore-upgrade)
6. [Caddy — TLS & reverse proxy](#6--caddy--tls--reverse-proxy)
7. [Logging](#7--logging)
8. [Monitoring & health verification](#8--monitoring--health-verification)
9. [Disaster recovery](#9--disaster-recovery)
10. [Release management](#10--release-management)
11. [Security](#11--security)
12. [Operational runbooks](#12--operational-runbooks)
13. [Golden rules (never break these)](#13--golden-rules-never-break-these)

---

## 1 · Canonical paths & inventory

### 1.1 · VPS paths

| Path | Purpose |
|------|---------|
| `/opt/strategy-factory` | Canonical repo checkout. Symlink to `/home/raghu/projects/strategy-factory-canonical`. |
| `/opt/strategy-factory/.env` | Production env file (chmod 600). Consumed by the `strategy-factory` compose project. |
| `/opt/factory-mongo/` | Out-of-repo compose project for self-hosted MongoDB. |
| `/opt/factory-mongo/.env` | `MONGO_ROOT_USERNAME` + `MONGO_ROOT_PASSWORD` (chmod 600). |
| `/opt/caddy/` | Out-of-repo compose project for Caddy reverse proxy. |
| `/opt/caddy/Caddyfile` | TLS + routing config. |
| `/opt/factory-rollback/<UTC_TS>/` | Rollback snapshots written by `factory-bootstrap.sh` before each deploy. |
| `/var/backups/strategy-factory/` | Default `infra/scripts/backup.sh` output directory. |
| `/var/log/caddy/strategy-factory.access.log` | Caddy access log for `/api/*`. |

### 1.2 · Docker Compose projects

| Compose project name | File | Manages |
|----------------------|------|---------|
| `strategy-factory` | `/opt/strategy-factory/infra/compose/docker-compose.prod.yml` | factory-backend · factory-vie · factory-frontend · factory-runner |
| `factory-mongo`    | `/opt/factory-mongo/docker-compose.yml`                        | factory-mongo |
| `caddy`            | `/opt/caddy/docker-compose.yml`                                 | caddy |

### 1.3 · Container inventory

| Container | Image | Exposes | Persistent state |
|-----------|-------|---------|------------------|
| `factory-backend`  | `strategy-factory/backend:${FACTORY_IMAGE_TAG}`  | `:8001` (internal) | none |
| `factory-vie`      | `strategy-factory/vie:${FACTORY_IMAGE_TAG}`      | `:8100` (internal) | none |
| `factory-frontend` | `strategy-factory/frontend:${FACTORY_IMAGE_TAG}` | `:80`   (internal) | none |
| `factory-runner`   | `strategy-factory/backend:${FACTORY_IMAGE_TAG}`  | heartbeat file only | volume `factory_bi5` |
| `factory-mongo`    | `mongo:7`                                        | `:27017` (internal) | volumes `factory_mongo_data`, `factory_mongo_backup` |
| `caddy`            | `caddy:2-alpine`                                 | `:80`, `:443`, `:443/udp` (host) | volumes `caddy_data`, `caddy_config`, `caddy_logs` |

### 1.4 · Network topology

- One external Docker network: **`vqb-network`**. All six containers
  attach to it and reach each other by name (`factory-backend`,
  `factory-mongo`, etc.). No other network is used.
- Only Caddy binds host ports (80 / 443). Every other service is
  `expose:`-only.
- MongoDB is never reachable from the public internet.

### 1.5 · Volume mappings

| Volume | Owner | Contents | Rebuild-safe |
|--------|-------|----------|--------------|
| `factory_mongo_data`   | factory-mongo | `/data/db` — MongoDB dbPath | **YES** — survives all compose recreates |
| `factory_mongo_backup` | factory-mongo | `/data/backup` — in-container backups | YES |
| `factory_bi5`          | factory-runner | `/app/data/bi5` — BI5 tick data | YES |
| `caddy_data`           | caddy | `/data` — ACME certs, keys | YES (cert renewal state) |
| `caddy_config`         | caddy | `/config` — autosave | YES |
| `caddy_logs`           | caddy | `/var/log/caddy` — access logs | YES |

### 1.6 · Environment variable strategy

| File | Owner | Consumed by |
|------|-------|-------------|
| `/opt/strategy-factory/.env` | Ops | `strategy-factory` compose project (all four factory-* services) |
| `/opt/factory-mongo/.env`    | Ops | `factory-mongo` compose project only |
| Repo `.env.example`          | Repo | Template for both the dev overlay and the production `.env` |

**Rule:** `docker compose --env-file <FILE>` supplies only
*interpolation* values. A variable listed in `.env` but not enumerated
in the compose file's `environment:` block never reaches the
container's `os.environ`. Always add new flags in **both** places
(see the comment block in `infra/compose/docker-compose.prod.yml` at
lines 80–91).

---

## 2 · Architecture

### 2.1 · Deployment architecture

```
  Public internet
        │  https://strategy.coinnike.com  (443/tcp, 443/udp, 80/tcp)
        ▼
  ┌────────────────────────┐
  │  Caddy (host: 80/443)  │  ← auto-TLS via Let's Encrypt (HTTP-01)
  │  compose project: caddy│    Certs stored on volume `caddy_data`
  └───────────┬────────────┘
              │
      vqb-network (Docker user-defined bridge, external)
              │
   ┌──────────┼───────────────────────┬──────────────────────┐
   ▼          ▼                       ▼                      ▼
 factory-  factory-               factory-             factory-mongo
 frontend  backend                vie                   (mongo:7 --auth)
  (nginx :80) (fastapi :8001)     (fastapi :8100)      compose project: factory-mongo
   │           │  │                                        ▲
   │           │  └──── uses SHARED_MONGO_URL ─────────────┘
   │           │
   │           └────────────► factory-runner (heartbeat / APScheduler)
   │
   └── /*  served by SPA, /api/* proxied to factory-backend by Caddy
```

### 2.2 · Directory structure (repo)

```
/opt/strategy-factory/
├── docker-compose.yml              # DEV overlay only (see §3.6)
├── infra/
│   ├── compose/
│   │   └── docker-compose.prod.yml # CANONICAL PROD ENTRY POINT
│   ├── scripts/
│   │   ├── compose.sh              # Wrapper — use this for one-off commands
│   │   ├── deploy.sh               # Full deploy (precheck + build + up + health)
│   │   ├── precheck.sh             # Fail-fast environment validator
│   │   ├── health.sh               # Post-deploy health probe
│   │   ├── rollback.sh             # Roll compose stack to a previous image tag
│   │   ├── backup.sh               # mongodump against SHARED_MONGO_URL
│   │   ├── restore.sh              # mongorestore
│   │   ├── bootstrap-vps.sh        # First-time VPS provisioning
│   │   └── diagnose-502.sh         # 502 troubleshooter
│   ├── caddy/README.md             # Caddyfile contract
│   └── traefik/README.md           # Legacy / future migration notes
├── deploy-artifacts/
│   ├── factory-mongo/              # Reference copy of /opt/factory-mongo/
│   ├── caddy/                      # Reference copy of /opt/caddy/
│   └── factory-bootstrap.sh        # One-shot idempotent installer
├── backend/  frontend/  vie/       # Application code
└── docs/
    ├── DEPLOYMENT_OPERATIONS.md    # THIS FILE
    ├── DEPLOYMENT_ARCHITECTURE_REVIEW.md
    └── DEPLOYMENT_MIGRATION_PLAN.md
```

### 2.3 · Reverse-proxy routing (Caddy)

| Match | Target |
|-------|--------|
| `strategy.coinnike.com/api/*` | `factory-backend:8001` |
| `strategy.coinnike.com/*`     | `factory-frontend:80` |

Caddy sets `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, and
preserves the client `Host` header — the backend's CORS + RBAC + audit
journal all see the real caller.

### 2.4 · Dev overlay vs production

`/opt/strategy-factory/docker-compose.yml` (the file at repo root) is
the **local developer overlay**. It bundles Mongo, publishes ports
3000/8001 to the host, and does not join `vqb-network`. **Never
invoke it on the production VPS.** If both overlays run simultaneously
you get two `factory-mongo` containers claiming the same name and a
race on volume `factory_mongo_data`.

`scripts/one_click_deploy.sh` uses this dev overlay — treat it as a
local-laptop acceptance verifier, not a deploy tool.

---

## 3 · Docker operations

### 3.1 · Canonical invocation forms

Only three ways to talk to the production compose project:

```bash
# a) Full deploy from a clean checkout
/opt/strategy-factory/infra/scripts/deploy.sh

# b) Wrapper for one-off commands (works from any CWD)
/opt/strategy-factory/infra/scripts/compose.sh <subcommand>

# c) Explicit form from repo root
cd /opt/strategy-factory
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml <subcommand>
```

**Forbidden:** `cd infra/compose && docker compose -f docker-compose.prod.yml ...`
The compose file guards this at parse time (`${VAR:?...}`), but the
wrapper is the frictionless path.

### 3.2 · Build

Images are rebuilt from source on every deploy. `deploy.sh` bakes
`BUILD_VERSION` / `BUILD_COMMIT` / `BUILD_DATE` into the images at
build time (exposed at `GET /api/version`).

```bash
# Standalone build (rarely used — deploy.sh does it):
cd /opt/strategy-factory
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml build
```

### 3.3 · Deploy (fresh checkout → live)

```bash
cd /opt/strategy-factory
git fetch origin && git checkout main && git reset --hard origin/main
./infra/scripts/deploy.sh
```

`deploy.sh` runs:
1. `precheck.sh` — fail-fast validation of `.env`, docker daemon,
   `vqb-network`, `SHARED_MONGO_URL` reachability, DNS, reverse-proxy
   container presence.
2. `docker network create vqb-network` (idempotent).
3. `docker compose ... build`.
4. `docker compose ... up -d`.
5. Belt-and-suspenders: guarantees factory-backend + factory-runner are
   on `vqb-network` (in case a previous dev-overlay run attached them
   to a compose-local bridge).
6. `health.sh` — waits ~8 s then verifies every hop.

### 3.4 · Update (zero-downtime)

```bash
cd /opt/strategy-factory
git fetch origin && git checkout main && git reset --hard origin/main
./infra/scripts/deploy.sh                  # or --skip-precheck to shave a few seconds
```

`docker compose up -d` recreates only containers whose image or config
changed. Caddy's `reverse_proxy` treats an unhealthy target as
unavailable and retries — traffic drains automatically.

### 3.5 · Restart

```bash
# Single service
./infra/scripts/compose.sh restart factory-backend

# All four factory services
./infra/scripts/compose.sh restart

# Bounce a mis-behaving out-of-repo service
docker compose --project-directory /opt/caddy         -f /opt/caddy/docker-compose.yml         restart
docker compose --project-directory /opt/factory-mongo -f /opt/factory-mongo/docker-compose.yml restart
```

### 3.6 · Health verification (post-any-change)

```bash
/opt/strategy-factory/infra/scripts/health.sh
```

All-green output is the sign-off gate for every deploy. It checks:
- Container states + Docker healthchecks (backend / vie / frontend).
- In-cluster `GET /api/health`.
- Backend → VIE reachability.
- Frontend `/healthz`.
- Aggregated `GET /api/readiness` (mongo / vie / redis).
- Public `https://${FACTORY_DOMAIN}/api/health` and `https://${FACTORY_DOMAIN}/`.

### 3.7 · Image cleanup

Docker retains old image layers across builds. Prune periodically:

```bash
# Non-destructive: only images that no container references
docker image prune -f                         # dangling only
docker image prune -af --filter "until=168h"  # older than 7 days AND unreferenced
```

`docker system prune -af --volumes` is **NEVER** to be run on the
VPS — it would destroy `factory_mongo_data`.

### 3.8 · Rollback (last-good image tag)

```bash
# The tag is whatever FACTORY_IMAGE_TAG points at in `.env`.
# Assumes prior deploys tagged their images and pushed to a registry.
FACTORY_IMAGE_TAG=<previous-tag> /opt/strategy-factory/infra/scripts/rollback.sh
```

For a repo-level rollback (bad commit on `main`) see
[§9.5 · disaster recovery](#95--recovery-from-a-bad-commit-on-main).

---

## 4 · Container lifecycle & recovery

### 4.1 · Startup validation

After ANY container start / restart:

```bash
docker inspect factory-backend --format '{{.State.Status}}/{{.State.Health.Status}}'
# → running/healthy

# One-shot: state + health for all six
for c in factory-backend factory-frontend factory-vie factory-runner factory-mongo caddy; do
  printf '%-20s ' "$c"
  docker inspect "$c" --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}'
done
```

### 4.2 · Failure diagnosis checklist

Follow in order — stop when the answer becomes obvious.

1. `docker ps -a --filter name=factory-` — look for `Exited (…)`.
2. `docker logs --tail 200 <container>`.
3. `docker inspect <container> --format '{{json .State.Health}}' | jq`.
4. `./infra/scripts/health.sh` — cross-cutting probes.
5. For 502s: `./infra/scripts/diagnose-502.sh` — walks every hop.
6. `docker network inspect vqb-network | jq '.[0].Containers'` — confirm
   membership.
7. `docker exec factory-backend curl -fsS http://factory-mongo:27017` —
   is Mongo resolvable?

### 4.3 · Traefik labels are inert

The prod compose file emits `traefik.*` labels on `factory-backend` and
`factory-frontend`. Caddy ignores them. They are retained so a future
Traefik migration is a one-container swap (see
`infra/traefik/README.md`). Do not chase them when debugging.

### 4.4 · Rescue a stuck container (no data loss)

```bash
# 1. Confirm the state (dead / restarting loop / healthcheck-failing).
docker inspect factory-backend --format '{{json .State}}' | jq

# 2. Bring down JUST that container.
./infra/scripts/compose.sh rm -sf factory-backend

# 3. Recreate from the current image + env.
./infra/scripts/compose.sh up -d factory-backend

# 4. Verify.
./infra/scripts/health.sh
```

`rm -sf` is safe for the four factory-* services — they carry no
persistent state (Mongo is external, factory-runner's `factory_bi5`
volume is untouched by `rm`).

---

## 5 · MongoDB — backup, restore, upgrade

### 5.1 · Data preservation policy

- MongoDB data lives on the Docker volume `factory_mongo_data`.
- **The volume is never touched by any compose command in the
  `strategy-factory` project** — that project doesn't declare it.
- Only `docker compose down -v` **inside the `factory-mongo` project
  directory** (`/opt/factory-mongo`) would remove the volume. Never
  do this.

### 5.2 · Nightly backup (script-managed)

```bash
# Ad-hoc dump into the default location (/var/backups/strategy-factory)
/opt/strategy-factory/infra/scripts/backup.sh

# Custom output dir
/opt/strategy-factory/infra/scripts/backup.sh /mnt/backups/factory
```

Under the hood: launches a throwaway `mongo:7.0` container attached
to `vqb-network`, runs `mongodump --uri "$SHARED_MONGO_URL"
--archive=/dump/strategy_factory-<UTC_TS>.archive.gz --gzip`, then
prunes archives older than 30 days.

Recommended cron on the VPS:

```cron
# /etc/cron.d/strategy-factory-backup
15 3 * * *   root  /opt/strategy-factory/infra/scripts/backup.sh /var/backups/strategy-factory >>/var/log/strategy-factory-backup.log 2>&1
```

### 5.3 · Restore

```bash
/opt/strategy-factory/infra/scripts/restore.sh \
  /var/backups/strategy-factory/strategy_factory-20260722_031500.archive.gz
```

`restore.sh` calls `mongorestore ... --drop`. It replaces the existing
DB — take a fresh `backup.sh` first if you might need to unwind.

### 5.4 · Upgrade precautions

- Mongo 7 → 8 is out of scope for this document. Follow the official
  MongoDB upgrade path (feature-compatibility version).
- Before any upgrade, run `backup.sh`, verify the archive size, then
  copy it off-box (`scp`) to a machine you trust.
- Never delete `factory_mongo_data` to "start clean" without proving
  a restore first.

---

## 6 · Caddy — TLS & reverse proxy

### 6.1 · Configuration locations

| Path | Owner | Purpose |
|------|-------|---------|
| `/opt/caddy/docker-compose.yml` | Ops | Compose project definition |
| `/opt/caddy/Caddyfile`           | Ops | Routing + TLS declarative config |
| `caddy_data` volume              | Caddy | ACME certs / keys / autosave |
| `/var/log/caddy/strategy-factory.access.log` (host bind) | Caddy | Access log (JSON) |

Reference copies of the two files ship in
`/opt/strategy-factory/deploy-artifacts/caddy/`.

### 6.2 · TLS certificate management

- Caddy uses Let's Encrypt via HTTP-01 by default.
- Certificates and account keys are stored on the `caddy_data` volume.
  **This is the sole state Caddy owns — do not delete the volume.**
- Set the ACME account email in the global block of `Caddyfile` (grep
  for `email` — the bundle ships with a `REPLACE_WITH_LETSENCRYPT_EMAIL`
  placeholder that `factory-bootstrap.sh` refuses to accept).

### 6.3 · Automatic renewal

- Caddy renews ~30 days before expiry automatically. No cron needed.
- Verify next renewal date:
  ```bash
  docker exec caddy caddy list-certificates
  ```
- On renewal failure Caddy logs `certificate obtained` (or the error)
  to stdout; capture with `docker logs caddy | grep -Ei 'cert|acme'`.

### 6.4 · Reverse-proxy routing

Full contract lives in `/opt/strategy-factory/infra/caddy/README.md`.
Summary:

```caddyfile
strategy.coinnike.com {
    handle /api/* { reverse_proxy factory-backend:8001 { ... } }
    handle       { reverse_proxy factory-frontend:80 }
    log { output file /var/log/caddy/strategy-factory.access.log }
}
```

Reload Caddyfile changes without downtime:

```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

---

## 7 · Logging

### 7.1 · Log locations

| Source | How to view |
|--------|-------------|
| factory-backend  | `./infra/scripts/compose.sh logs -f factory-backend` |
| factory-vie      | `./infra/scripts/compose.sh logs -f factory-vie` |
| factory-frontend | `./infra/scripts/compose.sh logs -f factory-frontend` |
| factory-runner   | `./infra/scripts/compose.sh logs -f factory-runner` |
| factory-mongo    | `docker logs -f factory-mongo` (out-of-repo project) |
| caddy            | `docker logs -f caddy` |
| Caddy access log | `tail -f /var/log/caddy/strategy-factory.access.log \| jq .` |
| Backup log       | `tail -f /var/log/strategy-factory-backup.log` |
| Rollback snaps   | `ls -1t /opt/factory-rollback/ \| head -5` |

### 7.2 · Common inspection commands

```bash
# Errors only, last 500 lines
./infra/scripts/compose.sh logs --tail 500 factory-backend | grep -Ei 'error|traceback|refused'

# Compact timeline of the last 24 h across all four factory services
./infra/scripts/compose.sh logs --since 24h --timestamps 2>&1 | less

# Find slow requests via Caddy access log
jq -c 'select(.duration > 1) | {ts,uri:.request.uri,dur:.duration}' \
  /var/log/caddy/strategy-factory.access.log | tail -20
```

### 7.3 · Log rotation

- **Docker container logs**: rotate via Docker daemon
  (`/etc/docker/daemon.json`):
  ```json
  {
    "log-driver": "json-file",
    "log-opts": { "max-size": "50m", "max-file": "5" }
  }
  ```
  Restart docker daemon after editing (`systemctl restart docker`).
- **Caddy access log**: bind-mounted to `/var/log/caddy/` on the host.
  Add a `logrotate` rule:
  ```
  # /etc/logrotate.d/caddy-strategy-factory
  /var/log/caddy/strategy-factory.access.log {
      daily
      rotate 14
      compress
      missingok
      notifempty
      copytruncate
  }
  ```
- **Mongo container**: uses Docker's json-file driver — same rotation
  policy applies.

---

## 8 · Monitoring & health verification

### 8.1 · Container health checks

Every service in `docker-compose.prod.yml` declares a Docker
`healthcheck` — see the file for exact commands. Summary:

| Service | Probe | Interval | Start period |
|---------|-------|----------|--------------|
| factory-backend  | `curl -fsS http://127.0.0.1:8001/api/health` | 30 s | 60 s |
| factory-vie      | `curl -fsS http://127.0.0.1:8100/health`     | 30 s | 15 s |
| factory-frontend | `wget -qO- http://127.0.0.1/healthz`         | 30 s | 15 s |
| factory-runner   | `test -f /tmp/factory_runner.hb`             | 30 s | 45 s |
| factory-mongo    | `mongosh --eval "db.runCommand('ping').ok"`   | 15 s | 20 s |

### 8.2 · Service verification

```bash
# 1. In-cluster health probe (canonical)
./infra/scripts/health.sh

# 2. External reachability
curl -fsS https://${FACTORY_DOMAIN}/api/health          # → 200
curl -fsS https://${FACTORY_DOMAIN}/          -o /dev/null -w '%{http_code}\n'  # → 200

# 3. Readiness aggregate (mongo / vie / redis)
docker exec factory-backend curl -fsS http://127.0.0.1:8001/api/readiness | jq
# → { "checks": { "mongo": {"status":"green"}, "vie": {"status":"green"}, "redis": {"status":"skipped"} } }
```

### 8.3 · Prometheus / Loki integration (labels-only)

Every service in the prod compose carries
`prometheus.scrape=true` + `logging=promtail` labels. If a shared
Prometheus + Promtail stack runs on the same VPS on `vqb-network`, it
auto-discovers these containers. If not, the labels are inert.

### 8.4 · Failure diagnosis checklist (fast)

1. `./infra/scripts/health.sh` — one-shot verdict.
2. `docker ps -a --format 'table {{.Names}}\t{{.Status}}'`.
3. Tail the offending service log (`§7.1`).
4. If public URL fails but in-cluster health passes → Caddy /
   `vqb-network` issue → `./infra/scripts/diagnose-502.sh`.
5. If mongo=red in readiness → confirm `SHARED_MONGO_URL` creds:
   ```bash
   docker exec factory-backend python -c "
   import os, pymongo
   print(pymongo.MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000).admin.command('ping'))
   "
   ```
6. If vie=red → verify at least one provider key is set in `.env`.

---

## 9 · Disaster recovery

### 9.1 · Preserve first, act second

The order below is non-negotiable. If the VPS is on fire, still back
up the Mongo volume before doing anything else.

### 9.2 · Repository restoration

GitHub is the single source of truth. To restore from any checkpoint:

```bash
cd /opt
[[ -d strategy-factory ]] || git clone https://github.com/raghugr2013-lgtm/strategy-factory-canonical.git strategy-factory
cd strategy-factory
git fetch origin --prune
git checkout main
git reset --hard origin/main
git status                    # working tree clean
```

If the checkout was destroyed but the `.env` and volumes survive on
the VPS, the stack can be rebuilt without data loss:
`./infra/scripts/deploy.sh`.

### 9.3 · Environment restoration

```bash
# From the last known-good backup of /opt/strategy-factory/.env
sudo install -m 600 /path/to/backup/.env /opt/strategy-factory/.env
sudo install -m 600 /path/to/backup/factory-mongo.env /opt/factory-mongo/.env
sudo install -m 644 /path/to/backup/Caddyfile /opt/caddy/Caddyfile
```

If no backup exists, rebuild from `deploy-artifacts/repo-env/.env`
(only the file layout — every secret must be regenerated:
`JWT_SECRET`, `ADMIN_PASSWORD`, `MONGO_ROOT_PASSWORD`).

### 9.4 · Database restoration

```bash
# From a mongodump archive
/opt/strategy-factory/infra/scripts/restore.sh \
  /var/backups/strategy-factory/strategy_factory-<UTC_TS>.archive.gz
```

`restore.sh` runs `mongorestore --drop`. Point-in-time recovery is
NOT supported without an oplog snapshot — do not rely on it.

### 9.5 · Recovery from a bad commit on `main`

```bash
cd /opt/strategy-factory
git log --oneline -20                     # find the last-good SHA
git checkout <good-sha>                    # detached HEAD — safe
./infra/scripts/deploy.sh --skip-precheck  # redeploy the good code

# Once verified, propagate a proper revert commit through GitHub;
# never leave production on a detached HEAD indefinitely.
```

### 9.6 · Full VPS rebuild procedure

1. Provision a clean Ubuntu 24.04 host with DNS + firewall in place.
2. `sudo bash <(curl -fsSL https://raw.githubusercontent.com/raghugr2013-lgtm/strategy-factory-canonical/main/infra/scripts/bootstrap-vps.sh)`.
3. Copy the three env files + Caddyfile into place (see §1.1).
4. Copy the latest Mongo backup archive to `/var/backups/strategy-factory/`.
5. `sudo bash /opt/factory-bootstrap.sh` — brings up Mongo → Caddy → factory stack.
6. `/opt/strategy-factory/infra/scripts/restore.sh <archive>`.
7. `./infra/scripts/health.sh`.

### 9.7 · Production verification checklist

Sign-off gate for any recovery:

- [ ] `git status` clean, `HEAD == origin/main`.
- [ ] `./infra/scripts/health.sh` exits 0.
- [ ] `curl -fsS https://${FACTORY_DOMAIN}/api/health` → 200.
- [ ] `curl -fsS https://${FACTORY_DOMAIN}/`           → 200.
- [ ] `readiness` reports mongo=green, vie=green (redis skipped OK).
- [ ] `docker compose ls` shows exactly three projects: `strategy-factory`, `factory-mongo`, `caddy`.
- [ ] No duplicate container names in `docker ps -a`.
- [ ] Login with `ADMIN_EMAIL` succeeds via the UI.
- [ ] `docker exec factory-mongo mongosh --quiet --eval "db.getSiblingDB('${FACTORY_DB_NAME}').stats().dataSize"` returns a plausible size.

---

## 10 · Release management

### 10.1 · GitHub as the single source of truth

- All production code MUST come from
  `https://github.com/raghugr2013-lgtm/strategy-factory-canonical.git`
  on branch `main`.
- Never patch `/opt/strategy-factory` directly on the VPS. If a
  hotfix is required, push it through GitHub first, then
  `git pull` on the VPS.

### 10.2 · Release tagging

```bash
# On your workstation, after PR merge:
git tag -a strategy-factory@1.1.<N> -m "Release notes …"
git push origin --tags
```

Rebuild images with the tag baked in:

```bash
FACTORY_IMAGE_TAG=1.1.<N> ./infra/scripts/deploy.sh
```

The tag is embedded in every image, surfaced at `GET /api/version`,
and used by `rollback.sh` to switch back.

### 10.3 · Deployment sequence

1. Verify CI green on the target commit.
2. `git fetch origin && git checkout main && git reset --hard origin/main`.
3. `./infra/scripts/precheck.sh`   — should say `precheck OK`.
4. `./infra/scripts/deploy.sh`.
5. `./infra/scripts/health.sh`.
6. Smoke-test via the UI: log in, open Strategy Passport, verify no
   console errors.
7. Announce release in the ops channel with SHA + tag.

### 10.4 · Rollback sequence

1. `FACTORY_IMAGE_TAG=<previous-tag> ./infra/scripts/rollback.sh`.
2. `./infra/scripts/health.sh`.
3. If rollback fails, follow §9.5.

---

## 11 · Security

### 11.1 · Secrets management

- **Never commit `.env`.** `.gitignore` blocks `.env` / `.env.*` and
  allow-lists only `.env.example`.
- Rotate `JWT_SECRET`, `ADMIN_PASSWORD`, `MONGO_ROOT_PASSWORD` on:
  - Any suspected compromise.
  - Every quarter as routine hygiene.
- Rotation procedure for `JWT_SECRET`:
  1. Update `/opt/strategy-factory/.env` (chmod 600).
  2. `./infra/scripts/deploy.sh --skip-precheck` — bakes the new value.
  3. All existing user sessions are invalidated (they must log in
     again). This is expected and part of the security guarantee.

### 11.2 · File permissions

```bash
sudo chmod 600 /opt/strategy-factory/.env
sudo chmod 600 /opt/factory-mongo/.env
sudo chmod 644 /opt/caddy/Caddyfile
sudo chown root:root /opt/strategy-factory/.env /opt/factory-mongo/.env
```

Rollback snapshots under `/opt/factory-rollback/` are `chmod 700`
(only root can read them).

### 11.3 · Least-privilege principles

- MongoDB has `--auth` + never publishes 27017 to the host.
- factory-backend has read/write access only to the `FACTORY_DB_NAME`
  database.
- factory-runner ships with NO `JWT_SECRET` env — it has no auth
  surface (heartbeat-only under freeze).
- Caddy's `caddy_data` volume is Caddy-only (owner: root in the
  container).

### 11.4 · Hardening recommendations

- Enable `ufw`: allow `22/tcp` (from a known jump host if possible),
  `80/tcp`, `443/tcp`, `443/udp`. Deny everything else.
- Rotate the SSH host keys after any suspected compromise; use
  ed25519 keys only.
- Consider Fail2Ban on SSHD if the VPS is on the public IP directly.
- Do not install `mongosh` on the host — always exec into a container.
- Never `docker run --rm --network host mongo ...`. Host-network
  containers bypass `vqb-network` isolation.

---

## 12 · Operational runbooks

Copy-paste-ready. Every runbook is idempotent and exits with a clear
success gate.

### 12.1 · Runbook A — Fresh deployment (new VPS)

```bash
# 1. Provision Ubuntu 24.04 + DNS pointing at the VPS's public IP.

# 2. Bootstrap Docker + Compose plugin + vqb-network.
sudo bash <(curl -fsSL https://raw.githubusercontent.com/raghugr2013-lgtm/strategy-factory-canonical/main/infra/scripts/bootstrap-vps.sh)

# 3. Place secrets (from your secrets manager or a trusted host).
sudo mkdir -p /opt/factory-mongo /opt/caddy
sudo install -m 600 factory-mongo.env  /opt/factory-mongo/.env
sudo install -m 644 Caddyfile          /opt/caddy/Caddyfile
sudo sed -i 's|REPLACE_WITH_LETSENCRYPT_EMAIL@example.com|ops@your.tld|' /opt/caddy/Caddyfile

# 4. Copy factory-mongo + caddy compose files from the repo bundle.
git clone https://github.com/raghugr2013-lgtm/strategy-factory-canonical.git /opt/strategy-factory
sudo install -m 644 /opt/strategy-factory/deploy-artifacts/factory-mongo/docker-compose.yml /opt/factory-mongo/
sudo install -m 644 /opt/strategy-factory/deploy-artifacts/caddy/docker-compose.yml         /opt/caddy/

# 5. Place the repo .env.
sudo install -m 600 strategy-factory.env /opt/strategy-factory/.env

# 6. One-shot bootstrap.
sudo bash /opt/strategy-factory/deploy-artifacts/factory-bootstrap.sh

# 7. Verify.
/opt/strategy-factory/infra/scripts/health.sh
```

### 12.2 · Runbook B — Standard update (existing VPS)

```bash
cd /opt/strategy-factory
git fetch origin && git checkout main && git reset --hard origin/main
./infra/scripts/deploy.sh
./infra/scripts/health.sh
```

Zero downtime — Caddy drains the old container automatically.

### 12.3 · Runbook C — Emergency rollback

```bash
# Path 1 — image rollback (previous tag pushed to registry).
FACTORY_IMAGE_TAG=<previous-tag> /opt/strategy-factory/infra/scripts/rollback.sh
/opt/strategy-factory/infra/scripts/health.sh

# Path 2 — commit rollback (no registry needed; rebuilds from source).
cd /opt/strategy-factory
git log --oneline -20                      # pick the good SHA
git checkout <good-sha>
./infra/scripts/deploy.sh --skip-precheck
/opt/strategy-factory/infra/scripts/health.sh
```

If either path leaves the stack red, escalate to Runbook D (container
recovery) or Runbook E (Mongo recovery).

### 12.4 · Runbook D — Container recovery (individual service)

```bash
# Assume factory-backend is unhealthy.
docker inspect factory-backend --format '{{json .State}}' | jq .Health

# Bounce it — no data loss.
/opt/strategy-factory/infra/scripts/compose.sh rm -sf factory-backend
/opt/strategy-factory/infra/scripts/compose.sh up -d factory-backend

# Watch it come healthy (up to 60 s).
for i in {1..12}; do
  s=$(docker inspect factory-backend --format '{{.State.Health.Status}}')
  echo "$(date +%T) → $s"
  [[ "$s" == "healthy" ]] && break
  sleep 5
done
/opt/strategy-factory/infra/scripts/health.sh
```

### 12.5 · Runbook E — Mongo recovery

```bash
# 1. Take a fresh snapshot before touching anything.
docker exec factory-mongo mongodump \
  --uri "mongodb://root:$(grep MONGO_ROOT_PASSWORD /opt/factory-mongo/.env | cut -d= -f2)@127.0.0.1:27017/?authSource=admin" \
  --archive=/data/backup/rescue-$(date -u +%Y%m%d_%H%M%S).archive.gz --gzip

# 2. Bounce the container.
docker compose --project-directory /opt/factory-mongo -f /opt/factory-mongo/docker-compose.yml restart
docker exec factory-mongo mongosh --quiet --eval "db.runCommand('ping').ok"   # → 1

# 3. Confirm factory-backend can reconnect.
docker exec factory-backend curl -fsS http://127.0.0.1:8001/api/readiness | jq .checks.mongo
```

If the container refuses to start:

```bash
docker logs --tail 200 factory-mongo
# If the volume is intact, redeploy the compose project (data survives).
docker compose --project-directory /opt/factory-mongo -f /opt/factory-mongo/docker-compose.yml up -d --force-recreate
```

Full data restore from a `mongodump` archive:

```bash
/opt/strategy-factory/infra/scripts/restore.sh /path/to/archive.gz
```

### 12.6 · Runbook F — Caddy recovery

```bash
# Reload without downtime after a Caddyfile change:
docker exec caddy caddy reload --config /etc/caddy/Caddyfile

# Hard-restart:
docker compose --project-directory /opt/caddy -f /opt/caddy/docker-compose.yml restart

# Investigate cert issues:
docker exec caddy caddy list-certificates
docker logs caddy | grep -Ei 'certificate|acme|obtained|error' | tail -50

# If certs are corrupted, restore from a `caddy_data` volume backup —
# do NOT delete the volume, or Let's Encrypt rate limits will kick in.
```

### 12.7 · Runbook G — Health audit (weekly)

```bash
# 1. Full health probe.
/opt/strategy-factory/infra/scripts/health.sh

# 2. Compose-project sanity.
docker compose ls                                      # exactly 3 projects
docker compose --project-name strategy-factory ps       # 4 containers

# 3. Duplicate detection.
docker ps -a --format '{{.Names}}' | sort | uniq -c | awk '$1>1'   # empty

# 4. Volume + disk usage.
docker system df -v | grep -E 'factory_|caddy_'
df -h /var/lib/docker

# 5. Backup freshness.
ls -1t /var/backups/strategy-factory/ | head -3
```

### 12.8 · Runbook H — Production verification (after any change)

Print-and-tick:

- [ ] `./infra/scripts/health.sh` exit 0.
- [ ] `curl -fsS https://${FACTORY_DOMAIN}/api/health` → 200.
- [ ] `curl -fsS https://${FACTORY_DOMAIN}/`           → 200.
- [ ] Login via the UI succeeds with a known admin.
- [ ] `GET /api/version` reports the expected `BUILD_COMMIT`.
- [ ] `readiness` reports mongo=green, vie=green.
- [ ] `docker compose ls` shows the three canonical projects only.
- [ ] No new error lines in `factory-backend` / `factory-vie` logs
      since the change window.

---

## 13 · Golden rules (never break these)

1. **GitHub is the single source of truth.** No production patches on
   the VPS. Every change lands on `origin/main` first.
2. **One canonical production compose file:**
   `infra/compose/docker-compose.prod.yml`. Invoked only via
   `deploy.sh`, `compose.sh`, or the explicit repo-root form.
3. **One canonical env file per compose project.**
   `/opt/strategy-factory/.env`, `/opt/factory-mongo/.env`,
   `/opt/caddy/Caddyfile`. Chmod 600 on the two `.env` files.
4. **Never `cd infra/compose && docker compose …`.** Guaranteed to
   crash at parse time (`${VAR:?…}`), but the wrapper is the
   frictionless path.
5. **Never run the dev overlay (`/opt/strategy-factory/docker-compose.yml`)
   on the production VPS.** It bundles a second Mongo that will fight
   the production one for the same container name.
6. **Never `docker compose down -v` inside `/opt/factory-mongo/`.**
   That would destroy `factory_mongo_data`.
7. **Never `docker system prune -af --volumes` on the VPS.** Same
   reason.
8. **Never commit a real `.env`.** `.gitignore` guards this; do not
   override.
9. **Always take a `backup.sh` before an upgrade, rollback, or
   restore.**
10. **All six containers must be on `vqb-network`** — verify with
    `docker network inspect vqb-network` after any topology change.

---

## Appendix A · Legacy documentation index

Documents superseded by this manual (kept for historical context):

| File | Superseded section |
|------|-------------------|
| `docs/DEPLOYMENT.md` | §2, §3, §5, §6 |
| `docs/DEPLOYMENT_ASSUMPTIONS.md` | §1, §2 |
| `docs/POST_FREEZE_DEPLOYMENT_CHECKLIST.md` | §10, §12 |
| `docs/acceptance_v1_1/DEPLOYMENT_GUIDE.md` | §12.1 |
| `deploy-artifacts/DEPLOY_RUNBOOK.md` | §12.1, §12.2 |
| `memory/VPS_DEPLOYMENT_RUNBOOK.md` | §12 |

They remain in the repo; when in doubt, THIS document wins.
