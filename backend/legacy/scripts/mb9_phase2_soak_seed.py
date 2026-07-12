#!/usr/bin/env python3
"""MB-9 Phase 2 — Soak Canonical-Fixture Seeding Helper.

Operator-invoked utility that seeds (and un-seeds) the minimal canonical
fixture set required to make the 24-hour Phase 2 soak generate meaningful
behavioural observations. Reduces operator error during seeding; does NOT
automate the soak.

CRITICAL DISCIPLINE (Gate-D contract, mirrors mb9_phase2_soak_helper.py):

  * Operator-invoked only. Does NOTHING unless run at the CLI.
  * No scheduler. No background tasks. No autonomous loops.
  * No flag manipulation. READS the active Phase 2 flag state; NEVER writes
    to os.environ or .env files.
  * No service control. No supervisorctl, no restart, no deployment hooks.
  * No third-party network calls. Local Mongo only.
  * No production credentials. Synthetic entities only.
  * Fully reversible. --unseed deletes only rows tagged with the seed marker.

Use:

    python -m scripts.mb9_phase2_soak_seed --seed-status
    python -m scripts.mb9_phase2_soak_seed --dry-run --seed
    python -m scripts.mb9_phase2_soak_seed --seed [--include-legacy]
    python -m scripts.mb9_phase2_soak_seed --unseed [--include-legacy]

Exit codes:

    0   success (including idempotent no-ops)
    1   partial failure (some rows seeded/unseeded, others failed)
    2   invalid invocation or missing prerequisites
    3   refused — flag set or marker collision needs operator review
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
RECEIPTS_DIR = ROOT / "_soak_seed_receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)

# Make 'engines' importable when invoked as a module.
sys.path.insert(0, str(ROOT.parent))

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT.parent / ".env")
except ImportError:  # pragma: no cover
    pass


SEED_MARKER = "mb9_phase2_soak_seed"
SEED_ACTOR = "soak_seed_script"

PHASE2_FLAGS = (
    "RUNNER_AFFINITY_POLICY",
    "RUNNER_TOKEN_GRACE_SEC",
    "RUNNER_AUTO_ROTATE",
    "RUNNER_PARITY_DRIFT_WINDOW_DAYS",
    "RUNNER_MULTI_ACCOUNT_ENABLED",
    "RUNNER_ROTATE_INTERVAL_SEC",
    "RUNNER_AUTO_ROUTE_AT_REGISTER",
)

PHASE2_BEHAVIOUR_FLAGS = (
    "RUNNER_MULTI_ACCOUNT_ENABLED",
    "RUNNER_AUTO_ROTATE",
    "RUNNER_AUTO_ROUTE_AT_REGISTER",
)

RUNNERS_PLAN: List[Dict[str, Any]] = [
    {
        "name":              "soak_seed_runner_eurusd_h1h4",
        "pair_filters":      ["EURUSD"],
        "timeframe_filters": ["H1", "H4"],
        "notes":             "S-1.a · seeded for Phase 2 soak",
    },
    {
        "name":              "soak_seed_runner_eurusd_gbpusd_h1",
        "pair_filters":      ["EURUSD", "GBPUSD"],
        "timeframe_filters": ["H1"],
        "notes":             "S-1.b · seeded for Phase 2 soak (overlapping pair·TF with S-1.a)",
    },
    {
        "name":              "soak_seed_runner_usdjpy_m30h1",
        "pair_filters":      ["USDJPY"],
        "timeframe_filters": ["M30", "H1"],
        "notes":             "S-1.c · seeded for Phase 2 soak (disjoint pair·TF)",
    },
]

# Accounts attach to the first runner only (S-1.a) → exercises multi-account fan-out.
ACCOUNTS_PLAN: List[Dict[str, Any]] = [
    {"runner_index": 0, "account_id": "soak-broker-1", "broker": "ctrader",
     "notes": "S-2.a · base currency USD"},
    {"runner_index": 0, "account_id": "soak-broker-2", "broker": "ctrader",
     "notes": "S-2.b · base currency EUR"},
]

# S-5 deployments — one per disjoint pair-TF, exercises sticky_pair_tf routing.
DEPLOYMENTS_PLAN: List[Dict[str, Any]] = [
    {"pair": "EURUSD", "tf": "H1", "tag": "soak_seed_deploy_eurusd_h1"},
    {"pair": "USDJPY", "tf": "H1", "tag": "soak_seed_deploy_usdjpy_h1"},
]


# ── helpers ─────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_db():
    from engines.db import get_db
    return get_db()


def _phase2_behaviour_flag_set() -> List[str]:
    """Return the names of any Phase 2 behaviour flag currently truthy
    in os.environ. Read-only."""
    truthy = ("1", "true", "yes", "on")
    out = []
    for k in PHASE2_BEHAVIOUR_FLAGS:
        v = (os.environ.get(k) or "").strip().lower()
        if v in truthy:
            out.append(f"{k}={os.environ.get(k)!r}")
    return out


def _stdout_is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _write_receipt(receipt: Dict[str, Any], prefix: str = "seed") -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RECEIPTS_DIR / f"{prefix}_{ts}.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True))
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception:  # pragma: no cover
        pass
    return path


# ── status / queries ───────────────────────────────────────────────

async def _query_seeded() -> Dict[str, Any]:
    """Return the current count + sample of every seeded entity."""
    db = _get_db()
    f = {"seed_marker": SEED_MARKER}
    runners = await db["master_bot_runners"].find(
        f, {"_id": 0, "runner_id": 1, "name": 1, "pair_filters": 1,
            "timeframe_filters": 1}
    ).to_list(None)
    accounts = await db["runner_accounts"].find(
        f, {"_id": 0, "runner_id": 1, "account_id": 1,
            "migration_source": 1}
    ).to_list(None)
    defs = await db["master_bot_definitions"].find(
        f, {"_id": 0, "revision_id": 1, "master_bot_id": 1, "name": 1}
    ).to_list(None)
    packs = await db["master_bot_packs"].find(
        f, {"_id": 0, "pack_id": 1, "master_bot_id": 1, "filename": 1}
    ).to_list(None)
    deploys = await db["master_bot_deployments"].find(
        f, {"_id": 0, "deployment_id": 1, "pair": 1, "tf": 1,
            "assigned_runner_id": 1, "runner_id": 1}
    ).to_list(None)
    return {
        "runners":     runners,
        "accounts":    accounts,
        "definitions": defs,
        "packs":       packs,
        "deployments": deploys,
    }


def _expected_totals(include_legacy: bool) -> Dict[str, int]:
    return {
        "runners":     3,
        "accounts":    2 + (1 if include_legacy else 0),
        "definitions": 1,
        "packs":       1,
        "deployments": 2,
    }


# ── seed ───────────────────────────────────────────────────────────

async def _seed_runner(plan: Dict[str, Any]) -> Dict[str, Any]:
    from engines import runner_registry as runners
    db = _get_db()
    existing = await db["master_bot_runners"].find_one(
        {"seed_marker": SEED_MARKER, "name": plan["name"]}, {"_id": 0}
    )
    if existing:
        return {"status": "exists", "runner_id": existing["runner_id"],
                "name": plan["name"], "token": None}
    out = await runners.register_runner(
        name=plan["name"],
        platform="linux",
        hostname="soak-seed-fixture",
        pair_filters=plan["pair_filters"],
        timeframe_filters=plan["timeframe_filters"],
        notes=plan["notes"],
        actor=SEED_ACTOR,
    )
    # Stamp the seed marker.
    await db["master_bot_runners"].update_one(
        {"runner_id": out["runner_id"]},
        {"$set": {"seed_marker": SEED_MARKER}},
    )
    return {"status": "created", "runner_id": out["runner_id"],
            "name": plan["name"], "token": out["token"],
            "pair_filters": out["pair_filters"],
            "timeframe_filters": out["timeframe_filters"]}


async def _seed_account(runner_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    from engines import multi_account_envelope as mae
    db = _get_db()
    existing = await db["runner_accounts"].find_one(
        {"seed_marker": SEED_MARKER, "runner_id": runner_id,
         "account_id": plan["account_id"]}, {"_id": 0},
    )
    if existing:
        return {"status": "exists", "runner_id": runner_id,
                "account_id": plan["account_id"]}
    await mae.add_account(
        runner_id=runner_id,
        account_id=plan["account_id"],
        broker=plan["broker"],
        credentials_envelope="",
        notes=plan["notes"],
        actor=SEED_ACTOR,
    )
    await db["runner_accounts"].update_one(
        {"runner_id": runner_id, "account_id": plan["account_id"]},
        {"$set": {"seed_marker": SEED_MARKER}},
    )
    return {"status": "created", "runner_id": runner_id,
            "account_id": plan["account_id"]}


async def _seed_definition() -> Dict[str, Any]:
    """Direct-insert a minimal canonical definition row.

    We bypass engines.master_bot_definition.compile_definition because that
    function requires a real Master Bot with members and a strategy tree.
    The row shape exactly mirrors what compile_definition writes — we are
    NOT modifying the engine, only mimicking its output schema for a seeded
    synthetic fixture. seed_marker discriminator makes the row reversible.
    """
    from engines import master_bot_definition as mbd
    db = _get_db()
    await mbd.ensure_indexes()
    existing = await db[mbd.DEFINITIONS_COLL].find_one(
        {"seed_marker": SEED_MARKER}, {"_id": 0}
    )
    if existing:
        return {"status": "exists", "revision_id": existing["revision_id"],
                "master_bot_id": existing["master_bot_id"]}
    master_bot_id = uuid.uuid4().hex
    revision_id = uuid.uuid4().hex
    now = _now_iso()
    doc = {
        "revision_id":     revision_id,
        "master_bot_id":   master_bot_id,
        "rev":             1,
        "definition_hash": "sha256:" + ("0" * 64),
        "payload": {
            "synthetic":   True,
            "name":        "soak_seed_mb_v1",
            "runtime_mode": "multi_strategy",
            "members":     [],
            "ranker_doc":  None,
        },
        "compiled_at":     now,
        "compiled_by":     SEED_ACTOR,
        "name":            "soak_seed_mb_v1",
        "seed_marker":     SEED_MARKER,
    }
    await db[mbd.DEFINITIONS_COLL].insert_one(doc)
    return {"status": "created", "revision_id": revision_id,
            "master_bot_id": master_bot_id}


async def _seed_pack(master_bot_id: str, revision_id: str) -> Dict[str, Any]:
    """Direct-insert a minimal canonical pack row.

    Bypass build_pack for the same reason as definition: it requires a real
    cBot artifact + parity signoff. Shape mirrors master_bot_pack canonical
    row + seed_marker.
    """
    from engines import master_bot_pack as mbpack
    db = _get_db()
    try:
        await db[mbpack.PACKS_COLL].create_index(
            [("master_bot_id", 1), ("pack_version", 1)], unique=True
        )
    except Exception:  # pragma: no cover
        pass
    existing = await db[mbpack.PACKS_COLL].find_one(
        {"seed_marker": SEED_MARKER}, {"_id": 0}
    )
    if existing:
        return {"status": "exists", "pack_id": existing["pack_id"],
                "master_bot_id": existing["master_bot_id"]}
    pack_id = uuid.uuid4().hex
    now = _now_iso()
    doc = {
        "pack_id":        pack_id,
        "master_bot_id":  master_bot_id,
        "revision_id":    revision_id,
        "pack_version":   "v1",
        "rev":            1,
        "filename":       "soak_seed_pack_v1.cbotpack",
        "sha256":         "0" * 64,
        "size_bytes":     0,
        "synthetic":      True,
        "built_at":       now,
        "built_by":       SEED_ACTOR,
        "seed_marker":    SEED_MARKER,
    }
    await db[mbpack.PACKS_COLL].insert_one(doc)
    return {"status": "created", "pack_id": pack_id,
            "master_bot_id": master_bot_id}


async def _seed_deployment(
    master_bot_id: str,
    pack_id: str,
    revision_id: str,
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Direct-insert a minimal canonical deployment row.

    Bypass register_deployment because it asserts parity_signoff freshness
    against a real revision_id. Shape mirrors master_bot_deployment
    canonical row + seed_marker. assigned_runner_id is left null; the
    Phase 2 router-at-register will populate it when the flag is flipped
    (which is the whole point of the soak observation).
    """
    from engines import master_bot_deployment as mbd
    db = _get_db()
    existing = await db[mbd.DEPLOYMENTS_COLL].find_one(
        {"seed_marker": SEED_MARKER, "pair": plan["pair"], "tf": plan["tf"]},
        {"_id": 0},
    )
    if existing:
        return {"status": "exists",
                "deployment_id": existing["deployment_id"],
                "pair": plan["pair"], "tf": plan["tf"]}
    deployment_id = uuid.uuid4().hex
    now = _now_iso()
    doc = {
        "deployment_id":            deployment_id,
        "master_bot_id":            master_bot_id,
        "pack_id":                  pack_id,
        "revision_id":              revision_id,
        "rev":                      1,
        "filename":                 "soak_seed_pack_v1.cbotpack",
        "sha256":                   "0" * 64,
        "size_bytes":               0,
        "runner_id":                None,
        "assigned_runner_id":       None,
        "pair":                     plan["pair"],
        "tf":                       plan["tf"],
        "state":                    "registered",
        "parity_verdict":           "PASSED",
        "parity_signoff_ttl_days":  30,
        "state_transitions":        [{
            "from": None, "to": "registered",
            "at": now, "by": SEED_ACTOR,
            "reason": "soak_seed_fixture",
        }],
        "created_at":               now,
        "created_by":               SEED_ACTOR,
        "runner_ack":               None,
        "promoted_at":              None,
        "rolled_back_at":           None,
        "name":                     plan["tag"],
        "synthetic":                True,
        "seed_marker":              SEED_MARKER,
    }
    await db[mbd.DEPLOYMENTS_COLL].insert_one(doc)
    return {"status": "created", "deployment_id": deployment_id,
            "pair": plan["pair"], "tf": plan["tf"]}


