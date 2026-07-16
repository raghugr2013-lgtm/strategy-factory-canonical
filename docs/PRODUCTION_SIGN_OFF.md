# Backend Production Sign-Off — v1.2.0-alpha2

**Template.** Fill in each section before granting sign-off. Attach linked report files where indicated.

---

## Deployment identity

| Field | Value |
|-------|-------|
| Git tag | `v1.2.0-alpha2-feature-freeze` |
| Commit SHA | `___________________________________` |
| Deployed at (UTC) | `___________________________________` |
| VPS host | `___________________________________` |
| Operator | `___________________________________` |

---

## Boot verification

Attach `/tmp/baseline_status.json` (see POST_FREEZE_DEPLOYMENT_CHECKLIST §10).

- [ ] `legacy full-recovery mount: 100 routers/attachers online` present in boot log
- [ ] `meta_learning engine ready (mode=observe, cadence=900s)` present
- [ ] `factory_eval engine ready (mode=observe, cadence=3600s)` present
- [ ] 17 orchestrator tasks registered
- [ ] `Application startup complete` present

---

## Paper Broker Validation

Attach:
- `paper_flow_100_orders.json`
- `paper_flow_500_orders.json`
- `paper_flow_1000_orders.json`

| Workload | Verdict | Duration | Fills | Rejects | Journal seq monotonic |
|----------|---------|----------|-------|---------|----------------------|
| 100 orders | ______ | ______ | ______ | ______ | ______ |
| 500 orders | ______ | ______ | ______ | ______ | ______ |
| 1000 orders | ______ | ______ | ______ | ______ | ______ |

All three must be PASS with zero journal gaps.

---

## 24-hour Tier 5 validation

Attach `tier5_24h_report.json`.

| Metric | Threshold | Measured | Verdict |
|--------|-----------|----------|---------|
| Backend uptime | ≥ 99.5% | ______ | ______ |
| RSS memory drift | ≤ +25% over 24h | ______ | ______ |
| Orchestrator dispatch drift | ≤ 5% | ______ | ______ |
| Journal seq monotonic per account | 100% | ______ | ______ |
| `outcome_events` writes/s p95 | ≤ 200 | ______ | ______ |
| Mongo pool p95 | ≤ 80% saturated | ______ | ______ |
| `meta_learning_evaluation` cycles | ≥ 24 (hourly-ish under 24h) | ______ | ______ |
| `factory_evaluation` cycles | ≥ 24 | ______ | ______ |
| Zero override writes (OBSERVE) | 0 | ______ | ______ |
| Zero application writes (OBSERVE) | 0 | ______ | ______ |

---

## 72-hour Tier 5 validation

Attach `tier5_72h_report.json`.

Same table as 24h with thresholds:
- Uptime ≥ 99.9%
- RSS drift ≤ +40% over 72h
- All other invariants identical.

---

## Findings resolution log

| # | Finding | Severity | Fix commit | Verified in re-run |
|---|---------|----------|------------|--------------------|
| 1 | ______ | ______ | ______ | ______ |
| 2 | ______ | ______ | ______ | ______ |
| 3 | ______ | ______ | ______ | ______ |

If any HIGH severity finding remains unresolved, sign-off is BLOCKED.

---

## Rollback plan (mandatory record)

- **Instant kill**: `POST /api/execution/broker/kill-switch` (admin JWT).
- **Engine dormancy**: `META_LEARNING_MODE=disabled` + `FACTORY_EVAL_MODE=disabled` + `ORCHESTRATOR_ENABLED=false`.
- **Full rollback tag**: `git checkout <previous_release_tag>` + `supervisorctl restart backend`.
- **Data preserved**: Mongo state is fully forward/backward compatible; downgrade never drops collections.

Test the rollback path once (dry-run) BEFORE granting sign-off.

- [ ] Rollback dry-run executed successfully. Timestamp: `______________`

---

## Sign-off

I have reviewed all attached reports, verified the metrics, exercised the rollback path, and confirm this build is ready for continuous paper operation and (subject to a separate operator decision) transition to live broker.

**Operator signature:** `___________________________________`
**Date (UTC):** `___________________________________`
**Freeze tag:** `v1.2.0-alpha2-feature-freeze`

Only after this signature does the frontend implementation phase begin, strictly following `docs/UI_UX_MASTER_DESIGN_SPECIFICATION_v1.0.md`.
