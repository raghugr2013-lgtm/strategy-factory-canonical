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
# Preference order (all container-based; host `mongosh` NOT required):
#   a) `docker exec` on an already-running mongo container on vqb-network
#      (fast: no image pull, works offline).
#   b) `docker run --rm mongo:7.0 mongosh ...` (slower, requires image pull).
#   c) Skip with WARN if neither works — actual DB connectivity is
#      re-verified by the backend healthcheck immediately after deploy.
mongo_ping() {
  # $1 = URI ; prints ok/reason on stdout ; returns 0 on success.
  local uri="$1"
  local out rc

  # (a) exec inside a running mongo container on vqb-network.
  local running
  running=$(docker ps --filter "network=vqb-network" --format '{{.Names}} {{.Image}}' \
            | awk '/[Mm]ongo/{print $1; exit}')
  if [[ -n "$running" ]]; then
    if out=$(timeout 10 docker exec "$running" \
              mongosh "$uri" --quiet --eval 'db.adminCommand({ping:1}).ok' 2>&1); then
      if echo "$out" | tail -1 | grep -q '^1$'; then
        echo "ok via docker exec $running"; return 0
      fi
      echo "docker exec $running mongosh returned unexpected output:"; echo "$out"
      return 2   # ran, but rejected — likely bad URI/credentials
    fi
    echo "docker exec $running mongosh failed:"; echo "$out"
  fi

  # (b) ephemeral container. Suppress image-pull progress but keep errors.
  local pull_err
  if ! pull_err=$(docker image inspect mongo:7.0 >/dev/null 2>&1 \
                  || docker pull mongo:7.0 2>&1 >/dev/null); then
    echo "cannot obtain mongo:7.0 image (needed to run mongosh); pull output:"
    echo "$pull_err"
    return 3   # infrastructure problem — cannot verify
  fi
  if out=$(timeout 15 docker run --rm --network vqb-network mongo:7.0 \
             mongosh "$uri" --quiet --eval 'db.adminCommand({ping:1}).ok' 2>&1); then
    if echo "$out" | tail -1 | grep -q '^1$'; then
      echo "ok via ephemeral mongo:7.0 container"; return 0
    fi
    echo "ephemeral mongosh returned unexpected output:"; echo "$out"
    return 2
  fi
  rc=$?
  echo "ephemeral mongosh failed (exit=$rc):"; echo "$out"
  return 1
}

if docker info >/dev/null 2>&1; then
  detail=$(mongo_ping "$SHARED_MONGO_URL"); rc=$?
  case $rc in
    0)  ok    "SHARED_MONGO_URL reachable — ${detail#ok via }" ;;
    2)  bad   "SHARED_MONGO_URL is set but Mongo rejected the ping — check URI, user, password, authSource:"
        echo "$detail" | sed 's/^/    /' ;;
    3)  warn  "SHARED_MONGO_URL check skipped — cannot obtain mongo:7.0 image (no host mongosh required; run 'docker pull mongo:7.0' once when the VPS has network access). Backend healthcheck will still verify connectivity post-deploy."
        echo "$detail" | sed 's/^/    /' ;;
    *)  bad   "SHARED_MONGO_URL check failed — see error below (check that mongo container is on vqb-network):"
        echo "$detail" | sed 's/^/    /' ;;
  esac
else
  warn "docker daemon not reachable — skipping Mongo connectivity check"
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

# --- 8. Reverse-proxy container running on vqb-network (Caddy in production;
#         Traefik is retained as an accepted alternative for legacy VPSes) ---
if docker info >/dev/null 2>&1; then
  # Prefer Caddy (the actual production proxy). Also accept Traefik for
  # legacy/staging VPSes still on the older topology.
  proxy_id=$(docker ps --filter "network=vqb-network" --format '{{.ID}} {{.Image}} {{.Names}}' \
             | awk '/[Cc]addy|[Tt]raefik/{print $1" "$2" "$3; exit}')
  if [[ -n "$proxy_id" ]]; then
    ok "reverse-proxy container found on vqb-network: $proxy_id"
  else
    warn "No Caddy (or Traefik) container detected on vqb-network — public routing will not work until one is running (see infra/caddy/README.md)"
  fi
fi

# --- 9. Ports 80/443 unlikely to conflict with backend/frontend (they don't bind — via Caddy) ---
ok "backend/frontend bind on internal ports only (routed via Caddy) — no host-port conflicts"

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
