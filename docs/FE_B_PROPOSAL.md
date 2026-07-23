# Sprint FE-B Proposal — Autonomous Factory Dashboards (Extend)

**Status:** proposal · follows the accepted `docs/FRONTEND_EXPOSURE_ROADMAP.md`.
**Prerequisite:** Sprint FE-A complete (see
`docs/PHASE_1_FACTORY_KPI_REPORT.md`-style verification in
`/app/test_reports/iteration_2.json`).
**Guiding order:** Discover → Reuse → Refine → Extend → Build New.
**Scope guardrail:** zero new backend engines, zero new backend endpoints,
zero database schema changes. Frontend-only. Reuse the existing
`AppShell` + `EngineeringSurface` template + adapter pattern +
`LivenessBadge` + design tokens. No duplicate components.

---

## 1 · Sprint objective

Add the single most important missing operator UI: the Autonomous
Factory dashboards. When FE-B ships, the operator can watch the
factory generate strategies, run backtests, refresh market
intelligence, evaluate itself, and propose meta-learning
adjustments — every autonomous stage becomes a click away.

Every surface below is a NEW route that either lives in the existing
`Engineering` group or a NEW `Factory` group between Mission Control
and Engineering.

## 2 · Surfaces to add (7 total, one per orchestrator concern)

Each surface starts as an `EngineeringSurface`-template mount and is
then filled out with a real component driven by a dedicated adapter.

| # | Route | Backing endpoints (already exist under Freeze) | Adapter to add | LOC estimate |
|---|-------|------------------------------------------------|----------------|--------------|
| 1 | `/c/factory/orchestrator` | `GET /api/orchestrator/status`, `GET /api/orchestrator/decisions`, `POST /api/orchestrator/start`, `POST /api/orchestrator/stop`, `POST /api/orchestrator/tasks/{name}/dispatch`, `GET /api/orchestrator/history`, `GET /api/orchestrator/registry` (7) | `orchestratorAdapter.js` | ~350 |
| 2 | `/c/factory/health` (Factory Health / KPI) | `/api/factory-eval/config`, `/kpis`, `/reports`, `/insights`, `/recommendations`, `/pending`, `/providers/leaderboard`, `/strategies/top-contributors` (28) | `factoryEvalAdapter.js` | ~400 |
| 3 | `/c/factory/meta-learning` (OBSERVE-mode inspector) | `/api/meta-learning/config`, `/evaluations`, `/recommendations`, `/pending`, `/applications`, `/overrides`, `/refresh` (15) | `metaLearningAdapter.js` | ~380 |
| 4 | `/c/factory/market-intelligence` | `/api/market-intelligence/state`, `/changes`, `/intelligence`, `/refresh`, `/observers` (10) | `marketIntelligenceAdapter.js` | ~360 |
| 5 | `/c/factory/auto-factory` | `/api/auto/*` (16) + `/api/mutation/*` (10) | `autoFactoryAdapter.js` | ~380 |
| 6 | `/c/factory/research` (Research Center) | `/api/knowledge/nearest`, `/champions`, `/statistics`, `/families/{h}`, `/health`, `/evaluate`, `/similarity` + `/api/research/*` + `/api/research-runs/*` + `/api/research-lineage/*` (40+) | `researchAdapter.js` | ~420 |
| 7 | `/c/factory/brain` (Brain policy inspector) | `/api/brain/*` (6) | `brainAdapter.js` | ~280 |

**Total endpoints unlocked:** ~120 net-new + reinforces the 8
already-bound.

## 3 · UI pattern (single-shape, applied 7 times)

Every dashboard follows the same three-band composition already
proven by Mission Control + Coverage:

```
┌─── EYEBROW + HEADLINE + BRIEFING ────────────────────────────┐
│ e.g. "AUTONOMOUS ORCHESTRATOR · OBSERVE"                      │
│      "17 tasks registered. 4 in flight. Budget 42% burned."   │
├───────────────────────────────────────────────────────────────┤
│ 4-CARD METRIC ROW (MetricBlock)                               │
│  Running · Tick count · Dispatched · Last error               │
├───────────────────────────────────────────────────────────────┤
│ WIDE ROW #1 — the "what is happening now" widget              │
│   Orchestrator: decisions table (last 20 ticks, one per row)  │
│   Factory Health: leaderboard table (providers · strategies)  │
│   Meta-Learning: pending recommendations list                 │
│   Market Intel: observer state grid                           │
│   Auto Factory: mutation queue                                │
│   Research: champions table + families explorer               │
│   Brain: policy state + regime-transition matrix              │
├───────────────────────────────────────────────────────────────┤
│ WIDE ROW #2 — the "context" widget                            │
│   Orchestrator: task registry (17 tasks · runs_ok/fail)       │
│   Factory Health: KPI trend charts                            │
│   Meta-Learning: overrides + applications ledger              │
│   Market Intel: recent changes                                │
│   Auto Factory: recent mutations attempted                    │
│   Research: similarity playground                             │
│   Brain: scorer weight vector                                 │
└───────────────────────────────────────────────────────────────┘
```

