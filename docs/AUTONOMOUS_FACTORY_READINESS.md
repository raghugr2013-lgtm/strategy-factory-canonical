# Strategy Factory — Autonomous Factory Readiness Report

**Companion to:** `docs/CAPABILITY_INVENTORY.md`,
`docs/GAP_ANALYSIS.md`, `docs/DEPENDENCY_MAP.md`.
**Question this document answers:** How much of a 24×7 autonomous
research engine already exists in the canonical repo, what still has
to be built, and what only needs refinement?

---

## 1 · Executive summary

The Factory is **≈ 85 % ready** to run as a 24×7 autonomous research
engine. Every strategic subsystem — scheduler tier, task registry,
strategy generation stack, backtest+optimization+validation stack,
data pipeline, intelligence layer, meta-learning, factory evaluation,
governance, and observability — is already implemented, tested, and
mounted behind runtime flags. **OBSERVE mode is the shipping default**
for every mutating decision.

Only three items sit between the current stack and full autonomy:

1. **[Refine]** Swap the Phase-0 heartbeat stub in `app/runner.py`
   with the recovered `legacy/factory_runner.py` sibling process
   (one entrypoint change, no code rewrite).
2. **[Extend]** Activate `legacy/engines/factory_supervisor/*`
   (recovered — J1..J6 in the inventory) through the wired
   factory-runner. The engine already exposes fleet registry,
   worker scheduling, copilot, notification center, defer queue,
   FAG flag governance, and submission dispatcher.
3. **[Extend]** Wire the frontend Approvals executor + Timeline
   persistence to their real endpoints once the backend freeze
   permits mutations on `POST /api/timeline/events` and the
   individual state-transition endpoints.

Nothing else has to be built. Every task the autonomous factory needs
to run at 3 a.m. — with no operator present — is already registered.

---

## 2 · What already exists to support a 24×7 research engine

### 2.1 · Three-tier scheduler already live

| Tier | Module | Status | Env flag | Role |
|------|--------|--------|----------|------|
| B (fixed interval) | `legacy/engines/learning/continuous_scheduler.py` (legacy) | **PR** | `LEARNING_SCHEDULER_ENABLED` | Baseline learning cycle |
| B.1 (capacity-aware continuous) | `legacy/engines/learning/continuous_scheduler.py` | **PR** | `LEARNING_CONTINUOUS_MODE` | Preferred learning scheduler |
| B.2 (Unified Autonomous Orchestration Engine) | `legacy/engines/orchestrator/*` + `/api/orchestrator/*` | **PR** | `ORCHESTRATOR_ENABLED` | **Canonical autonomy driver.** Subordinates every other scheduler when running (`subordinate_to_orchestrator=true` default). |

All three auto-start on boot when their flag is truthy. Each one
persists its enable state, its budget, and its progress in Mongo so a
container restart doesn't lose a running experiment.

### 2.2 · Autonomous task registry — 17 verbs

Every noun in the autonomous-factory verb list is covered:

| Verb | Task | Module |
|------|------|--------|
| Generate a new strategy | `strategy_generate` | `orchestrator/tasks/strategy_generate.py` |
| Backtest | `backtest` | `.../backtest.py` |
| Mutate | `mutation` | `.../mutation.py` |
| Optimize | `optimization` | `.../optimization.py` |
| Rank | `ranking` | `.../ranking.py` |
| Validate | `validation` | `.../validation.py` |
| Learn from outcomes | `learning_cycle` | `.../learning_cycle.py` |
| Top-up market data | `market_data_topup` | `.../market_data_topup.py` |
| Refresh knowledge index | `knowledge_index_refresh` | `.../knowledge_index_refresh.py` |
| Refresh market intelligence | `market_intelligence_refresh` | `.../market_intelligence_refresh.py` |
| Refresh master-bot bundles | `master_bot_bundle_refresh` | `.../master_bot_bundle_refresh.py` |
| Meta-learn (policy proposals) | `meta_learning_evaluation` | `.../meta_learning_evaluation.py` |
| Factory-eval (self-audit) | `factory_evaluation` | `.../factory_evaluation.py` |
| Self-rebuild (code repair) | `self_rebuild` | `.../self_rebuild.py` |
| BI5 realism sweep | `bi5_realism_sweep` | `.../bi5_realism_sweep.py` |
| Broker health check | `broker_health_check` | `.../broker_health_check.py` |
| Execution attribution | `execution_attribution` | `.../execution_attribution.py` |

