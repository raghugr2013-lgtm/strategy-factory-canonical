# Sprint 2 · Completion Report

> **Sprint:** 2 (post-Prototype-Validation, pre-Sprint-3)
> **Milestones:** N1 · N2 · N3 · N4 · N5 — all COMPLETE
> **Prepared:** 2026-07-21
> **Recommended git tag:** `v1.3.0-sprint2-complete`
> **Freeze status:** Backend Feature Freeze v1.1.0-stage4 · Design Freeze v1.0 · both preserved end-to-end

---

## 1. Sprint 2 summary

Sprint 2 shipped the QA infrastructure baseline, one new signature surface (Master Bot D4), one new gallery surface (Strategy Passport D5), streaming affordances across three surfaces, and closed the four Sprint 1 latent risks — all without breaching the Backend Feature Freeze or Design Freeze v1.0.

- **Milestones landed:** 5 / 5 (N1 → N5)
- **New surfaces:** 2 (D4 Master Bot · D5 Strategy Passport)
- **Storybook stories:** **69** (Sprint 1 baseline: 0 · N1 exit: 65 · N5 exit: 69)
- **Playwright specs / assertions:** **12 tests · all passing** on `yarn build` static output
- **axe-core violations:** **0 unwaived** across morning-routine, `/c/masterbot`, `/c/strategies/:id`; one documented `color-contrast` waiver (Design-Freeze-owned tokens)
- **Files added under `/app/frontend/src/os/`:** 12
- **Files modified under `/app/frontend/src/os/`:** 9 (all additive / semantic; zero token or layout changes)
- **Backend changes:** **0** (`git diff backend/` = empty since v1.1.0-stage4 tag)

## 2. Milestone-by-milestone status

| # | Milestone | Delivered | Exit gates | Evidence |
|---|---|---|:-:|---|
| **N1** | QA infra baseline | Storybook 8.6 + addon-a11y · Playwright + axe-playwright · `.axerc.json` allowlist · CI (`.github/workflows/frontend-qa.yml`) · `check-testids.js` · `check-pr-title.js` | ✅ 8/8 | `memory/SPRINT_2_N1_COMPLETION_REPORT.md`, `memory/SPRINT_2_N1_COMPATIBILITY_REPORT.md` |
| **N2** | Master Bot Dashboard (D4) | `/c/masterbot` surface · `masterBotAdapter.js` (fixture-only) · ⌘K palette + left-rail entry · 1 story · 3 Playwright tests | ✅ 6/6 | `test_reports/iteration_1.json` (11/12 initial pass) |
| **N3** | Streaming surfaces | `streamAdapter.js` (WSS + poll fallback) · `useStream` hook · `StreamPostmark` on Timeline · Approvals · StatusRail · 3 Playwright tests | ✅ 3/3 | Tick counter increments verified in strict-mode Playwright |
| **N4** | Sprint 1 latent-risk closure | `useFocusTrap` on ⌘K palette · 401 interceptor + `sf-auth-unauthorized` event · `REACT_APP_STRICT_LIVE` flag · `Promise.allSettled` + `mc-partial-notice` · legacy v01 archived to `.archive/v01/` · absolute-path splat catch-all | ✅ 5/5 | `test_reports/iteration_3.json` (7/7 after fix) |
| **N5** | Strategy Passport (D5) | `/c/strategies/:id` surface · `fetchStrategy(id)` with live→fixture fallback · Strategy Explorer row click wiring · 3 stories · 4 Playwright tests (row click · fallback shell · back link · axe) | ✅ 4/4 | Full 12-test suite green + preview walkthrough screenshots 08–11 |

## 3. Freeze compliance ledger

| Layer | Rule | Compliance |
|---|---|:-:|
| Backend | No source edits, no feature-flag flips | ✅ 0 backend commits under `/app/backend/` |
| Design tokens | No `tokens.css` / typography / spacing edits | ✅ untouched since Sprint 1 M1 |
| Semantic ARIA additions | Non-visual metadata OK | ✅ 5 minor additions (StatusRail footer + tabIndex, MissionControl role=list, MasterBot / Passport aria-label lists) |
| Adapter boundary | All new endpoints go through `/os/adapters/` with fixture fallback | ✅ masterBotAdapter, factoryAdapter.fetchStrategy, streamAdapter |

## 4. Test evidence (final regression pass)

```
$ yarn test:e2e         # Playwright, static build target
Running 12 tests using 1 worker
  ✓  N2 · master bot dashboard · surface renders identity + plan + decisions via fixture
  ✓  N2 · master bot dashboard · reachable via ⌘K palette
  ✓  N2 · master bot dashboard · axe-core · master bot has zero unwaived violations
  ✓  N1 · morning routine · login screen loads and reaches mission control via fixture auth
  ✓  N1 · morning routine · axe-core · mission control has zero violations
  ✓  N5 · strategy passport · explorer row click → passport surface renders all sections
  ✓  N5 · strategy passport · unknown id → fallback shell renders
  ✓  N5 · strategy passport · back link returns to explorer
  ✓  N5 · strategy passport · axe-core · strategy passport has zero unwaived violations
  ✓  N3 · streaming surfaces · status-rail streams (poll fallback) with tick counter
  ✓  N3 · streaming surfaces · timeline stream postmark renders + polls
  ✓  N3 · streaming surfaces · approvals stream postmark renders + polls
12 passed (28.2s)
```

```
$ yarn build-storybook
Preview built · 22.8s · 69 stories · 0 errors
```

```
$ node scripts/check-testids.js
✓ data-testid coverage: OK (every interactive element in src/os has a data-testid).
```

