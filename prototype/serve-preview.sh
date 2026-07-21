#!/usr/bin/env bash
# Serve the prototype's built dist on port 3000 so the Emergent preview
# URL routes to it. Vite `preview` provides SPA-fallback for our
# non-hash routes (/c/*, /prototype/*, /auth/*).
#
# Usage:
#   sudo supervisorctl stop frontend        # free port 3000
#   bash /app/prototype/serve-preview.sh &  # launch, background
#
# Or invoked via nohup by the main agent when starting a walkthrough.
set -euo pipefail
cd /app/prototype
exec npx vite preview --host 0.0.0.0 --port 3000 --strictPort