async def _seed_legacy_account(runner_id: str) -> Dict[str, Any]:
    """Optional S-6 legacy bootstrap row (opt-in via --include-legacy)."""
    db = _get_db()
    existing = await db["runner_accounts"].find_one(
        {"seed_marker": SEED_MARKER,
         "migration_source": "mb9_phase2_legacy_bootstrap",
         "runner_id": runner_id}, {"_id": 0},
    )
    if existing:
        return {"status": "exists", "runner_id": runner_id,
                "account_id": existing["account_id"]}
    aid = "_legacy_single_account"
    now = _now_iso()
    doc = {
        "runner_id":                 runner_id,
        "account_id":                aid,
        "broker":                    "ctrader",
        "credentials_envelope_hash": "sha256:" + ("0" * 64),
        "active":                    True,
        "created_at":                now,
        "created_by":                SEED_ACTOR,
        "notes":                     "S-6 · legacy bootstrap row (seeded)",
        "migration_source":          "mb9_phase2_legacy_bootstrap",
        "seed_marker":               SEED_MARKER,
    }
    await db["runner_accounts"].insert_one(doc)
    return {"status": "created", "runner_id": runner_id, "account_id": aid}


async def _do_seed(include_legacy: bool, allow_piped_tokens: bool,
                   no_stdout_tokens: bool) -> Tuple[int, Dict[str, Any]]:
    """Execute the full seed. Returns (exit_code, receipt)."""
    blocked = _phase2_behaviour_flag_set()
    if blocked:
        print(f"[seed] REFUSED — Phase 2 behaviour flag(s) set: {blocked}",
              file=sys.stderr)
        print("[seed] unset the flag(s), restart backend, then retry.",
              file=sys.stderr)
        return 3, {}

    receipt: Dict[str, Any] = {
        "anchor":                  _now_iso(),
        "seed_marker":             SEED_MARKER,
        "include_legacy":          include_legacy,
        "phase1_baseline_verified": True,
        "runners":                 [],
        "accounts":                [],
        "definition":              None,
        "pack":                    None,
        "deployments":             [],
        "legacy_account":          None,
    }
    errors: List[str] = []

    try:
        # S-1 runners
        runner_records: List[Dict[str, Any]] = []
        for plan in RUNNERS_PLAN:
            r = await _seed_runner(plan)
            runner_records.append(r)
            receipt["runners"].append(r)

        # S-2 accounts on runner[0]
        runner_zero = runner_records[0]["runner_id"]
        for plan in ACCOUNTS_PLAN:
            a = await _seed_account(runner_zero, plan)
            receipt["accounts"].append(a)

        # S-3 definition
        d = await _seed_definition()
        receipt["definition"] = d

        # S-4 pack
        from engines import master_bot_definition as mbd
        # Re-read in case it was "exists"
        defin_row = await _get_db()[mbd.DEFINITIONS_COLL].find_one(
            {"seed_marker": SEED_MARKER}, {"_id": 0}
        )
        p = await _seed_pack(defin_row["master_bot_id"],
                             defin_row["revision_id"])
        receipt["pack"] = p

        # S-5 deployments
        from engines import master_bot_pack as mbpack
        pack_row = await _get_db()[mbpack.PACKS_COLL].find_one(
            {"seed_marker": SEED_MARKER}, {"_id": 0}
        )
        for plan in DEPLOYMENTS_PLAN:
            dep = await _seed_deployment(
                pack_row["master_bot_id"], pack_row["pack_id"],
                pack_row["revision_id"], plan,
            )
            receipt["deployments"].append(dep)

        # S-6 optional legacy
        if include_legacy:
            leg = await _seed_legacy_account(runner_zero)
            receipt["legacy_account"] = leg
    except Exception as exc:
        errors.append(repr(exc))

    receipt["errors"] = errors
    if errors:
        return 1, receipt

    # Receipt file (chmod 600)
    path = _write_receipt(receipt, prefix="seed")
    receipt["receipt_path"] = str(path)

    # Token surface decision.
    piped = not _stdout_is_tty()
    redact = no_stdout_tokens or (piped and not allow_piped_tokens)
    if redact:
        safe = json.loads(json.dumps(receipt))  # deep-copy
        for r in safe["runners"]:
            if r.get("token"):
                r["token"] = "<redacted — see receipt file>"
        print("[seed] one-time tokens REDACTED from stdout "
              "(non-TTY stdout or --no-stdout-tokens).")
        print(json.dumps(safe, indent=2, sort_keys=True))
    else:
        print("WARNING: tokens below are ONE-TIME and SECRET. "
              "Save the receipt and clear your terminal scrollback.")
        print(json.dumps(receipt, indent=2, sort_keys=True))
    print(f"\n[seed] receipt written to {path}")
    return 0, receipt


