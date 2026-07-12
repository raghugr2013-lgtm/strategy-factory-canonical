# Strategy Factory v1.1 — Canonical Filesystem Layout

The repository is organized so that the frozen Strategy Factory core and the
future-module extension point are clearly separated. **Do not rearrange this
tree post-freeze** — the module loader, deploy scripts, and acceptance
reports all reference these paths.

```
/app
├── VERSION                             # "1.1.0"
├── README.md                           # entry point → points to this doc
├── .env.example                        # every required env var, defaults safe
├── docker-compose.yml                  # local dev stack (bundled Mongo)
├── ruff.toml                           # legacy per-file ignores
├── yarn.lock                           # frontend lockfile
│
├── backend/                            # ───────── CORE STRATEGY FACTORY ─────────
│   ├── app/                            # Phase-1 core (frozen)
│   │   ├── main.py                     # FastAPI factory · mounts core + legacy + modules
│   │   ├── auth/                       # JWT + RBAC + refresh + admin seed
│   │   ├── api/                        # health, admin, strategies, research, dashboard
│   │   ├── core/                       # settings, versioning
│   │   ├── db/                         # Mongo client, indexes, models
│   │   └── vie/                        # VIE bridge (client to /app/vie service)
│   ├── legacy/                         # ─── LEGACY PRESERVED CODE (frozen) ───
│   │   ├── api/                        # 83 v01 routers (auto-mounted under /api/*)
│   │   │   └── latent/                 # Phase-29+ latent routers
│   │   ├── engines/                    # 169 v01 engines
│   │   ├── config/                     # v01 config (symbols, universes)
│   │   └── tests/                      # v01 pytest suite
│   ├── engines/                        # (top-level shim path used by legacy imports)
│   ├── server.py                       # v01 uvicorn entry (kept for parity)
│   ├── requirements.txt                # frozen Python deps
│   ├── pytest.ini
│   ├── Dockerfile                      # python:3.12-slim + uvicorn + /api/health check
│   └── prop_firm_pdfs/                 # sample rulebooks (used by prop-firm ingestion)
│
├── frontend/                           # ───────── CORE STRATEGY FACTORY UI ────────
│   ├── package.json                    # yarn deps
│   ├── craco.config.js                 # @-alias config
│   ├── Dockerfile                      # node:20 build → nginx:alpine + /healthz
│   ├── public/
│   ├── legacy/                         # (unused; retained for parity)
│   └── src/                            # v01 verbatim (202/215 files byte-identical)
│       ├── App.js, index.js, App.css, index.css     # v01 root
│       ├── a11y/, assets/, constants/, hooks/,
│       │   i18n/, lib/, pages/Welcome/,
│       │   routes/, services/, stores/, styles/     # v01 support layers
│       ├── command/                    # v01 Command OS shell (frozen)
│       ├── components/                 # 66 v01 operator components + shadcn ui
│       └── modules/                    # ─── v1.1-owned extension barrel ───
│                                       #     (future modules register here)
│
├── vie/                                # ───────── VIE (Vendor Independent Engine) ─────
│   ├── router.py                       # FastAPI router
│   ├── registry.py                     # provider registry (auto-detects .env keys)
│   ├── providers/                      # openai, anthropic, gemini, deepseek, groq, kimi
│   ├── server.py                       # uvicorn entry
│   ├── requirements.txt
│   └── Dockerfile
│
├── infra/                              # ───────── INFRASTRUCTURE ─────────
│   ├── compose/
│   │   └── docker-compose.prod.yml     # production overlay (Traefik + external Mongo)
│   ├── traefik/                        # example Traefik dynamic config
│   ├── monitoring/                     # (Prometheus + Loki wiring notes)
│   ├── docker/                         # per-service overrides
│   └── scripts/                        # 20 operator scripts
│       ├── bootstrap-vps.sh            # first-time VPS setup
│       ├── deploy.sh                   # one-shot deploy
│       ├── deploy-dry-run.sh
│       ├── precheck.sh                 # health + secrets + network checks
│       ├── health.sh                   # runtime health probes
│       ├── backup.sh                   # mongodump wrapper
│       ├── restore.sh                  # mongorestore wrapper
│       ├── migrate-data.py / .sh       # v01 → v1.1 schema shim
│       ├── verify-migration.py         # post-restore verifier
│       ├── validate-migration.py
│       ├── audit-vps-db.py             # DB inventory + counts
│       ├── verify-vps-schema.py / .sh
│       ├── seed-synthetic-v01.py       # synthetic v01 seed for dev
│       ├── build-bundle.sh             # tarball builder for offline shipping
│       ├── verify-bundle.sh
│       └── rollback.sh                 # rollback to previous release
│
├── scripts/                            # ─── repo-root helpers ───
│   └── deploy_verify.sh                # 31-step E2E acceptance run
│
├── backup/                             # ─── MONGO MIGRATION ARTIFACTS ─────
│   ├── strategy_factory_v1.1_baseline.archive   # mongodump --gzip (canonical seed)
│   └── MANIFEST.md                     # collection counts + restore commands
│
├── modules/                            # ─── FUTURE MODULES (extension point) ───
│   ├── README.md                       # plugin contract (backend + frontend)
│   ├── __init__.py
│   └── <slug>/                         # e.g. arbicorex, gemhunter, research_intel
│       ├── manifest.yml
│       ├── backend/{api, engines, models}/
│       ├── frontend/
│       └── docs/
│
├── docs/                               # ─── DOCUMENTATION ─────
│   ├── FINAL_RECOVERY_REPORT.md
│   ├── openapi.json                    # snapshot of /api/openapi.json
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── legacy/                         # v01 archival docs
│   ├── modules/
│   │   └── ADDING_A_MODULE.md          # step-by-step module integration guide
│   └── acceptance_v1_1/                # ─── ACCEPTANCE PACK (this release) ───
│       ├── BACKEND_ACCEPTANCE_REPORT.md
│       ├── API_INVENTORY.md            # all 497 endpoints
│       ├── ENGINE_INVENTORY.md         # all 169 engines
│       ├── FRONTEND_RESTORATION_REPORT.md
│       ├── E2E_WORKFLOW_LOG.md
│       ├── DEPLOY_VERIFY_RUN.log       # live 31/31 PASS
│       ├── DEPLOYMENT_GUIDE.md
│       ├── ARCHITECTURE_DIAGRAM.md
│       ├── RELEASE_NOTES_v1.1.md
│       ├── RELEASE_PACKAGE.md          # sign-off block
│       ├── FILESYSTEM_LAYOUT.md        # this file
│       ├── screenshots_original/       # 12 v01 baseline JPGs
│       └── screenshots_recovered/      # 10 live v1.1 JPGs
│
├── memory/                             # ─── AGENT / PLATFORM MEMORY ─────
│   ├── PRD.md                          # canonical product requirements
│   └── test_credentials.md             # admin + storage keys
│
├── tests/                              # ─── REPO-LEVEL SMOKE TESTS ─────
├── test_reports/                       # (agent-produced JSON reports)
├── data_imports/                       # sample CSVs used by ingestion
└── audit_workspace/                    # (archival, not shipped)
```

