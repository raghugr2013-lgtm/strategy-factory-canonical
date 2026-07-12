# ACTIVATION_MATRIX.md

**Audit type:** Phase 1 — Activation Matrix
**Source:** `backend/engines/feature_flags.py` (App.zip) + server startup hooks + adapter modules.

This matrix tells the operator **exactly** what changes when each flag flips. Rows are flags; columns are concrete observable side-effects.

Legend:
* **Default** = `_FLAG_SPECS` default in `engines/feature_flags.py` (audit-recorded as the conservative dormant state).
* **Activates** = What goes from no-op to active when the flag is set to `true` / non-default.
* **Pre-requisites** = Other flags or runtime artefacts that must also be present.
* **Reversibility** = How fast the operator can roll back (flag flip + restart unless noted).

---

## 1. Master switches (high-impact)

### `ENABLE_DYNAMIC_MARKET_UNIVERSE`  *(DSR-3)*

| Field | Value |
|---|---|
| Default | `False` |
| Scope | `market_universe` |
| Activates | (a) `market_universe_adapter` populates the in-process cache from Mongo at startup; (b) `auto_data_maintainer._ingestion_symbols()` returns rows from `market_universe_symbols` (where `eligibility.ingestion_enabled=true`); (c) other consumers (factory, validation, marketplace) MAY consume the registry. |
| Pre-requisites | (1) `market_universe_symbols` collection seeded — happens unconditionally at startup; (2) At least one row with `enabled=true, eligibility.ingestion_enabled=true` in the desired tier. |
| Observable | UI `/c/governance/symbol-registry` shows rows; backend log line `[startup] market_universe adapter cache — loaded=<n>`. When OFF: log line `flag OFF, legacy fallback in effect`. |
| Side-effects | The runtime ingestion universe becomes whatever is in the registry. The hard-coded `config/symbols.py` is no longer consulted on the auto_maintenance path. |
| Reversibility | < 30 s (flag flip + restart). |
| Risk | If registry has fewer symbols than legacy, ingestion will silently narrow. Always shadow-audit first. |

### `FACTORY_RUNNER_OWNS_SCHEDULERS`

| Field | Value |
|---|---|
| Default | `False` |
| Scope | runtime topology |
| Activates | The FastAPI worker process skips scheduler restoration (`_restore_auto_maintenance`, `_restore_auto_discovery_scheduler`, `_restore_orchestrator_scheduler` become no-ops). The sibling `factory_runner.py` process owns scheduler authority. |
| Pre-requisites | The `factory_runner.py` process must be running (separate supervisor program). |
| Observable | Startup log: `auto-maintenance deferred to factory_runner sibling`. Verify the runner is alive at `/api/latent/factory-runner-heartbeat`. |
| Reversibility | < 30 s (flag flip + restart of both processes). |
| Risk | If runner process is NOT running, schedulers never fire. |

### `ENABLE_FACTORY_SUPERVISOR`

| Field | Value |
|---|---|
| Default | `False` |
| Scope | `factory_supervisor` |
| Activates | (a) `supervisor_heartbeat.emit()` and `supervisor_events.emit()` perform real writes; (b) leader lease auto-claim loop becomes meaningful; (c) consumption gates of the FS-P1.4 sub-flags (`FS_ENABLE_*`) become effective. |
| Pre-requisites | Indexes already created at boot. |
| Observable | `/api/factory-supervisor/heartbeat`, `/api/factory-supervisor/events`, `notifications` (only if `ENABLE_NOTIFICATION_CENTER=true`). |
| Side-effects | None — observability only in FS-P1.0. Routing decisions still default to `local_only`. |
| Reversibility | < 30 s. |

### `FS_ENABLE_WORKER_SCHEDULER`

