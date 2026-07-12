#!/usr/bin/env bash
# Strategy Factory — deterministic release-bundle builder.
#
# Produces a byte-reproducible strategy-factory-<version>.tar.gz that ships
# with an in-tree SHA256SUMS manifest so operators can verify each extracted
# file matches the bundle after unpacking.
#
# Usage (from repo parent):
#     ./strategy-factory/infra/scripts/build-bundle.sh
#
# Outputs (in the repo parent):
#     strategy-factory-1.0.0.tar.gz
#     strategy-factory-1.0.0.tar.gz.sha256
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"
NAME="$(basename "$ROOT")"

VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || echo 1.0.0)"
OUT="$PARENT/${NAME}-${VERSION}.tar.gz"

# 1) Compute SHA256SUMS for every file in the tree (excluding transient artefacts + the manifest itself).
cd "$ROOT"
find . -type f \
    ! -path './dry-run-reports/*' \
    ! -path '*/__pycache__/*' \
    ! -name '*.pyc' \
    ! -path '*/.pytest_cache/*' \
    ! -name 'SHA256SUMS' \
    -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS

echo "SHA256SUMS ($(wc -l < SHA256SUMS) entries) written to $ROOT/SHA256SUMS"

# 2) Deterministic tar + gzip (no timestamps, sorted, root:0:0 ownership)
cd "$PARENT"
rm -f "$OUT" "$OUT.tmp"
tar --exclude="$NAME/dry-run-reports" \
    --exclude="$NAME/**/__pycache__" \
    --exclude="$NAME/**/.pyc" \
    --exclude="$NAME/**/.pytest_cache" \
    --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime='2026-02-15 00:00:00 UTC' \
    -cf "${OUT%.gz}" "$NAME"
gzip -n -9 "${OUT%.gz}"

# 3) Ship a companion .sha256 next to the tarball for a two-check verification loop
sha256sum "$OUT" | tee "$OUT.sha256"

echo
echo "Bundle built: $OUT"
echo "SHA-256    : $(sha256sum "$OUT" | awk '{print $1}')"
echo "Size       : $(wc -c < "$OUT") bytes"
