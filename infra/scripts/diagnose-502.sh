#!/usr/bin/env bash
# Strategy Factory — production 502 diagnostic.
#
# Run this on the VPS (as the user that manages docker), from anywhere.
# It probes every hop between the public Traefik entrypoint and the
# factory-backend container to isolate a 502 Bad Gateway.
#
# Exits 0 if all hops succeed, 1 otherwise.
set -u

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; N=$'\e[0m'
else G=""; R=""; Y=""; C=""; B=""; N=""; fi

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

DOMAIN="${FACTORY_DOMAIN:-strategy.coinnike.com}"
NET="${VQB_NETWORK:-vqb-network}"
BACKEND="${BACKEND_CONTAINER:-factory-backend}"
PROXY="${PROXY_CONTAINER:-}"   # Caddy (production) or Traefik (legacy). Auto-detected below.

section(){ echo; echo "${B}${C}── $1 ──${N}"; }
ok(){    echo "${G}✓${N} $1"; }
warn(){  echo "${Y}!${N} $1"; }
bad(){   echo "${R}✗${N} $1" >&2; FAIL=$((FAIL+1)); }

FAIL=0

# ── 0. Environment sanity ─────────────────────────────────────────────
section "0. Environment"
echo "  FACTORY_DOMAIN = ${DOMAIN}"
echo "  vqb-network    = ${NET}"
echo "  backend cntr   = ${BACKEND}"

# ── 1. Public HTTPS layer (what the user sees) ────────────────────────
section "1. Public HTTPS layer"
code=$(curl -sSk -o /dev/null -w "%{http_code}" --max-time 8 "https://${DOMAIN}/api/health" || echo "000")
hdr=$(curl -sSk -I --max-time 8 "https://${DOMAIN}/api/health" 2>/dev/null | tr -d '\r' | head -20)
if [[ "$code" == "200" ]]; then ok "https://${DOMAIN}/api/health → 200 (nothing to fix)"
elif [[ "$code" == "502" ]]; then bad "https://${DOMAIN}/api/health → 502 Bad Gateway (Traefik cannot reach upstream)"
elif [[ "$code" == "000" ]]; then bad "https://${DOMAIN}/api/health → connection failed (DNS / firewall / no Traefik listener)"
else warn "https://${DOMAIN}/api/health → HTTP ${code}"; fi
echo "$hdr" | sed 's/^/    /'

# ── 2. Docker network topology ────────────────────────────────────────
section "2. Docker network — is Traefik on the same network as factory-backend?"
if ! docker network inspect "$NET" >/dev/null 2>&1; then
  bad "network '${NET}' does not exist"
  echo "    fix:  docker network create ${NET}"
else
  ok "network '${NET}' exists"
  # Every container on the network
  members=$(docker network inspect "$NET" -f '{{range $k,$v := .Containers}}{{$v.Name}} {{end}}')
  echo "    members: ${members:-<none>}"
  # Factory-backend attached?
  if echo " $members " | grep -q " $BACKEND "; then
    ok "${BACKEND} is attached to ${NET}"
  else
    bad "${BACKEND} is NOT attached to ${NET} — Traefik cannot resolve it"
    echo "    fix:  docker network connect ${NET} ${BACKEND}"
    echo "          (or rebuild:  cd $ROOT && ./infra/scripts/compose.sh up -d factory-backend)"
  fi
  # Reverse-proxy attached? (Caddy production; Traefik accepted as legacy.)
  if [[ -z "$PROXY" ]]; then
    PROXY=$(docker ps --filter "network=${NET}" --format '{{.Names}} {{.Image}}' \
            | awk '/[Cc]addy/{print $1; exit}')
    if [[ -z "$PROXY" ]]; then
      PROXY=$(docker ps --filter "network=${NET}" --format '{{.Names}} {{.Image}}' \
              | awk '/[Tt]raefik/{print $1; exit}')
    fi
  fi
  if [[ -n "$PROXY" ]]; then
    ok "reverse-proxy container on ${NET}: ${PROXY}"
  else
    bad "no Caddy/Traefik container attached to ${NET}"
    echo "    fix:  docker network connect ${NET} <your-proxy-container>"
    echo "    (list candidates:  docker ps --filter 'ancestor=caddy' --format '{{.Names}}')"
  fi
fi

# ── 3. Backend container health & port binding ────────────────────────
section "3. Backend container state"
if ! docker inspect "$BACKEND" >/dev/null 2>&1; then
  bad "container ${BACKEND} does not exist — nothing to route to"
else
  state=$(docker inspect -f '{{.State.Status}}' "$BACKEND")
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$BACKEND")
  restarts=$(docker inspect -f '{{.RestartCount}}' "$BACKEND")
  case "$state:$health" in
    running:healthy|running:n/a) ok "state=${state} health=${health} restarts=${restarts}" ;;
    running:starting)            warn "state=${state} health=${health} restarts=${restarts} — still initialising" ;;
    running:*)                   bad  "state=${state} health=${health} restarts=${restarts}" ;;
    *)                           bad  "state=${state} (container is NOT running)" ;;
  esac
  echo "    IPs on all networks:"
  docker inspect "$BACKEND" -f '{{range $k,$v := .NetworkSettings.Networks}}      {{$k}} → {{$v.IPAddress}}{{"\n"}}{{end}}'
  # In-container reachability
  if docker exec "$BACKEND" curl -fsS --max-time 5 http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
    ok "in-container 127.0.0.1:8001/api/health → 200"
  else
    bad "in-container 127.0.0.1:8001/api/health FAILED — app is not answering"
  fi
