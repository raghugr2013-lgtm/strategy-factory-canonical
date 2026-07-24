# Prototype → Production Migration Tracker

_Single source of truth for the Vite/React prototype → production frontend
migration. Updated at the end of every phase._

_Backend Feature Freeze: **PRESERVED**. No new API endpoints have been
introduced in any migration phase. Every surface reuses existing adapters._

---

## 1. Completed migration phases

| Phase | Surface / scope | Route(s) | Rollback commit tag | Status |
|-------|------------------|----------|---------------------|--------|
| A | UserMenu + SurfaceHeader (primitives) | shell-mounted | Phase A | ✅ Merged |
| B | ApprovalCenter | `/c/approvals/center` (alongside `/c/approvals`) | Phase B | ✅ Merged |
| C | StrategyExplorer | `/c/strategies/explorer` (alongside `/c/strategies`) | Phase C | ✅ Merged |
| D1 | EvaluationHarness (read-only) | `/c/evaluation` (net-new) | Phase D1 | ✅ Merged |
| D2 | EvaluationHarness (interactions unlocked) | `/c/evaluation` (same route) | Phase D2 | ✅ Merged |
| E | TimelineExplorer | `/c/timeline/explorer` (alongside `/c/timeline`) | Phase E | ✅ Merged |

Every phase is a single, self-contained, rollback-safe commit. Reverting any
single phase leaves earlier phases functional.

## 2. Remaining prototype surfaces

| Surface | Status | Planned action |
|---------|--------|----------------|
| Master Bot / Workforce | 🟡 Pending | **Phase F** — new `WorkforceExplorer` at `/c/workforce/explorer` alongside `/c/workforce` and `/c/masterbot`. Reuses `masterBotAdapter`. |
| Mission Control | 🟢 Optional | **Phase G (optional)** — in-place polish only. Skip if operator considers current MC acceptable. |

## 3. Decisions on skipped migrations

| Surface | Decision | Rationale |
|---------|----------|-----------|
| `StrategyPassport.tsx` | **Do not migrate** | Production `StrategyPassport.jsx` (827 lines · 4 tabs · POST /api/knowledge/nearest · promote CTA · Lineage from timelineShim) is materially richer than the 222-line prototype fixture. |
| `ScenarioBanner.tsx` | **Do not migrate** | Prototype-only demo affordance. Header comment states _"PROTOTYPE ONLY. Removed at Design Freeze."_ |
| `SettingsStub.tsx` | **Do not migrate** | Production `Settings.jsx` already exists as a `SurfaceStub` with an equivalent message. |
| `SurfaceHeader.tsx` | **Already ported (Phase A)** | Now `primitives/SurfaceHeader.jsx`. |
| Shell (`AppShell`/`LeftRail`/`InspectorSheet`) | **Do not migrate** | Production shell (`AppShell.jsx`, `LeftRail.jsx`, `Header.jsx`, `StatusRail.jsx`, `WorkspaceContextChip.jsx`, `ApprovalsModal.jsx`, `DangerRibbon.jsx`) is richer than the prototype's 3-file shell. |

## 4. Rollback points

Every phase is anchored on a single commit and produces its own architecture
doc. To roll back:

| Phase | To restore state prior to this phase | Also revert (dependents) |
|-------|--------------------------------------|--------------------------|
| A     | Revert Phase-A commit                | Phases B, C, D1, D2, E rely on `primitives/SurfaceHeader` — reverting A would break those. Not recommended in isolation. |
| B     | Revert Phase-B commit                | None |
| C     | Revert Phase-C commit                | None |
| D1    | Revert Phase-D1 commit               | Also reverts D2 (D2 diffed on D1) |
| D2    | Revert Phase-D2 commit               | None (returns to D1 read-only state) |
| E     | Revert Phase-E commit                | None |

Each revert removes exactly:

- the new surface JSX file
- the new Storybook story file
- the new Playwright spec
- the route declaration in `AppRouter.jsx`
- the discovery link on the paired legacy surface (if any)
- the phase's architecture doc

No other surfaces are touched by a rollback.

## 5. Bundle-size history

_All measurements from `yarn build` output — main bundle after gzip._

| Baseline / phase           | main.js (gzipped) | Δ vs. Phase D2 baseline |
|----------------------------|-------------------|--------------------------|
| Phase D2 baseline          | 237.18 kB         | 0 kB (reference)        |
| Phase E (TimelineExplorer + StrategyPassport crumb) | **239.30 kB** | **+2.12 kB (+0.89%)** |

Guardrail: keep cumulative main.js growth ≤ ~1% per phase, ≤ ~5% overall.

## 6. Adapters reused (no new endpoints added)

| Phase | Adapters reused | New endpoints |
|-------|-----------------|---------------|
| A     | (none — primitive port) | 0 |
| B     | `approvalsAdapter`, `navigationStore` | 0 |
| C     | `factoryAdapter`, `strategyLabAdapter`, `navigationStore`, `useWorkspaceStore` | 0 |
| D1    | `useEvaluationStore` (client-only, `localStorage['sf.eval.v1']`) | 0 |
| D2    | Same as D1 (mutators pre-declared) | 0 |
| E     | `timelineAdapter`, `streamAdapter (useStream)`, `navigationStore`, `useWorkspaceStore` | 0 |

## 7. Deferred backlog (post-migration)

- **P2** — Deprecate legacy `Approvals.jsx`, `Strategies.jsx`, and optionally
  `Timeline.jsx` / `Workforce.jsx` once operators validate the Explorer
  variants.
- **P2** — Productivity add-ons for the Evaluation Harness (deferred per
  user direction until Phase F completes):
  - Copy readiness summary to clipboard
  - Export report (Markdown / JSON)
  - Share snapshot (URL-encoded state)
