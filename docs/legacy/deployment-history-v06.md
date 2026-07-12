# Strategy Factory — Production Deployment (Shared-Infra VPS)

**Target profile:** Ubuntu 22.04 VPS with the following shared services already running:

| Service | Version | Role |
|---|---|---|
| Traefik | v3.6.2 | Edge router + TLS terminator |
| MongoDB | (shared) | Primary persistence |
| Redis | (shared) | *(Not required by the Strategy Factory today)* |
| Portainer | — | Container UI |
| Prometheus | — | Metrics scraper |
| Grafana | — | Dashboards |
| Loki + Promtail | — | Log aggregation |
| cAdvisor | — | Container metrics |
| Node Exporter | — | Host metrics |

Shared Docker network: **`vqb-network`** (external, managed by the platform).

---

## 1. Files shipped in this package

```
deploy/prod/
├── docker-compose.prod.yml             # 3-service stack, Traefik-labeled, joins vqb-network
├── .env.production.example             # compose-level env (domain, mongo, redis, image tag)
├── env/
│   └── backend.env.production.example  # container-level env (JWT, admin, LLM, CORS)
├── nginx/
│   └── nginx-frontend.conf             # static SPA server (no TLS — Traefik terminates)
├── README.md                           # this file
└── frontend-build/                     # copy the production frontend build here
                                        # (extract from factory-frontend-build-*.tar.gz)
```

`docker-compose.prod.yml` intentionally does **NOT** ship its own MongoDB, Nginx-edge, or TLS terminator. All three are provided by the shared VPS layer.

---

## 2. Service topology

```
                    ┌─────────────────────────────────────────────────────┐
                    │                    Traefik (edge)                    │
                    │             websecure @ 443 · certresolver           │
                    └───────────────┬─────────────────────────┬────────────┘
                                    │                         │
              Host: ${FACTORY_DOMAIN} && PathPrefix(/api)     Host: ${FACTORY_DOMAIN}
                                    │                         │
                    ┌───────────────▼──────────┐   ┌──────────▼──────────┐
                    │      factory-backend     │   │   factory-frontend  │
                    │  FastAPI + uvicorn 8001  │   │   nginx 1.27 · 80   │
                    │  (no schedulers here)    │   │   static SPA build  │
                    └────────────┬─────────────┘   └─────────────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │      factory-runner      │
                    │  Sibling APScheduler     │
                    │  owner (Phase D.1)       │
                    │  FACTORY_RUNNER_OWNS_    │
                    │  SCHEDULERS=true         │
                    └────────────┬─────────────┘
                                 │
                        vqb-network (shared)
                                 │
                    ┌────────────▼─────────────┐
                    │  Shared MongoDB          │  ← SHARED_MONGO_URL
                    │  Shared Redis (optional) │  ← SHARED_REDIS_URL (unused today)
                    └──────────────────────────┘
```

---

## 3. Bring-up sequence

### 3.1 Prerequisites

1. Ensure `vqb-network` exists on the host:
   ```bash
   docker network inspect vqb-network >/dev/null || docker network create vqb-network
   ```
2. Ensure the shared MongoDB reachable via the connection URI you'll set as `SHARED_MONGO_URL`. Verify from any container on `vqb-network`:
   ```bash
   docker run --rm --network vqb-network mongo:7.0 mongosh "$SHARED_MONGO_URL" --eval "db.adminCommand({ping:1})"
   ```
3. Ensure the DNS record for `${FACTORY_DOMAIN}` points at this VPS's public IP.

### 3.2 Extract the handoff bundle onto the VPS

