# 06 · Migration Plan (Phase 2 candidate — to be approved)

> ⚠️ This plan is part of the **visual approval package only**. Implementation begins only after the sign-off checklist in `07_SIGNOFF_CHECKLIST.md` is fully approved.

---

## 0 · Constraint zero (binding for every phase)

```
git diff --stat /app/backend   →   empty after every phase boundary
git log -- backend/             →   no new commits added
```

If any phase produces non-empty backend diff, **roll back the phase**. The brief is explicit: no functionality removal, no route removal, no engine removal.

---

## 1 · Phase summary table

| Phase | Goal | Risk class | Operator impact | Effort | Reversibility |
|---|---|---|---|---|---|
| **M0** Tokens + theme rebase | Apply Binance/Bybit tokens from §02 design system. **Remove all light-theme code paths.** Excise `ThemeToggle`. No layout changes. | **R0** (cosmetic) | O1 (visual only) | **~0.5 d** | Trivial — flip one CSS file. |
| **M1** Top tab shell swap | Restore the locked 11-CORE + 6-MORE tab roster from §01. Mount in `CommandShell`. LeftRail demoted behind `ui.leftrail` flag. URL redirects preserve deep links. | **R2** (navigation) | O2 (relearn-position) | **~1.5 d** | Instant — flip flag back to LeftRail. |
| **M2** Anchor screens (5) | Compose **S-01 Dashboard · S-02 Execution · S-04 Monitoring · S-06 Trade Runner · S-03 Auto Factory** per wireframes in §03. | **R3** (composition) | O2 | **~3 d** | Per-screen — each is one PR. |
| **M3** Remaining tabs (6) | Compose **S-05 · S-07 · S-08 · S-09 · S-10 · S-11** + More-menu screens S-13…S-17. | **R3** (composition) | O2 | **~2.5 d** | Per-screen. |
| **M4** Global overlays restyle | Restyle Notification Drawer · Copilot · Inspector · Command Palette to match Binance/Bybit tokens. Add 🔔 + 💬 to topbar right cluster. | **R1** (chrome) | O1 | **~1 d** | Pure CSS + 2-icon mount. |
| **M5** Polish + certification | Sticky status rail. Sub-tab transitions. Accessibility re-cert. Light-theme re-cert (resolves RC1-1 / RC1-2). Density-mode regression. Smoke probe across all 17 screens. | **R1** (polish) | O1 | **~1 d** | Per-fix granular. |
|  | **Total** |  |  | **~9.5 d** |  |

**Risk-class legend:** R0 = cosmetic-only. R1 = chrome / layout polish. R2 = navigation paths change. R3 = component composition (no signature changes). **R4 deliberately not used** — would require backend or engine changes, which is forbidden.

**Operator-impact legend:** O1 = visual only (no relearn). O2 = relearn-position (the muscle-memory bargain that restores the OLD workflow). O3 = relearn-workflow (forbidden — every workflow stays ≤ 2 clicks per `RECOVERY_FINAL_CERTIFICATION.md`).

---

## 2 · Detailed phase plan

### M0 · Tokens + theme rebase (~0.5 d) — R0/O1

**Scope:**
- Overwrite `/app/frontend/src/styles/asf-design-tokens.css` `:root` block with the §02 design-system values (Binance gold accent + Binance surfaces + Binance semantic colors + 4-level border + 5-level text hierarchy + elevation tokens).
- **Delete all `[data-theme="light"]` blocks** from `asf-design-tokens.css`, `asf-rc1-light-overrides.css`, and `command/tokens.css`. Light theme is no longer supported.
- **Remove `ThemeToggle.js` from topbar** — control is excised (Excellence-of-focus mandate).
- Update `/app/frontend/src/command/tokens.css` to inherit (no overrides).
- Re-sync `VerdictBadge` / `VerdictChip` palettes to use `--color-success` / `--color-danger` semantic tokens.

**Acceptance:**
- All 15 `/c/*` routes render with the new tokens.
- No `[data-theme]` attribute on `<html>` anywhere (verified by search).
- No JS file changed beyond `ThemeToggle` removal.
- DEV-RC1 blockers RC1-1 + RC1-2 cleared (cannot recur — light theme deleted).

