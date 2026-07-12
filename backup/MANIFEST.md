# Strategy Factory v1.1 — MongoDB baseline dump manifest

**File:** `backup/strategy_factory_v1.1_baseline.archive`  (gzip mongodump archive)

**Source DB:** `test_database` (preview) — restore into `${FACTORY_DB_NAME}` on target.

**Format:** mongodump 6.0 `--archive --gzip`


## Collections & document counts

| Collection | Documents |
|------------|-----------|
| `admission_journal` | 0 |
| `advisory_locks` | 0 |
| `asf_import_actions` | 27,100 |
| `asf_import_log` | 2 |
| `audit_log` | 68 |
| `auto_factory_alert_log` | 13 |
| `auto_factory_config` | 1 |
| `auto_run_cycles` | 0 |
| `bi5_cert_sweep_log` | 28 |
| `bi5_cert_sweep_runs` | 4 |
| `bi5_certification` | 3 |
| `bi5_data_certification` | 15 |
| `bi5_ingest_log` | 4 |
| `calibration_outcomes` | 0 |
| `calibration_tables` | 0 |
| `cbot_parity_signoff` | 0 |
| `challenge_rules` | 3 |
| `factory_supervisor_defer_queue` | 0 |
| `factory_supervisor_fag_proposals` | 0 |
| `factory_supervisor_heartbeats` | 0 |
| `factory_supervisor_lock` | 0 |
| `factory_supervisor_submissions` | 0 |
| `governance_universe` | 1 |
| `host_capabilities` | 2 |
| `ingested_strategies` | 5 |
| `llm_call_log` | 0 |
| `market_data` | 313,777 |
| `market_spread` | 309,950 |
| `market_universe_audit` | 476 |
| `market_universe_symbols` | 7 |
| `master_bot_deployments` | 0 |
| `master_bot_members` | 0 |
| `master_bot_ranker_config` | 1 |
| `master_bot_runners` | 0 |
| `master_bot_tiers` | 0 |
| `master_bots` | 0 |
| `multi_cycle_runs` | 0 |
| `mutation_events` | 10,430 |
| `mutation_stability_log` | 1,042 |
| `notifications` | 0 |
| `orchestrator_env_priority` | 1 |
| `pipeline_logs` | 0 |
| `post_import_pipeline_log` | 3 |
| `prop_firm_rules` | 3 |
| `refresh_tokens` | 30 |
| `risk_of_ruin_evaluations` | 0 |
| `runner_accounts` | 0 |
| `runner_token_rotation_history` | 0 |
| `scaling_events` | 0 |
| `scaling_nodes` | 0 |
| `strategies` | 1 |
| `strategy_library` | 14 |
| `strategy_library_archive` | 126 |
| `strategy_lifecycle` | 0 |
| `strategy_lifecycle_history` | 892 |
| `strategy_performance_history` | 1,047 |
| `users` | 1 |
| **TOTAL** | **665,050** |

## Restore command

```bash
# Local docker-compose (bundled mongo)
docker exec -i factory-mongo mongorestore \
    --nsFrom 'test_database.*' --nsTo '${FACTORY_DB_NAME}.*' \
    --archive --gzip --drop < backup/strategy_factory_v1.1_baseline.archive

# Production (external mongo)
mongorestore --uri "${SHARED_MONGO_URL}" \
    --nsFrom 'test_database.*' --nsTo '${FACTORY_DB_NAME}.*' \
    --archive --gzip --drop < backup/strategy_factory_v1.1_baseline.archive
```
