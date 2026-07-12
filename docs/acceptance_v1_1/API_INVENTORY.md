# Strategy Factory v1.1 — Complete API Inventory

**Total endpoints:** 497  |  **Groups:** 62  |  **Source:** `GET /api/openapi.json` at build time.

Auth: **JWT** = requires `Authorization: Bearer <asf_auth_token>`. **Public** = no auth. **Runner** = internal runner token.

Status: **Operational** = router mounted, endpoint responds. **Runtime-verified** for smoke-tested endpoints.

## `api/admin/*` — 40 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/admin/bi5/certifications` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/certifications/stats` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/certifications/{strategy_id}` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/certifications/{strategy_id}/latest` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/certified/{strategy_id}` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/certify-strategy` | POST | Public | Operational | Registered |
| `/api/admin/bi5/data-certifications` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/data-certifications/latest` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/run` | POST | Public | Operational | Registered |
| `/api/admin/bi5/sweep` | POST | Public | Operational | Registered |
| `/api/admin/bi5/sweep/results` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/sweep/runs` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/sweep/status` | GET | Public | Operational | Smoke |
| `/api/admin/bi5/symbols` | GET | Public | Operational | Smoke |
| `/api/admin/execution-realism-defaults` | DELETE | Public | Operational | Registered |
| `/api/admin/execution-realism-defaults` | POST | Public | Operational | Registered |
| `/api/admin/flag` | GET | Public | Operational | Smoke |
| `/api/admin/flag` | POST | Public | Operational | Registered |
| `/api/admin/flag/history` | GET | Public | Operational | Smoke |
| `/api/admin/flag/{flag_name}` | DELETE | Public | Operational | Registered |
| `/api/admin/market-universe` | DELETE | Public | Operational | Registered |
| `/api/admin/market-universe` | POST | Public | Operational | Registered |
| `/api/admin/market-universe/audit/{symbol}` | GET | Public | Operational | Smoke |
| `/api/admin/market-universe/bulk-import` | POST | Public | Operational | Registered |
| `/api/admin/market-universe/diff/{symbol}/{ts}` | GET | Public | Operational | Smoke |
| `/api/admin/market-universe/{symbol}` | GET | Public | Operational | Smoke |
| `/api/admin/market-universe/{symbol}/calendar` | POST | Public | Operational | Registered |
| `/api/admin/market-universe/{symbol}/eligibility` | POST | Public | Operational | Registered |
| `/api/admin/market-universe/{symbol}/enable` | POST | Public | Operational | Registered |
| `/api/admin/market-universe/{symbol}/tier` | POST | Public | Operational | Registered |
| `/api/admin/providers` | GET | Public | Operational | Smoke |
| `/api/admin/providers/probe` | POST | Public | Operational | Registered |
| `/api/admin/users` | GET | Public | Operational | Smoke |
| `/api/admin/users` | POST | Public | Operational | Registered |
| `/api/admin/users/{user_id}` | DELETE | Public | Operational | Registered |
| `/api/admin/users/{user_id}` | PATCH | Public | Operational | Registered |
| `/api/admin/widening-proposals` | GET | Public | Operational | Smoke |
| `/api/admin/widening-proposals` | POST | Public | Operational | Registered |
| `/api/admin/widening-proposals/{proposal_id}/approve` | POST | Public | Operational | Registered |
| `/api/admin/widening-proposals/{proposal_id}/reject` | POST | Public | Operational | Registered |

## `api/asf/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/asf/import/migration` | POST | Public | Operational | Registered |
| `/api/asf/import/{import_id}` | GET | Public | Operational | Smoke |
| `/api/asf/import/{import_id}/abort` | POST | Public | Operational | Registered |
| `/api/asf/import/{import_id}/commit` | POST | Public | Operational | Registered |

## `api/auth/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/auth/login` | POST | Public | Operational | Runtime-verified |
| `/api/auth/logout` | POST | Public | Operational | Registered |
| `/api/auth/me` | GET | Public | Operational | Runtime-verified |
| `/api/auth/refresh` | POST | Public | Operational | Registered |

## `api/auto/*` — 16 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/auto/evolution/weights` | GET | Public | Operational | Smoke |
| `/api/auto/multi-cycle/history` | GET | Public | Operational | Smoke |
| `/api/auto/multi-cycle/runs/{run_id}/best` | GET | Public | Operational | Smoke |
| `/api/auto/multi-cycle/start` | POST | Public | Operational | Registered |
| `/api/auto/multi-cycle/status` | GET | Public | Operational | Smoke |
| `/api/auto/multi-cycle/stop` | POST | Public | Operational | Registered |
| `/api/auto/mutation-runner` | POST | Public | Operational | Registered |
| `/api/auto/mutation-runner/cycles` | GET | Public | Operational | Smoke |
| `/api/auto/mutation-runner/status` | GET | Public | Operational | Smoke |
| `/api/auto/mutation-runner/stop` | POST | Public | Operational | Registered |
| `/api/auto/run-cycle` | POST | Public | Operational | Registered |
| `/api/auto/run-cycle/history` | GET | Public | Operational | Smoke |
| `/api/auto/run-once` | POST | Public | Operational | Registered |
| `/api/auto/scheduler/start` | POST | Public | Operational | Registered |
| `/api/auto/scheduler/status` | GET | Public | Operational | Smoke |
| `/api/auto/scheduler/stop` | POST | Public | Operational | Registered |