# ── unseed ─────────────────────────────────────────────────────────

async def _do_unseed(include_legacy: bool) -> Tuple[int, Dict[str, Any]]:
    """Delete every row tagged with the seed marker. Returns (exit, receipt)."""
    db = _get_db()
    f = {"seed_marker": SEED_MARKER}

    counts = {}
    counts["master_bot_deployments"] = (
        await db["master_bot_deployments"].delete_many(f)
    ).deleted_count
    counts["master_bot_packs"] = (
        await db["master_bot_packs"].delete_many(f)
    ).deleted_count
    counts["master_bot_definitions"] = (
        await db["master_bot_definitions"].delete_many(f)
    ).deleted_count
    counts["runner_accounts"] = (
        await db["runner_accounts"].delete_many(f)
    ).deleted_count
    counts["master_bot_runners"] = (
        await db["master_bot_runners"].delete_many(f)
    ).deleted_count

    receipt = {
        "anchor":                  _now_iso(),
        "seed_marker":             SEED_MARKER,
        "deletions":               counts,
        "include_legacy_removed":  include_legacy,
        "expected_total":          sum(_expected_totals(include_legacy).values()),
        "actual_total":            sum(counts.values()),
        "status":                  "complete",
        "warnings":                [],
    }
    path = _write_receipt(receipt, prefix="unseed")
    receipt["receipt_path"] = str(path)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print(f"\n[unseed] receipt written to {path}")
    return 0, receipt


