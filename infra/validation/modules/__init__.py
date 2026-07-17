"""Common probe + result types + module runner base class."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

import requests

from .. import config
from ..auth import Session


@dataclass
class ProbeResult:
    module: str
    name: str
    method: str
    path: str
    status: str          # "PASS" | "FAIL" | "WARN"
    http_status: Optional[int] = None
    duration_ms: float = 0.0
    response_bytes: int = 0
    detail: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def probe(
    sess: Session, *, module: str, name: str, method: str, path: str,
    expect: Any = 200, json_body: Optional[dict] = None,
    warn_on_status: Optional[List[int]] = None,
    slow_warn_ms: Optional[int] = None,
    validate: Optional[Callable[[requests.Response], Optional[str]]] = None,
) -> ProbeResult:
    """Execute an HTTP probe and grade it.

    `expect` accepts an int, a list/tuple of ints, or a callable returning
    True/False. HTTP mismatch → FAIL. `validate(response)` may return a
    non-empty string to override to FAIL/WARN based on body semantics
    (return `"warn: ..."` prefix to mark WARN).
    `warn_on_status` codes are treated as WARN not FAIL.
    """
    warn_on_status = warn_on_status or []
    slow_warn_ms = slow_warn_ms or config.SLOW_MS_WARN
    url = f"{config.BASE_URL}{path}"
    t0 = time.time()
    http = None
    body_len = 0
    try:
        r = sess.s.request(method, url, json=json_body,
                            timeout=config.TIMEOUT_S)
        http = r.status_code
        body_len = len(r.content or b"")
    except requests.RequestException as e:
        return ProbeResult(module=module, name=name, method=method,
                            path=path, status="FAIL",
                            duration_ms=(time.time() - t0) * 1000,
                            detail=f"exception: {e}")

    duration_ms = (time.time() - t0) * 1000
    status = "PASS"
    detail = ""

    # HTTP-status grading
    expected_ok = False
    if callable(expect):
        expected_ok = bool(expect(http))
    elif isinstance(expect, (list, tuple, set)):
        expected_ok = http in expect
    else:
        expected_ok = http == expect

    if not expected_ok:
        if http in warn_on_status:
            status = "WARN"
            detail = f"unexpected HTTP {http} (warn-listed)"
        else:
            status = "FAIL"
            detail = f"unexpected HTTP {http} (expected {expect})"

    # Body-level validation (only if HTTP ok)
    if status == "PASS" and validate is not None:
        try:
            msg = validate(r)
            if msg:
                if msg.startswith("warn:"):
                    status = "WARN"; detail = msg[5:].strip()
                else:
                    status = "FAIL"; detail = msg
        except Exception as e:  # noqa: BLE001
            status = "FAIL"; detail = f"validator raised: {e}"

    # Latency-warn (only if it wasn't already flagged)
    if status == "PASS" and duration_ms > slow_warn_ms:
        status = "WARN"
        detail = f"slow: {duration_ms:.0f}ms > {slow_warn_ms}ms"

    return ProbeResult(
        module=module, name=name, method=method, path=path,
        status=status, http_status=http, duration_ms=duration_ms,
        response_bytes=body_len, detail=detail,
    )


class ModuleRunner:
    """Base class — each module subclasses + overrides run()."""

    NAME: str = "base"

    def run(self, sess: Session) -> List[ProbeResult]:
        raise NotImplementedError
