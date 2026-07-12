#!/usr/bin/env bash
# Strategy Factory — production smoke test.
# Exits 0 if all containers are healthy AND public https endpoints work.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'; else G=""; R=""; C=""; N=""; fi

pass=0; fail=0
ok(){ pass=$((pass+1)); echo "${G}✓${N} $1"; }
bad(){ fail=$((fail+1)); echo "${R}✗${N} $1" >&2; }

for c in factory-backend factory-vie factory-frontend; do
  state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "missing")
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$c" 2>/dev/null || echo "missing")
  [[ "$state" == "running" && ( "$health" == "healthy" || "$health" == "n/a" ) ]] \
    && ok "container ${c} → running (health=${health})" \
    || bad "container ${c} → state=${state}, health=${health}"
done

docker exec factory-backend curl -fsS --max-time 5 http://127.0.0.1:8001/api/health >/dev/null \
  && ok "in-cluster /api/health → 200" || bad "in-cluster /api/health failed"

docker exec factory-backend curl -fsS --max-time 5 http://factory-vie:8100/health >/dev/null \
  && ok "backend → VIE reachable" || bad "backend cannot reach VIE"

docker exec factory-frontend wget -qO- --tries=1 --timeout=3 http://127.0.0.1/healthz >/dev/null 2>&1 \
  && ok "frontend /healthz → 200" || bad "frontend /healthz failed"

# Full readiness probe — surfaces Mongo + VIE + Redis (skipped/green/yellow/red)
ready_json=$(docker exec factory-backend curl -fsS --max-time 10 http://127.0.0.1:8001/api/readiness 2>/dev/null || echo '{}')
mongo_s=$(echo "$ready_json" | python3 -c "import sys,json;print(json.load(sys.stdin).get('checks',{}).get('mongo',{}).get('status','?'))" 2>/dev/null || echo "?")
vie_s=$(echo "$ready_json"   | python3 -c "import sys,json;print(json.load(sys.stdin).get('checks',{}).get('vie',{}).get('status','?'))" 2>/dev/null || echo "?")
redis_s=$(echo "$ready_json" | python3 -c "import sys,json;print(json.load(sys.stdin).get('checks',{}).get('redis',{}).get('status','?'))" 2>/dev/null || echo "?")
[[ "$mongo_s" == "green" ]] && ok "readiness → mongo=$mongo_s" || bad "readiness → mongo=$mongo_s"
[[ "$vie_s"   == "green" ]] && ok "readiness → vie=$vie_s"     || bad "readiness → vie=$vie_s"
case "$redis_s" in
  green)   ok "readiness → redis=green" ;;
  skipped) ok "readiness → redis=skipped (SHARED_REDIS_URL not configured)" ;;
  yellow)  bad "readiness → redis=yellow" ;;
  red)     bad "readiness → redis=red" ;;
  *)       bad "readiness → redis=$redis_s" ;;
esac

if [[ -n "${FACTORY_DOMAIN:-}" ]]; then
  curl -fsS --max-time 8 "https://${FACTORY_DOMAIN}/api/health" -o /dev/null \
    && ok "public https://${FACTORY_DOMAIN}/api/health → 200" \
    || bad "public https://${FACTORY_DOMAIN}/api/health failed"
  curl -fsS --max-time 8 "https://${FACTORY_DOMAIN}/" -o /dev/null \
    && ok "public https://${FACTORY_DOMAIN}/ → 200" \
    || bad "public https://${FACTORY_DOMAIN}/ failed"
fi

echo
if [[ $fail -eq 0 ]]; then
  echo "${G}All checks passed${N} (${pass})"
  exit 0
else
  echo "${R}${fail} check(s) failed${N} (${pass} passed)"
  exit 1
fi
