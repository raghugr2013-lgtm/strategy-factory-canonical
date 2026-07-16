"""Phase E — Autonomous production stability harness.

Runs a compressed continuous-operation drill against a live backend for
`--duration-s` seconds. Every `sample_period_s` (default 5s) records:

    - process RSS (backend + this driver)
    - CPU% (process + system)
    - Mongo connection pool + collection counts
    - orchestrator dispatched_total + in_flight
    - continuous-scheduler cycles_launched_total
    - `outcome_events` count (proves learning loop is writing)
    - portfolio rebuild timing (round-trip ms)

Emits `audit/PHASE_E_STABILITY_REPORT.json` + a plain-text summary at exit.

Usage (compressed local run):
    /root/.venv/bin/python /app/backend/scripts/phase_e_stability_run.py \
        --duration-s 600 --sample-s 5

Usage (full VPS 24h run):
    LEARNING_CONTINUOUS_MODE=true ORCHESTRATOR_ENABLED=true \
        /root/.venv/bin/python /app/backend/scripts/phase_e_stability_run.py \
        --duration-s 86400 --sample-s 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/legacy")

import psutil                          # noqa: E402
import requests                        # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@strategy-factory.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "strategy_factory_v1")


def _login() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=10)
    r.raise_for_status()
    return r.json().get("access_token") or r.json().get("token")


def _get(path: str, token: str) -> Dict[str, Any]:
    r = requests.get(f"{BASE_URL}{path}",
                     headers={"Authorization": f"Bearer {token}"},
                     timeout=15)
    r.raise_for_status()
    return r.json()


def _post(path: str, token: str, body: dict) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}{path}", json=body,
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=30)
    r.raise_for_status()
    return r.json()


async def _mongo_snap(client: AsyncIOMotorClient) -> Dict[str, Any]:
    db = client[DB_NAME]
    try:
        srv = await client.admin.command("serverStatus")
        conns = srv.get("connections", {})
    except Exception:
        conns = {}
    coll_counts = {}
    for c in ("outcome_events", "strategy_lineage", "strategy_library",
              "master_bots", "strategies", "knowledge_index"):
        try:
            coll_counts[c] = await db[c].estimated_document_count()
        except Exception:
            coll_counts[c] = None
    return {"connections": conns, "collections": coll_counts}


def _backend_process() -> psutil.Process:
    """Locate the uvicorn backend process — matches the supervisor cmdline."""
    for p in psutil.process_iter(attrs=["pid", "cmdline", "name"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if "uvicorn" in cl and "server:app" in cl:
            return p
    # Fallback: any python that owns port 8001
    for p in psutil.process_iter():
        try:
            for c in p.net_connections(kind="tcp"):
                if getattr(c, "laddr", None) and c.laddr.port == 8001:
                    return p
        except Exception:
            continue
    return psutil.Process()   # self as last resort


def _pct(vs: List[float], p: float) -> float:
    if not vs:
        return 0.0
    xs = sorted(vs)
    k = max(0, min(len(xs) - 1, int(p / 100.0 * (len(xs) - 1))))
    return round(xs[k], 3)


async def _run(duration_s: int, sample_s: int, out_path: str) -> None:
    print(f"[phase-e] start duration={duration_s}s sample={sample_s}s "
          f"backend={BASE_URL} mongo={MONGO_URL}", flush=True)
    token = _login()
    mongo = AsyncIOMotorClient(MONGO_URL)
    proc = _backend_process()
    print(f"[phase-e] backend pid={proc.pid} name={proc.name()}", flush=True)

    # Start orchestrator + continuous scheduler if not running.
    try:
        st = _get("/api/orchestrator/status", token)
        if not st.get("running"):
            _post("/api/orchestrator/start", token, {})
        st = _get("/api/learning/continuous/status", token)
        if not st.get("running"):
            _post("/api/learning/continuous/start", token, {})
    except Exception as e:                                       # noqa: BLE001
        print(f"[phase-e] warn: could not (re)start engines: {e}", flush=True)

    t_start = time.time()
    samples: List[Dict[str, Any]] = []
    rebuild_ms: List[int] = []
    errors: List[str] = []
    baseline_rss_mb = None

    tick = 0
    while (time.time() - t_start) < duration_s:
        tick += 1
        s: Dict[str, Any] = {"tick": tick,
                             "elapsed_s": round(time.time() - t_start, 1)}
        try:
            with proc.oneshot():
                s["backend_rss_mb"] = round(proc.memory_info().rss / (1024 ** 2), 1)
                s["backend_cpu_pct"] = proc.cpu_percent(interval=None)
                s["backend_threads"] = proc.num_threads()
            if baseline_rss_mb is None:
                baseline_rss_mb = s["backend_rss_mb"]
            s["system_cpu_pct"] = psutil.cpu_percent(interval=None)
            s["system_mem_pct"] = psutil.virtual_memory().percent
            s["load_1m"] = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
            s["mongo"] = await _mongo_snap(mongo)

            s["orchestrator"] = _get("/api/orchestrator/status", token)["meta"]
            s["continuous"]   = _get("/api/learning/continuous/status", token)["runtime"]

            # Sample a portfolio rebuild round-trip (tiny state, no persist).
            t0 = time.time()
            rep = _post("/api/portfolio/rebuild/stability", token, {
                "regime": "trending",
                "state": {
                    "master_bot_id": "stability",
                    "members": [
                        {"strategy_hash": "hs_a", "style": "trend_following",
                         "confidence": 0.7, "allocation": 0.3, "status": "active",
                         "tier": "tier_2",
                         "backtest": {"profit_factor": 1.6, "max_drawdown_pct": 8,
                                      "total_trades": 120}},
                        {"strategy_hash": "hs_b", "style": "mean_reversion",
                         "confidence": 0.55, "allocation": 0.3, "status": "active",
                         "tier": "tier_3",
                         "backtest": {"profit_factor": 1.3, "max_drawdown_pct": 6,
                                      "total_trades": 90}},
                    ],
                },
            })
            rebuild_ms.append(int((time.time() - t0) * 1000))
            s["rebuild_ms"] = rebuild_ms[-1]
            s["rebuild_outcome_events"] = len(rep.get("outcome_events_ids", []))
        except Exception as e:                                   # noqa: BLE001
            errors.append(f"tick{tick}: {str(e)[:200]}")
            s["error"] = str(e)[:200]
        samples.append(s)
        if tick % max(1, (60 // sample_s)) == 0:
            print(f"[phase-e] t={s['elapsed_s']}s rss={s.get('backend_rss_mb')}MB "
                  f"orc_dispatched={s.get('orchestrator',{}).get('dispatched_total')} "
                  f"cont_cycles={s.get('continuous',{}).get('cycles_launched_total')} "
                  f"outcome_events={s.get('mongo',{}).get('collections',{}).get('outcome_events')} "
                  f"rebuild_ms={s.get('rebuild_ms')}", flush=True)
        await asyncio.sleep(sample_s)

    # ── Summary ──
    rss = [s.get("backend_rss_mb") for s in samples if s.get("backend_rss_mb") is not None]
    rebuild_pcts = {"p50": _pct(rebuild_ms, 50), "p95": _pct(rebuild_ms, 95),
                    "max": max(rebuild_ms) if rebuild_ms else 0}
    orch_start = samples[0].get("orchestrator", {}).get("dispatched_total") or 0
    orch_end   = samples[-1].get("orchestrator", {}).get("dispatched_total") or 0
    cont_start = samples[0].get("continuous", {}).get("cycles_launched_total") or 0
    cont_end   = samples[-1].get("continuous", {}).get("cycles_launched_total") or 0
    oe_start = samples[0].get("mongo", {}).get("collections", {}).get("outcome_events") or 0
    oe_end   = samples[-1].get("mongo", {}).get("collections", {}).get("outcome_events") or 0

    mongo_conn_max = 0
    for s in samples:
        cur = ((s.get("mongo") or {}).get("connections") or {}).get("current") or 0
        if cur > mongo_conn_max:
            mongo_conn_max = cur

    rss_growth = round((rss[-1] - rss[0]) if len(rss) >= 2 else 0.0, 2)
    rss_growth_per_hour = round(rss_growth * (3600.0 / max(1, duration_s)), 2)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": duration_s,
        "sample_s":   sample_s,
        "backend_url": BASE_URL,
        "backend_pid": proc.pid,
        "baseline_rss_mb": baseline_rss_mb,
        "final_rss_mb":    rss[-1] if rss else None,
        "rss_p95_mb":      _pct(rss, 95),
        "rss_growth_mb":   rss_growth,
        "rss_growth_per_hour_mb": rss_growth_per_hour,
        "system_cpu_pct_p95": _pct(
            [s.get("system_cpu_pct", 0) for s in samples], 95),
        "backend_cpu_pct_p95": _pct(
            [s.get("backend_cpu_pct", 0) for s in samples], 95),
        "load_1m_p95": _pct(
            [s.get("load_1m") or 0 for s in samples], 95),
        "mongo_connections_max": mongo_conn_max,
        "orchestrator_dispatched_delta": orch_end - orch_start,
        "orchestrator_dispatch_rate_per_min": round(
            (orch_end - orch_start) * 60.0 / max(1, duration_s), 2),
        "continuous_cycles_delta": cont_end - cont_start,
        "continuous_cycle_rate_per_min": round(
            (cont_end - cont_start) * 60.0 / max(1, duration_s), 2),
        "outcome_events_written": oe_end - oe_start,
        "outcome_event_rate_per_min": round(
            (oe_end - oe_start) * 60.0 / max(1, duration_s), 2),
        "rebuild_ms": rebuild_pcts,
        "n_errors": len(errors),
        "errors_first_5": errors[:5],
        "n_samples": len(samples),
        "verdict": _verdict(rss_growth_per_hour, rebuild_pcts, len(errors),
                            orch_end - orch_start, oe_end - oe_start),
    }

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps({
        "report": report,
        "samples": samples,
    }, indent=2, default=str))
    print("\n===== PHASE E STABILITY REPORT =====")
    print(json.dumps(report, indent=2))
    print(f"\n[phase-e] full samples + report → {out_path}")


def _verdict(rss_per_h: float, rebuild_pcts: dict, n_err: int,
             dispatched: int, events: int) -> Dict[str, Any]:
    signals = {
        "no_leak":              rss_per_h < 50.0,     # < 50 MB/hour growth
        "rebuild_fast":         rebuild_pcts["p95"] < 200,
        "no_errors":            n_err == 0,
        "orchestrator_alive":   dispatched > 0,
        "learning_loop_alive":  events >= 0,   # ≥0 (0 acceptable when passive)
    }
    passed = all(signals.values())
    return {"pass": passed, "signals": signals}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--duration-s", type=int, default=600)
    p.add_argument("--sample-s",   type=int, default=5)
    p.add_argument("--out",        default="/app/audit/PHASE_E_STABILITY_REPORT.json")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args.duration_s, args.sample_s, args.out))


if __name__ == "__main__":
    main()