```bash
# On the VPS
mkdir -p /opt/factory
cd /opt/factory
tar -xzf ~/factory-handoff-bundle-20260614.tar.gz --strip-components=1
# The bundle roots to `factory-handoff-bundle-20260614/`; --strip-components=1
# lands its contents directly into /opt/factory/.

# Verify integrity
sha256sum -c MANIFEST_SHA256SUMS   # expect all OK

# Extract application source next to deploy/
tar -xzf factory-source-20260614_151752.tar.gz
# → /opt/strategy-factory/backend/, /opt/strategy-factory/frontend/, etc.
# The layout MUST end up as:
#   /opt/strategy-factory/backend/{Dockerfile,requirements.txt,server.py,...}
#   /opt/strategy-factory/deploy/prod/{docker-compose.prod.yml,...}
# The compose build context is `../../backend` (relative to deploy/prod/),
# resolving to /opt/strategy-factory/backend/ — the directory that
# contains requirements.txt at its root.

# One-time: install .dockerignore into the backend build context so
# the image doesn't bake the stale preview .env or __pycache__ trees.
cp /opt/strategy-factory/deploy/prod/backend.dockerignore \
   /opt/strategy-factory/backend/.dockerignore

# Extract the production frontend build into the deploy/prod/ tree
mkdir -p /opt/factory/deploy/prod/frontend-build
tar -xzf factory-frontend-build-20260614_151752.tar.gz -C /tmp/
mv /tmp/build/* /opt/factory/deploy/prod/frontend-build/
```

### 3.3 Restore the MongoDB dump into the SHARED instance

```bash
# Recommended: restore into a DEDICATED database (e.g. strategy_factory)
docker run --rm --network vqb-network \
  -v /opt/factory:/dump \
  mongo:7.0 \
  mongorestore \
    --uri "${SHARED_MONGO_URL}" \
    --archive=/dump/mongodb-dump-20260614_151752.archive.gz \
    --gzip \
    --nsFrom='test_database.*' \
    --nsTo='strategy_factory.*'
```

### 3.4 Populate env files

```bash
cd /opt/factory/deploy/prod

# Compose-level env (domain, mongo URI, image tag, redis)
cp .env.production.example .env.production
$EDITOR .env.production
chmod 600 .env.production

# Container-level env (JWT, admin, CORS, LLM providers)
cp env/backend.env.production.example env/backend.env.production
$EDITOR env/backend.env.production
chmod 600 env/backend.env.production
```

Absolute minimum values that MUST be changed:

- `.env.production` → `FACTORY_DOMAIN`, `SHARED_MONGO_URL`, `FACTORY_DB_NAME`
- `env/backend.env.production` → `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `CORS_ORIGINS`

### 3.5 Build + start

```bash
cd /opt/factory/deploy/prod
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d

# Wait for health
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f factory-backend
```

### 3.6 Smoke tests

```bash
# Direct container check (bypassing Traefik)
docker exec factory-backend curl -fsS http://localhost:8001/api/health

# Public route (via Traefik + TLS)
curl -fsS "https://${FACTORY_DOMAIN}/api/health"

# Confirm the imported strategy cohort survived the mongorestore
docker exec factory-backend python -c "
import asyncio; from engines.db import get_db
async def _(): db = get_db(); print('legacy_cohort =', await db.strategy_library.count_documents({'provenance.cohort_id':'1vcpu_2026_migration'}))
asyncio.run(_())
"
# Expect: legacy_cohort = 14

# Confirm the sibling runner is heartbeating
docker exec factory-backend python -c "
import asyncio; from engines.db import get_db
async def _():
    db = get_db()
    doc = await db.audit_log.find_one({'event':'factory_runner:heartbeat'}, sort=[('ts_dt', -1)])
    print('last heartbeat:', doc and doc.get('ts'))
