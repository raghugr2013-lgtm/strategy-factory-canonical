"""
Factory Supervisor FS-P1.2 — Worker runtime.

A *pluggable* worker registry. Each worker handles ONE workload-class
*family* and is fronted by a small async `run(envelope) -> WorkerResult`
contract. The defer-queue background poller pulls due rows, looks up
the appropriate worker by `workload_class`, and dispatches.

Discipline:
  * **Default OFF.** `FS_ENABLE_DEFER_WORKER=false` ⇒ `start()` is a
    no-op; `claim_and_run_once()` returns immediately. Legacy callers
    unaffected.
  * **Provider-neutral / transport-neutral.** Local execution today
    is a stub (`run()` returns `WorkerResult(outcome="completed",
    skipped="local_runtime_stub_FS_P1_2")`). Real worker bodies land
    in FS-P1.5+. The contract is what FS-P1.2 ships; the bodies are
    additive.
  * **Workers register, never hardcode.** Future workers add ONE
    entry to `WORKER_REGISTRY` and define a `run()` coroutine —
    no other module touches the worker runtime.
  * **Multi-node routing.** When the workload's `assigned_host` is
    non-local, the worker delegates to `remote_transport.resolve_transport()`
    (transport-neutral) — today that's the noop/http stub.

Worker classes (registered in FS-P1.2):
    local_executor              ACTIVE-stub; "completed" outcome
    multi_node_executor         registered, inactive; falls back to local stub
    ctrader_telemetry_worker    registered, inactive
    auto_learning_worker        registered, inactive (Auto-Learning gate OFF)
    notification_center_worker  registered, inactive (NC tasks)
    copilot_context_refresh     registered, inactive (Stage-2 Copilot)

Public surface:
    WorkerResult                — frozen dataclass
    Worker                      — ABC
    WORKER_REGISTRY             — dict[name → metadata]
    ALL_WORKER_NAMES
    is_enabled()
    worker_id()                 — stable per-process id
    pick_worker_for(workload_class) → Worker
    claim_and_run_once(batch=8) → list[result_dict]
    worker_manifest()           → list[dict]   (Copilot input)
"""
from __future__ import annotations

import abc
import logging
import os
import socket
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.factory_supervisor import (
    defer_queue,
    remote_transport,
)

logger = logging.getLogger(__name__)


# ─── Stable per-process worker id ────────────────────────────────────

_WORKER_ID: Optional[str] = None


def worker_id() -> str:
    """A stable identifier for this Python process. Used by claim()."""
    global _WORKER_ID
    if _WORKER_ID is None:
        try:
            host = socket.gethostname() or "host"
        except Exception:                                      # pragma: no cover
            host = "host"
        _WORKER_ID = f"{host}:pid{os.getpid()}:{uuid.uuid4().hex[:8]}"
    return _WORKER_ID


# ─── Worker result + ABC ─────────────────────────────────────────────

@dataclass
class WorkerResult:
    """Outcome of one worker.run(envelope) invocation."""
    outcome:    str                  # 'completed' | 'retry' | 'failed'
    reason:     str = ""
    detail:     Dict[str, Any] = field(default_factory=dict)
    soft_defer: bool = False         # True ⇒ defer-queue keeps row queued

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Worker(abc.ABC):
    """One worker per workload-class family. Provider/transport neutral."""

    name: str = "abstract"
    active: bool = False

    @abc.abstractmethod
    async def run(self, envelope: Dict[str, Any]) -> WorkerResult: ...


# ─── Stub worker bodies (FS-P1.2 ships interface only) ───────────────

class _StubWorker(Worker):
    """Generic stub that returns 'completed' with a phase marker."""
    name = "stub"
    active = False

    async def run(self, envelope: Dict[str, Any]) -> WorkerResult:
        return WorkerResult(
            outcome="completed", reason=f"{self.name}_stub_FS_P1_2",
            detail={"workload_id": envelope.get("workload_id"),
                    "workload_class": envelope.get("workload_class")},
        )


class LocalExecutorWorker(_StubWorker):
    """Active in FS-P1.2 — completes the row immediately as a stub.
    Real local execution wiring lands in FS-P1.5+ (when the dispatcher
    starts owning live execution rather than recording intent)."""
    name = "local_executor"
    active = True


class MultiNodeExecutorWorker(Worker):
    """Delegates to the resolved RemoteTransport. Inactive in FS-P1.2."""
    name = "multi_node_executor"
    active = False

    async def run(self, envelope: Dict[str, Any]) -> WorkerResult:
        target_host = envelope.get("assigned_host")
        transport = remote_transport.resolve_transport()
        res = await transport.submit(envelope, target_host=target_host)
        if res.accepted:
            return WorkerResult(
                outcome="completed", reason="remote_accepted",
                detail=res.to_dict(),
            )
        if res.soft_defer:
            return WorkerResult(
                outcome="retry", reason=res.error or "remote_soft_defer",
                soft_defer=True, detail=res.to_dict(),
            )
        return WorkerResult(
            outcome="failed", reason=res.error or "remote_refused",
            detail=res.to_dict(),
        )


