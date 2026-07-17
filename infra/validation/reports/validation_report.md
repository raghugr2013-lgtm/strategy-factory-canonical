# Validation Report — 20260717T103745Z

- **Started:** 2026-07-17T10:37:45.649207+00:00
- **Finished:** 2026-07-17T10:37:49.953772+00:00
- **Duration:** 4.30s
- **Base URL:** `http://localhost:8001`

## Aggregate

| Metric | Value |
|--------|-------|
| Total probes | 83 |
| PASS | 83 |
| FAIL | 0 |
| WARN | 0 |
| Average latency (ms) | 50.24 |
| p95 latency (ms) | 13.71 |
| Fastest (ms) | 1.03 |
| Slowest (ms) | 1549.52 |
| Total response bytes | 17327811 |

## Module: `health`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | health_endpoint | GET | `/api/health` | PASS | 200 | 1.0 | 168 | - |
| 2 | deployment_registry | GET | `/api/deployment/registry` | PASS | 200 | 2.2 | 143 | - |
| 3 | orchestrator_tasks_ok | GET | `/api/orchestrator/tasks` | PASS | 200 | 2.3 | 6036 | - |
| 4 | auth_me | GET | `/api/auth/me` | PASS | 200 | 1.3 | 342 | - |

## Module: `authentication`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | jwt_valid_me | GET | `/api/auth/me` | PASS | 200 | 1.2 | 342 | - |
| 2 | reject_bad_credentials | POST | `/api/auth/login` | PASS | 422 | 0.0 | 146 | got HTTP 422, expected 401/400/422 |
| 3 | unauth_requires_token | GET | `/api/auth/me` | PASS | 401 | 0.0 | 33 | - |

## Module: `strategy_engineering`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | phase1_create | POST | `/api/strategies` | PASS | 201 | 2.5 | 284 | - |
| 2 | phase1_list_shape | GET | `/api/strategies` | PASS | 200 | 2.2 | 559 | - |
| 3 | phase1_get_by_id | GET | `/api/strategies/5c49c84f68c448fc` | PASS | 200 | 1.9 | 282 | - |
| 4 | phase1_delete_by_id | DELETE | `/api/strategies/5c49c84f68c448fc` | PASS | 204 | 1.8 | 0 | - |
| 5 | phase1_deleted_404 | GET | `/api/strategies/5c49c84f68c448fc` | PASS | 404 | 1.7 | 31 | - |
| 6 | generate_strategy | POST | `/api/generate-strategy` | PASS | 200 | 77.1 | 603 | - |
| 7 | run_backtest | POST | `/api/run-backtest` | PASS | 422 | 3.0 | 96 | - |
| 8 | rank_strategies | POST | `/api/rank-strategies` | PASS | 422 | 2.0 | 93 | - |
| 9 | save_strategy | POST | `/api/save-strategy` | PASS | 422 | 2.1 | 251 | - |
| 10 | validate_strategy | POST | `/api/validate-strategy` | PASS | 422 | 2.0 | 96 | - |
| 11 | optimize_strategy | POST | `/api/optimize-strategy` | PASS | 422 | 1.8 | 96 | - |
| 12 | mutate_strategy | POST | `/api/mutate-strategy` | PASS | 400 | 1.7 | 57 | - |
| 13 | analyze_strategy | POST | `/api/analyze-strategy` | PASS | 422 | 1.8 | 96 | - |
| 14 | compare_strategies | POST | `/api/strategies/compare` | PASS | 422 | 2.0 | 95 | - |
| 15 | legacy_list_wrapper | GET | `/api/legacy/strategies` | PASS | 200 | 2.9 | 333 | - |
| 16 | legacy_wrapper_shape | GET | `/api/legacy/strategies` | PASS | 200 | 5.5 | 333 | - |

## Module: `portfolio`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | get_config | GET | `/api/portfolio-intelligence/config` | PASS | 200 | 2.3 | 252 | - |
| 2 | list_masterbots | GET | `/api/master-bot` | PASS | 200 | 2.4 | 28 | - |
| 3 | recent_bundles | GET | `/api/portfolio-intelligence/history` | PASS | 200 | 2.4 | 24 | - |
| 4 | analyze | POST | `/api/portfolio-analyze` | PASS | 422 | 2.1 | 95 | - |
| 5 | auto_build | POST | `/api/portfolio-auto-build` | PASS | 400 | 5.0 | 63 | - |
| 6 | live_allocation | POST | `/api/portfolio-live-allocation` | PASS | 422 | 2.1 | 95 | - |
| 7 | rebalance_config | GET | `/api/rebalance/config` | PASS | 200 | 2.2 | 202 | - |
| 8 | allocation_history | GET | `/api/allocation-history` | PASS | 200 | 2.3 | 115 | - |

## Module: `propfirm`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | challenge_firms | GET | `/api/challenge-firms` | PASS | 200 | 3.9 | 3850 | - |
| 2 | challenge_rules | GET | `/api/challenge-rules` | PASS | 200 | 3.5 | 4916 | - |
| 3 | match_strategy | POST | `/api/match-strategy` | PASS | 400 | 1.7 | 59 | - |
| 4 | profile_strategy | POST | `/api/profile-strategy` | PASS | 400 | 1.8 | 59 | - |
| 5 | estimate_prob | POST | `/api/estimate-probability` | PASS | 400 | 1.6 | 59 | - |
| 6 | simulate_challenge | POST | `/api/simulate-challenge` | PASS | 400 | 1.6 | 59 | - |
| 7 | safety_check | POST | `/api/safety-check` | PASS | 422 | 1.5 | 96 | - |

