# Adding a New Module to Strategy Factory v1.1

**Audience:** integrator adding ArbiCore X, GemHunter, Research Intelligence, or any new intelligence module.

**Golden rule:** the v01 Strategy Factory core (`backend/legacy/`, `backend/app/`, `frontend/src/` except `frontend/src/modules/`) is **frozen** and must not be modified. Every new module lives entirely inside `/app/modules/<slug>/`.

---

## 1 · Create the module skeleton

```bash
SLUG=arbicorex   # or gemhunter, research_intel, ...

mkdir -p /app/modules/$SLUG/backend/{api,engines,models}
mkdir -p /app/modules/$SLUG/frontend
mkdir -p /app/modules/$SLUG/docs
touch    /app/modules/$SLUG/backend/__init__.py
touch    /app/modules/$SLUG/backend/api/__init__.py
touch    /app/modules/$SLUG/backend/engines/__init__.py
touch    /app/modules/$SLUG/__init__.py
```

## 2 · Write the manifest

`/app/modules/<slug>/manifest.yml`:

```yaml
name: ArbiCore X
slug: arbicorex
version: 0.1.0
description: Cross-exchange crypto arbitrage & inventory engine.
owners: [ ops@example.com ]
roles: [ admin, developer, operator ]
mongo_prefix: arbicorex_
requires_vie: true
```

## 3 · Backend router (auto-mounted)

`/app/modules/<slug>/backend/api/routes.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/arbicorex", tags=["arbicorex"])

@router.get("/status")
async def status():
    return {"ok": True, "module": "arbicorex"}
```

That's it — restart the backend and `GET /api/arbicorex/status` is live. The
loader (`backend/app/main.py::_mount_future_modules`) discovers every
`APIRouter` export under `/app/modules/*/backend/api/*.py` and mounts it with
the same JWT dependency as the core routers.

## 4 · Frontend surface

`/app/frontend/src/modules/<slug>/index.jsx`:

```jsx
import React from "react";

function ArbiCoreXHome() {
  return <div className="p-8 text-zinc-100">ArbiCore X — coming soon.</div>;
}

export default {
  id: "arbicorex",
  label: "ArbiCore X",
  sections: [
    { id: "home", title: "ArbiCore X · Home", Component: ArbiCoreXHome },
  ],
};
```

Then, in the v1.1-owned barrel `frontend/src/modules/index.js`, add:

```js
export { default as arbicorex } from "./arbicorex/index.jsx";
```

The Command OS registry (`command/shell/modulesRegistry.js`) does not need to
be edited — a companion loader (added under `src/modules/loader.js` at
integration time, not in v01) reads the barrel and appends module entries
to the registry after v01 modules are registered.

## 5 · Database

- All collections **must** be prefixed with the module slug: `arbicorex_*`.
- Access frozen core collections **read-only**. Never write to `market_data`,
  `strategy_library`, `mutation_events`, etc.

## 6 · VIE usage

Use the shared VIE service — never talk to LLM providers directly.

```python
import httpx
async def ask_vie(prompt: str):
    async with httpx.AsyncClient(base_url="http://factory-vie:8100") as c:
        r = await c.post("/vie/dispatch", json={"prompt": prompt})
        return r.json()
```

## 7 · Docs

Every module MUST ship:

- `docs/modules/<slug>/README.md`
- `docs/modules/<slug>/ACCEPTANCE.md` — module-level acceptance report
- `docs/modules/<slug>/ARCHITECTURE.md`

## 8 · Verification

```bash
# Backend
curl -fsS "$BASE/api/openapi.json" | jq '.paths | keys | .[] | select(startswith("/api/<slug>"))'
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/<slug>/status"

# Frontend
open "$BASE/c/<slug>"

# Run acceptance workflow to ensure nothing regressed in the core
./scripts/deploy_verify.sh   # must remain 31/31 PASS
```

## What NOT to do

- ❌ Never edit anything under `backend/legacy/`, `backend/app/`, `frontend/src/command/`, `frontend/src/components/`, `frontend/src/services/`, `frontend/src/hooks/`, `frontend/src/stores/`, `frontend/src/styles/`, or `frontend/src/routes/`.
- ❌ Never re-introduce `EMERGENT_LLM_KEY` or vendor-locked LLM clients.
- ❌ Never widen a frozen collection's schema with module-owned fields.
- ❌ Never gate frozen-core behaviour on a module-owned flag.

If a change to the frozen core is genuinely required, cut a new v2.x release
with its own recovery + acceptance pack.
