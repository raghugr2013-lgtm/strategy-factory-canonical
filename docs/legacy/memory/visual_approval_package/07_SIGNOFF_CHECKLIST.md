# 07 · Operator Sign-off Checklist

> Phase 1 deliverable. Phase 4 (implementation) cannot start until ALL items below are explicitly approved (mark `[x]`) or explicitly waived (mark `[~]` with one-line rationale).

---

## Acceptance items

### A1 — Tab roster

The locked tab roster is exactly:

**CORE (always-visible, left to right):**
```
Dashboard · Execution · Auto Factory · Monitoring · Paper Exec ·
Trade Runner · Portfolio · Explorer · Market Data · Auto Select · Admin
```

**MORE ▾ (overflow popover):**
```
Workspace · Auto Factory (Legacy) · Prop Firms · Live Tracking · Optimization · Library (N)
```

- [ ] **A1 approved.** Exactly these 11 + 6 tabs in exactly this order. No additions, no removals, no role-based hiding (except Admin which is admin-only by design).

### A2 — Visual design system

Binance/Bybit dark trading terminal aesthetic per `02_DESIGN_SYSTEM.md`:

* Surface palette `#0B0E11` / `#1E2329` / `#2B3139` / `#080C11`.
* Accent gold `#F0B90B` for active tabs, primary CTAs, hover wash.
* Semantic green `#0ECB81` / red `#F6465D`.
* Inter for UI, JetBrains Mono for data, Manrope for display.
* Compact-density mode preserved.

- [ ] **A2 approved.**

### A3 — Screen wireframes

The 17 ASCII wireframes in `03_SCREEN_WIREFRAMES.md` match operator expectation for:

- [ ] S-01 Dashboard (with the 3 NEW right-rail cards + bottom log strip)
- [ ] S-02 Execution (3-step strip)
- [ ] S-03 Auto Factory (+ Master Bot Compile accordion)
- [ ] S-04 Monitoring (4 sub-tabs: Runtime · Soak · Compute · Cluster — with Master Bot Dashboard + Factory Supervisor + Scaling in Cluster)
- [ ] S-05 Paper Exec
- [ ] S-06 Trade Runner
- [ ] S-07 Portfolio (2 sub-tabs: Builder · Panel & Intelligence)
- [ ] S-08 Explorer (with right deep-dive pane)
- [ ] S-09 Market Data (3 sub-tabs: Manual · Automated · Archive)
- [ ] S-10 Auto Select
- [ ] S-11 Admin (5 sub-tabs: Users · Flags · Realism · Tuning · Rules)
- [ ] S-12 Workspace (3/9 col)
- [ ] S-13 / S-14 / S-15 / S-16 / S-17 (More ▾ screens)

### A4 — New-capability re-housing

Per `05_GLOBAL_OVERLAYS_AND_NEW_CAPABILITIES.md`:

- [ ] Master Bot administration lives in Monitoring → Cluster sub-tab.
- [ ] Master Bot compile lives in Auto Factory → bottom accordion.
- [ ] Factory Supervisor lives in Monitoring → Cluster sub-tab.
- [ ] Auto Learning surfaces in Monitoring → Runtime stream + Admin → Tuning.
- [ ] Notification Drawer global overlay (`⌘⌥N` + 🔔 in topbar right cluster).
- [ ] Copilot Panel global overlay (`⌘J` + 💬 in topbar right cluster).
- [ ] Governance: Universe top-of-dashboard; widening proposals in Notification Drawer; flag governance in Admin → Flags.
- [ ] Scaling lives in Monitoring → Cluster sub-tab.
- [ ] Diagnostics: 3 right-rail cards on Dashboard (readiness · parity · ingestion); soak/CPU/scaling under Monitoring.
- [ ] Challenge Matching lives in Prop Firms (More ▾) → Challenge sub-tab.
- [ ] Readiness lives in Dashboard right-rail card + Admin → Users top strip.

### A5 — Preservation contract

- [ ] **Zero backend changes.** `git diff --stat /app/backend` must be empty after every phase.
- [ ] **Zero capability removal.** All 41 sections in current `modulesRegistry.js` map to an explicit home per `04_COMPONENT_REHOUSING_MATRIX.md`.
- [ ] **Auth-fix preserved** (`installAuthFetchInterceptor()` at boot).
- [ ] **A11y, theme, density-mode infrastructure preserved.**
- [ ] **No new navigation concepts introduced.**

### A6 — Migration plan

The phased plan in `06_MIGRATION_PLAN.md`:

- [ ] M0 (tokens, 0.5 d) approved
- [ ] M1 (top tab shell swap, 1.5 d) approved
- [ ] M2 (5 anchor screens, 3 d) approved
- [ ] M3 (remaining tabs, 2.5 d) approved
- [ ] M4 (global overlays restyle, 1 d) approved
- [ ] M5 (polish + cert, 1 d) approved

### A7 — Sequencing option

Choose one (mark `[x]`):

- [ ] **Option A** — single-engineer linear, ~9.5 d wall-clock.
- [ ] **Option B** — two-engineer parallel, ~6 d wall-clock.
- [ ] **Option C** — single-engineer UI + parallel BI5 R1, ~12 d wall-clock + BI5 R1 done.

---

## Authorization

```
Approved by:    ________________________

Date:           ________________________

Notes / waivers:
```

---

## On approval

Once this checklist is filed signed, the next action is:

> **Begin M0 (token rebase, 0.5 d) under read/write guardrails.**

`/app/memory/visual_approval_package/` becomes the immutable design contract for the implementation phase.

— End of CHECKLIST —