# ── status ─────────────────────────────────────────────────────────

async def _do_status(include_legacy: bool) -> int:
    snap = await _query_seeded()
    expected = _expected_totals(include_legacy)
    actual = {
        "runners":     len(snap["runners"]),
        "accounts":    len(snap["accounts"]),
        "definitions": len(snap["definitions"]),
        "packs":       len(snap["packs"]),
        "deployments": len(snap["deployments"]),
    }
    flags_blocked = _phase2_behaviour_flag_set()
    posture = "PASS" if not flags_blocked else f"FAIL — {flags_blocked}"

    print("[seed-status]")
    print(f"  seed_marker          : {SEED_MARKER}")
    print(f"  phase1_posture       : {posture}")
    print(f"  include_legacy       : {include_legacy}")
    print("  --")
    for k in ("runners", "accounts", "definitions", "packs", "deployments"):
        print(f"  {k:<13s} ({expected[k]} expected) : "
              f"{actual[k]} / {expected[k]}")
        for row in snap[k]:
            label_keys = [x for x in ("name", "runner_id", "account_id",
                                      "pack_id", "deployment_id",
                                      "revision_id", "pair", "tf",
                                      "migration_source")
                          if row.get(x)]
            label = " ".join(f"{x}={row[x]!r}" for x in label_keys)
            print(f"    - {label}")

    legacy_rows = [a for a in snap["accounts"]
                   if a.get("migration_source") == "mb9_phase2_legacy_bootstrap"]
    print("  --")
    print(f"  legacy (S-6)         : {len(legacy_rows)} / "
          f"{1 if include_legacy else 0}")

    total_expected = sum(expected.values())
    total_actual = sum(actual.values())
    print("  --")
    print(f"  total                : {total_actual} / {total_expected}")
    return 0


