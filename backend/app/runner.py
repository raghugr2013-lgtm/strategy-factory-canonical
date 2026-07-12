"""factory-runner container entrypoint (Phase 0 stub).

Purpose:
  - Provide a boot-healthy sibling container from day one (per approved plan).
  - Emit a heartbeat file at /tmp/factory_runner.hb so the docker-compose
    healthcheck passes without needing a Mongo write path yet.
  - Later phases (specifically Phase 5 — Factory Supervisor) will replace this
    stub with the recovered `legacy.factory_runner:main()` invocation.

Behaviour:
  - If ENABLE_FACTORY_RUNNER != true, exits immediately (compose can still
    start the container in "disabled" mode without churn).
  - Otherwise, loops writing the heartbeat file every 30s and logs a
    "phase 0 stub — awaiting Phase 5 wiring" line every 5 minutes.
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
log = logging.getLogger("factory_runner_stub")


def _enabled() -> bool:
    raw = (os.environ.get("ENABLE_FACTORY_RUNNER") or "").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")


def _write_hb() -> None:
    _HB.write_text(str(int(time.time())))


def main() -> None:
    if not _enabled():
        log.info("ENABLE_FACTORY_RUNNER is not truthy — exiting cleanly")
        return
    log.info("factory-runner stub starting (Phase 0 — no APScheduler jobs yet)")
    tick = 0
    while True:
        try:
            _write_hb()
            if tick % _LOG_EVERY == 0:
                log.info("phase 0 stub alive — awaiting Phase 5 (Factory Supervisor) wiring")
            tick += 1
        except Exception:  # noqa: BLE001
            log.exception("heartbeat write failed")
        time.sleep(_INTERVAL_S)


if __name__ == "__main__":
    main()
