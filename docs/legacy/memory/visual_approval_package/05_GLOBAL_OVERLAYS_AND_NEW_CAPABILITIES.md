# 05 · Global Overlays & New Capability Re-housing

> The new capabilities that are NOT inline tab content live as **global overlays** — keyboard-driven, mounted at shell level, available from any screen. This file is the contract for where each one lives and which backend it reads from.

---

## 1 · Global overlays (mounted in App shell, available everywhere)

| Overlay | Trigger | Position | Mount file | Backend |
|---|---|---|---|---|
| **Command Palette** | `⌘K` / `Ctrl+K` | Centered modal | `command/shell/CommandPalette.jsx` | local (palette commands invoke React Router + theme/density store) |
| **Notification Drawer** | `⌘⌥N` / `⌘⇧N` · bell icon in topbar right cluster | Right slide-out (440 px) | `command/shell/NotificationDrawer.jsx` + `ui-asf/AsfNotificationDrawer.jsx` | `/api/monitoring/status` · `/api/admin/widening-proposals` |
| **Copilot Panel** | `⌘J` | Right slide-out (520 px) | `command/shell/CopilotPanel.jsx` | `/api/orchestrator/heartbeat` · `/api/llm/call-log/recent` (read-only advisory) |
| **Inspector Pane** | `⌘.` | Right slide-out (380 px) | `command/shell/inspector/InspectorPane.jsx` + `InspectorProvider.jsx` + `views.jsx` | per-context |
| **Detail Drawer** | per-context (e.g. "View details" in Explorer) | Right slide-out (520 px) | `ui-asf/AsfDetailDrawer.jsx` | per-panel APIs |
| **Shortcuts overlay** | `?` | Centered modal | `command/shell/ShortcutsOverlay.jsx` | local |
| **Emergency Banner** | (auto · ≤480 px viewport) | Sticky top under topbar | `command/shell/EmergencyBanner.jsx` | local |

All overlays:
- Respect `:focus-visible` outline, focus trap, `role="dialog" + aria-modal + aria-labelledby`.
- Restyled in the new design system to match Binance/Bybit (no purple, no glow; gold for active, soft slate for chrome).
- Survive across tab changes.

---

## 2 · Bell + topbar right-cluster (new addition to old topbar)

The old 1-vCPU topbar right cluster carries: `[Clear (N)] · TraderModeButton · ThemeToggle · DensityToggle · auth-badge · Sign-out · Online dot`.

Restored topbar **adds** between `DensityToggle` and `auth-badge`:

```
… │ DensityToggle │ 🔔(N) │ 💬 Copilot │ auth-badge │ Sign-out │ ● Online
```

- 🔔 bell icon → opens Notification Drawer; carries unread count chip.
- 💬 Copilot icon → opens Copilot Panel.

Both icons sit between density + auth so muscle memory for the rightmost controls (auth/online) is preserved.

---

## 3 · New capabilities — final placement

### 3.1 Master Bot (NEW capability)

| Surface | Lives at |
|---|---|
| Master Bot **administration** (fleet, runners, deployments, token rotation) | **Monitoring → Cluster sub-tab** (S-04). `MasterBotDashboard.jsx` mounted at the top of the Cluster sub-tab, FactorySupervisorPanel + ScalingPanel below. |
| Master Bot **compile** (one-shot artefact build from a saved strategy) | **Auto Factory → bottom accordion** (S-03). `MasterBotCompilePanel.jsx` (or `MutateMasterBotCompile.jsx`) collapsed below the AutoFactoryPhase55 cohort table. |
| Master Bot **runner registry** (Windows VPS agents) | **Monitoring → Cluster sub-tab** (S-04). Below MasterBotDashboard. |
| Master Bot **export pack** (`.cbotpack` builder + download) | **Auto Factory → bottom accordion** (S-03). Inline inside MasterBotCompilePanel. |

Backend endpoints unchanged: `/api/master-bot/*` + `/api/runner/*`.

### 3.2 Factory Supervisor (NEW capability)

| Surface | Lives at |
|---|---|
| Leader lease + heartbeat | **Monitoring → Cluster sub-tab** (S-04). |
| Fleet registry (workers in/out) | **Monitoring → Cluster sub-tab** (S-04). |
| Submission dispatcher + defer queue | **Monitoring → Cluster sub-tab** (S-04). |
| Supervisor events log | **Monitoring → Runtime sub-tab** alert stream (S-04). |
| Architect advisor (recommendations) | **Copilot Panel** (advisory cards). |

Backend endpoints unchanged: `/api/factory-supervisor/*` + `/api/orchestrator/*`.

### 3.3 Auto Learning (NEW capability — dormant)

| Surface | Lives at |
|---|---|
| Auto-learning status + outcomes | **Monitoring → Runtime sub-tab** alert stream (S-04). |
| Auto-learning configuration | **Admin → Tuning sub-tab** (S-11). |
| Auto-learning training data inspector | **Copilot Panel** (read-only advisory cards). |

### 3.4 Notification Drawer (NEW chrome)

* Global overlay (`⌘⌥N` or bell).
* Source: `/api/monitoring/status` (alerts) + `/api/admin/widening-proposals` (governance items).
* Sections inside the drawer:
  - **🔴 Critical** (alerts / errors)
  - **🟡 Pending** (widening proposals to approve)
  - **🔵 Info** (recent factory events)