# ── dry-run ────────────────────────────────────────────────────────

async def _do_dry_run(action: str, include_legacy: bool) -> int:
    expected = _expected_totals(include_legacy)
    snap = await _query_seeded()
    print(f"[dry-run:{action}] PLAN — no writes performed")
    print(f"  seed_marker          : {SEED_MARKER}")
    print(f"  include_legacy       : {include_legacy}")
    if action == "seed":
        if _phase2_behaviour_flag_set():
            print(f"  FLAG GUARD           : WOULD REFUSE — "
                  f"{_phase2_behaviour_flag_set()}")
            return 3
        plan_rows = [
            ("master_bot_runners",      3, len(snap["runners"])),
            ("runner_accounts",         expected["accounts"],
                                        len(snap["accounts"])),
            ("master_bot_definitions",  1, len(snap["definitions"])),
            ("master_bot_packs",        1, len(snap["packs"])),
            ("master_bot_deployments",  2, len(snap["deployments"])),
        ]
        print("  WOULD INSERT (idempotent — skips rows already present):")
        for coll, want, have in plan_rows:
            todo = max(0, want - have)
            print(f"    {coll:<28s} want={want} have={have} would_insert={todo}")
    elif action == "unseed":
        plan_rows = [
            ("master_bot_deployments",  len(snap["deployments"])),
            ("master_bot_packs",        len(snap["packs"])),
            ("master_bot_definitions",  len(snap["definitions"])),
            ("runner_accounts",         len(snap["accounts"])),
            ("master_bot_runners",      len(snap["runners"])),
        ]
        print(f"  WOULD DELETE (filter strictly seed_marker == "
              f"{SEED_MARKER!r}):")
        for coll, have in plan_rows:
            print(f"    {coll:<28s} would_delete={have}")
    return 0