| Field | Value |
|---|---|
| Default | `False` |
| Scope | `factory_supervisor` |
| Activates | The persistent asyncio worker loop is started at backend boot. It scans every `FS_WORKER_POLL_INTERVAL_SEC` (default 15s) for due rows in the defer-queue. |
| Pre-requisites | `ENABLE_FACTORY_SUPERVISOR=true` (otherwise no events to defer). Per-task sub-flags gate individual workers: `FS_ENABLE_TELEMETRY_WORKER`, `FS_ENABLE_NOTIFICATION_WORKER`, `FS_ENABLE_AUTO_LEARNING_WORKER` (strictly OFF per directive), `FS_ENABLE_COPILOT_REFRESH`. |
| Observable | Boot log `fs worker_scheduler — started=true`. |
| Reversibility | < 30 s. |

### `ENABLE_NOTIFICATION_CENTER`

| Field | Value |
|---|---|
| Default | `False` |
| Scope | `notification_center` |
| Activates | `supervisor_events.emit()` ALSO writes to the canonical `notifications` collection (in addition to `scaling_events`). The frozen Notification shape (severity / category / status / payload) is honoured. |
| Pre-requisites | `ENABLE_FACTORY_SUPERVISOR=true`. |
| Observable | Rows appear in `notifications`; the live NotificationDrawer (⌘⌥N) shows them. |
| Reversibility | < 30 s. Notification rows persist; they're inert until the read API consumption gate is also active. |

### `FS_ENABLE_NOTIFICATION_API`

| Field | Value |
|---|---|
| Default | `False` |
| Scope | `factory_supervisor` |
| Activates | Downstream consumers (Architect / Copilot) may consume `/notifications`, `/notifications/unread-count`, `/notifications/acknowledge`. The endpoints work either way; this flag is the consumption gate. |
| Pre-requisites | none |
| Observable | Architect / Copilot start surfacing NC rows. |
| Reversibility | < 30 s. |

---

## 2. Auto-Learning / FS-P1.4 (strictly safe, advisory only)

| Flag | Default | Activates | Pre-requisites | Reversibility |
|---|---|---|---|---|
| `FS_ENABLE_SYSTEM_STATE_VIEW` | OFF | Architect + Copilot + FAG may consume `system_state_view.snapshot()` outputs | `ENABLE_FACTORY_SUPERVISOR=true` | < 30 s |
| `FS_ENABLE_ARCHITECT_DASHBOARD` | OFF | Architect Dashboard surfaces "Next Recommended Action" candidates | system state view, FS on | < 30 s |
| `FS_ENABLE_RECOMMENDATION_ENGINE` | OFF | Recommendation Engine outputs become consumable | FS on | < 30 s |
| `FS_ENABLE_ELIGIBILITY_ENGINE` | OFF | Eligibility Signals consumable | FS on | < 30 s |
| `FS_ENABLE_FAG_ENGINE` | OFF | Feature Activation Governance proposals can be created. Admin-only `activate()`. | FS on | < 30 s |
| `FS_ENABLE_COPILOT` | OFF | Operational Copilot answers from `CopilotContext` (no LLM call) | FS on | < 30 s |
| `FS_ENABLE_COPILOT_ADVANCED` | OFF | Advanced Copilot may call provider (must be registered AND selected via `FS_COPILOT_PROVIDER`) | FS on, provider in registry, NOT `none` | < 30 s |
| `FS_COPILOT_PROVIDER` | `"none"` (NullLLMAdapter) | Concrete provider invoked when Advanced Copilot is ON | provider registered in `PROVIDER_REGISTRY` | < 30 s |
| `FS_ENABLE_AUTO_LEARNING` | OFF | Auto-Learning aggregator emits insights consumable by Recommendation/Eligibility/NC fan-out/Architect/Copilot | FS on | < 30 s |
| `FS_ENABLE_AUTO_LEARNING_LOOP` | **OFF (HARD-LOCKED)** | A periodic learning loop. **`ENABLE_AUTONOMOUS_DISCOVERY` is a hard veto.** | n/a — operator directive: stays OFF | n/a |

---

## 3. Strategy scoring & lifecycle