asyncio.run(_())
"
```

---

## 4. `FACTORY_RUNNER_OWNS_SCHEDULERS` — recommended production value

| Value | Behaviour | Recommended for |
|---|---|---|
| **`true`** *(this stack)* | Uvicorn workers **skip** scheduler restoration on startup. The sibling `factory-runner` container owns the single APScheduler authority (orchestrator, auto, data-maintainer, BI5 sweep, challenge maker, monitoring). Uvicorn workers stay 100% dedicated to HTTP. | **Production (this stack).** Required whenever uvicorn is run with `--workers > 1`, or whenever a sibling runner container is present. |
| `false` *(default in source)* | Uvicorn workers restore their own schedulers. Sibling runner exits immediately on start. | Single-node dev boxes with `--workers 1` and no sibling process. Not appropriate for this compose stack — you would get duplicate schedulers (one per uvicorn worker) racing the sibling. |

**Recommended production value: `FACTORY_RUNNER_OWNS_SCHEDULERS=true`** — already set in both `factory-backend` and `factory-runner` service `environment:` blocks in `docker-compose.prod.yml`. Do not override to `false` in either env file.

**Enforcement guard:** `server.py:_factory_runner_owns_schedulers()` reads this flag on every uvicorn startup and short-circuits scheduler restore when `true`. `factory_runner.py:_main()` reads the same flag and exits cleanly when `false` — so accidentally leaving the sibling container running with the flag unset is safe (it will just idle-exit).

**Verification post-boot:** the `factory_runner:startup` audit event must appear in `audit_log` within 60 s of `up -d`. Sample query:

```javascript
db.audit_log.find({ event: /^factory_runner:/ }).sort({ ts_dt: -1 }).limit(5)
```

---

## 5. Health checks

### 5.1 Container-level (Docker + Traefik)

| Container | Test | Interval | Exposed to |
|---|---|---|---|
| `factory-backend` | `curl -fsS http://localhost:8001/api/health` | 30 s | Docker healthcheck + Traefik service healthcheck |
| `factory-frontend` | `wget -qO- http://localhost/healthz` | 30 s | Docker + Traefik |
| `factory-runner` | *(no HTTP surface — audit-log heartbeat)* | 5 min via `FACTORY_RUNNER_HEARTBEAT_SEC` | Grafana panel on `audit_log` |

`docker compose ps` will show HEALTHY / UNHEALTHY for backend + frontend. Traefik automatically pulls unhealthy backends out of rotation.