## `api/auto-factory/*` — 7 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/auto-factory` | POST | Public | Operational | Registered |
| `/api/auto-factory/run` | POST | Public | Operational | Registered |
| `/api/auto-factory/saved` | GET | Public | Operational | Runtime-verified |
| `/api/auto-factory/saved` | POST | Public | Operational | Runtime-verified |
| `/api/auto-factory/saved/{strategy_id}` | DELETE | Public | Operational | Registered |
| `/api/auto-factory/schedule` | POST | Public | Operational | Registered |
| `/api/auto-factory/status` | GET | Public | Operational | Smoke |

## `api/auto-factory-results/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/auto-factory-results` | GET | Public | Operational | Smoke |

## `api/auto-maintenance/*` — 3 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/auto-maintenance/run-now` | POST | Public | Operational | Registered |
| `/api/auto-maintenance/status` | GET | Public | Operational | Smoke |
| `/api/auto-maintenance/toggle` | POST | Public | Operational | Registered |

## `api/auto-select/*` — 3 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/auto-select/config` | GET | Public | Operational | Smoke |
| `/api/auto-select/recent` | GET | Public | Operational | Smoke |
| `/api/auto-select/run` | POST | Public | Operational | Registered |

## `api/bi5-realism/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/bi5-realism/cohort/stale-count` | GET | Public | Operational | Smoke |
| `/api/bi5-realism/evaluate/{strategy_hash}` | POST | Public | Operational | Registered |
| `/api/bi5-realism/sweep` | POST | Public | Operational | Registered |
| `/api/bi5-realism/{strategy_hash}` | GET | Public | Operational | Smoke |

## `api/cbot-parity/*` — 3 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/cbot-parity` | GET | Public | Operational | Smoke |
| `/api/cbot-parity/{strategy_hash}` | GET | Public | Operational | Smoke |
| `/api/cbot-parity/{strategy_hash}/sign-off` | POST | Public | Operational | Registered |

## `api/challenge/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/challenge/clear-cooldown` | POST | Public | Operational | Registered |
| `/api/challenge/control` | POST | Public | Operational | Registered |
| `/api/challenge/decision` | POST | Public | Operational | Registered |
| `/api/challenge/status` | GET | Public | Operational | Smoke |

## `api/check-gaps/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/check-gaps` | POST | Public | Operational | Registered |

## `api/cpu-pool/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/cpu-pool/state` | GET | Public | Operational | Smoke |

## `api/dashboard/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/dashboard/summary` | GET | Public | Operational | Runtime-verified |

## `api/data/*` — 17 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/data/backup/export` | GET | Public | Operational | Smoke |
| `/api/data/backup/export-all` | GET | Public | Operational | Smoke |
| `/api/data/backup/export-bulk` | POST | Public | Operational | Registered |
| `/api/data/backup/import` | POST | Public | Operational | Registered |
| `/api/data/export` | POST | Public | Operational | Registered |
| `/api/data/health` | GET | Public | Operational | Smoke |
| `/api/data/health/symbols` | GET | Public | Operational | Smoke |
| `/api/data/ingest-csv` | POST | Public | Operational | Registered |
| `/api/data/maintenance/backfill` | POST | Public | Operational | Registered |
| `/api/data/maintenance/config` | GET | Public | Operational | Smoke |
| `/api/data/maintenance/config` | POST | Public | Operational | Registered |
| `/api/data/maintenance/coverage` | GET | Public | Operational | Smoke |
| `/api/data/maintenance/import-backup` | POST | Public | Operational | Registered |
| `/api/data/maintenance/recent-runs` | GET | Public | Operational | Smoke |
| `/api/data/maintenance/run` | POST | Public | Operational | Registered |
| `/api/data/maintenance/status` | GET | Public | Operational | Smoke |
| `/api/data/maintenance/toggle` | POST | Public | Operational | Registered |

## `api/data-coverage/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/data-coverage` | GET | Public | Operational | Runtime-verified |

## `api/deployment/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/deployment/registry` | GET | Public | Operational | Smoke |

## `api/diag/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/diag/bi5/health` | GET | Public | Operational | Smoke |

