#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# phase1_validate.sh — one-shot validation harness for the VPS
#
# Purpose: gather every signal the Phase-1 sign-off gate requires
# and print a single, copy-pasteable output block. Idempotent,
# read-only, safe to run at any moment on a live production VPS.
#
# Usage (on the VPS):
#   sudo -u <docker-user> /opt/strategy-factory/infra/scripts/phase1_validate.sh
#   sudo -u <docker-user> /opt/strategy-factory/infra/scripts/phase1_validate.sh > /tmp/phase1-validation.txt
#
# The output is designed to be pasted straight into
# `docs/PHASE_1_FACTORY_VALIDATION_REPORT.md` (the template ships
# with placeholders keyed to this script's section headers).
#
# Nothing here writes to any collection, mutates any container, or
# starts/stops any service. Safe to run 100× a day.
# ─────────────────────────────────────────────────────────────────

set -u
LC_ALL=C

ROOT="${STRATEGY_FACTORY_ROOT:-/opt/strategy-factory}"
COMPOSE_FILE="${ROOT}/infra/compose/docker-compose.prod.yml"
ENV_FILE="${ROOT}/.env"
API="${FACTORY_API_URL:-http://127.0.0.1:8001}"
PUBLIC_API="${FACTORY_PUBLIC_API_URL:-}"

# ── helpers ─────────────────────────────────────────────────────
_hr() { printf '\n──── %-60s ────\n' "$1"; }
_kv() { printf '  %-38s %s\n' "$1" "${2:-}"; }
_json() { python3 -c 'import sys, json; d=json.load(sys.stdin); print(json.dumps(d, indent=2, default=str))' 2>/dev/null || cat; }
_env_get() { grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | sed "s/^${1}=//" ; }

echo "════════════════════════════════════════════════════════════════"
echo "  Strategy Factory — Phase 1 Validation"
echo "  Host      : $(hostname)"
echo "  Timestamp : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  Root      : $ROOT"
echo "════════════════════════════════════════════════════════════════"

# ═════════════════════════════════════════════════════════════════
_hr "1 · Repo state"
# ═════════════════════════════════════════════════════════════════
cd "$ROOT" 2>/dev/null || { echo "  !! $ROOT missing"; exit 2; }
_kv "HEAD SHA"              "$(git rev-parse HEAD 2>/dev/null)"
_kv "Branch"                "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
_kv "Working tree clean?"   "$(git status --porcelain 2>/dev/null | head -1 || echo 'yes')"
_kv "origin/main equal?"    "$([ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main 2>/dev/null)" ] && echo 'yes' || echo 'NO — investigate')"

# ═════════════════════════════════════════════════════════════════
_hr "2 · Env file activation flags (read-only)"
# ═════════════════════════════════════════════════════════════════
if [ ! -f "$ENV_FILE" ]; then
  echo "  !! $ENV_FILE missing"
else
  for k in FACTORY_RUNNER_OWNS_SCHEDULERS ORCHESTRATOR_ENABLED BUDGET_PERSIST MI_ENABLED \
           LEARNING_SCHEDULER_ENABLED LEARNING_CONTINUOUS_MODE \
           META_LEARNING_MODE FACTORY_EVAL_MODE EXEC_ENABLED FACTORY_RUNNER_HEARTBEAT_SEC; do
    _kv "$k" "$(_env_get "$k")"
  done
fi

# ═════════════════════════════════════════════════════════════════
_hr "3 · Compose sanity"
# ═════════════════════════════════════════════════════════════════
if command -v docker >/dev/null 2>&1; then
  # Valid compose file with env
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/tmp/.pf-compose-config.yml 2>/tmp/.pf-compose-err
  _kv "compose config --env-file"  "$([ $? -eq 0 ] && echo OK || echo "FAIL: $(cat /tmp/.pf-compose-err | head -1)")"
  # Interpolation guards
  docker compose -f "$COMPOSE_FILE" config >/dev/null 2>/tmp/.pf-compose-err
  if [ $? -ne 0 ] && grep -q 'SHARED_MONGO_URL' /tmp/.pf-compose-err; then
    _kv "interpolation guard fires without --env-file"  "OK (SHARED_MONGO_URL diagnostic)"
  else
    _kv "interpolation guard fires without --env-file"  "REGRESSION — guards not firing"
  fi
else
  _kv "docker CLI"  "not installed — cannot run compose parse tests"
fi

