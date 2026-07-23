# Strategy Factory — Phase 1 Factory KPI Report

**Status:** template — fill from `phase1_validate.sh` output + the
supplementary Mongo queries below.
**Companion to:** `docs/PHASE_1_FACTORY_VALIDATION_REPORT.md`,
`docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md` (§4 ledger recon).

**Cadence:** run every 24 h during the first week of continuous
operation; then weekly.

---

## Report metadata

| Field | Value |
|-------|-------|
| Reporting window (UTC) | `<start>` → `<end>` |
| Window length | `<hours>` |
| Repo SHA at start of window | `<sha>` |
| Repo SHA at end of window (if a deploy landed mid-window) | `<sha>` |
| Orchestrator running for entire window? | `<yes/no>` |
| Budget cap (USD/day) | `<int>` |
| Budget used (USD in window) | `<float>` |

---

## Section 1 · Cycle throughput (24 h window)

Run:

```bash
DBN=$(grep '^FACTORY_DB_NAME=' /opt/strategy-factory/.env | cut -d= -f2)
DBN=${DBN:-strategy_factory_v1}
docker exec factory-mongo mongosh --quiet --eval "
db = db.getSiblingDB('$DBN');
const since = new Date(Date.now() - 24*3600*1000);
function C(coll, field) {
  try { return db[coll].countDocuments({[field]: {\$gte: since}}); }
  catch (_) { try { return db[coll].countDocuments({[field]: {\$gte: since.toISOString()}}); } catch(_) { return -1; } }
}
print(JSON.stringify({
  audit_log:               C('audit_log', 'ts'),
  outcome_events:          C('outcome_events', 'ts_dt'),
  strategies_created:      C('strategies', 'created_at'),
  backtest_reports:        C('backtest_reports', 'created_at'),
  validation_reports:      C('validation_reports', 'created_at'),
  ranking_snapshots:       C('ranking_snapshots', 'created_at'),
  meta_learning_evals:     C('meta_learning_evaluations', 'created_at'),
  meta_learning_apps:      C('meta_learning_applications', 'created_at'),
  factory_eval_reports:    C('factory_eval_reports', 'created_at'),
  factory_eval_apps:       C('factory_eval_applications', 'created_at'),
  mi_snapshots:            C('market_intelligence_snapshots', 'created_at'),
  research_lineage_events: C('research_lineage_events', 'ts_dt'),
  bi5_certifications:      C('bi5_certification', 'created_at'),
}, null, 2));
"
```

Fill in:

| Cycle stage | 24 h count | Cadence expected | Verdict |
|-------------|-----------|------------------|---------|
| Market data refresh (`bi5_certification`) | `<int>` | 1 per pair per day | `<green/yellow/red>` |
| Knowledge index refresh (implicit — read-only) | (see log grep for `knowledge_index_refresh`) | 1 per day | `<>` |
| Market intelligence snapshots | `<int>` | depends on `MI_CADENCE_S`, typically 4–24 per day | `<>` |
| Strategies created | `<int>` | ≥ 1 per successful `strategy_generate` tick | `<>` |
| Backtests completed (`backtest_reports`) | `<int>` | ≥ 1 per created strategy | `<>` |
| Validation jobs (`validation_reports`) | `<int>` | ≥ 1 per promoted strategy | `<>` |
| Ranking snapshots | `<int>` | ≥ 1 per ranking cadence | `<>` |
| Strategy Passports created | derived (any new `strategies` row can be Passport-rendered) | `<>` |
| Meta-learning evaluations | `<int>` | 1 per `meta_learning_evaluation` tick | `<>` |
| **Meta-learning applications** | **`0`** (contract — OBSERVE) | `0` | must be `0` |
| Factory-eval reports | `<int>` | 1 per `factory_evaluation` tick | `<>` |
| **Factory-eval applications** | **`0`** (contract — OBSERVE) | `0` | must be `0` |
| Outcome events (all sources) | `<int>` | rising | `<>` |
| Research lineage events | `<int>` | rising | `<>` |
| Audit log entries | `<int>` | rising | `<>` |

---

## Section 2 · Failed / skipped jobs (24 h window)

Run:

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/orchestrator/status" | jq '.counters'
```

Fill in:

| Task | `runs_total` | `runs_ok` | `runs_fail` | Fail rate | Verdict |
|------|--------------|-----------|-------------|-----------|---------|
| backtest | | | | | |
| mutation | | | | | |
| optimization | | | | | |
| ranking | | | | | |
| validation | | | | | |
| strategy_generate | | | | | |
| learning_cycle | | | | | |
| market_data_topup | | | | | |
| knowledge_index_refresh | | | | | |
| market_intelligence_refresh | | | | | |
| master_bot_bundle_refresh | | | | | |
| meta_learning_evaluation | | | | | |
| factory_evaluation | | | | | |
| self_rebuild | | | | | |
| bi5_realism_sweep | | | | | |
| broker_health_check | | | | | |
| execution_attribution | | | | | (dormant with EXEC_ENABLED=false — 0/0 is expected) |

Skipped-due-to-readiness inspection (top-5 reasons):

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/orchestrator/decisions?limit=200" | python3 -c "
import sys, json, collections
data = json.load(sys.stdin)
reasons = collections.Counter()
for d in data:
  for c in (d.get('candidates') or []):
    if not c.get('eligible'):
      reasons[(c.get('task_name'), c.get('reason','?'))[:80]] += 1
for k, v in reasons.most_common(15):
  print(f'{v:5d}  {k}')"
```

