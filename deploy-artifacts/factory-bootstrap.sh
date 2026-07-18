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

# ── Rollback snapshot ─────────────────────────────────────────────
# Captured BEFORE anything is deployed. Purely informational — no
# state anywhere is modified by this block. If the deploy fails, the
# ERR trap prints the exact commands needed to return the system to
# the state recorded here.
TS="$(date -u +%Y%m%d_%H%M%SZ)"
SNAP_ROOT="/opt/factory-rollback"
SNAP_DIR="$SNAP_ROOT/$TS"
mkdir -p "$SNAP_DIR"
chmod 700 "$SNAP_ROOT"

echo "▸ [0/5] recording rollback snapshot → $SNAP_DIR"

# 0.1 — repo git SHA + branch (only if the repo is present)
if [[ -d "$REPO_DIR/.git" ]]; then
  ( cd "$REPO_DIR"
    git rev-parse HEAD                > "$SNAP_DIR/repo.head.sha"        2>/dev/null || true
    git rev-parse --abbrev-ref HEAD   > "$SNAP_DIR/repo.branch"          2>/dev/null || true
    git status --short --branch       > "$SNAP_DIR/repo.status"          2>/dev/null || true
    git log -1 --pretty=fuller        > "$SNAP_DIR/repo.head.commit.txt" 2>/dev/null || true
  )
else
  echo "(no /opt/strategy-factory checkout yet)" > "$SNAP_DIR/repo.head.sha"
fi

# 0.2 — running containers + their image IDs (used for image rollback)
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.ID}}' \
  > "$SNAP_DIR/containers.txt" 2>/dev/null || true
docker inspect --format \
  '{{.Name}} {{.Config.Image}} {{.Image}}' $(docker ps -aq) 2>/dev/null \
  | sed 's|^/||' > "$SNAP_DIR/containers.image_sha.txt" || true

# 0.3 — image list (for `docker image tag` rollback if needed)
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}' \
  > "$SNAP_DIR/images.txt" 2>/dev/null || true

# 0.4 — checksums of the three .env files (never their contents)
for e in /opt/factory-mongo/.env /opt/caddy/Caddyfile "$REPO_DIR/.env"; do
  [[ -f "$e" ]] && sha256sum "$e" >> "$SNAP_DIR/env.sha256" || true
done

# 0.5 — docker network membership snapshot
docker network inspect vqb-network > "$SNAP_DIR/vqb-network.json" 2>/dev/null || true

# 0.6 — write a ready-to-paste rollback script (informational only)
cat > "$SNAP_DIR/ROLLBACK.sh" <<'ROLLBACK_EOF'
#!/usr/bin/env bash
# Rollback commands captured at snapshot time.
# Nothing here runs automatically — read it, then run pieces you want.
set -euo pipefail
SNAP_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Snapshot: $SNAP_DIR"
echo
echo "── Recorded repo state ──────────────────────────────────────"
[[ -s "$SNAP_DIR/repo.head.sha" ]] && cat "$SNAP_DIR/repo.head.sha"
[[ -s "$SNAP_DIR/repo.branch"   ]] && cat "$SNAP_DIR/repo.branch"
cat "$SNAP_DIR/repo.status" 2>/dev/null || true
echo
echo "── To restore the repo to the captured commit ───────────────"
if [[ -s "$SNAP_DIR/repo.head.sha" ]]; then
  sha="$(cat "$SNAP_DIR/repo.head.sha")"
  echo "  cd /opt/strategy-factory && git fetch origin"
  echo "  cd /opt/strategy-factory && git checkout $sha"
