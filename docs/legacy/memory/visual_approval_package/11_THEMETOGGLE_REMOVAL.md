# 11 · ThemeToggle Removal — Final Confirmation

> Operator-confirmed 2026-06-11. Filed before M0 begins.

## Decision

**ThemeToggle will be FULLY REMOVED from the workstation. ASF becomes DARK-ONLY going forward.**

## What this means

| Item | Disposition |
|---|---|
| `src/components/ThemeToggle.js` | **DELETED** in M0. |
| `src/components/ThemeToggle.tsx` (if exists) | **DELETED**. |
| `src/hooks/useTheme.js` | **DELETED**. |
| `src/stores/themeStore.js` | **DELETED**. |
| `bootstrapThemeStore()` call in `src/index.js` | **REMOVED**. |
| `[data-theme]` attribute set on `<html>` | **REMOVED** (any code that toggles it deleted). |
| `[data-theme="light"]` CSS blocks across `styles/*.css` | **DELETED**. |
| `asf-rc1-light-overrides.css` | **DELETED**. |
| Topbar `<ThemeToggle/>` mount | **REMOVED** from topbar component. |
| `data-testid="theme-toggle"` | **GONE** — no longer testable, no longer expected. |

## What the operator sees

- The 🔆/☾ icon button currently between Density and Notifications **disappears**.
- The right-side topbar control cluster after M0 reads, left to right:
  `[Trader] [Density] [🔔 Notifications] [💬 Copilot] [admin@…] [⎋ Sign out] [● Online]`
- No setting · no toggle · no flicker · no "wrong-theme" possibility ever again.
- All design / a11y / motion / depth effort consolidates on a single canvas: institutional dark.

## What rule changes downstream

- **DEV-RC1 blockers RC1-1 + RC1-2** (light-theme contrast cluster + overlay light-mode bleed) are **structurally extinct** — they presume a light theme that no longer exists.
- The M5 smoke probe **must assert** there is no `[data-theme]` attribute on `<html>` anywhere in the routed pages.
- The M5 smoke probe **must assert** there is no element matching `[data-testid="theme-toggle"]`.
- The M5 smoke probe runs at **17 screens × 1 theme × 2 densities = 34 screen-states** (was 68 in the dual-theme world).

## Reversibility

This change is fully reversible at git level (single revert) but the operator brief is explicit: this is the directional decision. Re-introducing light is treated as a **new** product decision, not a regression to be guarded against.

## Authorization

```
ThemeToggle removal approved:

Approved by:    ________________________

Date:           ________________________
```

— End of THEMETOGGLE REMOVAL LOCK —