Paste the top-15 skip reasons here:

```
<paste>
```

---

## Section 3 · Average cycle duration

Run per task (repeat for each of the 17):

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/orchestrator/decisions?limit=1000" > /tmp/decisions.json
python3 <<'PY'
import json, statistics as st
data = json.load(open('/tmp/decisions.json'))
launches = {}
for d in data:
    for l in (d.get('launched') or []):
        launches.setdefault(l['task_name'], []).append(l['score'])
for t, scores in sorted(launches.items()):
    if scores:
        print(f"{t:32s} n={len(scores):4d}  score_mean={st.mean(scores):.3f}  score_p50={st.median(scores):.3f}")
PY
```

For task-level durations, tail the backend log for
`[orchestrator] <task> → ok=... dur_ms=<n>` lines and aggregate:

```bash
docker logs --tail 5000 factory-backend 2>&1 \
  | grep -E '^\[orchestrator\] .* dur_ms=' \
  | awk -F'[ =]' '{print $2, $NF}' \
  | sort | awk '
    {sum[$1]+=$2; cnt[$1]+=1; if ($2 > max[$1]) max[$1]=$2}
    END {for (t in sum) printf "%-32s n=%-5d avg_ms=%-8d max_ms=%d\n", t, cnt[t], int(sum[t]/cnt[t]), max[t]}'
```

Paste output:

```
<task>                              n=<int>  avg_ms=<int>  max_ms=<int>
```

Verdict:

- [ ] No task's `avg_ms` exceeds its cadence in ms (would indicate the
      task can't keep up with its own trigger frequency).
- [ ] No `max_ms` above `HARD_TIMEOUT_S * 900` (approaching hard timeout).

---

## Section 4 · Budget burn

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/orchestrator/status" | jq '.meta.budget'
```

Fill in:

| Field | Value |
|-------|-------|
| Daily cap USD | `<float>` |
| Used USD (window) | `<float>` |
| Utilisation % | `<%>` |
| Peak provider | `<name>` |

Verdict:

- [ ] Utilisation < 90 %. If ≥ 90 %, expand cap or investigate high-cost task.
- [ ] Budget rehydrated on last restart (`BUDGET_PERSIST=true`).

---

## Section 5 · Provider health (AI workforce)

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/ai-workforce/providers" | jq
```

Fill in:

| Provider | Configured | Circuit state | Requests (window) | Errors | p95 latency (ms) |
|----------|-----------|---------------|-------------------|--------|-------------------|
| openai   | | | | | |
| anthropic| | | | | |
| gemini   | | | | | |
| deepseek | | | | | |
| groq     | | | | | |
| kimi     | | | | | |

Verdict:

- [ ] No provider circuit `open` for > 15 min.
- [ ] Every configured provider has ≥ 1 successful request in window.

---

## Section 6 · Data pipeline

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/data/coverage" | jq '.summary // .'
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/data-maintenance/status" | jq
```

Fill in coverage by pair:

| Symbol | TF | Coverage % | Last cert | BI5 age (h) | Verdict |
|--------|----|-----------|-----------|-------------|---------|
| EURUSD | M1 | | | | |
| EURUSD | H1 | | | | |
| … | … | | | | |

Verdict:

- [ ] Every active pair ≥ 95 % coverage.
- [ ] No pair's `bi5_age_hours` exceeds `MAX_BI5_AGE_H` (default 168).

---

## Section 7 · Meta-learning signal (OBSERVE — read-only)

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/meta-learning/recommendations?limit=20" | jq
```

Summarise the top 5 policy recommendations the engine wants an operator
to consider (recorded, never auto-applied):

```
1. <recommendation summary + confidence>
2. …
```

Verdict:

- [ ] Recommendations write to `meta_learning_recommendations` at cadence.
- [ ] `meta_learning_applications = 0` (OBSERVE contract).

---

## Section 8 · Factory evaluation (OBSERVE — read-only)

```bash
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/factory-eval/kpis" | jq
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/factory-eval/recommendations?limit=20" | jq
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/factory-eval/providers/leaderboard" | jq
```

Paste highlights:

- Top 3 KPIs (headline numbers): `<>`
- Top 3 open recommendations: `<>`
- Provider leaderboard (best → worst): `<>`

Verdict:

- [ ] Reports write to `factory_eval_reports` at cadence.
- [ ] `factory_eval_applications = 0` (OBSERVE contract).

---

## Section 9 · Bottlenecks + follow-ups (free-form)

Prioritised list of the highest-value REFINEMENTS observed at
runtime — Reuse before Refine before Extend before Build New:

1. `<e.g. "provider X circuit open 40 % of window — investigate rate-limit or key rotation">`
2. `<e.g. "backtest task avg_ms 12k — check pool sizing headroom">`
3. `<e.g. "MI_CADENCE too aggressive for XAUUSD — spread analyser wobbling; lower cadence flag">`

The Implementation Roadmap Phase 2 list already covers the seven big
extensions. This section is for the small, runtime-observed
refinements you would not have known to do without operating the
system for 24 h.

---

## Sign-off

**KPI window verdict:** `GREEN / YELLOW / RED`
**Signed:** `<operator>`  ·  `<UTC timestamp>`
**Next report:** `<UTC>` (same window length)
