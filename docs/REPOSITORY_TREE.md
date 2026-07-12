# Repository Tree — Strategy Factory v1.0.0

Snapshot of the delivered `strategy-factory/` repository. Legacy modules are summarised (344 files) rather than enumerated — the full listing lives inside the tarball.

## Root

```
strategy-factory/
├── .env.example
├── README.md
├── VERSION
├── backend/
├── frontend/
├── vie/
├── infra/
└── docs/
```

## backend/

Lean production core + preserved legacy tree.

```
backend/
├── .env                             # local preview env (safe defaults)
├── requirements.txt                 # runtime deps
├── server.py                        # supervisor entrypoint (imports app.main:app)
├── Dockerfile                       # multi-stage image (python:3.12-slim)
├── pytest.ini
├── app/                             # ── ACTIVE CORE ─────────────────────────
│   ├── __init__.py
│   ├── main.py                      # FastAPI factory + lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   ├── admin.py                 # /api/admin/{users,providers,providers/probe}
│   │   ├── dashboard.py             # /api/dashboard/summary
│   │   ├── health.py                # /api/health, /api/readiness, /api/version
│   │   ├── research.py              # /api/research/{query,history}
│   │   └── strategies.py            # /api/strategies CRUD
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── deps.py                  # get_current_user, require_roles
│   │   ├── routes.py                # /api/auth/{login,refresh,logout,me}
│   │   ├── security.py              # bcrypt + JWT encode/decode
│   │   └── seed.py                  # idempotent admin seed
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                # env-driven settings (fail-fast)
│   │   └── versioning.py            # /api/version payload
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                # BaseDocument, PyObjectId, User, RefreshToken
│   │   └── mongo.py                 # motor client + ensure_indexes()
│   └── vie/
│       ├── __init__.py
│       └── client.py                # THE ONLY LLM ENTRYPOINT (async httpx to VIE)
├── tests/
│   └── backend_test.py              # 16 pytest cases (health, VIE, auth, RBAC, CRUD, dashboard)
└── legacy/                          # ── PRESERVED FROM v01 (344 FILES) ──────
    ├── README.md                    # re-enablement pointer to STAGE2_PRESERVATION.md
    ├── requirements.legacy.txt      # pandas/numpy/apscheduler/pdfplumber/etc.
    ├── engines/                     # 175 files
    ├── api/                         # 66 legacy router files
    ├── cbot_engine/                 # cBot IR + transpiler
    ├── data_engine/                 # BI5 ingest, tick archive, gap analyzer, market calendar
    ├── scripts/                     # BI5 archive helpers, seed helpers
    └── factory_runner.py            # APScheduler sibling entrypoint (deferred)
```

**Active surface** = only `app/**` is imported by `server.py`. Legacy code is on disk and grep-able but never executed until an operator re-enables it (see `docs/STAGE2_PRESERVATION.md`).

## frontend/

React 18 + shadcn/ui + Tailwind + react-router-dom v7.

```
frontend/
├── .env                              # REACT_APP_BACKEND_URL for preview
├── package.json, yarn.lock
├── craco.config.js, jsconfig.json    # path aliases (@/…)
├── tailwind.config.js, postcss.config.js
├── components.json                   # shadcn
├── Dockerfile                        # multi-stage → nginx:1.27-alpine
├── nginx.conf                        # SPA fallback + /healthz
├── public/
│   ├── index.html
│   └── manifest.json
└── src/
    ├── App.js                        # routes + AuthProvider + Toaster
    ├── App.css, index.css, index.js
    ├── lib/
    │   ├── api.js                    # axios + refresh-token rotation interceptor
    │   └── auth.jsx                  # AuthContext + hasRole helper
    ├── components/
    │   ├── Layout.jsx                # sidebar with role-filtered nav
    │   ├── ProtectedRoute.jsx        # loading/redirect/role gate
    │   └── ui/                       # shadcn primitives (unmodified)
    ├── hooks/                        # shadcn use-toast hook
    └── pages/
        ├── LoginPage.jsx
        ├── DashboardPage.jsx
        ├── AdminPage.jsx             # Users tab + Providers tab
        ├── StrategiesPage.jsx        # list + create dialog + delete
        ├── ResearchPage.jsx          # prompt + task + provider + history
        └── ProvidersPage.jsx         # LIVE PROBE DASHBOARD (summary tiles + per-provider probe)
```

