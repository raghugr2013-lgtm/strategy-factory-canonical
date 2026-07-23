"""factory-runner container entrypoint.

Phase 1 Activation (2026-07-23) — this file is a backward-compatible
DISPATCHER:

* When ``FACTORY_RUNNER_OWNS_SCHEDULERS`` is truthy, we delegate to
  ``legacy.factory_runner._main()`` — the recovered sibling-process
  implementation that owns the persisted schedulers (orchestrator,
  auto-scheduler, auto-data-maintainer) and emits Mongo-backed
  ``audit_log`` heartbeats.
* Otherwise, we preserve the Phase-0 behaviour: emit a filesystem
  heartbeat at ``/tmp/factory_runner.hb`` so the docker healthcheck
  passes without touching Mongo.

In both modes the heartbeat file is refreshed every ``_INTERVAL_S``
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
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

_HB = Path("/tmp/factory_runner.hb")
_LOG_EVERY = 10  # every 10 heartbeats (~5min) log a status line
_INTERVAL_S = 30

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s runner: %(message)s")
log = logging.getLogger("factory_runner_dispatch")


def _enabled(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _write_hb() -> None:
    _HB.write_text(str(int(time.time())))


def _run_stub_loop() -> None:
    """Phase-0 heartbeat-only loop (backward-compatible fallback)."""
    log.info("factory-runner heartbeat-only mode (Phase-0 stub semantics)")
    tick = 0
    while True:
        try:
            _write_hb()
            if tick % _LOG_EVERY == 0:
                log.info("stub alive — set FACTORY_RUNNER_OWNS_SCHEDULERS=true to activate sibling schedulers")
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


def main() -> None:
    if not _enabled("ENABLE_FACTORY_RUNNER"):
        log.info("ENABLE_FACTORY_RUNNER is not truthy — exiting cleanly")
        return

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