| Flag | Default | Activates | Side-effect | Reversibility |
|---|---|---|---|---|
| `ENABLE_RISK_OF_RUIN` | OFF | Per-strategy RoR persisted + diagnostic. | Diagnostic only (`RISK_OF_RUIN_WEIGHT` still 0.0). | < 30 s |
| `RISK_OF_RUIN_WEIGHT` | `0.0` | When > 0, RoR weighted into `deploy_score`. | **Verifies calibration first**. | < 30 s |
| `RISK_OF_RUIN_DEFAULT_SIMS` | `2000` | Monte-Carlo sim count for RoR. | Pure cost knob. | n/a |
| `ENABLE_AGING_PENALTY` | OFF | `aging_penalty` applied to `deploy_score` in `survivor_registry`. | Stale strategies demote from top of ranking. | < 30 s |
| `AGING_TAU_DAYS` | `60.0` | Decay constant (`penalty = 1 - exp(-Δt/TAU)`). | Curve shape. | < 30 s |
| `AGING_AUTO_DEMOTION_THRESHOLD` | `0.5` | Aging threshold for lifecycle to consider demotion. | Diagnostic until `ENABLE_AGING_AUTO_DEMOTION` ON. | < 30 s |
| `ENABLE_AGING_AUTO_DEMOTION` | OFF | Automatic stage demotion based on aging. | After `ENABLE_AGING_PENALTY` has soaked 30+ days. | < 30 s |
| `ENABLE_CALIBRATION` | OFF | Calibration table applied to predicted `pass_probability`. | Table is built + persisted regardless. | < 30 s |
| `CALIBRATION_MIN_OUTCOMES` | `30` | Minimum outcomes per decile bin. | Tunes when bins deviate from identity. | < 30 s |
| `CALIBRATION_DECILE_COUNT` | `10` | Number of deciles. | Tunes resolution. | < 30 s |

---

## 4. Mutation & Orchestration

| Flag | Default | Activates | Reversibility |
|---|---|---|---|
| `ENABLE_ADAPTIVE_ROTATION` | OFF | Adaptive `env_priority`-weighted rotation in RULE 12. Static rotation otherwise. | < 30 s |
| `ENABLE_ANTI_CORRELATION_FILTER` | OFF | Reject mutations with `|Pearson| > ANTI_CORRELATION_THRESHOLD` against active survivors. | < 30 s |
| `ANTI_CORRELATION_THRESHOLD` | `0.85` | Cutoff. | < 30 s |
| `ENABLE_AI_ADVISORY` | OFF | AI advisory surface (commentary). | < 30 s |
| `ENABLE_DEPLOYMENT_THROTTLE` | OFF | Rate-limit deployment exports per (firm, pair). | < 30 s |
| `ENABLE_AUTONOMOUS_DISCOVERY` | OFF | Orchestrator RULE 12 (AUTONOMOUS_DISCOVERY_TICK) emits trigger actions. | < 30 s |
| `ENABLE_CADENCE_SCHEDULER` | OFF | Per-cell min cadence enforced. Otherwise every cell always runnable. | < 30 s |
| `CADENCE_MIN_GAP_MIN` | `60` | Minutes between two runs of the same cell. | < 30 s |
| `ENABLE_ADAPTIVE_COOLDOWN` | OFF | Cooldown multiplied by error-rate / load. Static otherwise. | < 30 s |
| `ADAPTIVE_COOLDOWN_MAX_MULT` | `4.0` | Cap. | < 30 s |
| `ENABLE_EVENT_CONTINUATION` | OFF | `event_continuations` queue accepts enqueue/pop. No-op otherwise. | < 30 s |
| `ENABLE_REPLAY_PRIORITY` | OFF | Replay candidates sorted by `stage_rank` + `deploy_score`. | < 30 s |
| `ENABLE_PROCESS_POOL_BACKTEST` | OFF | Backtest hot paths route through `cpu_pool` when `USE_PROCESS_POOL=true` AND call-site wired. | < 30 s |
| `ENABLE_PROCESS_POOL_MUTATION` | OFF | Mutation hot paths through cpu_pool. Same conditions. | < 30 s |
| `COMPUTE_AWARE_ORCHESTRATION` | OFF | Orchestrator reads `compute_probe` headroom to widen/narrow scan width. | < 30 s |
| `ENABLE_SOAK_STABILITY_EMITTER` | OFF | Per-tick stability samples written. | < 30 s |
| `ENABLE_ROTATIONAL_ORCHESTRATION` | OFF | Rotational tick `would_execute=true`. Preview endpoint always returns the proposal regardless. | < 30 s |
| `ROTATIONAL_MAX_CELLS_PER_TICK` | `3` | Cap. | < 30 s |
| `ROTATIONAL_EXPLORATION_FLOOR_PCT` | `0.20` | Min exploratory fraction. | < 30 s |
| `ENABLE_AGENT_ADVISOR` | OFF | Mark agent-advisor "would call LLM if wired". Scaffold returns prompt template only. | < 30 s |