**Rollback:** restore previous CSS files from git.

### M1 · Top tab shell swap (~1.5 d) — R2/O2

**Scope:**
- New component: `command/shell/TopTabBar.jsx` (verbatim port of old `App.js` LL 200–273, lifted into the existing `CommandShell`).
- New component: `command/shell/StatusRail.jsx` (existing rail kept; restyled).
- Re-key `modulesRegistry.js` to the locked 11-CORE + 6-MORE roster (tab IDs from §01).
- URL redirect map: legacy `/c/<old-module>/<old-section>` → new tab path. Implemented in `command/shell/router.js`.
- `LeftRail` mount gated behind `ui.leftrail` flag in `featureFlags` (default OFF). Instant rollback if needed.
- `NavMoreMenu.jsx` ported verbatim from old codebase (it already lives in current code).

**Acceptance:**
- All 11 core tabs render with correct label + active state.
- More ▾ menu opens, supports keyboard nav, escapes overflow container via `position:fixed`.
- All deep links (e.g. bookmarks to `/c/diag/monitoring`) redirect to `/c/monitoring` or open inside `monitoring` with the right sub-tab pre-selected.
- All previous data-testids resolved by the redirect.

**Rollback:** flip `ui.leftrail=true` → old shell restored within seconds.

### M2 · Anchor screens (~3 d) — R3/O2

One screen per commit:

| Day | Screen | Components composed | Source of composition |
|--:|---|---|---|
| Day 1 | **S-01 Dashboard** | GovernanceCard + UniverseGovernance + StrategyIngestion + AutoScheduler + Orchestrator + MultiCycle + AutoMutation + StrategyDashboard + DeploymentReadinessCard + IngestionHealth + ParityCertification + PipelineLogsPanel | Old App.js LL 286–296 + §03 wireframe |
| Day 2 | **S-06 Trade Runner** | TradeRunner (existing component, single mount) | §03 wireframe |
| Day 2 | **S-03 Auto Factory** | AutoFactoryPhase55 + MasterBotCompilePanel (accordion) | §03 wireframe |
| Day 3 | **S-04 Monitoring** | MonitoringSuite + 4 sub-tab composites (Monitoring · SoakDiagnostics · CpuPoolState · ScalingPanel+FactorySupervisorPanel+MasterBotDashboard) | §03 wireframe |
| Day 3 | **S-02 Execution** | ExecutionDashboard (existing — re-mount only) | Old App.js L295 |

**Acceptance per screen:**
- Layout matches wireframe in §03.
- `data-testid` map preserved.
- All backend calls return 200 (probed live).
- Density-mode renders correctly.
- Light-theme renders correctly.

**Rollback per screen:** revert the single commit.

### M3 · Remaining tabs (~2.5 d) — R3/O2

Day 1 — **S-05 Paper Exec** + **S-07 Portfolio (2 sub-tabs)** + **S-10 Auto Select**.
Day 2 — **S-08 Explorer** (with right deep-dive pane) + **S-09 Market Data (3 sub-tabs)** + **S-11 Admin (5 sub-tabs)**.
Day 3 — **S-12 Workspace** + More-menu screens **S-13/S-14/S-15/S-16/S-17**.

**Acceptance:** same as M2 (per screen).

### M4 · Global overlays restyle (~1 d) — R1/O1

**Scope:**
- Apply Binance/Bybit tokens to `NotificationDrawer`, `CopilotPanel`, `InspectorPane`, `CommandPalette`, `ShortcutsOverlay`, `AsfDetailDrawer`.
- Mount 🔔 (unread chip from `/api/monitoring/status`) and 💬 in topbar right cluster between DensityToggle and auth-badge.
- Resolve **RC1-3** (CommandPalette `aria-labelledby`) inline (1-line fix).

**Acceptance:**
- Drawers open under light theme without dark-surface bleed (clears RC1-2).
- Keyboard shortcuts work: ⌘K · ⌘J · ⌘⌥N · ⌘. · `?`.
- `:focus-visible` ring renders on all overlay elements.

### M5 · Polish + certification (~1 d) — R1/O1

