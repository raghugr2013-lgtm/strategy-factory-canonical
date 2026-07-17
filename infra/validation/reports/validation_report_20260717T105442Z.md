# Validation Report — 20260717T105442Z

- **Started:** 2026-07-17T10:54:42.183615+00:00
- **Finished:** 2026-07-17T10:54:42.424456+00:00
- **Duration:** 0.24s
- **Base URL:** `http://localhost:8001`

## Aggregate

| Metric | Value |
|--------|-------|
| Total probes | 4 |
| PASS | 4 |
| FAIL | 0 |
| WARN | 0 |
| Average latency (ms) | 1.76 |
| p95 latency (ms) | 2.31 |
| Fastest (ms) | 1.07 |
| Slowest (ms) | 2.38 |
| Total response bytes | 6689 |

## Module: `health`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | health_endpoint | GET | `/api/health` | PASS | 200 | 1.1 | 168 | - |
| 2 | deployment_registry | GET | `/api/deployment/registry` | PASS | 200 | 2.3 | 143 | - |
| 3 | orchestrator_tasks_ok | GET | `/api/orchestrator/tasks` | PASS | 200 | 2.4 | 6036 | - |
| 4 | auth_me | GET | `/api/auth/me` | PASS | 200 | 1.3 | 342 | - |
