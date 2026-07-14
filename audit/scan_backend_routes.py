#!/usr/bin/env python3
"""Enumerate every FastAPI route the backend would expose given the current
mounting logic in app/main.py.

Simulates the two mount phases:
  1. Phase-1 core routers (already have absolute /api prefixes hard-coded).
  2. Legacy full-recovery mount block (conflict_map + primary_names + latent_names + auto_factory).
"""
import ast
import os
import re
from pathlib import Path

ROOT = Path("/app/backend")

# ── Phase-1 core routers (hard-coded prefixes inside files) ─────────
PHASE1_FILES = {
    "app.api.health":     "app/api/health.py",
    "app.auth.routes":    "app/auth/routes.py",
    "app.api.admin":      "app/api/admin.py",
    "app.api.strategies": "app/api/strategies.py",
    "app.api.research":   "app/api/research.py",
    "app.api.dashboard":  "app/api/dashboard.py",
}

CONFLICT_MAP = {
    "admin": "/api/legacy",
    "strategies": "/api/legacy",
    "dashboard": "/api/legacy",
    "readiness": "/api/legacy",
}

PRIMARY_NAMES = [
    "admin", "admin_execution_realism", "admin_flag_governance", "admin_market_universe",
    "asf", "auto_mutation", "auto_selection",
    "bi5_cert_sweep", "bi5_certification", "bi5_ingest", "bi5_realism",
    "cbot", "cbot_parity",
    "challenge",
    "cpu_pool_state", "dashboard",
    "data", "data_health", "data_maintenance",
    "deployment", "diag_bi5_health",
    "execution", "factory_supervisor", "gem_factory", "governance",
    "incremental_run_alias", "ingestion",
    "lifecycle", "live_tracking", "llm_diagnostics", "llm_health",
    "master_bot", "monitoring", "multi_cycle", "mutation",
    "optimization", "orchestrator", "orchestrator_heartbeat",
    "phase12_tuning", "phase4_matching",
    "pipeline", "pipeline_logs",
    "portfolio", "portfolio_builder", "portfolio_intelligence",
    "prop_firm_intelligence", "prop_firm_rules_review", "prop_firms",
    "readiness", "regime", "research_lineage",
    "runner", "scaling", "soak_diagnostics",
    "strategies", "strategy_memory", "trade_runner",
    # not in primary_names but referenced separately: dashboard_route, phase4_route (side-effect attachers)
    "market_intelligence", "challenge_matching", "prop_firm_analysis",
]

LATENT_NAMES = [
    "activation_governance", "activation_timeline",
    "advanced_scaffolding", "calibration",
    "cbot_log_diagnostic", "cbot_trade_parity",
    "compute_probe",
    "deployment_extras", "deployment_readiness",
    "execution_realism_defaults", "factory_runner_heartbeat",
    "feature_flags", "htf_parity",
    "ingestion_aggregate", "ingestion_health", "lifecycle_decay",
    "market_universe", "observability",
    "parity_certification", "risk_of_ruin",
    "safe_to_widen", "widening_history",
]

def extract_router_prefixes(path: Path):
    """Return list of (variable_name, prefix) for every APIRouter(...) call in file."""
    src = path.read_text()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            # APIRouter(prefix="...")
            func = node.value.func
            if isinstance(func, ast.Name) and func.id in ("APIRouter",):
                prefix = ""
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out.append((t.id, prefix))
    return out

def extract_route_decorators(path: Path):
    """Return list of (router_var, method, path) for every @router.<method>() call."""
    src = path.read_text()
    tree = ast.parse(src)
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    method = dec.func.attr
                    if method in ("get", "post", "delete", "put", "patch", "head", "options"):
                        router_var = None
                        if isinstance(dec.func.value, ast.Name):
                            router_var = dec.func.value.id
                        if dec.args and isinstance(dec.args[0], ast.Constant):
                            routes.append((router_var, method.upper(), dec.args[0].value))
    return routes

def analyze_file(path: Path, mount_prefix: str, label: str, all_routes: list):
    prefixes = dict(extract_router_prefixes(path))
    routes   = extract_route_decorators(path)
    for router_var, method, sub in routes:
        r_pref = prefixes.get(router_var, "")
        full = f"{mount_prefix}{r_pref}{sub}"
        # collapse duplicate slashes
        full = re.sub(r'/+', '/', full)
        all_routes.append((method, full, label))

def main():
    all_routes = []

    # ── Phase 1 core ────────────────────────────────────────────────
    for label, rel in PHASE1_FILES.items():
        p = ROOT / rel
        if p.exists():
            analyze_file(p, "", f"phase1:{label}", all_routes)

    # ── Legacy primary ─────────────────────────────────────────────
    for name in PRIMARY_NAMES:
        p = ROOT / "legacy" / "api" / f"{name}.py"
        if not p.exists():
            continue
        mount = CONFLICT_MAP.get(name, "/api")
        analyze_file(p, mount, f"legacy:{name}", all_routes)

    # dashboard_route / phase4_route (side-effect attachers)
    # They attach onto legacy.api.strategies router (which is under /api/legacy per conflict_map)
    for name in ("dashboard_route", "phase4_route"):
        p = ROOT / "legacy" / "api" / f"{name}.py"
        if p.exists():
            mount = CONFLICT_MAP.get("strategies", "/api")
            analyze_file(p, mount, f"legacy:{name}", all_routes)

    # ── Auto factory (mounted with prefix /api) ────────────────────
    p = ROOT / "legacy" / "api" / "auto_factory.py"
    if p.exists():
        analyze_file(p, "/api", "legacy:auto_factory", all_routes)

    # ── Latent under /api/latent? or /api? Actually main.py mounts them at /api ──
    for name in LATENT_NAMES:
        p = ROOT / "legacy" / "api" / "latent" / f"{name}.py"
        if p.exists():
            analyze_file(p, "/api", f"latent:{name}", all_routes)

    # Print sorted
    for m, path, lbl in sorted(set(all_routes), key=lambda x: (x[1], x[0])):
        print(f"{m:6s} {path:70s} :: {lbl}")

if __name__ == "__main__":
    main()
