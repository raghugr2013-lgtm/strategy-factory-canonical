# Strategy Factory Canonical — Operator Manual

_Version 1.0 · 2026-07-23 · Pre-Phase-1_
_Companion to `docs/PRODUCTION_READINESS_REPORT.md` and `docs/HKB_MIGRATION_REPORT.md`_

---

## Table of Contents

1. [System architecture](#1-system-architecture)
2. [Frontend modules & workflows](#2-frontend-modules--workflows)
3. [Daily operator workflow](#3-daily-operator-workflow)
4. [VPS Phase-1 activation procedure](#4-vps-phase-1-activation-procedure)
5. [Environment variables & configuration](#5-environment-variables--configuration)
6. [OBSERVE · Recommendation · Autonomous modes](#6-observe--recommendation--autonomous-modes)
7. [Meta-Learning lifecycle](#7-meta-learning-lifecycle)
8. [Factory Evaluation lifecycle](#8-factory-evaluation-lifecycle)
9. [Orchestrator lifecycle](#9-orchestrator-lifecycle)
10. [Strategy lifecycle · creation → deployment](#10-strategy-lifecycle)
11. [HKB & Curated Library usage](#11-hkb--curated-library-usage)
12. [Approval workflow](#12-approval-workflow)
13. [Validation workflow](#13-validation-workflow)
14. [Monitoring & health checks](#14-monitoring--health-checks)
15. [Recovery & rollback procedures](#15-recovery--rollback-procedures)
16. [First 24–72 hours after activation](#16-first-2472-hours-after-activation)
17. [Known limitations under Feature Freeze](#17-known-limitations-under-feature-freeze)
18. [Phase-2 roadmap](#18-phase-2-roadmap)

---

## 1. System architecture

Strategy Factory Canonical is a **two-part** autonomous trading research
platform:

```
┌────────────────────────────────────────────────────────────────┐
│                     OPERATOR OS (Frontend)                     │
│   React 18 · react-router · @tanstack/react-query · Vite       │
│                                                                │
│   ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│   │  Mission     │  │  Factory     │  │   Engineering      │   │
│   │  Control     │  │  Cockpit +   │  │   Workspace        │   │
│   │  (approvals) │  │  5 dashboards│  │   (labs & data)    │   │
│   └──────────────┘  └──────────────┘  └────────────────────┘   │
│         │                  │                    │              │
└─────────┼──────────────────┼────────────────────┼──────────────┘
          ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        BACKEND API (FastAPI)                    │
│                    Feature Freeze v1.1.0-stage4                 │
│                                                                 │
│   /api/auth         /api/orchestrator     /api/meta-learning    │
│   /api/strategies   /api/factory-eval     /api/data/*           │
│   /api/knowledge    /api/governance       /api/coe/*            │
│   /api/health       /api/ai-workforce                           │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                          MONGODB                                │
│   strategy_factory_v1            (production DB, live state)    │
│   strategy_knowledge_base        (KB derived views)             │
│   hkb_staging_20260723           (isolated HKB staging, safe)   │
└─────────────────────────────────────────────────────────────────┘
```

### Runtime layers

- **Frontend** — All routes below `/c/*` are authenticated operator
  surfaces. Auth token stored in `authStore` (in-memory, JWT). Each
  surface consumes its own React Query hooks that poll the backend
  every 15–30 seconds. **No writes** happen from a Factory-group
  surface — everything is read-only.
- **Backend** — Feature-frozen at v1.1.0-stage4. Every autonomous
  engine (orchestrator, meta-learning, factory-eval, mutation,
  factory-supervisor) is present but gated by env flags. No new
  engines will be added in Phase 1.
- **MongoDB** — Three databases in use:
  1. `strategy_factory_v1` — live production state.
  2. `strategy_knowledge_base` — derived KB views populated by
     `hkb/scripts/build_kb_views.py`.
  3. `hkb_staging_20260723` — isolated HKB staging DB, kept for
     rollback verification only; drop when confident.

### Module relationships (backend engines)

```
              ┌──────────────────┐
   flags →    │   Orchestrator   │  ← tick every 60s, dispatches
              └────────┬─────────┘
                       │ enqueues via COE queue
                       ▼
              ┌──────────────────┐
              │  Factory-        │  ← invokes engines by schedule
              │  Supervisor      │
              └────────┬─────────┘
                       │
        ┌──────────────┼───────────────┬───────────────┐
        ▼              ▼               ▼               ▼
  ┌──────────┐  ┌──────────┐   ┌──────────┐   ┌──────────────┐
  │ Mutation │  │ Factory- │   │ Meta-    │   │ Data-        │
  │ Engine   │  │ Eval     │   │ Learning │   │ Maintenance  │
  └────┬─────┘  └────┬─────┘   └────┬─────┘   └────┬─────────┘
       │             │              │              │
       ▼             ▼              ▼              ▼
              ┌──────────────────────────┐
              │  MongoDB (state, ledgers,│
              │  histories, corpora)     │
              └──────────────────────────┘
```

- **Orchestrator** owns cadence — every tick dispatches ready tasks.
- **Factory-Supervisor** runs the actual engines under the
  orchestrator's schedule.
- **Mutation Engine** produces new strategy variants.
- **Factory-Eval** grades outcomes and publishes KPIs / insights /
  recommendations.
- **Meta-Learning** learns from historical outcomes and proposes
  parameter refinements (still gated by operator approval).
- **Data-Maintenance** keeps the coverage matrix honest.

**All writes go through the COE queue** (`/api/coe/*`) — one queue,
one dead-letter, one place to pause.

---

## 2. Frontend modules & workflows

### 2.1 Mission Control · `/c/mission`

The operator's home. Shows aggregate factory state at a glance. Two
sub-panels:
- **Status Rail** (top) — 5 domain chips (orchestrator, coverage, AI
  provider, governance, budget) + kill-posture chip.
- **Mission Control body** — quick links, recent approvals, open
  alerts.

### 2.2 Factory group · `/c/factory/*`

Six dashboards. **Cockpit** is the primary landing page; the rest are
drill-downs.

| Route | Purpose |
|---|---|
| `/c/factory`                    | **Cockpit** — one-glance operator view, 7 subsystem tiles + alerts + tasks + decisions |
| `/c/factory/orchestrator`       | Orchestrator status, decisions ledger, task registry |
| `/c/factory/meta-learning`      | Meta-Learning mode, recommendations, evaluations, pending approvals |
| `/c/factory/evaluation`         | Factory-Eval KPIs, insights, recommendations, coverage gaps |
| `/c/factory/data-governance`    | Data-maintenance runs + governance promotion ledger + queue depth |
| `/c/factory/curated`            | Curated Strategy Library (HKB champions across 6 categories) |

### 2.3 Engineering workspace · `/c/engineering/*`

Build & data surfaces. Nine primary routes:

| Route | Purpose |
|---|---|
| `/c/engineering/market-data`         | Live-provider coverage, gap-fill status |
| `/c/engineering/coverage`            | Coverage matrix, per-cell health |
| `/c/engineering/datasets`            | Snapshot/dataset management |
| `/c/engineering/strategy-lab`        | LLM-driven strategy exploration + KB nearest-neighbour |
| `/c/engineering/strategy-pipeline`   | Stage-graded pipeline view (exploratory → champion) |
| `/c/engineering/optimization`        | Hyperparameter tuning surface |
| `/c/engineering/validation`          | Validation reports + robustness |
| `/c/engineering/prop-firms`          | FTMO / FundedNext / PipFarm rule packages |
| `/c/engineering/deployments`         | Deployment posture (Phase-1 empty state) |

### 2.4 Admin group · `/c/admin/*`

Admin-only (RBAC-gated). Users · Integrations · Logs.

### 2.5 Strategy Explorer · `/c/strategies`

Global strategy list with the persistent **HKB banner** at the top
(shows `140 legacy · 132 families → View Curated Library`). Once
live strategies land post-Phase-1, they appear in the table; the HKB
banner remains permanently visible per operator directive.

### 2.6 Data flow contract

Every surface follows the same pattern:

1. React Query hook polls a `/api/*` endpoint every 15–30 s.
2. `safeFetch` wrapper returns `null` on 4xx/5xx — surfaces degrade to
   `DORMANT`/empty-state, never crash.
3. `deriveHealth()` helper classifies backend responses:
   `{detail:"... is off"}` → **DORMANT**, `{status:"ok"}` →
   **HEALTHY**, `{error}` → **CRITICAL**.
4. **No writes** from any Factory-group surface. Reads only.

---

## 3. Daily operator workflow

**Morning (5 minutes):**
1. `/c/factory` — check the Overall Factory Health chip. Green =
   nothing to see; amber/red = start the drill-down.
2. Read the Current Alerts panel — every alert has a subsystem tile
   below it as a one-click drill-in.
3. Skim Recent Decisions — was last night's tick nominal, degraded,
   or critical?

**Mid-day (as needed):**
- Approvals → `/c/mission` shows pending items. Every approval is
  optional under OBSERVE; the factory continues without them.
- Deep-dive → click the corresponding Cockpit tile.

**End of day (5 minutes):**
1. `/c/factory/orchestrator` → confirm cycle count matches expected
   (24 ticks/day at 60 s cadence = 1,440/day post-Phase-1).
2. `/c/factory/data-governance` → confirm no coverage gaps opened,
   DLQ empty.
3. `/c/factory/curated` — spot-check whether meta-learning has
   promoted any new candidates into B/A tiers.

**Weekly (30 minutes):**
- Read `PHASE_1_FACTORY_KPI_REPORT.md` — one-page snapshot of the
  factory's week.
- Review `/c/factory/meta-learning` pending queue; approve/reject
  recommendations.

---

## 4. VPS Phase-1 activation procedure

Full runbook lives in `docs/PRODUCTION_READINESS_REPORT.md` §9 and
`docs/PHASE_1_ACTIVATION_PLAN.md` §6. Summary:

**Prerequisites (all met):**
- Backup: `/app/hkb/backups/prod_pre_hkb_20260723_143620.archive`.
- HKB migration complete (1,073,286 docs).
- Curated Library populated (19 candidates).
- OAT passed (iteration_5 · 100 %).
- HKB UI exposure fixed (iteration_7 · 100 %).

**Activation steps on the VPS:**

```bash
# 1. Apply the four env flags to /opt/strategy-factory/.env
FACTORY_RUNNER_OWNS_SCHEDULERS=true
ORCHESTRATOR_ENABLED=true
BUDGET_PERSIST=true
MI_ENABLED=true

# 2. Deploy and health-check
./infra/scripts/deploy.sh
./infra/scripts/health.sh

# 3. Run the validator
sudo -u <docker-user> \
  /opt/strategy-factory/infra/scripts/phase1_validate.sh \
  > /tmp/phase1.txt

# 4. Populate the validation report
cp /tmp/phase1.txt >> docs/PHASE_1_FACTORY_VALIDATION_REPORT.md
```

**Open the Cockpit** (`https://<vps-domain>/c/factory`) — within
5 minutes you should see:

| Tile | Pre-activation | Post-activation (expected) |
|---|---|---|
| Overall Factory Health   | ATTENTION | **HEALTHY**  |
| Orchestrator             | HALTED    | **RUNNING · NOMINAL** |
| Meta-Learning            | DISABLED  | **OBSERVE · HEALTHY** |
| Factory Evaluation       | DISABLED  | **OBSERVE · HEALTHY** |
| AI Provider              | NO PROVIDER | live provider list |
| Data Maintenance         | IDLE + empty | **ACTIVE** or **IDLE**, non-empty coverage |
| Governance               | maturity value | maturity value (unchanged) |
| Queue (COE)              | DISABLED  | **ACTIVE · DLQ 0** |

If any tile fails to move within 5 minutes, roll back per
`PHASE_1_ACTIVATION_PLAN.md` §7 (three-tier: env-only · code · ledger).

---

## 5. Environment variables & configuration

### 5.1 Phase-1 activation flags (VPS only)

| Flag | Value | Effect |
|---|---|---|
| `FACTORY_RUNNER_OWNS_SCHEDULERS` | `true` | Runner registers schedulers on boot |
| `ORCHESTRATOR_ENABLED`           | `true` | Orchestrator ticks start |
| `BUDGET_PERSIST`                 | `true` | Budget ledger persists across restarts |
| `MI_ENABLED`                     | `true` | Market Intelligence engine on |

### 5.2 Health-provider flags (Phase-1 optional)

Turn these on to activate the health-provider chain that populates
the Cockpit tiles fully:

- `META_LEARNING_HEALTH_PROVIDER_ENABLED`
- `FACTORY_EVAL_HEALTH_PROVIDER_ENABLED`
- `COE_METRICS_ENABLED`
- `DATA_MAINTENANCE_ENABLED`
- `DATA_MAINTENANCE_HEALTH_ENABLED`

Under Feature Freeze these can be `true` without unlocking any WRITE
paths — they only enable **read** endpoints for the Cockpit.

### 5.3 Never modify these

- `MONGO_URL` / `DB_NAME` (backend)
- `REACT_APP_BACKEND_URL` (frontend)
- Emergent-managed universal LLM key (auto-injected)

### 5.4 Universe & governance

`strategy_factory_v1.governance_universe.config` — the authoritative
universe filter. Currently pairs=[EURUSD, GBPUSD, USDJPY, XAUUSD],
timeframes=[H1, H4], `phase_version=30.2`. Legacy 1-vCPU audit trail
archived to `governance_universe_legacy._id="config_legacy_hkb-1vcpu-20260611"`.

---

## 6. OBSERVE · Recommendation · Autonomous modes

Every autonomous engine operates in one of three modes, controlled by
its own `mode` config field (visible on each dashboard):

### 6.1 OBSERVE mode (default post-activation)

- Engine runs continuously, produces recommendations.
- **No mutation is applied without operator approval.**
- Every recommendation lands in `pending` — operator sees it in
  `/c/factory/meta-learning` or `/c/factory/evaluation`.
- Rejected recommendations are archived; accepted ones move to
  `applications`.
- Safety: 100 % operator veto.

### 6.2 Recommendation mode (Phase-2)

- Engine auto-applies **low-risk** recommendations (per policy).
- **High-risk** recommendations still require operator approval.
- Every auto-application is logged to `applications` with
  `auto_applied=true`.
- Rollback: any auto-applied change can be reverted via
  `POST /api/meta-learning/applications/{id}/revert`.

### 6.3 Autonomous mode (Phase-3, future)

- Engine auto-applies ALL recommendations within policy.
- Operator sees applications post-hoc; can still revert.
- Safety: policy limits + circuit breakers.

**Current state:** All engines default to **OBSERVE** on Phase-1
activation. Do not enable Recommendation or Autonomous modes until
Phase-2 review is complete.

---

## 7. Meta-Learning lifecycle

**Endpoints:** `/api/meta-learning/*` (8 endpoints, all READ-only under freeze).

```
   evaluation cycle (every 6h post-Phase-1)
   ┌──────────────────────────────┐
   ▼                              │
observe (backtest outcomes)       │
       │                          │
       ▼                          │
score (per-strategy metrics)      │
       │                          │
       ▼                          │
recommend (parameter tweaks)      │
       │                          │
       ▼                          │
pending queue ────────────────────┤
       │                          │
   operator                       │
   approves/rejects               │
       │                          │
       ▼                          │
applications ledger ──────────────┘  (feeds back into observe)
```

**Dashboard signals:**
- `mode` — OBSERVE / dry-run / off
- `pending` — operator action queue (visible in Cockpit alert if > 0)
- `applications` — window of applied recommendations
- `overrides` — operator-set values that block auto-apply

**HKB warm-up:** on first Phase-1 activation, meta-learning consumes
the 10,430 imported mutation events + 1,042 stability decisions as
prior evidence, bootstrapping the evaluator without waiting for
fresh backtest cycles.

---

## 8. Factory Evaluation lifecycle

**Endpoints:** `/api/factory-eval/*` (10 endpoints, READ-only under freeze).

Grades the autonomous stack across four dimensions:

1. **Data pipeline** — coverage completeness, provider quality.
2. **Generation** — mutation output quality, diversity, novelty.
3. **Validation** — OOS pass rate, stability, robustness.
4. **Execution** — realized vs expected performance.

Publishes:
- **KPIs** — one KPI grid per evaluation window.
- **Insights** — human-readable narrative findings.
- **Recommendations** — proposed parameter changes.
- **Coverage gaps** — flagged missing data cells.

Cadence: hourly full-eval + on-demand via manual refresh (post-freeze).

---

## 9. Orchestrator lifecycle

**Endpoints:** `/api/orchestrator/*` (7 endpoints).

The orchestrator is the metronome. Every 60 seconds:

```
tick t=n
  │
  ├─ read current state (running tasks, budget, cool-downs)
  ├─ compute band: nominal / warn / critical
  ├─ dispatch ready tasks:
  │      · mutation_run (every 15 min)
  │      · factory_eval (every 1 h)
  │      · meta_learning (every 6 h)
  │      · data_maintenance (every 30 min)
  │      · governance_review (daily)
  ├─ record decision in ledger
  └─ emit metrics
```

**Bands:**
- `nominal` — everything within thresholds.
- `warn` — one or more subsystems degraded but not blocking.
- `critical` — one or more circuits open; halts new dispatches.

**Halted state (pre-Phase-1):** `orch.running=false`; every tile
shows HALTED. Post-flag-flip: transitions to `running=true` within
one tick.

---

## 10. Strategy lifecycle

Strategies traverse a canonical stage graph from birth to graveyard:

```
ingested → exploratory → promising → consolidating → validating → champion → deployed
                                                       │
                                                       ▼
                                                     rejected (with reason)
```

| Stage | Trigger | Backend collection |
|---|---|---|
| ingested          | GitHub / TradingView / operator upload   | `ingested_strategies` |
| exploratory       | first mutation cycle                     | `strategy_lifecycle` (stage=exploratory) |
| promising         | pf > 1.0 · dd < 40 · trades ≥ 30         | `strategy_lifecycle` (stage=promising) |
| consolidating     | multi-window OOS confirmation            | `strategy_lifecycle` (stage=consolidating) |
| validating        | prop-firm rules dry-run                  | `strategy_lifecycle` (stage=validating) |
| champion          | passes all validation gates              | `strategy_library` + `strategy_kb_champions` |
| deployed          | operator approval + `eligible_for_deploy=true` | `strategies` (production) |
| rejected          | any stage failure                        | history ledger only, no promotion |

**HKB legacy population:** All 878 lifecycle rows imported from the
1-vCPU pod sit at stage=exploratory. Meta-Learning will re-evaluate
them on first Phase-1 cycle and may promote some to `promising` if
their historical metrics reconcile against the live corpus.

---

## 11. HKB & Curated Library usage

### 11.1 Historical Knowledge Base (HKB)

**Permanent memory.** 1,073,286 documents; every one carries
`__legacy=true`. Never pruned except for provably corrupted or
duplicated records. Includes:

- 140 library specimens
- 878 lifecycle-tracked strategies
- 1,042 mutation runs (10,430 events)
- 1,047 backtest signatures
- 1,053,512 OHLCV candles (3 years, 7 pairs)

**Operator surfaces:**
- `/c/engineering/strategy-lab` — shows `KB 140 / 132 families`
- `/c/engineering/strategy-pipeline` — shows `Historical KB Size 140`
- `/c/strategies` — permanent HKB banner (`140 legacy · 132 families →`)
- `/c/factory/curated` — the primary HKB exploration surface

### 11.2 Curated Strategy Library

19 unique candidates ranked by composite score:
`0.35·PF_logistic + 0.30·DD_inverse + 0.20·OOS + 0.15·stability`.

Tier structure:
- `A-Elite` (composite ≥ 0.70) — empty at Phase-1 (legacy corpus had none)
- `B-Candidate` (composite ≥ 0.50) — 3 candidates
- `C-Experimental` (composite ≥ 0.30) — 16 candidates

Six champion categories exposed on the Curated Library dashboard:
`top_by_composite · top_by_pair · top_by_timeframe · a_elite ·
b_candidate · c_experimental`.

**Refresh:** after every meta-learning cycle post-Phase-1, re-run
`hkb/scripts/build_kb_views.py` to refresh the derived views (fully
idempotent).

---

## 12. Approval workflow

**Under Feature Freeze v1.1.0-stage4:** the Approvals executor is
`null` — the modal opens, captures operator UX events into the
client-side `timelineShim`, but performs **no backend mutation**.

**How it currently works (pre-freeze-lift):**
1. Operator sees `pending` items on `/c/factory/meta-learning` or
   `/c/factory/evaluation`.
2. Operator clicks a pending item → opens the Approvals modal on
   `/c/mission`.
3. Operator approves or rejects → event drops into
   `sessionStorage` (client-side only).
4. Since no backend mutation happens, the pending item remains
   `pending` on next refresh.

**Post-freeze-lift (Phase 4 work):**
- Executor becomes a live POST to the corresponding backend endpoint
  (`/api/meta-learning/pending/{id}/approve`,
  `/api/factory-eval/pending/{id}/approve`, etc.).
- Every approval writes a row to `approvals_ledger` with the operator
  identity + timestamp.

**Recommendation for Phase-1:** treat approvals as informational only
— rely on OBSERVE mode's read-only safety guarantee. Do not depend
on the approval flow to gate anything critical until the executor is
wired.

---

## 13. Validation workflow

Runs on every strategy transitioning from `consolidating` →
`validating`:

1. **OOS holdout** — 20 % test set never seen during optimisation.
2. **Robustness** — parameter perturbation; strategy must survive
   ±10 % parameter jitter without pf/dd degradation > 15 %.
3. **Stability** — rolling-window OOS PF standard deviation.
4. **Prop firm dry-run** — simulate the chosen firm's daily-DD +
   total-DD + min-trades rules; must pass all.
5. **Universe fit** — strategy must be applicable to at least one
   pair × timeframe in the governance universe.

Failure at any step → strategy moves to `rejected` with the failure
reason recorded in `strategy_lifecycle.evidence`.

Operator surfaces:
- `/c/engineering/validation` — validation report list.
- `/c/strategies/{id}` — individual passport with per-gate evidence.

---

## 14. Monitoring & health checks

### 14.1 Real-time signals (Cockpit)

| Signal | Source | Green condition |
|---|---|---|
| Orchestrator status  | `/api/orchestrator/status` | `running=true`, band=nominal |
| Meta-Learning health | `/api/meta-learning/health` | `status=ok` |
| Factory-Eval health  | `/api/factory-eval/health` | `status=ok` |
| AI Provider health   | `/api/ai-workforce/health` | ≥ 1 provider configured, no circuit open |
| Data health          | `/api/data/health` | `status=ok`, no missing symbols |
| Governance maturity  | `/api/governance/ecosystem-maturity` | score ≥ 0.5 |
| COE queue            | `/api/coe/state` | `paused=false`, DLQ depth = 0 |

### 14.2 Server-side health probes

```
GET /api/health              — aggregate probe
GET /api/health/live         — liveness (200 always if process up)
GET /api/health/ready        — readiness (200 when dependencies up)
GET /api/health/database     — Mongo connectivity
GET /api/health/providers    — provider chain health
```

### 14.3 Log locations (VPS)

- `/var/log/strategy-factory/backend.log` — FastAPI + engines.
- `/var/log/strategy-factory/orchestrator.log` — orchestrator ticks.
- `/var/log/strategy-factory/coe.log` — queue depth + dispatch.
- `/var/log/strategy-factory/frontend.log` — nginx access.

### 14.4 Alert channels

Configured via `auto_factory_alert_log` collection. Email/webhook
recipients set in `.env`:
- `ALERT_EMAIL_TO`
- `ALERT_WEBHOOK_URL` (Slack / Discord / custom)

---

## 15. Recovery & rollback procedures

### 15.1 Three-tier rollback (from PHASE_1_ACTIVATION_PLAN.md §7)

**Tier 1 · env-only (2 minutes, zero data risk)**
```bash
# On the VPS
sed -i 's/^ORCHESTRATOR_ENABLED=true/ORCHESTRATOR_ENABLED=false/' /opt/strategy-factory/.env
docker compose restart backend
```
Effect: orchestrator halts, factory-supervisor stops dispatching.
All state preserved. Operator UI shows HALTED.

**Tier 2 · code (10 minutes)**
```bash
cd /opt/strategy-factory
git checkout v1.1.0-stage4
./infra/scripts/deploy.sh
```
Effect: rolls back to the exact release the operator signed off on.

**Tier 3 · ledger / data (60+ minutes)**
```bash
# Restore the pre-HKB-migration backup (see §15.3 below)
mongorestore --uri=$MONGO_URL --archive=<backup>.archive \
  --gzip --drop --nsInclude='strategy_factory_v1.*'
```
Effect: reverts DB to pre-HKB state. Last resort — HKB import is
lost, must be re-run.

### 15.2 Emergency stop (kill switch)

```bash
# The kill-posture chip on the Cockpit shows this state:
POST /api/orchestrator/stop           # halts orchestrator
POST /api/coe/pause                   # halts queue
```

Effect: all dispatches drain; running tasks complete; no new work
starts. Reversible via `POST /api/orchestrator/start` +
`POST /api/coe/resume`.

### 15.3 Backups

- **Pre-HKB-migration:** `/app/hkb/backups/prod_pre_hkb_20260723_143620.archive`
- **Recurring (post-Phase-1):** schedule
  `mongodump --uri="$MONGO_URL" --db=strategy_factory_v1 --archive=/opt/backups/prod_$(date +%Y%m%d_%H%M%S).archive --gzip`
  every 6 h via cron. Keep 30 days.

### 15.4 Selective HKB rollback

Every migrated doc carries `__migration_source='hkb-1vcpu-20260611'`,
so undoing the HKB import is:

```bash
# Undo everything HKB per-collection
for c in strategy_library strategy_lifecycle mutation_events \
         market_data curated_strategy_library <etc>; do
  mongosh --eval "db.$c.deleteMany({__migration_source:'hkb-1vcpu-20260611'})" \
    strategy_factory_v1
done
```

---

## 16. First 24–72 hours after activation

### Hour 0–1 (activation window)

- Overall Factory Health transitions **ATTENTION → HEALTHY** within
  5 minutes.
- All 7 Cockpit tiles show a live tone (green/info/dormant, no
  critical).
- First orchestrator tick fires within 60 s of flag flip.

### Hour 1–6

- First **factory-eval** cycle completes; publishes first
  post-activation KPI report.
- First **data-maintenance** run detects any coverage gaps against
  live providers; backfills automatically.
- First **mutation cycle** runs (empty result expected — the mutation
  engine warms up over 4–6 hours).

### Hour 6–24

- First **meta-learning** cycle runs. Consumes the 10,430 HKB
  mutation events as prior evidence and produces its first
  recommendation batch.
- **Approvals queue** may start receiving items — remember,
  approvals executor is `null` under freeze; items remain `pending`
  informationally.

### Hour 24–72

- 24 orchestrator ticks × 1,440 minutes / 24 = 1,440 ticks logged.
- Expected pass_analysis re-scoring: none until backend engines are
  wired (post-freeze).
- Expected new B/A tier candidates: 0–2 (freeze prevents strategy
  promotion; growth resumes post-freeze).
- Expected DLQ depth: 0 in steady state.

### Warning signs (any → investigate)

- Orchestrator band stays `warn` for > 30 min.
- COE DLQ depth > 5.
- Coverage gaps > 10.
- AI provider circuit `open` for > 15 min.
- Overall Factory Health `CRITICAL` for > 5 min.

---

## 17. Known limitations under Feature Freeze

Every one of these is intentional under v1.1.0-stage4:

### 17.1 Zero WRITE endpoints wired from the operator UI

All approve / reject / revert / execute / run / promote / dispatch /
pause / resume / reset / rotate / rehydrate / payout endpoints exist
in the backend but are NOT called from any frontend surface. The
Approvals modal is client-side only.

### 17.2 No new backend engines will be added

Feature Freeze v1.1.0-stage4 is a hard boundary. Any new capability
requires lifting the freeze — a separate operator decision.

### 17.3 Timeline is a client-side shim

`/c/mission` timeline reads from sessionStorage, not from a backend
`/api/timeline` endpoint (which doesn't exist yet). No historical
timeline survives page refresh.

### 17.4 POST_IMPORT_PIPELINE Stages 2 + 3.1-3.4 + 4-8 are queued

The full 8-stage post-import re-scoring pipeline (Quality v2, Evidence,
Market, Trust, Rank, Match, Portfolio, Marketplace) requires backend
engine invocation. Stages 0, 1, and 3.5 (executed by external
scripts) are complete; the rest wait for the freeze lift.

### 17.5 Curated Library A-Elite tier is empty

The legacy 1-vCPU factory never produced a composite-score ≥ 0.70
strategy. Post-Phase-1 the mutation engine + meta-learning will
promote candidates into A-Elite over 2–4 weeks of continuous
operation.

### 17.6 Market data is BID-only

The imported OHLCV corpus is single-sided (Dukascopy BID). Realistic
execution simulation with slippage requires a spread-aware provider
— that is a Phase-2 wiring decision.

### 17.7 Some health-provider endpoints return `{detail:"... is off"}`

By design in the preview environment. Post-Phase-1 the flags in §5.2
turn these into `{status:"ok"}`. The Cockpit already handles this
transition automatically (deriveHealth normalisation).

### 17.8 Master Bot deep-dive not yet surfaced

58 `master-bot/*` endpoints exist; only 2 are wired (state, IR
coverage). A dedicated Master Bot dashboard is a Phase-2 FE-B
extension.

### 17.9 Portfolio surface not yet surfaced

11 `portfolio/*` endpoints exist; none are wired. Post-Phase-1 the
first live strategies land; a Portfolio dashboard is a Phase-2
FE-B extension.

---

## 18. Phase-2 roadmap

**Phase-2 objective:** graduate from OBSERVE → Recommendation mode
across all autonomous engines, wire the operator WRITE flows, and
expand the operator UI to expose the remaining ~50 % of
operator-critical READ endpoints.

### 18.1 Freeze lift & WRITE wiring (P0)

- Lift Feature Freeze v1.1.0-stage4 (operator decision).
- Wire the Approvals executor → `POST /api/*/approve` for meta-learning
  and factory-eval.
- Wire the strategy promotion flow → `POST /api/strategies/promote`.
- Wire the deployment posture → `POST /api/deployments/*`.

### 18.2 POST_IMPORT_PIPELINE completion (P0)

Run Stages 2, 3.1–3.4, and 4–8 to re-score the imported HKB with the
current backend engines:
- Quality v2 · Evidence · Market · Trust re-scoring.
- Governance re-rank.
- Prop-firm re-match.
- Portfolio-builder re-portfolio.
- Master-Bot re-generate.
- Marketplace-ready gating.

### 18.3 New operator dashboards (P1)

- `/c/factory/master-bot` — Master Bot deep-dive (58 endpoints).
- `/c/factory/portfolio` — live portfolio composition & PnL (11 endpoints).
- `/c/factory/ai-provider` — AI provider deep-dive (8 endpoints).
- `/c/factory/budget` — orchestrator budget + brain risk budget.
- `/c/factory/approvals` — dedicated approvals inbox surface.

### 18.4 Post-freeze backend enhancements (P1)

- Timeline live endpoint (`/api/timeline/*`) — replaces client-side shim.
- WebSocket streams (`/stream/*`) — real-time orchestrator ticks,
  mutation events, approval events.
- Spread-aware market-data provider (bid + ask) — replaces BID-only
  legacy corpus.
- Auto-Recommendation policy engine — governs which recommendations
  can auto-apply and which need approval.

### 18.5 Operational hardening (P2)

- Multi-VPS deployment (staging + prod).
- Automated PHASE_1_FACTORY_KPI_REPORT.md generation (cron + template
  fill-in).
- Alert channel expansion (PagerDuty integration).
- Backup rotation automation.

### 18.6 Marketplace (P2, future)

- Public strategy marketplace surface exposing champion strategies
  with anonymised metadata for external evaluators.
- Requires marketplace-ready gating (POST_IMPORT_PIPELINE Stage 8).

---

## Appendices

- `docs/PRODUCTION_READINESS_REPORT.md` — 10-section sign-off pass
- `docs/HKB_MIGRATION_REPORT.md` — final HKB migration report
- `docs/HKB_MARKET_DATA_INSPECTION.md` — market_data corpus profile
- `docs/BACKEND_COVERAGE_REPORT.md` — endpoint coverage audit
- `docs/PHASE_1_ACTIVATION_PLAN.md` — detailed activation runbook
- `docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md` — observability matrix
- `docs/FE_B_PROPOSAL.md` — frontend expansion roadmap
- `memory/PRD.md` — chronological work-log (source of truth)

**Sign-off:**

| Role | Approval | Date |
|---|---|---|
| Frontend engineering | ✅ (FE-A + FE-B/1-5 + HKB banner + Curated Library) | 2026-07-23 |
| Backend engineering  | ✅ (Feature Freeze v1.1.0-stage4 preserved end-to-end) | 2026-07-23 |
| Testing              | ✅ (iterations 1-7, cumulative 100 % pass) | 2026-07-23 |
| Operator Acceptance  | ✅ (`test_reports/iteration_5.json`) | 2026-07-23 |
| HKB migration        | ✅ (`test_reports/iteration_7.json`, bug fixed & verified) | 2026-07-23 |
| **Ready for VPS Phase-1 activation** | **✅** | **on operator command** |
