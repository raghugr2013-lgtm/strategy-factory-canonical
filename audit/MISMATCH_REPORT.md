# Strategy Factory — Frontend ↔ Backend API Mismatch Report

Total distinct frontend paths analysed: **277**  
Total backend paths analysed: **497**

---

## MISMATCHES (52)

| Frontend path | Resolution |
|---|---|
| `/api/admin/approve` | MISSING_IN_BACKEND |
| `/api/admin/flag-governance` | MISSING_IN_BACKEND |
| `/api/admin/readiness` | MOUNTED_AT_LEGACY: /api/legacy/admin/readiness |
| `/api/admin/reject` | MISSING_IN_BACKEND |
| `/api/allocation-history` | MOUNTED_AT_LEGACY: /api/legacy/allocation-history |
| `/api/analyze-strategy` | MOUNTED_AT_LEGACY: /api/legacy/analyze-strategy |
| `/api/auth/signup` | MISSING_IN_BACKEND |
| `/api/auto-factory/saved.` | MISSING_IN_BACKEND |
| `/api/auto-factory/saved/{id` | MISSING_IN_BACKEND |
| `/api/challenge-firms` | MOUNTED_AT_LEGACY: /api/legacy/challenge-firms |
| `/api/cpu-pool-state` | MISSING_IN_BACKEND |
| `/api/dashboard/datasets` | MOUNTED_AT_LEGACY: /api/legacy/dashboard/datasets |
| `/api/dashboard/generate` | MOUNTED_AT_LEGACY: /api/legacy/dashboard/generate |
| `/api/dashboard/generate-portfolio` | MOUNTED_AT_LEGACY: /api/legacy/dashboard/generate-portfolio |
| `/api/dashboard/portfolios` | MISSING_IN_BACKEND |
| `/api/dashboard/portfolios/list` | MOUNTED_AT_LEGACY: /api/legacy/dashboard/portfolios/list |
| `/api/dashboard/portfolios/save` | MOUNTED_AT_LEGACY: /api/legacy/dashboard/portfolios/save |
| `/api/dashboard/quality-profile` | MOUNTED_AT_LEGACY: /api/legacy/dashboard/quality-profile |
| `/api/extract-params` | MOUNTED_AT_LEGACY: /api/legacy/extract-params |
| `/api/generate-strategy` | MOUNTED_AT_LEGACY: /api/legacy/generate-strategy |
| `/api/health.` | MISSING_IN_BACKEND |
| `/api/inbox/events` | MISSING_IN_BACKEND |
| `/api/latent/ingestion-aggregate.` | MISSING_IN_BACKEND |
| `/api/library/auto-save` | MOUNTED_AT_LEGACY: /api/legacy/library/auto-save |
| `/api/library/list` | MOUNTED_AT_LEGACY: /api/legacy/library/list |
| `/api/library/save` | MOUNTED_AT_LEGACY: /api/legacy/library/save |
| `/api/llm/call-log/recent.` | MISSING_IN_BACKEND |
| `/api/market-data.` | MISSING_IN_BACKEND |
| `/api/match-firms-phase4` | MOUNTED_AT_LEGACY: /api/legacy/match-firms-phase4 |
| `/api/match-firms-phase4.` | MISSING_IN_BACKEND |
| `/api/monte-carlo` | MOUNTED_AT_LEGACY: /api/legacy/monte-carlo |
| `/api/optimize-random` | MOUNTED_AT_LEGACY: /api/legacy/optimize-random |
| `/api/optimize-strategy` | MOUNTED_AT_LEGACY: /api/legacy/optimize-strategy |
| `/api/orchestrator/heartbeat.` | MISSING_IN_BACKEND |
| `/api/phase12-tuning` | MISSING_IN_BACKEND |
| `/api/portfolio-analyze` | MOUNTED_AT_LEGACY: /api/legacy/portfolio-analyze |
| `/api/portfolio-auto-build` | MOUNTED_AT_LEGACY: /api/legacy/portfolio-auto-build |
| `/api/portfolio-live-allocation` | MOUNTED_AT_LEGACY: /api/legacy/portfolio-live-allocation |
| `/api/prop-firms/extract-jobs.` | MISSING_IN_BACKEND |
| `/api/rank-strategies` | MOUNTED_AT_LEGACY: /api/legacy/rank-strategies |
| `/api/rebalance/config` | MOUNTED_AT_LEGACY: /api/legacy/rebalance/config |
| `/api/rebalance/run` | MOUNTED_AT_LEGACY: /api/legacy/rebalance/run |
| `/api/rebalance/status` | MOUNTED_AT_LEGACY: /api/legacy/rebalance/status |
| `/api/run-backtest` | MOUNTED_AT_LEGACY: /api/legacy/run-backtest |
| `/api/safety-check` | MOUNTED_AT_LEGACY: /api/legacy/safety-check |
| `/api/save-strategy` | MOUNTED_AT_LEGACY: /api/legacy/save-strategy |
| `/api/soak/diagnostics` | MISSING_IN_BACKEND |
| `/api/strategies/compare` | MOUNTED_AT_LEGACY: /api/legacy/strategies/compare |
| `/api/strategies/{id` | MISSING_IN_BACKEND |
| `/api/strategy/describe` | MOUNTED_AT_LEGACY: /api/legacy/strategy/describe |
| `/api/validate-strategy` | MOUNTED_AT_LEGACY: /api/legacy/validate-strategy |
| `/api/{router` | MISSING_IN_BACKEND |