# ═════════════════════════════════════════════════════════════════
_hr "4 · Container inventory + Docker healthchecks"
# ═════════════════════════════════════════════════════════════════
for c in factory-backend factory-frontend factory-vie factory-runner factory-mongo caddy; do
  if docker inspect "$c" >/dev/null 2>&1; then
    state=$(docker inspect "$c" --format '{{.State.Status}}')
    hc=$(docker inspect "$c" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}')
    started=$(docker inspect "$c" --format '{{.State.StartedAt}}')
    _kv "$c" "$state / $hc  (started $started)"
  else
    _kv "$c" "MISSING"
  fi
done
echo
echo "  --- vqb-network membership ---"
docker network inspect vqb-network --format '{{range $k, $v := .Containers}}    {{$v.Name}}: {{$v.IPv4Address}}
{{end}}' 2>/dev/null || echo "    vqb-network missing"

# ═════════════════════════════════════════════════════════════════
_hr "5 · Backend health + readiness"
# ═════════════════════════════════════════════════════════════════
docker exec factory-backend curl -fsS -m 5 "$API/api/health"    2>&1 | _json | sed 's/^/    /'
echo
docker exec factory-backend curl -fsS -m 5 "$API/api/readiness" 2>&1 | _json | sed 's/^/    /'

if [ -n "$PUBLIC_API" ]; then
  echo
  echo "  --- public reachability ($PUBLIC_API) ---"
  curl -fsS -m 5 -o /dev/null -w '    /api/health         → HTTP %{http_code} · ttfb %{time_starttransfer}s\n' "$PUBLIC_API/api/health"
  curl -fsS -m 5 -o /dev/null -w '    /                   → HTTP %{http_code} · ttfb %{time_starttransfer}s\n' "$PUBLIC_API/"
fi

# ═════════════════════════════════════════════════════════════════
_hr "6 · Auth-scoped autonomous factory endpoints"
# ═════════════════════════════════════════════════════════════════
ADMIN_EMAIL_V=$(_env_get ADMIN_EMAIL)
ADMIN_PASS_V=$(_env_get ADMIN_PASSWORD)

if [ -n "$ADMIN_EMAIL_V" ] && [ -n "$ADMIN_PASS_V" ]; then
  TOKEN=$(docker exec factory-backend curl -sS -m 5 -X POST "$API/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL_V\",\"password\":\"$ADMIN_PASS_V\"}" 2>/dev/null \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("access_token") or d.get("token") or "")' 2>/dev/null)
  if [ -n "$TOKEN" ]; then
    _kv "admin token acquired"  "yes"

    echo
    echo "  --- /api/orchestrator/status ---"
    docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" "$API/api/orchestrator/status" \
      | python3 -c 'import sys,json
d=json.load(sys.stdin)
print(f"    running               : {d.get(\"running\")}")
print(f"    enabled_by_env        : {d.get(\"enabled_by_env\")}")
m=d.get("meta",{}) or {}
print(f"    tick_count            : {m.get(\"tick_count\")}")
print(f"    dispatched_total      : {m.get(\"dispatched_total\")}")
print(f"    last_error            : {m.get(\"last_error\")}")
lt=(m.get("last_tick") or {})
print(f"    last_tick.band        : {lt.get(\"band\")}")
print(f"    last_tick.in_flight   : {lt.get(\"in_flight\")}")
print(f"    in_flight (now)       : {len(d.get(\"in_flight\") or [])}")
print(f"    task_names_count      : {len(d.get(\"task_names\") or [])}")
c=d.get("counters",{}) or {}
print(f"    counters.runs_total   : {c.get(\"runs_total\")}")
print(f"    counters.runs_ok      : {c.get(\"runs_ok\")}")
print(f"    counters.runs_fail    : {c.get(\"runs_fail\")}")' 2>&1 | sed 's/^/    /'

    echo
    echo "  --- /api/orchestrator/decisions?limit=5 ---"
    docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" "$API/api/orchestrator/decisions?limit=5" \
      | python3 -c 'import sys,json
