# Platform Compatibility

Confirmation that this repository is the canonical foundation for the remainder of the Strategy Factory roadmap **and** the shared platform substrate for future VQB products (specifically ArbiCore X).

---

## 1. Strategy Factory roadmap fit

This repository will host **all future Strategy Factory development**. No further consolidation or architectural rewrite is required to implement the Stage 2 features listed below.

| Feature | Required infrastructure (all present) | Notes |
|---|---|---|
| **Research Engine completion** | `/api/research` core, VIE, `research_queries` collection, legacy `research_lineage` + `market_intelligence` engines | Additive endpoints under `/api/research/*` |
| **Strategy Generation** | `strategies` collection, VIE `task="generation"`, legacy `strategy_engine` + `strategy_ir*` | IR templates already present in `backend/legacy/engines/` |
| **Validation** | Legacy `validation_engine`, `signal_quality`, `spread_analyzer` | Add `/api/validation/*` routers |
| **Optimization** | Legacy `optimization_engine`, `ga_optimizer`, `random_search_optimizer` (requires `numpy`/`pandas`) | Install `requirements.legacy.txt` |
| **Backtesting** | Legacy `backtest_engine`, `execution_simulator`, `walk_forward_engine`, `monte_carlo_engine`, BI5 tick archive | Enable `factory_bi5` volume + BI5 backfill script |
| **AI Explanation** | VIE `task="explanation"`, legacy `strategy_description`, `analysis_engine`, `agent_advisor`, `ai_orchestrator` | Migrate legacy LLM calls to VIE (documented) |
| **Strategy Improvement** | Legacy `refinement_engine`, `mutation_engine`, `evolution_engine` + APScheduler sibling | Enable `factory-runner` container |
| **Strategy Comparison** | Legacy `parity_certification`, `parity_drift_view`, `r5_shadow_comparator` | Read-only diagnostic; no infrastructure changes |
| **Master Bot framework** | Legacy `master_bot_*` (7 engines) + `legacy/api/master_bot.py`, `deployment.py` | Additive routers under `/api/master-bot/*` |
| **Strategy Dossier** | Legacy `strategy_memory`, `strategy_profiler`, `strategy_lifecycle` | Extends existing `strategies` documents |
| **Automated Valuation** | Legacy `expected_value`, `risk_of_ruin`, `pass_probability`, `readiness_engine` | Reads from existing collections |
| **Internal Strategy Library** | Existing `strategies` collection + legacy `strategy_library`, `strategy_ranking_engine`, `governance_universe` | Frontend page already scaffolded (`StrategiesPage.jsx`) |

**Architectural contract for Stage 2 additions:**
1. Use `app.include_router(...)` in `app/main.py` — never edit existing routers, only add.
2. All LLM calls go through `app.vie.client.get_vie()` — never import a provider SDK directly.
3. Role-gate every mutating endpoint with `Depends(require_roles(...))`.
4. New collections follow the `BaseDocument` + `PyObjectId` pattern in `app/db/models.py`.
5. New env vars land in `.env.example` — same fail-fast policy in `app/core/config.py`.
6. New docs live in `docs/` following the existing naming convention.

Follow those six rules and Stage 2 slides in without a single line of restructuring in the Phase 1 core.

---

## 2. Shared platform components (reusable without restructuring)

The following building blocks are engineered as **shared platform substrate**, not Strategy-Factory-specific implementations. Each is decoupled from business logic and reusable by future VQB products.

### 2.1 Authentication (`backend/app/auth/`)
- Local JWT (HS256) + bcrypt password hashing
- Refresh-token rotation with Mongo-backed revocation
- Interface: `get_current_user(request)` returns a `UserPublic` object regardless of the token issuer
- **Reusable by any FastAPI service** that mounts this package as-is
- **Modular SSO plug-in point** (documented in `docs/AUTH_AND_RBAC.md`): swap `security.py` for Keycloak/Authentik/OIDC without touching route guards

### 2.2 RBAC (`backend/app/auth/deps.py`)
- 5 canonical roles: `admin`, `developer`, `researcher`, `operator`, `viewer`
- Enforcement via `require_roles(*roles)` dependency
- **Reusable across all VQB products** — a user with role `researcher` in Strategy Factory has the same permission surface in ArbiCore X (or any future product) that consumes this auth module.
- Adding a product-specific role is a one-line change in `models.py::ALL_ROLES` — no cascading refactor.

### 2.3 VIE (`vie/`)
- Provider-agnostic HTTP gateway on port 8100
- 6 providers wired, env-gated, failover-capable
- Task-based routing (`research`, `generation`, `validation`, `explanation`, `fast`, `default`)
- Live probe endpoint (`POST /probe`) for connectivity/latency diagnostics
- **Reusable by any VQB service on `vqb-network`** — just `POST http://factory-vie:8100/generate`. No SDK. No coupling.