## Separation rules

| Boundary | Frozen? | May new modules touch? |
|---|:---:|:---:|
| `/app/backend/legacy/**` | **Yes** | ❌ No (read-only import allowed) |
| `/app/backend/app/**` | **Yes** | ❌ No (loader only auto-mounts modules) |
| `/app/frontend/src/**` except `src/modules/` | **Yes** | ❌ No |
| `/app/vie/**` | **Yes** | ❌ No (use HTTP client) |
| `/app/infra/**` | Base is stable | ✅ May add module-specific compose overlays |
| `/app/modules/<slug>/**` | **No** | ✅ Yes — this is the module's territory |
| `/app/frontend/src/modules/**` | **No** | ✅ Yes — v1.1-owned barrel |
| Mongo collections with `<slug>_` prefix | **No** | ✅ Full control |
| Mongo core collections (`market_data`, `strategy_library`, …) | **Yes** | ❌ Read-only |

## Extension points summary

| Extension | Path | Loader |
|---|---|---|
| Backend router | `modules/<slug>/backend/api/*.py` → export `router: APIRouter` | `backend/app/main.py::_mount_future_modules` (auto) |
| Backend engine | `modules/<slug>/backend/engines/*.py` | Import from module code (never from core) |
| Frontend page | `modules/<slug>/frontend/*.jsx` + register in `frontend/src/modules/index.js` | v1.1-owned barrel + optional command-shell hook |
| Compose service | `modules/<slug>/infra/compose.<slug>.yml` | `docker compose -f docker-compose.yml -f modules/<slug>/infra/compose.<slug>.yml` |
| Mongo collections | `<slug>_*` | Standard Mongo client |
| Environment vars | Prefix with `<SLUG_UPPER>_` in `.env` | Read from the module code |
