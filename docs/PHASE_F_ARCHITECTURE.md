# Phase F · Workforce Explorer — Architecture

_Prototype-polished workforce surface at `/c/workforce/explorer`, running
alongside legacy `/c/workforce` (roster) and `/c/masterbot` (orchestrator
identity). Zero new backend endpoints._

## 1. Component graph

```
                              ┌─────────────────────────────┐
                              │       AppRouter.jsx         │
                              │   /c/workforce/explorer     │
                              └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │   surfaces/                 │
                              │   WorkforceExplorer.jsx     │◀── data-testid="workforce-explorer"
                              └───┬─────────┬───────────────┘
                                  │         │
                 ┌────────────────┘         └──────────────────────┐
                 │                                                 │
                 ▼                                                 ▼
     ┌──────────────────────────┐                    ┌──────────────────────────┐
     │  adapters/                │                    │  workspace-state/         │
     │   • factoryAdapter        │                    │   • navigationStore       │
     │       fetchWorkers()      │                    │       saveSurface/read    │
     │       (WORKERS_FIXTURE    │                    │       ({ view })          │
     │        fallback)          │                    │   • useWorkspaceStore     │
     │   • masterBotAdapter      │                    │       killPostureArmed    │
     │       aggregateMasterBot()│                    │                          │
     │       → identity+plan     │                    │                          │
     └────────────┬─────────────┘                    └────────────┬─────────────┘
                  │                                               │
                  ▼                                               ▼
       ┌────────────────────────┐                    ┌──────────────────────────┐
       │  primitives/           │                    │  Icon inference           │
       │   • SurfaceHeader      │                    │   ingestion → Cpu         │
       │   • SignatureFrame     │                    │   signal    → Sparkles    │
       │   • DivisionCaption    │                    │   feature   → Sparkles    │
       │   • WorkerCard         │                    │   gov       → Landmark    │
       │   • Chip               │                    │   candle    → Cpu         │
       │   • StateTemplate      │                    │   master-bot→ Bot         │
       └────────────────────────┘                    └──────────────────────────┘
```

## 2. Route contract

| Route                    | Component            | Status              |
|--------------------------|----------------------|---------------------|
| `/c/workforce`           | `Workforce`          | Legacy — unchanged  |
| `/c/masterbot`           | `MasterBot`          | Legacy — unchanged  |
| `/c/workforce/explorer`  | `WorkforceExplorer`  | **NEW** — additive  |

Discovery links added on BOTH legacy surfaces:
- `data-testid="workforce-try-explorer"` on `Workforce.jsx`
- `data-testid="masterbot-try-workforce-explorer"` on `MasterBot.jsx`

## 3. Three-view toggle

| Key       | Testid                              | Layout                                    | Purpose |
|-----------|-------------------------------------|-------------------------------------------|---------|
| `org`     | `workforce-explorer-view-org`       | `WorkerCard` grid (`auto-fit, minmax(280,1fr)`) | Default — identity-first. |
| `purpose` | `workforce-explorer-view-purpose`   | Purpose-sorted list (`workforce-explorer-purpose-{id}`) | Foregrounds intent; state muted to a Chip. |
| `status`  | `workforce-explorer-view-status`    | State-sorted table (`workforce-explorer-status-{id}`) | Foregrounds attention; error/blocked first. |

State ordering in the status table: `error → blocked → active → idle → dormant`
(matches Bible §7.6 "surface attention that needs operator action first").

Choice persists in `navigationStore.memory['/c/workforce/explorer'] = { view }`.
Restored on mount so the operator returns to the same view they left in.

## 4. Prototype affordances landed

| Prototype pattern                           | Production wiring                       |
|---------------------------------------------|-----------------------------------------|
| SurfaceHeader anatomy                       | `primitives/SurfaceHeader`              |
| SignatureFrame · gold · Master Bot identity | `primitives/SignatureFrame` (`tone='gold'`) |
| Kill-posture SignatureFrame · crit          | Reads `useWorkspaceStore.killPostureArmed` |
| Three-view toggle (org / purpose / status)  | Same three modes; identical testids     |
| View memory via saveSurface / readSurface   | `navigationStore.saveSurface(pathname, {view})` |
| Per-state count chips                       | Reduced from `workers[].state`          |
| Purpose-first sorted list                   | `sort((a,b) => a.purpose.localeCompare(b.purpose))` |
| Status-first sorted table                   | `sort(STATE_ORDER)` — error/blocked first |

## 5. Backend Feature Freeze compliance

- No new API endpoints.
- No new adapters. Reuses `factoryAdapter.fetchWorkers` and
  `masterBotAdapter.aggregateMasterBot` — both existing production
  adapters, both emit `unavailableBreadcrumb` and fall back to fixtures
  under v1.1.0-stage4.
- Zero net-new network calls compared to legacy Workforce + MasterBot.

Sanity grep:

```
$ rg -n "fetch|axios" frontend/src/os/surfaces/WorkforceExplorer.jsx
32  import { fetchWorkers } from '../adapters/factoryAdapter';
33  import { aggregateMasterBot } from '../adapters/masterBotAdapter';
```

Only two adapter imports — both are pre-existing production adapters.

## 6. Rollback

Single commit. `git revert <sha>` removes:

- `frontend/src/os/surfaces/WorkforceExplorer.jsx`
- `frontend/src/os/surfaces/WorkforceExplorer.stories.jsx`
- `frontend/tests/e2e/workforce-explorer.spec.cjs`
- The `/c/workforce/explorer` route declaration in `AppRouter.jsx`
- The `workforce-try-explorer` link on `Workforce.jsx`
- The `masterbot-try-workforce-explorer` link on `MasterBot.jsx`
- This doc + tracker entry

No other surfaces touched.