### 5.2 Business-level HTTP endpoints (already implemented, admin-token gated except where noted)

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/health` | Public | Liveness — always 200 while process is up. |
| `GET /api/admin/readiness` | Admin JWT | Full green/yellow/red tile matrix (DB, LLM, BI5, schedulers, data). Use as Grafana single-source-of-truth. |
| `GET /api/llm/diagnostics` | Public read-only | Which providers are configured, resolved routing, no keys leaked. |
| `GET /api/llm/runner-state` | Public read-only | Semaphore/failover state for the LLM runner. |
| `GET /api/llm/call-log/recent?limit=50` | Admin JWT | Recent LLM call tail (cost + drift monitoring). |
| `GET /api/orchestrator/heartbeat` | Public read-only | Scheduler liveness + last-tick timestamps. |
| `GET /api/diag/bi5/health` | Public read-only | BI5 archive coverage summary. |
| `GET /api/data/health` | Public read-only | Market-data coverage per symbol/timeframe. |

Grafana can poll any of these via the **JSON-API datasource plugin** (no code changes) or Prometheus's **json_exporter**.

---

## 6. Prometheus + Grafana + Loki wiring

### 6.1 Container-level metrics (works today, zero config)

cAdvisor auto-scrapes every container on the host — CPU, memory, network, filesystem, restart-count. The three containers show up in Grafana under their container_name labels:

- `container_name="factory-backend"`
- `container_name="factory-runner"`
- `container_name="factory-frontend"`

Recommended Grafana dashboard: `cAdvisor Dashboard 14282` (Kubernetes/Docker Container).

### 6.2 Host-level metrics

Node Exporter already covers disk I/O, load average, filesystem free space, etc. The `factory_bi5` and `factory_imports` named volumes appear under `/var/lib/docker/volumes/*` — set a Grafana alert on 80% capacity.

### 6.3 Log aggregation (Loki + Promtail)

Promtail's standard docker driver config picks up stdout/stderr from all three containers. The `logging: "promtail"` label on each service is a hint for Promtail's `docker_sd` job — filter dashboards by `container="factory-backend"`. Loki queries:

```logql
{container="factory-backend"} |= "ERROR"                             # backend errors
{container="factory-runner"}  |~ "scheduler|BI5|orchestrator"        # scheduler + BI5 sweep activity
{container=~"factory-.*"}     |~ "audit_log|factory_runner:"         # any audit-log write
```

### 6.4 Application-level Prometheus `/metrics` endpoint — NOT included

The current backend does not expose `/metrics`. If you want per-endpoint request counts / latencies scraped by Prometheus, add one of these — this is a small, additive change:

1. **`prometheus-fastapi-instrumentator` (recommended)** — 3 lines in `server.py`:
   ```python
   from prometheus_fastapi_instrumentator import Instrumentator
   Instrumentator().instrument(app).expose(app, endpoint="/api/metrics")
   ```
   Then add to `docker-compose.prod.yml` under `factory-backend.labels`:
   ```yaml
   prometheus.io/scrape: "true"
   prometheus.io/path:   "/api/metrics"
   prometheus.io/port:   "8001"
   ```
   And to Prometheus's `scrape_configs`:
   ```yaml
   - job_name: factory-backend
     docker_sd_configs:
       - host: unix:///var/run/docker.sock
     relabel_configs:
       - source_labels: [__meta_docker_container_label_prometheus_io_scrape]
         action: keep
         regex: "true"
   ```

2. **`json_exporter`** — no code change; scrape `GET /api/admin/readiness` and translate the green/yellow/red tiles into gauges. Best for high-signal-per-cost dashboards.

Either approach ships zero business logic changes and is fully additive.

---

## 7. Backup & restore

The compose stack owns four named volumes:

| Volume | Contents | Backup priority |
|---|---|---|
| `factory_bi5` | BI5 tick archive (~110 MB, grows ~30 MB/sym/mo) | Medium — re-downloadable from Dukascopy via `bi5_one_shot_backfill.py` |
| `factory_inbox` | ASF importer staging | High — pending imports are ephemeral but audit rows aren't |
| `factory_imports` | Bulk imports + master-bot exports | High — user uploads |
| `factory_misc` | `host_id`, prop-firm PDFs | Low — sample PDFs shipped in source |

MongoDB backup happens on the SHARED instance, not here. Ensure the shared Mongo's backup policy covers the `strategy_factory` DB.

Volume backup snippet (cron):

```bash
for v in factory_bi5 factory_inbox factory_imports factory_misc; do
  docker run --rm -v "$v:/src:ro" -v /var/backups/factory:/dst \
    alpine tar -czf "/dst/${v}-$(date +%F).tar.gz" -C /src .
done
find /var/backups/factory -type f -mtime +30 -delete
```

---

## 8. Zero-downtime redeploy

```bash
cd /opt/factory/deploy/prod
git pull                                      # or scp a new source tarball
docker compose --env-file .env.production -f docker-compose.prod.yml build factory-backend
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --no-deps --build factory-backend factory-runner
# Traefik automatically drains the old backend as healthchecks flip.
```

Because the frontend is a static SPA, the same pattern works for `factory-frontend` — but you can also just `rsync` a new build into `./frontend-build/` and Nginx serves it on the next request.

---

## 9. Rollback

```bash
cd /opt/factory/deploy/prod
docker compose --env-file .env.production -f docker-compose.prod.yml down
# Restore from the outer handoff bundle
tar -xzf ~/factory-handoff-bundle-20260614.tar.gz -C /tmp/rollback
# Point the image tag back or re-restore the mongodump if data-corruption
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

---

## 10. What is NOT shipped in this package (by design)

- ❌ MongoDB container — using shared Mongo on `vqb-network`.
- ❌ Nginx-edge / TLS terminator — Traefik owns edge routing + certs.
- ❌ Redis container — the Strategy Factory does not use Redis on any hot path today.
- ❌ Prometheus/Grafana/Loki/Promtail — using shared observability stack.
- ❌ certbot / letsencrypt — Traefik's certresolver handles it.
- ❌ `install.sh` — the shared VPS already has Docker + firewall + monitoring installed.

---

## 11. v04 — deployment-issue fixes (2026-06-15 evening)

The three issues surfaced by the first VPS deploy have all been patched in-bundle:

### 11.1 Frontend healthcheck was failing on `localhost`

**Symptom:** `wget: can't connect to remote host: Connection refused` from Docker's healthcheck, while `wget -qO- http://127.0.0.1/healthz` inside the container returns `ok`.

**Root cause:** alpine's musl libc has documented quirks resolving `localhost` in some container network configurations (relies on `/etc/hosts` + NSS ordering that isn't always present in slim images).

**Fix in v04:**
- `factory-frontend.healthcheck.test` now uses `http://127.0.0.1/healthz` explicitly, wrapped in `CMD-SHELL` with `--tries=1 --timeout=3` for tighter failure semantics.
- Same fix applied to `factory-backend.healthcheck.test` (`http://127.0.0.1:8001/api/health`) as a preventive measure.
- `start_period: 15s` added to the frontend so Docker doesn't mark it unhealthy in the first 15s while nginx is still binding.

### 11.2 Public frontend returned failure while `/api/*` worked

**Symptom:** `https://strategy.coinnike.com/api/health` returned 200 but `https://strategy.coinnike.com/` failed.

**Root cause (highest probability):** Two Traefik-side factors compounding:
1. The compose shipped Traefik-owned `loadbalancer.healthcheck.*` labels alongside Docker's healthcheck. When BOTH are configured and one fails (e.g. Docker HC due to §11.1), Traefik silently drops the container from the LB even after Docker reports healthy again, producing hard-to-diagnose 404/503 at the public URL.
2. Some deployments choke on the dict/map label form when values look boolean.

**Fix in v04:**
- **Removed** all `traefik.http.services.*.loadbalancer.healthcheck.*` labels from both backend and frontend. Docker's healthcheck is now the single source of truth; Traefik always routes to containers whose Docker HC is `healthy`.
- **Converted all labels to LIST form** (`- "traefik.enable=true"`) which is the canonical form documented in Traefik's Docker provider and immune to YAML-value-coercion edge cases.
- Set explicit `traefik.http.routers.factory-ui.service=factory-ui` (and `factory-api.service=factory-api`) so router→service binding is unambiguous.
- Bumped frontend router priority from `1` → `10` (still well below backend's `100` — no rule-length ambiguity).

### 11.3 Factory runner started but wrote no heartbeat / cohort count unreadable

**Symptom:** `factory-runner heartbeat missing from audit_log`, `unable to count legacy cohort`.

**Root cause (highest probability):** The runner's audit-log writes are wrapped in a bare `try/except` that swallows any Mongo write failure. When the shared Mongo is reachable to `mongorestore` but not from the `factory-runner` container (different auth path, wrong DB name, or `SHARED_MONGO_URL` pointing at a hostname the runner can't resolve), the process runs but writes nothing — silent failure.

**Fix in v04:**
- **New container healthcheck on `factory-runner`** that does a `motor` ping to `MONGO_URL`. Failure now surfaces as `docker ps` → `unhealthy` for `factory-runner` — the diagnosis is one command away.
- **Boot-marker echoes** on runner startup so `docker logs factory-runner` shows exactly what env the process saw (`MONGO_URL set: yes/no`, `DB_NAME=…`, `FACTORY_RUNNER_OWNS_SCHEDULERS=…`) before Python takes over.
- **`PYTHONUNBUFFERED=1`** so log lines flush immediately instead of buffering.
- **Default `FACTORY_RUNNER_HEARTBEAT_SEC` cut from 300s → 60s** so smoke tests see the first heartbeat within one minute of `docker compose up -d`. Bump back to 300 for steady-state noise reduction.
- **`prod-smoke-test.sh` now has a dedicated Mongo-ping check** (step 5) that runs BEFORE the heartbeat/cohort checks. If Mongo is unreachable, this fails first with a clear error, so operators don't chase downstream ghosts.
- The audit-log query in the smoke test now looks for any `factory_runner:*` row (startup / heartbeat / shutdown), not just heartbeats — startup fires immediately at process start and proves the runner reached Mongo.

### 11.4 Diagnostic commands for the three issues

```bash
# Issue 1 — frontend healthcheck
docker inspect factory-frontend --format='{{json .State.Health}}' | jq
docker logs factory-frontend --tail=50

# Issue 2 — Traefik routing (needs jq; adjust for your Traefik dashboard)
curl -s http://traefik:8080/api/http/routers 2>/dev/null | jq '.[] | select(.name | startswith("factory-"))'
curl -s http://traefik:8080/api/http/services 2>/dev/null | jq '.[] | select(.name | startswith("factory-"))'

# Issue 3 — runner Mongo path
docker logs factory-runner --tail=100
docker exec factory-runner python -c "
import os, asyncio
import motor.motor_asyncio as m
async def _():
    c = m.AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000)
    print(await c.admin.command('ping'))
    print('DB_NAME=', os.environ.get('DB_NAME'))
    print('collections =', await c[os.environ['DB_NAME']].list_collection_names())
asyncio.run(_())"
```

If step 3 fails with a `ServerSelectionTimeoutError`, check:
- `SHARED_MONGO_URL` uses the container-network-resolvable hostname (`mongo`), not `localhost`.
- Auth database — is `?authSource=admin` present in the URI?
- The Mongo container is on `vqb-network` (`docker inspect mongo | jq .[0].NetworkSettings.Networks`).

---

## 12. v05 — smoke-test & healthcheck fixes (2026-06-16)

Three smoke-test failures on the first v04 deploy — the app itself was fine.

### 12.1 `factory-runner` reported `unhealthy` even though logs showed successful startup

**Root cause:** v04's runner healthcheck used a YAML folded scalar (`>-`) with an inline `async def` block. YAML folds newlines to spaces, which destroys Python indentation → `IndentationError` inside the container → healthcheck always fails → container permanently `unhealthy` even when the runner is happily writing schedulers and heartbeats.

**Fix in v05:** replaced the multi-line async def with a single-line expression:

```yaml
test: ["CMD-SHELL", "python -c \"import asyncio, os, motor.motor_asyncio as m; asyncio.run(m.AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000).admin.command('ping'))\" || exit 1"]
```

`AsyncIOMotorClient(...).admin.command('ping')` returns a coroutine directly — no `async def` wrapper needed, no indentation, no YAML folding hazard. Also bumped `start_period` from 30s → 45s to give the runner time to complete scheduler restore before the first HC fires.

### 12.2 `factory-runner audit query failed (empty)` in the smoke test

**Root cause:** the smoke test used `docker exec factory-backend python - <<'PY'` (heredoc to python's stdin) WITHOUT the `-i` flag. Docker's `exec` does not attach stdin by default, so the container's `python -` process saw an empty stdin → executed no code → produced no output → the smoke test recorded "empty" and reported failure. Same bug in the legacy cohort count query.

**Fix in v05:** added `-i` to both heredoc `docker exec` calls (`docker exec -i factory-backend python - <<'PY'`). The single-line `docker exec ... python -c "..."` calls (Mongo ping, readiness tiles) were unaffected because they use `-c`, not stdin.

### 12.3 `unable to count legacy cohort` on a fresh deploy

**Root cause:** the smoke test correctly reported that the 14-strategy legacy cohort was not present in the DB. On a fresh deploy this happens whenever the operator has not yet run the `mongorestore` step from README §3.3. The check is not decorative — the entire Strategy Factory expects the 14 imported strategies to be present in `strategy_library` with `provenance.cohort_id = "1vcpu_2026_migration"`.

**Fix in v05:** the smoke test now distinguishes three cases with clearer messages:
- `count == 14` → PASS ("legacy strategy cohort restored → 14 documents")
- `count == 0`  → FAIL with actionable text ("did you run mongorestore from the handoff dump? See README §3.3")
- `0 < count < 14` or `count > 14` → FAIL as "partial mongorestore"

**Answer to your explicit question:** on a clean deploy, the cohort check MUST return 14. Empty is a sign that `mongorestore` was skipped or targeted the wrong DB. Run the command from README §3.3 pointing at your shared Mongo instance:

```bash
docker run --rm --network vqb-network \
  -v /opt/strategy-factory:/dump \
  mongo:7.0 \
  mongorestore --uri "${SHARED_MONGO_URL}" \
    --archive=/dump/mongodb-dump-20260614_151752.archive.gz \
    --gzip --nsFrom='test_database.*' --nsTo='strategy_factory.*'
```

Then re-run `./prod-smoke-test.sh` and all three should turn green.

### 12.4 Direct answers to your four questions

1. **"Is the audit failure simply a consequence of the broken healthcheck, or a separate application issue?"** — Neither. It's a smoke-test bug (`docker exec` missing `-i` flag). The runner itself is fine; audit rows exist in the DB but the smoke test couldn't read them.
2. **"On a fresh production installation, should the legacy cohort check legitimately return empty?"** — NO. It should return 14 after `mongorestore` from the handoff dump. An empty result means mongorestore hasn't been run (or ran against the wrong DB).
3. **"Is the runner actually healthy and only misreported because of the healthcheck bug?"** — YES. The runner's own operation (scheduler restore, data maintainer restore, heartbeat writes) all succeed. Docker was misreporting because the HC command itself was crashing with an IndentationError.
4. **"Please provide the corrected healthcheck …"** — Done, v05 above.

Once v05 is deployed + `mongorestore` is run, all three smoke-test failures should clear on the same invocation.

---

## 13. v06 — runner healthcheck: motor → pymongo (2026-06-16)

The v05 healthcheck was still failing with:

```
ValueError: a coroutine was expected, got <Future pending>
```

**Root cause:** Motor's `AsyncIOMotorClient(...).admin.command('ping')` returns a `Future` (not a coroutine) when called outside a running event loop. `asyncio.run()` rejects Futures with the above error, so the HC command exited non-zero → Docker marked the runner unhealthy even though the process was fine.

**Fix in v06:** replaced the motor+asyncio one-liner with a pymongo (synchronous) equivalent. Motor lists `pymongo>=4.5` as a hard dependency, so pymongo is already inside every backend/runner image — no `pip install`, no image rebuild:

```yaml
test: ["CMD-SHELL", "python -c \"import os, pymongo; pymongo.MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=3000).admin.command('ping')\" || exit 1"]
```

`pymongo.MongoClient(...).admin.command('ping')` is a plain synchronous call: no event loop, no Future, no coroutine. It raises on failure (non-zero exit → unhealthy) and returns `{'ok': 1.0}` on success (zero exit → healthy). Verified inside this workspace: `import pymongo; pymongo.MongoClient(...).admin.command('ping') → {'ok': 1.0}`.

If for any reason pymongo were unavailable in the future, the equivalent shell-only fallback is `curl` + `nc`:

```yaml
# Alternative: TCP reachability only (does NOT validate auth or that
# the target DB actually exists — just proves the TCP socket answers).
# Uncomment ONLY if switching away from pymongo.
# test:
#   - "CMD-SHELL"
#   - >-
#     python -c "import os, urllib.parse as u; p = u.urlparse(os.environ['MONGO_URL']); print(p.hostname, p.port or 27017)" |
#     xargs -n2 sh -c 'exec 3<>/dev/tcp/$0/$1' _ _
```

The pymongo variant is preferred because it validates auth + reachability + a live command round-trip.

### Direct answer to the four questions in this round
1. **Runner healthcheck is broken?** — Yes, one last time. v05's motor+asyncio approach hits a Future-vs-coroutine trap on modern motor releases.
2. **Corrected healthcheck?** — v06 above. One line. Sync. No async pitfalls.
3. **Dockerfile / compose change needed?** — Compose YAML only. Dockerfile unchanged. Image unchanged. `docker compose up -d --force-recreate factory-runner` is enough; no rebuild.
4. **Shell-based fallback?** — Documented above (commented out in compose). Pymongo is preferred; the shell fallback is there for the record only.

---

**End of README.**