## Module: `market_intelligence`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | config | GET | `/api/market-intelligence/config` | PASS | 200 | 1.0 | 188 | - |
| 2 | rankings | GET | `/api/market-intelligence/rankings` | PASS | 200 | 1.3 | 29 | - |
| 3 | state_snapshot | GET | `/api/market-intelligence/state` | PASS | 422 | 1.5 | 90 | - |
| 4 | state_history | GET | `/api/market-intelligence/state/history` | PASS | 422 | 1.7 | 90 | - |
| 5 | recent_changes | GET | `/api/market-intelligence/changes` | PASS | 200 | 2.0 | 36 | - |
| 6 | observers_config | GET | `/api/market-intelligence/observers/config` | PASS | 200 | 1.5 | 553 | - |
| 7 | aggregate | GET | `/api/market-intelligence/intelligence` | PASS | 422 | 1.6 | 90 | - |

## Module: `execution_intelligence`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | config | GET | `/api/execution/config` | PASS | 200 | 1.5 | 721 | - |
| 2 | status | GET | `/api/execution/status` | PASS | 200 | 2.1 | 47 | - |
| 3 | orders | GET | `/api/execution/orders` | PASS | 200 | 1.9 | 23 | - |
| 4 | fills | GET | `/api/execution/fills` | PASS | 200 | 1.9 | 22 | - |
| 5 | positions | GET | `/api/execution/positions` | PASS | 200 | 5.5 | 26 | - |
| 6 | quality | GET | `/api/execution/quality` | PASS | 422 | 1.6 | 90 | - |
| 7 | attribution | GET | `/api/execution/attribution` | PASS | 422 | 1.5 | 99 | - |
| 8 | risk_status | GET | `/api/execution/risk/status` | PASS | 200 | 2.5 | 60 | - |
| 9 | broker_health | GET | `/api/execution/broker/health` | PASS | 200 | 1.8 | 411 | - |
| 10 | paper_config | GET | `/api/execution/paper/config` | PASS | 200 | 1.3 | 207 | - |
| 11 | journal_recent | GET | `/api/execution/journal?limit=5` | PASS | 200 | 2.0 | 46 | - |

## Module: `meta_learning`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | mode_is_observe | GET | `/api/meta-learning/config` | PASS | 200 | 1.6 | 752 | - |
| 2 | cycle_refresh_force | POST | `/api/meta-learning/refresh?force=true` | PASS | 200 | 666.1 | 226 | - |
| 3 | pending_list | GET | `/api/meta-learning/pending` | PASS | 200 | 2.6 | 24 | - |
| 4 | observe_zero_overrides | GET | `/api/meta-learning/overrides` | PASS | 200 | 2.1 | 26 | - |
| 5 | observe_zero_apps | GET | `/api/meta-learning/applications` | PASS | 200 | 2.1 | 29 | - |
| 6 | approve_blocked_409 | POST | `/api/meta-learning/recommendations/x/approve` | PASS | 409 | 1.8 | 90 | - |
| 7 | evaluations | GET | `/api/meta-learning/evaluations?limit=10` | PASS | 200 | 2.2 | 28 | - |
| 8 | recommendations | GET | `/api/meta-learning/recommendations?limit=10` | PASS | 200 | 1.9 | 32 | - |
| 9 | mode_history | GET | `/api/meta-learning/mode-history` | PASS | 200 | 1.7 | 24 | - |

## Module: `factory_evaluation`

| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |
|---|------|--------|------|--------|------|----|-------|--------|
| 1 | mode_is_observe | GET | `/api/factory-eval/config` | PASS | 200 | 1.3 | 782 | - |
| 2 | cycle_refresh_force | POST | `/api/factory-eval/refresh?force=true` | PASS | 200 | 1549.5 | 213 | - |
| 3 | observe_zero_overrides | GET | `/api/factory-eval/overrides` | PASS | 200 | 2.9 | 26 | - |
| 4 | observe_zero_apps | GET | `/api/factory-eval/applications` | PASS | 200 | 2.2 | 29 | - |
| 5 | approve_blocked_409 | POST | `/api/factory-eval/recommendations/x/approve` | PASS | 409 | 4.7 | 89 | - |
| 6 | reports_list | GET | `/api/factory-eval/reports?limit=5` | PASS | 200 | 1328.1 | 14393086 | - |
| 7 | reports_latest | GET | `/api/factory-eval/reports/latest` | PASS | 200 | 253.3 | 2878622 | - |
| 8 | kpis | GET | `/api/factory-eval/kpis` | PASS | 200 | 13.7 | 330 | - |
| 9 | insights | GET | `/api/factory-eval/insights?limit=10` | PASS | 200 | 7.4 | 5632 | - |
| 10 | pending | GET | `/api/factory-eval/pending` | PASS | 200 | 2.6 | 6524 | - |
| 11 | providers_lead | GET | `/api/factory-eval/providers/leaderboard` | PASS | 200 | 13.0 | 390 | - |
| 12 | top_strategies | GET | `/api/factory-eval/strategies/top-contributors` | PASS | 200 | 3.3 | 20 | - |
| 13 | pruning_cands | GET | `/api/factory-eval/strategies/pruning-candidates` | PASS | 200 | 2.3 | 27 | - |
| 14 | portfolio_trends | GET | `/api/factory-eval/portfolios/health-trends` | PASS | 200 | 2.2 | 23 | - |
| 15 | path_rankings | GET | `/api/factory-eval/execution/path-rankings` | PASS | 200 | 2.1 | 22 | - |
| 16 | regime_eff | GET | `/api/factory-eval/regimes/effectiveness` | PASS | 200 | 2.1 | 24 | - |
| 17 | bottlenecks | GET | `/api/factory-eval/bottlenecks` | PASS | 200 | 3.3 | 12105 | - |
| 18 | coverage_gaps | GET | `/api/factory-eval/coverage-gaps` | PASS | 200 | 2.4 | 5321 | - |