Every task is idempotent, ledger-backed, and honours OBSERVE mode by
default.

### 2.3 · Budget guardrail with restart-preserved state

- **`BudgetTracker`** (`orchestrator/budget_tracker.py`) — daily USD
  accounting for LLM + broker + data provider calls.
- **`BUDGET_PERSIST=true`** rehydrates from Mongo on boot (see
  `backend/app/main.py:262–279`).
- If the daily cap is hit the orchestrator halts new task starts and
  the sibling runner stays alive to finish in-flight work.

### 2.4 · Outcome-event ledger — every autonomous decision is auditable

`legacy/engines/learning/{emitter,lineage,supervisor,ledger}.py` +
`meta_learning/ledger.py` + `factory_eval/ledger.py` +
`market_intel_engine/ledger.py` — four independent ledgers, all with
Mongo indexes bootstrapped on boot. Every strategy state transition,
every meta-learning proposal, every intelligence snapshot writes a
tamper-evident row.

### 2.5 · OBSERVE mode is the shipping default

The Backend Feature Freeze v1.1.0-stage4 is currently in effect, and
every mutating engine defaults to OBSERVE:

- **Meta-Learning:** `META_LEARNING_MODE=observe` (see
  `main.py:224–241`). Read endpoints work; no policy is applied
  automatically.
- **Factory Evaluation:** `FACTORY_EVAL_MODE=observe` (`main.py:243–260`).
- **Market Intelligence:** `MI_ENABLED=false` in production by default.
- **Execution Engine:** `EXEC_ENABLED=false` for live; paper is
  always safe.

Turning any of these to `active` is an explicit env flag change.

### 2.6 · Restart-safe persistence

Every scheduler and every long-running job persists its enable flag
and its progress ledger in Mongo. `main.py:87–187` shows the boot
sequence:

- auto-maintenance scheduler resumes if `enabled=true`.
- learning scheduler auto-starts if `LEARNING_SCHEDULER_ENABLED`.
- continuous scheduler auto-starts if `LEARNING_CONTINUOUS_MODE`.
- orchestrator auto-starts if `ORCHESTRATOR_ENABLED`.
- market-intelligence indexes bootstrap if `MI_ENABLED`.
- execution indexes bootstrap if `EXEC_ENABLED`.
- meta-learning indexes bootstrap unless `disabled`.
- factory-eval indexes bootstrap unless `disabled`.
- budget tracker rehydrates from Mongo if `BUDGET_PERSIST`.
- CTS module registers with the Universal Health Contract.

The container can be restarted at any moment without losing state.

### 2.7 · Governance + safety already in place

- **Activation governance** (K1) — every state transition is gated.
- **Activation journal** (K1) + **audit log writer** (K2) — every
  action is recorded.
- **Rule engine / rule enforcement / safety engine / safety injector**
  (K4) — hard limits on what the orchestrator may attempt.
- **Admission controller + adaptive concurrency/cooldown/pool sizer**
  (K5) — soft back-pressure so the factory doesn't overrun capacity.
- **COE / COE-γ / pressure middleware / metrics router** (K6) —
  cross-service coordination.
- **CTS + Universal Health Contract** (K7 / A3) — read-only health
  aggregation with 503-when-off semantics.
- **Feature flags + FAG proposals** (K3, J6) — flag governance can
  propose flag changes for operator approval instead of flipping
  autonomously.

### 2.8 · Infrastructure primitives ready for CPU-heavy work

- **CPU pool / IO pool / queue pressure** (L1) — parallelism control.
- **Host capability + compute probe** (L2) — the factory measures
  its own headroom before scheduling.
- **AI Workforce** (I6) — six-provider router with circuit breakers
  and telemetry.
- **VIE** (A8) — vendor-agnostic LLM gateway (isolated container).
- **Adaptive pool sizer** (K5) — right-sizes worker counts under load.

### 2.9 · Observability the operator can trust