fi

# ── 4. Reverse proxy → backend reachability (proves the 502 hop) ──────
section "4. Reverse proxy → backend upstream test"
if [[ -n "${PROXY:-}" ]] && docker inspect "$PROXY" >/dev/null 2>&1; then
  # Get backend IP on vqb-network
  bip=$(docker inspect "$BACKEND" -f "{{with index .NetworkSettings.Networks \"${NET}\"}}{{.IPAddress}}{{end}}" 2>/dev/null)
  if [[ -z "$bip" ]]; then
    bad "no IP for ${BACKEND} on ${NET} — cannot test upstream"
  else
    if docker exec "$PROXY" wget -qO- --tries=1 --timeout=5 "http://${bip}:8001/api/health" 2>/dev/null >/dev/null \
       || docker exec "$PROXY" curl -fsS --max-time 5 "http://${bip}:8001/api/health" >/dev/null 2>&1; then
      ok "${PROXY} CAN reach ${BACKEND} at http://${bip}:8001/api/health"
      warn "Since the proxy can reach the backend, the 502 is a ROUTER / CADDYFILE problem (see §5)"
    else
      bad "${PROXY} CANNOT reach ${BACKEND} at http://${bip}:8001/api/health"
      echo "    → the 502 is a NETWORK problem (proxy and backend on different networks)"
    fi
    # Also try by name
    if docker exec "$PROXY" getent hosts "$BACKEND" >/dev/null 2>&1 \
       || docker exec "$PROXY" nslookup "$BACKEND" >/dev/null 2>&1; then
      ok "${PROXY} resolves DNS name '${BACKEND}' on ${NET}"
    else
      warn "${PROXY} cannot DNS-resolve '${BACKEND}' on ${NET}"
    fi
  fi
else
  warn "no Caddy/Traefik container detected — skipping upstream test"
fi

# ── 5. Router / label registration ────────────────────────────────────
section "5. Traefik labels on ${BACKEND}"
docker inspect "$BACKEND" -f '{{range $k,$v := .Config.Labels}}{{if or (eq $k "traefik.enable") (contains $k "traefik.http.routers.factory") (contains $k "traefik.http.services.factory") (eq $k "traefik.docker.network")}}      {{$k}} = {{$v}}{{"\n"}}{{end}}{{end}}' 2>/dev/null \
  | sed 's/^      /    /'
if docker inspect "$BACKEND" -f '{{index .Config.Labels "traefik.enable"}}' 2>/dev/null | grep -qi true; then
  ok "traefik.enable=true"
else
  bad "traefik.enable is NOT set to 'true' — Traefik will ignore this container"
fi
declared_net=$(docker inspect "$BACKEND" -f '{{index .Config.Labels "traefik.docker.network"}}' 2>/dev/null)
if [[ "$declared_net" == "$NET" ]]; then
  ok "traefik.docker.network=${NET} matches"
else
  bad "traefik.docker.network='${declared_net}' does not match actual network '${NET}'"
fi

# ── 6. Duplicates / stale containers ──────────────────────────────────
section "6. Duplicate / stale factory-backend containers"
dupes=$(docker ps -a --filter "name=factory-backend" --format '{{.Names}} {{.Status}}' | wc -l)
if [[ "$dupes" -le 1 ]]; then
  ok "exactly one ${BACKEND} container (no stale duplicates)"
else
  warn "found ${dupes} factory-backend* containers — stale ones can confuse Traefik:"
  docker ps -a --filter "name=factory-backend" --format '    {{.Names}}  {{.Status}}  ({{.RunningFor}})'
  echo "    fix:  docker rm -f <stale-name>"
fi

# ── 7. Proxy-side view (routes / logs) ────────────────────────────────
section "7. Reverse-proxy registered routes / recent logs"
if [[ -n "${PROXY:-}" ]]; then
  # Caddy: dump the loaded config via the admin API (default :2019).
  if docker exec "$PROXY" wget -qO- --tries=1 --timeout=3 "http://127.0.0.1:2019/config/apps/http/servers" 2>/dev/null \
       | grep -q factory-backend; then
    ok "Caddy config references 'factory-backend' upstream (admin API :2019)"
  fi
  # Traefik legacy fallback: try the api dashboard.
  for port in 8080 9000 8081; do
    if docker exec "$PROXY" wget -qO- --tries=1 --timeout=3 "http://127.0.0.1:${port}/api/http/routers" 2>/dev/null | grep -q factory-api; then
      ok "Traefik has router 'factory-api' registered (api port ${port})"
      break
    fi
  done
  # Check recent proxy logs for the domain or 502s
  echo "    Recent proxy log lines mentioning ${DOMAIN} or 502:"
  docker logs --since 5m "$PROXY" 2>&1 | grep -iE "${DOMAIN}|factory-|502" | tail -10 | sed 's/^/      /'
fi

# ── 8. Recent backend log lines ───────────────────────────────────────
section "8. Recent ${BACKEND} log tail (last 20 lines)"
docker logs --tail 20 "$BACKEND" 2>&1 | sed 's/^/    /'

echo
if [[ $FAIL -eq 0 ]]; then
  echo "${G}All diagnostics passed${N}"
  exit 0
else
  echo "${R}${FAIL} problem(s) detected${N} — apply the printed fixes and re-run this script"
  exit 1
fi
