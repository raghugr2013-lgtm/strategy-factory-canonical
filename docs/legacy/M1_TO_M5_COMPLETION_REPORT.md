# M1_TO_M5_COMPLETION_REPORT.md — Deployment Packaging

**Executed:** 2026-02 (this session) · per operator authorisation
("Proceed with M1–M5 deployment packaging work only").
**Constraints honoured:** No BI5 R3 · no Phase 13 · no Phase 14 · no shadow-mode trade capture · no additional strategy validation · no deployment performed.

---

## 1. Status

✅ **All 5 mandatory items complete. Deployment bundle ready for VPS transfer.**

| Item | Status | Effort |
|---|---|---:|
| M-1 path env-ification | ✅ done (5 surgical edits, defaults unchanged for backward compat) | ~40 min |
| M-2 test URL hygiene | ✅ done (single conftest.py addition; no per-file edits) | ~15 min |
| M-3 nginx + frontend build | ✅ done (nginx config + build helper script) | ~30 min |
| M-4 docker-compose stack | ✅ done (3-service: backend + mongo + nginx + 8 volumes + internal net) | ~45 min |
| M-5 startup probe | ✅ done (multi-check probe + install + backup + restore drill) | ~30 min |
| **TOTAL** | | **~2.7 h** |

Regression: **47/47 ASF + strategy_library tests pass.** Zero behavioural drift
(every env-var default equals the pre-edit constant).

---

## 2. Code changes (M-1 + M-2)

### M-1 — Path env-ification (5 edits)

| File | Change |
|---|---|
| `backend/api/asf.py` | `inbox_dir = p.get("inbox_dir", os.environ.get("ASF_INBOX_DIR", "/app/_migration_inbox/"))` |
| `backend/engines/asf/importer/migration_adapter.py` | `inbox_dir: Optional[str] = None` parameter; resolved from `ASF_INBOX_DIR` at call-time |
| `backend/api/data.py` | `IMPORT_DIR = os.environ.get("BULK_IMPORT_DIR", "/app/data_imports")` |
| `backend/engines/master_bot_export.py` | `EXPORT_DIR_DEFAULT = os.environ.get("MASTER_BOT_EXPORT_DIR", "/app/data_imports/master_bots")` |
| `backend/engines/master_bot_pack.py` | `PACK_DIR_DEFAULT = os.environ.get("MASTER_BOT_PACK_DIR", "/app/data_imports/master_bot_packs")` |

All defaults are **identical to the pre-edit constants** → backward-compatible.

### M-2 — Test URL hygiene (1 addition)

`backend/conftest.py` gains an autouse `pytest_collection_modifyitems` block
that scans each test file for `preview.emergentagent.com` references and skips
them when `BASE_URL` / `REACT_APP_BACKEND_URL` is either unset or pointing to a
dead preview host. Net effect: 17 test files no longer need per-file edits;
they simply skip cleanly on the VPS unless the operator points BASE_URL at the
live host.

---

## 3. Deployment bundle (M-3, M-4, M-5)

Self-contained at `/app/deploy/` (also packaged as `/app/deploy/factory-deploy-bundle.tgz`,
**10 KB tarball**, ready for `scp`).

```
deploy/
├── README.md                       2.6 KB · operator manifest + quick-start
├── docker-compose.yml              3.0 KB · 3-service stack + 8 volumes + internal net
├── nginx/
│   └── factory.conf                3.4 KB · TLS + reverse-proxy + static-serve
├── env/
│   ├── backend.env.example         1.5 KB · 13 env vars (5 must-change)
│   └── frontend.env.example        0.3 KB · build-time only
└── scripts/
    ├── install.sh                  3.2 KB · one-shot VPS provisioner
    ├── build_frontend.sh           0.8 KB · yarn build helper (run on Emergent)
    ├── startup_probe.sh            3.7 KB · M-5 — green/red verdict
    ├── backup.sh                   1.4 KB · daily mongodump + weekly BI5 tarball
    └── restore_drill.sh            1.2 KB · backup-restore rehearsal
```

### Static validation (all green)

* **YAML:** docker-compose.yml parses cleanly. 3 services (mongo, backend, nginx).
  8 volumes (mongo_data, mongo_config, factory_bi5, factory_inbox, factory_imports,
  factory_misc, factory_certs, factory_acme). 1 internal network.
* **nginx.conf:** brace-balanced · contains `proxy_pass`, `ssl_certificate`,
  `listen 443` · matches expected reverse-proxy shape.
* **All 5 shell scripts:** `bash -n` syntax check passes.
* **All scripts:** `chmod +x` applied.

### What each artifact does

