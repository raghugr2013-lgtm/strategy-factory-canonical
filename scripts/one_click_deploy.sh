#!/usr/bin/env bash
# ------------------------------------------------------------
# Strategy Factory v1.1 — one-click bootstrap
# ------------------------------------------------------------
# Zero-touch cold-start: bring up the stack, restore the v1.1
# baseline data, and run the 31-step acceptance verifier.
# Exit code 0 = release-ready. Non-zero = fail loudly.
#
# Usage: ./scripts/one_click_deploy.sh
# Requires: docker + docker compose plugin, .env at repo root.
# ------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "→ .env missing — bootstrapping from .env.example"
  cp "$ROOT/.env.example" "$ENV_FILE"
  echo "  edit $ENV_FILE and re-run this script."
  exit 2
fi

set -a; . "$ENV_FILE"; set +a

echo "→ building and starting containers"
docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" up -d --build

echo "→ waiting for backend health (up to 120 s)"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8001/api/health >/dev/null 2>&1; then
    echo "  backend healthy"
    break
  fi
  sleep 2
done

echo "→ restoring baseline MongoDB dump (idempotent)"
"$HERE/restore_baseline.sh" --drop || echo "  (baseline restore skipped — non-fatal)"

echo "→ running deployment acceptance (31 steps)"
BASE="http://localhost:8001" \
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@strategyfactory.dev}" \
ADMIN_PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set in .env}" \
  "$HERE/deploy_verify.sh"

echo
echo "✓ Strategy Factory v1.1 is live and acceptance-verified."
echo "  UI:  http://localhost:3000"
echo "  API: http://localhost:8001/api/openapi.json"