## PARTIAL/PREFIX MATCHES (23)

| Frontend base | Backend hits |
|---|---|
| `/api/admin/execution-realism` | `/api/admin/execution-realism-defaults` |
| `/api/admin/flag/{flag_name` | `/api/admin/flag/{flag_name}` |
| `/api/admin/market-universe/{sym` | `/api/admin/market-universe/{symbol}`, `/api/admin/market-universe/{symbol}/calendar`, `/api/admin/market-universe/{symbol}/eligibility` |
| `/api/admin/widening-proposals/{proposal_id` | `/api/admin/widening-proposals/{proposal_id}/approve`, `/api/admin/widening-proposals/{proposal_id}/reject` |
| `/api/auto/multi-cycle/runs` | `/api/auto/multi-cycle/runs/{run_id}/best` |
| `/api/data/backup` | `/api/data/backup/export`, `/api/data/backup/export-all`, `/api/data/backup/export-bulk` |
| `/api/execution/cbot` | `/api/execution/cbot/{session_id}/{strategy_id}` |
| `/api/execution/paper/deviation` | `/api/execution/paper/deviation-alerts`, `/api/execution/paper/deviation/{strategy_hash}` |
| `/api/factory-supervisor` | `/api/factory-supervisor/architect/dashboard`, `/api/factory-supervisor/architect/recommended-action`, `/api/factory-supervisor/auto-learning/aggregate` |
| `/api/gem-factory` | `/api/gem-factory/run`, `/api/gem-factory/status`, `/api/gem-factory/sweep-degradation` |
| `/api/live` | `/api/live/config`, `/api/live/refresh-data`, `/api/live/start` |
| `/api/live/update` | `/api/live/update-all`, `/api/live/update/{strategy_id}` |
| `/api/master-bot/exports` | `/api/master-bot/exports/{export_id}/download/{kind}` |
| `/api/master-bot/packs` | `/api/master-bot/packs/{pack_id}/download` |
| `/api/monitoring` | `/api/monitoring/equity-curve`, `/api/monitoring/pause`, `/api/monitoring/reset` |
| `/api/prop-firms` | `/api/prop-firms/discover-challenges`, `/api/prop-firms/extract`, `/api/prop-firms/extract-async` |
| `/api/prop-firms/intelligence` | `/api/prop-firms/intelligence/list`, `/api/prop-firms/intelligence/{firm_slug}` |
| `/api/research-runs/by-strategy` | `/api/research-runs/by-strategy/{strategy_hash}` |
| `/api/scaling` | `/api/scaling/admission`, `/api/scaling/admission/journal-stats`, `/api/scaling/architect/snapshot` |
| `/api/strategies/library` | `/api/strategies/library/{strategy_id}/details` |
| `/api/trade-runner/status` | `/api/trade-runner/status/{run_id}` |
| `/api/trade-runner/step` | `/api/trade-runner/step/{run_id}` |
| `/api/trade-runner/stop` | `/api/trade-runner/stop/{run_id}` |

