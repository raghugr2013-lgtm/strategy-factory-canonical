# Strategy Factory — Implementation Roadmap

**Companion to:** `docs/CAPABILITY_INVENTORY.md` · `docs/GAP_ANALYSIS.md`
· `docs/DEPENDENCY_MAP.md` · `docs/AUTONOMOUS_FACTORY_READINESS.md`.

**Guiding order (non-negotiable):**

1. **Reuse** what already exists.
2. **Refine** what exists but needs polish.
3. **Extend** where a contract is already fixed and only the impl is missing.
4. **Replace** only when Reuse/Refine/Extend cannot meet a hard requirement.
5. **Build New** only when no existing subsystem can be extended.

This roadmap prioritises 1→5 strictly. Every step below cites the
subsystem IDs from `docs/CAPABILITY_INVENTORY.md`.

Constraints re-affirmed:

- No application logic changes required for Phases 0–2.
- No API modifications.
- No database schema changes.
- No production behaviour changes.
- OBSERVE mode preserved.
- No duplicate implementations.

---

## Phase 0 · Verify baseline (already done)

- ✅ Deployment stabilization accepted (`DEPLOYMENT_ARCHITECTURE_REVIEW.md`).
- ✅ Capability Inventory + Gap Analysis + Dependency Map + Readiness
  Report published.
- ✅ Regression pyramid (Tier 1–5) available.
- ✅ Backend Feature Freeze v1.1.0-stage4 confirmed intact.

**Gate to Phase 1:** operator sign-off on the four architectural
blueprint documents.

---

## Phase 1 · Refine (production-safe, env-only)

**Objective:** activate what already exists without writing new code.

### 1.1 · Swap factory-runner entrypoint to recovered impl (R1)

- **Action:** change the `factory-runner` container command from
  `python -m app.runner` to `python -m legacy.factory_runner`, and set
  `FACTORY_RUNNER_OWNS_SCHEDULERS=true` in `.env`.
- **Affected files:** `infra/compose/docker-compose.prod.yml`
  (single-line `command:` change) + `.env` addition.
- **Existing code:** recovered `legacy/factory_runner.py` (unchanged).
- **Verification:** `./infra/scripts/health.sh` — runner container
  healthy, audit log shows `factory_runner:startup`.
- **Rollback:** revert compose `command:` line.

### 1.2 · Turn on the canonical orchestrator (R2)

- **Action:** set `ORCHESTRATOR_ENABLED=true` in production `.env`.
  Every subordinate scheduler with `subordinate_to_orchestrator=true`
  (default) automatically dorms.
- **Existing code:** Phase B.2 orchestrator (C3, C4, C5).
- **Verification:** `GET /api/orchestrator/status` returns `running`;
  `learning`/`continuous` scheduler statuses read `subordinated`.

### 1.3 · Turn on continuous learning (R3)

- **Action:** set `LEARNING_CONTINUOUS_MODE=true` (only relevant if
  orchestrator is off — otherwise no-op).

### 1.4 · Turn on Market Intelligence + auto data maintenance (R4)

- **Action:** set `MI_ENABLED=true`; set `auto_maintenance_config.enabled=true`
  from the admin UI (persisted, so it survives restarts).
- **Existing code:** Phase G market intel (I3) + auto data maintainer (F5).
- **Verification:** market-intelligence indexes bootstrap on next boot;
  BI5 top-ups resume automatically.

**Gate to Phase 2:** all Phase-1 tasks return green through
`./infra/scripts/health.sh` and Tier-1 CI stays green.

---

## Phase 2 · Extend (contract-preserving impl work)

**Objective:** finish the small, contract-preserving deltas so the
long-term modules can ship without further backend engine changes.

### 2.1 · Embedding similarity backend (E2)

- **Slot:** `app/knowledge/similarity.py` — replace `EmbeddingSimilarityStub`.
- **Contract:** `SimilarityBackend` protocol; response shape
  `SimilarityMatchOut` **unchanged**.
- **Choice (deferred to a follow-up ask):** sentence-transformers
  (self-hosted) vs provider API (via VIE). Both keep the router
  intact — only the `backend` field flips from `rule_based` to
  `embedding`.
- **Tests:** extend `backend/tests/test_knowledge_router.py` +
  `test_knowledge_layer.py` to cover the new backend under
  `SIMILARITY_BACKEND=embedding`.
- **Rollback:** flip env var back to `rule_based`; contract identical.

### 2.2 · UKIE domain + connector registration (E7)

- **Slot:** `legacy/engines/knowledge/router.py` (`/api/knowledge/{domains,connectors}`).
- **Action:** register the domains the KB Migration Spec references;
  set `UKIE_DOMAIN_REGISTRY_ENABLED=true`.
