#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# Strategy Factory — one-shot production bootstrap.
# Target: strategy.coinnike.com  (VPS 144.91.78.175)
#
# What it does (idempotent):
#   1. Ensures the shared `vqb-network` exists.
#   2. Brings up self-hosted MongoDB at /opt/factory-mongo.
#   3. Brings up Caddy (auto-HTTPS) at /opt/caddy.
#   4. Deploys the factory stack from the canonical repo at
#      /opt/strategy-factory  (clones/updates from
#      raghugr2013-lgtm/strategy-factory-canonical, branch main).
#   5. Runs health.sh and prints the final verdict.
#
# Prerequisites (already reported complete):
#   - Ubuntu 24.04 VPS, root/sudo.
#   - Docker + docker compose plugin installed.
#   - DNS A record: strategy.coinnike.com → this VPS's public IP.
#   - Ports 80, 443/tcp, 443/udp open in the firewall.
#
# Before running, you MUST place these files on the VPS:
#   /opt/factory-mongo/docker-compose.yml
#   /opt/factory-mongo/.env
#   /opt/caddy/docker-compose.yml
#   /opt/caddy/Caddyfile       (with the real Let's Encrypt email)
#   /opt/strategy-factory/.env (production .env for the repo root)
#
# Then simply run:  sudo bash /opt/factory-bootstrap.sh
# ────────────────────────────────────────────────────────────────
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "error: must run as root (sudo)" >&2; exit 1
fi

REPO_URL="https://github.com/raghugr2013-lgtm/strategy-factory-canonical.git"
REPO_BRANCH="main"
REPO_DIR="/opt/strategy-factory"

echo "▸ [1/5] ensuring vqb-network exists"
docker network inspect vqb-network >/dev/null 2>&1 || docker network create vqb-network

echo "▸ [2/5] starting factory-mongo"
for f in /opt/factory-mongo/docker-compose.yml /opt/factory-mongo/.env; do
  [[ -f "$f" ]] || { echo "  missing $f"; exit 1; }
done
chmod 600 /opt/factory-mongo/.env
docker compose --project-directory /opt/factory-mongo \
  --env-file /opt/factory-mongo/.env \
  -f /opt/factory-mongo/docker-compose.yml up -d

# Wait for Mongo to accept pings (up to 60s).
echo "  waiting for factory-mongo healthy..."
for i in {1..30}; do
  if docker exec factory-mongo mongosh --quiet --eval "db.runCommand('ping').ok" 2>/dev/null | grep -q '^1$'; then
    echo "  factory-mongo → pong"; break
  fi
  sleep 2
done

echo "▸ [3/5] starting Caddy"
for f in /opt/caddy/docker-compose.yml /opt/caddy/Caddyfile; do
  [[ -f "$f" ]] || { echo "  missing $f"; exit 1; }
done
if grep -q 'REPLACE_WITH_LETSENCRYPT_EMAIL' /opt/caddy/Caddyfile; then
  echo "  ERROR: /opt/caddy/Caddyfile still contains the email placeholder."
  echo "         Edit it and set a real email before continuing."
  exit 1
fi
docker compose --project-directory /opt/caddy \
  -f /opt/caddy/docker-compose.yml up -d

echo "▸ [4/5] deploying the canonical factory stack"
if [[ ! -d "$REPO_DIR/.git" ]]; then
  git clone --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
git fetch origin
git checkout "$REPO_BRANCH"
git reset --hard "origin/$REPO_BRANCH"

if [[ ! -f "$REPO_DIR/.env" ]]; then
  echo "  ERROR: $REPO_DIR/.env is missing. Copy the production .env into place first."
  exit 1
fi
chmod 600 "$REPO_DIR/.env"

# precheck + build + up + in-cluster health
"$REPO_DIR/infra/scripts/deploy.sh"

echo "▸ [5/5] final verification"
"$REPO_DIR/infra/scripts/health.sh"

echo
echo "══════════════════════════════════════════════════════════════"
echo "  Production deploy complete."
echo "  Verify externally:"
echo "    curl -fsS https://strategy.coinnike.com/api/health"
echo "    open   https://strategy.coinnike.com/"
echo "══════════════════════════════════════════════════════════════"