* Footer: `[Mark all read]  [Open Monitoring]`

### 3.5 Copilot Panel (NEW chrome)

* Global overlay (`⌘J` or 💬 icon).
* Source: `/api/orchestrator/heartbeat` + `/api/llm/call-log/recent`.
* Layout: 3 stacked accordion sections:
  - **System advisory** (live recommendations from architect_advisor)
  - **Recent LLM calls** (read-only audit trail)
  - **Operator playbook hints** (context-aware tips per active tab)
* Read-only in this restoration; interactive chat input remains deferred per `PRE_RC1_BLOCKERS.md` RC1-5.

### 3.6 Governance (mature)

| Surface | Lives at |
|---|---|
| Universe governance | **Dashboard** top bar (S-01) — `UniverseGovernancePanel.jsx`. |
| Universe audit (history) | **Admin → Rules sub-tab** (S-11) — collapsible section. |
| Flag governance | **Admin → Flags sub-tab** (S-11). |
| Widening proposals | **Notification Drawer → Pending section**. |
| Rule sets (PropFirm + system) | **Admin → Rules sub-tab** (S-11). |

### 3.7 Scaling (NEW capability)

| Surface | Lives at |
|---|---|
| Scaling controls + worker count | **Monitoring → Cluster sub-tab** (S-04). |
| Scaling events log | **Monitoring → Runtime sub-tab** alert stream (S-04). |
| Compute probe / host capability | **Monitoring → Compute sub-tab** (S-04). |

### 3.8 Diagnostics (deep)

| Surface | Lives at |
|---|---|
| Deployment readiness | **Dashboard → right-rail card** (S-01) — collapsible. |
| Parity certification (HTF / Trade) | **Dashboard → right-rail card** (S-01). |
| Ingestion health | **Dashboard → right-rail card** (S-01). |
| Pipeline logs (full feed) | **Dashboard → bottom log-tail strip** (S-01) (4-row preview) + Command Palette deep-link `> Open: Pipeline logs (full)` opens an Inspector Pane. |
| Soak diagnostics | **Monitoring → Soak sub-tab** (S-04). |
| CPU pool state | **Monitoring → Compute sub-tab** (S-04). |

### 3.9 Challenge Matching (NEW capability)

| Surface | Lives at |
|---|---|
| Challenge sim against a firm's rules | **Prop Firms → Challenge sub-tab** (S-14). `ChallengeMatchingPanel`. |
| Challenge portfolio builder | **Prop Firms → Challenge sub-tab** (S-14). `ChallengePortfolioPanel` inline. |
| Match input validator | (used internally by FirmMatchPanel; not its own panel.) |

### 3.10 Readiness (NEW capability)

| Surface | Lives at |
|---|---|
| Readiness top-line ("Backend ● healthy …") | **Admin → Users sub-tab top strip** (S-11). |
| Per-engine readiness drill-down | **Dashboard → right-rail card** (S-01). |

### 3.11 AUTH + accessibility + theme + density (preserved)

| Surface | Lives at |
|---|---|
| `installAuthFetchInterceptor()` | `src/index.js` boot (preserved). |
| `AuthGate.js` | Wraps `<CommandShell />` in `App.js`. |
| ThemeToggle | Topbar right cluster (preserved). |
| DensityToggle | Topbar right cluster (preserved). |
| TraderModeButton | Topbar right cluster (preserved, but **deprecated** — cleanup post-RC1). |
| Focus trap utilities | `command/shell/*` overlays (preserved). |
| Reduced-motion + coarse-pointer rules | `styles/asf-u4-a11y.css` (preserved). |
| Responsive postures (handheld / tablet / workstation) | `command/shell/usePosture.js` (preserved). |

---

## 4 · Backend route preservation table

This is the contract proving zero backend changes. Every route listed in the OPERATOR brief is preserved by being consumed at the surfaces listed above.

| Brief item | Route(s) consumed | Restored surface |
|---|---|---|
| Master Bot | `/api/master-bot/*` · `/api/runner/*` | S-03, S-04 (Cluster) |
| Factory Supervisor | `/api/factory-supervisor/*` · `/api/orchestrator/*` | S-04 (Cluster) · Copilot |
| Auto Learning | (dormant — `engines/factory_supervisor/auto_learning.py`) | S-04, S-11 (Tuning), Copilot |
| Notification Drawer | `/api/monitoring/status` · `/api/admin/widening-proposals` | Global overlay |
| Copilot | `/api/orchestrator/heartbeat` · `/api/llm/call-log/recent` | Global overlay |
| Governance | `/api/governance/*` · `/api/admin/widening-proposals` | S-01 + S-11 + Notification |
| Scaling | `/api/scaling/*` · `/api/cpu-pool/state` | S-04 (Cluster + Compute) |
| Diagnostics | `/api/monitoring/*` · `/api/auto-maintenance/status` · `/api/latent/parity-certification/*` · `/api/latent/deployment-readiness/*` | S-01 cards + S-04 |
| Challenge Matching | `/api/phase4/*` · `/api/challenge/*` · `/api/challenge-matching/*` | S-14 (Challenge sub-tab) |
| Readiness | `/api/readiness` · `/api/latent/deployment-readiness/*` | S-01 card + S-11 strip |
| Auth fixes | `/api/auth/*` (no changes; interceptor in frontend) | preserved |

— End of OVERLAYS & NEW CAP RE-HOUSING —