**Scope:**
- Sub-tab transition animations (180ms ease, transform-only).
- Sticky `StatusRail.jsx` confirmed at bottom on all 17 screens.
- Accessibility re-cert via existing `axe-core` harness (resolves **RC1-4**).
- Smoke probe (Playwright) walks all 17 screens, asserts:
  - Topbar 11 CORE tabs rendered.
  - More ▾ 6 items rendered + Admin appended for admin role.
  - Each screen mounts its top-level testid (`data-testid="screen-{id}"`).
  - Density toggle swaps `[data-density="compact"]` on `<html>`.
  - No `[data-theme]` attribute set anywhere (single-theme contract).
- Update `RC1_RELEASE_NOTES.md` to draft sign-off (resolves **RC1-5**).
- **cTrader-readiness rendering check:** every `.future-slot` and `.broker-chip.future` element passes a11y + renders correctly (placeholders only — no connection logic).

**Smoke probe sweep size:** 17 × 2 (comfortable + compact density) = **34 screen-states asserted** (was 68 in dual-theme world).

**Outcome at end of M5:**
- Workstation restored to old workflow.
- Every new capability re-housed and reachable.
- Binance/Bybit/TradingView/Quantower/cTrader dark institutional aesthetic locked in.
- **DEV-RC1 cuttable at the same HEAD** — all 5 PRE_RC1 blockers resolved as a side-effect (RC1-1/RC1-2 by deletion, RC1-3/RC1-4 by M4/M5 work, RC1-5 by release notes).
- cTrader-readiness slots reserved in Trade Runner / Monitoring / Portfolio / Master Bot — ready for post-RC1 broker-integration workstream without re-flow.

---

## 3 · Sequencing options

### Option A — single-engineer linear (~9.5 d) — recommended default

```
Day 0     operator signs §07 checklist
Day 0.5   M0 lands  (tokens)        → RC1-1 + RC1-2 cleared
Day 2     M1 lands  (shell swap)    → tab roster restored
Day 5     M2 lands  (5 anchor screens)
Day 7.5   M3 lands  (remaining 6+5 screens)
Day 8.5   M4 lands  (overlay restyle) → RC1-3 cleared
Day 9.5   M5 lands  (polish + RC1-4 axe + RC1-5 release notes) → DEV-RC1 cut
```

### Option B — two-engineer parallel (~6 d wall-clock)

```
Engineer 1: M0 → M1 → M4 → M5
Engineer 2: M2 anchors (parallel after M1) → M3 (parallel after M2)
```

### Option C — single-engineer w/ BI5 R1 in parallel (~12 d)

A second engineer starts BI5 Recovery Phase R1 on Day 0 (B-1 + B-2 + B-9 from `BI5_RECOVERY_AUDIT.md`). Since R1 is backend + small UI-form-field change only, it doesn't conflict with M0–M5. By Day 12 you have the restored workstation **AND** BI5 data plane live.

Operator picks the option in the §07 sign-off form.

---

## 4 · Per-phase rollback ladder

| If this breaks… | …roll back to |
|---|---|
| Theme regression on M0 | Revert single CSS file. Zero downtime. |
| Tab roster breaks deep links on M1 | Flip `ui.leftrail=true` flag. Instant. |
| One anchor screen on M2 misrenders | Revert the single screen commit. Other 16 screens unaffected. |
| Overlay restyle breaks keyboard nav on M4 | Revert the overlay's commit. Other overlays unaffected. |
| Smoke probe finds a regression on M5 | Stay on previous-day HEAD. RC1 cut postponed by 0.5 d. |

---

## 5 · Smoke probe definition (Playwright — to be written in M5)

```
For each of 17 screens (S-01 … S-17):
  Click the tab in the top bar
  Assert URL matches the locked tab ID
  Assert <main> has data-testid="screen-<id>"
  Assert no console.error
  Capture screenshot
  Assert any API calls returned 200 (or 4xx-by-design)

Repeat the full sweep for:
  - [data-theme="dark"]   (default)
  - [data-theme="light"]
  - [data-density="comfortable"]
  - [data-density="compact"]

= 17 × 4 = 68 screen-states asserted.
```

— End of MIGRATION PLAN —
