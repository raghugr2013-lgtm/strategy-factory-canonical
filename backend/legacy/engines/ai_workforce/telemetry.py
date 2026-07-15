"""AI Workforce telemetry — records every LLM call for observability + scoring."""
from __future__ import annotations

import time
from collections import deque
from threading import RLock
from typing import Deque, Dict, List, Optional

from .circuit_breaker import get_breaker

RING_SIZE = 500


class _Telemetry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._ring: Deque[Dict[str, object]] = deque(maxlen=RING_SIZE)

    def record(
        self, *,
        provider: str,
        model: str,
        task: str,
        ok: bool,
        latency_ms: int,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        http_status: Optional[int] = None,
        error_class: str = "",
        error: str = "",
        cost_usd: Optional[float] = None,
    ) -> None:
        ts = time.time()
        with self._lock:
            self._ring.append({
                "ts": ts,
                "provider": provider,
                "model": model,
                "task": task,
                "ok": ok,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "http_status": http_status,
                "error_class": error_class,
                "cost_usd": cost_usd,
            })
        get_breaker().record(provider, ok, error=error)

    def snapshot(self, window_s: int = 3600) -> Dict[str, Dict[str, object]]:
        cutoff = time.time() - window_s
        acc: Dict[str, Dict[str, object]] = {}
        with self._lock:
            calls = [c for c in self._ring if c["ts"] >= cutoff]
        for c in calls:
            p = c["provider"] or "unknown"
            b = acc.setdefault(p, {
                "calls": 0, "ok": 0, "fail": 0,
                "latency_samples": [], "tokens_prompt": 0,
                "tokens_completion": 0, "cost_usd": 0.0,
                "model": c["model"], "last_error": "",
            })
            b["calls"] += 1
            if c["ok"]:
                b["ok"] += 1
            else:
                b["fail"] += 1
                if c.get("error_class"):
                    b["last_error"] = c["error_class"]
            b["latency_samples"].append(int(c["latency_ms"]))
            if c["prompt_tokens"]:     b["tokens_prompt"] += int(c["prompt_tokens"])
            if c["completion_tokens"]: b["tokens_completion"] += int(c["completion_tokens"])
            if c["cost_usd"]:          b["cost_usd"] += float(c["cost_usd"])
        for p, b in acc.items():
            samples = sorted(b.pop("latency_samples"))
            n = len(samples)
            b["latency_p50_ms"] = samples[n // 2] if n else 0
            b["latency_p95_ms"] = samples[int(n * 0.95)] if n else 0
            b["error_rate"] = (b["fail"] / b["calls"]) if b["calls"] else 0.0
        return acc

    def recent(self, limit: int = 50) -> List[Dict[str, object]]:
        with self._lock:
            return list(self._ring)[-limit:]


_TELEMETRY = _Telemetry()


def get_telemetry() -> _Telemetry:
    return _TELEMETRY
