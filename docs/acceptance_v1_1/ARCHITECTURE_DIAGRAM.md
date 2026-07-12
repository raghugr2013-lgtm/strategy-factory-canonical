# Strategy Factory v1.1 — Architecture Diagram

```
                                    ╔═══════════════════════════════════════════════╗
                                    ║                    Traefik / SPA               ║
                                    ║   https://${FACTORY_DOMAIN}   → factory-frontend ║
                                    ║                                → /api/*  → factory-backend ║
                                    ╚════════════┬═════════════════════┬═════════════╝
                                                 │                     │
                        ┌────────────────────────▼────┐   ┌────────────▼──────────────────────────┐
                        │   factory-frontend (nginx)  │   │        factory-backend  (uvicorn)      │
                        │  ─────────────────────────  │   │  ─────────────────────────────────    │
                        │  React 19 + CRA5 + shadcn   │   │  FastAPI 0.116                        │
                        │  v01 Command OS:            │   │  ┌─────────────────────────────────┐ │
                        │   • AuthGate                │   │  │ Phase-1 core (auth, users, VIE) │ │
                        │   • CommandModuleApp        │   │  ├─────────────────────────────────┤ │
                        │   • CommandShell            │   │  │ Legacy mount (83 routers)       │ │
                        │     • TopTabBar             │   │  │  • strategies       • lifecycle │ │
                        │     • LeftRail              │   │  │  • auto-factory     • prop firms │ │
                        │     • CommandBar (⌘K)       │   │  │  • gem-factory      • master bot│ │
                        │     • LifecycleRail (10)    │   │  │  • backtest         • execution │ │
                        │     • StatusRail            │   │  │  • validation       • cbot      │ │
                        │     • NotificationDrawer    │   │  │  • optimization     • monitoring│ │
                        │     • OperatorInbox         │   │  │  • portfolio        • orchestr. │ │
                        │  10 modules × N sections:   │   │  │  • data / BI5       • governance│ │
                        │   dashboard, lab, explorer, │   │  │  • latent           • scaling   │ │
                        │   mutate, portfolio,        │   │  │  • llm bridge       • research  │ │
                        │   propfirm, exec, ai, diag, │   │  │  • readiness        • regime    │ │
                        │   governance                │   │  └─────────────────────────────────┘ │
                        │                             │   │  169 engine modules load at import   │
                        │  services/auth.js:          │   │  ENABLE_LEGACY_ROUTERS=true default   │
                        │   • installAuthFetchInterceptor│   │                                       │
                        │     injects Bearer JWT      │   │  Auth: JWT + refresh (bcrypt hash)    │
                        │     on every /api/*         │   │  RBAC: admin/developer/researcher/    │
                        │  Token storage:             │   │        operator/viewer                │
                        │   localStorage.asf_auth_token   │  Login → returns BOTH:                │
                        │   localStorage.asf_auth_user│   │   flat  {access_token,refresh_token}  │
                        └───────────────┬─────────────┘   │   nested{token,user} (v01 alias)      │
                                        │                 │                                       │
                                        │                 │  Delegates AI to VIE via HTTP         │
                                        │                 └──────────────────┬────────────────────┘
                                        │                                    │
                                        ▼                                    ▼
                        ┌──────────────────────────┐        ┌───────────────────────────────────┐
                        │    factory-runner        │        │      factory-vie  (uvicorn)         │
                        │  (heartbeat + schedulers)│        │  ───────────────────────────────  │
                        │   • orchestrator tick    │        │  Vendor Independent Engine         │
                        │   • BI5 cert sweep       │        │  Providers (auto-detected via env) │
                        │   • mutation cadence     │        │   • openai         • deepseek     │
                        │   • soak stability       │        │   • anthropic      • groq         │
                        │   • lifecycle decay      │        │   • gemini         • kimi         │
                        │   • paper alert bridge   │        │  Routes: /vie/dispatch, /providers │
                        └───────────────┬──────────┘        └──────────────┬────────────────────┘
                                        │                                  │
                                        └───────────────┬──────────────────┘
                                                        │
                                                        ▼
                                    ┌───────────────────────────────────────┐
                                    │              MongoDB                   │
                                    │  strategy_factory_v1 (57 collections)  │
                                    │  ────────────────────────────────────  │
                                    │  users, refresh_tokens                 │
                                    │  market_data (313,777)                 │
                                    │  market_spread (309,950)               │
                                    │  strategy_library (14)                 │
                                    │  strategy_library_archive (126)        │
                                    │  strategy_lifecycle_history (892)      │
                                    │  strategy_performance_history (1,047)  │
                                    │  mutation_events (10,430)              │
                                    │  asf_import_actions (27,100)           │
                                    │  bi5_ingestions / bi5_certifications   │
                                    │  portfolios / portfolio_builder_runs   │
                                    │  prop_firms / prop_firm_rules          │
                                    │  paper_execution_runs / _trades        │
                                    │  live_positions / runners              │
                                    │  master_bots / master_bot_history      │
                                    │  monitoring_events / soak_windows      │
                                    │  orchestrator_state / scheduler_events │
                                    │  governance_universe / promotions      │
                                    │  scaling_nodes / cpu_pool_history      │
                                    │  regime_state / research_runs …        │
                                    └───────────────────────────────────────┘
```

## Request lifecycle (operator → backend → VIE)

```
Operator (browser)
   │  Sign in via AuthGate → POST /api/auth/login
   │  ↳ receives {access_token, token, user}; stores asf_auth_token
   │
   ▼
Command Module App (React)
   │  services/auth.js installAuthFetchInterceptor()
   │  wraps window.fetch; adds "Authorization: Bearer <asf_auth_token>"
   │
   ▼  every /api/* call
FastAPI backend (factory-backend)
   │  Verifies JWT via /app/backend/app/auth/*
   │  Routes /api/auth/*         → Phase-1
   │        /api/vie/* /llm/*    → VIE bridge
   │        /api/<all others>    → legacy routers (83)
   │
   ├──► Mongo (data, state, telemetry)
   │
   └──► factory-vie (HTTP)
           │  /vie/dispatch
           │  picks provider from env-detected registry
           ▼
        OpenAI / Anthropic / Gemini / DeepSeek / Groq / Kimi
```

## Container topology

- `factory-mongo` — MongoDB 6, persistent volume `mongo-data`.
- `factory-vie` — VIE HTTP service on `:8100` (health `/health`).
- `factory-backend` — FastAPI on `:8001` (health `/api/health`), depends on `factory-mongo`, `factory-vie`.
- `factory-frontend` — nginx serving CRA build on `:80` (health `/healthz`).
- `factory-runner` — background scheduler sibling; shares the backend image, invokes the same engine modules under a different entrypoint.
