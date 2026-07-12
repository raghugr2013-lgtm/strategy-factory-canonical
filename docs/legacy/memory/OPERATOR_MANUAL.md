# OPERATOR_MANUAL.md

**Audit type:** Phase 1 — Operator Manual
**Source:** App.zip (backend) + Frontend.zip (frontend)
**Audience:** The single human operator who runs the AI Strategy Factory.

This manual answers "as the operator, what can I do today, and where do I do it?" It is a navigational and procedural guide, **not** an architecture document.

---

## 1. Where everything lives in the UI

The operator UI is the **CommandShell**. Open it at the pod's preview URL:

```
https://<pod-host>/
```

The shell is gated by AuthGate — log in once and the session persists. All work happens inside one of **10 modules** in the left rail (LeftRail) or via the **Top Tab Bar** above the CommandBar.

```
┌─────────────────────────────────────────────────────────────┐
│ TopTabBar (M0)            ⌘K palette · ⌘. inspector · ⌘J cop│
├──────┬──────────────────────────────────────────────────────┤
│ ◇    │ Module Surface                                       │
│ ▢ L  │ ┌────────────────────────────────────────────────┐   │
│ E    │ │ LifecycleRail (M1) — Generate → … → Deploy     │   │
│ F    │ ├────────────────────────────────────────────────┤   │
│ T    │ │ Active section (e.g. Strategy Panel)           │   │
│ R    │ │                                                │   │
│ A    │ │ …operator surfaces…                            │   │
│ I    │ └────────────────────────────────────────────────┘   │
│ L    │                                                      │
├──────┴──────────────────────────────────────────────────────┤
│ StatusRail (chips: orchestrator · LLM · ingestion · …)      │
└─────────────────────────────────────────────────────────────┘
```

### 1.1 The 10 modules

| Rail | Module | Purpose | URL prefix |
|---|---|---|---|
| 1 | **Dashboard** | **Mission Control (restored 2026-06)** — briefing + the 8-panel operator workbench in one scroll | `/c/dashboard` |
| 2 | **Research Lab** | Generate, analyse, backtest, validate one strategy at a time | `/c/lab` |
| 3 | **Strategy Explorer** | Browse, compare, save survivors. Phase 13/14/15 reservations collapsed in a bottom accordion. | `/c/explorer` |
| 4 | **Mutation Engine** | Auto-mutation runners, multi-cycle, auto-factory, Master Bot | `/c/mutate` |
| 5 | **Portfolio OS** | Portfolio builder + intelligence. Phase 14 reservation collapsed in a bottom accordion. | `/c/portfolio` |
| 6 | **Prop Firm** | Catalogue + Firm Match + **Challenge Matching** (surfaced 2026-06) | `/c/propfirm` |
| 7 | **Execution Center** | **Execution Overview (one-glance KPIs)** · Paper · Trade Runner · Live tracking · Broker chips | `/c/exec` |
| 8 | **AI Workforce** | LLM call river · Orchestrator · Auto-Scheduler | `/c/ai` |
| 9 | **Diagnostics** | Readiness · Parity · Ingestion · Pipeline · Market Data · Monitoring · **BI5 Health** | `/c/diag` |
| 10 | **Governance** | Promotion · Universe · **Symbol Registry (DSR)** · Rules · Env · Readiness · Admin | `/c/governance` |

### 1.2 Three posture modes

The shell adapts to viewport size automatically:
* **Workstation** (>= 1280 px): full UI, every section visible.
* **Tablet** (768–1279 px): subset of sections — many "power user" sections are hidden.
* **Briefing** (mobile / <480 px): read-only with EmergencyBanner.

Operator can override with the Command Palette → `cmd:posture-reset`.

---

## 2. Daily operator workflow

### 2.1 Start the day

1. Open `/c/dashboard/briefing`.
2. Scan the **Mission Briefing** card (operator attention summary).
3. Glance at the **StatusRail** chips at the bottom — they should be all green.
4. Open **Diagnostics → Deployment Readiness** (`/c/diag/readiness`) — confirm overall verdict.
5. Open **Diagnostics → BI5 Health** (`/c/diag/bi5-health`) — verify coverage % is >0 and last sync is recent.
6. Open **Diagnostics → Ingestion Health** — confirm BID + BI5 freshness.

If any of those is red/amber, jump to `/c/diag/pipeline` to inspect the most recent pipeline logs, then `/c/diag/monitoring` for soak/CPU/scaling state.

