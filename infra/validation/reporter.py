"""Reporter — aggregates ProbeResult rows into JSON/MD/TXT + console."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import config
from .modules import ProbeResult


COLORS = {
    "PASS": "\033[92m", "FAIL": "\033[91m", "WARN": "\033[93m",
    "RESET": "\033[0m", "BOLD": "\033[1m",
}


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stats(rows: List[ProbeResult]) -> Dict[str, Any]:
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    lat = [r.duration_ms for r in rows if r.duration_ms > 0]
    return {
        "total": len(rows),
        "pass": counts["PASS"], "fail": counts["FAIL"], "warn": counts["WARN"],
        "avg_ms": round(statistics.mean(lat), 2) if lat else 0.0,
        "p95_ms": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 2)
                    if lat else 0.0,
        "min_ms": round(min(lat), 2) if lat else 0.0,
        "max_ms": round(max(lat), 2) if lat else 0.0,
        "total_bytes": sum(r.response_bytes for r in rows),
    }


def _by_module(rows: List[ProbeResult]) -> Dict[str, List[ProbeResult]]:
    out: Dict[str, List[ProbeResult]] = {}
    for r in rows:
        out.setdefault(r.module, []).append(r)
    return out


def render_console(rows: List[ProbeResult]) -> str:
    lines = []
    by_mod = _by_module(rows)
    for mod, mod_rows in by_mod.items():
        st = _stats(mod_rows)
        if st["fail"] > 0:
            tag = "FAIL"
        elif st["warn"] > 0:
            tag = "WARN"
        else:
            tag = "PASS"
        c = COLORS[tag]
        lines.append(
            f"[{c}{tag}{COLORS['RESET']}] {COLORS['BOLD']}{mod:<24}{COLORS['RESET']}"
            f" pass={st['pass']:>3} fail={st['fail']:>3} warn={st['warn']:>3}"
            f" avg={st['avg_ms']:>6.1f}ms p95={st['p95_ms']:>6.1f}ms"
        )
    st_all = _stats(rows)
    lines.append("")
    lines.append(f"Summary  PASS {st_all['pass']}   FAIL {st_all['fail']}"
                    f"   WARN {st_all['warn']}   avg_ms={st_all['avg_ms']}"
                    f"   p95_ms={st_all['p95_ms']}")
    return "\n".join(lines)


def render_markdown(rows: List[ProbeResult], meta: Dict[str, Any]) -> str:
    lines = [
        f"# Validation Report — {meta['run_id']}",
        f"",
        f"- **Started:** {meta['started_at']}",
        f"- **Finished:** {meta['finished_at']}",
        f"- **Duration:** {meta['duration_s']:.2f}s",
        f"- **Base URL:** `{meta['base_url']}`",
        f"",
        "## Aggregate",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
    ]
    st = _stats(rows)
    for k, v in [("Total probes", st["total"]),
                  ("PASS", st["pass"]), ("FAIL", st["fail"]),
                  ("WARN", st["warn"]),
                  ("Average latency (ms)", st["avg_ms"]),
                  ("p95 latency (ms)", st["p95_ms"]),
                  ("Fastest (ms)", st["min_ms"]),
                  ("Slowest (ms)", st["max_ms"]),
                  ("Total response bytes", st["total_bytes"])]:
        lines.append(f"| {k} | {v} |")

    # Per module
    for mod, mod_rows in _by_module(rows).items():
        lines += ["", f"## Module: `{mod}`", "",
                  "| # | Name | Method | Path | Status | HTTP | ms | bytes | Detail |",
                  "|---|------|--------|------|--------|------|----|-------|--------|"]
        for i, r in enumerate(mod_rows, 1):
            lines.append(
                f"| {i} | {r.name} | {r.method} | `{r.path}` | {r.status}"
                f" | {r.http_status or '-'} | {r.duration_ms:.1f} |"
                f" {r.response_bytes} | {r.detail or '-'} |")
    return "\n".join(lines) + "\n"


def render_txt(rows: List[ProbeResult], meta: Dict[str, Any]) -> str:
    st = _stats(rows)
    slowest = max(rows, key=lambda r: r.duration_ms) if rows else None
    fastest = min([r for r in rows if r.duration_ms > 0],
                    key=lambda r: r.duration_ms) if rows else None
    lines = [
        f"Validation Summary  ({meta['run_id']})",
        f"  started:   {meta['started_at']}",
        f"  finished:  {meta['finished_at']}",
        f"  duration:  {meta['duration_s']:.2f}s",
        f"  base_url:  {meta['base_url']}",
        f"",
        f"  PASS       {st['pass']}",
        f"  FAIL       {st['fail']}",
        f"  WARN       {st['warn']}",
        f"  avg_ms     {st['avg_ms']}",
        f"  p95_ms     {st['p95_ms']}",
    ]
    if slowest:
        lines.append(f"  slowest    {slowest.duration_ms:.1f}ms  "
                      f"{slowest.method} {slowest.path}")
    if fastest:
        lines.append(f"  fastest    {fastest.duration_ms:.1f}ms  "
                      f"{fastest.method} {fastest.path}")
    return "\n".join(lines) + "\n"


def write_reports(rows: List[ProbeResult], meta: Dict[str, Any]) -> Dict[str, Path]:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = meta['run_id']
    j = config.REPORTS_DIR / f"validation_report_{stamp}.json"
    m = config.REPORTS_DIR / f"validation_report_{stamp}.md"
    t = config.REPORTS_DIR / f"validation_summary_{stamp}.txt"

    payload = {"meta": meta, "stats": _stats(rows),
                "probes": [r.to_dict() for r in rows]}
    j.write_text(json.dumps(payload, indent=2))
    m.write_text(render_markdown(rows, meta))
    t.write_text(render_txt(rows, meta))

    # Also update "latest" symlinks (plain files, easy to grep)
    (config.REPORTS_DIR / "validation_report.json").write_text(
        json.dumps(payload, indent=2))
    (config.REPORTS_DIR / "validation_report.md").write_text(
        render_markdown(rows, meta))
    (config.REPORTS_DIR / "validation_summary.txt").write_text(
        render_txt(rows, meta))
    return {"json": j, "md": m, "txt": t}
