# Sprint 2 · Mid-Sprint Visual Review Package

> **Prepared:** 2026-07-21
> **Scope:** N1 → N4 complete · N5 pending your visual review
> **Preview URL:** https://stall-debug.preview.emergentagent.com/
> **Fixture credentials:** `operator@coinnike.com` / `prototype123`
> **Freeze status:** Backend Feature Freeze v1.1.0-stage4 · Design Freeze v1.0 · both preserved

---

## Walkthrough by surface

### 1 · Login (pre-auth)
- Same LoginScreen as Sprint 1 M5.
- The **status rail at the bottom now shows a `STREAM · POLL FALLBACK · <time>` postmark** — this is a new N3 affordance.
- Fixture credentials are printed on the card. Type them in, hit **SIGN IN**.

### 2 · Mission Control (`/c/mission`)
- Same 6-question anatomy as Sprint 1 M4.
- **New in Sprint 2:** N4 partial-failure boundary — if any of the four aggregator slots (timeline / approvals / workers / pipeline) fails, a `data-testid="mc-partial-notice"` orange strip appears above the attention block instead of the whole surface erroring.
- Left rail now has a new second entry **`MASTER BOT`** between MISSION and TIMELINE.

### 3 · Master Bot Dashboard (`/c/masterbot`) — **NEW · Sprint 2 N2**
- **§1 Identity strip · 4 metric blocks:** STANCE (OBSERVE · mb@v4.2.0) · TRUST BUDGET (34 / 120 kOps · 28% spent) · UPTIME (5d 14h 22m) · CURRENT PLAN (12 strategies · epoch 4/6).
- **§2 Current plan card · gold SignatureFrame:** ambition-first purpose line + 4 guardrails (max drawdown, concentration, liquidity floor, regime fit) each with pass/note chips + started-at postmark.
- **§3 Last decisions log:** 5 most-recent decisions from the Master Bot with time · verb · subject · outcome chip (SHIPPED / DEFERRED / BLOCKED / NOTED). Enable Advanced Lens (Cmd+K → "Advanced lens") to see rationale.
- **Reachable via:** left rail `MASTER BOT`, Cmd+K → "go to master bot", direct URL `/c/masterbot`.
- **Adapter mode:** fixture-only until backend exposes `/api/master-bot/*` (still under freeze).

### 4 · Timeline (`/c/timeline`)
- Same layout as Sprint 1.
- **New in Sprint 2 N3:** a `STREAM · POLL FALLBACK · <time>` postmark next to the time-window chip. Every 15 seconds the postmark ticks and the timeline silently refetches. When a WSS URL is configured (post-freeze) the postmark will flip to `STREAM · WSS · <time>`.

### 5 · Approvals (`/c/approvals`)
- Same 3 approval cards with optimistic Approve/Defer/Block controls.
- **New in Sprint 2 N3:** same streaming postmark, same silent refetch cadence.

### 6 · Workforce & Strategies (unchanged in Sprint 2)
- Both surfaces render exactly as in Sprint 1 M4/M5. STRATEGIES will be extended by N5 with a Strategy Passport.

### 7 · Command Palette (`⌘K`)
- **New N2 entry:** GO TO MASTER BOT · `/c/masterbot`.
- **New N4 behaviour:** focus is now trapped inside the palette (Tab/Shift+Tab cycles within the palette, Esc returns focus to the trigger). Fixes WCAG 2.1 §2.4.3 focus-return.

### 8 · Status Rail (global footer)
- **New N3 postmark:** the streaming pulse indicator appears on the right.
- **New N4 semantic wrap:** rail now sits inside a `<footer role="contentinfo">` landmark so axe-core reports zero region violations.

## Sprint 2 feature ledger (through N4)

| # | Delta | Milestone | Live in preview? |
|---|---|---|:-:|
| 1 | Storybook 8.6 baseline · 66 stories | N1 | Runs locally (yarn storybook / build-storybook); not deployed with preview |
| 2 | axe-core + `.axerc.json` waiver ledger | N1 | Runs in CI + Playwright |
| 3 | Playwright morning-routine + a11y suite | N1 | Runs in CI |
| 4 | Visual regression baseline (1 → 2 → 3 frames) | N1 → N2 → N3 | Runs in CI |
| 5 | CI: PR-title + data-testid lints + Storybook a11y + Playwright | N1 | `.github/workflows/frontend-qa.yml` |
| 6 | Master Bot dashboard `/c/masterbot` + adapter | **N2** | ✅ Visible |
| 7 | Left-rail + ⌘K palette pick up masterbot route | N2 | ✅ Visible |
| 8 | Streaming adapter · WSS + polling fallback | N3 | ✅ Visible (poll mode under freeze) |
| 9 | Timeline · Approvals · StatusRail stream postmarks | N3 | ✅ Visible |
| 10 | `useFocusTrap` on Cmd+K palette | N4 | ✅ Active |
| 11 | Centralised 401 interceptor + `sf-auth-unauthorized` event | N4 | Not exercised (auth backend live) |
| 12 | `REACT_APP_STRICT_LIVE=1` diagnostic flag | N4 | Available (opt-in via env) |
| 13 | `Promise.allSettled` + `partial` breadcrumb on Mission Control | N4 | ✅ Active |
| 14 | Legacy v01 CommandShell purge → `/app/frontend/.archive/v01/` | N4 | ✅ Bundle shrinks accordingly |

## What's still pending

| # | Item | Milestone | Blocked by |
|---|---|---|---|
| A | Strategy Passport surface `/c/strategies/:id` (D5) | **N5** | Your visual approval of N1-N4 |
| B | VPS deployment of the coherent Sprint 2 build | Post-N5 | N5 completion |
| C | Production Candidate Report | Post-VPS | VPS smoke tests |
| D | Backend routers `/api/master-bot/*`, `/api/stream/*`, etc. | Deferred | Backend Feature Freeze lift |

## Freeze verification for this review

- **Backend edits:** 0. `git status backend/` shows no changes since v1.1.0-stage4.
- **Token edits:** 0. `src/os/tokens.css` untouched — every visual change is composition of existing tokens.
- **Behavioural regressions detected:** 0 (Playwright · morning-routine + master-bot + streaming suites all pass on the yarn-build output).

## Screenshots captured (this review)

| # | Surface | Screenshot |
|---|---|---|
| 01 | Login (with stream postmark in status rail) | `/tmp/sf-01-login.png` |
| 02 | Mission Control | `/tmp/sf-02-mission-control.png` |
| 03 | Master Bot Dashboard | `/tmp/sf-03-masterbot.png` |
| 04 | Timeline (with stream postmark) | `/tmp/sf-04-timeline.png` |
| 05 | Approvals (with stream postmark) | `/tmp/sf-05-approvals.png` |
| 06 | Strategies (unchanged — Sprint 1 surface) | `/tmp/sf-06-strategies.png` |
| 07 | Command Palette (with Master Bot entry) | `/tmp/sf-07-cmdk.png` |

## Recommendation

**Approve N1-N4 and authorize N5 kickoff.** All N1-N4 exit gates are green; no design-freeze or backend-freeze breach detected; the surfaces landed in this sprint composite cleanly with Sprint 1 architecture. N5 (Strategy Passport) will complete Sprint 2 and unlock the coherent VPS deployment + Production Candidate Report the operator has scheduled.

*If any of the screenshots reveals a visual regression, please annotate the surface + region and I will diagnose against Design Freeze v1.0 before N5 kickoff.*
