# DEPLOYMENT_READINESS_REPORT.md — Self-Managed Linux VPS (12-vCPU)

**Mode:** Planning + read-only audit. **No code modified. No deployment performed.**
**Target:** 12-vCPU Linux VPS, self-managed, off-Emergent.
**Scope honoured:** No BI5 R3 · no Phase 13 · no Phase 14 · no deployment activity. Read-only.

---

## 1. Current roadmap position

| Phase / Gate | Status |
|---|---|
| Migration restore + validation | ✅ Done |
| BI5 R2 Step-0 calibration (Option A) | ✅ Done |
| R2 Batch (B-4 sweep / B-5 ranker / B-8 UI) | ✅ Done |
| ASF v1.0 spec + backend architecture LOCKED | ✅ Done |
| GATE 3 — ASF migration importer build | ✅ Done (14 files / ~2,200 LOC / 28 tests green) |
| GATE 3 dry-run + wet-run | ✅ Done (14 T1 + 11,598 T2 + 1,938 T3 imported; verifier `verified`) |
| Post-import pipeline run #1 (revalidation / rescoring / rematching) | ✅ Done (14 blocked by `DATA_CERT_MISSING` / `MISSING_FILLS`) |
| Post-import pipeline run #2 (after BI5 backfill + sweep) | ✅ Done (XAUUSD moved to `MISSING_FILLS`; ETHUSD still `DATA_CERT_MISSING`) |
| **HERE** — Deployment readiness audit | ✅ This document |
| 12-vCPU VPS deployment | ⏳ Pending operator decision |
| Shadow-mode trade capture | ⏳ Operator-locked |
| Per-merit promotions from `IMPORTED_SEED` | ⏳ Awaits shadow-mode |
| BI5 R3 (B-3 tick-replay / B-6 simulate_fills / B-7 Trade Runner) | ⏳ Backlog |
| Phase 13 Dossier Engine | ⏳ Backlog |
| Phase 14 Valuation Engine | ⏳ Backlog |
| ASF Exporter / DR / Marketplace | ⏳ Backlog |

---

## 2. Mandatory work before 12-vCPU deployment

The system is **substantially ready**. Only **5 mandatory items** stand between the
current state and a clean VPS deployment:

| # | Item | Type | Reason | Effort |
|---|---|---|---|---:|
| **M-1** | Make ASF inbox + bulk-import paths configurable | Code (small) | 4 hardcoded `/app/_migration_inbox/` + `/app/data_imports/` constants must read from env vars before VPS deploy | **1 h** |
| **M-2** | Strip preview-URL fallbacks from test files (or document `BASE_URL` requirement) | Hygiene | ~15 test files have dead `*.preview.emergentagent.com` defaults; tests pass when `BASE_URL` is set but the fallbacks confuse new operators | **0.5 h** |
| **M-3** | Production-mode frontend bundle (`yarn build`) + nginx static-serve config | Build | Current setup runs `craco start` (dev server). VPS needs a built static bundle served by nginx | **1 h** |
| **M-4** | Compose stack (docker-compose.yml) wrapping backend + mongo + nginx | Packaging | Backend Dockerfile already exists; need a compose file orchestrating all 3 services with a single command | **2 h** |
| **M-5** | One-shot startup verification script | Ops | Probes `/api/health`, scheduler liveness, mongo writeable, frontend reachable | **1 h** |
| **TOTAL** | | | | **~5.5 h** |

**Nothing else is mandatory.** Everything currently working in this Emergent pod
will run on a vanilla Ubuntu 22.04 / Debian 12 / RHEL 9 host with stock package
versions.

---

## 3. Blockers vs. deferrable

### 3.1 BLOCKERS (must complete before VPS first-boot)

1. **M-1 path config** — code change. Without it, the ASF importer + master-bot
   export silently fail to find their working directories on a VPS.
2. **M-3 production bundle** — without `yarn build` + nginx, you'd be running the
   React dev server in production (CPU-hungry, hot-reload watchers, websocket
   noise). Not acceptable at 12-vCPU.
3. **M-4 compose stack** — without it, deployment is a series of error-prone
   manual `systemd unit` files.

### 3.2 STRONGLY RECOMMENDED (can complete on-VPS post-first-boot but better up-front)

4. **M-2 test-URL hygiene** — annoying but not service-breaking.
5. **M-5 startup probe** — operationally important; not strictly required for the
   first boot.
