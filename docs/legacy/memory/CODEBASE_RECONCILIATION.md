# CODEBASE_RECONCILIATION.md

**Audit type:** Phase 0 — Codebase Reconciliation
**Date:** 2026-01 (executed against the three operator-supplied artefacts)
**Mode:** Read-only. No code modified. No services restarted.

---

## 1. Inputs reviewed

| Artefact | Size | Notes |
|---|---|---|
| `App.zip` | 138 MB | Newest export. Backend is canonical. Contains `_inventory/` of historical bundles. |
| `App backup.zip` | 126 MB | Older snapshot of the full repo (frontend included). |
| `Frontend.zip` | 840 KB | Newest frontend export — strictly supersedes the frontend snapshot embedded in App.zip. |
| `/app` (live) | — | Effectively empty: a 1-line `server.py`, default `package.json`, only `memory/test_credentials.md`. The Kubernetes pod has **NOT** been hydrated with either zip. |

All zips were extracted to `/tmp/audit/{app_zip,app_backup_zip,frontend_zip}` for comparison. The live `/app` was inspected via `view_bulk`/`ls` and is otherwise untouched.

---

## 2. Layout differences

### 2.1 App.zip (canonical)

```
/App
├── backend/                  ← canonical backend (543 .py files)
│   ├── api/                  (≈60 routers)
│   ├── engines/              (≈170 engines)
│   ├── data_engine/          (BI5 + CSV + Dukascopy + tick adapters)
│   ├── cbot_engine/          (IR + parity + transpiler)
│   ├── config/               (bi5_symbols.py, symbols.py)
│   ├── scripts/              (incl. bi5_one_shot_backfill.py)
│   ├── server.py             (687 LOC, 56 routers wired)
│   ├── factory_runner.py     (sibling scheduler-owning process)
│   ├── startup_validator.py
│   └── tests/                (pytest suite, incl. test_bi5_r1, test_dsr1_schema, test_dsr2_scheduler)
├── memory/
│   ├── PRD.md
│   ├── PROJECT_CONTINUITY_REPORT.md
│   └── visual_approval_package/   (M0..M5 visual + handoff package, screens 01..12)
├── _inventory/
│   ├── frontend_extracted/   ← OLDER frontend snapshot (pre M0..M5 final wiring)
│   ├── app_extracted/        ← whole previous /app (538 .py files)
│   ├── old1vcpu/             ← 1-vCPU deployment frontend (legacy)
│   ├── asf_ui_handoff/       ← ASF_UI_Handoff_2026-06-08 package
│   ├── Frontend.zip          (== the operator-supplied Frontend.zip)
│   ├── old1vcpu_frontend.zip
│   └── old_ui_screenshots.docx
└── data/, test_reports/, tests/
```

**App.zip does NOT carry a top-level `frontend/` directory.** Frontend lives only as snapshots inside `_inventory/`.

### 2.2 Frontend.zip (canonical frontend)

```
/Frontend
├── src/
│   ├── App.js                        (wired to CommandModuleApp + AuthGate)
│   ├── command/
│   │   ├── shell/
│   │   │   ├── CommandShell.jsx      (mounts TopTabBar + LifecycleRail + StatusRail + DangerRibbon)
│   │   │   ├── modulesRegistry.js    (355 LOC — 10 modules, all sections incl. DSR + BI5)
│   │   │   ├── TopTabBar.jsx         (M0)
│   │   │   ├── LifecycleRail.jsx     (M1)
│   │   │   ├── OperatorInboxDrawer.jsx (M4)
│   │   │   ├── DangerRibbon.jsx
│   │   │   ├── inboxEvents.js
│   │   │   └── StatusRail.jsx        (already in older snapshot)
│   │   └── reservations/             (M2/M3 placeholder cards)
│   │       ├── Phase13ReservationsCard.jsx
│   │       ├── Phase14DualScorecardCard.jsx
│   │       ├── Phase15MarketplaceReservation.jsx
│   │       ├── StrategyScoreReservationCard.jsx
│   │       └── ExecutionBrokerChips.jsx
│   ├── components/
│   │   ├── SymbolRegistryPanel.jsx   (DSR-1, NEW vs older snapshot)
│   │   ├── BI5HealthPanel.jsx        (BI5 R1, NEW)
│   │   ├── ArchitectDashboard.jsx
│   │   └── …65 other operator components…
│   ├── stores/   (theme · locale · notifications · eventRing)
│   ├── services/ (api · auth · phase9_api · throttledPost)
│   ├── i18n/     (en-US, de-DE)
│   └── styles/   (asf-design-tokens.css + RC1 overrides)
├── package.json
└── tailwind.config.js
```

