#!/usr/bin/env python3
"""Strategy Factory — VPS pre-migration schema probe (companion script).

Invoked by verify-vps-schema.sh inside a python:3.12-slim container.
This is a stand-alone Python file (NOT a shell heredoc) so f-string and
brace expansion cannot be broken by the outer shell's quoting rules.

Reads:
  env SOURCE_MONGO_URL  — source Mongo URI
  env SRC_DB            — source DB name (default: test_database)
  env SAMPLE_SIZE       — docs to sample per collection (default: 200)
  env OUT_JSON          — path to write the JSON report
  env OUT_MD            — path to write the Markdown report

Exit codes:
  0 — both checks PASS
  1 — at least one check REVIEW_REQUIRED
  2 — connection or environment error
"""
from __future__ import annotations

import collections
import json
import os
import sys
from datetime import datetime, timezone

try:
    from pymongo import MongoClient
except ImportError:
    sys.stderr.write("error: pymongo not installed inside container\n")
    sys.exit(2)


EXPECTED_MARKET_DATA_FIELDS = {
    "_id", "symbol", "timeframe", "tf", "period", "provider",
    "ts", "timestamp", "time", "t", "datetime", "as_of",
    "open", "o", "high", "h", "low", "l", "close", "c",
    "volume", "v", "tick_volume",
    "spread", "bid", "ask",
    "session", "source",
}

# Field names that indicate `mutation_stability_log` is being used as an
# evolutionary-learning / genome / lineage store rather than as pure
# operational telemetry. Any of these appearing in a sample is a red flag
# that requires operator review before excluding the collection.
LEARNING_RED_FLAG_FIELDS = {
    "generation", "genome", "chromosome", "population",
    "fitness_history", "elite", "lineage", "ancestors",
    "parent_ids", "mutation_history", "policy", "reward_curve",
}


def probe_collection(db, name: str, sample_size: int) -> tuple[int, collections.Counter]:
    """Return (docs_sampled, field_counter) for the given collection.

    Uses $sample so we don't scan huge collections.
    """
    counter: collections.Counter = collections.Counter()
    total = 0
    if name not in db.list_collection_names():
        return total, counter
    for doc in db[name].aggregate([{"$sample": {"size": sample_size}}]):
        total += 1
        for k in doc.keys():
            counter[k] += 1
    return total, counter


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# VPS Pre-migration Schema Verification")
    lines.append("")
    lines.append(f"_Generated: {report['generated_at']}_")
    lines.append("")
    lines.append(
        f"**Source DB:** `{report['source_db']}`  ·  "
        f"**Sample size:** {report['sample_size']}  ·  "
        f"**Overall verdict:** **{report['overall_verdict']}**"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    for name, check in report["checks"].items():
        lines.append(f"## `{name}` — **{check['verdict']}**")
        lines.append("")
        lines.append(f"- Docs sampled: {check['docs_sampled']}")
        lines.append(f"- Note: {check['note']}")
        if name == "market_data" and check["docs_sampled"] > 0:
            unexpected = check["unexpected_fields"]
            lines.append(f"- Unexpected fields: `{unexpected}`")
        if name == "mutation_stability_log" and check["docs_sampled"] > 0:
            flags = check["learning_red_flag_fields_detected"]
            lines.append(f"- Learning red flags: `{flags}`")
        top = sorted(check["field_counts"].items(), key=lambda kv: -kv[1])[:20]
        if top:
            lines.append("- Top fields observed:")
            for k, v in top:
                lines.append(f"    - `{k}` — {v}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    uri = os.environ.get("SOURCE_MONGO_URL")
    if not uri:
        sys.stderr.write("error: SOURCE_MONGO_URL required\n")
        return 2
    db_name = os.environ.get("SRC_DB", "test_database")
    sample_size = int(os.environ.get("SAMPLE_SIZE", "200"))
    out_json = os.environ.get("OUT_JSON", "/work/verify-vps-schema.json")
    out_md = os.environ.get("OUT_MD", "/work/verify-vps-schema.md")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"error: cannot connect to source Mongo: {e}\n")
        return 2

    db = client[db_name]

    # ── check 1: market_data field schema ────────────────────────────
    mkt_total, mkt_fields = probe_collection(db, "market_data", sample_size)
    unexpected_mkt = sorted(set(mkt_fields) - EXPECTED_MARKET_DATA_FIELDS)
    if mkt_total == 0:
        mkt_verdict = "PASS"
        mkt_note = "collection absent — nothing to exclude"
    elif unexpected_mkt:
        mkt_verdict = "REVIEW_REQUIRED"
        mkt_note = f"{len(unexpected_mkt)} unexpected field(s) detected — inspect before excluding"
    else:
        mkt_verdict = "PASS"
        mkt_note = "only reproducible OHLCV/spread/timestamp fields observed"

    # ── check 2: mutation_stability_log shape ────────────────────────
    mut_total, mut_fields = probe_collection(db, "mutation_stability_log", sample_size)
    red_flags_hit = sorted(set(mut_fields) & LEARNING_RED_FLAG_FIELDS)
    if mut_total == 0:
        mut_verdict = "PASS"
        mut_note = "collection absent — nothing to exclude"
    elif red_flags_hit:
        mut_verdict = "REVIEW_REQUIRED"
        mut_note = f"learning-store red-flag fields present: {red_flags_hit}"
    else:
        mut_verdict = "PASS"
        mut_note = "operational telemetry shape only — no evolutionary-learning fields"

    overall = "PASS" if (mkt_verdict == "PASS" and mut_verdict == "PASS") else "REVIEW_REQUIRED"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_db": db_name,
        "sample_size": sample_size,
        "checks": {
            "market_data": {
                "docs_sampled": mkt_total,
                "expected_fields": sorted(EXPECTED_MARKET_DATA_FIELDS),
                "unexpected_fields": unexpected_mkt,
                "field_counts": dict(mkt_fields),
                "verdict": mkt_verdict,
                "note": mkt_note,
            },
            "mutation_stability_log": {
                "docs_sampled": mut_total,
                "learning_red_flag_fields_detected": red_flags_hit,
                "field_counts": dict(mut_fields),
                "verdict": mut_verdict,
                "note": mut_note,
            },
        },
        "overall_verdict": overall,
    }

    with open(out_json, "w") as f:
        json.dump(report, f, indent=2, default=str)
    with open(out_md, "w") as f:
        f.write(render_markdown(report))

    print(f"market_data verdict:            {mkt_verdict}")
    print(f"mutation_stability_log verdict: {mut_verdict}")
    print(f"overall_verdict:                {overall}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