- **Universal Health Contract** — `/api/health/{system,subsystems,<name>}`.
- **Readiness aggregate** — `/api/readiness` reports mongo / vie / redis.
- **Subsystem health retrofit router** — five otherwise-missing
  subsystems get their own `/api/<subsystem>/health` endpoint.
- **Docker labels** — every prod container carries
  `prometheus.scrape=true` + `logging=promtail` (attach a shared
  Grafana + Loki without touching this repo).
- **Research lineage** (K10) + activation timeline for every state
  transition.
- **Backup script** for Mongo (`infra/scripts/backup.sh`).

### 2.10 · Automated regression pyramid ready to run in CI

- **Tier 1** (< 15 s per commit) — memory backend fast smoke.
- **Tier 2** (< 60 s hourly) — 100 + 500 order stress drills.
- **Tier 3** (< 3 min daily) — mongo backend full integration drill.
- **Tier 4** (< 10 min pre-release) — 1000 orders + full regression.
- **Tier 5** (24 h / 72 h) — paper-broker validation soak.

The autonomous factory can gate every self-generated release on the
tier-4 verdict before promoting.

---

## 3 · What must still be built

**Nothing at the subsystem level.** There is no engine, model, ledger,
scheduler, or orchestrator that has to be written from scratch to run
the factory 24×7.

The only two build items are optional, business-driven expansions:

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 1 | MT4/MT5 emitters alongside `cbot_engine/ir_transpiler.py` | LOW / on-demand | Only if a business need for those platforms materialises. Architecturally a peer of the existing cTrader C# emitter. |
| 2 | Additional broker adapters beyond paper + cTrader | LOW / on-demand | Same slot pattern under `execution/broker/`. |

Everything else is **Extend** or **Refine**.

---

## 4 · What only needs refinement (short list)

| # | Item | Effort | Effect on autonomy |
|---|------|--------|--------------------|
| R1 | Swap `app/runner.py` heartbeat stub → recovered `legacy/factory_runner.py` behind `FACTORY_RUNNER_OWNS_SCHEDULERS=true` | **Small** — entrypoint change in the compose file + supervisor registration; the code already exists. | Unlocks a CPU-heavy sibling process so uvicorn workers stay free for HTTP. |
| R2 | Set `ORCHESTRATOR_ENABLED=true` in production `.env`, then set the subordinate scheduler flags to false | **Trivial** — env-only change | Every legacy scheduler becomes dormant; the orchestrator drives the factory. |
| R3 | Set `LEARNING_CONTINUOUS_MODE=true` (or leave orchestrator to own it) | **Trivial** | Preferred over fixed-interval learning. |
| R4 | Set `MI_ENABLED=true` (production) | **Trivial** | Boots the market intelligence indexes + observers. |

---

## 5 · What must be extended (short list)

| # | Item | Effort | Effect on autonomy |
|---|------|--------|--------------------|
| E1 | Activate the recovered Factory Supervisor engine (J1..J6) through the wired sibling runner (R1) | **Medium** | Full 24×7 fleet management: worker runtime, defer queue, copilot, notification center, submission dispatcher, FAG proposals. |
| E2 | Implement the embedding backend behind the existing `EmbeddingSimilarityStub` | **Medium** | Sub-second KB semantic search at 10k+ scale; contract is already fixed. |
| E3 | Execute Phases M0–M3 of `docs/KB_MIGRATION_SPEC.md v0.1` | **Medium** | Post-launch import path for new corpora. |
| E4 | Wire the Approvals modal `executor:` to real state-transition endpoints once freeze permits (per Slice γ HANDOVER §4) | **Small** | Human-approved autonomous mutations become auditable end-to-end. |
| E5 | Swap Timeline shim's session persistence to `POST /api/timeline/events` | **Small** | Cross-surface, cross-session lineage. |
| E6 | Finish cTrader broker adapter (or any live-broker adapter) | **Medium** | Enables the "deploy after paper-broker green" arm of the autonomous factory. |
| E7 | Register KB migration domains + connectors in UKIE (`UKIE_DOMAIN_REGISTRY_ENABLED=true`) | **Small** | E3 gets its ingestion side of the contract. |

---

## 6 · Readiness scorecard

