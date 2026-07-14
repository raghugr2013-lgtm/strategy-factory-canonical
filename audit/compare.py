#!/usr/bin/env python3
"""Compare frontend expectations vs backend exposure.
Generates a canonical mismatch report as Markdown.
"""
import re
from pathlib import Path

FE = Path("/app/audit/frontend_routes.txt")
BE = Path("/app/audit/backend_routes.txt")

# Load frontend paths (strip method-less)
fe_paths = set()
for line in FE.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('/api/...') or '${' in line:
        continue
    if not line.startswith('/api/'):
        continue
    fe_paths.add(line)

# Load backend routes → set of paths (path templates)
be_map = {}  # path -> set of methods
for line in BE.read_text().splitlines():
    if not line.strip():
        continue
    parts = line.split(maxsplit=2)
    if len(parts) < 2:
        continue
    method, path = parts[0], parts[1]
    be_map.setdefault(path, set()).add(method)

# Normalise: backend uses {var} placeholders; frontend text extracted may
# have trailing partial names. We try lenient matching:
#   - exact match, or
#   - frontend path is prefix of backend path, or
#   - after collapsing all /{var}/ into /*/ both match.

def strip_params(p: str) -> str:
    return re.sub(r'/\{[^}]+\}', '/*', p)

fe_norm = {p: strip_params(p) for p in fe_paths}
be_norm = {p: strip_params(p) for p in be_map}

# Bucket check
be_by_norm = {}
for bp, np_ in be_norm.items():
    be_by_norm.setdefault(np_, []).append(bp)

mismatches = []  # (fe_path, resolution)
exact = []
partial = []

for fp, fn in sorted(fe_norm.items()):
    # exact match
    if fp in be_map:
        exact.append(fp)
        continue
    # normalised match
    hits = be_by_norm.get(fn, [])
    if hits:
        exact.append(f"{fp} → (backend has {hits[0]})")
        continue
    # partial (fe is prefix of a backend path)
    prefix_hits = [b for b in be_map if b.startswith(fp) or b.startswith(fp + '/')]
    if prefix_hits:
        partial.append((fp, prefix_hits[:3]))
        continue
    # look in /api/legacy/
    legacy_candidate = "/api/legacy" + fp[len("/api"):]
    legacy_norm = strip_params(legacy_candidate)
    legacy_hits = be_by_norm.get(legacy_norm, [])
    if legacy_hits:
        mismatches.append((fp, f"MOUNTED_AT_LEGACY: {legacy_hits[0]}"))
        continue
    mismatches.append((fp, "MISSING_IN_BACKEND"))

out = []
out.append("# Strategy Factory — Frontend ↔ Backend API Mismatch Report\n")
out.append(f"Total distinct frontend paths analysed: **{len(fe_paths)}**  ")
out.append(f"Total backend paths analysed: **{len(be_map)}**\n")
out.append("---\n")
out.append(f"## MISMATCHES ({len(mismatches)})\n")
out.append("| Frontend path | Resolution |\n|---|---|")
for fp, res in mismatches:
    out.append(f"| `{fp}` | {res} |")
out.append(f"\n## PARTIAL/PREFIX MATCHES ({len(partial)})\n")
out.append("| Frontend base | Backend hits |\n|---|---|")
for fp, hits in partial:
    out.append(f"| `{fp}` | " + ", ".join(f"`{h}`" for h in hits) + " |")
out.append(f"\n## EXACT MATCHES ({len(exact)})\n")
for fp in exact:
    out.append(f"- `{fp}`")

Path("/app/audit/MISMATCH_REPORT.md").write_text("\n".join(out))
print(f"Report → /app/audit/MISMATCH_REPORT.md")
print(f"Mismatches: {len(mismatches)}")
print(f"Partial:    {len(partial)}")
print(f"Exact:      {len(exact)}")