fi
echo
echo "── To restore container images (per row: name image image_sha) ─"
echo "  See containers.image_sha.txt in this directory."
echo "  Redeploy after retagging with:  ./infra/scripts/deploy.sh --skip-precheck"
echo
echo "── To bring the whole stack down (leaves Mongo data intact) ──"
echo "  docker compose --project-directory /opt/strategy-factory \\"
echo "    -f /opt/strategy-factory/infra/compose/docker-compose.prod.yml down"
echo
echo "── Canonical repo rollback script (if you prefer) ───────────"
echo "  /opt/strategy-factory/infra/scripts/rollback.sh"
ROLLBACK_EOF
chmod +x "$SNAP_DIR/ROLLBACK.sh"

# 0.7 — ERR trap: on ANY failure below, print the rollback pointer.
#        This does NOT roll anything back automatically — it only tells
#        the operator where the snapshot lives and how to use it.
trap '
  rc=$?
  echo
  echo "══════════════════════════════════════════════════════════════"
  echo "  DEPLOY FAILED (exit=$rc)"
  echo "  Rollback snapshot:  '"$SNAP_DIR"'"
  echo "  Recorded:"
  echo "    • repo HEAD  : $(cat '"$SNAP_DIR"'/repo.head.sha 2>/dev/null || echo n/a)"
  echo "    • branch     : $(cat '"$SNAP_DIR"'/repo.branch   2>/dev/null || echo n/a)"
  echo "    • containers : '"$SNAP_DIR"'/containers.txt"
  echo "    • images     : '"$SNAP_DIR"'/images.txt"
  echo "    • env sha256 : '"$SNAP_DIR"'/env.sha256"
  echo "  Print rollback commands:"
  echo "    bash '"$SNAP_DIR"'/ROLLBACK.sh"
  echo "  Nothing has been rolled back automatically."
  echo "══════════════════════════════════════════════════════════════"
  exit $rc
' ERR

echo "  snapshot ready"
# ──────────────────────────────────────────────────────────────────

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

# Safety: never destroy local production changes automatically.
# 1. Fetch new refs from origin (read-only).
# 2. Show current status.
# 3. If the working tree is clean AND on the expected branch, continue.
# 4. If there are ANY local modifications / untracked files / a
#    different branch checked out, STOP and require operator sign-off.
echo "  fetching latest refs from origin (read-only)"
git fetch origin --prune

current_branch="$(git rev-parse --abbrev-ref HEAD)"
echo "  current branch: $current_branch  (expected: $REPO_BRANCH)"
echo "  git status:"
git status --short --branch | sed 's/^/    /'

dirty=""
if [[ "$current_branch" != "$REPO_BRANCH" ]]; then
  dirty="on branch '$current_branch', expected '$REPO_BRANCH'"
elif [[ -n "$(git status --porcelain)" ]]; then
  dirty="working tree has local modifications or untracked files"
fi

if [[ -n "$dirty" ]]; then
  cat <<EOF

  ⚠  Refusing to auto-advance the repo — $dirty.
     Nothing has been discarded. Bootstrap will now stop.

     Review the changes:  cd $REPO_DIR && git status && git diff
     If safe to discard:  cd $REPO_DIR && git checkout $REPO_BRANCH \\
                          && git reset --hard origin/$REPO_BRANCH
     Then re-run:         sudo bash /opt/factory-bootstrap.sh

EOF
  exit 2
fi

# Clean tree on the right branch — a plain fast-forward is safe.
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse "origin/$REPO_BRANCH")"
if [[ "$local_sha" != "$remote_sha" ]]; then
  echo "  fast-forwarding $current_branch: $local_sha → $remote_sha"
  git merge --ff-only "origin/$REPO_BRANCH"
else
  echo "  repo already at origin/$REPO_BRANCH ($local_sha) — no update needed"
fi

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
echo "  Rollback snapshot: $SNAP_DIR"
echo "    Print rollback commands:  bash $SNAP_DIR/ROLLBACK.sh"
echo "  Verify externally:"
echo "    curl -fsS https://strategy.coinnike.com/api/health"
echo "    open   https://strategy.coinnike.com/"
echo "══════════════════════════════════════════════════════════════"
