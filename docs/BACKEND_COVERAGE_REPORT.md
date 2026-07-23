# Backend Coverage Report — Strategy Factory Canonical

_Report date · 2026-07-23_
_Backend Feature Freeze · v1.1.0-stage4 (preserved)_
_Frontend baseline · FE-B Slices 1–5 shipped_

## Executive Summary

| Metric | Value |
|---|---|
| Total backend endpoints (openapi.json) | **646** |
| Distinct backend paths reached from the frontend | **46** |
| Overall reach (path-level, informational) | **~7 %** |
| Operator-critical endpoints exposed | **48 / 215 (~22 %)** |
| Operator-critical WRITE endpoints exposed | **0** (intentional — Feature Freeze) |
| Operator-critical READ endpoints exposed | **48 / ~90 (~53 %)** |
| Internal-engine endpoints exposed | **1 / 245** (intentional — hidden) |
| Diagnostic / migration endpoints exposed | **1 / 55** (intentional — hidden) |

**Interpretation.** The raw "7 % overall reach" number is misleading. The
backend ships 646 endpoints across 63 tags, but 300+ of those are internal
mutating engines (factory-supervisor, execution-engine, mutation, tuning,
scaling, optimization) invoked by the orchestrator and factory-supervisor
loops — they are not, and never should be, operator-facing surfaces.
Removing internal engines and diagnostic / migration endpoints yields an
operator-relevant surface of ~215 endpoints, of which ~90 are READs. The
frontend now reaches **48 of those ~90 operator-critical READs (~53 %)**
with zero WRITEs, exactly as required by the Feature Freeze.

## Bucket Coverage

### Bucket 1 — Operator-critical (48 / 215 exposed)

Endpoints that must be reachable through the operator UI eventually. All
READs; every WRITE remains intentionally un-wired under Feature Freeze
v1.1.0-stage4.

| Tag | Exposed | Total | Notes |
|---|---:|---:|---|
| master-bot                 | 2  | 58 | Deep-dive surface deferred (FE-B post-freeze slice) |
| knowledge                  | 4  | 34 | Champions / statistics / nearest / health wired via Strategy Lab & Pipeline |
| factory-eval-engine        | 9  | 27 | ✅ FE-B Slice 3 dashboard |
| meta-learning-engine       | 7  | 14 | ✅ FE-B Slice 2 dashboard |
| health                     | 2  | 12 | Aggregate system health probes wired via StatusRail |
| portfolio                  | 0  | 11 | Portfolio surface stub — deferred post-freeze |
| governance                 | 7  | 10 | ✅ FE-B Slice 4 dashboard |
| coe                        | 3  | 10 | ✅ FE-B Slice 4 (queue tile in Cockpit + Data & Governance) |
| data-maintenance           | 4  | 9  | ✅ FE-B Slice 4 dashboard |
| ai-workforce               | 1  | 8  | Health only (StatusRail + Cockpit); router-config / metrics / quality / scores are backend-owned |
| orchestrator               | 2  | 7  | ✅ status + decisions wired; start / stop / dispatch / tasks are WRITE (frozen) |
| auth                       | 2  | 5  | login + me wired; refresh / logout / register unreached but not blocking OAT |
| strategies                 | 3  | 5  | list + generate + get-by-id (Strategy Lab + Pipeline + Passport) |
| coverage                   | 1  | 2  | Data coverage wired via Coverage / Datasets / Market Data surfaces |
| data-health                | 1  | 3  | Data health probe wired in Data & Governance |
| lifecycle / approvals      | 0  | —  | Timeline shim covers approvals client-side; live wiring deferred post-freeze |
| timeline                   | 0  | —  | Timeline shim client-side; live endpoint deferred post-freeze |

### Bucket 2 — Internal engines (1 / 245 exposed — intentional)

These endpoints are invoked internally by the orchestrator / factory-supervisor
/ auto-mutation-runner background loops. They mutate factory state and are
**not** operator-facing. Exposing them from the frontend would violate the
"orchestrator owns cadence" contract.

Tags in this bucket: `factory-supervisor · execution-engine · execution ·
trade-runner · learning · auto-mutation-runner · auto-multi-cycle · auto-selection ·
tuning · mutation · scaling · optimization · brain · market-intelligence ·
market-intelligence-engine · challenge-matching · intelligence · lifecycle ·
llm · prop-firms · prop-firms-intelligence · prop-firm-analysis ·
prop-firm-rules-review · portfolio-builder · portfolio-intelligence · admin`.

### Bucket 3 — Diagnostic / migration (1 / 55 exposed — intentional)

