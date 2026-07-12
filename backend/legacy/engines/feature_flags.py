"""
Phase 4/5 latent-capability — centralised feature-flag manifest.

Single audit surface for every dormant / staged capability. Replaces
ad-hoc `os.environ.get("ENABLE_*")` reads scattered across engines with
ONE registry that the operator can introspect at startup, at runtime
(via `/api/latent/feature-flags`), or from the pytest suite.

Discipline (per operator decree):
    * Build dormant infrastructure NOW.
    * Activate ONLY when evidence-based maturity gates pass.
    * Default values here are the CONSERVATIVE / DORMANT setting.
    * `os.environ` override is the activation mechanism.
    * Every flag must declare scope + intent for the audit log.

Usage:
    from engines.feature_flags import flag, all_flags
    if flag("ENABLE_AGING_PENALTY"):
        ...

    # At startup (server.py):
    from engines.feature_flags import log_at_startup
    log_at_startup(logging.getLogger(__name__))
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterable, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Flag registry — the SINGLE place to declare a latent capability.
#
# Schema per entry:
#   name      str   ENV var name (also the human-readable key)
#   default   Any   conservative dormant default
#   kind      str   "bool" | "float" | "int" | "str"
#   scope     str   subsystem this flag governs
#   intent    str   one-line summary for audit / docs
#   gates     Optional[List[str]]  other flags this depends on
# ─────────────────────────────────────────────────────────────────────
_FLAG_SPECS: Tuple[Dict[str, Any], ...] = (
    # ─── Phase 4 P4.14 — Risk-of-Ruin engine ──────────────────────
    {
        "name":    "ENABLE_RISK_OF_RUIN",
        "default": False,
        "kind":    "bool",
        "scope":   "risk_of_ruin",
        "intent":  "Persist + diagnose RoR per strategy. Diagnostic-only.",
    },
    {
        "name":    "RISK_OF_RUIN_WEIGHT",
        "default": 0.0,
        "kind":    "float",
        "scope":   "risk_of_ruin",
        "intent":  (
            "Weight of RoR in deploy_score. MUST remain 0.0 until "
            "Phase 4 evidence verifies the calibration."
        ),
    },
    {
        "name":    "RISK_OF_RUIN_DEFAULT_SIMS",
        "default": 2000,
        "kind":    "int",
        "scope":   "risk_of_ruin",
        "intent":  "Default Monte-Carlo simulation count for RoR.",
    },

    # ─── Phase 4 P4.15 — Lifecycle decay / aging ──────────────────
    {
        "name":    "ENABLE_AGING_PENALTY",
        "default": False,
        "kind":    "bool",
        "scope":   "lifecycle_decay",
        "intent":  (
            "Apply aging_penalty to deploy_score in survivor_registry. "
            "While false, aging_penalty is computed + persisted but never "
            "applied to deployment decisions."
        ),
    },
    {
        "name":    "AGING_TAU_DAYS",
        "default": 60.0,
        "kind":    "float",
        "scope":   "lifecycle_decay",
        "intent":  "Decay time constant — penalty=1-exp(-Δt/TAU).",
    },
    {
        "name":    "AGING_AUTO_DEMOTION_THRESHOLD",
        "default": 0.5,
        "kind":    "float",
        "scope":   "lifecycle_decay",
        "intent":  (
            "If ENABLE_AGING_PENALTY AND aging_penalty>threshold AND "
            "last_revalidation>90d, lifecycle MAY demote. Diagnostic-only "
            "until ENABLE_AGING_AUTO_DEMOTION is also true."
        ),
    },
    {
        "name":    "ENABLE_AGING_AUTO_DEMOTION",
        "default": False,
        "kind":    "bool",
        "scope":   "lifecycle_decay",
        "intent":  (
            "Permit automatic stage demotion based on aging. Operator "
            "must explicitly enable AFTER ENABLE_AGING_PENALTY has "
            "soaked for 30+ days."
        ),
        "gates":   ["ENABLE_AGING_PENALTY"],
    },

    # ─── Phase 4 P4.16 — Confidence calibration ────────────────────
    {
        "name":    "ENABLE_CALIBRATION",
        "default": False,
        "kind":    "bool",
        "scope":   "calibration",
        "intent":  (
            "Apply calibration table to predicted pass_probability. "
            "While false, calibration table is built + persisted but "
            "the return value is the raw prediction (identity transform)."
        ),
    },
    {
        "name":    "CALIBRATION_MIN_OUTCOMES",
        "default": 30,
        "kind":    "int",
        "scope":   "calibration",
        "intent":  (
            "Minimum outcomes required per decile bin before that bin "
            "deviates from identity. Below this, the bin returns raw."
        ),
    },
    {
        "name":    "CALIBRATION_DECILE_COUNT",
        "default": 10,
        "kind":    "int",
        "scope":   "calibration",
        "intent":  "Number of probability deciles in the table.",
    },

    # ─── Phase 5 latent governance hooks (pre-wired, dormant) ──────
    {
        "name":    "ENABLE_ADAPTIVE_ROTATION",
        "default": False,
        "kind":    "bool",
        "scope":   "orchestration",
        "intent":  (
            "Adaptive env_priority-weighted rotation in RULE 12. "
            "While false, static hour-of-day rotation is used."
        ),
    },
    {
        "name":    "ENABLE_ANTI_CORRELATION_FILTER",
        "default": False,
        "kind":    "bool",
        "scope":   "mutation",
        "intent":  (
            "Reject variants with |Pearson| > threshold against active "
            "survivors. While false, no rejection."
        ),
    },
    {
        "name":    "ANTI_CORRELATION_THRESHOLD",
        "default": 0.85,
        "kind":    "float",
        "scope":   "mutation",
        "intent":  "Pearson correlation cutoff for variant rejection.",
    },
    {
        "name":    "ENABLE_AI_ADVISORY",
        "default": False,
        "kind":    "bool",
        "scope":   "ai_advisory",
        "intent":  (
            "Surface AI-generated advisory (commentary, not decisions). "
            "Reserved for Phase 9; infrastructure dormant pre-soak."
        ),
    },
    {
        "name":    "ENABLE_DEPLOYMENT_THROTTLE",
        "default": False,
        "kind":    "bool",
        "scope":   "deployment",
        "intent":  (
            "Rate-limit deployment exports per (firm, pair). Dormant "
            "until operator decree."
        ),
    },

    # ─── Phase 1+2 scaffolding (2026 audit) — ALL DORMANT ──────────
    # Each flag below gates a NEW primitive added during the
    # institutional Phase 1+2 scaffolding pass. Defaults preserve
    # current single-worker behaviour; activation requires both the
    # env-var override AND a future code change at the call-site.
    {
        "name":    "ENABLE_AUTONOMOUS_DISCOVERY",
        "default": False,
        "kind":    "bool",
        "scope":   "orchestration",
        "intent":  (
            "Permit orchestrator RULE 12 (AUTONOMOUS_DISCOVERY_TICK) "
            "to emit a trigger action when survivor headroom is "
            "sufficient. While false, RULE 12 emits telemetry only."
        ),
    },
    {
        "name":    "ENABLE_CADENCE_SCHEDULER",
        "default": False,
        "kind":    "bool",
        "scope":   "scheduler",
        "intent":  (
            "Enforce per-cell minimum cadence before re-running a "
            "(pair, timeframe, style). While false, every cell is "
            "always runnable (current behaviour)."
        ),
    },
    {
        "name":    "CADENCE_MIN_GAP_MIN",
        "default": 60,
        "kind":    "int",
        "scope":   "scheduler",
        "intent":  "Minimum minutes between two runs of the same cell.",
    },
    {
        "name":    "ENABLE_ADAPTIVE_COOLDOWN",
        "default": False,
        "kind":    "bool",
        "scope":   "scheduler",
        "intent":  (
            "Multiply base cooldown by error-rate / load signals. "
            "While false, the cooldown is the static base value."
        ),
    },
    {
        "name":    "ADAPTIVE_COOLDOWN_MAX_MULT",
        "default": 4.0,
        "kind":    "float",
        "scope":   "scheduler",
        "intent":  "Hard cap on the adaptive cooldown multiplier.",
    },
    {
        "name":    "ENABLE_EVENT_CONTINUATION",
        "default": False,
        "kind":    "bool",
        "scope":   "continuation",
        "intent":  (
            "Permit the event_continuations queue to accept enqueue() "
            "and pop_next() calls. While false, both are no-ops."
        ),
    },
    {
        "name":    "ENABLE_REPLAY_PRIORITY",
        "default": False,
        "kind":    "bool",
        "scope":   "replay",
        "intent":  (
            "Sort replay candidates by stage_rank + deploy_score. "
            "While false, candidate order is preserved."
        ),
    },
    {
        "name":    "ENABLE_PROCESS_POOL_BACKTEST",
        "default": False,
        "kind":    "bool",
        "scope":   "cpu_pool",
        "intent":  (
            "Permit backtest hot paths to route through cpu_pool. "
            "Effective only when USE_PROCESS_POOL=true and the call-"
            "site has been wired."
        ),
        "gates":   ["USE_PROCESS_POOL"],
    },
    {
        "name":    "ENABLE_PROCESS_POOL_MUTATION",
        "default": False,
        "kind":    "bool",
        "scope":   "cpu_pool",
        "intent":  (
            "Permit mutation hot paths to route through cpu_pool. "
            "Effective only when USE_PROCESS_POOL=true and the call-"
            "site has been wired."
        ),
        "gates":   ["USE_PROCESS_POOL"],
    },
    {
        "name":    "COMPUTE_AWARE_ORCHESTRATION",
        "default": False,
        "kind":    "bool",
        "scope":   "orchestration",
        "intent":  (
            "Let the orchestrator read compute_probe headroom to "
            "widen / narrow scan width. While false, scan width is "
            "static."
        ),
    },

    # ─── VPS Scaling Phase 1.A — observability + skeleton router ───
    # Per VPS_SCALING_P1_IMPLEMENTATION_PLAN.md / WORKER_ALLOCATION_FLOW.md.
    # Default OFF — the router returns DECISION_ACCEPT for every call
    # regardless of band. Flipping this flag ON makes the router consult
    # the band field on compute_probe.headroom_summary(). NO engine
    # consults the router in P1.A — wiring lands in P1.D. Operators
    # may flip this flag freely during the P1.A soak window: behaviour
    # changes ONLY at the (future) wrap sites.
    {
        "name":    "ENABLE_BAND_BASED_ROUTING",
        "default": False,
        "kind":    "bool",
        "scope":   "scaling",
        "intent":  (
            "VPS Scaling P1.A — when ON, engines.scaling_router.route() "
            "returns accept/defer/refuse based on compute_probe band. "
            "When OFF (default), the router returns DECISION_ACCEPT "
            "regardless of band. The router is advisory in P1.A; no "
            "engine consumes its verdict until P1.D."
        ),
    },

    # ─── VPS Scaling Phase 1.B — adaptive pool sizing ───────────────
    # Per VPS_SCALING_P1_IMPLEMENTATION_PLAN.md §1.2 + §2.5.
    # Default OFF — when OFF, `cpu_pool.pool_size()` returns the legacy
    # value (CPU_POOL_SIZE env or 4). Flipping ON allows the adaptive
    # sizer to consult the persisted `host_capability` row whenever
    # CPU_POOL_SIZE is unset. CPU_POOL_SIZE env always wins absolutely.
    {
        "name":    "ENABLE_ADAPTIVE_POOL_SIZING",
        "default": False,
        "kind":    "bool",
        "scope":   "scaling",
        "intent":  (
            "VPS Scaling P1.B — when ON AND CPU_POOL_SIZE env is unset, "
            "cpu_pool.pool_size() consults adaptive_pool_sizer."
            "recommend_pool_size(host_capability). When OFF (default), "
            "pool_size() returns the legacy value. The explicit env pin "
            "wins regardless of flag state."
        ),
    },
    # Workload profile pin: operator override for the tiered classifier.
    # 'auto' = derive from host capability via PROFILE_THRESHOLDS table.
    # 'small'/'medium'/'large'/'xlarge' = pin the profile explicitly.
    # Pinned profile is honoured EVEN WHEN ENABLE_ADAPTIVE_POOL_SIZING
    # is OFF — but the sizer is only consulted under the flag, so the
    # pin is only observably reflected in cpu_pool size when both are set.
    {
        "name":    "WORKLOAD_PROFILE",
        "default": "auto",
        "kind":    "string",
        "scope":   "scaling",
        "intent":  (
            "VPS Scaling P1.B — operator override for the tiered "
            "profile classifier in host_capability.recommend_profile(). "
            "Valid: auto / small / medium / large / xlarge."
        ),
    },

    # ─── VPS Scaling Phase 1.C — admission control + queue pressure ──
    # Per VPS_SCALING_P1_IMPLEMENTATION_PLAN.md §1.3 + §1.4 and
    # CAPACITY_ENGINE_DESIGN.md §4/§5/§6. Default OFF — when OFF,
    # admission_controller.gate() short-circuits to admit. When ON,
    # the gate consults host capability, compute probe, and queue
    # pressure to produce admit / defer / refuse per WorkloadClass.
    # The verdict is ADVISORY in P1.C — no engine consumes it. Wiring
    # into the cpu_pool / auto_factory / mutation_engine /
    # master_bot_deployment entry points lands in P1.D.
    {
        "name":    "ENABLE_ADMISSION_CONTROL",
        "default": False,
        "kind":    "bool",
        "scope":   "scaling",
        "intent":  (
            "VPS Scaling P1.C — when ON, admission_controller.gate() "
            "returns admit/defer/refuse based on host capability + "
            "compute probe band + queue pressure. When OFF (default), "
            "the gate ALWAYS returns admit (reason=flag_off) — byte-"
            "identical to the pre-P1.C world. Advisory in P1.C; "
            "consumed by wrap sites in P1.D."
        ),
    },
    {
        "name":    "QUEUE_PRESSURE_WINDOW_SEC",
        "default": 30,
        "kind":    "int",
        "scope":   "scaling",
        "intent":  (
            "VPS Scaling P1.C — rolling-window length in seconds for "
            "queue_pressure.snapshot(). Range 1..600; defaults to 30."
        ),
    },

    # ─── Factory Supervisor Phase 1.0 — observability + leader lease ──
    # Per FACTORY_SUPERVISOR_P1_ARCHITECTURE_REVIEW.md.
    # Default OFF — when OFF, factory_supervisor modules are dormant:
    #   * supervisor_heartbeat.emit() / supervisor_events.emit() are no-op
    #   * fleet_registry.snapshot() still works (read-only, no side effects)
    #   * supervisor_lock primitives still work (no auto-claim loop in FS-P1.0)
    # Flipping ON activates emit paths. No routing, no admission overrides
    # yet — those land in FS-P1.1+. Rollback < 60 s via flag flip + restart.
    {
        "name":    "ENABLE_FACTORY_SUPERVISOR",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "Factory Supervisor FS-P1.0 master switch. When OFF (default), "
            "supervisor_heartbeat/supervisor_events emit() are no-ops; "
            "byte-identical to the pre-FS world. When ON, the Supervisor "
            "writes heartbeats + events. Routing/admission overrides land "
            "in FS-P1.1+; FS-P1.0 ships observability + leader lease only."
        ),
    },
    {
        "name":    "FS_ROUTING_POLICY",
        "default": "local_only",
        "kind":    "string",
        "scope":   "factory_supervisor",
        "intent":  (
            "Factory Supervisor routing policy. Valid: "
            "local_only / least_busy / round_robin / sticky_pair_tf. "
            "FS-P1.0 ships local_only ONLY; other policies activate in FS-P1.1."
        ),
    },
    {
        "name":    "FS_LEADER_LEASE_TTL_SEC",
        "default": 60,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "TTL (seconds) for the supervisor leader cooperative lease. "
            "Clamped 5..3600. Holder is expected to renew at <=TTL/2."
        ),
    },
    {
        "name":    "FS_HEARTBEAT_CADENCE_SEC",
        "default": 30,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "Supervisor heartbeat cadence (seconds). Verdict bands use "
            "this as the canonical cadence: alive < 2x, stale < 4x, dead >= 4x."
        ),
    },
    {
        "name":    "ENABLE_NOTIFICATION_CENTER",
        "default": False,
        "kind":    "bool",
        "scope":   "notification_center",
        "intent":  (
            "Notification Center master switch. When OFF (default), "
            "supervisor_events.emit() writes ONLY to scaling_events. "
            "When ON AND ENABLE_FACTORY_SUPERVISOR=true, events ALSO "
            "land in the canonical `notifications` collection with the "
            "frozen Notification shape (severity/category/status/payload). "
            "The full NC API surface lands in FS-P1.3."
        ),
    },

    # ─── Factory Supervisor — FS-P1.2 (defer queue + worker runtime) ──
    {
        "name":    "FS_ENABLE_DEFER_QUEUE",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.2 — when ON AND ENABLE_FACTORY_SUPERVISOR=true, the "
            "submission_dispatcher persists deferred outcomes to "
            "`factory_supervisor_defer_queue` for later retry. When OFF, "
            "deferred outcomes are still emitted as events but NOT enqueued."
        ),
    },
    {
        "name":    "FS_ENABLE_DEFER_WORKER",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.2 — when ON AND FS_ENABLE_DEFER_QUEUE=true, the "
            "background worker_runtime polls the defer queue on cadence "
            "and re-dispatches eligible rows. OFF by default; activation "
            "requires explicit operator sign-off."
        ),
    },
    {
        "name":    "FS_DEFER_RETRY_BASE_SEC",
        "default": 30,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "Base retry delay (seconds) for the defer queue. Effective "
            "delay = base * 2^retry_count, clamped to FS_DEFER_RETRY_MAX_SEC."
        ),
    },
    {
        "name":    "FS_DEFER_RETRY_MAX_SEC",
        "default": 1800,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "Maximum retry delay (seconds) for the defer queue. Exponential "
            "backoff is clamped to this ceiling."
        ),
    },
    {
        "name":    "FS_DEFER_MAX_RETRIES",
        "default": 8,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "Maximum retry attempts per deferred workload. After this many "
            "retries the row is marked status='failed' and a WORK_FAILED "
            "event is emitted."
        ),
    },
    {
        "name":    "FS_DEFER_TTL_SEC",
        "default": 86400,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "TTL (seconds) for queued rows. Rows older than this are "
            "auto-expired by the worker (status='expired'); WORK_EXPIRED "
            "event emitted."
        ),
    },
    {
        "name":    "FS_WORKER_POLL_INTERVAL_SEC",
        "default": 15,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "Defer-queue worker poll interval (seconds). Worker scans for "
            "due rows at this cadence. Clamped 1..600."
        ),
    },
    {
        "name":    "FS_REMOTE_TRANSPORT",
        "default": "none",
        "kind":    "string",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.2 — remote-submit transport selector. Valid: "
            "none / http. 'http' is a stub in FS-P1.2 that returns "
            "NotConnectedResult; real activation requires sign-off "
            "+ concrete implementation in FS-P1.5+. Provider/transport "
            "neutral — future transports (grpc, websocket, queue) plug "
            "in via TRANSPORT_REGISTRY with zero call-site change."
        ),
    },

    # ─── Factory Supervisor — FS-P1.3 (system_state_view + dashboard + scheduler) ──
    {
        "name":    "FS_ENABLE_SYSTEM_STATE_VIEW",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — when ON, downstream consumers (Copilot, FAG, "
            "Auto-Learning readiness) are PERMITTED to consume "
            "system_state_view.snapshot() for decisions. The aggregator "
            "itself always runs (read-only is safe); when OFF the "
            "snapshot is advisory_only=true."
        ),
    },
    {
        "name":    "FS_ENABLE_ARCHITECT_DASHBOARD",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — when ON, the Architect Dashboard advisor is "
            "permitted to surface 'Next Recommended Action' candidates "
            "to operators / Copilot. The Architect remains read-only, "
            "advisory-only, with zero execution authority either way."
        ),
    },
    {
        "name":    "FS_ENABLE_WORKER_SCHEDULER",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — when ON AND ENABLE_FACTORY_SUPERVISOR=true, the "
            "background worker_scheduler starts a persistent asyncio "
            "loop on backend startup that drains due defer-queue rows "
            "every FS_WORKER_POLL_INTERVAL_SEC. Default OFF. Per-task "
            "sub-flags (FS_ENABLE_TELEMETRY_WORKER / NC / AUTO_LEARNING "
            "/ COPILOT_REFRESH) gate individual future workers."
        ),
    },
    {
        "name":    "FS_ENABLE_NOTIFICATION_API",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — when ON, downstream consumers (Architect / "
            "Copilot) may consume the Notification Center read API "
            "(/notifications, /notifications/unread-count, "
            "/notifications/acknowledge). The endpoints work either "
            "way; this flag is the consumption gate."
        ),
    },
    {
        "name":    "FS_ENABLE_TELEMETRY_WORKER",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — per-task sub-flag for the cTrader telemetry "
            "scheduler task. Activation requires this flag AND "
            "FS_ENABLE_WORKER_SCHEDULER. Body lands in FS-P1.4+."
        ),
    },
    {
        "name":    "FS_ENABLE_NOTIFICATION_WORKER",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — per-task sub-flag for the NC fan-out worker "
            "(multi-channel deliveries). Activation requires this flag "
            "AND FS_ENABLE_WORKER_SCHEDULER. Body lands in FS-P1.4+."
        ),
    },
    {
        "name":    "FS_ENABLE_AUTO_LEARNING_WORKER",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — per-task sub-flag for the Auto-Learning queue "
            "drain worker. Strictly OFF per operator decree. Activation "
            "requires this flag AND FS_ENABLE_WORKER_SCHEDULER AND a "
            "future Auto-Learning gate."
        ),
    },
    {
        "name":    "FS_ENABLE_COPILOT_REFRESH",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.3 — per-task sub-flag for the periodic Copilot "
            "context refresh task. Provider-agnostic. Activation "
            "requires this flag AND FS_ENABLE_WORKER_SCHEDULER. Body "
            "lands in FS-P1.4+."
        ),
    },

    # ─── Factory Supervisor — FS-P1.4 (Recommendation engine, Eligibility,
    #     Feature Activation Governance, Copilot context layer, LLM shim) ──
    # All FS-P1.4 capabilities ship DORMANT. Recommendation /
    # Eligibility engines run unconditionally as read-only producers
    # (safe); downstream consumption is gated by the per-engine
    # CONSUMPTION flags below. The FAG state machine `observe →
    # recommend → notify → approve → activate` requires
    # FS_ENABLE_FAG_ENGINE=true to land proposals, AND the only
    # mutator (`activate()`) further requires the caller to be admin.
    # The Copilot layers are entirely provider-agnostic — no LLM SDK
    # is imported at module load; the Advanced layer's only mutator
    # is provider registration, which itself does not call any LLM.
    {
        "name":    "FS_ENABLE_RECOMMENDATION_ENGINE",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 — when ON AND ENABLE_FACTORY_SUPERVISOR=true, "
            "downstream consumers (Copilot, FAG, Auto-Learning) are "
            "PERMITTED to consume recommendation_engine.evaluate() "
            "output for decisions. The engine itself always runs "
            "(read-only is safe); the flag is the consumption gate."
        ),
    },
    {
        "name":    "FS_ENABLE_ELIGIBILITY_ENGINE",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 — when ON AND ENABLE_FACTORY_SUPERVISOR=true, "
            "downstream consumers may consume eligibility_signals."
            "evaluate_all() output. The evaluator itself always runs "
            "(read-only pure functions); the flag is the gate."
        ),
    },
    {
        "name":    "FS_ENABLE_FAG_ENGINE",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 — Feature Activation Governance master switch. "
            "When OFF (default), fag_proposals.observe() is a no-op "
            "(returns reason='engine_off' without DB write); even "
            "ON, fag_proposals.activate() requires admin role. The "
            "operator's directive veto (Auto-Learning) is honoured "
            "REGARDLESS of this flag."
        ),
    },
    {
        "name":    "FS_ENABLE_COPILOT",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 — Operational Copilot layer consumption gate. "
            "When OFF (default), copilot_operational.answer() returns "
            "advisory_only=true. The layer NEVER calls an LLM; it "
            "answers from the CopilotContext alone."
        ),
    },
    {
        "name":    "FS_ENABLE_COPILOT_ADVANCED",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 — Advanced Intelligence Copilot layer. When OFF "
            "(default), copilot_advanced.invoke() returns "
            "{'provider': 'none', 'advisory_only': true, ...} without "
            "calling any provider. Even when ON, an explicit provider "
            "must be registered AND selected via FS_COPILOT_PROVIDER. "
            "No LLM SDK is imported at module load — provider-agnostic."
        ),
    },
    {
        "name":    "FS_COPILOT_PROVIDER",
        "default": "none",
        "kind":    "string",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 — selected provider name for the Advanced "
            "Intelligence Copilot. Valid: any name registered in "
            "engines.factory_supervisor.copilot_advanced.PROVIDER_REGISTRY "
            "(default 'none' → NullLLMAdapter, never calls out)."
        ),
    },
    {
        "name":    "FS_FAG_PROPOSAL_TTL_SEC",
        "default": 86400,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 — TTL (seconds) for FAG proposals before "
            "expire_overdue() flips them to state='expired'. Default "
            "1 day; clamped 60..2592000."
        ),
    },

    # ─── Factory Supervisor — FS-P1.4 Auto-Learning Infrastructure ──
    # The Auto-Learning aggregator unifies the four dormant learning
    # components (risk_of_ruin, lifecycle_decay, calibration_framework,
    # execution_realism_defaults) into a read-only insights surface
    # consumed by the Recommendation Engine, Eligibility Signals,
    # Notification Center fan-out, Architect Dashboard, and Copilot
    # Context. Every gate below DEFAULTS OFF. Strict operator policy:
    # NO automatic loop, NO automatic strategy mutation, NO automatic
    # deployment, NO automatic feature activation.
    {
        "name":    "FS_ENABLE_AUTO_LEARNING",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 Auto-Learning — consumption gate for the read-only "
            "Auto-Learning Insights aggregator. When OFF (default), the "
            "aggregator still runs (read-only is safe) but every consumer "
            "must honour advisory_only=true. NEVER causes execution, "
            "mutation, deployment, or feature activation."
        ),
    },
    {
        "name":    "FS_ENABLE_AUTO_LEARNING_LOOP",
        "default": False,
        "kind":    "bool",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 Auto-Learning — loop gate. Strictly OFF per operator "
            "directive. Even if flipped ON, ENABLE_AUTONOMOUS_DISCOVERY "
            "remains a hard veto. No loop exists today; this flag exists "
            "to be matched against the directive veto by audit tooling."
        ),
        "gates":   ["ENABLE_AUTONOMOUS_DISCOVERY"],
    },
    {
        "name":    "FS_AUTO_LEARNING_ROR_THRESHOLD",
        "default": 0.10,
        "kind":    "float",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 Auto-Learning — Risk-of-Ruin threshold (0..1). When "
            "any recently-evaluated strategy reports a RoR at or above "
            "this value, the Auto-Learning aggregator emits a WARN-class "
            "insight. Advisory only."
        ),
    },
    {
        "name":    "FS_AUTO_LEARNING_AGING_THRESHOLD",
        "default": 0.6,
        "kind":    "float",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 Auto-Learning — aging-penalty threshold (0..1) for "
            "flagging stale strategies as revalidation candidates. "
            "Advisory only — never triggers automatic demotion."
        ),
    },
    {
        "name":    "FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES",
        "default": 30,
        "kind":    "int",
        "scope":   "factory_supervisor",
        "intent":  (
            "FS-P1.4 Auto-Learning — minimum resolved outcomes required "
            "before the aggregator emits a CALIBRATION_READY suggestion. "
            "Advisory only."
        ),
    },


    # ─── Phase 2 Pass 5 — long-tail scaffolding (also dormant) ─────
    {
        "name":    "ENABLE_SOAK_STABILITY_EMITTER",
        "default": False,
        "kind":    "bool",
        "scope":   "observability",
        "intent":  (
            "Permit per-tick stability sample writes to the "
            "soak_stability_samples collection. While false, "
            "capture() is a no-op."
        ),
    },
    {
        "name":    "ENABLE_ROTATIONAL_ORCHESTRATION",
        "default": False,
        "kind":    "bool",
        "scope":   "orchestration",
        "intent":  (
            "Mark that rotational orchestration would be executed if "
            "wired. The preview endpoint always returns a proposal, "
            "but `would_execute` reflects this flag."
        ),
    },
    {
        "name":    "ROTATIONAL_MAX_CELLS_PER_TICK",
        "default": 3,
        "kind":    "int",
        "scope":   "orchestration",
        "intent":  (
            "Cap on cells per rotational tick when activated. Pure "
            "configuration; consumed by rotational_orchestrator only."
        ),
    },
    {
        "name":    "ROTATIONAL_EXPLORATION_FLOOR_PCT",
        "default": 0.20,
        "kind":    "float",
        "scope":   "orchestration",
        "intent":  (
            "Minimum exploratory fraction in the rotational slice "
            "(anti-monoculture)."
        ),
    },
    {
        "name":    "ENABLE_AGENT_ADVISOR",
        "default": False,
        "kind":    "bool",
        "scope":   "ai_advisory",
        "intent":  (
            "Mark that the agent-advisor would call an LLM if wired. "
            "Even when true, the scaffold returns only the prompt "
            "template — no LLM call is made from the scaffold."
        ),
    },

    # ─── P0.4 — Dormant cBot trade-lifecycle parity module ─────────
    # Audit doc §3.2: today's cbot_parity proves SIGNAL parity, not
    # TRADE parity. P0.4 introduces a dormant candle-level trade
    # lifecycle simulator (next-bar-open entry, intrabar SL/TP
    # resolution, position bookkeeping). NO production wiring; no
    # tick engine; flag-gated. Default OFF — preserves current
    # behavior byte-for-byte.
    {
        "name":    "ENABLE_CBOT_TRADE_PARITY",
        "default": False,
        "kind":    "bool",
        "scope":   "cbot_parity",
        "intent":  (
            "Enable the dormant cBot trade-lifecycle parity module "
            "(engines.cbot_trade_parity). When OFF the module's "
            "simulate_trades() is callable but no production code "
            "path consults it. Activation requires both this flag "
            "AND a future code change to wire a call-site into the "
            "trust gate."
        ),
    },
    {
        "name":    "CBOT_TRADE_PARITY_FIRST_N",
        "default": 50,
        "kind":    "int",
        "scope":   "cbot_parity",
        "intent":  (
            "Number of first trades to compare in the trade-lifecycle "
            "parity report. Operator-tunable; consumed only by "
            "engines.cbot_trade_parity.simulate_trades()."
        ),
    },

    # ─── P1.2 — Per-pair execution-realism defaults registry ───────
    # Dormant registry; no production engine consults it. When the
    # operator decrees this flag ON, a FUTURE P1.1 wiring will
    # substitute the lookup result for the hard-coded
    # execution_engine.DEFAULT_EXECUTION_CONFIG. Today the registry is
    # only readable/writable through the admin endpoints; the
    # execution engine continues to default to zero costs.
    {
        "name":    "ENABLE_EXECUTION_REALISM_DEFAULTS",
        "default": False,
        "kind":    "bool",
        "scope":   "execution_realism",
        "intent":  (
            "Mark that engines.execution_realism_defaults would be "
            "consulted by the execution engine if wired. While OFF, "
            "the registry is a pure CRUD surface — no engine reads it."
        ),
    },

    # ─── P1.6 — Dynamic market-universe registry ───────────────────
    # Dormant per-symbol registry sitting BESIDE governance_universe.
    # governance_universe decrees allowed (pair × TF × style) sets;
    # market_universe captures per-symbol broker spec / classification /
    # tier / exploration budget / compute hint so operators can
    # register arbitrary broker symbols (XRPUSD, NAS100, US30, XTIUSD,
    # exotic FX crosses, etc.) WITHOUT code edits. NO engine consults
    # the registry today; statically enforced by the dormancy test.
    {
        "name":    "ENABLE_DYNAMIC_MARKET_UNIVERSE",
        "default": False,
        "kind":    "bool",
        "scope":   "market_universe",
        "intent":  (
            "Mark that engines.market_universe would be consulted by "
            "ingestion / mutation / explorer / replay / parity / "
            "execution-realism / orchestration if wired. While OFF, "
            "the registry is a pure CRUD surface — no engine reads it."
        ),
    },
    {
        "name":    "MARKET_UNIVERSE_DEFAULT_TIER",
        "default": "candidate",
        "kind":    "str",
        "scope":   "market_universe",
        "intent":  (
            "Default tier for newly-registered symbols. Operators "
            "promote/demote per-row via /api/admin/market-universe/"
            "{symbol}/tier. Must be one of: active, candidate, dormant, "
            "experimental, regime_activated."
        ),
    },
    {
        "name":    "MARKET_UNIVERSE_AUTO_INGEST",
        "default": False,
        "kind":    "bool",
        "scope":   "market_universe",
        "intent":  (
            "Future hook: when ON, ingestion runners would auto-pull "
            "data for tier=active symbols in the registry. Today: "
            "documentation-only; no ingestion runner consults this flag."
        ),
    },
    {
        "name":    "MARKET_UNIVERSE_AUDIT_TTL_DAYS",
        "default": 90,
        "kind":    "int",
        "scope":   "market_universe",
        "intent":  (
            "R0 — TTL retention for the market_universe_audit collection "
            "in days. 90 days approved (decision §7.3). Index is created "
            "by engines.db_indexes.ensure_indexes; changing this value "
            "retunes the index on next startup."
        ),
    },

    # ─── P1.4 — Dormant HTF parity validation ──────────────────────
    # Audit doc §3.1, §3.2: today's interpreter synthesises HTF_EMA
    # via a SUBSAMPLE of the LTF close series (cheap, deterministic,
    # but APPROXIMATE relative to cTrader's true MarketData.GetBars
    # (htfTimeframe) feed). P1.4 introduces a dormant validator that
    # compares the subsample path against a properly TIME-BUCKETED
    # HTF synthesis and quantifies the divergence. NO production
    # wiring; flag-gated. Default OFF — preserves current behavior
    # byte-for-byte. Activation requires this flag flip AND a
    # deliberate future code change to wire a call-site (most likely
    # into cbot_parity.sign_off_parity once soak evidence has
    # accumulated, as a precursor to P1.5 hard-gate promotion).
    {
        "name":    "ENABLE_HTF_PARITY_VALIDATION",
        "default": False,
        "kind":    "bool",
        "scope":   "htf_parity",
        "intent":  (
            "Enable the dormant HTF parity validator "
            "(engines.htf_parity). When OFF the module's "
            "validate_htf_parity() is callable but no production "
            "code path consults it. Activation requires both this "
            "flag AND a future code change to wire a call-site."
        ),
    },
    {
        "name":    "HTF_PARITY_MAX_DIVERGENCE_PCT",
        "default": 5.0,
        "kind":    "float",
        "scope":   "htf_parity",
        "intent":  (
            "Tolerance (percent of compared bars) for the "
            "WITHIN_TOLERANCE verdict band. Above this value the "
            "verdict steps down to DIVERGENT. Operator-tunable; "
            "consumed only by engines.htf_parity.validate_htf_parity()."
        ),
    },

    # ─── P1.5 — Parity certification + dormant hard-gate primitive ─
    # Audit doc §9 + PRD §13: P1.5 promotes trade-parity (P1.3) and
    # HTF-parity (P1.4) from advisory metadata to HARD GATE on every
    # cBot export. The promotion decision must be evidence-based —
    # the operator needs an aggregator over recent sign-offs to see
    # the would-be hard-gate pass-rate before flipping anything. The
    # primitive (engines.parity_certification.would_pass_hard_gate)
    # is dormant; the existing engines.cbot_parity.is_passed remains
    # the production semantic. Activation requires BOTH a flag flip
    # AND a separately-reviewed code change in cbot_parity.py.
    {
        "name":    "ENABLE_TRADE_PARITY_HARD_GATE",
        "default": False,
        "kind":    "bool",
        "scope":   "cbot_parity",
        "intent":  (
            "Mark that trade-parity (P1.3 advisory) would be required "
            "by the cBot export hard gate if wired. While OFF, "
            "engines.cbot_parity.is_passed() continues to drive every "
            "caller using SIGNAL parity only. Activation requires "
            "this flag flip AND a single-file change in cbot_parity.py."
        ),
    },
    {
        "name":    "ENABLE_HTF_PARITY_HARD_GATE",
        "default": False,
        "kind":    "bool",
        "scope":   "cbot_parity",
        "intent":  (
            "Mark that HTF-parity (P1.4 advisory) would be required "
            "by the cBot export hard gate if wired. While OFF, "
            "engines.cbot_parity.is_passed() continues to drive every "
            "caller using SIGNAL parity only."
        ),
    },
    {
        "name":    "PARITY_CERTIFICATION_MIN_SAMPLES",
        "default": 30,
        "kind":    "int",
        "scope":   "cbot_parity",
        "intent":  (
            "Minimum sign-off sample size before the promotion-"
            "readiness verdict can leave NEEDS_MORE_EVIDENCE. "
            "Operator-tunable; consumed only by "
            "engines.parity_certification.evaluate_promotion_readiness."
        ),
    },
    {
        "name":    "PARITY_CERTIFICATION_MIN_PASS_RATE",
        "default": 0.95,
        "kind":    "float",
        "scope":   "cbot_parity",
        "intent":  (
            "Minimum would-pass-hard-gate rate (0..1) before the "
            "promotion-readiness verdict can return PROMOTABLE. "
            "Operator-tunable; consumed only by "
            "engines.parity_certification.evaluate_promotion_readiness."
        ),
    },

    # ─── Operational hygiene (always active, just toggleable) ──────
    {
        "name":    "AUDIT_LOG_RETENTION_DAYS",
        "default": 90,
        "kind":    "int",
        "scope":   "audit_log",
        "intent":  (
            "TTL window for audit_log.ts_dt-bearing docs. Mongo reaper "
            "deletes older. Set to 0 to disable TTL (not recommended)."
        ),
    },

    # ─── MB-9 Phase 2.B — Multi-Runner Routing + Token Rotation +
    #     Parity-Drift Dashboard + Multi-Account Fan-out.
    #
    # All six flags ship default-OFF (or to the value that makes the
    # Phase 1 single-runner / single-account behaviour byte-identical).
    # Engines under engines/runner_router.py, runner_token_rotator.py,
    # parity_drift_view.py, multi_account_envelope.py read these via
    # os.environ.get() with matching defaults — registration here is
    # what exposes them on /api/latent/feature-flags so the operator
    # can audit the live values.
    # ───────────────────────────────────────────────────────────────
    {
        "name":    "RUNNER_AFFINITY_POLICY",
        "default": "sticky_pair_tf",
        "kind":    "str",
        "scope":   "mb9_phase2",
        "intent":  (
            "Active routing policy for engines.runner_router. Valid: "
            "sticky_pair_tf (default) / least_busy / round_robin / "
            "local_only. Single-runner fleets always degenerate to "
            "the single registered runner — byte-identical to Phase 1."
        ),
    },
    {
        "name":    "RUNNER_TOKEN_GRACE_SEC",
        "default": 300,
        "kind":    "int",
        "scope":   "mb9_phase2",
        "intent":  (
            "Grace window (seconds) during which BOTH old and new "
            "runner bearer tokens authenticate after a rotation. "
            "Minimum 30s; default 300s (5 minutes). Consumed by "
            "engines.runner_token_rotator.validate_with_grace."
        ),
    },
    {
        "name":    "RUNNER_ROTATE_INTERVAL_SEC",
        "default": 2592000,
        "kind":    "int",
        "scope":   "mb9_phase2",
        "intent":  (
            "Auto-rotation cadence (seconds). Default 30 days "
            "(2,592,000s). Only consulted when RUNNER_AUTO_ROTATE is "
            "also true; manual rotation via POST /master-bot/runners/"
            "{id}/rotate-token is always available regardless."
        ),
    },
    {
        "name":    "RUNNER_AUTO_ROTATE",
        "default": False,
        "kind":    "bool",
        "scope":   "mb9_phase2",
        "intent":  (
            "Master switch for the auto-rotation scheduler. Default "
            "OFF — no scheduler ticks. Manual rotation is always "
            "available. The scheduler hook lands in a future wiring "
            "pass and is unwired in Phase 2.B."
        ),
        "gates":   [],
    },
    {
        "name":    "RUNNER_PARITY_DRIFT_WINDOW_DAYS",
        "default": 7,
        "kind":    "int",
        "scope":   "mb9_phase2",
        "intent":  (
            "Trailing window (days) for parity-drift aggregation. "
            "Default 7. Consumed by engines.parity_drift_view; "
            "deployments with <2 sign-offs in window return "
            "decision=insufficient_data (honest refusal)."
        ),
    },
    {
        "name":    "RUNNER_MULTI_ACCOUNT_ENABLED",
        "default": False,
        "kind":    "bool",
        "scope":   "mb9_phase2",
        "intent":  (
            "Master switch for multi-account fan-out per runner. "
            "Default OFF — engines.multi_account_envelope.list_accounts "
            "returns a synthetic legacy single-account row so "
            "downstream poll-envelope assembly stays byte-identical "
            "to Phase 1. Operator may pre-seed account rows via the "
            "API while the flag is off (CRUD is always available)."
        ),
    },
    {
        "name":    "RUNNER_AUTO_ROUTE_AT_REGISTER",
        "default": False,
        "kind":    "bool",
        "scope":   "mb9_phase2",
        "intent":  (
            "MB-9 Phase 2.C consumer gate. When False (default), "
            "master_bot_deployment.register_deployment stores "
            "runner_id=None verbatim when the operator omitted it — "
            "byte-identical to Phase 1. When True, the consumer "
            "consults engines.runner_router.route() to pick a runner. "
            "Router refusal (no_alive_runner_in_fleet) is honoured "
            "and runner_id remains None — never silently mis-assigned."
        ),
    },
)


def _parse(spec: Dict[str, Any], raw: str | None) -> Any:
    if raw is None or raw == "":
        return spec["default"]
    kind = spec["kind"]
    try:
        if kind == "bool":
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if kind == "int":
            return int(float(raw))
        if kind == "float":
            return float(raw)
        return str(raw)
    except (TypeError, ValueError):
        logger.warning(
            "[feature_flags] %s: invalid %s value %r — using default %r",
            spec["name"], kind, raw, spec["default"],
        )
        return spec["default"]


def flag(name: str) -> Any:
    """Return the live (env-overridden) value for a flag.

    Raises KeyError if the flag is not registered — callers must
    declare every flag they use in `_FLAG_SPECS` so the audit surface
    stays complete.
    """
    for spec in _FLAG_SPECS:
        if spec["name"] == name:
            return _parse(spec, os.environ.get(name))
    raise KeyError(
        f"feature_flag {name!r} not registered — add it to "
        "engines.feature_flags._FLAG_SPECS"
    )


def all_flags() -> Dict[str, Dict[str, Any]]:
    """Return a structured snapshot of every flag's resolved value.

    Used by the diagnostic endpoint and the startup logger. Suitable
    for direct JSON serialization.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for spec in _FLAG_SPECS:
        resolved = _parse(spec, os.environ.get(spec["name"]))
        out[spec["name"]] = {
            "value":       resolved,
            "default":     spec["default"],
            "is_dormant":  resolved == spec["default"],
            "is_overridden": resolved != spec["default"],
            "kind":        spec["kind"],
            "scope":       spec["scope"],
            "intent":      spec["intent"],
            "gates":       spec.get("gates", []),
        }
    return out


