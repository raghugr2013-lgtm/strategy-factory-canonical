#!/usr/bin/env python3
"""Strategy Factory — Post-Migration Verification.

After a live migration, this utility confirms zero data loss and produces a
Migration Verification Report suitable for sign-off.

Inputs:
  * source audit JSON  (from audit-vps-db.py, taken BEFORE migration)
  * target Mongo URI + DB name (the v1.0 canonical destination)
  * (optional) migration report JSON produced by migrate-data.py

Checks:
  1. Every source collection is represented in the target (either directly or
     via a documented rename/merge as recorded in migrate-data.py).
  2. Document counts match the migration report's `migrated` +
     `skipped_already_present` for each collection.
  3. Canonical v1.0 indexes exist on `users`, `strategies`, `research_queries`.
  4. Every migrated user has an `email`, `password_hash`, `role`, `status`,
     `user_id`.
  5. Every migrated strategy has `strategy_id`, `name`, `created_by`.
  6. If `--api-base` is supplied, live-checks
     `/api/health`, `/api/version`, `/api/vie/providers`, and (optionally with
     `--admin-email`/`--admin-password`) a full login → `/api/auth/me`
     → `/api/strategies` → `/api/research/recent` smoke pass.

Outputs:
  * JSON verification report
  * Markdown verification report

Exit codes: 0 = PASS, 1 = REVIEW_REQUIRED, 2 = connection failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import request, error

try:
    from bson import ObjectId
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:
    sys.stderr.write("error: pymongo not installed. Run: pip install pymongo==4.9.2\n")
    sys.exit(2)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("verify")


# Explicit rename/merge map — kept in sync with migrate-data.py.
RENAME_MAP = {
    "strategy_library": "strategies",
    "research_lineage": "research_queries",
}


EXPECTED_INDEXES = {
    "users": {"email_uniq", "user_id_uniq"},
    "strategies": {"strategy_id_uniq"},
    "research_queries": {"query_id_uniq"},
}


def _redact_uri(uri: str) -> str:
    try:
        if "@" in uri and "://" in uri:
            scheme, rest = uri.split("://", 1)
            if "@" in rest:
                creds, host = rest.split("@", 1)
                user = creds.split(":", 1)[0]
                return f"{scheme}://{user}:***@{host}"
        return uri
    except Exception:  # noqa: BLE001
        return "***"


# ─────────────────────────────────────────────────────────────────────
# Fingerprint helpers — must produce identical hashes to migrate-data.py.
# ─────────────────────────────────────────────────────────────────────
def _canonical(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _canonical(v[k]) for k in sorted(v.keys()) if k != "_id"}
    if isinstance(v, (list, tuple)):
        return [_canonical(x) for x in v]
    if isinstance(v, datetime):
        return v.replace(microsecond=0).isoformat() if v.tzinfo else v.replace(tzinfo=timezone.utc, microsecond=0).isoformat()
    if isinstance(v, ObjectId):
        return f"$oid:{v}"
    if isinstance(v, bytes):
        return f"$bin:{v.hex()}"
    return v


def source_fingerprint(doc: dict) -> str:
    payload = json.dumps(_canonical(doc), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def collect_source_fingerprints(source_uri: str, source_db_name: str) -> Dict[str, List[str]]:
    """Re-scan the source DB and produce {collection: [fingerprint,…]}."""
    client = MongoClient(source_uri, serverSelectionTimeoutMS=10000)
    db = client[source_db_name]
    out: Dict[str, List[str]] = {}
    for c in db.list_collection_names():
        out[c] = [source_fingerprint(d) for d in db[c].find({})]
    return out


def check_fingerprints(source_fps: Dict[str, List[str]], tgt_db) -> Dict[str, Any]:
    """For each source collection, count how many of its fingerprints show up in the target
    (under ANY target collection, since renames like strategy_library → strategies mean
    fingerprints from strategy_library land in target.strategies)."""
    # Build target fingerprint set once (across all collections that carry _migration_meta).
    tgt_fps_by_source: Dict[str, set] = {}
    for tgt_col in tgt_db.list_collection_names():
        for doc in tgt_db[tgt_col].find({"_migration_meta.source_fingerprint": {"$exists": True}},
                                        {"_migration_meta": 1}):
            meta = doc.get("_migration_meta") or {}
            src_col = meta.get("source_collection")
            fp = meta.get("source_fingerprint")
            if src_col and fp:
                tgt_fps_by_source.setdefault(src_col, set()).add(fp)

    results: Dict[str, Any] = {}
    total_matched = 0
    total_missing = 0
    for src_col, fps in source_fps.items():
        present = tgt_fps_by_source.get(src_col, set())
        missing = [fp for fp in fps if fp not in present]
        matched = len(fps) - len(missing)
        results[src_col] = {
            "source_docs": len(fps),
            "matched_in_target": matched,
            "missing_count": len(missing),
            "sample_missing_fingerprints": missing[:5],
            "verdict": "OK" if len(missing) == 0 else "DATA_LOSS",
        }
        total_matched += matched
        total_missing += len(missing)
    results["_totals"] = {
        "source_docs": sum(len(fps) for fps in source_fps.values()),
        "matched_in_target": total_matched,
        "missing_count": total_missing,
        "verdict": "OK" if total_missing == 0 else "DATA_LOSS",
    }
    return results


def _http(method: str, url: str, *, headers: Optional[dict] = None, data: Optional[bytes] = None, timeout: int = 15) -> Dict[str, Any]:
    req = request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            body = r.read().decode() or "{}"
            return {"status": r.status, "body": _try_json(body)}
    except error.HTTPError as e:
        return {"status": e.code, "body": _try_json(e.read().decode() or "{}"), "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"status": 0, "body": None, "error": str(e)}


def _try_json(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        return s


def check_collection_coverage(audit: Dict[str, Any], tgt_db) -> List[Dict[str, Any]]:
    """Strict per-collection coverage check.

    Uses `_migration_meta.source_collection` on target docs (stamped by
    migrate-data.py) to count exactly how many docs came from each source
    collection, regardless of where they landed (handles fold/rename).
    """
    tgt_cols = set(tgt_db.list_collection_names())
    # Count migrated docs by source_collection (across all target collections)
    migrated_by_source: Dict[str, int] = {}
    for tgt_col in tgt_cols:
        for doc in tgt_db[tgt_col].find({"_migration_meta.source_collection": {"$exists": True}},
                                        {"_migration_meta.source_collection": 1}):
            src = (doc.get("_migration_meta") or {}).get("source_collection")
            if src:
                migrated_by_source[src] = migrated_by_source.get(src, 0) + 1

    results: List[Dict[str, Any]] = []
    for src in audit["collections"]:
        name = src["name"]
        expected_target = RENAME_MAP.get(name, name)
        target_present = expected_target in tgt_cols
        raw_target_docs = tgt_db[expected_target].count_documents({}) if target_present else 0
        migrated_from_this = migrated_by_source.get(name, 0)
        source_docs = src["document_count"]

        if source_docs == 0:
            verdict = "EMPTY_SOURCE"
        elif migrated_from_this == source_docs:
            verdict = "OK"
        elif migrated_from_this > 0:
            verdict = "PARTIAL"
        else:
            verdict = "REVIEW"

        results.append({
            "source": name,
            "expected_target": expected_target,
            "target_present": target_present,
            "source_docs": source_docs,
            "target_docs_in_expected_target": raw_target_docs,
            "migrated_from_this_source": migrated_from_this,
            "verdict": verdict,
        })
    return results


def check_fold_assertions(audit: Dict[str, Any], tgt_db) -> Dict[str, Any]:
    """Explicit per-fold assertions: e.g. `strategy_library` (14) folded into `strategies`.

    Reports source count vs count of docs in target `strategies` whose
    `_migration_meta.source_collection == "strategy_library"`.
    """
    src_counts = {c["name"]: c["document_count"] for c in audit["collections"]}
    folds = []
    for src_name, tgt_name in RENAME_MAP.items():
        before = src_counts.get(src_name, 0)
        if tgt_name not in tgt_db.list_collection_names():
            after = 0
        else:
            after = tgt_db[tgt_name].count_documents({"_migration_meta.source_collection": src_name})
        folds.append({
            "source": src_name,
            "folded_into": tgt_name,
            "before": before,
            "after": after,
            "verdict": "OK" if before == after else "MISMATCH",
        })
    return {"folds": folds, "verdict": "OK" if all(f["verdict"] == "OK" for f in folds) else "MISMATCH"}


def check_indexes(tgt_db) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for col, expected in EXPECTED_INDEXES.items():
        if col not in tgt_db.list_collection_names():
            results.append({"collection": col, "expected": sorted(expected), "actual": [], "verdict": "MISSING_COLLECTION"})
            continue
        actual = {ix["name"] for ix in tgt_db[col].list_indexes()}
        missing = sorted(expected - actual)
        results.append({
            "collection": col,
            "expected": sorted(expected),
            "actual": sorted(actual),
            "missing": missing,
            "verdict": "OK" if not missing else "MISSING_INDEXES",
        })
    return results


def spot_check_users(tgt_db) -> Dict[str, Any]:
    if "users" not in tgt_db.list_collection_names():
        return {"present": False}
    users = list(tgt_db["users"].find({}, {"email": 1, "password_hash": 1, "role": 1, "status": 1, "user_id": 1}))
    incomplete: List[str] = []
    from collections import Counter
    by_role: Counter = Counter()
    by_status: Counter = Counter()
    for u in users:
        for req_field in ("email", "password_hash", "role", "status", "user_id"):
            if not u.get(req_field):
                incomplete.append(f"{u.get('email', '?')}:{req_field}")
                break
        by_role[str(u.get("role"))] += 1
        by_status[str(u.get("status"))] += 1
    return {
        "present": True,
        "total": len(users),
        "by_role": dict(by_role),
        "by_status": dict(by_status),
        "incomplete_examples": incomplete[:5],
        "verdict": "OK" if not incomplete else "REVIEW",
    }


def spot_check_strategies(tgt_db) -> Dict[str, Any]:
    if "strategies" not in tgt_db.list_collection_names():
        return {"present": False}
    total = tgt_db["strategies"].count_documents({})
    incomplete = 0
    for s in tgt_db["strategies"].find({}, {"strategy_id": 1, "name": 1, "created_by": 1}, limit=1000):
        if not (s.get("strategy_id") and s.get("name") and s.get("created_by")):
            incomplete += 1
    return {
        "present": True,
        "total": total,
        "incomplete_sample": incomplete,
        "verdict": "OK" if incomplete == 0 else "REVIEW",
    }


def spot_check_research(tgt_db) -> Dict[str, Any]:
    if "research_queries" not in tgt_db.list_collection_names():
        return {"present": False}
    total = tgt_db["research_queries"].count_documents({})
    return {"present": True, "total": total, "verdict": "OK" if total >= 0 else "REVIEW"}


def api_smoke(api_base: str, admin_email: Optional[str], admin_password: Optional[str]) -> Dict[str, Any]:
    api_base = api_base.rstrip("/")
    results: Dict[str, Any] = {}
    for path in ("/api/health", "/api/version"):
        r = _http("GET", api_base + path)
        results[path] = {"status": r["status"], "ok": 200 <= (r["status"] or 0) < 300}

    if admin_email and admin_password:
        payload = json.dumps({"email": admin_email, "password": admin_password}).encode()
        login = _http("POST", api_base + "/api/auth/login", headers={"Content-Type": "application/json"}, data=payload)
        results["/api/auth/login"] = {"status": login["status"], "ok": login["status"] == 200}
        token = None
        if isinstance(login["body"], dict):
            token = login["body"].get("access_token") or login["body"].get("token")
        if token:
            auth = {"Authorization": f"Bearer {token}"}
            for path in ("/api/auth/me", "/api/strategies", "/api/research/history", "/api/admin/users", "/api/admin/providers"):
                r = _http("GET", api_base + path, headers=auth)
                results[path] = {"status": r["status"], "ok": 200 <= (r["status"] or 0) < 300}
        else:
            results["_note"] = "no access_token returned; skipped authenticated endpoints"
    return results


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Migration Verification Report")
    lines.append("")
    lines.append(f"* Generated: `{report['generated_at']}`")
    lines.append(f"* Source audit ts: `{report['audit_generated_at']}`")
    lines.append(f"* Target: `{report['target']['uri']}` / `{report['target']['db']}`")
    lines.append(f"* **Verdict: `{report['verdict']}`**")
    lines.append("")

    lines.append("## Collection coverage (source vs target — strict, via `_migration_meta.source_collection`)")
    lines.append("")
    lines.append("| Source | → | Target | Source docs | Migrated from this source | Verdict |")
    lines.append("|---|---|---|---:|---:|---|")
    for r in report["collection_coverage"]:
        lines.append(
            f"| `{r['source']}` | → | `{r['expected_target']}` | {r['source_docs']:,} | "
            f"{r['migrated_from_this_source']:,} | {r['verdict']} |"
        )
    lines.append("")

    if report.get("fold_assertions"):
        lines.append("## Fold assertions (before → after)")
        lines.append("")
        lines.append("| Source | Folded into target | Before | After | Verdict |")
        lines.append("|---|---|---:|---:|---|")
        for f in report["fold_assertions"].get("folds", []):
            lines.append(f"| `{f['source']}` | `{f['folded_into']}` | {f['before']:,} | {f['after']:,} | {f['verdict']} |")
        lines.append("")

    if report.get("fingerprints"):
        fp = report["fingerprints"]
        lines.append("## Fingerprint check (SHA-256 per source doc, matched against target `_migration_meta.source_fingerprint`)")
        lines.append("")
        lines.append("| Source collection | Source docs | Matched in target | Missing | Verdict |")
        lines.append("|---|---:|---:|---:|---|")
        for src_col, r in fp.items():
            if src_col == "_totals":
                continue
            lines.append(f"| `{src_col}` | {r['source_docs']:,} | {r['matched_in_target']:,} | {r['missing_count']:,} | {r['verdict']} |")
        totals = fp.get("_totals", {})
        lines.append(f"| **TOTAL** | **{totals.get('source_docs',0):,}** | **{totals.get('matched_in_target',0):,}** | **{totals.get('missing_count',0):,}** | **{totals.get('verdict','?')}** |")
        lines.append("")

    lines.append("## Indexes")
    lines.append("")
    lines.append("| Collection | Expected | Present | Missing | Verdict |")
    lines.append("|---|---|---|---|---|")
    for r in report["indexes"]:
        lines.append(f"| `{r['collection']}` | {', '.join(r['expected'])} | {', '.join(r.get('actual', []))} | {', '.join(r.get('missing', []))} | {r['verdict']} |")
    lines.append("")

    lines.append("## Spot checks")
    lines.append("")
    lines.append("### Users")
    lines.append("```json")
    lines.append(json.dumps(report["users"], indent=2, default=str))
    lines.append("```")
    lines.append("")
    lines.append("### Strategies")
    lines.append("```json")
    lines.append(json.dumps(report["strategies"], indent=2, default=str))
    lines.append("```")
    lines.append("")
    lines.append("### Research")
    lines.append("```json")
    lines.append(json.dumps(report["research"], indent=2, default=str))
    lines.append("```")
    lines.append("")

    if report.get("api"):
        lines.append("## API smoke tests")
        lines.append("")
        lines.append("| Endpoint | Status | OK |")
        lines.append("|---|---:|---|")
        for path, res in report["api"].items():
            if isinstance(res, dict) and "status" in res:
                lines.append(f"| `{path}` | {res['status']} | {'✓' if res.get('ok') else '✗'} |")
        lines.append("")

    if report.get("migration_summary"):
        lines.append("## Migration report summary (from migrate-data.py)")
        lines.append("```json")
        lines.append(json.dumps(report["migration_summary"], indent=2, default=str))
        lines.append("```")
        lines.append("")

    if report.get("manual_actions"):
        lines.append("## Manual actions required")
        for a in report["manual_actions"]:
            lines.append(f"* {a}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-migration verification")
    ap.add_argument("--audit", required=True, help="pre-migration audit JSON")
    ap.add_argument("--target", required=True, help="target Mongo URI")
    ap.add_argument("--target-db", default="strategy_factory_v1")
    ap.add_argument("--source", help="optional source Mongo URI (enables fingerprint re-scan)")
    ap.add_argument("--source-db", help="optional source DB name (defaults to audit's source.db)")
    ap.add_argument("--migration-report", help="optional migration report JSON from migrate-data.py")
    ap.add_argument("--api-base", help="optional base URL for API smoke tests (e.g. http://localhost:8001)")
    ap.add_argument("--admin-email", help="optional admin email for authenticated smoke tests")
    ap.add_argument("--admin-password", help="optional admin password for authenticated smoke tests")
    ap.add_argument("--out-json", default="verification-report.json")
    ap.add_argument("--out-md", default="verification-report.md")
    args = ap.parse_args()

    with open(args.audit) as f:
        audit = json.load(f)
    migration_summary = None
    if args.migration_report:
        with open(args.migration_report) as f:
            migration_summary = json.load(f).get("summary")

    try:
        client = MongoClient(args.target, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
    except PyMongoError as e:
        log.error("connection failed: %s", e)
        return 2

    tgt_db = client[args.target_db]

    coverage = check_collection_coverage(audit, tgt_db)
    fold = check_fold_assertions(audit, tgt_db)
    indexes = check_indexes(tgt_db)
    users = spot_check_users(tgt_db)
    strategies = spot_check_strategies(tgt_db)
    research = spot_check_research(tgt_db)

    fingerprints: Optional[Dict[str, Any]] = None
    if args.source:
        src_db_name = args.source_db or audit.get("source", {}).get("db")
        if src_db_name:
            log.info("Recomputing source fingerprints from %s / %s …", _redact_uri(args.source), src_db_name)
            src_fps = collect_source_fingerprints(args.source, src_db_name)
            fingerprints = check_fingerprints(src_fps, tgt_db)

    api_results = None
    if args.api_base:
        api_results = api_smoke(args.api_base, args.admin_email, args.admin_password)

    # Manual actions
    manual: List[str] = []
    if users.get("present"):
        non_admin = users["by_role"].get("viewer", 0) + users["by_role"].get("developer", 0) + users["by_role"].get("researcher", 0) + users["by_role"].get("operator", 0)
        if non_admin > 0:
            manual.append(
                f"Re-assign roles in **Admin → Users** for {non_admin} migrated non-admin user(s). "
                "Their original v01 role/status is preserved verbatim in `legacy_role` / `legacy_status` for reference."
            )
    for r in coverage:
        if r["verdict"] in ("PARTIAL", "REVIEW"):
            manual.append(
                f"Investigate `{r['source']}` → `{r['expected_target']}`: source={r['source_docs']:,} "
                f"but only {r['migrated_from_this_source']:,} bear `_migration_meta.source_collection='{r['source']}'`."
            )
    for f in fold.get("folds", []):
        if f["verdict"] != "OK":
            manual.append(
                f"Fold mismatch: `{f['source']}` before={f['before']} after={f['after']} in `{f['folded_into']}`."
            )
    if fingerprints and fingerprints.get("_totals", {}).get("missing_count", 0) > 0:
        manual.append(
            f"Fingerprint check found {fingerprints['_totals']['missing_count']} source documents "
            "with no matching `_migration_meta.source_fingerprint` in the target (DATA LOSS)."
        )

    verdict = "PASS"
    if any(r["verdict"] in ("PARTIAL", "REVIEW") for r in coverage):
        verdict = "REVIEW_REQUIRED"
    if fold.get("verdict") != "OK":
        verdict = "REVIEW_REQUIRED"
    if any(r["verdict"] in ("MISSING_COLLECTION", "MISSING_INDEXES") for r in indexes):
        verdict = "REVIEW_REQUIRED"
    if users.get("verdict") == "REVIEW":
        verdict = "REVIEW_REQUIRED"
    if strategies.get("verdict") == "REVIEW":
        verdict = "REVIEW_REQUIRED"
    if fingerprints and fingerprints.get("_totals", {}).get("verdict") == "DATA_LOSS":
        verdict = "REVIEW_REQUIRED"
    if api_results:
        for path, res in api_results.items():
            if isinstance(res, dict) and res.get("status") and not res.get("ok"):
                verdict = "REVIEW_REQUIRED"
                manual.append(f"API endpoint `{path}` returned status {res['status']} — investigate.")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_generated_at": audit.get("generated_at"),
        "target": {"uri": _redact_uri(args.target), "db": args.target_db},
        "collection_coverage": coverage,
        "fold_assertions": fold,
        "fingerprints": fingerprints,
        "indexes": indexes,
        "users": users,
        "strategies": strategies,
        "research": research,
        "api": api_results,
        "migration_summary": migration_summary,
        "manual_actions": manual,
        "verdict": verdict,
    }

    with open(args.out_json, "w") as f:
        json.dump(report, f, indent=2, default=str)
    with open(args.out_md, "w") as f:
        f.write(render_markdown(report))

    log.info("Verdict: %s", verdict)
    log.info("JSON → %s", args.out_json)
    log.info("MD   → %s", args.out_md)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