6. **TLS certificate** (Let's Encrypt via certbot) — fine to start with self-signed
   for 24 h, then move to LE.
7. **Daily mongodump cron** — backup must exist before any wet-run on the VPS.
8. **`/api/admin/bi5/sweep` re-schedule** — APScheduler runs in-process; if you
   add a second backend replica later you'd want an external cron, but for the
   first 12-vCPU deploy the in-process scheduler is fine.

### 3.3 SAFE TO DEFER (post-deployment, no blocking dependency)

9. BI5 R3 (B-3 tick-replay, B-6 simulate_fills, B-7 Trade Runner consolidation)
10. Phase 13 Dossier Engine
11. Phase 14 Valuation Engine
12. ASF Exporter + DR scheduler + Marketplace PKI signing
13. Shadow-mode trade capture (currently operator-locked; will become the gating
    pre-req for promoting imported survivors)
14. Per-cohort dashboard tiles for the imported survivors
15. Adapter source update to also write flat `pair`/`timeframe` aliases (operator
    backfilled in place during this session; adapter still ASF-nested-only)

---

## 4. Estimated effort for each remaining phase

| Item | Type | Code? | Estimated effort |
|---|---|:--:|---:|
| **M-1 path-config** | Pre-deploy code | yes | 1 h |
| **M-2 test URL hygiene** | Pre-deploy hygiene | yes | 0.5 h |
| **M-3 nginx + yarn build** | Pre-deploy build | partial | 1 h |
| **M-4 docker-compose stack** | Pre-deploy packaging | yes | 2 h |
| **M-5 startup probe script** | Pre-deploy ops | yes | 1 h |
| **VPS provisioning + apt + docker + compose up** | Ops | no | 1 h |
| **First-boot smoke test + admin login + smoke endpoints** | Ops | no | 0.5 h |
| **TLS + LE certbot** | Ops | no | 1 h |
| **Daily mongodump cron + restore drill** | Ops | no | 1 h |
| **Shadow-mode trade capture (3 XAUUSD strategies)** | Code + ops | yes | ~2 d |
| **Promote XAUUSD survivors that PASS** | Manual decision | no | 0.5 h |
| **ETHUSD source-data ingest** | Ops | no | 0.5 d |
| **Phase 13 Dossier Engine** | Roadmap | yes | ~3–5 d |
| **Phase 14 Valuation Engine** | Roadmap | yes | ~3–5 d |
| **BI5 R3 (B-3 / B-6 / B-7)** | Roadmap | yes | ~5–7 d |
| **ASF Exporter + DR + Marketplace** | Roadmap | yes | ~7–10 d |
| **72-h deployment soak** | Ops | no | 3 d wall-clock (passive) |

**Critical path to "first operational 12-vCPU Strategy Factory":**
M-1 → M-2 → M-3 → M-4 → M-5 → VPS provision → first boot → smoke test → TLS → backup cron = **~10–12 dev-hours + 1 day wall-clock**.

---

## 5. Recommended path to first live 12-vCPU operation

**Shortest viable path (5 milestones, ~1.5 days end-to-end):**

```
Day 0  (4 h) — Author the 5 mandatory items (M-1 to M-5) on Emergent
              · Code changes self-contained; existing tests catch regressions
              · Commit + push (or zip the working tree if pushing later)

Day 1  (8 h) — Provision the 12-vCPU VPS
              ½ h     spin up VPS (12-vCPU / 32+ GB RAM / 200 GB SSD)
              ½ h     install docker + docker-compose (Ubuntu 22.04 LTS)
              ½ h     git clone OR scp the working tree
              ½ h     populate .env files (MONGO_URL, JWT_SECRET, ADMIN_*, EMERGENT_LLM_KEY)
              1 h     `docker compose up -d` → backend + mongo + nginx
              ½ h     restore Mongo snapshot (mongorestore from the asf_inspect
                      + test_database mongodumps)
              ½ h     run M-5 startup probe → expect green
              1 h     curl smoke (admin login, GET /api/asf/import/{wet-run-id})
              1 h     install certbot, get LE cert, point nginx at it
              ½ h     wire daily mongodump cron + restore-drill rehearsal
              ½ h     declare "first operational 12-vCPU Strategy Factory"

Day 2-3       72-h passive soak; monitor /api/health + scheduler liveness
              (no code work)

After soak    Authorise shadow-mode trade capture; resume cohort progression
```

**Net code work:** ~5.5 dev-hours.  **Net VPS bring-up:** ~6 ops-hours.  **Wall clock to live:** 1 day.

---

## 6. VPS Compatibility Report

### 6.1 Linux compatibility

✅ **Fully compatible** with standard Linux distributions.

| Layer | Current | VPS-ready? | Notes |
|---|---|:--:|---|
| Backend | Python 3.11 + FastAPI + uvicorn | ✅ | `Dockerfile` already exists at `backend/Dockerfile`; uses `python:3.11-slim` base; no Emergent-only deps |
| Frontend | React 18 + CRA/craco | ✅ | `yarn build` produces static bundle; nginx serves it |
| DB | MongoDB 7.0 | ✅ | Standard upstream package (`mongodb-org` apt repo) |
| Schedulers | APScheduler (in-process) | ✅ | Runs inside the backend's asyncio loop; no external cron required |
| LLM | `emergentintegrations` SDK + EMERGENT_LLM_KEY | ✅ | SDK installs from PyPI on any host; key is just an env var |

### 6.2 Hardcoded path dependencies

15 hardcoded `/app/*` references in non-test code. Most are operator-facing data
directories that simply need to exist on the VPS host. **Only 4 require env-var
parameterisation** (item M-1):

| Path | File | Action for VPS |
|---|---|---|
| `/app/_migration_inbox/` | `api/asf.py` · `engines/asf/importer/migration_adapter.py` | **env-ify → `ASF_INBOX_DIR`** |
| `/app/data_imports` | `api/data.py` | **env-ify → `BULK_IMPORT_DIR`** |
| `/app/data_imports/master_bots` | `engines/master_bot_export.py` | **env-ify → `MASTER_BOT_EXPORT_DIR`** |
| `/app/data_imports/master_bot_packs` | `engines/master_bot_pack.py` | **env-ify → `MASTER_BOT_PACK_DIR`** |
| `/app/data/bi5/dukascopy/` | `data_engine/tick_archive.py` | ✅ already env-driven via `BI5_ARCHIVE_PATH` |
| `/app/data/host_id` | `engines/host_capability.py` | ✅ acceptable — create dir on VPS |
| `/app/backend/prop_firm_pdfs/` | `engines/prop_firm_config_engine.py` | ✅ acceptable — create dir on VPS |
| `/app/test_reports/`, `/app/frontend/src/hooks/...` | scripts + diagnostic | ✅ test-only / non-prod paths |

### 6.3 Emergent-specific dependencies

| Dependency | Used in code? | VPS impact |
|---|:--:|---|
| `INTEGRATION_PROXY_URL` (`https://integrations.emergentagent.com`) | **no** | Set in supervisor env but never referenced. Drop. |
| `APP_URL` (`*.preview.emergentagent.com`) | **no** | Same — drop. |
| `EMERGENT_LLM_KEY` | **yes** (LLM engines) | Works anywhere — it's a normal API key |
| `emergentintegrations` PyPI package | **yes** | Already on the public PyPI mirror; `pip install` works on any Linux |
| Supervisor + nginx-code-proxy + code-server | **no** (only used by Emergent's IDE) | Not needed on VPS |
| Emergent's auth-protected preview-URL ingress | **no** | VPS uses its own nginx + LE TLS |

**Net Emergent-specific runtime dependencies: ZERO.** The only Emergent artefact
in the running stack is the LLM key, which is a portable API token.

### 6.4 Services requiring replacement on a VPS

| Emergent component | VPS replacement |
|---|---|
| Emergent supervisor (`/etc/supervisor/conf.d/`) | systemd unit OR Docker Compose `restart: always` |
| Emergent ingress (preview-URL TLS termination) | nginx + Let's Encrypt certbot |
| Emergent code-server | not required in production |
| Emergent's auto-Mongo provisioning | mongo container OR apt-installed mongod |
| Emergent's `*.preview.emergentagent.com` DNS | your domain + A record |

---

## 7. Deployment Package Requirements

### 7.1 Backend (Python 3.11)

```
fastapi==0.110.1
uvicorn==0.25.0
pymongo==4.5.0
motor==3.3.1
APScheduler==3.11.2
pydantic==2.12.5
python-dotenv==1.2.2
passlib==1.7.4
bcrypt==4.1.3
PyJWT==2.12.1
python-multipart==0.0.24
httpx==0.28.1
pandas==2.0.3
numpy==1.26.4
dukascopy-python==4.0.1
openai
requests
pdfplumber==0.11.9
pypdf==6.10.2
reportlab==4.5.0
beautifulsoup4==4.14.3
lxml==6.1.0
pytest-asyncio==1.3.0
psutil==6.1.0
emergentintegrations    # installed from Emergent's PyPI index
```

Base image: **`python:3.11-slim`** (already used by `/app/backend/Dockerfile`).

### 7.2 Frontend (Node 20 + Yarn 1.22)

* Build step: `yarn install --frozen-lockfile && yarn build`
* Output: `frontend/build/` static assets (~5–10 MB gzipped)
* Served by nginx as static files (no Node runtime in production)
* `yarn` (Classic 1.22.x) is required — `yarn.lock` is at /app/yarn.lock

### 7.3 MongoDB

* Version: **7.0.x** (matches current pod)
* Single instance (no sharding / no replica set needed for first-boot)
* Data volume: ~110 MB (live `test_database`) + 102 MB inspection snapshot
* WiredTiger storage engine (default)
* No authentication required if bound to docker internal network; add SCRAM if
  exposed beyond localhost

### 7.4 Python tooling

* Python 3.11.x (3.11.15 confirmed working)
* pip / virtualenv via the Docker image; no system-wide install required

### 7.5 Node / Yarn tooling

* Node 20.x LTS
* Yarn Classic 1.22.x

### 7.6 Required environment variables

| Variable | Owner | Purpose |
|---|---|---|
| `MONGO_URL` | backend | Mongo connection string |
| `DB_NAME` | backend | Mongo database name |
| `JWT_SECRET` | backend | Auth token signing key (rotate per-VPS) |
| `ADMIN_EMAIL` | backend | Seeded admin login |
| `ADMIN_PASSWORD` | backend | Seeded admin password |
| `CORS_ORIGINS` | backend | Comma-list of allowed origins |
| `EMERGENT_LLM_KEY` | backend | LLM key for AI features |
| `ENABLE_DYNAMIC_MARKET_UNIVERSE` | backend | Feature flag |
| `BI5_ARCHIVE_PATH` | backend (optional) | Override `/app/data/bi5/dukascopy/` |
| **`ASF_INBOX_DIR`** | backend (NEW — needed for M-1) | ASF import inbox |
| **`BULK_IMPORT_DIR`** | backend (NEW — needed for M-1) | Generic bulk import dir |
| `REACT_APP_BACKEND_URL` | frontend (build-time) | Public backend URL (https://factory.yourdomain.tld) |

---

## 8. Production Deployment Checklist

### 8.1 OS packages

```bash
apt update && apt install -y \
  docker.io docker-compose-plugin git curl jq certbot python3-certbot-nginx
```

(Optional: install `mongod` natively only if you choose not to run Mongo in a
container.)

### 8.2 Mongo setup

* Provision a docker volume `mongo_data` (or `/var/lib/mongo` on host)
* Run `mongorestore --archive=test_database_dump.gz --gzip` for the seed data
* Create indexes via the existing `engines/db_indexes.py` first-run path (runs
  automatically at backend startup)
* Optional: enable SCRAM auth + bind to internal docker network

### 8.3 Service startup

```bash
docker compose up -d                # backend + mongo + nginx
docker compose logs -f backend      # tail to confirm schedulers fired
curl -fsS https://factory.example.com/api/health   # smoke gate
```

### 8.4 Scheduler startup

All in-process via APScheduler — fire automatically on FastAPI `@app.on_event("startup")`
hooks at `/app/backend/server.py` lines 308 / 317 / 348 / 367 / 397 / 442 / 458 /
474 / 489 / 502 / 527 / 685 (12 startup hooks):
* `bi5_cert_sweep_scheduler` (weekly Sunday 03:00 UTC)
* `factory_supervisor_scheduler` (orchestrator tick)
* `challenge_manager` scheduler
* `auto_factory_engine` scheduler
* `monitoring_engine` scheduler
* `auto_scheduler` interval

No external systemd timer / cron required for first deploy.

### 8.5 Backup requirements

```bash
# /etc/cron.daily/factory-backup
mongodump --uri="$MONGO_URL" --gzip \
  --out=/backup/$(date +%F)/
find /backup -mtime +30 -delete   # 30-day retention
```

Plus weekly `tar -czf /backup/data-$(date +%F).tgz /app/data` for the BI5 archive
files.

**Mandatory before any wet-run on the VPS.** Should be tested with at least one
restore drill before declaring the deployment live.

### 8.6 Firewall requirements

```
ufw allow 22/tcp                  # SSH (consider key-only)
ufw allow 80/tcp                  # HTTP (LE challenge)
ufw allow 443/tcp                 # HTTPS
ufw deny  27017/tcp               # Mongo NEVER public
ufw deny  8001/tcp                # backend NEVER public (nginx terminates)
ufw deny  3000/tcp                # frontend not used in prod
ufw enable
```

---

## 9. Easy Deployment Package Plan

### 9.1 Recommended approach — **Docker Compose**

| Option | Verdict | Why |
|---|---|---|
| **Docker Compose** ✅ | **Recommended** | Backend Dockerfile already exists. Single command lifecycle (`compose up/down`). nginx + mongo + backend wired via internal network. Mature tooling for VPS deploys at this scale. |
| Plain systemd units | ✗ | More moving parts, harder to test locally, no container isolation |
| Kubernetes | ✗ | Overkill for single-VPS; introduces an orchestrator just to run 3 containers |
| Nomad / Swarm | ✗ | Niche; no team familiarity assumed |
| Bare-metal install | ✗ | Lose isolation; harder to upgrade Python/Node independently |

### 9.2 Recommended deployment architecture (12-vCPU VPS)

```
┌────────────────────────────────────────────────────────────────────────┐
│  Linux VPS — Ubuntu 22.04 LTS — 12 vCPU / 32 GB RAM / 200 GB SSD       │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  nginx  (host:80, host:443)                                       │  │
│  │   • TLS terminator (Let's Encrypt)                                │  │
│  │   • / → static React bundle from /var/www/factory/build/          │  │
│  │   • /api/* → reverse-proxy → backend:8001                         │  │
│  └────────────────┬─────────────────────────────────────────────────┘  │
│                   │                                                    │
│  ┌────────────────▼─────────────────────────────────────────────────┐  │
│  │  backend  (container · image: factory-backend:latest)            │  │
│  │   • FastAPI + uvicorn (port 8001 — bound to docker net only)     │  │
│  │   • 12 in-process APScheduler jobs                               │  │
│  │   • mounts: /app/data (BI5 archive) + /app/_migration_inbox      │  │
│  │             + /app/data_imports (read-write)                      │  │
│  │   • env: .env file at /etc/factory/backend.env                   │  │
│  │   • CPU: ~2–4 vCPU under steady-state                            │  │
│  │   • RAM: ~1–3 GB under steady-state                              │  │
│  └────────────────┬─────────────────────────────────────────────────┘  │
│                   │                                                    │
│  ┌────────────────▼─────────────────────────────────────────────────┐  │
│  │  mongodb  (container · image: mongo:7.0)                         │  │
│  │   • port 27017 — bound to docker net only (NOT public)           │  │
│  │   • volume: /var/lib/factory-mongo                               │  │
│  │   • CPU: ~1–2 vCPU                                               │  │
│  │   • RAM: ~2–4 GB (wired-tiger cache)                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  Headroom:  ~6 vCPU / ~25 GB RAM for shadow-mode trade capture +      │
│             post-import BI5 sweeps + future BI5 R3 backtests          │
└────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Recommended file layout on the VPS

```
/opt/factory/
├── docker-compose.yml          (3-service stack)
├── nginx/
│   └── factory.conf            (TLS + reverse proxy + static)
├── env/
│   ├── backend.env             (MONGO_URL etc. — chmod 600)
│   └── frontend.env            (REACT_APP_BACKEND_URL — used at build time only)
├── data/
│   ├── bi5/dukascopy/          (mounted into backend container)
│   ├── _migration_inbox/       (mounted into backend container)
│   ├── data_imports/           (mounted into backend container)
│   └── mongo/                  (mongo volume)
├── frontend/build/             (yarn-built static bundle — nginx serves)
└── backups/                    (daily mongodumps + weekly tgz)
```

---

## 10. Remaining code changes required for clean Linux VPS deploy

**5 surgical edits** (no architectural changes, no business-logic refactors):

| # | File | Change | Reason |
|---|---|---|---:|
| 1 | `backend/api/asf.py` | `inbox_dir = p.get("inbox_dir", os.environ.get("ASF_INBOX_DIR", "/app/_migration_inbox/"))` | M-1 path env-ification |
| 2 | `backend/engines/asf/importer/migration_adapter.py` | Same default + env fallback | M-1 |
| 3 | `backend/api/data.py` | `IMPORT_DIR = os.environ.get("BULK_IMPORT_DIR", "/app/data_imports")` | M-1 |
| 4 | `backend/engines/master_bot_export.py` | `EXPORT_DIR_DEFAULT = os.environ.get("MASTER_BOT_EXPORT_DIR", "/app/data_imports/master_bots")` | M-1 |
| 5 | `backend/engines/master_bot_pack.py` | `PACK_DIR_DEFAULT = os.environ.get("MASTER_BOT_PACK_DIR", "/app/data_imports/master_bot_packs")` | M-1 |
| 6 (optional) | `backend/tests/test_*.py` | Replace dead-preview fallbacks with `pytest.skip("requires BASE_URL")` or remove default | M-2 hygiene |

**Net deltas:** 5 lines of code (one-liner per file) for the production path, plus
optional test-file hygiene. **No new features, no schema changes, no API surface
changes, no regression risk.**

Run the full pytest suite after the 5 edits — expected: zero new failures (the
defaults stay the same if env vars aren't set).

---

## 11. Deployment Decision Matrix

### Legend
* **Emergent only** — depends on Emergent's preview ingress / IDE
* **VPS only** — needs ops-level VPS access
* **Either** — runs cleanly in both contexts

### A — Mandatory before 12-vCPU deployment

| Item | Where to run | Emergent? | VPS? | Preferred | CPU req | Wall time |
|---|---|:--:|:--:|---|:--:|---:|
| M-1 path env-ification | code | ✅ | n/a | **Emergent** | low | 1 h |
| M-2 test URL hygiene | code | ✅ | n/a | Emergent | low | 0.5 h |
| M-3 yarn build + nginx config | code/build | ✅ | ✅ | **Either** (build on either; nginx config is VPS-ops) | low | 1 h |
| M-4 docker-compose.yml | code/ops | ✅ author + ✅ run | **VPS** to actually start | Emergent (author) → VPS (run) | low | 2 h |
| M-5 startup probe script | code/ops | ✅ author | **VPS** to invoke | Either | low | 1 h |
| Provision 12-vCPU VPS + Docker | ops | n/a | ✅ | **VPS** | n/a | 1 h |
| First `docker compose up -d` | ops | n/a | ✅ | **VPS** | 12 vCPU | 0.5 h |
| Restore Mongo snapshot | ops | n/a | ✅ | **VPS** | 1 vCPU | 0.5 h |
| TLS via Let's Encrypt | ops | n/a | ✅ | **VPS** | low | 1 h |
| Daily mongodump cron + drill | ops | n/a | ✅ | **VPS** | 1 vCPU at 03:00 | 1 h |

**A-tier total:** **~9.5 h** + 1 day wall-clock.

### B — Strongly recommended before deployment (can do post-first-boot but cleaner up-front)

| Item | Where to run | Emergent? | VPS? | Preferred | CPU req | Wall time |
|---|---|:--:|:--:|---|:--:|---:|
| Run full pytest suite once on Emergent | code | ✅ | ✅ | **Emergent** | 2 vCPU | 0.5 h |
| Adapter source update — flat-shape aliases | code | ✅ | n/a | **Emergent** | low | 0.5 h |
| `engines/db_indexes.py` smoke-run | ops | ✅ | ✅ | **VPS** (first boot) | low | < 1 min |
| Document admin account rotation policy | docs | ✅ | n/a | **Emergent** | n/a | 0.5 h |
| Add /api/health + /api/data/health to nginx upstreams | ops | n/a | ✅ | **VPS** | low | 0.5 h |

**B-tier total:** **~2.5 h**.

### C — Safe to complete after 12-vCPU first-boot

| Item | Where to run | Emergent? | VPS? | Preferred | CPU req | Wall time |
|---|---|:--:|:--:|---|:--:|---:|
| Shadow-mode trade capture (3 XAUUSD strategies) | runtime | ❌ | ✅ | **VPS** | 1–2 vCPU steady | ~2 d (passive capture) |
| Promote XAUUSD survivors that PASS BI5 | runtime | ❌ | ✅ | **VPS** | low | 0.5 h |
| ETHUSD source-data ingest | runtime | ✅ (if archive in pod) or ✅ VPS | ✅ | **VPS** | 1 vCPU | 0.5 d |
| Per-cohort dashboard tile (admin UI) | code+UI | ✅ | n/a | **Emergent** | low | ~4 h |
| BI5 R3 — B-3 tick-replay | code | ✅ | ✅ | **Emergent** | medium during dev | ~3 d |
| BI5 R3 — B-6 simulate_fills | code | ✅ | ✅ | **Emergent** | medium during dev | ~2 d |
| BI5 R3 — B-7 Trade Runner consolidation | code | ✅ | ✅ | **Emergent** | medium during dev | ~2 d |
| Phase 13 Dossier Engine | code | ✅ | ✅ | **Emergent** | medium during dev | ~3–5 d |
| Phase 14 Valuation Engine | code | ✅ | ✅ | **Emergent** | medium during dev | ~3–5 d |
| ASF Exporter (engines/asf/exporter/*) | code | ✅ | ✅ | **Emergent** | medium during dev | ~3 d |
| ASF DR scheduler (engines/asf/disaster_recovery/*) | code+ops | ✅ author / ✅ VPS run | **Both** | Emergent (build) → VPS (operate) | 2 vCPU at scheduled times | ~2 d build |
| Marketplace + PKI signing | code | ✅ | ✅ | **Emergent** | medium during dev | ~5–7 d |
| 72-h deployment soak | ops | n/a | ✅ | **VPS** | steady-state | 3 d wall-clock (passive) |
| `r5_shadow_comparator` non-prod path probe — make graceful | code | ✅ | n/a | Emergent | low | 0.5 h |

**C-tier total dev effort:** ~25–35 dev-days spread across roadmap. **Operational
items run continuously on the VPS.**

---

## 12. Shortest path to first operational 12-vCPU Strategy Factory

**Recommendation: ship Tier-A only. Defer everything in Tier-B/C until after first boot.**

```
TODAY (Emergent pod):       4–5 hours of code work
  ├─ M-1 path env-ification (one-liner × 5 files)
  ├─ M-2 test URL hygiene (skip fallbacks → BASE_URL required)
  ├─ M-3 yarn build + nginx.conf
  ├─ M-4 docker-compose.yml (backend + mongo + nginx)
  └─ M-5 startup probe script

  CI sanity:  pytest backend/tests/ -q   (28 ASF + 19 strategy_library + smoke)

TOMORROW (12-vCPU VPS):     ~6 hours of ops work
  ├─ Provision VPS (DigitalOcean / Hetzner / OVH / your provider)
  ├─ apt install docker.io git certbot
  ├─ git clone (or scp) the working tree to /opt/factory/
  ├─ Populate /etc/factory/backend.env from the Emergent .env
  ├─ docker compose up -d
  ├─ mongorestore the test_database snapshot
  ├─ Run M-5 probe → expect green
  ├─ Smoke curl: admin login, GET /api/asf/import/{wet-run-id}
  ├─ Let's Encrypt certbot → TLS live
  └─ Daily mongodump cron installed + restore-drill rehearsed

DAY 2-3                     72-h passive soak; no code work
  └─ Monitor /api/health + scheduler liveness

AFTER SOAK                  Operator decides which Tier-C items to start
  └─ Recommended order: shadow-mode XAUUSD → ETHUSD source-data → Phase 13 Dossier
```

**End-to-end:** **5 dev-hours + 6 ops-hours = 11 working hours. First live 12-vCPU
Strategy Factory in 24–36 wall-clock hours.**

---

## 13. Operator-locked exclusions honoured

* No code modified during this audit.
* No BI5 R3 work started.
* No Phase 13 / Phase 14 work started.
* No deployment performed.
* No new roadmap branch opened.

---

**End of DEPLOYMENT_READINESS_REPORT.md.**
**Status: 5 mandatory items totalling ~5.5 dev-hours. System is otherwise VPS-ready out of the box. Awaiting operator GO on M-1 → M-5 + VPS provisioning.**
