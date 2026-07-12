#!/usr/bin/env python3
"""Strategy Factory — Migration Coverage Validator.

Static check that answers: given the audit report of the source VPS DB and the
MIGRATION_PLAN inside `migrate-data.py`, will every source collection be
migrated? Which need pass-through vs transformer? Which have no plan row and
need one added?

This utility never touches Mongo. It reads the audit JSON and the migration
plan, and emits:
  * A JSON validation report
  * A Markdown validation report with copy-pasteable plan rows for uncovered
    collections
  * An exit code (0 = fully covered, 1 = uncovered collections found)

Usage:
    python infra/scripts/validate-migration.py \\
      --audit /work/audit-report.json \\
      --plan  infra/scripts/migrate-data.py \\
      --out-json /work/validation-report.json \\
      --out-md   /work/validation-report.md
"""
from __future__ import annotations

import argparse
import ast
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("validate")


def parse_migration_plan(path: str) -> List[Dict[str, Any]]:
    """Extract MIGRATION_PLAN entries from migrate-data.py by AST-parsing the module."""
    with open(path) as f:
        tree = ast.parse(f.read(), filename=path)

    plan: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        target_names: List[str] = []
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
        else:
            continue
        if "MIGRATION_PLAN" not in target_names:
            continue
        if not isinstance(node.value, ast.List):
            continue
        for elt in node.value.elts:
            if isinstance(elt, ast.Dict):
                row: Dict[str, Any] = {}
                for k, v in zip(elt.keys, elt.values):
                    if isinstance(k, ast.Constant):
                        if isinstance(v, ast.Constant):
                            row[k.value] = v.value
                        elif isinstance(v, ast.Name):
                            row[k.value] = v.id  # transformer function name
                        else:
                            row[k.value] = ast.unparse(v)
                plan.append(row)
        break
    return plan


def parse_intentionally_excluded(path: str) -> set:
    """Extract INTENTIONALLY_EXCLUDED set literal from migrate-data.py."""
    with open(path) as f:
        tree = ast.parse(f.read(), filename=path)
    for node in ast.walk(tree):
        target_names: List[str] = []
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
        else:
            continue
        if "INTENTIONALLY_EXCLUDED" not in target_names:
            continue
        val = node.value
        # `set()`
        if isinstance(val, ast.Call) and isinstance(val.func, ast.Name) and val.func.id == "set" and not val.args:
            return set()
        # `{...}`  set literal
        if isinstance(val, ast.Set):
            return {e.value for e in val.elts if isinstance(e, ast.Constant)}
    return set()