class CTraderTelemetryWorker(_StubWorker):
    name = "ctrader_telemetry_worker"
    active = False


class AutoLearningWorker(_StubWorker):
    name = "auto_learning_worker"
    active = False


class NotificationCenterWorker(_StubWorker):
    name = "notification_center_worker"
    active = False


class CopilotContextRefreshWorker(_StubWorker):
    name = "copilot_context_refresh"
    active = False


# ─── Registry ────────────────────────────────────────────────────────

WORKER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "local_executor": {
        "factory": LocalExecutorWorker,
        "active":  True,
        "handles": "*",
        "intent":  "Active local-execution stub (FS-P1.2). Real body in FS-P1.5+.",
    },
    "multi_node_executor": {
        "factory": MultiNodeExecutorWorker,
        "active":  False,
        "handles": "*remote*",
        "intent":  "Routes envelopes to RemoteTransport. Provider/transport neutral.",
    },
    "ctrader_telemetry_worker": {
        "factory": CTraderTelemetryWorker,
        "active":  False,
        "handles": "ctrader_telemetry / deployment-class workloads",
        "intent":  "Consumes telemetry-class envelopes from cTrader runners.",
    },
    "auto_learning_worker": {
        "factory": AutoLearningWorker,
        "active":  False,
        "handles": "auto_learning_* workloads",
        "intent":  "Drains Auto-Learning queue (Auto-Learning gate strictly OFF).",
    },
    "notification_center_worker": {
        "factory": NotificationCenterWorker,
        "active":  False,
        "handles": "notification_center / NC fan-out workloads",
        "intent":  "Materialises notifications + multi-channel deliveries.",
    },
    "copilot_context_refresh": {
        "factory": CopilotContextRefreshWorker,
        "active":  False,
        "handles": "copilot_context_refresh workloads",
        "intent":  "Periodic CopilotContext refresh — provider-agnostic.",
    },
}

ALL_WORKER_NAMES = tuple(WORKER_REGISTRY.keys())


def is_enabled() -> bool:
    try:
        from engines.feature_flags import flag
        return (
            bool(flag("ENABLE_FACTORY_SUPERVISOR"))
            and bool(flag("FS_ENABLE_DEFER_QUEUE"))
            and bool(flag("FS_ENABLE_DEFER_WORKER"))
        )
    except Exception:                                          # pragma: no cover
        return False


def pick_worker_for(workload_class: str) -> Worker:
    """Class → worker mapping. Today: everything goes to local_executor."""
    if not workload_class:
        return LocalExecutorWorker()
    # Heuristic: if envelope assigned_host implies remote, prefer
    # multi_node_executor when active. Otherwise default local.
    if WORKER_REGISTRY["multi_node_executor"]["active"]:
        # NOTE: caller checks `assigned_host`; we expose preference here.
        pass
    return LocalExecutorWorker()


def worker_manifest() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name, meta in WORKER_REGISTRY.items():
        out.append({
            "name":    name,
            "active":  bool(meta["active"]),
            "handles": meta["handles"],
            "intent":  meta["intent"],
        })
    return out


# ─── One-shot poll loop ──────────────────────────────────────────────

async def claim_and_run_once(batch: int = 8) -> List[Dict[str, Any]]:
    """Run a single pass: claim up to `batch` due rows, dispatch each
    to a worker, and update the defer queue.

    Returns a list of `{row_id, outcome, reason}` dicts. Never raises.
    """
    out: List[Dict[str, Any]] = []
    if not is_enabled():
        return out
    wid = worker_id()
    claimed = await defer_queue.claim_due(wid, batch=batch)
    for row in claimed:
        envelope = row.get("original_envelope") or {}
        wl_class = row.get("workload_class") or ""
        worker = pick_worker_for(wl_class)
        try:
            res = await worker.run(envelope)
        except Exception as e:                                 # pragma: no cover
            res = WorkerResult(
                outcome="failed", reason=f"worker_exception:{e}"[:200],
            )
        verdict_like = {
            "outcome": res.outcome,
            "reason":  res.reason,
            "detail":  res.detail,
        }
        row_id = row["row_id"]
        if res.outcome == "completed":
            await defer_queue.mark_completed(row_id, detail=res.detail)
        elif res.outcome == "failed":
            await defer_queue.mark_failed(
                row_id, reason=res.reason or "failed", detail=res.detail,
            )
        else:
            # "retry" / anything else → push back to queue with backoff.
            await defer_queue.mark_retry(row_id, verdict_like)
        out.append({
            "row_id":   row_id,
            "outcome":  res.outcome,
            "reason":   res.reason,
            "worker":   worker.name,
            "ts":       datetime.now(timezone.utc).isoformat(),
        })
    return out