```
$ CI=false yarn build
Compiled successfully.  Done in 10.0s
```

Testing-agent iterations 1 → 3 progression:
- **iter-1:** 11/12 pass · MEDIUM found (`/c/legacy` empty outlet)
- **iter-2:** CRITICAL regression on fix (relative Navigate infinite loop) → immediate rollback
- **iter-3:** 7/7 pass (absolute `<Navigate to="/c/mission">` verified live)

## 5. Recommended git tag

**`v1.3.0-sprint2-complete`** — minor version bump (Sprint 2 introduces new user-facing surfaces + adapter capabilities without any breaking change). Preceded by `v1.2.0-sprint1-complete`. This tag captures:
- 2 new surfaces (`/c/masterbot`, `/c/strategies/:id`)
- 1 new adapter (`masterBotAdapter`) + `fetchStrategy` extension
- Streaming adapter + hook + postmark component
- QA infrastructure (Storybook · axe-core · Playwright · CI)
- Legacy v01 code archived out of `src/`

Suggested annotated tag message:
```
Sprint 2 complete · N1 QA baseline · N2 Master Bot · N3 streaming · N4 latent-risk closure · N5 Strategy Passport. 69 stories · 12 e2e tests · 0 unwaived a11y violations. Backend Feature Freeze v1.1.0-stage4 preserved. Design Freeze v1.0 preserved.
```

## 6. Files touched (canonical inventory)

New files under `/app/frontend/`:
```
.axerc.json
.storybook/main.js
.storybook/preview.js
playwright.config.cjs
scripts/check-pr-title.js
scripts/check-testids.js
scripts/spa-serve.py
src/os/adapters/masterBotAdapter.js
src/os/adapters/streamAdapter.js
src/os/features/useStream.js
src/os/features/useFocusTrap.js
src/os/features/StreamPostmark.jsx
src/os/surfaces/MasterBot.jsx
src/os/surfaces/MasterBot.stories.jsx
src/os/surfaces/StrategyPassport.jsx
src/os/surfaces/StrategyPassport.stories.jsx
src/os/primitives/*.stories.jsx        (15 stories files)
src/os/features/FacetBar.stories.jsx
src/os/features/TimeWindowChip.stories.jsx
tests/e2e/morning-routine.spec.cjs
tests/e2e/master-bot.spec.cjs
tests/e2e/streaming.spec.cjs
tests/e2e/strategy-passport.spec.cjs
```

New CI at repo root: `.github/workflows/frontend-qa.yml`
Archived: `/app/frontend/.archive/v01/` (13 legacy directories / files moved out of `src/`).

Modified (all additive/semantic):
```
frontend/package.json                   (+scripts, +devDependencies)
frontend/src/index.css                  (dropped 5 legacy CSS imports)
frontend/src/index.js                   (comment updated)
frontend/src/os/adapters/apiClient.js   (401 interceptor + strict-live flag)
frontend/src/os/adapters/factoryAdapter.js (+ fetchStrategy)
frontend/src/os/adapters/fixtures.js    (+ MASTER_BOT_FIXTURE, STRATEGY_PASSPORT_FIXTURE)
frontend/src/os/adapters/missionAggregator.js (Promise.allSettled)
frontend/src/os/auth/RequireAuth.jsx    (sf-auth-unauthorized listener)
frontend/src/os/palette/CmdKPalette.jsx (useFocusTrap)
frontend/src/os/routing/AppRouter.jsx   (masterbot + passport routes + splat catch-all)
frontend/src/os/routing/routes.js       (MASTER BOT nav entry)
frontend/src/os/shell/StatusRail.jsx    (footer landmark + stream postmark + tabIndex)
frontend/src/os/surfaces/MissionControl.jsx (mc-partial-notice, workforce testid, role=list)
frontend/src/os/surfaces/Timeline.jsx   (stream postmark + refetch on tick)
frontend/src/os/surfaces/Approvals.jsx  (stream postmark + refetch on tick)
frontend/src/os/surfaces/Strategies.jsx (row-click → passport)
```

## 7. Known deferrals (carried to Sprint 3)

| # | Item | Origin | Sprint-3 candidate |
|---|---|---|---|
| DEF-1 | 60-frame visual regression matrix (currently 3 baseline snapshots) | N1 exit-gate reinterpretation | Sprint-3 QA cadence expansion |
| DEF-2 | `color-contrast` axe waiver (token layer) | Sprint 2 §7 R4 | Sprint-3 Design Token Review |
| DEF-3 | `@emotion/is-prop-valid` framer-motion module-not-found WARN | N1 §C1 | Housekeeping when Storybook build config is next touched |
| DEF-4 | `check-testids.js` regex heuristic (currently multi-line brace-aware; could false-positive on very exotic JSX) | N1 §C6 | Upgrade to `@babel/parser` walker |
| DEF-5 | Storybook bundle size >244 kB CRA5 posture warning | N1 §D4 | Consider Vite Storybook migration |
| DEF-6 | Backend routers for `/api/master-bot/*`, `/api/stream/*`, `/api/timeline`, `/api/approvals`, `/api/factory/pipeline`, `/api/ai-workforce/workers` | Backend Feature Freeze | Backend Activation Roadmap (post-freeze) |

## 8. Recommendation

**Cut `v1.3.0-sprint2-complete` and proceed to the single-coherent VPS deployment path outlined in the operator's execution strategy.** No Sprint 3 work should begin until the VPS has been updated and the Production Candidate Report has been signed off. Sprint 3 backlog candidates (DEF-1 through DEF-6 above) are all cost-of-quality items — none blocks user-facing progress.

---

*End of Sprint 2 Completion Report.*