### 2.2 Run new strategies

Two paths:

**Manual path** (one-off):
1. `/c/lab/panel` → choose pair, timeframe, style → Generate.
2. `/c/lab/analysis` → review metrics.
3. `/c/lab/backtest` → Walk Forward / OOS / Monte Carlo (`/c/lab/validate`).
4. `/c/lab/cbot` → compile.
5. `/c/lab/optim` → optimize if needed.

**Auto path** (factory):
1. `/c/mutate/factory` → start an Auto Factory run.
2. `/c/mutate/factory-55` → use Phase 55 enhanced runner.
3. Monitor in `/c/mutate/cycle` (Multi-Cycle) or `/c/mutate/auto-select`.

### 2.3 Build & deploy portfolio / master bot

1. `/c/explorer/explorer` → pick survivors.
2. `/c/portfolio/builder` → assemble portfolio (Builder).
3. `/c/portfolio/panel` → review.
4. `/c/portfolio/intel` → intelligence overlays.
5. `/c/mutate/master-bot` → review Master Bot Dashboard.
6. `/c/mutate/master-bot-compile` → compile + export.
7. `/c/exec/paper` → run paper execution.
8. `/c/exec/runner` → Trade Runner (deploy & observe).
9. `/c/exec/live` → Live Tracking.

### 2.4 Match to prop firms

1. `/c/propfirm#admin` → confirm firm catalogue.
2. `/c/propfirm#match` → run Firm Match (Phase 4).
3. `/c/propfirm#challenge` → **Challenge Matching** (surfaced 2026-06; also reachable via ⌘K → "Challenge Matching"). Challenge templates, simulator and matching endpoints — no more curl.

### 2.5 Register a new market symbol (DSR-1)

1. `/c/governance/symbol-registry` → **Symbol Registry Panel**.
2. Use the 6-button asset-class picker (Forex / Metal / Index / Crypto / CFD / Futures).
3. Toggle Ingestion / Factory / Validation / Marketplace eligibility chips.
4. Pick execution platforms (cTrader / MT4 / MT5 / MatchTrader / TradeLocker / DXTrade).
5. Submit. The row lands in `market_universe_symbols`.
6. By default the row is **registered but not consumed** — the runtime universe is still `config/symbols.py`. To make the registry authoritative, set the env var `ENABLE_DYNAMIC_MARKET_UNIVERSE=true` and restart the backend.

> **Important:** DSR-3 (full dynamic universe consumption) is intentionally still flag-gated OFF. The recommended path is to register symbols, run a shadow-audit window (≥ 7 days), then flip the flag.

### 2.6 BI5 ingest cycle

* The scheduler runs BI5 ingest every **60 minutes** against all ingestion-eligible symbols with `lookback_days=30` (B-1).
* Manual run: `POST /api/admin/bi5/run` (no UI button — use the Command Palette → `cmd:retry-all` or the Diagnostics → Market Data → BI5 source upload widgets).
* One-time historical backfill of the on-disk archive (zero re-downloading):
  ```bash
  cd /app/backend
  python -m scripts.bi5_one_shot_backfill              # all 7 seeded symbols
  python -m scripts.bi5_one_shot_backfill EURUSD       # one symbol
  ```
  After it completes, refresh `/c/diag/bi5-health` — coverage % will jump.

### 2.7 Govern, promote, retire

* `/c/governance/gov` — overall promotion view (survivor governance, widening proposals).
* `/c/governance/universe` — allowed (pair × timeframe × style) sets.
* `/c/governance/rules` — single-source rules review for prop firms.
* `/c/governance/env` — env priority and rotation knobs.
* `/c/governance/readiness` — readiness snapshot (one-line verdict + jump button also at the top of the Admin tab).
* `/c/governance/admin` (composite — Users · Flag Governance · Execution Realism · Phase 12 Tuning) — admin-only.

---

## 3. Power-user tools

### 3.1 Keyboard shortcuts (all global)

| Shortcut | Action |
|---|---|
| ⌘K / Ctrl+K | Open Command Palette (search modules + actions) |
| ⌘⇧F | Toggle Focus Mode |
| ⌘B | Toggle LeftRail expand (workstation only) |
| ⌘. | Toggle Inspector pane |
| ⌘⇧N | Toggle legacy notification drawer (store-driven) |
| ⌘⌥N | Toggle live notification drawer (backend-driven) |
| ⌘J | Toggle Copilot panel |
| ⌘⌥C | Copy current operator URL (for sharing into Slack/Telegram/audit) |
| ? | Open shortcuts overlay |