- **Existing tests:** `test_knowledge_domains.py`, `test_ukie_gamma.py`,
  `test_domain_router.py`.
- **No API change** — the router is already mounted; endpoints
  self-503 while the flag is off.

### 2.3 · KB Migration Spec — Phases M0 → M3 (E3)

- **Prerequisite:** operator sign-off on `docs/KB_MIGRATION_SPEC.md v0.1`
  (10 open questions in §11).
- **M0:** dry-run mapper (frontend-only preview — no writes).
- **M1..M3:** wait for the freeze to lift on schema additions +
  Timeline endpoint.
- **Existing surfaces:** `app/knowledge/*` + UKIE router — every M-phase
  writes only through those.

### 2.4 · Factory Supervisor activation (E1)

- **Prerequisite:** Phase 1.1 (runner swap) landed.
- **Slot:** `legacy/engines/factory_supervisor/*` — every module is
  already implemented (J1..J6); just needs runtime hook-up.
- **Action:** register the supervisor with the orchestrator's task
  queue (see `orchestrator/registry.py`); wire the notification
  center to the frontend surface (Approvals inbox — see Phase 3).
- **Existing tests:** `test_factory_supervisor_p1_0..p1_4.py`,
  `test_factory_supervisor_p1_4_auto_learning.py`.
- **Verification:** supervisor emits heartbeats + fleet events in the
  audit log; copilot recommendations surface via `/api/factory-supervisor/*`.

### 2.5 · cTrader (or replacement live-broker) adapter (E6)

- **Slot:** `legacy/engines/execution/broker/ctrader/` — scaffolded.
- **Contract:** `execution/broker/base.py` (`BrokerAdapter` ABC).
- **Existing tests:** `test_paper_execution.py`,
  `test_execution_realism_defaults.py`, `test_execution_simulator.py`.
- **Verification:** Tier-4 stress drill (1000 orders) against the new
  adapter passes; `broker_health_check` orchestrator task returns
  green; paper vs live parity < configured tolerance.

**Gate to Phase 3:** every Phase-2 change lands under freeze,
`ORCHESTRATOR_ENABLED=true`, and Tier-3 CI stays green nightly for
7 consecutive days.

---

## Phase 3 · Frontend Extensions (freeze-safe, additive)

**Objective:** wire the frontend to the now-active autonomous factory.

### 3.1 · Approvals inbox on Command surface (Slice δ)

- **Slot:** `frontend/src/os/surfaces/CommandSurface.jsx` — subscribe to
  `useTimelineEvents({eventPrefix:'operator_'})`.
- **Zero backend work.** Same shim, same events, new consumer.
- **PRD status:** deferred at user direction — this phase re-opens it.

### 3.2 · Command Palette · Strategy Pipeline entry

- **Slot:** `frontend/src/os/shell/CmdKPalette.jsx` — add one entry.
- **Trivial.**

### 3.3 · Explorer — re-insert-as-cold action

- **Slot:** `frontend/src/os/surfaces/StrategyExplorer.jsx` (or the
  Strategy Passport CTA) — call `POST /api/strategies` from a KB row
  with the guardrail note pre-filled.
- **Backend already correct** (B1 guardrails, B2 write path).

### 3.4 · Progressive personalization modes (D6 / E5)

- **Slot:** frontend routing frame + design-mode toggles.
- **Reference:** `memory/D6_PERSONALIZATION_MODES.md`,
  `memory/E5_CROSS_MODULE_NAVIGATION.md`.

**Gate to Phase 4:** every Phase-3 surface has `data-testid` invariance
verified by `scripts/check-testids.js`, and the Tier-3 CI stays green.

---

## Phase 4 · Freeze-lift extensions (executor + Timeline endpoint)

**Objective:** land the final two contract swaps once ops sign off on
lifting the freeze around Timeline mutation and per-strategy
state-transition endpoints.

### 4.1 · Real Timeline endpoint (E5)

- **Slot:** swap `adapters/timelineShim.js` persistence from
  sessionStorage-backed zustand → `POST /api/timeline/events`.
- **Consumers unchanged** — the shim signature is stable (per Slice γ
  HANDOVER §4).
- **Backend already indexed** (`outcome_events`), just needs a mutating
  route added; no schema change.

### 4.2 · Approvals executor wiring (E4)

- **Slot:** every `openApproval(...)` call site passes a real `executor`
  that hits the relevant state-transition endpoint (`/api/strategies/{id}/promote`,
  `/api/strategies/{id}/retire`, etc.).