# ── main ───────────────────────────────────────────────────────────

def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mb9_phase2_soak_seed",
        description="Operator-invoked seeding for the MB-9 Phase 2 soak.",
    )
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--seed", action="store_true",
                     help="Insert the S-1…S-5 fixture rows (idempotent).")
    grp.add_argument("--unseed", action="store_true",
                     help="Delete every row tagged with the seed marker "
                          "(idempotent).")
    grp.add_argument("--seed-status", action="store_true",
                     help="Report which seeded rows are present.")

    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan; do not write to Mongo.")
    ap.add_argument("--include-legacy", action="store_true",
                    help="Also seed/unseed the S-6 legacy account row.")
    ap.add_argument("--no-stdout-tokens", action="store_true",
                    help="Redact one-time tokens from stdout; receipt file "
                         "still records them.")
    ap.add_argument("--allow-piped-tokens", action="store_true",
                    help="Permit token emission to stdout when stdout is "
                         "not a TTY (default: redact).")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = _build_argparser()
    args = ap.parse_args(argv)

    if args.dry_run:
        if args.seed:
            return asyncio.run(_do_dry_run("seed", args.include_legacy))
        if args.unseed:
            return asyncio.run(_do_dry_run("unseed", args.include_legacy))
        if args.seed_status:
            print("[dry-run] --seed-status is already read-only.", file=sys.stderr)
            return 2

    if args.seed:
        code, _ = asyncio.run(_do_seed(
            include_legacy=args.include_legacy,
            allow_piped_tokens=args.allow_piped_tokens,
            no_stdout_tokens=args.no_stdout_tokens,
        ))
        return code
    if args.unseed:
        code, _ = asyncio.run(_do_unseed(include_legacy=args.include_legacy))
        return code
    if args.seed_status:
        return asyncio.run(_do_status(args.include_legacy))
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
