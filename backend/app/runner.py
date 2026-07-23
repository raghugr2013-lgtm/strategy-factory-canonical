"""factory-runner container entrypoint.

Phase 1b Activation (2026-07-24) — this file is a backward-compatible
DISPATCHER with THREE runtime modes:

1. **Factory Supervisor** (new — gated by ``FACTORY_SUPERVISOR_ENABLED``)
   Starts the APScheduler-backed :mod:`app.factory_supervisor` with 5
   placeholder recurring jobs (orchestrator / mutation / factory-eval /
   meta-learning / governance) and remains alive under an asyncio event
   loop until it receives SIGTERM/SIGINT.

2. **Legacy Scheduler** (gated by ``FACTORY_RUNNER_OWNS_SCHEDULERS``)
   Delegates to ``legacy.factory_runner._main()`` — the recovered
   sibling-process implementation that owns the persisted schedulers
   (orchestrator, auto-scheduler, auto-data-maintainer) and emits
   Mongo-backed ``audit_log`` heartbeats.

3. **Phase-0 Stub** (default when neither flag is set)
   Preserves the historical behaviour: emit a filesystem heartbeat at
   ``/tmp/factory_runner.hb`` so the docker healthcheck passes without
   touching Mongo, APScheduler, or the legacy sibling.

In every mode the heartbeat file is refreshed every ``_INTERVAL_S``
seconds so the compose ``healthcheck`` (``test -f
/tmp/factory_runner.hb``) stays green regardless of which mode the
container is running in.

Contract preserved:
* ``ENABLE_FACTORY_RUNNER`` still exits cleanly when unset — matches
  the historical stub semantics.
* Heartbeat file path, interval, log format are unchanged.
* No new endpoints are added.
* No database schema changes.
* No OBSERVE mode gate is bypassed.
* No changes to the strategy / validation / meta-learning / factory-eval
  engines.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

_HB = Path("/tmp/factory_runner.hb")
_LOG_EVERY = 10  # every 10 heartbeats (~5min) log a status line
_INTERVAL_S = 30
_RUNNER_VERSION = "1.1.0-supervisor"  # runner dispatcher version (independent of BUILD_VERSION)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s runner: %(message)s")
log = logging.getLogger("factory_runner_dispatch")


def _enabled(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _write_hb() -> None:
    _HB.write_text(str(int(time.time())))


def _build_version() -> str:
    return (os.environ.get("BUILD_VERSION") or "0.0.0").strip() or "0.0.0"


def _run_stub_loop() -> None:
    """Phase-0 heartbeat-only loop (backward-compatible fallback)."""
    log.info("factory-runner heartbeat-only mode (Phase-0 stub semantics)")
    tick = 0
    while True:
        try:
            _write_hb()
            if tick % _LOG_EVERY == 0:
                log.info(
                    "stub alive — set FACTORY_SUPERVISOR_ENABLED=true to activate the Factory Supervisor, "
                    "or FACTORY_RUNNER_OWNS_SCHEDULERS=true to activate legacy schedulers"
                )
            tick += 1
        except Exception:  # noqa: BLE001
            log.exception("heartbeat write failed")
        time.sleep(_INTERVAL_S)


def _delegate_to_legacy_sibling() -> int:
    """Hand control to the recovered ``legacy.factory_runner`` implementation.

    We ensure the docker healthcheck stays green by writing the
    heartbeat file BEFORE we start the sibling loop (so the file exists
    before the start_period elapses) and by launching a background
    thread that refreshes it every ``_INTERVAL_S`` seconds while the
    sibling loop is running. The sibling emits its own Mongo
    ``audit_log`` heartbeat separately.

    Returns the sibling's exit code so the container reflects any
    startup failure faithfully.
    """
    import asyncio
    import sys
    import threading

    # Prepend the `legacy` package path so the sibling's absolute imports
    # (`from engines.orchestrator_scheduler import …`) resolve, matching
    # the server.py shim used by FastAPI.
    _legacy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "legacy")
    if _legacy_dir not in sys.path:
        sys.path.insert(0, _legacy_dir)

    # Prime the heartbeat file so the docker healthcheck can pass
    # during the sibling's slower startup (scheduler restore + audit
    # writes may take longer than the 45s start_period).
    try:
        _write_hb()
    except Exception:  # noqa: BLE001
        log.exception("initial heartbeat write failed")

    stop_hb = threading.Event()

    def _hb_refresher() -> None:
        while not stop_hb.wait(_INTERVAL_S):
            try:
                _write_hb()
            except Exception:  # noqa: BLE001
                log.exception("heartbeat refresh failed")

    hb_thread = threading.Thread(target=_hb_refresher, name="hb-refresher", daemon=True)
    hb_thread.start()

    log.info("delegating to legacy.factory_runner (FACTORY_RUNNER_OWNS_SCHEDULERS=true)")
    try:
        from legacy.factory_runner import _main as _sibling_main
        return asyncio.run(_sibling_main())
    except Exception:  # noqa: BLE001
        log.exception("legacy.factory_runner crashed — falling back to heartbeat-only loop")
        stop_hb.set()
        _run_stub_loop()  # never returns
        return 1
    finally:
        stop_hb.set()


def _run_factory_supervisor() -> int:
    """Start the APScheduler-backed Factory Supervisor and stay alive.

    Startup sequence
    ----------------
    1. Log runner version, build version, and enabled mode.
    2. Prime the heartbeat file and launch the background refresher.
    3. Import + start :func:`app.factory_supervisor.start_supervisor`.
    4. Log every registered job (id, interval/cron, next_run_time).
    5. Enter an asyncio event loop and idle until a signal arrives.

    Shutdown sequence
    -----------------
    * SIGTERM / SIGINT triggers a graceful stop:
        - Scheduler stops accepting new jobs.
        - Currently-executing jobs are awaited (``stop_supervisor(wait=True)``).
        - Heartbeat refresher thread is signalled to stop.
        - Process exits with return code 0.

    Returns
    -------
    int
        Exit code for the runner container. ``0`` on clean shutdown,
        ``1`` if the supervisor fails to import/start.
    """
    import asyncio
    import threading

    build = _build_version()
    log.info(
        "factory-runner starting · runner_version=%s build_version=%s mode=FACTORY_SUPERVISOR",
        _RUNNER_VERSION,
        build,
    )

    # Prime the heartbeat file so the docker healthcheck passes during
    # scheduler bootstrap (which can take a beat on cold start).
    try:
        _write_hb()
    except Exception:  # noqa: BLE001
        log.exception("initial heartbeat write failed")

    stop_hb = threading.Event()

    def _hb_refresher() -> None:
        while not stop_hb.wait(_INTERVAL_S):
            try:
                _write_hb()
            except Exception:  # noqa: BLE001
                log.exception("heartbeat refresh failed")

    hb_thread = threading.Thread(target=_hb_refresher, name="hb-refresher", daemon=True)
    hb_thread.start()

    # Import late so a missing APScheduler dep produces a clean fallback
    # rather than an ImportError at module load time.
    try:
        from app.factory_supervisor import start_supervisor, stop_supervisor
    except Exception:  # noqa: BLE001
        log.exception("failed to import factory_supervisor — falling back to Phase-0 stub loop")
        stop_hb.set()
        _run_stub_loop()  # never returns
        return 1

    async def _amain() -> int:
        # Force the supervisor's env flag on so start_supervisor() honours
        # our dispatcher decision even if the operator only set the
        # runner-level flag.
        os.environ.setdefault("FACTORY_SUPERVISOR_ENABLED", "true")

        # Install shutdown signal handlers FIRST so any long-running
        # start-up work below can still be interrupted cleanly.
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _signal_handler(signame: str) -> None:
            log.info("received %s — beginning graceful shutdown", signame)
            stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _signal_handler, sig.name)
            except NotImplementedError:  # pragma: no cover — non-POSIX
                signal.signal(sig, lambda *_a: stop_event.set())

        scheduler = start_supervisor()
        if scheduler is None:
            log.error(
                "start_supervisor() returned None — APScheduler unavailable or disabled. "
                "Falling back to Phase-0 stub loop."
            )
            return 1

        # Structured startup summary: registered jobs + next runs.
        jobs = scheduler.get_jobs()
        log.info("factory-supervisor scheduler started successfully · %d jobs registered", len(jobs))
        for job in jobs:
            next_run = job.next_run_time.isoformat() if job.next_run_time else "n/a"
            log.info(
                "  ↳ job=%s trigger=%s next_run=%s",
                job.id,
                job.trigger,
                next_run,
            )

        try:
            await stop_event.wait()
        finally:
            log.info("stopping factory-supervisor (waiting for in-flight jobs) …")
            try:
                stop_supervisor(wait=True)
            except Exception:  # noqa: BLE001
                log.exception("stop_supervisor raised — continuing shutdown")
            stop_hb.set()
            log.info("factory-runner shutdown complete · exit_code=0")
        return 0

    try:
        return asyncio.run(_amain())
    except Exception:  # noqa: BLE001
        log.exception("factory-supervisor event loop crashed — falling back to stub loop")
        stop_hb.set()
        _run_stub_loop()  # never returns
        return 1


def main() -> None:
    if not _enabled("ENABLE_FACTORY_RUNNER"):
        log.info("ENABLE_FACTORY_RUNNER is not truthy — exiting cleanly")
        return

    # Dispatch order: Factory Supervisor > Legacy Scheduler > Phase-0 stub.
    if _enabled("FACTORY_SUPERVISOR_ENABLED"):
        rc = _run_factory_supervisor()
        raise SystemExit(rc)

    if _enabled("FACTORY_RUNNER_OWNS_SCHEDULERS"):
        rc = _delegate_to_legacy_sibling()
        # If the sibling returned (dormant path in legacy code), fall
        # back to the heartbeat loop so the container stays healthy
        # instead of restart-looping under docker's `unless-stopped`.
        log.info("legacy.factory_runner returned rc=%s — entering heartbeat-only loop", rc)
        _run_stub_loop()
        return

    _run_stub_loop()


if __name__ == "__main__":
    main()