## EXACT MATCHES (202)

- `/api/admin/bi5/certifications/stats`
- `/api/admin/bi5/data-certifications`
- `/api/admin/bi5/sweep`
- `/api/admin/bi5/sweep/runs`
- `/api/admin/bi5/sweep/status`
- `/api/admin/execution-realism-defaults`
- `/api/admin/flag`
- `/api/admin/flag/history`
- `/api/admin/market-universe`
- `/api/admin/users`
- `/api/admin/widening-proposals`
- `/api/auth/login`
- `/api/auth/me`
- `/api/auto-factory`
- `/api/auto-factory/run`
- `/api/auto-factory/saved`
- `/api/auto-factory/schedule`
- `/api/auto-factory/status`
- `/api/auto-maintenance/run-now`
- `/api/auto-maintenance/status`
- `/api/auto-maintenance/toggle`
- `/api/auto-select/config`
- `/api/auto-select/recent`
- `/api/auto-select/run`
- `/api/auto/multi-cycle/history`
- `/api/auto/multi-cycle/start`
- `/api/auto/multi-cycle/status`
- `/api/auto/multi-cycle/stop`
- `/api/auto/mutation-runner`
- `/api/auto/mutation-runner/status`
- `/api/auto/mutation-runner/stop`
- `/api/auto/run-once`
- `/api/auto/scheduler/start`
- `/api/auto/scheduler/status`
- `/api/auto/scheduler/stop`
- `/api/challenge-matching/challenge-types/by-firm`
- `/api/challenge-matching/run-eligible`
- `/api/challenge/clear-cooldown`
- `/api/challenge/control`
- `/api/challenge/decision`
- `/api/challenge/status`
- `/api/check-gaps`
- `/api/cpu-pool/state`
- `/api/data-coverage`
- `/api/data/backup/export`
- `/api/data/backup/export-all`
- `/api/data/backup/import`
- `/api/data/export`
- `/api/data/maintenance/backfill`
- `/api/data/maintenance/config`
- `/api/data/maintenance/coverage`
- `/api/data/maintenance/import-backup`
- `/api/data/maintenance/run`
- `/api/data/maintenance/status`
- `/api/data/maintenance/toggle`
- `/api/deployment/registry`
- `/api/diag/bi5/health`
- `/api/diagnostics/soak-snapshot`
- `/api/download-data`
- `/api/execution/emergency-stop`
- `/api/execution/paper/config`
- `/api/execution/paper/equity`
- `/api/execution/paper/runs`
- `/api/execution/paper/start`
- `/api/execution/paper/status`
- `/api/execution/paper/stop`
- `/api/execution/paper/trades`
- `/api/execution/start`
- `/api/execution/status`
- `/api/execution/stop`
- `/api/factory-supervisor/architect/dashboard`
- `/api/factory-supervisor/auto-learning/aggregate`
- `/api/factory-supervisor/auto-learning/insights`
- `/api/factory-supervisor/auto-learning/status`
- `/api/factory-supervisor/copilot/advanced/manifest`
- `/api/factory-supervisor/copilot/answers`
- `/api/factory-supervisor/defer-queue`
- `/api/factory-supervisor/defer-queue/cancel`
- `/api/factory-supervisor/defer-queue/expire-overdue`
- `/api/factory-supervisor/defer-queue/stats`
- `/api/factory-supervisor/eligibility`
- `/api/factory-supervisor/events`
- `/api/factory-supervisor/events/stats`
- `/api/factory-supervisor/fag/proposals`
- `/api/factory-supervisor/fleet`
- `/api/factory-supervisor/heartbeat-status`
- `/api/factory-supervisor/heartbeats`
- `/api/factory-supervisor/lock`
- `/api/factory-supervisor/lock/release`
- `/api/factory-supervisor/notifications`
- `/api/factory-supervisor/notifications/acknowledge`
- `/api/factory-supervisor/notifications/unread-count`
- `/api/factory-supervisor/recommendations/top`
- `/api/factory-supervisor/remote-transport`
- `/api/factory-supervisor/routing-policy`
- `/api/factory-supervisor/scheduler/status`
- `/api/factory-supervisor/status`
- `/api/factory-supervisor/submissions`
- `/api/factory-supervisor/submissions/stats`
- `/api/factory-supervisor/submit`
- `/api/factory-supervisor/workers`
- `/api/factory-supervisor/workers/tick`
- `/api/fix-gaps`
- `/api/gem-factory/run`
- `/api/gem-factory/status`
- `/api/gem-factory/sweep-degradation`
- `/api/generate-cbot`
- `/api/governance/replacement-candidates`
- `/api/governance/survivor-registry`
- `/api/governance/universe`
- `/api/governance/universe/preview`
- `/api/health`
- `/api/import-server-file`
- `/api/ingestion/logs`
- `/api/ingestion/run`
- `/api/ingestion/status`
- `/api/ingestion/toggle`
- `/api/latent/activation-governance`
- `/api/latent/deployment-extras`
- `/api/latent/deployment-readiness`
- `/api/latent/ingestion-aggregate`
- `/api/latent/market-universe`
- `/api/latent/parity-certification`
- `/api/live/refresh-data`
- `/api/live/start`
- `/api/live/stop`
- `/api/live/strategies`
- `/api/live/update-all`
- `/api/llm/call-log/recent`
- `/api/llm/diagnostics`
- `/api/llm/runner-state`
- `/api/logs`
- `/api/market-data`
- `/api/market-intelligence/config`
- `/api/market-intelligence/rankings`
- `/api/market-intelligence/scan-eligible`
- `/api/master-bot`
- `/api/master-bot/candidates`
- `/api/master-bot/ranker/config`
- `/api/monitoring/status`
- `/api/mutation/mutate`
- `/api/optimization/best`
- `/api/optimization/config`
- `/api/optimization/history`
- `/api/optimization/portfolio-actions`
- `/api/optimization/run`
- `/api/orchestrator/env-priority/config`
- `/api/orchestrator/env-priority/reset`
- `/api/orchestrator/env-priority/sample`
- `/api/orchestrator/env-priority/stats`
- `/api/orchestrator/heartbeat`
- `/api/orchestrator/scheduler/start`
- `/api/orchestrator/scheduler/status`
- `/api/orchestrator/scheduler/stop`
- `/api/orchestrator/tick`
- `/api/phase4/match-firms`
- `/api/portfolio-builder/build`
- `/api/portfolio-builder/config`
- `/api/portfolio-builder/recent`
- `/api/portfolio-builder/save`
- `/api/portfolio-intelligence/build`
- `/api/portfolio-intelligence/config`
- `/api/portfolio-intelligence/current`
- `/api/portfolio-intelligence/history`
- `/api/portfolio/build`
- `/api/portfolio/status`
- `/api/prop-firm-analysis/batch-analyze`
- `/api/prop-firm-analysis/rules`
- `/api/prop-firm-rules`
- `/api/prop-firms/discover-challenges`
- `/api/prop-firms/extract`
- `/api/prop-firms/extract-jobs`
- `/api/prop-firms/intelligence/list`
- `/api/prop-firms/list`
- `/api/prop-firms/save`
- `/api/prop-firms/save-challenges`
- `/api/research-runs`
- `/api/run-pipeline`
- `/api/scaling/admission`
- `/api/scaling/admission/journal-stats`
- `/api/scaling/architect/snapshot`
- `/api/scaling/concurrency`
- `/api/scaling/events`
- `/api/scaling/events/stats`
- `/api/scaling/heartbeat`
- `/api/scaling/nodes`
- `/api/scaling/pressure`
- `/api/scaling/route`
- `/api/server-files`
- `/api/strategies`
- `/api/strategies/explorer`
- `/api/trade-runner/runs`
- `/api/trade-runner/start`
- `/api/tuning/events`
- `/api/tuning/overview`
- `/api/tuning/performance`
- `/api/tuning/performance/snapshot`
- `/api/tuning/settings`
- `/api/tuning/settings/reset`
- `/api/tuning/slot-stats`
- `/api/tuning/slot-stats/recommend`
- `/api/upload-data`