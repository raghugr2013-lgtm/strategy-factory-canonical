"""
Factory Supervisor — package surface.

Phase 1.0 shipped:
    * supervisor_lock        — single-leader cooperative lease.
    * fleet_registry         — multi-host capability + pressure snapshot.
    * supervisor_heartbeat   — verdict-band liveness (reuses
                                factory_runner_heartbeat vocabulary).
    * supervisor_events      — canonical supervisor event vocabulary
                                with bridge to scaling_events (P1.D)
                                AND notifications (Notification Center).

Phase 1.1 added:
    * workload               — Workload envelope dataclass with the
                                frozen FS-P1.1 metadata contract.
    * routing_policy         — Pluggable policy registry (local_only
                                ACTIVE; 5 multi-host policies REGISTERED
                                but INACTIVE, fall back to local_only).
    * submission_dispatcher  — Central submit pipeline composing
                                routing_policy + admission_controller +
                                supervisor_events. Persists to the
                                `factory_supervisor_submissions` collection.

Phase 1.2 added:
    * defer_queue            — Single source of truth for postponed
                                workloads. Persists original envelope +
                                rationale + retry schedule to the
                                `factory_supervisor_defer_queue` collection.
    * remote_transport       — Provider/transport-neutral remote-submit
                                interface (HTTP stub today; gRPC / WS /
                                async-queue plug-ins land later with
                                ZERO call-site changes).
    * worker_runtime         — Pluggable worker registry (local_executor
                                ACTIVE-stub; 5 future workers REGISTERED
                                but INACTIVE). One-shot poll loop drains
                                due defer-queue rows.

Phase 1.3 added:
    * system_state_view      — Authoritative read model (read-only).
    * notification_center    — Read API + acknowledge/archive.
    * architect_advisor      — Next Recommended Action (advisory-only).
    * worker_scheduler       — Persistent asyncio sub-task registry.

Phase 1.4 added:
    * copilot_context        — Frozen Copilot-facing view of system_state_view.
    * recommendation_engine  — Rule-based recommendations (read-only).
    * eligibility_signals    — Per-feature readiness signals (read-only).
    * fag_proposals          — Feature Activation Governance pipeline
                                (Observe → Recommend → Notify → Approve →
                                Activate). Default OFF; activate() is admin-
                                only AND honours operator-directive vetoes.
    * copilot_operational    — Deterministic Operational Copilot
                                (NO LLM; answers 8 canonical questions).
    * copilot_advanced       — Advanced Intelligence Copilot — provider-
                                agnostic LLM shim. DORMANT by default;
                                no LLM SDK imported.
    * llm_adapter_base       — Provider-agnostic LLMAdapter ABC +
                                pluggable PROVIDER_REGISTRY.
    * auto_learning          — Auto-Learning Infrastructure (read-only).
                                Aggregates the four dormant learning
                                components (RoR, lifecycle_decay,
                                calibration_framework, execution_realism)
                                into a Recommendation/Insights surface.
                                NO loop, NO automatic mutation, NO automatic
                                activation. Default OFF; advisory only.

All modules remain DORMANT until `ENABLE_FACTORY_SUPERVISOR=true`
(plus per-feature sub-flags). Default OFF; rollback < 60 s.
"""
from __future__ import annotations

from engines.factory_supervisor import (
    architect_advisor,
    auto_learning,
    copilot_advanced,
    copilot_context,
    copilot_operational,
    defer_queue,
    eligibility_signals,
    fag_proposals,
    fleet_registry,
    llm_adapter_base,
    notification_center,
    recommendation_engine,
    remote_transport,
    routing_policy,
    submission_dispatcher,
    supervisor_events,
    supervisor_heartbeat,
    supervisor_lock,
    system_state_view,
    worker_runtime,
    worker_scheduler,
    workload,
)

__all__ = [
    "architect_advisor",
    "auto_learning",
    "copilot_advanced",
    "copilot_context",
    "copilot_operational",
    "defer_queue",
    "eligibility_signals",
    "fag_proposals",
    "fleet_registry",
    "llm_adapter_base",
    "notification_center",
    "recommendation_engine",
    "remote_transport",
    "routing_policy",
    "submission_dispatcher",
    "supervisor_events",
    "supervisor_heartbeat",
    "supervisor_lock",
    "system_state_view",
    "worker_runtime",
    "worker_scheduler",
    "workload",
]

