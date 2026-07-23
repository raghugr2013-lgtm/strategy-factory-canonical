# Strategy Factory Canonical — PRD

_Last updated: 2026-07-23_

## Original Problem Statement
Manage the deployment architecture of the "Strategy Factory Canonical" project
and expose existing backend capabilities through the frontend without
introducing new backend API functionality (Backend API is under a strict
**Feature Freeze**).

## Current Focus (Phase 1b)
Wire a production-ready `FactorySupervisor` (APScheduler AsyncIOScheduler)
into `backend/app/runner.py` with **5 recurring placeholder jobs** and clean
startup/shutdown, without touching any HTTP API, DB schema, engine, or the
frontend.

## Runtime Modes (backend/app/runner.py)
Dispatch order, preserved for backward compatibility:

1. **Factory Supervisor** — `FACTORY_SUPERVISOR_ENABLED=true`
   APScheduler-backed. 5 placeholder jobs, structured JSON logs,
   SIGTERM/SIGINT → `stop_supervisor(wait=True)`, exit 0.
2. **Legacy Scheduler** — `FACTORY_RUNNER_OWNS_SCHEDULERS=true`
   Delegates to `legacy.factory_runner._main()` (Mongo-backed audit heartbeats).
3. **Phase-0 Stub** — default when neither flag is set. Writes only the
   filesystem heartbeat at `/tmp/factory_runner.hb`.

## Scheduled Placeholder Jobs
| Job            | Trigger (default)        | Env override                     |
| -------------- | ------------------------ | -------------------------------- |
| orchestrator   | interval, every 1 min    | `SUPERVISOR_ORCHESTRATOR_CRON`   |
| mutation       | interval, every 15 min   | `SUPERVISOR_MUTATION_CRON`       |
| factory_eval   | interval, every 1 hour   | `SUPERVISOR_FACTORY_EVAL_CRON`   |
| meta_learning  | interval, every 6 hours  | `SUPERVISOR_META_LEARNING_CRON`  |
| governance     | cron, daily @ 04:00 UTC  | `SUPERVISOR_GOVERNANCE_CRON`     |

Every job body is a safe placeholder that emits a JSON log line:
`{"job":"orchestrator","tick":N,"status":"ok","duration_ms":M,"ts":"..."}`.

## Completed
- 2026-07-22: HKB migration + provenance metadata + UI exposure.
- 2026-07-22: Operator Manual (`/app/docs/OPERATOR_MANUAL.md`).
- 2026-07-23: **FactorySupervisor wiring into runner.py (Phase-1b)** — 5 jobs
  register, orchestrator placeholder fires within ~60s, graceful shutdown via
  SIGTERM/SIGINT verified (exit code 0).

## Backlog
- **P1** — Replace placeholder job bodies with real engine invocations (once
  the API Feature Freeze allows). Wiring points are documented in
  `factory_supervisor.py` docstrings.
- **P1** — VPS Phase-1 activation (operator-triggered).
- **P2** — Phase-2 roadmap.

## Files of Reference
- `/app/backend/app/runner.py`
- `/app/backend/app/factory_supervisor.py`
- `/app/backend/app/core/config.py`
- `/app/backend/legacy/factory_runner.py` (legacy delegate)
- `/app/docs/OPERATOR_MANUAL.md`

## Environment Variables (Runner)
| Name                              | Default | Purpose                                |
| --------------------------------- | ------- | -------------------------------------- |
| `ENABLE_FACTORY_RUNNER`           | false   | Master runner enable flag              |
| `FACTORY_SUPERVISOR_ENABLED`      | false   | Start APScheduler-backed supervisor    |
| `FACTORY_RUNNER_OWNS_SCHEDULERS`  | false   | Delegate to legacy sibling             |
| `SUPERVISOR_ORCHESTRATOR_CRON`    | —       | Optional crontab override (5-field)    |
| `SUPERVISOR_MUTATION_CRON`        | —       | Optional crontab override              |
| `SUPERVISOR_FACTORY_EVAL_CRON`    | —       | Optional crontab override              |
| `SUPERVISOR_META_LEARNING_CRON`   | —       | Optional crontab override              |
| `SUPERVISOR_GOVERNANCE_CRON`      | —       | Optional crontab override              |
| `BUILD_VERSION`                   | 0.0.0   | Reported in startup log                |
