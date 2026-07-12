"""
Phase D.1 — Sibling factory runner.

This is a SEPARATE Python process (NOT part of the uvicorn worker)
that owns the long-running scheduler authority and CPU-heavy
orchestration work. The FastAPI workers stay free for HTTP.

Activation:
  * Set `FACTORY_RUNNER_OWNS_SCHEDULERS=true` in `backend/.env`
  * Start the process via supervisor (separate program entry) OR:
      cd /app/backend && python factory_runner.py

When `FACTORY_RUNNER_OWNS_SCHEDULERS=true`, the uvicorn workers'
`server.py` startup hooks short-circuit their scheduler restoration —
preventing duplicate schedulers across worker + runner.

When `FACTORY_RUNNER_OWNS_SCHEDULERS=false` (default), the runner
exits immediately on startup so it can be left in the supervisor
config and toggled by env flag alone.

Discipline:
  * Operator-flag gated — defaults preserve current single-worker
    behavior.
  * Reuses the existing `engines.orchestrator_scheduler.restore_if_enabled`
    + `engines.auto_scheduler.restore_if_enabled` so all scheduler
    state machinery (persisted enable flag, BI5 weekly job, etc.)
    is identical to what FastAPI used to run.
  * Audit-logged at every lifecycle event so operators can verify
    "the sibling is alive" from Mongo even when the runner has no
    HTTP surface.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

# Load env BEFORE importing any engine that reads os.environ at import.
load_dotenv()

# Honour the platform flag — same parser semantics as elsewhere.
def _flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [factory_runner] %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def _audit(event: str, details: dict) -> None:
    try:
        from engines.db import get_db
        now = datetime.now(timezone.utc)
        await get_db()["audit_log"].insert_one({
            "ts": now.isoformat(),
            # Phase 2 P2.8.b — BSON Date companion enables TTL reaper
            # on `audit_log.ts_dt` (90d default via
            # AUDIT_LOG_RETENTION_DAYS).
            "ts_dt": now,
            "event": f"factory_runner:{event}",
            "phase": "D.1",
            **details,
        })
    except Exception as e:                                  # pragma: no cover
        logger.warning("audit failed: %s", e)


async def _main() -> int:
    if not _flag("FACTORY_RUNNER_OWNS_SCHEDULERS", default=False):
        logger.info(
            "FACTORY_RUNNER_OWNS_SCHEDULERS=false — sibling runner is "
            "dormant. Set the env var to true in backend/.env to "
            "activate. Exiting cleanly."
        )
        return 0

    await _audit("startup", {"pid": os.getpid()})
    logger.info("sibling runner ACTIVE — pid=%d", os.getpid())

    # Phase 4/5 — write the latent-capability boot state row so the
    # factory_runner's activation timeline lives in the same audit
    # surface as the FastAPI server's. Best-effort.
    try:
        from engines.feature_flags import (
            emit_boot_audit_event,
            emit_override_diff_event,
            log_at_startup,
        )
        log_at_startup(logger)
        await emit_boot_audit_event(source="factory_runner")
        # Forensic activation-state transition row (observational-only,
        # best-effort). Compares against the most recent prior
        # boot_state row in `audit_log`.
        await emit_override_diff_event(source="factory_runner")
    except Exception as e:                                  # pragma: no cover
        logger.debug("feature_flags boot emission failed: %s", e)

    # Restore the persisted schedulers (orchestrator + auto-discovery).
    # The orchestrator scheduler hosts the BI5 weekly sweep too — so
    # restoring it brings every persisted background job online here.
    try:
        from engines.orchestrator_scheduler import (
            restore_if_enabled as restore_orch,
        )
        await restore_orch()
        logger.info("orchestrator scheduler restore complete")
    except Exception:
        logger.exception("orchestrator scheduler restore failed")

    try:
        from engines.auto_scheduler import (
            restore_if_enabled as restore_auto,
        )
        await restore_auto()
        logger.info("auto scheduler restore complete")
    except Exception:
        logger.exception("auto scheduler restore failed")

    try:
        from data_engine.auto_data_maintainer import (
            restore_if_enabled as restore_dm,
        )
        await restore_dm()
        logger.info("auto data maintainer restore complete")
    except Exception:
        logger.exception("auto data maintainer restore failed")

    # ── Keep-alive loop with graceful shutdown ────────────────────
    stop_event = asyncio.Event()

    def _stop(signame):
        logger.info("received %s — shutting down", signame)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: _stop(s))
        except (NotImplementedError, RuntimeError):       # pragma: no cover
            # Windows / nested event loops — fall back to default behavior.
            pass

    # Idle heartbeat (audit ping every 5 minutes so operators can
    # verify the runner is alive even with no schedulers running).
    heartbeat_interval_sec = int(
        os.environ.get("FACTORY_RUNNER_HEARTBEAT_SEC") or 300
    )
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=heartbeat_interval_sec,
            )
        except asyncio.TimeoutError:
            try:
                await _audit("heartbeat", {"pid": os.getpid()})
            except Exception:
                pass

    await _audit("shutdown", {"pid": os.getpid()})
    logger.info("sibling runner stopped cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
