#!/usr/bin/env python3
"""
Sprint 2 · SPA-fallback static server for Playwright tests.
Any request that misses a real file (and is not under /static/) returns index.html.
Bound to 127.0.0.1:4173 by default.
"""
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'build')
PORT = int(sys.argv[2] if len(sys.argv) > 2 else 4173)

class SPAHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # strip query string
        real = super().translate_path(path.split('?', 1)[0])
        if os.path.isdir(real):
            candidate = os.path.join(real, 'index.html')
            return candidate if os.path.exists(candidate) else real
        if os.path.exists(real):
            return real
        # Do not fallback for static asset requests — they should 404 for real.
        if '/static/' in path or path.endswith(('.js', '.css', '.map', '.png', '.jpg', '.svg', '.ico', '.woff', '.woff2', '.json')):
            return real
        return os.path.join(ROOT, 'index.html')

    def log_message(self, *args):
        pass  # keep the console clean

if __name__ == '__main__':
    os.chdir(ROOT)
    server = ThreadingHTTPServer(('127.0.0.1', PORT), SPAHandler)
    print(f'SPA server ready · http://127.0.0.1:{PORT} · root={ROOT}')
    server.serve_forever()