## vie/

Standalone provider-agnostic HTTP LLM gateway.

```
vie/
├── .env                              # per-provider API key env vars (blank by default)
├── requirements.txt
├── server.py                         # uvicorn entrypoint (imports vie.api:app)
├── Dockerfile                        # python:3.12-slim
├── __init__.py
├── api.py                            # FastAPI service: /health, /providers, /generate, /probe
├── config/                           # (reserved)
├── providers/
│   ├── __init__.py
│   ├── base.py                       # BaseProvider ABC
│   ├── openai_p.py
│   ├── anthropic_p.py
│   ├── gemini_p.py
│   ├── deepseek_p.py
│   ├── groq_p.py
│   └── kimi_p.py
├── registry.py                       # env-driven registry, availability flags
└── router.py                         # task→provider preference with failover
```

## infra/

Deployment scaffolding.

```
infra/
├── compose/
│   └── docker-compose.prod.yml       # backend + vie + frontend, joined to external vqb-network
├── scripts/
│   ├── deploy.sh                     # network→build→up→health
│   ├── health.sh                     # container + in-cluster + public HTTPS checks
│   ├── rollback.sh                   # FACTORY_IMAGE_TAG=… ./rollback.sh
│   ├── backup.sh                     # mongodump via shared mongo
│   └── restore.sh                    # mongorestore
├── traefik/
│   └── README.md                     # pointer — Traefik is externally managed
├── monitoring/
│   ├── prometheus/                   # (reserved)
│   ├── grafana/                      # (reserved)
│   ├── loki/                         # (reserved)
│   └── README.md                     # pointer — monitoring is externally managed
└── docker/                           # (reserved for future compose overrides)
```

## docs/

Canonical documentation (12 files).

```
docs/
├── ACCEPTANCE_REPORT.md              # this session's production acceptance
├── AUDIT_REPORT.md                   # Phase 0 file-level Keep/Merge/Replace/Discard/Archive matrix
├── ARCHITECTURE.md                   # topology + module layout + Mongo schema + env vars
├── DEPLOYMENT.md                     # clean-VPS bring-up in 3 steps
├── VIE.md                            # provider surface + routing + failure semantics + probe
├── AUTH_AND_RBAC.md                  # JWT + 5 roles + refresh rotation + SSO plug-in point
├── VERSIONING.md                     # VERSION + git commit + build date injection
├── STAGE2_PRESERVATION.md            # every preserved legacy module + re-enablement path
├── PLATFORM_COMPATIBILITY.md         # roadmap fit + shared-platform contract + ArbiCore X hook
├── REPOSITORY_TREE.md                # THIS FILE
├── RELEASE_NOTES.md                  # 1.0.0 changes
├── MIGRATION_NOTES.md                # v01 → 1.0.0 env + data + user migration
└── legacy/                           # 112 preserved artifacts
    ├── memory/                       # v01 PRD, roadmap, audits
    ├── vie-history/                  # VIE PHASE1/2/2.5/3 design docs
    ├── vps-snapshot/                 # docker ps/networks/volumes/images captures
    └── deployment-history-v06.md     # v04/v05/v06 fix history
```

## Bundle tarball

`strategy-factory-1.0.0.tar.gz` (2.1 MB compressed) — the entire tree above minus `node_modules/`, `__pycache__/`, and any `build/` output.

## File counts (delivered)

| Bucket | Files |
|---|---|
| Active source (backend/app + frontend/src + vie + infra + docs + tests + root) | ~140 |
| Preserved legacy code (`backend/legacy/**`) | 344 |
| Preserved legacy docs (`docs/legacy/**`) | 112 |
| shadcn/ui primitives (`frontend/src/components/ui/**`) | ~50 |
| **Total in tarball** | **~650** |
