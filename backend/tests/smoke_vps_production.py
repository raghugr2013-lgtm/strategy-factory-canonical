"""
Comprehensive production VPS backend smoke test.
Target: https://strategy.coinnike.com

Runs sample-tests across all 21 priority tiers.
Continues past failures. Produces JSON report at /app/test_reports/vps_smoke_results.json.

Feature freeze: Stage-4 endpoints expected to return 503 (that is a PASS for dormancy).
"""
import json
import os
import time
from pathlib import Path

import requests

BASE_URL = "https://strategy.coinnike.com"
ADMIN_EMAIL = "admin@coinnike.com"
ADMIN_PASSWORD = "Tmn0SECEyDxV1KqfbHMw"
REPORT_PATH = Path("/app/test_reports/vps_smoke_results.json")
TIMEOUT = 20

# ---- Endpoint plan ----
# expected_status: int OR list of acceptable ints; None = "any 2xx"
# stage4: True => must return 503 (invariant check)
# body: dict/None for POST payload; missing => GET
# skip_reason: if set the endpoint is intentionally skipped

def T(method, path, tier, expected=None, stage4=False, body=None, skip=None, notes=""):
    return {
        "method": method,
        "path": path,
        "tier": tier,
        "expected": expected,
        "stage4": stage4,
        "body": body,
        "skip": skip,
        "notes": notes,
    }

