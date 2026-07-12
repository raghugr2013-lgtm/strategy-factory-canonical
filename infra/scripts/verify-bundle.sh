#!/usr/bin/env bash
# Strategy Factory — post-extract integrity verifier.
#
# Run this immediately after extracting the tarball. It reads SHA256SUMS
# (shipped inside the bundle) and re-computes every file's SHA-256,
# reporting any mismatch or missing file.
#
# Usage:
#     cd /opt/strategy-factory
#     ./infra/scripts/verify-bundle.sh
#
# Exit codes:
#     0 = all files match
#     1 = at least one file mismatched or missing
#     2 = SHA256SUMS missing (bundle unpacked incorrectly)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

MANIFEST="SHA256SUMS"

if [[ ! -f "$MANIFEST" ]]; then
  printf "\033[1;31m✗\033[0m %s not found — bundle was not extracted, or was extracted with a filter that stripped it.\n" "$MANIFEST" >&2
  exit 2
fi

printf "\033[1;36m▸ Verifying %d files against %s…\033[0m\n" "$(wc -l < "$MANIFEST")" "$MANIFEST"

if sha256sum --check --status "$MANIFEST"; then
  printf "\033[1;32m✓\033[0m All files match the manifest — extraction is intact.\n"
  exit 0
else
  printf "\n\033[1;31m✗\033[0m Integrity check failed. Files that do not match:\n" >&2
  sha256sum --check "$MANIFEST" 2>/dev/null | grep -v ': OK$' >&2 || true
  echo >&2
  printf "This means the on-disk file differs from what the tarball shipped.\n" >&2
  printf "Common causes:\n" >&2
  printf "  1. You extracted an OLDER bundle earlier and never re-extracted the current one\n" >&2
  printf "  2. Extraction used --keep-old-files / -k which preserved stale files\n" >&2
  printf "  3. A post-extract script or manual edit modified the file\n" >&2
  printf "\nRecovery:\n" >&2
  printf "  rm -rf %s\n" "$ROOT" >&2
  printf "  tar -xzf strategy-factory-1.0.0.tar.gz -C /opt/\n" >&2
  printf "  cd %s && ./infra/scripts/verify-bundle.sh\n" "$ROOT" >&2
  exit 1
fi