---

## 5. Scaling / Capacity

| Flag | Default | Activates | Reversibility |
|---|---|---|---|
| `ENABLE_BAND_BASED_ROUTING` | OFF | `scaling_router.route()` returns accept/defer/refuse per `compute_probe` band. Otherwise always returns ACCEPT. | < 30 s |
| `ENABLE_ADAPTIVE_POOL_SIZING` | OFF | `cpu_pool.pool_size()` consults `adaptive_pool_sizer.recommend_pool_size(host_capability)` when `CPU_POOL_SIZE` env unset. | < 30 s |
| `WORKLOAD_PROFILE` | `"auto"` | Pinned profile (`small`/`medium`/`large`/`xlarge`) honoured if `ENABLE_ADAPTIVE_POOL_SIZING=true`. | < 30 s |
| `ENABLE_ADMISSION_CONTROL` | OFF | `admission_controller.gate()` returns admit/defer/refuse. Otherwise always admits. | < 30 s |
| `QUEUE_PRESSURE_WINDOW_SEC` | `30` | Rolling window for queue pressure. | < 30 s |
| `USE_PROCESS_POOL` | OFF (env) | Permits the process pool. Sub-flags then permit specific hot paths. | < 30 s |

---

## 6. Parity

| Flag | Default | Activates | Reversibility |
|---|---|---|---|
| `ENABLE_CBOT_TRADE_PARITY` | OFF | `engines.cbot_trade_parity.simulate_trades()` consumable by trust gate. Module callable either way. | < 30 s |
| `CBOT_TRADE_PARITY_FIRST_N` | `50` | First-N trades compared. | n/a |
| `ENABLE_HTF_PARITY_VALIDATION` | OFF | HTF parity validator consumable. Today subsample method is used; this adds true time-bucketed comparison. | < 30 s |
| `HTF_PARITY_MAX_DIVERGENCE_PCT` | `5.0` | Verdict band tolerance. | < 30 s |
| `ENABLE_TRADE_PARITY_HARD_GATE` | OFF | Trade-parity becomes required by cBot export hard gate. | < 30 s |
| `ENABLE_HTF_PARITY_HARD_GATE` | OFF | HTF-parity becomes required by cBot export hard gate. | < 30 s |
| `PARITY_CERTIFICATION_MIN_SAMPLES` | `30` | Min sign-offs before promotion-readiness verdict leaves `NEEDS_MORE_EVIDENCE`. | < 30 s |
| `PARITY_CERTIFICATION_MIN_PASS_RATE` | `0.95` | Min would-pass-hard-gate rate before `PROMOTABLE`. | < 30 s |

---

## 7. Execution realism

| Flag | Default | Activates | Reversibility |
|---|---|---|---|
| `ENABLE_EXECUTION_REALISM_DEFAULTS` | OFF | Execution engine substitutes per-pair realism config from registry instead of `DEFAULT_EXECUTION_CONFIG`. Today registry is CRUD-only. | < 30 s |

---

## 8. Market Universe (DSR family)