- **Backend endpoints:** already defined in `legacy/api/strategies.py`
  et al. — this phase reactivates their mutation surface after the
  ops-approved freeze lift.

**Gate to Phase 5:** all approvals flows are logged in `outcome_events`
+ `activation_journal` and rollback via `infra/scripts/rollback.sh`
still passes.

---

## Phase 5 · Build New (only if business demand appears)

Nothing in the architectural blueprint requires new engines. Two
optional items exist and should NOT be started speculatively:

### 5.1 · MT4 / MT5 emitters

- **Trigger:** explicit business need for MT4/MT5 deployment.
- **Slot:** peer of `cbot_engine/ir_transpiler.py` under
  `cbot_engine/ir_transpiler_mt4.py` / `_mt5.py`.
- **No API contract change.**

### 5.2 · Additional broker adapters

- **Trigger:** explicit business need.
- **Slot:** peer of `execution/broker/paper.py` / `.../ctrader/`.
- **Contract:** `BrokerAdapter` ABC unchanged.

---

## Prioritised backlog (top-of-queue view)

| # | Item | Type | Reference | Freeze impact |
|---|------|------|-----------|---------------|
| 1 | Sign off on the four blueprint docs | Reuse | Phase 0 | — |
| 2 | Runner entrypoint swap | Refine | Phase 1.1 | none |
| 3 | Orchestrator enable | Refine | Phase 1.2 | none |
| 4 | Continuous learning enable | Refine | Phase 1.3 | none |
| 5 | MI + auto-data enable | Refine | Phase 1.4 | none |
| 6 | UKIE domain registration | Extend | Phase 2.2 | none |
| 7 | Embedding similarity backend | Extend | Phase 2.1 | none |
| 8 | KB Migration Spec sign-off + M0 dry-run | Extend | Phase 2.3 | none |
| 9 | Factory Supervisor activation | Extend | Phase 2.4 | none |
| 10 | cTrader adapter finish | Extend | Phase 2.5 | none |
| 11 | Approvals inbox on Command surface | Extend (FE) | Phase 3.1 | none |
| 12 | Palette entry + Explorer re-insert | Extend (FE) | Phase 3.2/3.3 | none |
| 13 | Personalization modes | Extend (FE) | Phase 3.4 | none |
| 14 | Timeline endpoint swap | Extend | Phase 4.1 | requires freeze lift |
| 15 | Approvals executor wiring | Extend | Phase 4.2 | requires freeze lift |
| 16 | MT4/MT5 emitters | Build New | Phase 5.1 | deferred |
| 17 | Additional broker adapters | Build New | Phase 5.2 | deferred |

---

## Golden invariants for every phase

1. **Reuse before Refine.** Refine before Extend. Extend before Replace.
   Replace before Build New. No exceptions.
2. **No duplicate implementations.** If a subsystem exists in
   `legacy/engines/` and works, it is the answer. Do not port it into
   `app/`.
3. **No API changes** without explicit freeze lift (Phase 4+ only).
4. **No database schema changes** without an approved migration plan.
5. **OBSERVE mode remains the shipping default** for every mutating
   engine until an operator explicitly flips the mode env var.
6. **Every phase gate is `./infra/scripts/health.sh` + a specific CI
   tier passing green.** No phase completes on inspection alone.
7. **Rollback is always one script away** (`infra/scripts/rollback.sh`
   or, for compose-level changes, `git revert` + `deploy.sh
   --skip-precheck`).
8. **Every new state transition writes to** `activation_journal` +
   `audit_log` + the relevant ledger (`outcome_events`,
   `meta_learning_*`, `factory_eval_*`, `market_intel_*`).

---

## What this roadmap explicitly does NOT propose

- Rewriting anything under `legacy/engines/`.
- Duplicating any subsystem into `app/` for "cleanliness".
- Building a new orchestrator, a new scheduler, or a new task queue.
- Building a new knowledge repository, evaluation engine, or lineage
  system.
- Building a new export target speculatively.
- Building a new broker adapter speculatively.
- Bypassing OBSERVE mode, the Approvals gate, or the Backend Feature
  Freeze.

If any future ask trips over one of these bullets, the roadmap
requires a re-review and a fresh version of this document.

---

## Sign-off gate

The four architectural blueprint documents
(`CAPABILITY_INVENTORY.md`, `GAP_ANALYSIS.md`, `DEPENDENCY_MAP.md`,
`AUTONOMOUS_FACTORY_READINESS.md`) are prerequisites for beginning
Phase 1. Once accepted, execution can proceed in the sequence
above — Phase 1 in a single afternoon, Phase 2 across two to three
focused sessions, Phase 3+ freeze-permitting.