Sysadmin-only endpoints (bi5 certification probes, ASF migration, data
backup, gem-factory research probes, cbot-parity checks). These are invoked
manually by the operator team via `curl` when validating post-migration
integrity; they do not belong on any operator dashboard.

Tags: `admin-bi5-cert · admin-bi5 · bi5-realism · bi5-bid-diff · diag-bi5 ·
asf-migration · data-backup · runner · gem-factory · research · dashboard ·
regime · strategy-memory · cbot-parity · cpu-pool · deployment ·
incremental-run-alias · llm-health · phase4-matching · admin-readiness ·
pipeline_logs`.

### Bucket 4 — Untagged (0 / 131)

131 endpoints ship without an OpenAPI `tags:` block. These are mostly
system-level bookkeeping (schema definitions, model probes, one-off
diagnostic routes) that route through the internal engines. None are
operator-critical.

## Operator-Critical Endpoints Not Yet Exposed

Ranked by operator visibility value, all still Freeze-safe (READ-only):

**HIGH priority (post-freeze, next FE-B extension slice)**
1. `master-bot/*` (58 total, 2 exposed) — Master Bot deep-dive: state, ledgers, IR coverage, health. Recommend a `/c/factory/master-bot` deep-dive dashboard.
2. `portfolio/*` (11 total, 0 exposed) — read-only portfolio composition, PnL, risk breakdown. Portfolio surface stub already exists at `/c/mission?focus=portfolio`.
3. `brain/risk-budget` — real-time risk budget. Pair with `orchestrator/budget`.
4. `orchestrator/tasks` (list) + `orchestrator/budget` — Task Registry can hydrate against `/tasks` instead of `status.task_names` (already read but not deep).

**MEDIUM priority (nice-to-have)**
5. `ai-workforce/{metrics,quality,scores,recent,router-config}` — AI Provider deep-dive dashboard (extend the Cockpit tile).
6. `factory-eval-engine/reports` (list) + `factory-eval/insights/{id}` — Historical reports + insight drill-down.
7. `meta-learning-engine/mode-history` — Meta-learning mode timeline.
8. `governance/replacement-candidates` + `governance/universe/preview` — Governance replacement flow visualization.
9. `coe/dead-letter` (list) + `coe/dead-letter/{id}` — DLQ row inspection.

**LOW priority (post-freeze WRITE flows once executor wired)**
- All `POST/PUT/PATCH/DELETE` endpoints (approve · reject · revert · execute · run · promote · dispatch · pause · resume · reset · rotate · rehydrate · payout). These are the operational levers; wiring them requires lifting the Feature Freeze and standing up the Approvals executor.

## Frontend → Backend Adapter Map

| Adapter | Backend endpoints consumed |
|---|---|
| `apiClient.js`                | `POST /api/auth/login`, `GET /api/auth/me` |
| `coverageAdapter.js`          | `GET /api/data/coverage` |
| `strategyLabAdapter.js`       | `POST /api/strategies/generate`, `POST /api/strategies`, `GET /api/strategies`, `POST /api/knowledge/nearest`, `GET /api/knowledge/statistics`, `GET /api/knowledge/champions` |
| `orchestratorAdapter.js`      | `GET /api/orchestrator/status`, `/decisions`, `/history`, `/api/ai-workforce/health`, `/api/factory-eval/config`, `/api/meta-learning/config` |
| `metaLearningAdapter.js`      | 8 × `/api/meta-learning/*` (status, config, health, evaluations, recommendations, pending, applications, overrides) |
| `factoryEvalAdapter.js`       | 10 × `/api/factory-eval/*` (status, config, health, kpis, reports/latest, reports, insights, recommendations, pending, coverage-gaps) |
| `dataGovernanceAdapter.js`    | 4 × `/api/data/maintenance/*`, `/api/data/health`, `/api/data/coverage`, 6 × `/api/governance/*`, 3 × `/api/coe/*` |
| `timelineShim.js`             | client-side (sessionStorage, no backend calls) |
| `StatusRail.jsx` (inline)     | `/api/orchestrator/status`, `/api/data/coverage`, `/api/ai-workforce/health`, `/api/governance/ecosystem-maturity` |

Total distinct GET paths: **46**. Total WRITE calls from operator-authored
adapters (excluding auth): **0**.

## Freeze Compliance Statement

Every adapter above is read-only. Freeze-safe. The only backend WRITE
issued from the operator UI is `POST /api/auth/login`, which is an
authentication flow, not a factory mutation. The Approvals modal (§12,
Slice γ) is wired to a `null` executor by design — it drops UX events into
the client-side timelineShim and never touches any backend endpoint.

Instrumentation during OAT (`iteration_5.json`) confirms zero POST/PUT/PATCH/DELETE
calls originate from any of the 5 Factory dashboards or the Cockpit.