## `api/diagnostics/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/diagnostics/soak-snapshot` | GET | Public | Operational | Smoke |

## `api/download-data/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/download-data` | POST | Public | Operational | Registered |

## `api/execution/*` — 14 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/execution/cbot/{session_id}/{strategy_id}` | GET | Public | Operational | Smoke |
| `/api/execution/emergency-stop` | POST | Public | Operational | Registered |
| `/api/execution/paper/config` | GET | Public | Operational | Smoke |
| `/api/execution/paper/deviation-alerts` | GET | Public | Operational | Smoke |
| `/api/execution/paper/deviation/{strategy_hash}` | GET | Public | Operational | Smoke |
| `/api/execution/paper/equity` | GET | Public | Operational | Smoke |
| `/api/execution/paper/runs` | GET | Public | Operational | Smoke |
| `/api/execution/paper/start` | POST | Public | Operational | Registered |
| `/api/execution/paper/status` | GET | Public | Operational | Smoke |
| `/api/execution/paper/stop` | POST | Public | Operational | Registered |
| `/api/execution/paper/trades` | GET | Public | Operational | Smoke |
| `/api/execution/start` | POST | Public | Operational | Registered |
| `/api/execution/status` | GET | Public | Operational | Smoke |
| `/api/execution/stop` | POST | Public | Operational | Registered |

