# Sprint 2 · Production Candidate Report

> **Prepared:** 2026-07-21
> **Candidate tag:** `v1.3.0-sprint2-complete`
> **Verdict:** ✅ **CANDIDATE APPROVED for VPS deployment.**
> **Freeze status at candidate cut:** Backend Feature Freeze v1.1.0-stage4 · Design Freeze v1.0 · both preserved end-to-end.

---

## 1. Executive verdict

Sprint 2 is a **safe, incremental, frontend-only** release. Every acceptance criterion from `SPRINT_2_PLANNING.md` §2 has been met. Every user-facing surface has been walked (Mission Control, Master Bot, Timeline, Approvals, Strategies Explorer, Strategy Passport, Command Palette). The QA infrastructure (Storybook · axe-core · Playwright · CI) is now permanent and shipping with the build.

Recommendation: **cut `v1.3.0-sprint2-complete`, deploy per the Deployment Package, run the 9-item smoke checklist, and produce the sign-off addendum.** No Sprint 3 work should begin until the VPS runs this build cleanly.

## 2. Candidate scope

| Layer | Contents | Risk to production |
|---|---|:-:|
| Frontend | 2 new surfaces · 1 new adapter · streaming affordances · QA infra · legacy v01 purged | LOW · additive · isolated behind adapter layer |
| Backend | **No changes** — v1.1.0-stage4 stays authoritative | ZERO |
| Storybook (optional) | 69 stories, static output | ZERO — informational only |
| CI (GitHub Actions) | 4-job workflow: pr-title · testids · storybook-a11y · playwright-e2e | LOW — dev-only signal |

## 3. Verification evidence

### 3.1 Automated

| Suite | Command | Result |
|---|---|:-:|
| Playwright E2E · full Sprint 2 regression | `yarn test:e2e` | ✅ **12 / 12 passed** |
| axe-core within Playwright | included in above | ✅ **0 unwaived** on 3 surfaces |
| Storybook build | `yarn build-storybook` | ✅ **69 stories · 0 errors · 22.8 s** |
| CRA production build | `CI=false yarn build` | ✅ compiles clean · 10 s · 166.5 kB main.js gzip |
| `data-testid` coverage lint | `node scripts/check-testids.js` | ✅ OK |
| PR-title convention lint | `node scripts/check-pr-title.js` | ✅ accepts N1..N5 / chore / docs / fix / test / feat / refactor |

### 3.2 Human walk-through

- Full 11-screenshot preview walk-through completed against the preview URL, covering all seven surfaces + palette + streaming postmark + passport sub-sections.
- Testing-agent iterations `iteration_1.json` (11/12 pass), `iteration_2.json` (regression caught immediately), `iteration_3.json` (7/7 after absolute-path fix). All present in `/app/test_reports/`.

## 4. Post-deployment smoke checklist (VPS)

Run each of the following on the deployed VPS URL. Every checkbox must be verified before signing the Sprint 2 addendum.

- [ ] `GET /` returns 200
- [ ] LoginScreen renders and shows a `data-testid="status-rail-stream-postmark"` in the pre-auth footer
- [ ] Sign in with fixture creds (`operator@coinnike.com` / `prototype123`) reaches Mission Control (`data-testid="mission-control"`)
- [ ] Left rail shows MASTER BOT entry
- [ ] `/c/masterbot` renders identity strip (4 metric blocks), gold plan card, 5-row decisions log
- [ ] `⌘K` (or `Ctrl+K`) opens palette with `GO TO MASTER BOT` entry; Tab-cycles stay inside palette
- [ ] `/c/timeline` shows `data-testid="timeline-stream-postmark"` and its `data-stream-tick-count` increments after 20 s
- [ ] `/c/approvals` shows `data-testid="approvals-stream-postmark"`; Approve/Defer/Block buttons remain clickable (optimistic UI)
- [ ] `/c/strategies` table row click navigates to `/c/strategies/<id>` and the passport surface renders all seven sections (signature · metrics · provenance · lineage · guardrails · equity curve · backtest · approvals)
- [ ] `/c/strategies/nonexistent-id` renders the fallback shell with `data-testid="passport-fallback-notice"`
- [ ] `/c/legacy` (or any unknown `/c/*` path) redirects to `/c/mission`
- [ ] Console shows only expected `[adapter] … unavailable under Backend Feature Freeze` breadcrumbs; **no uncaught errors, no `Maximum update depth exceeded`**

## 5. Deferred items (Sprint 3 candidates)

Copied from Completion Report §7 for traceability:

| # | Item | Reason for deferral |
|---|---|---|
| DEF-1 | 60-frame visual regression matrix (currently 3 route baselines) | Grows in lockstep with new surfaces; would produce noise if pre-populated |
| DEF-2 | `color-contrast` axe waiver at token layer | Owned by Design Freeze §1.5 — Sprint 3 Design Token Review candidate |
| DEF-3 | `@emotion/is-prop-valid` framer-motion module-not-found WARN | Cosmetic build warning only |
| DEF-4 | `check-testids.js` regex → `@babel/parser` upgrade | Current heuristic passes; upgrade is quality-of-life |
| DEF-5 | Storybook bundle size warning (CRA5 default posture) | Possible Vite migration in Sprint 3 |
| DEF-6 | Backend routers for streaming, master-bot, timeline, approvals, factory, workforce | Backend Feature Freeze — awaits Backend Activation Roadmap |

## 6. Sign-off plan

1. **Cut tag** `v1.3.0-sprint2-complete` on the canonical branch.
2. **Follow the Deployment Package** (`memory/SPRINT_2_VPS_DEPLOYMENT_PACKAGE.md`) verbatim.
3. **Execute the 12-item smoke checklist** in §4 above on the VPS URL.
4. **Sign** the Sprint 2 addendum (or reply "signed" here). Only then do we open Sprint 3.

## 7. Freeze commitments carried into Sprint 3

- Backend Feature Freeze v1.1.0-stage4 remains ACTIVE until an explicit Backend Activation Roadmap replaces it. No feature flags will be flipped in Sprint 3 without operator instruction.
- Design Freeze v1.0 remains ACTIVE. Sprint 3 Design Token Review (if authorised) will produce a Design Freeze v1.1 spec before any token change.
- The adapter layer under `/app/frontend/src/os/adapters/` remains the compatibility boundary. Every new endpoint must go through it.

---

*End of Sprint 2 Production Candidate Report.*
