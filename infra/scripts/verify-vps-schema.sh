#!/usr/bin/env bash
# Strategy Factory — pre-migration VPS field-schema verification (wrapper).
#
# Runs verify-vps-schema.py inside a python:3.12-slim container on
# vqb-network, mounting the probe script and the report output directory.
#
# The heavy lifting is in the companion Python file — this wrapper only
# orchestrates the container so there is no shell-heredoc quoting bug.
#
# Two read-only checks are performed against the source VPS database:
#
#   1) `market_data` contains ONLY reproducible OHLCV / spread / timestamp
#      fields — safe to exclude from Lean migration.
#   2) `mutation_stability_log` is operational telemetry — no evolutionary-
#      learning / genome / lineage fields.
#
# Outputs: verify-vps-schema-<stamp>.{md,json} in $OUT_DIR (default: cwd).
#
# Usage:
#   SOURCE_MONGO_URL=mongodb://... SOURCE_MONGO_DB=test_database \
#       ./infra/scripts/verify-vps-schema.sh
#
# Env vars:
#   SOURCE_MONGO_URL  full URI to the source (v01 VPS) DB   [required]
#   SOURCE_MONGO_DB   source DB name                        [default: test_database]
#   OUT_DIR           report directory                      [default: $(pwd)]
#   SAMPLE_SIZE       docs to sample per collection         [default: 200]
#
# Exit codes:
#   0 — both checks PASS (safe to adopt Lean profile)
#   1 — at least one check REVIEW_REQUIRED
#   2 — connection or environment error
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="$ROOT/.env"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

: "${SOURCE_MONGO_URL:?SOURCE_MONGO_URL required (source v01 Mongo URI)}"
SRC_DB="${SOURCE_MONGO_DB:-test_database}"
OUT_DIR="${OUT_DIR:-$(pwd)}"
SAMPLE_SIZE="${SAMPLE_SIZE:-200}"
mkdir -p "$OUT_DIR"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
REPORT_JSON_NAME="verify-vps-schema-${STAMP}.json"
REPORT_MD_NAME="verify-vps-schema-${STAMP}.md"
REPORT_JSON="$OUT_DIR/$REPORT_JSON_NAME"
REPORT_MD="$OUT_DIR/$REPORT_MD_NAME"

echo "──────────────────────────────────────────────────────────────"
echo " Strategy Factory — Pre-migration schema verification"
echo " Started:  $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo " Source:   $SRC_DB"
echo " Report:   $REPORT_JSON"
echo "           $REPORT_MD"
echo " Sample:   $SAMPLE_SIZE docs per collection"
echo "──────────────────────────────────────────────────────────────"

set +e
docker run --rm \
    --network vqb-network \
    -v "$HERE/verify-vps-schema.py:/probe.py:ro" \
    -v "$OUT_DIR:/work" \
    -e SOURCE_MONGO_URL \
    -e SRC_DB="$SRC_DB" \
    -e SAMPLE_SIZE="$SAMPLE_SIZE" \
    -e OUT_JSON="/work/$REPORT_JSON_NAME" \
    -e OUT_MD="/work/$REPORT_MD_NAME" \
    python:3.12-slim sh -c 'pip install -q pymongo==4.9.2 && python -u /probe.py'
RC=$?
set -e

echo "──────────────────────────────────────────────────────────────"
echo " Finished: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo " Report:   $REPORT_JSON"
echo "           $REPORT_MD"
if [[ $RC -eq 0 ]]; then
    echo " Verdict:  PASS"
elif [[ $RC -eq 1 ]]; then
    echo " Verdict:  REVIEW_REQUIRED  (see report for details)"
else
    echo " Verdict:  ERROR (exit $RC)"
fi
echo "──────────────────────────────────────────────────────────────"
exit $RC
