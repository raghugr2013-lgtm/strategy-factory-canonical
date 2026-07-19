"""Prometheus text-format exporter for Phase 2 metrics.

Exposes the `MetricsRegistry` at `/api/coe/metrics` in canonical
Prometheus exposition format so Grafana / Alertmanager can scrape.

Feature-gated: `COE_METRICS_ENABLED=false` → endpoint returns HTTP 503.
"""
from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, HTTPException, Response

from .metrics import get_metrics

router = APIRouter(prefix="/api/coe", tags=["coe"])


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


@router.get("/metrics")
async def metrics_endpoint() -> Response:
    if not _flag("COE_METRICS_ENABLED", False):
        raise HTTPException(status_code=503, detail="COE_METRICS_ENABLED is off")
    snap = get_metrics().snapshot()
    lines: List[str] = ["# HELP coe_metrics Phase 2 Compute Orchestration Engine metrics"]

    # Counters
    for key, v in sorted(snap.get("counters", {}).items()):
        name, labels = _split_key(key)
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name}{labels} {v}")

    # Gauges
    for key, v in sorted(snap.get("gauges", {}).items()):
        name, labels = _split_key(key)
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name}{labels} {v}")

    # Histograms — expose as summary (count/sum + p50/p95/p99 as gauges)
    for key, h in sorted(snap.get("histograms", {}).items()):
        name, labels = _split_key(key)
        lines.append(f"# TYPE {name} summary")
        lines.append(f"{name}_count{labels} {h['count']}")
        lines.append(f"{name}_sum{labels} {h['sum']}")
        for q, tag in (("p50", "0.5"), ("p95", "0.95"), ("p99", "0.99")):
            q_labels = _merge_quantile(labels, tag)
            lines.append(f"{name}{q_labels} {h[q]}")

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")


@router.get("/state")
async def state_endpoint() -> dict:
    """Aggregated diagnostic snapshot — JSON."""
    if not _flag("COE_METRICS_ENABLED", False):
        raise HTTPException(status_code=503, detail="COE_METRICS_ENABLED is off")
    return {
        "metrics": get_metrics().snapshot(),
    }


def _split_key(key: str) -> tuple[str, str]:
    """Return (name, "{labels}" or "")."""
    if "{" not in key:
        return key, ""
    idx = key.index("{")
    return key[:idx], key[idx:]


def _merge_quantile(labels: str, q: str) -> str:
    if not labels:
        return f'{{quantile="{q}"}}'
    # Insert quantile label
    return labels[:-1] + f',quantile="{q}"}}'