def active_flags() -> Dict[str, Any]:
    """Return only the flags whose live value differs from the default.

    The audit "what is active right now" line.
    """
    return {
        name: meta["value"]
        for name, meta in all_flags().items()
        if meta["is_overridden"]
    }


def scope_index() -> Dict[str, list]:
    """Group flag names by scope (subsystem). Useful for diagnostics."""
    out: Dict[str, list] = {}
    for spec in _FLAG_SPECS:
        out.setdefault(spec["scope"], []).append(spec["name"])
    return out


def log_at_startup(target_logger: logging.Logger | None = None) -> None:
    """Emit a single readable log line summarising overridden flags.

    Call from a FastAPI startup hook so operators see at-a-glance
    which latent capabilities have been activated for this boot.
    """
    lg = target_logger or logger
    active = active_flags()
    if not active:
        lg.info(
            "[feature_flags] all %d flags at conservative defaults "
            "(no latent capabilities activated)",
            len(_FLAG_SPECS),
        )
        return
    lg.info(
        "[feature_flags] %d/%d flags overridden — active: %s",
        len(active), len(_FLAG_SPECS),
        ", ".join(f"{k}={v}" for k, v in active.items()),
    )


def iter_specs() -> Iterable[Dict[str, Any]]:
    """Read-only iterator over the registry (for docs/tests)."""
    return iter(_FLAG_SPECS)


