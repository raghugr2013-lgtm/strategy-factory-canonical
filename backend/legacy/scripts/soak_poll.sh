#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Phase 2 P2.6/P2.7 — soak snapshot CLI poller.
#
# Polls /api/diagnostics/soak-snapshot every N seconds and appends a
# single-line JSON record to a soak-evidence log file. Run during the
# 24h soak window before ProcessPool / workers ramp.
#
# Usage:
#   ./scripts/soak_poll.sh                           # 60s interval, default
#   INTERVAL_SEC=300 ./scripts/soak_poll.sh          # 5min interval
#   WINDOW_MINUTES=120 ./scripts/soak_poll.sh        # widen probe window
#   OUT_FILE=/tmp/soak.ndjson ./scripts/soak_poll.sh # custom log path
#
# Stops cleanly on Ctrl-C; safe to background with `nohup … &`.
#
# Output file format: newline-delimited JSON (.ndjson) — one snapshot
# per poll, each annotated with `_polled_at` (the host time of capture).
# ─────────────────────────────────────────────────────────────────────

set -u

API="${API:-http://localhost:8001}"
EMAIL="${ADMIN_EMAIL:-admin@local.test}"
PASSWORD="${ADMIN_PASSWORD:-admin123}"
INTERVAL_SEC="${INTERVAL_SEC:-60}"
WINDOW_MINUTES="${WINDOW_MINUTES:-60}"
OUT_FILE="${OUT_FILE:-/app/test_reports/soak_evidence.ndjson}"

mkdir -p "$(dirname "$OUT_FILE")"

echo "[soak_poll] starting"
echo "[soak_poll]   api            : $API"
echo "[soak_poll]   interval_sec   : $INTERVAL_SEC"
echo "[soak_poll]   window_minutes : $WINDOW_MINUTES"
echo "[soak_poll]   out_file       : $OUT_FILE"
echo "[soak_poll] press Ctrl-C to stop"

while true; do
    # Re-login each iter (token TTL is short; cost is one extra request).
    TOKEN="$(curl -fsS -X POST "$API/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
        | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("token") or d.get("access_token") or "")' \
        2>/dev/null || true)"

    if [ -z "$TOKEN" ]; then
        echo "[soak_poll] WARN — login failed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        sleep "$INTERVAL_SEC"
        continue
    fi

    SNAP="$(curl -fsS \
        -H "Authorization: Bearer $TOKEN" \
        "$API/api/diagnostics/soak-snapshot?window_minutes=$WINDOW_MINUTES" \
        2>/dev/null || true)"

    if [ -z "$SNAP" ]; then
        echo "[soak_poll] WARN — snapshot fetch failed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    else
        # Annotate the host-side capture timestamp and append.
        POLLED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "$SNAP" \
            | python3 -c "import sys,json; d=json.load(sys.stdin); d['_polled_at']='$POLLED_AT'; print(json.dumps(d, separators=(',', ':')))" \
            >> "$OUT_FILE"
        # Print just the summary line for live observation.
        echo "$SNAP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
parts = ['$POLLED_AT', 'overall=' + d.get('overall_verdict', '?')]
for k, v in (d.get('summary') or {}).items():
    parts.append(f'{k}={v}')
print(' | '.join(parts))
"
    fi

    sleep "$INTERVAL_SEC"
done