for d in json.load(sys.stdin)[-5:]:
  launched=d.get("launched",[])
  print(f"    tick={d.get(\"tick_id\",\"?\")[:14]} band={d.get(\"band\")} in_flight={d.get(\"in_flight\")} launched={[l[\"task_name\"] for l in launched]}")' 2>&1 | sed 's/^/    /'

    echo
    echo "  --- /api/meta-learning/config ---"
    docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" "$API/api/meta-learning/config" \
      | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"    mode={d.get(\"mode\")} cadence_s={d.get(\"cadence_s\")}")' 2>&1 | sed 's/^/    /'

    echo
    echo "  --- /api/factory-eval/config ---"
    docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" "$API/api/factory-eval/config" \
      | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"    mode={d.get(\"mode\")} cadence_s={d.get(\"cadence_s\")}")' 2>&1 | sed 's/^/    /'

    echo
    echo "  --- /api/knowledge/statistics ---"
    docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" "$API/api/knowledge/statistics" 2>/dev/null \
      | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"    total_strategies={d.get(\"total_strategies\")} families={d.get(\"families\")} champions={d.get(\"champions\")}")' 2>&1 | sed 's/^/    /'
  else
    _kv "admin token acquired"  "FAIL — /api/auth/login returned no token"
  fi
else
  echo "    ADMIN_EMAIL/ADMIN_PASSWORD not set in .env — skipping auth-scoped probes"
fi

# ═════════════════════════════════════════════════════════════════
_hr "7 · Ledger reconciliation (last 24 h)"
# ═════════════════════════════════════════════════════════════════
DBN=$(_env_get FACTORY_DB_NAME); DBN=${DBN:-strategy_factory_v1}
docker exec factory-mongo mongosh --quiet --eval "
db = db.getSiblingDB('${DBN}');
const since = new Date(Date.now() - 24*3600*1000);
function count(coll, field) {
  try { return db[coll].countDocuments({[field]: {\$gte: since}}); }
  catch (_) {
    try { return db[coll].countDocuments({[field]: {\$gte: since.toISOString()}}); }
    catch (_) { return -1; }
  }
}
print('    audit_log(ts,24h)              : ' + count('audit_log', 'ts'));
print('    outcome_events(ts_dt,24h)      : ' + count('outcome_events', 'ts_dt'));
print('    strategies(created_at,24h)     : ' + count('strategies', 'created_at'));
print('    backtest_reports(created_at)   : ' + count('backtest_reports', 'created_at'));
print('    validation_reports(created_at) : ' + count('validation_reports', 'created_at'));
print('    ranking_snapshots(created_at)  : ' + count('ranking_snapshots', 'created_at'));
print('    meta_learning_evaluations      : ' + count('meta_learning_evaluations', 'created_at'));
print('    meta_learning_applications     : ' + count('meta_learning_applications', 'created_at') + '  (must stay 0 in OBSERVE)');
print('    factory_eval_reports           : ' + count('factory_eval_reports', 'created_at'));
print('    factory_eval_applications      : ' + count('factory_eval_applications', 'created_at') + '  (must stay 0 in OBSERVE)');
print('    market_intelligence_snapshots  : ' + count('market_intelligence_snapshots', 'created_at'));
print('    research_lineage_events        : ' + count('research_lineage_events', 'ts_dt'));
print('    -- Sibling runner heartbeats (audit_log/factory_runner*, last 30min):');
db.audit_log.find({event: /factory_runner/, ts: {\$gte: new Date(Date.now()-30*60*1000).toISOString()}})
  .sort({ts:-1}).limit(3).forEach(r => print('      ' + r.event + '  pid=' + (r.data && r.data.pid) + '  ' + r.ts));
" 2>&1 | sed 's/^/  /'

# ═════════════════════════════════════════════════════════════════
_hr "8 · Recent orchestrator log fingerprints (backend, last 400 lines)"
# ═════════════════════════════════════════════════════════════════
docker logs --tail 400 factory-backend 2>&1 \
  | grep -E 'orchestrator|budget_tracker|market_intelligence|meta_learning|factory_eval|\[orchestrator\] ' \
  | tail -30 | sed 's/^/    /'

echo
echo "  --- factory-runner (last 40 lines) ---"
docker logs --tail 40 factory-runner 2>&1 | sed 's/^/    /'

# ═════════════════════════════════════════════════════════════════
_hr "9 · Heartbeat file freshness"
# ═════════════════════════════════════════════════════════════════
docker exec factory-runner bash -c '
  if [ -f /tmp/factory_runner.hb ]; then
    now=$(date +%s); ts=$(cat /tmp/factory_runner.hb); age=$((now - ts));
    echo "    hb file present · epoch=$ts · age=${age}s · $([ $age -lt 120 ] && echo GREEN || echo YELLOW)";
  else echo "    !! /tmp/factory_runner.hb missing"; fi'

echo
echo "════════════════════════════════════════════════════════════════"
echo "  Validation complete. Paste this whole block into"
echo "  docs/PHASE_1_FACTORY_VALIDATION_REPORT.md and email/DM back."
echo "════════════════════════════════════════════════════════════════"
