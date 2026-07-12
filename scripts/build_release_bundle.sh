#!/usr/bin/env bash
# ------------------------------------------------------------
# Strategy Factory v1.1 — release bundle builder
# ------------------------------------------------------------
# Produces a self-contained tarball ready to ship to a VPS.
# Includes the full canonical repo minus dev-only cruft.
#
# Output:  dist/strategy-factory-v1.1.0-<git|nogit>.tar.gz
#          dist/strategy-factory-v1.1.0-<...>.sha256
# ------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DIST="$ROOT/dist"
mkdir -p "$DIST"

VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || echo 1.1.0)"
COMMIT="$(git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo nogit)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="strategy-factory-v${VERSION}-${COMMIT}"
OUT="${DIST}/${NAME}.tar.gz"

echo "→ building $NAME"
cd "$ROOT"

tar --create --gzip \
    --exclude='./dist' \
    --exclude='./node_modules' \
    --exclude='./frontend/node_modules' \
    --exclude='./frontend/build' \
    --exclude='./.git' \
    --exclude='./.emergent' \
    --exclude='./audit_workspace' \
    --exclude='./test_reports' \
    --exclude='./tests/__pycache__' \
    --exclude='./**/__pycache__' \
    --exclude='./**/*.pyc' \
    --exclude='./**/*.pyo' \
    --exclude='./**/.DS_Store' \
    --exclude='./.ruff_cache' \
    --transform "s,^\./,${NAME}/," \
    --file "$OUT" \
    .

sha256sum "$OUT" | awk '{print $1}' > "${OUT%.tar.gz}.sha256"

echo "✓ built:"
echo "   $(ls -lh "$OUT" | awk '{print $5, $9}')"
echo "   sha256=$(cat "${OUT%.tar.gz}.sha256")"
echo
echo "Deploy to a fresh machine with:"
echo "   scp $(basename "$OUT") user@vps:~"
echo "   ssh user@vps 'tar xzf $(basename "$OUT") && cd ${NAME} && cp .env.example .env && \$EDITOR .env && ./scripts/one_click_deploy.sh'"