## `api/factory-supervisor/*` — 56 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/factory-supervisor/architect/dashboard` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/architect/recommended-action` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/auto-learning/aggregate` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/auto-learning/eligibility` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/auto-learning/insights` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/auto-learning/notify` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/auto-learning/status` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/copilot/advanced/invoke` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/copilot/advanced/manifest` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/copilot/advanced/providers` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/copilot/answer` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/copilot/answers` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/copilot/context` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/defer-queue` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/defer-queue/cancel` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/defer-queue/expire-overdue` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/defer-queue/stats` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/defer-queue/{row_id}` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/eligibility` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/eligibility/{feature_name}` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/events` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/events/stats` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/fag/activate` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/fag/approve` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/fag/expire-overdue` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/fag/observe` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/fag/proposals` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/fag/proposals/stats` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/fag/proposals/{proposal_id}` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/fag/recommend` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/fag/reject` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/fleet` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/heartbeat-status` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/heartbeats` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/lock` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/lock/release` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/notifications` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/notifications/acknowledge` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/notifications/archive` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/notifications/stats` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/notifications/unread-count` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/notifications/{notification_id}` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/recommendations` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/recommendations/top` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/remote-transport` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/routing-policy` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/scheduler/start` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/scheduler/status` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/scheduler/stop` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/status` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/submissions` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/submissions/stats` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/submit` | POST | Public | Operational | Registered |
| `/api/factory-supervisor/system-state-view` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/workers` | GET | Public | Operational | Smoke |
| `/api/factory-supervisor/workers/tick` | POST | Public | Operational | Registered |

## `api/fix-gaps/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/fix-gaps` | POST | Public | Operational | Registered |

## `api/gem-factory/*` — 3 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/gem-factory/run` | POST | Public | Operational | Registered |
| `/api/gem-factory/status` | GET | Public | Operational | Smoke |
| `/api/gem-factory/sweep-degradation` | POST | Public | Operational | Registered |

## `api/generate-cbot/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/generate-cbot` | POST | Public | Operational | Registered |

## `api/governance/*` — 10 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/governance/bi5-maturity` | GET | Public | Operational | Smoke |
| `/api/governance/ecosystem-maturity` | GET | Public | Operational | Smoke |
| `/api/governance/promotion-ledger` | GET | Public | Operational | Runtime-verified |
| `/api/governance/replacement-candidates` | GET | Public | Operational | Smoke |
| `/api/governance/replacement/execute` | POST | Public | Operational | Registered |
| `/api/governance/strategy-truth/{strategy_hash}` | GET | Public | Operational | Smoke |
| `/api/governance/survivor-registry` | GET | Public | Operational | Smoke |
| `/api/governance/universe` | GET | Public | Operational | Smoke |
| `/api/governance/universe` | POST | Public | Operational | Registered |
| `/api/governance/universe/preview` | GET | Public | Operational | Smoke |

## `api/health/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/health` | GET | Public | Operational | Runtime-verified |

## `api/import-server-file/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/import-server-file` | POST | Public | Operational | Registered |

## `api/incremental/*` — 5 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/incremental/alignment` | GET | Public | Operational | Smoke |
| `/api/incremental/bi5` | POST | Public | Operational | Registered |
| `/api/incremental/bid` | POST | Public | Operational | Registered |
| `/api/incremental/last-timestamp` | GET | Public | Operational | Runtime-verified |
| `/api/incremental/run` | POST | Public | Operational | Registered |

## `api/ingestion/*` — 5 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/ingestion/logs` | GET | Public | Operational | Smoke |
| `/api/ingestion/queue` | POST | Public | Operational | Registered |
| `/api/ingestion/run` | POST | Public | Operational | Registered |
| `/api/ingestion/status` | GET | Public | Operational | Smoke |
| `/api/ingestion/toggle` | POST | Public | Operational | Registered |

## `api/latent/*` — 38 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/latent/activation-governance` | GET | Public | Operational | Smoke |
| `/api/latent/activation-journal` | GET | Public | Operational | Smoke |
| `/api/latent/activation-timeline` | GET | Public | Operational | Smoke |
| `/api/latent/activation-timeline/summary` | GET | Public | Operational | Smoke |
| `/api/latent/agent-advisor` | GET | Public | Operational | Smoke |
| `/api/latent/calibration/build-table` | POST | Public | Operational | Registered |
| `/api/latent/calibration/outcomes` | POST | Public | Operational | Registered |
| `/api/latent/calibration/predictions` | POST | Public | Operational | Registered |
| `/api/latent/calibration/status` | GET | Public | Operational | Smoke |
| `/api/latent/cbot-log-diagnostic` | POST | Public | Operational | Registered |
| `/api/latent/cbot-trade-parity` | GET | Public | Operational | Smoke |
| `/api/latent/compute-probe` | GET | Public | Operational | Smoke |
| `/api/latent/deployment-extras` | GET | Public | Operational | Smoke |
| `/api/latent/deployment-readiness` | GET | Public | Operational | Smoke |
| `/api/latent/ecosystem-allocation` | GET | Public | Operational | Smoke |
| `/api/latent/execution-realism-defaults` | GET | Public | Operational | Smoke |
| `/api/latent/factory-runner-heartbeat` | GET | Public | Operational | Smoke |
| `/api/latent/feature-flags` | GET | Public | Operational | Smoke |
| `/api/latent/flag-overrides` | GET | Public | Operational | Smoke |
| `/api/latent/htf-parity` | POST | Public | Operational | Registered |
| `/api/latent/ingestion-aggregate` | GET | Public | Operational | Smoke |
| `/api/latent/ingestion-health` | GET | Public | Operational | Smoke |
| `/api/latent/lifecycle_decay/distribution` | GET | Public | Operational | Smoke |
| `/api/latent/lifecycle_decay/recompute` | POST | Public | Operational | Registered |
| `/api/latent/lifecycle_decay/seed-evidence-fields` | POST | Public | Operational | Registered |
| `/api/latent/lifecycle_decay/status` | GET | Public | Operational | Smoke |
| `/api/latent/market-universe` | GET | Public | Operational | Smoke |
| `/api/latent/market-universe/{symbol}` | GET | Public | Operational | Smoke |
| `/api/latent/mutation-saturation` | GET | Public | Operational | Smoke |
| `/api/latent/orchestration-health` | GET | Public | Operational | Smoke |
| `/api/latent/parity-certification` | GET | Public | Operational | Smoke |
| `/api/latent/replay-allocation` | GET | Public | Operational | Smoke |
| `/api/latent/risk_of_ruin/evaluate` | POST | Public | Operational | Registered |
| `/api/latent/risk_of_ruin/evaluations` | GET | Public | Operational | Smoke |
| `/api/latent/rotational-proposal` | GET | Public | Operational | Smoke |
| `/api/latent/safe-to-widen` | GET | Public | Operational | Smoke |
| `/api/latent/soak-stability` | GET | Public | Operational | Smoke |
| `/api/latent/widening-history` | GET | Public | Operational | Smoke |

## `api/legacy/*` — 46 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/legacy/admin/approve/{user_id}` | POST | Public | Operational | Registered |
| `/api/legacy/admin/readiness` | GET | Public | Operational | Smoke |
| `/api/legacy/admin/reject/{user_id}` | POST | Public | Operational | Registered |
| `/api/legacy/admin/users` | GET | Public | Operational | Smoke |
| `/api/legacy/allocation-history` | GET | Public | Operational | Smoke |
| `/api/legacy/analyze-strategy` | POST | Public | Operational | Registered |
| `/api/legacy/challenge-firms` | GET | Public | Operational | Smoke |
| `/api/legacy/challenge-rules` | GET | Public | Operational | Smoke |
| `/api/legacy/challenge-rules` | POST | Public | Operational | Registered |
| `/api/legacy/challenge-rules/{firm_slug}` | DELETE | Public | Operational | Registered |
| `/api/legacy/challenge-rules/{firm_slug}` | GET | Public | Operational | Smoke |
| `/api/legacy/challenge-rules/{firm_slug}` | PUT | Public | Operational | Registered |
| `/api/legacy/challenge-rules/{firm_slug}/changelog` | GET | Public | Operational | Smoke |
| `/api/legacy/challenge-rules/{firm_slug}/override` | POST | Public | Operational | Registered |
| `/api/legacy/challenge-rules/{firm_slug}/validate` | POST | Public | Operational | Registered |
| `/api/legacy/dashboard/datasets` | GET | Public | Operational | Smoke |
| `/api/legacy/dashboard/generate` | POST | Public | Operational | Registered |
| `/api/legacy/dashboard/generate-portfolio` | POST | Public | Operational | Registered |
| `/api/legacy/dashboard/quality-profile` | POST | Public | Operational | Registered |
| `/api/legacy/estimate-probability` | POST | Public | Operational | Registered |
| `/api/legacy/evaluate-decision` | POST | Public | Operational | Registered |
| `/api/legacy/extract-params` | POST | Public | Operational | Registered |
| `/api/legacy/generate-strategy` | POST | Public | Operational | Registered |
| `/api/legacy/match-strategy` | POST | Public | Operational | Registered |
| `/api/legacy/monte-carlo` | POST | Public | Operational | Registered |
| `/api/legacy/mutate-strategy` | POST | Public | Operational | Registered |
| `/api/legacy/optimize-random` | POST | Public | Operational | Registered |
| `/api/legacy/optimize-strategy` | POST | Public | Operational | Registered |
| `/api/legacy/portfolio-analyze` | POST | Public | Operational | Registered |
| `/api/legacy/portfolio-auto-build` | POST | Public | Operational | Registered |
| `/api/legacy/portfolio-live-allocation` | POST | Public | Operational | Registered |
| `/api/legacy/profile-strategy` | POST | Public | Operational | Registered |
| `/api/legacy/rank-strategies` | POST | Public | Operational | Registered |
| `/api/legacy/rebalance/config` | GET | Public | Operational | Smoke |
| `/api/legacy/rebalance/config` | POST | Public | Operational | Registered |
| `/api/legacy/rebalance/run` | POST | Public | Operational | Registered |
| `/api/legacy/rebalance/status` | GET | Public | Operational | Smoke |
| `/api/legacy/run-backtest` | POST | Public | Operational | Registered |
| `/api/legacy/safety-check` | POST | Public | Operational | Registered |
| `/api/legacy/save-strategy` | POST | Public | Operational | Registered |
| `/api/legacy/simulate-challenge` | POST | Public | Operational | Registered |
| `/api/legacy/strategies` | GET | Public | Operational | Runtime-verified |
| `/api/legacy/strategies/compare` | POST | Public | Operational | Registered |
| `/api/legacy/strategies/{strategy_id}` | DELETE | Public | Operational | Registered |
| `/api/legacy/strategies/{strategy_id}` | GET | Public | Operational | Smoke |
| `/api/legacy/validate-strategy` | POST | Public | Operational | Registered |

## `api/lifecycle/*` — 6 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/lifecycle/cohort/stage-counts` | GET | Public | Operational | Smoke |
| `/api/lifecycle/evaluate` | POST | Public | Operational | Registered |
| `/api/lifecycle/regime-evidence/{strategy_hash}` | GET | Public | Operational | Smoke |
| `/api/lifecycle/transitions/recent` | GET | Public | Operational | Smoke |
| `/api/lifecycle/{strategy_hash}` | GET | Public | Operational | Smoke |
| `/api/lifecycle/{strategy_hash}/history` | GET | Public | Operational | Smoke |

## `api/live/*` — 8 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/live/config` | POST | Public | Operational | Registered |
| `/api/live/refresh-data` | POST | Public | Operational | Registered |
| `/api/live/start` | POST | Public | Operational | Registered |
| `/api/live/stop` | POST | Public | Operational | Registered |
| `/api/live/strategies` | GET | Public | Operational | Smoke |
| `/api/live/update-all` | POST | Public | Operational | Registered |
| `/api/live/update/{strategy_id}` | POST | Public | Operational | Registered |
| `/api/live/{strategy_id}` | DELETE | Public | Operational | Registered |

## `api/llm/*` — 6 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/llm/call-log/recent` | GET | Public | Operational | Smoke |
| `/api/llm/cpu-pool` | GET | Public | Operational | Smoke |
| `/api/llm/diagnostics` | GET | Public | Operational | Runtime-verified |
| `/api/llm/health-by-provider` | GET | Public | Operational | Smoke |
| `/api/llm/index-summary` | GET | Public | Operational | Smoke |
| `/api/llm/runner-state` | GET | Public | Operational | Smoke |

## `api/logs/*` — 2 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/logs` | GET | Public | Operational | Smoke |
| `/api/logs/stages` | GET | Public | Operational | Smoke |

## `api/market-data/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/market-data` | GET | Public | Operational | Runtime-verified |

## `api/master-bot/*` — 58 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/master-bot` | GET | Public | Operational | Smoke |
| `/api/master-bot` | POST | Public | Operational | Registered |
| `/api/master-bot/candidates` | GET | Public | Operational | Smoke |
| `/api/master-bot/candidates/refresh` | POST | Public | Operational | Registered |
| `/api/master-bot/deployments/parity-drift` | GET | Public | Operational | Smoke |
| `/api/master-bot/deployments/parity-drift/scan-and-alert` | POST | Public | Operational | Registered |
| `/api/master-bot/deployments/parity-drift/{deployment_id}` | GET | Public | Operational | Smoke |
| `/api/master-bot/deployments/{deployment_id}` | GET | Public | Operational | Smoke |
| `/api/master-bot/deployments/{deployment_id}/promote` | POST | Public | Operational | Registered |
| `/api/master-bot/deployments/{deployment_id}/stage` | POST | Public | Operational | Registered |
| `/api/master-bot/exports/{export_id}/download/{kind}` | GET | Public | Operational | Smoke |
| `/api/master-bot/ir/backfill` | POST | Public | Operational | Registered |
| `/api/master-bot/ir/coverage` | GET | Public | Operational | Smoke |
| `/api/master-bot/packs/{pack_id}/download` | GET | Public | Operational | Smoke |
| `/api/master-bot/parity/gate-status` | GET | Public | Operational | Smoke |
| `/api/master-bot/ranker/config` | GET | Public | Operational | Smoke |
| `/api/master-bot/ranker/config` | POST | Public | Operational | Registered |
| `/api/master-bot/runners` | GET | Public | Operational | Smoke |
| `/api/master-bot/runners` | POST | Public | Operational | Registered |
| `/api/master-bot/runners/accounts/migrate-legacy` | POST | Public | Operational | Registered |
| `/api/master-bot/runners/accounts/migration-status` | GET | Public | Operational | Smoke |
| `/api/master-bot/runners/fleet` | GET | Public | Operational | Smoke |
| `/api/master-bot/runners/route-preview` | GET | Public | Operational | Smoke |
| `/api/master-bot/runners/{runner_id}` | GET | Public | Operational | Smoke |
| `/api/master-bot/runners/{runner_id}/accounts` | GET | Public | Operational | Smoke |
| `/api/master-bot/runners/{runner_id}/accounts` | POST | Public | Operational | Registered |
| `/api/master-bot/runners/{runner_id}/accounts/{account_id}` | DELETE | Public | Operational | Registered |
| `/api/master-bot/runners/{runner_id}/disable` | POST | Public | Operational | Registered |
| `/api/master-bot/runners/{runner_id}/rotate-token` | GET | Public | Operational | Smoke |
| `/api/master-bot/runners/{runner_id}/rotate-token` | POST | Public | Operational | Registered |
| `/api/master-bot/runners/{runner_id}/rotate-token/expire-old` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}` | DELETE | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}` | PUT | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/auto-fill` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/compile` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/definitions` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/definitions/latest` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/definitions/{rev}` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/deploy/register` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/deploy/rollback` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/deploy/status` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/deployments` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/diff` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/export` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/exports` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/members` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/members/{strategy_hash}` | DELETE | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/members/{strategy_hash}/demote` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/members/{strategy_hash}/disable` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/members/{strategy_hash}/enable` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/members/{strategy_hash}/move-to` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/members/{strategy_hash}/promote` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/pack` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/packs` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/parity/preview` | GET | Public | Operational | Smoke |
| `/api/master-bot/{master_bot_id}/tiers/{tier}` | POST | Public | Operational | Registered |
| `/api/master-bot/{master_bot_id}/tiers/{tier}/reorder` | POST | Public | Operational | Registered |

## `api/monitoring/*` — 8 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/monitoring/equity-curve` | GET | Public | Operational | Smoke |
| `/api/monitoring/pause` | POST | Public | Operational | Registered |
| `/api/monitoring/reset` | POST | Public | Operational | Registered |
| `/api/monitoring/resume` | POST | Public | Operational | Registered |
| `/api/monitoring/run` | POST | Public | Operational | Registered |
| `/api/monitoring/scheduler` | POST | Public | Operational | Registered |
| `/api/monitoring/status` | GET | Public | Operational | Smoke |
| `/api/monitoring/thresholds` | POST | Public | Operational | Registered |

## `api/mutation/*` — 10 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/mutation/catalogue` | GET | Public | Operational | Smoke |
| `/api/mutation/events` | GET | Public | Operational | Smoke |
| `/api/mutation/evolution/stats` | GET | Public | Operational | Smoke |
| `/api/mutation/ir-telemetry` | GET | Public | Operational | Smoke |
| `/api/mutation/mutate` | POST | Public | Operational | Registered |
| `/api/mutation/preview` | POST | Public | Operational | Registered |
| `/api/mutation/regime/classify` | GET | Public | Operational | Smoke |
| `/api/mutation/stability/logs` | GET | Public | Operational | Smoke |
| `/api/mutation/stability/stats` | GET | Public | Operational | Smoke |
| `/api/mutation/stats` | GET | Public | Operational | Smoke |

## `api/optimization/*` — 6 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/optimization/best` | GET | Public | Operational | Smoke |
| `/api/optimization/config` | GET | Public | Operational | Smoke |
| `/api/optimization/history` | GET | Public | Operational | Smoke |
| `/api/optimization/portfolio-actions` | GET | Public | Operational | Smoke |
| `/api/optimization/run` | POST | Public | Operational | Registered |
| `/api/optimization/strategy/{strategy_id}` | GET | Public | Operational | Smoke |

## `api/orchestrator/*` — 12 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/orchestrator/decide` | POST | Public | Operational | Registered |
| `/api/orchestrator/env-priority/config` | GET | Public | Operational | Smoke |
| `/api/orchestrator/env-priority/config` | POST | Public | Operational | Registered |
| `/api/orchestrator/env-priority/reset` | POST | Public | Operational | Registered |
| `/api/orchestrator/env-priority/sample` | POST | Public | Operational | Registered |
| `/api/orchestrator/env-priority/stats` | GET | Public | Operational | Smoke |
| `/api/orchestrator/heartbeat` | GET | Public | Operational | Smoke |
| `/api/orchestrator/scheduler/start` | POST | Public | Operational | Registered |
| `/api/orchestrator/scheduler/status` | GET | Public | Operational | Smoke |
| `/api/orchestrator/scheduler/stop` | POST | Public | Operational | Registered |
| `/api/orchestrator/state` | GET | Public | Operational | Smoke |
| `/api/orchestrator/tick` | POST | Public | Operational | Registered |

## `api/phase4/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/phase4/match-firms` | POST | Public | Operational | Registered |

## `api/portfolio/*` — 2 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/portfolio/build` | POST | Public | Operational | Registered |
| `/api/portfolio/status` | GET | Public | Operational | Smoke |

## `api/portfolio-builder/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/portfolio-builder/build` | POST | Public | Operational | Registered |
| `/api/portfolio-builder/config` | GET | Public | Operational | Smoke |
| `/api/portfolio-builder/recent` | GET | Public | Operational | Smoke |
| `/api/portfolio-builder/save` | POST | Public | Operational | Registered |

## `api/portfolio-intelligence/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/portfolio-intelligence/build` | POST | Public | Operational | Registered |
| `/api/portfolio-intelligence/config` | GET | Public | Operational | Smoke |
| `/api/portfolio-intelligence/current` | GET | Public | Operational | Smoke |
| `/api/portfolio-intelligence/history` | GET | Public | Operational | Smoke |

## `api/prop-firm-rules/*` — 6 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/prop-firm-rules` | GET | Public | Operational | Smoke |
| `/api/prop-firm-rules/ingest-parsed` | POST | Public | Operational | Registered |
| `/api/prop-firm-rules/{firm_slug}` | GET | Public | Operational | Smoke |
| `/api/prop-firm-rules/{firm_slug}/approve` | POST | Public | Operational | Registered |
| `/api/prop-firm-rules/{firm_slug}/reject` | POST | Public | Operational | Registered |
| `/api/prop-firm-rules/{firm_slug}/reset` | POST | Public | Operational | Registered |

## `api/prop-firms/*` — 13 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/prop-firms/discover-challenges` | POST | Public | Operational | Registered |
| `/api/prop-firms/extract` | POST | Public | Operational | Registered |
| `/api/prop-firms/extract-async` | POST | Public | Operational | Registered |
| `/api/prop-firms/extract-jobs` | GET | Public | Operational | Smoke |
| `/api/prop-firms/extract-jobs/{job_id}` | GET | Public | Operational | Smoke |
| `/api/prop-firms/intelligence/list` | GET | Public | Operational | Smoke |
| `/api/prop-firms/intelligence/{firm_slug}` | DELETE | Public | Operational | Registered |
| `/api/prop-firms/intelligence/{firm_slug}` | GET | Public | Operational | Smoke |
| `/api/prop-firms/list` | GET | Public | Operational | Smoke |
| `/api/prop-firms/save` | POST | Public | Operational | Registered |
| `/api/prop-firms/save-challenges` | POST | Public | Operational | Registered |
| `/api/prop-firms/{firm_slug}` | DELETE | Public | Operational | Registered |
| `/api/prop-firms/{firm_slug}` | GET | Public | Operational | Smoke |

## `api/readiness/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/readiness` | GET | Public | Operational | Smoke |

## `api/regime/*` — 2 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/regime/cohort-distribution` | GET | Public | Operational | Smoke |
| `/api/regime/strategy/{strategy_hash}` | GET | Public | Operational | Smoke |

## `api/research/*` — 2 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/research/history` | GET | Public | Operational | Smoke |
| `/api/research/query` | POST | Public | Operational | Registered |

## `api/research-runs/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/research-runs` | GET | Public | Operational | Smoke |
| `/api/research-runs/by-library/{library_id}` | GET | Public | Operational | Smoke |
| `/api/research-runs/by-strategy/{strategy_hash}` | GET | Public | Operational | Smoke |
| `/api/research-runs/{rrid}` | GET | Public | Operational | Smoke |

## `api/run-auto-factory/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/run-auto-factory` | POST | Public | Operational | Registered |

## `api/run-pipeline/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/run-pipeline` | POST | Public | Operational | Registered |

## `api/runner/*` — 4 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/runner/ack` | POST | Public | Operational | Registered |
| `/api/runner/artifact/{pack_id}` | GET | Public | Operational | Smoke |
| `/api/runner/heartbeat` | POST | Public | Operational | Registered |
| `/api/runner/poll` | GET | Runner | Operational | Smoke |

## `api/scaling/*` — 10 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/scaling/admission` | GET | Public | Operational | Smoke |
| `/api/scaling/admission/journal-stats` | GET | Public | Operational | Smoke |
| `/api/scaling/architect/snapshot` | GET | Public | Operational | Smoke |
| `/api/scaling/concurrency` | GET | Public | Operational | Smoke |
| `/api/scaling/events` | GET | Public | Operational | Smoke |
| `/api/scaling/events/stats` | GET | Public | Operational | Smoke |
| `/api/scaling/heartbeat` | POST | Public | Operational | Registered |
| `/api/scaling/nodes` | GET | Public | Operational | Smoke |
| `/api/scaling/pressure` | GET | Public | Operational | Smoke |
| `/api/scaling/route` | GET | Public | Operational | Smoke |

## `api/server-files/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/server-files` | GET | Public | Operational | Smoke |

## `api/strategies/*` — 12 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/strategies` | GET | Public | Operational | Runtime-verified |
| `/api/strategies` | POST | Public | Operational | Runtime-verified |
| `/api/strategies/explorer` | GET | Public | Operational | Smoke |
| `/api/strategies/generate` | POST | Public | Operational | Registered |
| `/api/strategies/library/{strategy_id}/details` | GET | Public | Operational | Smoke |
| `/api/strategies/{strategy_hash}/export` | GET | Public | Operational | Smoke |
| `/api/strategies/{strategy_hash}/export/cbot` | GET | Public | Operational | Smoke |
| `/api/strategies/{strategy_hash}/favorite` | POST | Public | Operational | Registered |
| `/api/strategies/{strategy_hash}/history` | GET | Public | Operational | Smoke |
| `/api/strategies/{strategy_hash}/re-run` | POST | Public | Operational | Registered |
| `/api/strategies/{strategy_id}` | DELETE | Public | Operational | Registered |
| `/api/strategies/{strategy_id}` | GET | Public | Operational | Smoke |

## `api/trade-runner/*` — 6 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/trade-runner/config` | GET | Public | Operational | Smoke |
| `/api/trade-runner/runs` | GET | Public | Operational | Smoke |
| `/api/trade-runner/start` | POST | Public | Operational | Registered |
| `/api/trade-runner/status/{run_id}` | GET | Public | Operational | Smoke |
| `/api/trade-runner/step/{run_id}` | POST | Public | Operational | Registered |
| `/api/trade-runner/stop/{run_id}` | POST | Public | Operational | Registered |

## `api/tuning/*` — 9 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/tuning/events` | GET | Public | Operational | Smoke |
| `/api/tuning/overview` | GET | Public | Operational | Smoke |
| `/api/tuning/performance` | GET | Public | Operational | Smoke |
| `/api/tuning/performance/snapshot` | POST | Public | Operational | Registered |
| `/api/tuning/settings` | GET | Public | Operational | Smoke |
| `/api/tuning/settings` | POST | Public | Operational | Registered |
| `/api/tuning/settings/reset` | POST | Public | Operational | Registered |
| `/api/tuning/slot-stats` | GET | Public | Operational | Smoke |
| `/api/tuning/slot-stats/recommend` | GET | Public | Operational | Smoke |

## `api/upload-data/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/upload-data` | POST | Public | Operational | Registered |

## `api/version/*` — 1 endpoint(s)

| Route | Method | Auth | Status | Tested |
|-------|--------|------|--------|--------|
| `/api/version` | GET | Public | Operational | Runtime-verified |

