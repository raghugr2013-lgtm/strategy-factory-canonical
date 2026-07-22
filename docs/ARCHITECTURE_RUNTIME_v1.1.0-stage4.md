# Strategy Factory — Architecture

## Runtime topology

```
                            ┌────────────────────────────────────────┐
                            │           Traefik (edge, TLS)          │
                            └──────────┬───────────────┬─────────────┘
                     Host: ${FACTORY_DOMAIN}         Host: same, PathPrefix(/api)
                                       │               │
                              ┌────────▼──────┐  ┌─────▼──────────┐
                              │ factory-      │  │ factory-       │
                              │ frontend      │  │ backend        │
                              │ nginx :80     │  │ fastapi :8001  │
                              │ SPA (React)   │  │ /api/* only    │
                              └───────────────┘  └───────┬────────┘
                                                         │ HTTP
                                                 ┌───────▼──────────┐
                                                 │ factory-vie      │
                                                 │ fastapi :8100    │
                                                 │ 6 provider adapt.│
                                                 └───┬──────────────┘
                                                     │ HTTPS (per-provider)
                                          ┌──────────┴─────────────┐
                                          │ OpenAI · Anthropic · Gemini
                                          │ DeepSeek · Groq · Kimi     │
                                          └─────────────────────────────┘

                     ┌─────────────────────────────────────────────────┐
                     │  Shared vqb-network                             │
                     │   • MongoDB (external — SHARED_MONGO_URL)       │
                     │   • Redis (unused today)                        │
                     │   • Prometheus / Grafana / Loki (scrape labels) │
                     └─────────────────────────────────────────────────┘
```

## Container roles

| Container | Image | Purpose | Public? |
|---|---|---|---|
| `factory-backend` | strategy-factory/backend | HTTP API (auth, admin, strategies, research, dashboard) | via Traefik `PathPrefix(/api)` |
| `factory-vie`     | strategy-factory/vie     | Provider-agnostic LLM gateway | in-cluster only |
| `factory-frontend`| strategy-factory/frontend| nginx serving React SPA build | via Traefik `Host()` |

VIE is **NEVER** exposed publicly. The backend is the only client.

## Module layout

```
backend/
├── app/
│   ├── main.py                # FastAPI app factory + lifespan
│   ├── core/config.py         # env-driven settings (fail-fast)
│   ├── core/versioning.py     # /api/version payload
│   ├── db/
│   │   ├── mongo.py           # motor client + ensure_indexes()
│   │   └── models.py          # BaseDocument + PyObjectId + User + RefreshToken
│   ├── auth/
│   │   ├── security.py        # hash_password, verify_password, JWT encode/decode
│   │   ├── deps.py            # get_current_user + require_roles(...)
│   │   ├── seed.py            # idempotent admin seed
│   │   └── routes.py          # /api/auth/{login,refresh,logout,me}
│   ├── vie/
│   │   └── client.py          # VIEClient — the ONLY LLM entrypoint
│   ├── api/
│   │   ├── health.py          # /api/health, /api/readiness, /api/version
│   │   ├── admin.py           # /api/admin/{users,providers}
│   │   ├── strategies.py      # /api/strategies (CRUD)
│   │   ├── research.py        # /api/research/{query,history} — via VIE
│   │   └── dashboard.py       # /api/dashboard/summary
│   └── modules/               # reserved for future Stage 2 wiring
├── legacy/                    # v01 preserved verbatim (see AUDIT_REPORT §7)
│   ├── engines/               # 145 engines
│   ├── api/                   # 60 routers
│   ├── cbot_engine/, data_engine/, factory_supervisor/, scripts/, tests/
│   └── requirements.legacy.txt
├── requirements.txt
├── Dockerfile
└── server.py                  # `from app.main import app`

vie/
├── api.py                     # HTTP surface: /health, /providers, /generate
├── registry.py                # env-driven provider registry (6 providers, availability flags)
├── router.py                  # task→provider preference with failover order
├── providers/
│   ├── base.py                # BaseProvider ABC
│   ├── openai_p.py            # ↓ six concrete adapters, each self-reports availability
│   ├── anthropic_p.py
│   ├── gemini_p.py
│   ├── deepseek_p.py
│   ├── groq_p.py
│   └── kimi_p.py
├── server.py                  # uvicorn entrypoint
├── requirements.txt
└── Dockerfile

frontend/
├── src/
│   ├── App.js                 # BrowserRouter + AuthProvider + ProtectedRoute
│   ├── lib/api.js             # axios client + refresh token rotation + error normalizer
│   ├── lib/auth.jsx           # AuthContext + hasRole()
│   ├── components/
│   │   ├── Layout.jsx         # sidebar + role-filtered nav
│   │   ├── ProtectedRoute.jsx # loading / redirect / role gate
│   │   └── ui/                # shadcn/ui primitives
│   └── pages/
│       ├── LoginPage.jsx
│       ├── DashboardPage.jsx
│       ├── StrategiesPage.jsx
│       ├── ResearchPage.jsx
│       ├── ProvidersPage.jsx
│       └── AdminPage.jsx
├── Dockerfile                 # multi-stage build → nginx:1.27-alpine
└── nginx.conf                 # SPA fallback + /healthz

infra/
├── compose/docker-compose.prod.yml   # backend + vie + frontend
├── scripts/{deploy,health,rollback,backup,restore}.sh
├── traefik/, monitoring/prometheus/, monitoring/grafana/, monitoring/loki/
│                                     # docs referencing existing shared services
docs/
├── AUDIT_REPORT.md, DEPLOYMENT.md, ARCHITECTURE.md, VIE.md,
│   AUTH_AND_RBAC.md, VERSIONING.md, RELEASE_NOTES.md
```

## Data model (MongoDB)

- `users` — `{ user_id, email(unique), password_hash, name, role, status, created_at, updated_at }`
- `refresh_tokens` — `{ jti(unique), user_id, expires_at(TTL), revoked, created_at }`
- `strategies` — `{ strategy_id, name, description, symbol, timeframe, ir?, tags[], status, created_by, created_at, updated_at }`
- `research_queries` — `{ query_id, prompt, task, provider, model, output, usage, created_by, created_at }`
- `audit_log` — reserved for future Stage 2 re-enablement

`ensure_indexes()` is called at startup and is idempotent.

## Environment variables (canonical)

See `.env.example`. Notably:

- **Fail-fast (required):** `MONGO_URL`, `DB_NAME`, `JWT_SECRET`
- **Refresh-token TTL:** `JWT_ACCESS_TTL_MIN` (default 60), `JWT_REFRESH_TTL_DAYS` (default 7)
- **Admin bootstrap:** `ADMIN_EMAIL`, `ADMIN_PASSWORD` (blank → skip seeding, no crash)
- **VIE:** `VIE_URL`, `VIE_TIMEOUT_S`, plus 6× provider keys and 6× optional model overrides
- **Version metadata:** `BUILD_VERSION`, `BUILD_COMMIT`, `BUILD_DATE` — injected at Docker build time

## Reserved namespaces

- `docker network create vqb-network` — shared across Strategy Factory + future ArbiCore X
- Mongo DB name — configurable per tenant; ArbiCore X will live in a sibling DB on the same instance
- VIE — engineered as a standalone container so ArbiCore X can consume the same gateway
