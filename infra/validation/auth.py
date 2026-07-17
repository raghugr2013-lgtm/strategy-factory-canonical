"""JWT session helper. Fails immediately if login fails."""
from __future__ import annotations

import sys
from typing import Optional

import requests

from . import config


class AuthError(RuntimeError):
    pass


class Session:
    """Wraps requests.Session with JWT reuse + probe metrics helper."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json"})
        self.token: Optional[str] = None
        self.email: str = config.ADMIN_EMAIL

    def login(self) -> str:
        r = self.s.post(
            f"{config.BASE_URL}/api/auth/login",
            json={"email": config.ADMIN_EMAIL,
                  "password": config.ADMIN_PASSWORD},
            timeout=config.TIMEOUT_S,
        )
        if r.status_code != 200:
            raise AuthError(
                f"login failed: HTTP {r.status_code} — {r.text[:200]}")
        body = r.json()
        tok = body.get("access_token") or body.get("token")
        if not tok:
            raise AuthError(f"login OK but no token: {body}")
        self.token = tok
        self.s.headers.update({"Authorization": f"Bearer {tok}"})
        return tok


def require_session() -> Session:
    """Login and return an authenticated session. Exit(2) on failure."""
    sess = Session()
    try:
        sess.login()
        return sess
    except (AuthError, requests.RequestException) as e:
        sys.stderr.write(f"[FATAL] authentication failed: {e}\n")
        sys.exit(2)