### 3.2 Command Palette actions (⌘K)

* `module:<id>` — jump to any module (`dashboard`, `lab`, `explorer`, …).
* `section:propfirm:challenge` — deep-link to Challenge Matching (listed in the "Sections" group).
* `cmd:focus-toggle` — same as ⌘⇧F.
* `cmd:density-toggle` — switch UI density.
* `cmd:premium-toggle` — premium aesthetic (cosmetic).
* `cmd:posture-reset` — clear posture override.
* `cmd:copy-url` — copy current URL.
* `cmd:notifications` — open notifications drawer.
* `cmd:shortcuts` — open shortcuts overlay.
* `cmd:retry-all` — fire a synthetic `asf:retry-all` event (modules opt in to refetch).
* `cmd:inspector` — toggle Inspector.
* `cmd:theme-toggle` — light/dark theme (when the light theme flag is on in `themeStore.js`).
* `cmd:lang-cycle` — cycle en-US → de-DE → en-US.
* `cmd:legacy` — drop back to legacy `/legacy` placeholder (parity testing only).

### 3.3 Hidden surfaces (palette-only)

* **Architect Dashboard** — Factory Supervisor advisor.
* **GEM Factory** — developer console (demoted from primary nav).
* **Factory Supervisor Panel** — observability dashboard for the supervisor lock + heartbeats.

> Challenge Matching is **no longer hidden** — since the 2026-06 restoration it is a first-class section at `/c/propfirm#challenge`.

### 3.4 Architect Dashboard

Reachable only via Command Palette → search "Architect". This is the **dormant** Factory Supervisor advisor. It surfaces:
* Recommended next actions (from `recommendation_engine.py`)
* Eligibility signals (from `eligibility_signals.py`)
* System state view (from `system_state_view.py`)

Until `ENABLE_FACTORY_SUPERVISOR=true` (and the FS-P1.4 consumption flags), every output is marked `advisory_only=true` and no engine consumes it. Safe to inspect anytime.

---

## 4. Feature flags — the single source of truth

The registry is `backend/engines/feature_flags.py`. The current live state is always at:

```
GET /api/latent/feature-flags
```

UI surface: `/c/governance/admin` → Power-User sub-tab "Flag Governance" (`AdminFlagGovernancePanel`).

### 4.1 Activation discipline

* Build dormant infrastructure NOW; activate only when evidence-based maturity gates pass.
* Default values are the conservative dormant setting.
* Activation = set the env var in `backend/.env` and restart the backend.

### 4.2 High-impact flags to know

| Flag | Default | What flipping it does |
|---|---|---|
| `ENABLE_DYNAMIC_MARKET_UNIVERSE` | OFF | DSR-3: scheduler + ingestion read the registry instead of `config/symbols.py`. |
| `FACTORY_RUNNER_OWNS_SCHEDULERS` | OFF | Hand scheduler authority to the sibling `factory_runner.py` process. |
| `ENABLE_FACTORY_SUPERVISOR` | OFF | Activate FS-P1.0 heartbeat + events. (Consumption gates land in FS-P1.4.) |
| `FS_ENABLE_WORKER_SCHEDULER` | OFF | Start the persistent FS worker loop. |
| `ENABLE_NOTIFICATION_CENTER` | OFF | NC writes land in `notifications` collection (in addition to `scaling_events`). |
| `ENABLE_AGING_PENALTY` | OFF | Apply aging penalty to deploy_score in `survivor_registry`. |
| `ENABLE_CBOT_TRADE_PARITY` | OFF | Activate trade-lifecycle parity simulator (advisory). |
| `ENABLE_HTF_PARITY_VALIDATION` | OFF | Activate HTF parity validator (advisory). |
| `ENABLE_TRADE_PARITY_HARD_GATE` | OFF | Promote trade parity from advisory to hard gate in cBot export. |
| `ENABLE_AUTONOMOUS_DISCOVERY` | OFF | Permit orchestrator RULE 12 to emit a trigger action. |
| `RUNNER_AUTO_ROTATE` | OFF | Auto-rotate runner bearer tokens every 30 days. |
| `RUNNER_MULTI_ACCOUNT_ENABLED` | OFF | Multi-account fan-out per runner. |
| `USE_PROCESS_POOL` | OFF | Permit process pool for backtest/mutation hot paths (with companion flags). |