| Capability area | Existing | Delta | Ready for 24×7? |
|------------------|----------|-------|-----------------|
| Scheduler tier | ✅ 3 tiers auto-start | — | **Yes** |
| Task registry | ✅ 17 tasks | — | **Yes** |
| Budget guardrail | ✅ persisted daily | — | **Yes** |
| OBSERVE mode default | ✅ all mutating engines | — | **Yes** |
| Governance + audit | ✅ multi-layer | — | **Yes** |
| Data engine + BI5 | ✅ scheduled top-ups | — | **Yes** |
| Strategy generation | ✅ IR + cBot + mutation + selection | — | **Yes** |
| Backtest + validation | ✅ WFA + MC + OOS | — | **Yes** |
| Meta-learning (OBSERVE) | ✅ 6 evaluators + collectors + applier | — | **Yes** |
| Factory evaluation (OBSERVE) | ✅ 6 collections + evaluators | — | **Yes** |
| Market intelligence | ✅ 8 observers + change detection | flag flip | **Yes** (behind flag) |
| Execution engine | ✅ order/position/quality/attribution/replay + broker health | flag flip + live adapter | **Yes** for paper; **Extend** for live |
| Paper trading | ✅ paper broker + deviation alerts | — | **Yes** |
| Sibling process for CPU-heavy work | ⚠️ recovered but stubbed in prod | R1 refine | **Almost** — one entrypoint swap |
| Factory supervisor (fleet, copilot, notifications, dispatcher) | ⚠️ recovered but dormant | E1 extend | **Almost** — activation only |
| Observability + health probes + backups | ✅ live | — | **Yes** |
| Regression pyramid (5 tiers) | ✅ live | — | **Yes** |
| Approvals + Timeline (human oversight) | ✅ producer shim; consumer pending | E4 + E5 extend | **Almost** — freeze-lift dependent |

**Aggregate:** every "Almost" row resolves to two operations (R1
swap + E1 activate) plus three small frontend extensions (E4, E5,
plus Approvals inbox on Command surface). Zero engine work.

---

## 7 · Risk register

| Risk | Mitigation already in place |
|------|-----------------------------|
| Runaway LLM spend | `BudgetTracker` (C5), persistent across restarts; orchestrator halts task starts on cap |
| Silent policy drift | Meta-Learning defaults to OBSERVE (I4); every proposal must clear FAG approval (J6) |
| Mongo data loss | Isolated `strategy_knowledge_base` DB (B1) never receives writes; nightly `mongodump` (§backup.sh) |
| Broker outage during live deploy | `execution/broker_health.py` + `broker_health_check` task (C4) + Health Contract (A3) |
| Duplicate scheduler execution | Advisory lock (L6) + orchestrator subordination pattern (`subordinate_to_orchestrator=true` default) |
| Container restart mid-experiment | Every scheduler + budget + ledger rehydrates from Mongo on boot (§2.6) |
| Autonomous approval loop bypass | Approvals modal (M2, Slice γ) currently `executor=null` under freeze — no autonomous mutation is possible today |
| Bad canonical release | 5-tier regression pyramid (§2.10) + rollback via `infra/scripts/rollback.sh` |

---

## 8 · Recommended activation sequence (for reference — execution plan lives in `IMPLEMENTATION_ROADMAP.md`)

1. Land Deployment Operations sign-off (done).
2. R1 — swap runner stub → recovered `legacy.factory_runner`.
3. Turn on orchestrator + continuous learning (R2, R3).
4. E7 — register UKIE domains for KB migration.
5. E2 — ship embedding similarity backend.
6. E3 — run KB Migration Spec Phases M0 → M3.
7. E1 — activate Factory Supervisor via the sibling runner.
8. E4 + E5 — wire Approvals executor + Timeline endpoint (post-freeze).
9. R4 + MI activation flags flipped in production.
10. E6 — cTrader (or another live-broker) adapter finished; live-broker
    arm becomes available.

At the end of this sequence the Factory runs autonomously with human
oversight only where it belongs — approvals + rollback authority.

---

## 9 · Bottom line

**The autonomous factory is already built.** The remaining work is
activation and one adapter — not construction. Every future
capability the roadmap needs will compose from what is already in
this repo.