PLAN = [
    # ---------- Tier 20: Health surface ----------
    T("GET", "/api/health", "20-health"),
    T("GET", "/api/health/config", "20-health"),
    T("GET", "/api/health/system", "20-health"),
    T("GET", "/api/health/subsystems", "20-health"),
    T("GET", "/api/version", "20-health"),

    # ---------- Tier 21: Auth flows ----------
    T("GET", "/api/auth/me", "21-auth"),
    T("POST", "/api/auth/refresh", "21-auth", body={}, notes="refresh flow (may 401 without refresh cookie)"),
    T("POST", "/api/auth/logout", "21-auth", body={}, notes="logout - safe on JWT"),
    T("POST", "/api/auth/register", "21-auth", expected=[400,403,409,422], body={"email":"smoketest_no@no.local","password":"x","name":"x"}, notes="registration should be closed in prod"),

    # ---------- Tier 1: Strategy Engineering ----------
    T("GET", "/api/strategies", "1-strategies"),
    T("GET", "/api/strategies/explorer", "1-strategies"),
    T("GET", "/api/library/list", "1-strategies"),
    T("POST", "/api/strategies/generate", "1-strategies", body={"num_strategies":1,"symbol":"EURUSD","timeframe":"H1"}, expected=[200,201,202,400,422,500]),
    T("POST", "/api/generate-strategy", "1-strategies", body={"symbol":"EURUSD","timeframe":"H1","num_strategies":1}, expected=[200,201,202,400,422,500]),
    T("POST", "/api/rank-strategies", "1-strategies", body={"strategies":[]}, expected=[200,400,422]),
    T("POST", "/api/mutate-strategy", "1-strategies", body={"strategy_hash":"nonexistent"}, expected=[200,400,404,422,500]),
    T("POST", "/api/optimize-strategy", "1-strategies", body={"strategy_hash":"nonexistent"}, expected=[200,400,404,422,500]),
    T("POST", "/api/validate-strategy", "1-strategies", body={"strategy":{}}, expected=[200,400,422]),
    T("POST", "/api/match-strategy", "1-strategies", body={"strategy":{}}, expected=[200,400,422,500]),
    T("POST", "/api/match-challenges", "1-strategies", body={"strategy":{}}, expected=[200,400,422,500]),
    T("POST", "/api/simulate-challenge", "1-strategies", body={"strategy":{},"challenge":{}}, expected=[200,400,422,500]),
    T("POST", "/api/profile-strategy", "1-strategies", body={"strategy":{}}, expected=[200,400,422,500]),
    T("POST", "/api/prop-analysis", "1-strategies", body={"strategy":{}}, expected=[200,400,404,422,500]),
    T("POST", "/api/run-backtest", "1-strategies", body={"strategy":{},"symbol":"EURUSD","timeframe":"H1"}, expected=[200,202,400,404,422,500]),
    T("POST", "/api/save-strategy", "1-strategies", body={"name":"smoketest_20260123_probe","symbol":"EURUSD","timeframe":"H1","logic":{"note":"smoke-test-safe"}}, expected=[200,201,400,422,500], notes="creates test-tagged strategy for persistence check"),

    # ---------- Tier 2: Portfolio ----------
    T("GET", "/api/portfolio/status", "2-portfolio"),
    T("GET", "/api/portfolio/health", "2-portfolio"),
    T("POST", "/api/portfolio/promotion-candidates", "2-portfolio", body={}, expected=[200,400,422]),
    T("POST", "/api/portfolio/retirement-candidates", "2-portfolio", body={}, expected=[200,400,422]),
    T("POST", "/api/portfolio-analyze", "2-portfolio", body={"strategies":[]}, expected=[200,400,422,500]),
    T("GET", "/api/rebalance/config", "2-portfolio"),
    T("GET", "/api/allocation-history", "2-portfolio"),

    # ---------- Tier 3: Dashboard ----------
    T("GET", "/api/dashboard/summary", "3-dashboard"),
    T("GET", "/api/dashboard/datasets", "3-dashboard"),
    T("GET", "/api/dashboard/portfolios/list", "3-dashboard"),

    # ---------- Tier 4: Learning ----------
    T("GET", "/api/learning/config", "4-learning"),
    T("GET", "/api/learning/metrics", "4-learning"),
    T("GET", "/api/learning/events", "4-learning"),
    T("GET", "/api/learning/runs", "4-learning"),
    T("GET", "/api/learning/cycles", "4-learning"),
    T("GET", "/api/learning/continuous/status", "4-learning"),
    T("GET", "/api/learning/scheduler/status", "4-learning"),

    # ---------- Tier 5: Market Intelligence ----------
    T("GET", "/api/market-intelligence/config", "5-market-intel"),
    T("GET", "/api/market-intelligence/state", "5-market-intel"),
    T("GET", "/api/market-intelligence/intelligence", "5-market-intel"),
    T("GET", "/api/market-intelligence/rankings", "5-market-intel"),
    T("GET", "/api/market-intelligence/changes", "5-market-intel"),
    T("GET", "/api/market-intelligence/state/history", "5-market-intel"),
    T("GET", "/api/market-intelligence/observers/config", "5-market-intel"),

    # ---------- Tier 6: Execution Intelligence (sample 8+) ----------
    T("GET", "/api/execution/status", "6-execution"),
    T("GET", "/api/execution/config", "6-execution"),
    T("GET", "/api/execution/health", "6-execution"),
    T("GET", "/api/execution/broker/health", "6-execution"),
    T("GET", "/api/execution/broker/history", "6-execution"),
    T("GET", "/api/execution/positions", "6-execution"),
    T("GET", "/api/execution/orders", "6-execution"),
    T("GET", "/api/execution/fills", "6-execution"),
    T("GET", "/api/execution/journal", "6-execution"),
    T("GET", "/api/execution/quality", "6-execution"),
    T("GET", "/api/execution/attribution", "6-execution"),
    T("GET", "/api/execution/risk/status", "6-execution"),
    T("GET", "/api/execution/paper/status", "6-execution"),
    T("GET", "/api/execution/paper/config", "6-execution"),

    # ---------- Tier 7: Meta-Learning (OBSERVE mode) ----------
    T("GET", "/api/meta-learning/config", "7-meta-learning", notes="must show mode:observe"),
    T("GET", "/api/meta-learning/status", "7-meta-learning"),
    T("GET", "/api/meta-learning/health", "7-meta-learning"),
    T("GET", "/api/meta-learning/pending", "7-meta-learning"),
    T("GET", "/api/meta-learning/recommendations", "7-meta-learning"),
    T("GET", "/api/meta-learning/evaluations", "7-meta-learning"),
    T("GET", "/api/meta-learning/mode-history", "7-meta-learning"),
    T("GET", "/api/meta-learning/overrides", "7-meta-learning"),
    T("GET", "/api/meta-learning/applications", "7-meta-learning"),
    # approve MUST return 409 (invariant)
    T("POST", "/api/meta-learning/recommendations/smoketest/approve", "7-meta-learning", expected=[409], body={}, notes="OBSERVE mode invariant"),

    # ---------- Tier 8: Factory-Eval (OBSERVE mode) ----------
    T("GET", "/api/factory-eval/config", "8-factory-eval", notes="must show mode:observe"),
    T("GET", "/api/factory-eval/status", "8-factory-eval"),
    T("GET", "/api/factory-eval/health", "8-factory-eval"),
    T("GET", "/api/factory-eval/pending", "8-factory-eval"),
    T("GET", "/api/factory-eval/recommendations", "8-factory-eval"),
    T("GET", "/api/factory-eval/kpis", "8-factory-eval"),
    T("GET", "/api/factory-eval/insights", "8-factory-eval"),
    T("GET", "/api/factory-eval/reports", "8-factory-eval"),
    T("GET", "/api/factory-eval/mode-history", "8-factory-eval"),
    # approve MUST return 409
    T("POST", "/api/factory-eval/recommendations/smoketest/approve", "8-factory-eval", expected=[409], body={}, notes="OBSERVE mode invariant"),

    # ---------- Tier 9: Knowledge Engine (Phase-1 vs Stage-4) ----------
    T("GET", "/api/knowledge/health", "9-knowledge", notes="Phase-1 KB - must 200"),
    T("GET", "/api/knowledge/status", "9-knowledge"),
    T("GET", "/api/knowledge/lookup", "9-knowledge"),
    T("POST", "/api/knowledge/preview-prompt", "9-knowledge", body={"prompt":"test","context":{}}, expected=[200,400,422]),
    T("GET", "/api/knowledge/domains", "9-knowledge"),
    T("GET", "/api/knowledge/connectors", "9-knowledge"),
    T("GET", "/api/knowledge/statistics", "9-knowledge"),
    T("GET", "/api/knowledge/pipeline/status", "9-knowledge"),
    # Stage-4 dormant invariants
    T("GET", "/api/knowledge/ukie/health", "9-knowledge", expected=[503], stage4=True, notes="P0-F1: UKIE dormant"),
    T("POST", "/api/knowledge/query", "9-knowledge", expected=[503], stage4=True, body={"query":"x"}),
    T("GET", "/api/knowledge/metrics", "9-knowledge", expected=[503], stage4=True),
    T("GET", "/api/knowledge/promote-events", "9-knowledge", expected=[503], stage4=True),
    T("GET", "/api/knowledge/retro-score-runs", "9-knowledge", expected=[503], stage4=True),
    T("GET", "/api/knowledge/connector-events", "9-knowledge", expected=[503], stage4=True),
    T("POST", "/api/knowledge/promote/smoketest", "9-knowledge", expected=[503], stage4=True, body={}),
    T("POST", "/api/knowledge/retro-score", "9-knowledge", expected=[503], stage4=True, body={}),

    # ---------- Tier 10: Auto Factory ----------
    T("GET", "/api/auto/scheduler/status", "10-auto"),
    T("GET", "/api/auto/multi-cycle/status", "10-auto"),
    T("GET", "/api/auto/multi-cycle/history", "10-auto"),
    T("GET", "/api/auto/run-cycle/history", "10-auto"),
    T("GET", "/api/auto/mutation-runner/status", "10-auto"),
    T("GET", "/api/auto/mutation-runner/cycles", "10-auto"),
    T("GET", "/api/auto/evolution/weights", "10-auto"),
    T("POST", "/api/safety-check", "10-auto", body={"strategy":{}}, expected=[200,400,422,500]),

    # ---------- Tier 11: Governance ----------
    T("GET", "/api/governance/bi5-maturity", "11-governance"),
    T("GET", "/api/governance/ecosystem-maturity", "11-governance"),
    T("GET", "/api/governance/promotion-ledger", "11-governance"),
    T("GET", "/api/governance/replacement-candidates", "11-governance"),
    T("GET", "/api/governance/survivor-registry", "11-governance"),
    T("GET", "/api/governance/universe", "11-governance"),
    T("GET", "/api/governance/universe/preview", "11-governance"),

    # ---------- Tier 12: Orchestrator (sample 6+) ----------
    T("GET", "/api/orchestrator/status", "12-orchestrator"),
    T("GET", "/api/orchestrator/state", "12-orchestrator"),
    T("GET", "/api/orchestrator/budget", "12-orchestrator"),
    T("GET", "/api/orchestrator/heartbeat", "12-orchestrator"),
    T("GET", "/api/orchestrator/tasks", "12-orchestrator"),
    T("GET", "/api/orchestrator/decisions", "12-orchestrator"),
    T("GET", "/api/orchestrator/scheduler/status", "12-orchestrator"),
    T("GET", "/api/orchestrator/env-priority/config", "12-orchestrator"),
    T("GET", "/api/orchestrator/env-priority/stats", "12-orchestrator"),

    # ---------- Tier 13: Runner / data ----------
    T("GET", "/api/data/health", "13-data"),
    T("GET", "/api/data/health/symbols", "13-data"),
    T("GET", "/api/data/coverage", "13-data"),
    T("GET", "/api/data/maintenance/status", "13-data"),
    T("GET", "/api/data/maintenance/config", "13-data"),
    T("GET", "/api/data/maintenance/coverage", "13-data"),
    T("GET", "/api/data/maintenance/recent-runs", "13-data"),

    # ---------- Tier 14: AI Workforce (read-only) ----------
    T("GET", "/api/ai-workforce/health", "14-ai-workforce"),
    T("GET", "/api/ai-workforce/metrics", "14-ai-workforce"),
    T("GET", "/api/ai-workforce/quality", "14-ai-workforce"),
    T("GET", "/api/ai-workforce/recent", "14-ai-workforce"),
    T("GET", "/api/ai-workforce/router-config", "14-ai-workforce"),
    T("GET", "/api/ai-workforce/scores", "14-ai-workforce"),

    # ---------- Tier 15: Master Bot (sample 10 READs) ----------
    T("GET", "/api/master-bot", "15-master-bot"),
    T("GET", "/api/master-bot/candidates", "15-master-bot"),
    T("GET", "/api/master-bot/runners", "15-master-bot"),
    T("GET", "/api/master-bot/runners/fleet", "15-master-bot"),
    T("GET", "/api/master-bot/runners/route-preview", "15-master-bot"),
    T("GET", "/api/master-bot/runners/accounts/migration-status", "15-master-bot"),
    T("GET", "/api/master-bot/deployments/parity-drift", "15-master-bot"),
    T("GET", "/api/master-bot/parity/gate-status", "15-master-bot"),
    T("GET", "/api/master-bot/ranker/config", "15-master-bot"),
    T("GET", "/api/master-bot/ir/coverage", "15-master-bot"),

    # ---------- Tier 16: Factory Supervisor (sample 10 READs) ----------
    T("GET", "/api/factory-supervisor/status", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/architect/dashboard", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/architect/recommended-action", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/auto-learning/status", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/auto-learning/aggregate", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/notifications", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/notifications/stats", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/notifications/unread-count", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/events", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/events/stats", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/fleet", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/heartbeat-status", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/heartbeats", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/defer-queue", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/eligibility", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/scheduler/status", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/fag/proposals", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/submissions", "16-factory-supervisor"),
    T("GET", "/api/factory-supervisor/routing-policy", "16-factory-supervisor"),

    # ---------- Tier 17: Admin ----------
    T("GET", "/api/admin/users", "17-admin"),
    T("GET", "/api/admin/providers", "17-admin"),
    T("GET", "/api/admin/readiness", "17-admin"),
    T("GET", "/api/admin/flag", "17-admin"),
    T("GET", "/api/admin/flag/history", "17-admin"),
    T("GET", "/api/admin/bi5/symbols", "17-admin"),
    T("GET", "/api/admin/bi5/certifications", "17-admin"),
    T("GET", "/api/admin/bi5/certifications/stats", "17-admin"),
    T("GET", "/api/admin/bi5/data-certifications", "17-admin"),
    T("GET", "/api/admin/bi5/data-certifications/latest", "17-admin"),
    T("GET", "/api/admin/bi5/sweep/status", "17-admin"),
    T("GET", "/api/admin/bi5/sweep/runs", "17-admin"),
    T("GET", "/api/admin/widening-proposals", "17-admin"),

    # ---------- Tier 18: Prop Firms ----------
    T("GET", "/api/prop-firms/list", "18-prop-firms"),
    T("GET", "/api/prop-firms/intelligence/list", "18-prop-firms"),
    T("GET", "/api/prop-firms/extract-jobs", "18-prop-firms"),
    T("GET", "/api/challenge-firms", "18-prop-firms"),

    # ---------- Tier 19: Latent, Live, Monitoring, Scaling, Tuning, Mutation ----------
    # Latent
    T("GET", "/api/latent/activation-governance", "19-latent"),
    T("GET", "/api/latent/deployment-readiness", "19-latent"),
    T("GET", "/api/latent/feature-flags", "19-latent"),
    # Live
    T("GET", "/api/live/strategies", "19-live"),
    # Monitoring
    T("GET", "/api/monitoring/status", "19-monitoring"),
    T("GET", "/api/monitoring/equity-curve", "19-monitoring"),
    # Scaling
    T("GET", "/api/scaling/nodes", "19-scaling"),
    T("GET", "/api/scaling/pressure", "19-scaling"),
    T("GET", "/api/scaling/admission", "19-scaling"),
    # Tuning
    T("GET", "/api/tuning/overview", "19-tuning"),
    T("GET", "/api/tuning/settings", "19-tuning"),
    T("GET", "/api/tuning/events", "19-tuning"),
    # Mutation
    T("GET", "/api/mutation/stats", "19-mutation"),
    T("GET", "/api/mutation/catalogue", "19-mutation"),
    T("GET", "/api/mutation/events", "19-mutation"),

    # ---------- Extra: COE dead-letter (Stage-4 must be 503) ----------
    T("GET", "/api/coe/dead-letter", "9-knowledge", expected=[503,404], stage4=True, notes="Stage-4 COE γ dormant"),
]


def classify(actual_status, expected, stage4):
    """Return (verdict, reason)."""
    if stage4:
        if actual_status == 503:
            return "PASS", "Stage-4 dormant (503) as expected"
        if isinstance(expected, list) and actual_status in expected:
            return "PASS", f"stage4 accepted {actual_status}"
        # a Stage-4 endpoint returning 200 is an invariant violation
        if actual_status == 200:
            return "FAIL_INVARIANT", f"Stage-4 endpoint returned 200 (invariant violation!)"
        return "FAIL", f"Stage-4 endpoint returned {actual_status}, expected 503"

    if expected is None:
        # accept any 2xx
        if 200 <= actual_status < 300:
            return "PASS", f"HTTP {actual_status}"
        return "FAIL", f"HTTP {actual_status} (expected 2xx)"
    if isinstance(expected, int):
        expected = [expected]
    if actual_status in expected:
        return "PASS", f"HTTP {actual_status} (expected)"
    if 200 <= actual_status < 300 and any(200 <= e < 300 for e in expected):
        return "PASS", f"HTTP {actual_status} (2xx expected)"
    return "FAIL", f"HTTP {actual_status}, expected one of {expected}"


def login(session):
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                     timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    session.headers.update({"Authorization": f"Bearer {tok}"})
    return data


def run():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    login_data = login(session)
    print(f"[login] OK as {login_data.get('user',{}).get('email')} role={login_data.get('user',{}).get('role')}")

    results = []
    tier_stats = {}
    invariant_violations = []
    slow_endpoints = []

    for i, ep in enumerate(PLAN, 1):
        method = ep["method"]
        path = ep["path"]
        tier = ep["tier"]
        expected = ep["expected"]
        stage4 = ep["stage4"]
        body = ep["body"]
        skip = ep["skip"]

        entry = {
            "index": i,
            "tier": tier,
            "method": method,
            "path": path,
            "expected": expected,
            "stage4": stage4,
            "notes": ep["notes"],
        }

        if skip:
            entry.update({"verdict": "SKIP", "reason": skip, "status": None})
            results.append(entry)
            tier_stats.setdefault(tier, {"pass":0,"fail":0,"skip":0}).__setitem__("skip", tier_stats[tier]["skip"]+1)
            continue

        url = f"{BASE_URL}{path}"
        t0 = time.time()
        try:
            if method == "GET":
                r = session.get(url, timeout=TIMEOUT)
            else:
                r = session.request(method, url, json=(body or {}), timeout=TIMEOUT)
            dt = time.time() - t0
        except requests.RequestException as e:
            dt = time.time() - t0
            entry.update({
                "verdict": "FAIL",
                "status": None,
                "reason": f"RequestException: {e.__class__.__name__}: {e}",
                "elapsed_s": round(dt, 2),
                "body_snippet": "",
            })
            results.append(entry)
            tier_stats.setdefault(tier, {"pass":0,"fail":0,"skip":0})["fail"] += 1
            print(f"[{i:03d}] {method} {path} -> EXCEPTION ({e.__class__.__name__})")
            continue

        verdict, reason = classify(r.status_code, expected, stage4)
        snippet = r.text[:300] if r.text else ""
        entry.update({
            "verdict": verdict,
            "status": r.status_code,
            "reason": reason,
            "elapsed_s": round(dt, 2),
            "body_snippet": snippet,
        })
        results.append(entry)

        if dt > 2.0:
            slow_endpoints.append({"path": path, "method": method, "elapsed_s": round(dt,2)})

        if verdict.startswith("FAIL"):
            tier_stats.setdefault(tier, {"pass":0,"fail":0,"skip":0})["fail"] += 1
            if verdict == "FAIL_INVARIANT":
                invariant_violations.append({"path": path, "status": r.status_code, "reason": reason})
        else:
            tier_stats.setdefault(tier, {"pass":0,"fail":0,"skip":0})["pass"] += 1

        marker = "OK " if verdict == "PASS" else ("INV" if verdict=="FAIL_INVARIANT" else "FAIL")
        print(f"[{i:03d}] {marker} {method} {path} -> {r.status_code} ({dt:.2f}s) — {reason}")

    # ---- Persistence check: after save-strategy, look for smoketest name in library/list ----
    persistence = {"attempted": True, "found_in_library_list": False, "found_in_explorer": False}
    try:
        lib = session.get(f"{BASE_URL}/api/library/list", timeout=TIMEOUT).json()
        expl = session.get(f"{BASE_URL}/api/strategies/explorer", timeout=TIMEOUT).json()
        txt_lib = json.dumps(lib)[:20000]
        txt_expl = json.dumps(expl)[:40000]
        persistence["found_in_library_list"] = "smoketest_20260123" in txt_lib
        persistence["found_in_explorer"] = "smoketest_20260123" in txt_expl
    except Exception as e:
        persistence["error"] = str(e)

    # ---- Global counters ----
    total = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    failed = sum(1 for r in results if r["verdict"].startswith("FAIL"))
    skipped = sum(1 for r in results if r["verdict"] == "SKIP")
    invariant_count = sum(1 for r in results if r["verdict"] == "FAIL_INVARIANT")

    report = {
        "base_url": BASE_URL,
        "total_tested": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "invariant_violations_count": invariant_count,
        "invariant_violations": invariant_violations,
        "slow_endpoints_ge_2s": slow_endpoints,
        "tier_stats": tier_stats,
        "persistence_check": persistence,
        "results": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\n=== Summary ===")
    print(f"Total: {total}  Pass: {passed}  Fail: {failed}  Skip: {skipped}  InvariantViolations: {invariant_count}")
    print(f"Report: {REPORT_PATH}")
    return report


if __name__ == "__main__":
    run()