Every surface reuses `MetricBlock`, `DivisionCaption`, `TableTile`,
`Chip`, `LivenessBadge`, `StateTemplate` — components that already
back Mission Control. No new primitives needed.

## 4 · Nav model changes (metadata-only)

Add a new NAV_GROUP between `mission-control` and `engineering`:

```js
{
  id: 'factory',
  label: 'Factory',
  testId: 'nav-group-factory',
  items: [
    { path: '/c/factory/orchestrator',        label: 'Orchestrator',        icon: Cpu,     testId: 'nav-orchestrator' },
    { path: '/c/factory/health',              label: 'Health & KPIs',       icon: Activity, testId: 'nav-factory-health' },
    { path: '/c/factory/meta-learning',       label: 'Meta-Learning',       icon: Brain,   testId: 'nav-meta-learning' },
    { path: '/c/factory/market-intelligence', label: 'Market Intelligence', icon: Radar,   testId: 'nav-market-intelligence' },
    { path: '/c/factory/auto-factory',        label: 'Auto-Factory',        icon: Bot,     testId: 'nav-auto-factory' },
    { path: '/c/factory/research',            label: 'Research Center',     icon: Library, testId: 'nav-research' },
    { path: '/c/factory/brain',               label: 'Brain',               icon: Sparkles,testId: 'nav-brain' },
  ],
},
```

## 5 · Delivery slices (each independently mergeable)

The seven surfaces can ship in any order, but the recommended
value-first sequence is:

1. **FE-B.1 · Orchestrator dashboard** (highest ROI; the single most
   important operator surface for a 24×7 factory).
2. **FE-B.2 · Factory Health & KPIs** (OBSERVE-only; operator can
   watch factory self-evaluation without any mutating power).
3. **FE-B.3 · Meta-Learning inspector** (OBSERVE recommendations).
4. **FE-B.4 · Market Intelligence** (change detection + observers).
5. **FE-B.5 · Research Center** (KB champions, families, similarity).
6. **FE-B.6 · Auto-Factory + Mutation cockpit**.
7. **FE-B.7 · Brain policy inspector** (advanced diagnostic).

Each slice is ~1 focused day of frontend work.

## 6 · Non-goals for FE-B

- No new backend engines.
- No new backend endpoints.
- No new database collections or indexes.
- No new design primitives (no new fonts, no new colors, no new
  component library entries).
- No live-execution / trading surface (that stays in FE-C's Deployments).
- No Admin surfaces (they stay in FE-F).
- No mutating flows that bypass `ApprovalsModal.jsx` for HIGH-risk
  operations.

## 7 · Sign-off checklist per slice

- [ ] New route mounted under `AppRouter.jsx` (protected by `RequireAuth`).
- [ ] New rail entry in `navigation.js` `NAV_GROUPS.factory.items`.
- [ ] New adapter under `frontend/src/os/adapters/` using `apiClient`.
- [ ] Surface component renders `EngineeringSurface` template pre-hydration.
- [ ] Live query polls at 15 s cadence + revalidates on focus.
- [ ] Graceful fallback to `StateTemplate` variant='error' on 5xx.
- [ ] All interactive elements have `data-testid` per invariant.
- [ ] `scripts/check-testids.js` passes.
- [ ] `testing_agent_v3` regression clean.
- [ ] Screenshot recorded under `docs/screenshots/fe-b-<slug>.jpeg`.

## 8 · Estimated impact

- **Endpoints newly reached:** ~120 (from 8 → ~128 = a 16× increase).
- **Frontend coverage against 613 backend endpoints:** from ~1.3 %
  today → **~21 % after FE-B**.
- **Effort:** 7 slices × ~1 day each = ~7 focused days (approx. 1.5 weeks calendar with review + testing).
- **Zero backend risk** — every endpoint pre-exists and is production-tested.

## 9 · What comes after FE-B

`docs/FRONTEND_EXPOSURE_ROADMAP.md` sprints FE-C (empty-state-to-live
conversion, ~90 endpoints), FE-D (path-reconciled Engineering
surfaces, ~40 endpoints), FE-E (Strategy Explorer + Portfolio depth,
~40 endpoints), FE-F (Admin + Governance, ~40 endpoints). After all
of them, total operator reach ≈ 400 of 613 endpoints (~65 %) — with
zero new backend engines.

## 10 · Decision requested

Confirm **FE-B.1 (Orchestrator dashboard)** as the first slice, or
name a preferred alternative starting slice from §5.