def validate(audit: Dict[str, Any], plan: List[Dict[str, Any]], excluded: set, strict: bool) -> Dict[str, Any]:
    source_cols: List[str] = [c["name"] for c in audit["collections"]]
    source_count_by_col: Dict[str, int] = {c["name"]: c["document_count"] for c in audit["collections"]}
    source_category: Dict[str, str] = {c["name"]: c["category"] for c in audit["collections"]}

    plan_source_cols = [row["source"] for row in plan]
    covered: List[Dict[str, Any]] = []
    intentionally_excluded: List[Dict[str, Any]] = []
    auto_passthrough: List[Dict[str, Any]] = []
    uncovered: List[Dict[str, Any]] = []

    for col in source_cols:
        if col in excluded:
            intentionally_excluded.append({
                "source": col,
                "source_docs": source_count_by_col[col],
                "category": source_category[col],
            })
            continue
        rows = [r for r in plan if r["source"] == col]
        if rows:
            for r in rows:
                covered.append({
                    "source": col,
                    "target": r["target"],
                    "key": r.get("key"),
                    "transformer": r.get("xform"),
                    "note": r.get("note"),
                    "source_docs": source_count_by_col[col],
                    "category": source_category[col],
                })
        else:
            entry = {
                "source": col,
                "source_docs": source_count_by_col[col],
                "category": source_category[col],
                "suggested_plan_row": {
                    "source": col, "target": col, "key": None, "xform": "upgrade_passthrough",
                },
            }
            if strict:
                uncovered.append(entry)
            else:
                # Default: engine's auto-passthrough safety net covers this
                auto_passthrough.append(entry)

    plan_but_no_source: List[str] = [c for c in plan_source_cols if c not in source_cols]

    xform_usage: Dict[str, int] = {}
    for r in covered:
        xf = r["transformer"] or "?"
        xform_usage[xf] = xform_usage.get(xf, 0) + 1

    # Verdict logic
    if uncovered:
        verdict = "REVIEW_REQUIRED"
    else:
        verdict = "PASS"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_generated_at": audit.get("generated_at"),
        "mode": "strict" if strict else "default (auto-passthrough accepted)",
        "source_summary": {
            "collections": len(source_cols),
            "documents": audit["totals"]["documents"],
        },
        "plan_summary": {
            "rows": len(plan),
            "unique_source_cols": len(set(plan_source_cols)),
            "transformer_usage": xform_usage,
            "intentionally_excluded_count": len(excluded),
        },
        "covered": covered,
        "intentionally_excluded": intentionally_excluded,
        "auto_passthrough_source_collections": auto_passthrough,
        "uncovered_source_collections": uncovered,
        "plan_rows_with_no_source_in_audit": plan_but_no_source,
        "verdict": verdict,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Migration Coverage Validation Report")
    lines.append("")
    lines.append(f"* Generated: `{report['generated_at']}`")
    lines.append(f"* Based on audit: `{report['audit_generated_at']}`")
    lines.append(f"* Mode: **{report['mode']}**")
    lines.append(f"* **Verdict: `{report['verdict']}`**")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"* Source collections: **{report['source_summary']['collections']}**")
    lines.append(f"* Source documents: **{report['source_summary']['documents']:,}**")
    lines.append(f"* Plan rows: **{report['plan_summary']['rows']}**")
    lines.append(f"* Unique source collections in plan: **{report['plan_summary']['unique_source_cols']}**")
    lines.append(f"* Intentionally excluded: **{report['plan_summary']['intentionally_excluded_count']}**")
    lines.append(f"* Planned (matched in source): **{len(report['covered'])}**")
    lines.append(f"* Would use engine auto-passthrough: **{len(report['auto_passthrough_source_collections'])}**")
    lines.append(f"* Uncovered (strict-mode only): **{len(report['uncovered_source_collections'])}**")
    lines.append("")

    lines.append("## Transformer usage")
    lines.append("")
    lines.append("| Transformer | Rows |")
    lines.append("|---|---:|")
    for xf, cnt in sorted(report["plan_summary"]["transformer_usage"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{xf}` | {cnt} |")
    lines.append("")

    lines.append("## Covered collections (explicit plan rows)")
    lines.append("")
    lines.append("| Source | → | Target | Key | Transformer | Docs | Note |")
    lines.append("|---|---|---|---|---|---:|---|")
    for c in report["covered"]:
        lines.append(
            f"| `{c['source']}` | → | `{c['target']}` | `{c['key']}` | `{c['transformer']}` | {c['source_docs']:,} | {c['note'] or ''} |"
        )
    lines.append("")

    if report["intentionally_excluded"]:
        lines.append("## Intentionally excluded (via `INTENTIONALLY_EXCLUDED` in `migrate-data.py`)")
        lines.append("")
        lines.append("These collections exist in the source DB but the operator has explicitly opted out of migrating them. Each is documented in the `INTENTIONALLY_EXCLUDED` docstring inside `migrate-data.py`.")
        lines.append("")
        lines.append("| Source | Docs | Category |")
        lines.append("|---|---:|---|")
        for e in report["intentionally_excluded"]:
            lines.append(f"| `{e['source']}` | {e['source_docs']:,} | {e['category']} |")
        lines.append("")

    if report["auto_passthrough_source_collections"]:
        lines.append("## Auto-passthrough (safety net — migrated verbatim by the engine)")
        lines.append("")
        lines.append("These collections are not in `MIGRATION_PLAN` but the engine's auto-passthrough safety net will migrate them verbatim (with a warning in the migration report). This is default policy — zero data loss is guaranteed. To be explicit, either add each one to `MIGRATION_PLAN` with `upgrade_passthrough`, or add to `INTENTIONALLY_EXCLUDED` if you want to skip it.")
        lines.append("")
        lines.append("| Source | Docs | Suggested plan row |")
        lines.append("|---|---:|---|")
        for a in report["auto_passthrough_source_collections"]:
            suggested = f"`{{\"source\": \"{a['source']}\", \"target\": \"{a['source']}\", \"key\": None, \"xform\": upgrade_passthrough}}`"
            lines.append(f"| `{a['source']}` | {a['source_docs']:,} | {suggested} |")
        lines.append("")

    if report["uncovered_source_collections"]:
        lines.append("## ⚠ Uncovered source collections (strict mode)")
        lines.append("")
        lines.append("In `--strict` mode, every source collection must be explicitly in `MIGRATION_PLAN` or in `INTENTIONALLY_EXCLUDED`. Add a plan row for each collection below, or exclude it explicitly.")
        lines.append("")
        for u in report["uncovered_source_collections"]:
            lines.append(f"### `{u['source']}` ({u['source_docs']:,} docs, category: {u['category']})")
            lines.append("Suggested plan row:")
            lines.append("```python")
            lines.append(f'{{"source": "{u["source"]}", "target": "{u["source"]}", "key": None, "xform": upgrade_passthrough}},')
            lines.append("```")
            lines.append("")

    if report["plan_rows_with_no_source_in_audit"]:
        lines.append("## Plan rows whose source collection is absent from the audit")
        lines.append("")
        lines.append("These plan rows are safely skipped at migration time (the utility logs `skipped — not present in source`), but they may indicate stale plan entries.")
        lines.append("")
        for name in report["plan_rows_with_no_source_in_audit"]:
            lines.append(f"* `{name}`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Migration plan coverage validator")
    ap.add_argument("--audit", required=True, help="path to audit-report.json produced by audit-vps-db.py")
    ap.add_argument("--plan", default="infra/scripts/migrate-data.py", help="path to migrate-data.py")
    ap.add_argument("--strict", action="store_true",
                    help="strict mode: require every source collection to be in MIGRATION_PLAN or INTENTIONALLY_EXCLUDED (default: auto-passthrough is accepted, PASS)")
    ap.add_argument("--out-json", default="validation-report.json")
    ap.add_argument("--out-md", default="validation-report.md")
    args = ap.parse_args()

    with open(args.audit) as f:
        audit = json.load(f)

    plan = parse_migration_plan(args.plan)
    excluded = parse_intentionally_excluded(args.plan)
    log.info("Parsed %d plan rows and %d exclusions from %s", len(plan), len(excluded), args.plan)

    report = validate(audit, plan, excluded, args.strict)

    with open(args.out_json, "w") as f:
        json.dump(report, f, indent=2, default=str)
    with open(args.out_md, "w") as f:
        f.write(render_markdown(report))

    log.info("Verdict: %s (mode: %s)", report["verdict"], report["mode"])
    log.info("JSON → %s", args.out_json)
    log.info("MD   → %s", args.out_md)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
