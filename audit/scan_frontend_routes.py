#!/usr/bin/env python3
"""Extract every distinct backend API endpoint the React frontend calls.
Templates like ${id} are normalised to {id} so comparison with backend
routes is meaningful.
"""
import re
from pathlib import Path

ROOT = Path("/app/frontend/src")

# Regex captures anything after /api/ up until the first quote, backtick,
# whitespace, question mark, dollar-brace (template close), or backslash.
PATH_RE = re.compile(r'/api/[A-Za-z0-9_\-/{}\.]+')

# We also try to detect ${var} inside template literals and reduce them
# to placeholders so we can match against FastAPI's {param} syntax.
def normalise(p: str) -> str:
    # keep only path portion; strip trailing punctuation
    p = re.sub(r'[)\]\},].*$', '', p)
    p = re.sub(r'/\$\{[^}]*\}', '/{param}', p)
    p = re.sub(r'\$\{[^}]*\}', '{param}', p)
    # trim trailing "/" only if the path length > /api/x
    if p.endswith('/') and len(p) > 5:
        p = p[:-1]
    return p

paths = set()
for f in ROOT.rglob('*.js'):
    txt = f.read_text(errors='ignore')
    # combine template literals then search
    for m in PATH_RE.findall(txt):
        paths.add(normalise(m))
for f in ROOT.rglob('*.jsx'):
    txt = f.read_text(errors='ignore')
    for m in PATH_RE.findall(txt):
        paths.add(normalise(m))

# Also handle template literal patterns  `${API_URL}/api/...`
TEMPLATE_RE = re.compile(r'`\$\{API_URL\}([^`]+)`')
for f in list(ROOT.rglob('*.js')) + list(ROOT.rglob('*.jsx')):
    txt = f.read_text(errors='ignore')
    for m in TEMPLATE_RE.findall(txt):
        m = re.sub(r'\?.*$', '', m)  # drop query string
        paths.add(normalise(m))

for p in sorted(paths):
    print(p)