### 2.3 App backup.zip

Same shape as App.zip but **older**. Key deltas:
* `backend/api/diag_bi5_health.py` ← **missing** in backup (BI5 R1 endpoint added in App.zip)
* `backend/scripts/bi5_one_shot_backfill.py` ← **missing** in backup (B-9 introduced)
* `backend/tests/test_bi5_r1.py`, `test_dsr1_schema.py`, `test_dsr2_scheduler.py` ← **missing** in backup
* `backend/server.py`, `engines/market_universe.py`, `api/admin_market_universe.py`, `api/latent/market_universe.py`, `data_engine/auto_data_maintainer.py` ← differ (DSR-1 + DSR-2 + BI5 R1 wiring added in App.zip)

---

## 3. Feature delta — App.zip vs App backup.zip vs Frontend.zip

### 3.1 Features present in **all three** (mature core)

* Strategy generation, mutation, validation
* Walk Forward, OOS, Monte Carlo
* Prop Firm catalogue + Firm Match + Challenge Simulator
* Portfolio Builder + Portfolio Intelligence
* Master Bot V1 (compile + deploy + runner)
* Paper Execution + Trade Runner + Live Tracking
* Auto Factory (incl. Phase 55)
* Auto Mutation Runner + Multi-Cycle
* Auto Scheduler + Orchestrator
* Auto Selection
* GEM Factory (dev-console; demoted from primary nav per R4)
* Diagnostics — Readiness · Parity · Ingestion Health · Pipeline Logs · Market Data Workbench · MonitoringSuite (Runtime · Soak · CPU Pool · Scaling)
* Governance — Universe Governance · Rules Review · Env Priority · Readiness · Admin (Users · Flag Gov · Exec Realism · Phase 12 Tuning)
* AI Workforce — LLM Call River · Orchestrator · Auto-Scheduler
* CommandShell, CommandPalette (⌘K), CopilotPanel (⌘J), NotificationDrawer (⌘⌥N), Shortcuts Overlay (?), Inspector pane (⌘.)
* Light/dark theme toggle, locale cycle (en-US ↔ de-DE)
* JWT auth + AuthGate + admin seed
* Phase 4/5 latent capability registry (≈80 feature flags, all dormant by default)

### 3.2 Features present in **App.zip backend + Frontend.zip** but **absent in App backup.zip**

These are the **2026-06 BI5 R1 + DSR-1/2 work** that is genuinely newer:

| Feature | Backend | Frontend |
|---|---|---|
| **BI5 R1 · Per-symbol health endpoint** | `api/diag_bi5_health.py` → `GET /api/diag/bi5/health` | `BI5HealthPanel.jsx` (mounted under `diag/bi5-health`) |
| **BI5 R1 · One-shot historical backfill** | `scripts/bi5_one_shot_backfill.py` | n/a (CLI only) |
| **BI5 R1 · Scheduler dispatches `run_bi5_ingest`** | `data_engine/auto_data_maintainer.py::_update_bi5_symbol` (B-1) | (auto · no UI) |
| **BI5 R1 · UI BI5 source propagation** | n/a | `MarketDataWorkbench.jsx` (already present) routed through `DataUpload`/`DataMaintenance` (B-2) |
| **DSR-1 · Symbol Registry UI** | reuses `admin_market_universe.py` + `latent/market_universe.py` | **`SymbolRegistryPanel.jsx`** + `SymbolRegistryPanel.css` (NEW), mounted at `governance/symbol-registry` |
| **DSR-2 · Scheduler consumes registry** | `data_engine/auto_data_maintainer.py::_ingestion_symbols` reads `market_universe` when flag ON, falls back to legacy `SYMBOL_CONFIG` when OFF | (auto · no UI) |
| **M0–M5 visible chrome** | n/a | `TopTabBar`, `LifecycleRail`, `OperatorInboxDrawer`, `DangerRibbon`, `inboxEvents`, Phase 13/14/15 reservation cards, Strategy Score reservation, Broker chips |

### 3.3 Features present **only in App backup.zip** (potentially regressed)

A directory-level scan reveals **no engines or components removed** between App backup.zip and App.zip — the App.zip is a strict superset.

Two minor exceptions:
* App backup.zip had a top-level `frontend/` and `data_imports/` — these now live under `_inventory/app_extracted/` inside App.zip (intentional restructure, not a loss).
* `runners/`, `_backups/`, `_hydration/` directories from backup are visible inside `_inventory/app_extracted/` (preserved, not removed).

**Conclusion: nothing has been lost.**

### 3.4 Features present **only in Frontend.zip**