Always inspect the audit log row written at boot — every flag-state change is captured as `latent_capability:boot_state` or `latent_capability:override_diff` in `audit_log`.

---

## 5. Surfaces that are placeholders (G — reservations)

These show in the UI but have **no backend** and **no behaviour**. They reserve layout space for Phase 13/14/15 without re-flow when those phases land. Since the 2026-06 restoration they live inside **collapsed accordions at the bottom of their modules** (cards unchanged — expand to inspect):

| Surface | Module → Section | Phase |
|---|---|---|
| **Strategy Score Architecture** (Quality · Evidence · Market · Trust) | `explorer → reservations` (accordion) | M3 |
| **Strategy Dossier (Passport + 12 reports)** | `explorer → reservations` (accordion) | Phase 13 |
| **Marketplace Layer** | `explorer → reservations` (accordion) | Phase 15 |
| **Dual Scorecards + Auto Valuation** | `portfolio → scorecards-reservations` (accordion) | Phase 14 |
| **Broker Accounts Chip Row** (Track A + Track B + reserved cTrader/VPS) | `exec → brokers` | Future broker integration |

Treat these as immovable — they anchor the navigation hierarchy for future phases.

---

## 6. Authentication

* Operator login is at `/` (the same URL — AuthGate intercepts when unauthenticated).
* Admin credentials are auto-seeded on first backend boot from `backend/.env` (see `auth_utils.seed_admin`).
* Session is stored as a JWT in localStorage.
* No password reset UI exists yet — reset is via env var + DB row delete.

Check `/app/memory/test_credentials.md` for the live admin credentials.

---

## 7. Scheduled background jobs

| Job | Cadence | Driver | Disable by |
|---|---|---|---|
| BID maintenance (1m chunks) | every 15 min | `auto_data_maintainer.restore_if_enabled` | Stop in UI: `MarketDataWorkbench → Automated tab` |
| BI5 maintenance (60-min cadence; dispatches `run_bi5_ingest`) | every 60 min | same | same |
| Auto Discovery scheduler | configurable | `auto_scheduler.restore_if_enabled` | UI: `AutoSchedulerControl` (`/c/ai/sched`) |
| Orchestrator scheduler | configurable | `orchestrator_scheduler.restore_if_enabled` | UI: `OrchestratorPanel` (`/c/ai/orch`) |
| Factory Supervisor worker | every `FS_WORKER_POLL_INTERVAL_SEC` (default 15s) when flag ON | `worker_scheduler.start()` | Flag `FS_ENABLE_WORKER_SCHEDULER=false` |
| Auto-token rotation | every `RUNNER_ROTATE_INTERVAL_SEC` (default 30 days) when flag ON | `runner_token_rotator` | Flag `RUNNER_AUTO_ROTATE=false` |

If `FACTORY_RUNNER_OWNS_SCHEDULERS=true`, the first four are deferred to the sibling `factory_runner.py` process (run separately, also via supervisor).

---

## 8. Common operator tasks → exact endpoints

### Run a one-shot strategy generation
```
POST /api/strategies/generate
```
UI: `/c/lab/panel` → Generate.

### Trigger a one-off BI5 ingest
```
POST /api/admin/bi5/run
Body: {"symbol": "EURUSD", "lookback_days": 30}
```

### Register a new symbol in the DSR
```
POST /api/admin/market-universe
Body: {"symbol": "XAUEUR", "broker_class": "dukascopy", "asset_class": "commodity_metal", "tier": "candidate", ...}
```
UI: `/c/governance/symbol-registry`.

### Check overall system readiness
```
GET /api/latent/deployment-readiness
GET /api/latent/deployment-extras
GET /api/readiness/snapshot
```
UI: `/c/diag/readiness`.

### Get per-symbol BI5 health
```
GET /api/diag/bi5/health
```
UI: `/c/diag/bi5-health`.

### Audit which flags are active right now
```
GET /api/latent/feature-flags
```
UI: `/c/governance/admin → Flag Governance` sub-tab.

### Inspect the activation timeline (when was flag X turned on?)
```
GET /api/latent/activation-timeline
```

---

## 9. Where to look when something breaks

