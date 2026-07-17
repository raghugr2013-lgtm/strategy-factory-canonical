# Validation Report — 20260717T105421Z

- **Started:** 2026-07-17T10:54:21.083954+00:00
- **Finished:** 2026-07-17T10:54:21.327273+00:00
- **Duration:** 0.24s
- **Base URL:** `http://localhost:8001`

## Aggregate

| Metric | Value |
|--------|-------|
| Total probes | 4 |
| PASS | 4 |
| FAIL | 0 |
| WARN | 0 |
| Average latency (ms) | 2.02 |
| p95 latency (ms) | 2.58 |
| Fastest (ms) | 1.1 |
| Slowest (ms) | 2.66 |
| Total response bytes | 6689 |

## Module: `health`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | health_endpoint | GET | `/api/health` | PASS | 200 | 1.1 | 168 | - |
| 2 | deployment_registry | GET | `/api/deployment/registry` | PASS | 200 | 2.7 | 143 | - |
| 3 | orchestrator_tasks_ok | GET | `/api/orchestrator/tasks` | PASS | 200 | 2.6 | 6036 | - |
| 4 | auth_me | GET | `/api/auth/me` | PASS | 200 | 1.7 | 342 | - |