(See §3.2 — all DSR-1, BI5 R1, M0–M5 UI work)
Additional small deltas:
* `frontend.env` differs from older `frontend_extracted/.env` (likely REACT_APP_BACKEND_URL pointing to the new pod URL — preserve current `/app/frontend/.env` on hydration).
* `src/styles/asf-design-tokens.css` has been updated; older `asf-rc1-light-overrides.css` removed.
* `useTheme.js` hook + `ThemeToggle.js` component **removed** in Frontend.zip — theme toggle is now driven by `themeStore` + Command Palette only (`cmd:theme-toggle`). This is intentional per `_inventory/asf_ui_handoff/.../11_THEMETOGGLE_REMOVAL.md`.

### 3.5 Features partially migrated

| Item | State |
|---|---|
| **`auto_scheduler.py`** | Generic mutation/discovery scheduler. Does **not** itself dispatch BI5; BI5 dispatch lives in `auto_data_maintainer._update_bi5_symbol`. Two scheduler tracks coexist and the operator's audit-doc reference to "Scheduler still partially hardcoded" remains TRUE for the auto_scheduler path. DSR-2 wiring is only complete on the auto_data_maintainer path. |
| **`config/symbols.py` & `config/bi5_symbols.py`** | Still present and still consulted as legacy fallback. The runtime path resolves to registry rows only when `ENABLE_DYNAMIC_MARKET_UNIVERSE=true` (flag default OFF). |
| **`factory_runner.py`** | Sibling process that owns schedulers when `FACTORY_RUNNER_OWNS_SCHEDULERS=true`. Code is present; activation is operator-elective. |
| **Factory Supervisor (FS-P1.0..1.4)** | Full backend scaffolding present, every flag default OFF. UI surface limited to `ArchitectDashboard.jsx`, `OperatorParityPanels.jsx::FactorySupervisorPanel`. Reachable only via Command Palette (⌘K → Power User) — demoted from primary nav per R4. |
| **Marketplace / Dossier / Valuation** | UI = reservation cards only (Phase 13/14/15 placeholders). Backend = no engines yet. Strictly a reservation. |

---

## 4. Recommended canonical codebase

| Slice | Source of truth | Action when hydrating `/app` |
|---|---|---|
| `/app/backend/` | **App.zip / backend/** | Copy as-is. |
| `/app/frontend/` | **Frontend.zip /** (the operator-supplied one) — **NOT** `App.zip/_inventory/frontend_extracted/` | Copy as-is. |
| `/app/memory/` | **App.zip / memory/** (PRD.md, PROJECT_CONTINUITY_REPORT.md, visual_approval_package) | Merge with current `/app/memory/` (which only has `test_credentials.md`). |
| `/app/data/`, `/app/tests/`, `/app/test_reports/`, `/app/_inventory/` | App.zip | Preserve. `_inventory/` is reference-only — do not run code from there. |
| `.env` files | Live `/app/frontend/.env` + `/app/backend/.env` | **Keep what's already in the pod** (preview URL + DB connection) — do **not** overwrite. The zips contain stale env values. |

### 4.1 Hierarchical rule (locked)

```
Backend  : App.zip  >  App backup.zip  >  (legacy, ignore)
Frontend : Frontend.zip  >  App.zip/_inventory/frontend_extracted  >  App.zip/_inventory/old1vcpu  >  (legacy, ignore)
Memory   : App.zip/memory  (only source)
```

If a future zip arrives, use the same priority order.

---

## 5. Observed but not investigated (read-only audit limit)

* Whether the **factory_runner.py** sibling process is currently invoked by supervisor in the live pod (live pod is empty — not applicable today).
* Whether the **scheduler-owned APScheduler** instances are actually firing (no live data — backend not booted).
* Whether the **MongoDB `market_universe_symbols` collection** has been seeded in the live environment (live pod has no DB connection wired — `/app/backend/.env` not present from these zips).

These are runtime concerns to verify **after** hydration. They do not change the static feature-exposure map.

---

## 6. Conclusion

**App.zip is correctly the canonical roadmap baseline for the BACKEND.**
**Frontend.zip is canonical for the FRONTEND** (newer than App.zip's frontend snapshot — adds DSR-1 Symbol Registry UI, BI5 R1 BI5HealthPanel, and the full M0–M5 chrome).
**App backup.zip contributes nothing missing.** It is purely a historical reference.

No features were lost across the chain. Every backup-only artefact survives inside App.zip's `_inventory/`.

The current `/app` directory has **not yet been hydrated** with any of these zips — it is essentially empty. Hydration is the next operator decision (out of scope for this audit; covered by the still-pending `MIGRATION_EXPORT_PLAN.md` and `MIGRATION_PRIORITY.md`).