| Symptom | First place to check |
|---|---|
| StatusRail chips amber/red | `/c/diag/monitoring` (Runtime sub-tab) |
| LLM panel stalled | `/c/diag/pipeline` then `/c/ai/river` |
| BI5 health stale / coverage low | `/c/diag/bi5-health` then `python -m scripts.bi5_one_shot_backfill` |
| Strategy panel 401 | Re-login through AuthGate; check `backend/.env` JWT_SECRET |
| Schedulers not firing | `tail -n 200 /var/log/supervisor/backend.*.log` — look for `[startup] auto-maintenance restore failed` / `auto-discovery scheduler restore failed` |
| DSR symbol registered but ingestion ignoring it | `ENABLE_DYNAMIC_MARKET_UNIVERSE` is OFF — that's expected, flip env var after shadow-audit window |
| Factory Supervisor section empty | `ENABLE_FACTORY_SUPERVISOR=false` — that's expected pre-FS-P1.4 |
| Master Bot deploy stuck | `/c/mutate/master-bot` then `master-bot-compile`; check `/api/master-bot/runners/*` |

---

## 10. Things the operator should NOT do

* Do **not** modify `config/symbols.py` directly — use the DSR Symbol Registry UI.
* Do **not** modify `engines/feature_flags.py` to enable a flag — set the env var.
* Do **not** delete the `_inventory/` directory inside the canonical App.zip — it is the migration audit trail.
* Do **not** edit any `_inventory/old1vcpu/*` files — those are immutable reference copies.
* Do **not** assume reservation cards (Phase 13/14/15) have working endpoints. They are layout-only.
* Do **not** activate `ENABLE_AGING_AUTO_DEMOTION`, `FS_ENABLE_AUTO_LEARNING_LOOP`, or `ENABLE_AUTONOMOUS_DISCOVERY` without a recorded soak window — these are gated for safety.

---

## 11. Roadmap (locked direction, in priority order)

| # | Item | Status today |
|---|---|---|
| A | **Dynamic Symbol Registry (DSR-3)** | UI ✓, CRUD ✓, scheduler-DSR-2 ✓ (with flag), DSR-3 awaiting shadow-audit + flag flip |
| B | **BI5 Recovery (BI5 R1)** | B-1 ✓, B-2 ✓, B-9 ✓ (CLI script), health endpoint ✓, panel ✓; pending: log-schema extension for Evidence/Trust/Dossier/Marketplace fields |
| C | **Strategy Dossier Engine** (Phase 13) | UI reservation ✓; no engine yet |
| D | **Automated Valuation Engine** (Phase 14) | UI reservation ✓; no engine yet |
| E | **Marketplace Layer** (Phase 15) | UI reservation ✓; no engine yet |
| F | **Deployment readiness** | Live verdict surfaces in place; awaiting pod hydration of canonical zips |

See `FEATURE_EXPOSURE_AUDIT.md` for the per-subsystem evidence and `ACTIVATION_MATRIX.md` for the flag→behaviour map.

---

## 9. UI Restoration (2026-06) — what changed

The GATE 0 restoration (Steps 1–7, all operator-authorized and testing-agent verified) restored the original 1-vCPU operator experience on top of the COMMAND shell. Frontend-only; zero backend changes; zero flags flipped.

| Change | Where |
|---|---|
| **Mission Control restored** — Dashboard = MissionBriefing + 8-panel workbench stack (workstation), accordions (tablet), briefing-only (mobile) | `/c/dashboard` |
| **Challenge Matching surfaced** (the only Hidden→Visible promotion) | `/c/propfirm#challenge` + ⌘K "Sections" |
| **Execution Overview** — one-glance KPI strip (Paper · Runner · Live) as the Execution landing | `/c/exec` (first section) |
| **Reservations collapsed** — Phase 13/14/15 + Strategy Score cards in bottom accordions (cards unchanged) | Explorer + Portfolio bottoms |
| **BI5 readiness strip** — READY/PARTIAL/NOT READY one-liner above Market Data sub-tabs | Market Data tab |
| **Readiness one-liner** — verdict + jump button on the Admin tab | Admin tab top |
| **Nav behaviour ported** — wheel→horizontal scroll on the tab strip; active tab auto-scrolls into view | top tab bar |
| **Orphans quarantined (NOT deleted)** — 9 zero-importer legacy files | `/app/_inventory/retired_frontend_2026-06/` (see its README) |

Untouched by the restoration: Factory Supervisor (veto), Auto Learning, Notification Center, Copilot v2, all 88 OFF feature flags, strategy import (GATE 3), `ArchitectDashboard.jsx` (kept in place as rehousing IP source).
