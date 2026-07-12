#!/usr/bin/env bash
# ------------------------------------------------------------
# Strategy Factory v1.1 — one-click deployment verification
# ------------------------------------------------------------
# Runs the full 31-step E2E acceptance workflow against a live
# stack and prints a pass/fail summary. Exits non-zero on any
# failure so CI / freeze gates can key off the exit code.
# ------------------------------------------------------------
set -uo pipefail

BASE="${BASE:-${REACT_APP_BACKEND_URL:-http://localhost:8001}}"
EMAIL="${ADMIN_EMAIL:-admin@strategyfactory.dev}"
PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD required}"

pass=0; fail=0
step() {
  local desc="$1" method="$2" path="$3" data="${4:-}" hdr="${5:-}"
  if [ "$method" = "POST" ] && [ -n "$data" ]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE$path" -H "Content-Type: application/json" ${hdr:+-H "$hdr"} -d "$data" --max-time 10)
  elif [ "$method" = "POST" ]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE$path" ${hdr:+-H "$hdr"} --max-time 10)
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$path" ${hdr:+-H "$hdr"} --max-time 10)
  fi
  if [ "$code" = "200" ]; then
    printf "  ✓ %-40s %s %s\n" "$desc" "$method" "$path"
    pass=$((pass+1))
  else
    printf "  ✗ %-40s %s %s  [HTTP %s]\n" "$desc" "$method" "$path" "$code"
    fail=$((fail+1))
  fi
}

echo "→ Strategy Factory v1.1 deployment verification"
echo "  BASE=$BASE  EMAIL=$EMAIL"
echo

# Login
R=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" --max-time 10)
TOKEN=$(echo "$R" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('access_token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "✗ Login failed. Response: $R"
  exit 1
fi
AUTH="Authorization: Bearer $TOKEN"
echo "  ✓ Login (JWT obtained)"
pass=1

step "Fetch current user"              GET  /api/auth/me                          "" "$AUTH"
step "Backend version"                 GET  /api/version                          "" "$AUTH"
step "System health"                   GET  /api/health                           "" "$AUTH"
step "Dashboard summary"               GET  /api/dashboard/summary                "" "$AUTH"
step "Strategy library"                GET  /api/legacy/strategies                "" "$AUTH"
step "Auto Factory saved"              GET  /api/auto-factory/saved               "" "$AUTH"
step "Auto Selection recent"           GET  /api/auto-select/recent               "" "$AUTH"
step "Portfolio Builder recent"        GET  /api/portfolio-builder/recent         "" "$AUTH"
step "Portfolio status"                GET  /api/portfolio/status                 "" "$AUTH"
step "Prop firms list"                 GET  /api/prop-firms/list                  "" "$AUTH"
step "Prop firm rules"                 GET  /api/prop-firm-rules                  "" "$AUTH"
step "Monitoring status"               GET  /api/monitoring/status                "" "$AUTH"
step "Live strategies"                 GET  /api/live/strategies                  "" "$AUTH"
step "Orchestrator state"              GET  /api/orchestrator/state               "" "$AUTH"
step "Execution status"                GET  /api/execution/status                 "" "$AUTH"
step "Readiness"                       GET  /api/readiness                        "" "$AUTH"
step "Data coverage (BI5)"             GET  "/api/data-coverage?symbol=ETHUSD&tf=H1" "" "$AUTH"
step "BI5 health"                      GET  /api/diag/bi5/health                  "" "$AUTH"
step "Latent parity certification"     GET  /api/latent/parity-certification      "" "$AUTH"
step "Latent ingestion health"         GET  /api/latent/ingestion-health          "" "$AUTH"
step "Governance promotion ledger"     GET  /api/governance/promotion-ledger      "" "$AUTH"
step "Scaling nodes"                   GET  /api/scaling/nodes                    "" "$AUTH"
step "CPU pool state"                  GET  /api/cpu-pool/state                   "" "$AUTH"
step "Mutation events"                 GET  /api/mutation/events                  "" "$AUTH"
step "Regime cohort distribution"      GET  /api/regime/cohort-distribution       "" "$AUTH"
step "Optimization history"            GET  /api/optimization/history             "" "$AUTH"
step "Master Bot list"                 GET  /api/master-bot                       "" "$AUTH"
step "Challenge status"                GET  /api/challenge/status                 "" "$AUTH"
step "VIE LLM diagnostics"             GET  /api/llm/diagnostics                  "" "$AUTH"
step "Logout"                          POST /api/auth/logout                      ""  "$AUTH"

echo
total=$((pass+fail))
echo "→ Summary: $pass / $total PASS · $fail FAIL"
[ "$fail" = "0" ] && exit 0 || exit 1
