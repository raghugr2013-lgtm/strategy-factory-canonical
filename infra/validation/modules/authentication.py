"""Module 2 — Authentication."""
from __future__ import annotations
from typing import List
import requests
from .. import config
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class AuthenticationModule(ModuleRunner):
    NAME = "authentication"

    def run(self, sess: Session) -> List[ProbeResult]:
        out: List[ProbeResult] = []
        # 1. /auth/me — token roundtrip
        out.append(probe(sess, module=self.NAME, name="jwt_valid_me",
                          method="GET", path="/api/auth/me"))

        # 2. Bad credentials → 401 expected
        r_bad = requests.post(f"{config.BASE_URL}/api/auth/login",
                                json={"email": "does-not-exist@x", "password": "nope"},
                                timeout=config.TIMEOUT_S)
        status = "PASS" if r_bad.status_code in (401, 400, 422) else "FAIL"
        out.append(ProbeResult(
            module=self.NAME, name="reject_bad_credentials", method="POST",
            path="/api/auth/login", status=status, http_status=r_bad.status_code,
            response_bytes=len(r_bad.content or b""),
            detail=f"got HTTP {r_bad.status_code}, expected 401/400/422"))

        # 3. Missing token → 401
        r_no = requests.get(f"{config.BASE_URL}/api/auth/me",
                              timeout=config.TIMEOUT_S)
        status = "PASS" if r_no.status_code == 401 else "FAIL"
        out.append(ProbeResult(
            module=self.NAME, name="unauth_requires_token", method="GET",
            path="/api/auth/me", status=status, http_status=r_no.status_code,
            response_bytes=len(r_no.content or b"")))
        return out