### 2.4 Monitoring
- Container labels (`prometheus.scrape=true`, `logging=promtail`, `loki_service=…`) hook into the existing shared Prometheus/Grafana/Loki stack.
- Zero code changes on the shared monitoring side to onboard a new product — just apply the same label set.
- Health/readiness endpoints follow a standard shape (`{status, checks, version}`) so a single Grafana dashboard can chart all VQB products.

### 2.5 Logging
- All services log JSON-ish lines to stdout at INFO level (`%(asctime)s %(levelname)s %(name)s: %(message)s`).
- Promtail's docker_sd config picks up any container carrying the `logging=promtail` label.
- Loki queries by `container=…` label — no product-specific setup required.

### 2.6 Configuration
- **Fail-fast env-driven config** (`app/core/config.py`) — required vars missing → clean startup error, never a silent fallback.
- Naming convention: `PRODUCT_<VAR>` for product-scoped, `SHARED_<VAR>` for platform-wide (e.g. `SHARED_MONGO_URL`, `SHARED_REDIS_URL`).
- **Reusable pattern** — copy the `Settings` class shape into a new product with product-specific env vars.

### 2.7 Docker infrastructure
- All product containers join **external network** `vqb-network`. Adding a new product = adding a service definition to a new compose file that also declares `networks: vqb-network: external: true`.
- Traefik routing labels are copy-pasteable — swap `factory-*` names for the new product's naming.
- Multi-stage Dockerfiles (Python slim + Node alpine + nginx alpine) are re-usable templates.

### 2.8 Shared services
- **MongoDB** (`SHARED_MONGO_URL`) — one instance, one DB per product. Users are per-product today (Strategy Factory has its own `users` collection); a cross-product user directory is a future roadmap item and is a pure additive change (`users_global` collection + a shim in `auth/deps.py`).
- **Redis** (`SHARED_REDIS_URL`) — wired but unused today. Reserved for cross-product caches, rate-limiting, or pub/sub.
- **Backup pipeline** (`infra/scripts/{backup,restore}.sh`) — runs against `SHARED_MONGO_URL`; supports N products on the same instance without modification.

---

## 3. ArbiCore X — future connection contract

**Scope for this engagement:** ArbiCore X is deliberately **not** integrated or merged into this repository. Strategy Factory is the only application being completed.

**How ArbiCore X will later connect (no changes to this repository required):**

```
       ┌────────────────────────────────────────────────────────┐
       │                     Traefik (edge)                     │
       └───────────────┬──────────────────────────┬─────────────┘
              factory.example.com          arbicore.example.com
                       │                          │
             ┌─────────▼──────────┐    ┌──────────▼──────────┐
             │  Strategy Factory  │    │      ArbiCore X     │
             │   (this repo)      │    │  (separate repo)    │
             └─────────┬──────────┘    └──────────┬──────────┘
                       │                          │
                       └──────────────┬───────────┘
                                      │ (all join vqb-network)
       ┌──────────────────────────────▼──────────────────────────────┐
       │                     SHARED PLATFORM                          │
       │  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────────┐   │
       │  │ factory │  │ MongoDB │  │  Redis   │  │  Traefik +   │   │
       │  │  -vie   │  │(shared) │  │ (shared) │  │  monitoring  │   │
       │  └─────────┘  └─────────┘  └──────────┘  └──────────────┘   │
       └──────────────────────────────────────────────────────────────┘
```

**ArbiCore X will:**
- Live in a **separate repository** and be deployed as its own Docker Compose stack.
- **Share the VIE container** (`factory-vie` — despite the name, it is the platform's LLM gateway, not Strategy-Factory-owned). Its endpoint is `http://factory-vie:8100`.
- **Share the auth module** by depending on `strategy-factory` as a Git submodule OR by re-implementing the exact same JWT structure with a shared `JWT_SECRET`. Cross-product SSO is a Stage 3 roadmap item; until then each product mounts its own `/api/auth/*` behind the same domain conventions.
- **Share monitoring + logging** by carrying the same container labels.
- **Share Docker infrastructure** (`vqb-network`, Traefik, Mongo, Redis) — no infrastructure changes required to add it.
- **NOT share business logic** — the `strategies`, `research_queries`, `users` collections stay Strategy-Factory-scoped. ArbiCore X uses its own DB or namespaced collections.

**What we will need to do when ArbiCore X starts** (all additive, no changes here):
1. Create the ArbiCore X repo with its own `app/main.py`, `app/api/*`, `app/db/mongo.py` (or use a package import from the shared platform).
2. Copy the auth module structure (or vendor it) — same 5 roles, same JWT format.
3. Point at `factory-vie:8100` for all LLM calls.
4. Deploy on the same VPS with its own Traefik router.

**Nothing in this repository needs to change** to make that possible. The VIE service name, container labels, network, and env-var conventions have been chosen deliberately with this future in mind.

---

## 4. Canonical baseline declaration

- **This repository is Strategy Factory v1.0 canonical baseline.**
- All Stage 2 development continues here.
- ArbiCore X will be handled as a separate application built on the shared platform substrate exposed by this repository — after Strategy Factory has been successfully deployed and validated.
