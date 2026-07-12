#!/usr/bin/env bash
# Strategy Factory — deployment dry-run harness.
#
# Executes the full pre-deployment migration pipeline against a synthetic v01
# dataset so the operator can prove zero data loss BEFORE running against the
# real VPS Mongo.
#
# Steps:
#   1. Seed a synthetic v01 dataset in `synthetic_v01`
#   2. Run audit-vps-db.py  → audit-report.json + audit-report.md
#   3. Run validate-migration.py → validation-report.json + .md
#   4. Run migrate-data.py (dry-run first, then live) → migration-report.json
#   5. Run verify-migration.py against target strategy_factory_dryrun
#   6. Print a summary and exit 0 (pass) / 1 (review) / 2 (fatal)
#
# Prereqs:
#   * MongoDB reachable at $MONGO_URI (default mongodb://localhost:27017)
#   * python3 with pymongo==4.9.2, bcrypt available in PATH
#   * Run from repo root: `./infra/scripts/deploy-dry-run.sh`
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
SRC_DB="${SRC_DB:-synthetic_v01}"
TGT_DB="${TGT_DB:-strategy_factory_dryrun}"
OUT_DIR="${OUT_DIR:-$ROOT/dry-run-reports}"
API_BASE="${API_BASE:-}"

mkdir -p "$OUT_DIR"

banner() { printf "\n\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()     { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
err()    { printf "  \033[1;31m✗\033[0m %s\n" "$*" >&2; }

banner "1/5 · Seeding synthetic v01 dataset in $SRC_DB"
python3 "$HERE/seed-synthetic-v01.py" --uri "$MONGO_URI" --db "$SRC_DB"

# Wipe target so we exercise fresh migration
python3 - <<PY
from pymongo import MongoClient
MongoClient("$MONGO_URI").drop_database("$TGT_DB")
print("[dry-run] target DB $TGT_DB dropped for a clean slate")
PY

banner "2/5 · Auditing source DB"
python3 "$HERE/audit-vps-db.py" \
  --source "$MONGO_URI" --source-db "$SRC_DB" \
  --out-json "$OUT_DIR/audit-report.json" \
  --out-md   "$OUT_DIR/audit-report.md"
ok "audit report → $OUT_DIR/audit-report.md"

banner "3/5 · Validating migration plan coverage"
set +e
python3 "$HERE/validate-migration.py" \
  --audit "$OUT_DIR/audit-report.json" \
  --plan  "$HERE/migrate-data.py" \
  --out-json "$OUT_DIR/validation-report.json" \
  --out-md   "$OUT_DIR/validation-report.md"
VAL_EXIT=$?
set -e
if [[ $VAL_EXIT -ne 0 ]]; then
  err "validation flagged uncovered source collections — see $OUT_DIR/validation-report.md"
  err "add plan rows for uncovered collections BEFORE running the real migration"
fi
ok "validation report → $OUT_DIR/validation-report.md"

banner "4a/5 · Migration dry-run (no writes)"
python3 "$HERE/migrate-data.py" \
  --source "$MONGO_URI" --source-db "$SRC_DB" \
  --target "$MONGO_URI" --target-db "$TGT_DB" \
  --dry-run \
  --report "$OUT_DIR/migration-report.dryrun.json"
ok "dry-run report → $OUT_DIR/migration-report.dryrun.json"

banner "4b/5 · Migration live (into $TGT_DB)"
python3 "$HERE/migrate-data.py" \
  --source "$MONGO_URI" --source-db "$SRC_DB" \
  --target "$MONGO_URI" --target-db "$TGT_DB" \
  --report "$OUT_DIR/migration-report.json"
ok "migration report → $OUT_DIR/migration-report.json"

banner "5/5 · Verifying target DB"
API_ARGS=()
if [[ -n "$API_BASE" ]]; then
  API_ARGS=(--api-base "$API_BASE")
  if [[ -n "${ADMIN_EMAIL:-}" && -n "${ADMIN_PASSWORD:-}" ]]; then
    API_ARGS+=(--admin-email "$ADMIN_EMAIL" --admin-password "$ADMIN_PASSWORD")
  fi
fi

set +e
python3 "$HERE/verify-migration.py" \
  --audit "$OUT_DIR/audit-report.json" \
  --source "$MONGO_URI" --source-db "$SRC_DB" \
  --target "$MONGO_URI" --target-db "$TGT_DB" \
  --migration-report "$OUT_DIR/migration-report.json" \
  --out-json "$OUT_DIR/verification-report.json" \
  --out-md   "$OUT_DIR/verification-report.md" \
  "${API_ARGS[@]}"
VER_EXIT=$?
set -e
ok "verification report → $OUT_DIR/verification-report.md"

banner "Dry-run complete"
echo
echo "  Reports in $OUT_DIR:"
echo "    · audit-report.md         — what's in the source"
echo "    · validation-report.md    — coverage of migration plan (informational; auto-passthrough covers unplanned collections)"
echo "    · migration-report.json   — every doc moved, with counts"
echo "    · verification-report.md  — before/after, fingerprints, spot checks, sign-off"
echo
if [[ $VER_EXIT -eq 0 ]]; then
  ok "VERDICT: PASS — safe to proceed with real VPS migration"
  if [[ $VAL_EXIT -ne 0 ]]; then
    echo "     (validator flagged unplanned collections — engine auto-passthrough'd them; add bespoke transformers only if their schemas need upgrading)"
  fi
  exit 0
else
  err "VERDICT: REVIEW_REQUIRED — see verification-report.md"
  exit 1
fi