# ─────────────────────────────────────────────────────────────────────
# Boot audit emitter (Phase 4/5 — institutional activation timeline).
#
# Every backend / factory_runner boot writes ONE row to `audit_log`
# summarising which latent capabilities are overridden at startup.
# Combined with the 90d TTL on `audit_log.ts_dt`, this gives the
# operator a queryable rolling activation timeline — answering
# questions like "when did ENABLE_AGING_PENALTY first go live?"
# without needing external journals.
#
# The row uses `engines.audit_log_writer.write_event` so `ts_dt` is
# always populated (TTL-reapable). Never raises — observability is
# best-effort, never source-of-truth.
# ─────────────────────────────────────────────────────────────────────

async def emit_boot_audit_event(
    source: str = "server",
    *,
    extra: Dict[str, Any] | None = None,
) -> bool:
    """Write ONE `audit_log` row describing the live latent-capability
    activation state at boot.

    Args
    ----
    source : free-text process identifier (e.g. "server", "factory_runner").
             Stamped into the audit row so multi-process boots stay
             distinguishable in the timeline.
    extra  : optional caller-supplied fields to attach (PID is auto).

    Returns
    -------
    True on persistence success, False otherwise. Never raises.
    """
    try:
        import os
        # Local import to avoid a top-level dependency cycle
        # (audit_log_writer → db → motor) at module import time.
        from engines.audit_log_writer import write_event
        snapshot = all_flags()
        active = {
            name: meta["value"]
            for name, meta in snapshot.items() if meta["is_overridden"]
        }
        return await write_event(
            "latent_capability:boot_state",
            phase="latent-os",
            source=source,
            process_pid=os.getpid(),
            flag_count=len(snapshot),
            overridden_count=len(active),
            all_dormant=(not active),
            active_overrides=active,
            scopes=sorted(scope_index().keys()),
            **(extra or {}),
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[feature_flags] emit_boot_audit_event failed: %s", e)
        return False


def _compute_override_diff(
    prev: Dict[str, Any],
    curr: Dict[str, Any],
) -> Dict[str, Any]:
    """Pure helper — return a structured diff between two override dicts.

    Shape:
        {
            "added":   {flag: new_value, ...},   # in curr, not in prev
            "removed": {flag: prev_value, ...},  # in prev, not in curr
            "changed": {flag: {"from": p, "to": c}, ...},  # in both, ≠
        }
    """
    added: Dict[str, Any] = {}
    removed: Dict[str, Any] = {}
    changed: Dict[str, Any] = {}
    for k in set(prev) | set(curr):
        if k in curr and k not in prev:
            added[k] = curr[k]
        elif k in prev and k not in curr:
            removed[k] = prev[k]
        elif prev[k] != curr[k]:
            changed[k] = {"from": prev[k], "to": curr[k]}
    return {"added": added, "removed": removed, "changed": changed}


def _is_empty_diff(diff: Dict[str, Any]) -> bool:
    return not (diff.get("added") or diff.get("removed") or diff.get("changed"))


async def emit_override_diff_event(
    source: str = "server",
    *,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Write a `latent_capability:override_diff` row IF the current
    active_overrides differ from the most recent previous boot-state
    row in `audit_log`.

    Designed to run RIGHT AFTER `emit_boot_audit_event(source=...)`.
    The new boot_state row this boot just wrote is the most recent;
    we look at the SECOND-most-recent to find the prior baseline.

    Returns a structured payload describing what was emitted (or why
    not). Never raises.
        {
          "emitted":         bool,
          "reason":          "first_boot" | "no_change" | "diff_written" | "error",
          "diff":            {...} | None,
          "previous_boot":   {ts, source, process_pid} | None,
          "current_overrides": {...},
        }
    """
    out: Dict[str, Any] = {
        "emitted":           False,
        "reason":            "error",
        "diff":              None,
        "previous_boot":     None,
        "current_overrides": {},
    }
    try:
        import os
        from engines.db import get_db
        from engines.audit_log_writer import write_event

        snapshot = all_flags()
        current_overrides = {
            name: meta["value"]
            for name, meta in snapshot.items() if meta["is_overridden"]
        }
        out["current_overrides"] = current_overrides

        # Find the second-most-recent boot_state row. The most recent
        # is the one this same boot just wrote.
        db = get_db()
        cur = db["audit_log"].find(
            {"event": "latent_capability:boot_state"},
            {
                "_id": 0, "ts": 1, "ts_dt": 1, "source": 1,
                "process_pid": 1, "active_overrides": 1,
            },
        ).sort("ts_dt", -1).limit(2)
        rows = [d async for d in cur]
        if len(rows) < 2:
            out["reason"] = "first_boot"
            return out

        # rows[0] = current boot; rows[1] = previous boot
        prev = rows[1]
        prev_overrides = prev.get("active_overrides") or {}
        diff = _compute_override_diff(prev_overrides, current_overrides)

        out["previous_boot"] = {
            "ts":          prev.get("ts"),
            "source":      prev.get("source"),
            "process_pid": prev.get("process_pid"),
        }
        out["diff"] = diff

        if _is_empty_diff(diff):
            out["reason"] = "no_change"
            return out

        ok = await write_event(
            "latent_capability:override_diff",
            phase="latent-os",
            source=source,
            process_pid=os.getpid(),
            added=diff["added"],
            removed=diff["removed"],
            changed=diff["changed"],
            n_added=len(diff["added"]),
            n_removed=len(diff["removed"]),
            n_changed=len(diff["changed"]),
            previous_boot_ts=prev.get("ts"),
            previous_boot_source=prev.get("source"),
            previous_boot_pid=prev.get("process_pid"),
            **(extra or {}),
        )
        out["emitted"] = bool(ok)
        out["reason"] = "diff_written" if ok else "error"
        return out
    except Exception as e:                                  # pragma: no cover
        logger.debug("[feature_flags] emit_override_diff_event failed: %s", e)
        out["reason"] = "error"
        out["error"] = str(e)[:200]
        return out