| Artifact | Responsibility |
|---|---|
| `docker-compose.yml` | Single-command lifecycle: backend (FastAPI + 12 APScheduler jobs) + mongo:7.0 + nginx:1.27-alpine. Bind-mounts host volumes for BI5 archive · ASF inbox · imports · TLS certs. Internal `factory-internal` network — mongo/backend NEVER exposed to the host. |
| `nginx/factory.conf` | TLS terminator (LE) · static-serve `/usr/share/nginx/html` · reverse-proxy `/api/*` → `backend:8001` · `/healthz` probe · security headers · ACME http-01 challenge path. |
| `env/backend.env.example` | 13 env vars: 6 inherited from Emergent (MONGO_URL, DB_NAME, JWT_SECRET, ADMIN_*, CORS_ORIGINS, EMERGENT_LLM_KEY), 5 new M-1 paths (`ASF_INBOX_DIR`, `BULK_IMPORT_DIR`, `MASTER_BOT_EXPORT_DIR`, `MASTER_BOT_PACK_DIR`, `BI5_ARCHIVE_PATH`), 2 optional (`POD_HOST_ID`, `BUILD_LABEL`). |
| `env/frontend.env.example` | Build-time only — bakes `REACT_APP_BACKEND_URL` into the static bundle. |
| `install.sh` | Detects distro (Ubuntu/Debian/RHEL/Rocky/Alma/Fedora). Installs docker + compose-plugin + certbot + ufw + mongosh. Configures firewall (22 + 80 + 443 only). Creates `/opt/factory/` layout with correct perms (`env/` 0700). Idempotent. |
| `build_frontend.sh` | Runs on Emergent (or any Node 20 + Yarn 1.22 host). `yarn install --frozen-lockfile && REACT_APP_BACKEND_URL=… yarn build`. Outputs static bundle to `/app/deploy/frontend-build/`. |
| `startup_probe.sh` | M-5 — green/red verdict. 14 checks: 3 container-up · 2 HTTP · 1 admin-login · 4 Mongo · 3 admin-endpoints · 3 volume presence. Exits 0 on green, 1 on any red. |
| `backup.sh` | Daily mongodump (gzip archive) · weekly BI5 archive tarball (Monday only) · daily config tarball · 30-day retention prune · syslog one-liner. |
| `restore_drill.sh` | Restores latest mongodump into `factory_restore_drill` scratch DB, prints row counts for the 6 key collections, drops the scratch DB. Live `factory` DB never touched. |

---

## 4. Deployment quick-start (operator-runnable)

```bash
# ── On Emergent ────────────────────────────────────────────────────
REACT_APP_BACKEND_URL=https://factory.example.com \
  /app/deploy/scripts/build_frontend.sh

mongodump --uri="$MONGO_URL" --db=test_database --archive --gzip \
  > /tmp/factory_dump.gz

tar -czf /tmp/factory-deploy.tgz \
  -C /app deploy/ \
  -C /tmp factory_dump.gz

# ── On the VPS (root) ──────────────────────────────────────────────
scp /tmp/factory-deploy.tgz root@VPS:/root/
ssh root@VPS
cd /root && tar -xzf factory-deploy.tgz -C /opt/factory/

sudo /opt/factory/scripts/install.sh    # apt + docker + ufw + layout

cd /opt/factory
cp env/backend.env.example env/backend.env
chmod 600 env/backend.env
$EDITOR env/backend.env                  # rotate JWT_SECRET, ADMIN_PASSWORD

docker compose up -d
docker compose exec -T mongo mongorestore --gzip --archive \
  --nsFrom='test_database.*' --nsTo='factory.*' < /tmp/factory_dump.gz

certbot certonly --webroot -w /var/www/acme \
  -d factory.example.com --agree-tos -m you@example.com
$EDITOR /opt/factory/nginx/factory.conf  # set server_name + cert paths
docker compose restart nginx

ADMIN_EMAIL=admin@factory.local \
ADMIN_PASSWORD='your-pass' \
BASE=https://factory.example.com \
  /opt/factory/scripts/startup_probe.sh
# Expect: STATUS: GREEN

cp /opt/factory/scripts/backup.sh /etc/cron.daily/factory-backup
chmod +x /etc/cron.daily/factory-backup
/opt/factory/scripts/backup.sh && /opt/factory/scripts/restore_drill.sh
```

End-to-end: **~6 ops-hours**, idempotent at every step, fully reversible until
`docker compose up -d`.

---

## 5. Regression evidence

```
$ python -m pytest tests/test_asf_schema.py tests/test_asf_dedup_policy.py \
                   tests/test_asf_migration_adapter.py tests/test_strategy_library.py -q
...............................................                          [100%]
47 passed in 0.20s
```

* 7 schema tests (ASF v1.0 Pydantic models)
* 5 dedup-policy tests
* 16 migration-adapter integration tests
* 19 strategy_library tests

Zero failures introduced by M-1 or M-2.

---

## 6. Locked exclusions honoured

| Activity | Status |
|---|---|
| BI5 R3 (B-3 / B-6 / B-7) | ❌ Not started |
| Phase 13 Dossier Engine | ❌ Not started |
| Phase 14 Valuation Engine | ❌ Not started |
| Shadow-mode trade capture | ❌ Not started |
| Additional strategy validation | ❌ Not started |
| Deployment performed | ❌ Not performed — bundle is what an operator uses to deploy |

---

## 7. Files changed/added in this run

### Code (6 surgical edits)
* `backend/api/asf.py`
* `backend/api/data.py`
* `backend/engines/asf/importer/migration_adapter.py`
* `backend/engines/master_bot_export.py`
* `backend/engines/master_bot_pack.py`
* `backend/conftest.py`

### New deployment bundle (10 files at `/app/deploy/`)
* `README.md`
* `docker-compose.yml`
* `nginx/factory.conf`
* `env/backend.env.example`
* `env/frontend.env.example`
* `scripts/install.sh`
* `scripts/build_frontend.sh`
* `scripts/startup_probe.sh`
* `scripts/backup.sh`
* `scripts/restore_drill.sh`

### Companion document
* `M1_TO_M5_COMPLETION_REPORT.md` (this file)

### Packaged tarball
* `deploy/factory-deploy-bundle.tgz` (10 KB, ready for scp)

---

**End of M1_TO_M5_COMPLETION_REPORT.md.**
**Status: deployment bundle complete and validated. Awaiting operator GO on VPS bring-up.**
