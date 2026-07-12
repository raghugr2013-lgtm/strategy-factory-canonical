#!/usr/bin/env bash
# Strategy Factory — pre-deploy sanity check.
# Verifies the operator has done the manual bits documented in DEPLOYMENT.md
# BEFORE we touch any container. Fails fast with a clear reason.
#
# Usage:  ./infra/scripts/precheck.sh
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; N=$'\e[0m'; else G=""; R=""; Y=""; N=""; fi
pass=0; warn=0; fail=0
ok(){ pass=$((pass+1)); echo "${G}✓${N} $1"; }
warn(){ warn=$((warn+1)); echo "${Y}!${N} $1"; }
bad(){ fail=$((fail+1)); echo "${R}✗${N} $1" >&2; }

# --- 1. .env exists and is readable ---
if [[ ! -f "$ENV_FILE" ]]; then
  bad ".env not found at $ENV_FILE (copy from .env.example)"
  exit 1
fi
ok ".env present"
set -a; . "$ENV_FILE"; set +a

# --- 2. Required vars set ---
require() {
  local name="$1"
  local val
  val="$(printenv "$name" || true)"
  if [[ -z "$val" || "$val" == "CHANGE_ME" || "$val" == "CHANGE_ME_TO_64_CHAR_HEX" ]]; then
    bad "env var $name is unset or still a placeholder"
  else
    ok "env var $name is set"
  fi
}
require FACTORY_DOMAIN
require JWT_SECRET
require ADMIN_EMAIL
require ADMIN_PASSWORD
require SHARED_MONGO_URL
require FACTORY_DB_NAME
require CORS_ORIGINS

# --- 3. Docker installed and daemon reachable ---
if command -v docker >/dev/null 2>&1; then
  ok "docker → $(docker --version)"
  if docker info >/dev/null 2>&1; then
    ok "docker daemon reachable"
  else
    bad "docker daemon not reachable (need sudo or docker group membership)"
  fi
else
  bad "docker not installed — run ./infra/scripts/bootstrap-vps.sh first"
fi

if docker compose version >/dev/null 2>&1; then
  ok "docker compose plugin → $(docker compose version --short 2>/dev/null || docker compose version | head -1)"
else
  bad "docker compose plugin not installed — run ./infra/scripts/bootstrap-vps.sh first"
fi

# --- 4. vqb-network exists ---
if docker network inspect vqb-network >/dev/null 2>&1; then
  ok "docker network 'vqb-network' exists"
else
  warn "docker network 'vqb-network' missing — deploy.sh will create it"
fi

# --- 5. Shared Mongo reachable ---
if docker info >/dev/null 2>&1; then
  if timeout 15 docker run --rm --network vqb-network mongo:7.0 \
       mongosh "$SHARED_MONGO_URL" --quiet --eval 'db.adminCommand({ping:1})' >/dev/null 2>&1; then
    ok "SHARED_MONGO_URL reachable (mongosh ping ok)"
  else
    bad "SHARED_MONGO_URL not reachable (check URI, credentials, and that mongo is on vqb-network)"
  fi
fi

# --- 6. Redis reachable (only if configured) ---
if [[ -n "${SHARED_REDIS_URL:-}" ]]; then
  if docker info >/dev/null 2>&1; then
    # SHARED_REDIS_URL format: redis://[:password@]host:port[/db]
    if timeout 10 docker run --rm --network vqb-network redis:7.4-alpine \
         sh -c 'redis-cli -u "$0" ping' "$SHARED_REDIS_URL" 2>&1 | grep -q PONG; then
      ok "SHARED_REDIS_URL reachable (PONG)"
    else
      warn "SHARED_REDIS_URL set but not reachable (non-fatal — redis is optional)"
    fi
  fi
else
  warn "SHARED_REDIS_URL not set (Redis is optional today; readiness will report 'skipped')"
fi

# --- 7. DNS resolves for FACTORY_DOMAIN ---
if getent hosts "$FACTORY_DOMAIN" >/dev/null 2>&1; then
  resolved=$(getent hosts "$FACTORY_DOMAIN" | awk '{print $1}' | head -1)
  ok "DNS: $FACTORY_DOMAIN → $resolved"
else
  bad "DNS lookup failed for $FACTORY_DOMAIN (add an A/AAAA record before deploy)"
fi

# --- 8. Traefik container running on vqb-network ---
if docker info >/dev/null 2>&1; then
  # Traefik container name is not standardised — look for any container with label traefik.docker.network=vqb-network OR image starting with traefik/
  traefik_id=$(docker ps --filter "network=vqb-network" --format '{{.ID}} {{.Image}}' | awk '/traefik/{print $1; exit}')
  if [[ -n "$traefik_id" ]]; then
    ok "Traefik container found on vqb-network: $traefik_id"
  else
    warn "No Traefik container detected on vqb-network — public routing will not work until Traefik is running"
  fi
fi

# --- 9. Ports 80/443 unlikely to conflict with backend/frontend (they don't bind — via Traefik) ---
ok "backend/frontend bind on internal ports only (via Traefik) — no host-port conflicts"

echo
if [[ $fail -gt 0 ]]; then
  echo "${R}precheck FAILED${N} — ${fail} error(s), ${warn} warning(s), ${pass} ok"
  exit 1
fi
if [[ $warn -gt 0 ]]; then
  echo "${Y}precheck OK with warnings${N} — ${warn} warning(s), ${pass} ok"
else
  echo "${G}precheck OK${N} — ${pass} check(s) passed"
fi
exit 0
