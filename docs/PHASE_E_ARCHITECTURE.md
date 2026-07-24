# Phase E · Timeline Explorer — Architecture

_Prototype-polished chronological activity feed at `/c/timeline/explorer`,
running alongside the legacy `/c/timeline` surface. Zero new backend endpoints._

## 1. Component graph

```
                              ┌─────────────────────────────┐
                              │       AppRouter.jsx         │
                              │   /c/timeline/explorer      │
                              └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │   surfaces/                 │
                              │   TimelineExplorer.jsx      │◀── data-testid="timeline-explorer"
                              └───┬─────────┬───────────────┘
                                  │         │
                 ┌────────────────┘         └──────────────────────┐
                 │                                                 │
                 ▼                                                 ▼
     ┌──────────────────────────┐                    ┌──────────────────────────┐
     │  adapters/               │                    │  workspace-state/         │
     │   • timelineAdapter       │                    │   • navigationStore       │
     │       fetchTimeline({actor,window})            │       facets.actor        │
     │   • streamAdapter (useStream)                  │       saveSurface/read    │
     │                          │                    │       setCrumb            │
     │                          │                    │   • useWorkspaceStore     │
     │                          │                    │       timeWindow          │
     │                          │                    │       selectStrategy      │
     └────────────┬─────────────┘                    └────────────┬─────────────┘
                  │                                               │
                  ▼                                               ▼
       ┌────────────────────────┐                    ┌──────────────────────────┐
       │  primitives/           │                    │  features/                │
       │   • SurfaceHeader      │                    │   • FacetBar (actor axis) │
       │   • SignatureFrame     │                    │   • TimeWindowChip        │
       │   • ActivityRow        │                    │   • StreamPostmark        │
       │   • EvidenceDrawer     │                    │   • useStream             │
       │   • Chip · StateTemplate│                   └──────────────────────────┘
       └────────────────────────┘
```

## 2. Route contract

| Route                    | Component          | Status              |
|--------------------------|--------------------|---------------------|
| `/c/timeline`            | `Timeline`         | Legacy — unchanged  |
| `/c/timeline/explorer`   | `TimelineExplorer` | **NEW** — additive  |

Discovery link `timeline-try-explorer` added to the legacy Timeline
controls row (matches Phase B/C pattern).

## 3. Data model

`TimelineExplorer` performs a single client-side `fetch` per `(actor, timeWindow)`
combination through the shared adapter:

```
fetchTimeline({ actor, window }) → TimelineEvent[]

TimelineEvent = {
  id: string,            // "e-01"
  timestamp: string,     // "12:34:02"
  actorKind: string,     // "governance" | "master-bot" | ...
  actorName: string,
  verb: string,          // "held"
  subject: string,       // "strat-014-schema-v3" ← strategy id extracted
  outcome?: { tone: ChipTone, label: string },
  trailer?: string,
  provenance?: { source, transform, attested },
  lineage?: { self, ancestors, descendants },
}
```

Row memory is persisted in `navigationStore.memory[loc.pathname]`
(sessionStorage) as `{ selectedId }`. Restored on mount so a return
from the passport re-opens the same drawer.

## 4. Prototype affordances landed

| Prototype pattern                       | Production wiring |
|-----------------------------------------|-------------------|
| SurfaceHeader anatomy                   | `primitives/SurfaceHeader` (same as Phase A/B/C/D) |
| SignatureFrame around list              | `primitives/SignatureFrame` |
| Row memory via saveSurface/readSurface  | `navigationStore.saveSurface(pathname, {selectedId})` |
| Return-crumb on cross-nav               | `navigationStore.setCrumb({path, label:'back to timeline', origin:'timeline-explorer', originId})` |
| Decision Identity on row activation     | `useWorkspaceStore.selectStrategy(id)` |
| Evidence drawer + open-passport shortcut| `primitives/EvidenceDrawer` `footerAction` prop already supported |

## 5. Backend Feature Freeze compliance

- No new API endpoints.
- No new adapters. Reuses `timelineAdapter.fetchTimeline` and `useStream`.
- Zero net-new network calls compared to legacy Timeline.

Sanity grep:

```
$ rg -n "fetch|axios" frontend/src/os/surfaces/TimelineExplorer.jsx
40  import { fetchTimeline } from '../adapters/timelineAdapter';
```

Only one adapter import — matches legacy Timeline.

## 6. Rollback

Single commit. `git revert <sha>` removes:

- `frontend/src/os/surfaces/TimelineExplorer.jsx`
- `frontend/src/os/surfaces/TimelineExplorer.stories.jsx`
- `frontend/tests/e2e/timeline-explorer.spec.cjs`
- The `/c/timeline/explorer` route declaration in `AppRouter.jsx`
- The `timeline-try-explorer` link on `Timeline.jsx`
- This doc + tracker entry

No other surfaces touched.
