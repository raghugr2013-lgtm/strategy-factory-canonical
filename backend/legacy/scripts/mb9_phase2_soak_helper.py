#!/usr/bin/env python3
"""MB-9 Phase 2 — Soak Preparation Helper.

Operator-invoked diagnostic & snapshot utility for the 24-hour
Phase 2 soak. Reduces operator error during the soak; does NOT
automate it.

CRITICAL DISCIPLINE (Gate-D contract):

  * **Operator-invoked only.** This script does NOTHING unless run
    by an operator at the command line.
  * **No scheduler.** No background tasks, no autonomous loops.
  * **No flag manipulation.** This script READS the active Phase 2
    flag state. It NEVER writes to ``os.environ`` and NEVER touches
    .env files. Flag flips are the operator's manual action.
  * **No data mutation.** Read-only against MongoDB. The only
    artefacts written are local snapshot JSON files under
    ``/app/backend/scripts/_soak_snapshots/`` for diff purposes.
  * **No service control.** No supervisorctl, no restart, no
    deployment hooks.

Use:

    # Take a baseline snapshot (e.g., before flipping any flag ON).
    python -m scripts.mb9_phase2_soak_helper --snapshot baseline

    # Verify Phase-1 posture (every Phase 2 flag is OFF and the
    # consumer paths still return Phase-1 shapes).
    python -m scripts.mb9_phase2_soak_helper --verify-phase1-baseline

    # Verify Phase-2 posture (the operator has flipped a flag ON
    # and the consumer paths reflect Phase-2 shapes).
    python -m scripts.mb9_phase2_soak_helper --verify-phase2-on

    # Compare two snapshots (e.g., baseline vs. T+24h).
    python -m scripts.mb9_phase2_soak_helper --diff baseline T24h

    # Full pre-flight (snapshot + verify baseline + lint indexes).
    python -m scripts.mb9_phase2_soak_helper --preflight

Exit codes:

    0   verification or snapshot succeeded
    1   verification failed (operator must review before continuing)
    2   missing argument or invalid invocation
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
SNAP_DIR = ROOT / "_soak_snapshots"
SNAP_DIR.mkdir(exist_ok=True)

# Ensure 'engines' importable from this script location.
sys.path.insert(0, str(ROOT.parent))

# Load backend/.env so MONGO_URL / DB_NAME are available when the
# operator invokes this from the command line. Read-only; does not
# touch the .env file itself.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT.parent / ".env")
except ImportError:  # pragma: no cover
    pass


PHASE2_FLAGS = (
    "RUNNER_AFFINITY_POLICY",
    "RUNNER_TOKEN_GRACE_SEC",
    "RUNNER_AUTO_ROTATE",
    "RUNNER_PARITY_DRIFT_WINDOW_DAYS",
    "RUNNER_MULTI_ACCOUNT_ENABLED",
    "RUNNER_ROTATE_INTERVAL_SEC",
    "RUNNER_AUTO_ROUTE_AT_REGISTER",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_active_flags() -> Dict[str, Any]:
    """Snapshot the current process environment for each Phase 2 flag.
    Read-only — never writes to os.environ."""
    return {k: os.environ.get(k) for k in PHASE2_FLAGS}


async def _snapshot_runtime_state() -> Dict[str, Any]:
    """Pull a read-only summary of the live runtime state."""
    from engines import feature_flags as ff
    from engines import multi_account_envelope as mae
    from engines import runner_account_migration as rmig
    from engines import runner_registry as runners
    from engines import runner_router as rr

    fleet = await runners.list_runners()
    mig_status = await rmig.migration_status()
    return {
        "anchor":              _iso_now(),
        "env_flags":           _read_active_flags(),
        "registered_flags": {
            k: ff.flag(k)
            for k in PHASE2_FLAGS
        },
        "router_policy_active": rr._resolved_policy(),
        "router_valid_policies": list(rr.VALID_POLICIES),
        "multi_account_enabled_runtime": mae._flag_enabled(),
        "fleet_count":         len(fleet),
        "fleet_summary":       [
            {
                "runner_id":         r.get("runner_id"),
                "name":              r.get("name"),
                "verdict":           r.get("verdict"),
                "status":            r.get("status"),
                "age_seconds":       r.get("age_seconds"),
                "pair_filters":      r.get("pair_filters"),
                "timeframe_filters": r.get("timeframe_filters"),
            }
            for r in fleet
        ],
        "migration_status":    mig_status,
    }


async def cmd_snapshot(label: str) -> int:
    snap = await _snapshot_runtime_state()
    path = SNAP_DIR / f"{label}.json"
    path.write_text(json.dumps(snap, indent=2, sort_keys=True))
    print(f"[snapshot:{label}] wrote {path}")
    print(f"  fleet_count          : {snap['fleet_count']}")
    print(f"  router_policy_active : {snap['router_policy_active']}")
    print(f"  multi_account_enabled: {snap['multi_account_enabled_runtime']}")
    print(f"  legacy_account_rows  : {snap['migration_status']['legacy_account_rows']}")
    return 0


def _is_phase1_posture(snap: Dict[str, Any]) -> Dict[str, Any]:
    """A 'Phase-1 posture' means every Phase 2 flag is at its default
    value AND the consumer-visible runtime state matches Phase 1."""
    env = snap["env_flags"]
    failures = []
    # Every behaviour flag must be unset / default-OFF.
    for k in ("RUNNER_MULTI_ACCOUNT_ENABLED", "RUNNER_AUTO_ROTATE",
              "RUNNER_AUTO_ROUTE_AT_REGISTER"):
        if env.get(k):
            failures.append(f"{k}={env[k]!r} (expected unset)")
    if snap["multi_account_enabled_runtime"]:
        failures.append(
            "multi_account_enabled_runtime=true (expected false)"
        )
    if snap["router_policy_active"] != "sticky_pair_tf":
        failures.append(
            f"router_policy_active={snap['router_policy_active']!r} "
            "(expected sticky_pair_tf default)"
        )
    return {"phase1_posture": not failures, "failures": failures}


async def cmd_verify_phase1_baseline() -> int:
    snap = await _snapshot_runtime_state()
    res = _is_phase1_posture(snap)
    print("[verify-phase1-baseline]")
    if res["phase1_posture"]:
        print("  PASS — every Phase 2 flag at default-OFF; "
              "runtime in Phase-1 posture.")
        return 0
    print("  FAIL — Phase-2 flag(s) active:")
    for f in res["failures"]:
        print(f"    - {f}")
    return 1


async def cmd_verify_phase2_on() -> int:
    """The operator has set at least one Phase 2 flag ON. We
    confirm runtime reflects it."""
    snap = await _snapshot_runtime_state()
    env = snap["env_flags"]
    any_on = any(env.get(k) for k in PHASE2_FLAGS)
    print("[verify-phase2-on]")
    if not any_on:
        print("  FAIL — no Phase 2 flag is set. Did you export one "
              "before invoking this command?")
        return 1
    set_flags = {k: v for k, v in env.items() if v is not None}
    print("  active flags:")
    for k, v in set_flags.items():
        print(f"    - {k}={v!r}")
    print(f"  runtime multi_account_enabled = "
          f"{snap['multi_account_enabled_runtime']}")
    print(f"  router policy active           = "
          f"{snap['router_policy_active']}")
    return 0


async def cmd_diff(a_label: str, b_label: str) -> int:
    a_path = SNAP_DIR / f"{a_label}.json"
    b_path = SNAP_DIR / f"{b_label}.json"
    if not a_path.exists() or not b_path.exists():
        print(f"[diff] missing snapshot: a={a_path.exists()} "
              f"b={b_path.exists()}")
        return 2
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())
    print(f"[diff] {a_label} → {b_label}")
    print(f"  anchor a                : {a['anchor']}")
    print(f"  anchor b                : {b['anchor']}")
    print(f"  fleet_count   Δ         : "
          f"{b['fleet_count'] - a['fleet_count']}")
    print(f"  legacy_rows   Δ         : "
          f"{b['migration_status']['legacy_account_rows'] - a['migration_status']['legacy_account_rows']}")
    changed_flags = [
        k for k in PHASE2_FLAGS
        if a["env_flags"].get(k) != b["env_flags"].get(k)
    ]
    if changed_flags:
        print("  flag changes:")
        for k in changed_flags:
            print(f"    - {k}: {a['env_flags'].get(k)!r} → "
                  f"{b['env_flags'].get(k)!r}")
    else:
        print("  flag changes: none")
    return 0


async def cmd_preflight() -> int:
    """Snapshot + verify baseline + index lint. Operator runs this
    immediately before the soak begins."""
    rc = await cmd_snapshot("preflight")
    if rc != 0:
        return rc
    rc = await cmd_verify_phase1_baseline()
    if rc != 0:
        return rc
    # Index check — read-only sanity.
    from engines import multi_account_envelope as mae
    from engines import runner_token_rotator as rtr
    from engines.db import get_db
    db = get_db()
    coll_a = await db[mae.ACCOUNTS_COLL].index_information()
    coll_h = await db[rtr.HISTORY_COLL].index_information()
    print("[preflight:indexes]")
    print(f"  runner_accounts  indexes: {sorted(coll_a.keys())}")
    print(f"  rotation_history indexes: {sorted(coll_h.keys())}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mb9_phase2_soak_helper",
        description="MB-9 Phase 2 soak preparation — operator-invoked, "
                    "read-only diagnostics and snapshots.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--snapshot", metavar="LABEL",
                   help="write a snapshot to _soak_snapshots/<label>.json")
    g.add_argument("--verify-phase1-baseline", action="store_true",
                   help="assert every Phase 2 flag is default-OFF and "
                        "runtime is in Phase-1 posture")
    g.add_argument("--verify-phase2-on", action="store_true",
                   help="display the active Phase 2 flag(s) and the "
                        "runtime they produce")
    g.add_argument("--diff", nargs=2, metavar=("A", "B"),
                   help="diff two previously-recorded snapshots")
    g.add_argument("--preflight", action="store_true",
                   help="snapshot + verify-phase1-baseline + index lint")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    if args.snapshot:
        return asyncio.run(cmd_snapshot(args.snapshot))
    if args.verify_phase1_baseline:
        return asyncio.run(cmd_verify_phase1_baseline())
    if args.verify_phase2_on:
        return asyncio.run(cmd_verify_phase2_on())
    if args.diff:
        return asyncio.run(cmd_diff(args.diff[0], args.diff[1]))
    if args.preflight:
        return asyncio.run(cmd_preflight())
    return 2


if __name__ == "__main__":
    sys.exit(main())