| Flag | Default | Activates | Reversibility |
|---|---|---|---|
| `ENABLE_DYNAMIC_MARKET_UNIVERSE` | OFF | (See §1) Engines consult `market_universe`. | < 30 s |
| `MARKET_UNIVERSE_DEFAULT_TIER` | `"candidate"` | Default tier on registration. | < 30 s |
| `MARKET_UNIVERSE_AUTO_INGEST` | OFF | Documented hook: future ingestion runners would auto-pull for `tier=active`. No runner consults this today. | < 30 s |
| `MARKET_UNIVERSE_AUDIT_TTL_DAYS` | `90` | TTL retention for `market_universe_audit`. Re-tunes the Mongo TTL index on next boot. | < 30 s |

---

## 9. Master Bot / Multi-Runner (MB-9 Phase 2.B+)

| Flag | Default | Activates | Reversibility |
|---|---|---|---|
| `RUNNER_AFFINITY_POLICY` | `"sticky_pair_tf"` | Active routing policy. Other valid: `least_busy`, `round_robin`, `local_only`. Single-runner fleets degenerate regardless. | < 30 s |
| `RUNNER_TOKEN_GRACE_SEC` | `300` | Window during which both old + new bearer tokens authenticate after rotation. | < 30 s |
| `RUNNER_ROTATE_INTERVAL_SEC` | `2592000` (30 d) | Auto-rotation cadence. Consulted only when `RUNNER_AUTO_ROTATE=true`. | < 30 s |
| `RUNNER_AUTO_ROTATE` | OFF | Activate auto-rotation scheduler. Manual rotation always available. | < 30 s |
| `RUNNER_PARITY_DRIFT_WINDOW_DAYS` | `7` | Trailing window for parity-drift aggregation. | < 30 s |
| `RUNNER_MULTI_ACCOUNT_ENABLED` | OFF | Multi-account fan-out per runner. Otherwise envelope is synthetic single-account row. | < 30 s |
| `RUNNER_AUTO_ROUTE_AT_REGISTER` | OFF | `register_deployment` consults `runner_router.route()` for runner_id picking. Otherwise honours operator-supplied `runner_id=None`. | < 30 s |

---

## 10. Operational hygiene

| Flag | Default | Activates | Reversibility |
|---|---|---|---|
| `AUDIT_LOG_RETENTION_DAYS` | `90` | TTL window for `audit_log.ts_dt`-bearing docs. Set to `0` to disable. | < 30 s (rebuilds TTL index) |

---

## 11. Verifying a flag change

After any flag change:

1. Restart backend: `sudo supervisorctl restart backend`.
2. Confirm the boot log shows the override: `[feature_flags] N/M flags overridden — active: <FLAG=value>, …`.
3. Hit `GET /api/latent/feature-flags` and verify the `is_overridden=true` row.
4. Inspect `audit_log` for the `latent_capability:override_diff` row — it records `added`, `removed`, `changed` between this boot and the previous boot.

## 12. Critical operator directives (hard constraints)

| Directive | How enforced |
|---|---|
| NO automatic strategy mutation without explicit operator | All mutation runners are operator-triggered; orchestrator RULE 12 requires `ENABLE_AUTONOMOUS_DISCOVERY=true`; Auto-Learning loop requires `FS_ENABLE_AUTO_LEARNING_LOOP=true` AND `ENABLE_AUTONOMOUS_DISCOVERY=true` (operator veto on the latter). |
| NO automatic deployment | Master Bot compile + export is always operator-triggered. |
| NO automatic feature activation | `FS_ENABLE_FAG_ENGINE.activate()` requires admin role even when ON. |
| NO automatic Auto-Learning consumption | `FS_ENABLE_AUTO_LEARNING` consumers honour `advisory_only=true`. |
| Factory stays private | Marketplace Layer (Phase 15) is a reservation only. Public surface will be a separate read-only product. |

## 13. Flag activation timeline (queryable)

The `audit_log` collection persists:
* One `latent_capability:boot_state` row per backend boot.
* One `latent_capability:override_diff` row per boot whose override set differs from the previous boot.

Both rows include `ts_dt` and are auto-reaped at `AUDIT_LOG_RETENTION_DAYS`. The activation-timeline endpoint exposes a query surface:

```
GET /api/latent/activation-timeline
GET /api/latent/activation-governance
```

This gives a rolling 90-day answer to "when did ENABLE_X go live?" — no external journal needed.
