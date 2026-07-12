# /app/modules — Future modules mount point

**Purpose:** this directory is the **only** place where new intelligence modules
(ArbiCore X, GemHunter, Research Intelligence, and any subsequent AI systems)
may be added. The frozen Strategy Factory core (`/app/backend/legacy/`,
`/app/backend/app/`, `/app/frontend/src/`) **must not be modified** to
integrate a new module.

## Layout convention

Each module lives under its own top-level slug:

```
/app/modules/
├── __init__.py
├── README.md                     (this file)
├── <module_slug>/                e.g. arbicorex, gemhunter, research_intel
│   ├── manifest.yml              module metadata (name, version, roles, DB prefix)
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── api/                  FastAPI routers (mounted under /api/<slug>/*)
│   │   ├── engines/              Python engines / business logic
│   │   └── models/               Pydantic + MongoDB models
│   ├── frontend/                 React components / pages
│   │   ├── index.js              exports the module for the loader
│   │   └── *.jsx
│   ├── infra/                    (optional) module-specific compose overlay
│   └── docs/                     Module recovery + acceptance reports
```

## Backend loader contract

`/app/backend/app/main.py` iterates `/app/modules/*/backend/api/` at boot and
mounts every `router` export under `/api/<module_slug>/*`.

Each module must expose one entry point:

```python
# /app/modules/<slug>/backend/api/__init__.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/<slug>", tags=["<slug>"])
```

## Frontend loader contract

The Command OS `modulesRegistry.js` is frozen v01 code and MUST NOT be
modified in place. To register a new module's UI:

1. Create `/app/frontend/src/modules/<slug>/index.js` exporting the module
   entry (id, label, icon, sections).
2. At integration time, the ArbiCore X (or future) PR adds a single import
   line in the module's own **wrapper** file `/app/frontend/src/modules/index.js`
   (a v1.1-owned barrel, not v01 code), which the frozen registry consumes
   via a `try {}` optional import. See `docs/modules/ADDING_A_MODULE.md`.

This preserves v01 verbatim while giving modules a clean extension point.

## Database convention

Module collections MUST be namespaced with the module slug prefix:

- `arbicorex_signals`, `arbicorex_positions`
- `gemhunter_candidates`, `gemhunter_verdicts`

The frozen core collections (`market_data`, `strategy_library`, etc.) are
**read-only** from module code. Any write should go through a dedicated
module collection.

## Adding a new module — 5 minutes

```bash
mkdir -p /app/modules/<slug>/backend/{api,engines,models} \
         /app/modules/<slug>/frontend \
         /app/modules/<slug>/docs
touch /app/modules/<slug>/{backend,frontend}/__init__.py
# Create manifest.yml, backend/api/routes.py, frontend/index.js
# Restart backend + rebuild frontend — no other changes needed.
```

**Reserved slugs:**
- `arbicorex` — ArbiCore X arbitrage system (planned)
- `gemhunter` — GemHunter opportunity scanner (planned)
- `research_intel` — Research Intelligence module (planned)

## What you MUST NOT do

- ❌ Modify `/app/backend/legacy/**`
- ❌ Modify `/app/backend/app/**` (except adding new routers under the loader pattern)
- ❌ Modify `/app/frontend/src/**` outside `src/modules/`
- ❌ Introduce global feature flags that gate frozen-core behaviour
- ❌ Add new environment variables to `.env.example` that break existing deploys
- ❌ Downgrade or replace VIE

Any change that violates these rules requires cutting a new v2.x release with
its own recovery + acceptance pack.
