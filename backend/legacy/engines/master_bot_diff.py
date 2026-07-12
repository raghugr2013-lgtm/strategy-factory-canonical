"""Master Bot V1 — Revision Diff (utility).

Compares two `master_bot_definitions` rows of the same Master Bot and
returns a structured summary:

    members_added    — strategy_hash not present in `from`, present in `to`
    members_removed  — strategy_hash present in `from`, absent in `to`
    tier_moves       — strategy_hash present in both, different tier
    enable_changes   — strategy_hash present in both, different `enabled`
    snapshot_drifts  — strategy_hash present in both, snapshot diff
    ranker_changes   — weights / ranker version delta
    constraint_changes — Master Bot constraint deltas
    runtime_changes  — runtime mode / policy delta
    tier_metadata    — allocation_share / max_members / label per-tier delta
    hash_changed     — whether definition_hash differs

Read-only. No DB writes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engines import master_bot_definition as mbd


def _by_hash(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for tier in payload.get("tiers") or []:
        tk = tier.get("tier_key")
        for m in tier.get("members") or []:
            h = m.get("strategy_hash")
            if h:
                out[h] = {**m, "tier_key": tk}
    return out


def _tiers_meta(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for tier in payload.get("tiers") or []:
        tk = tier.get("tier_key")
        if tk:
            out[tk] = {
                "label":            tier.get("label"),
                "allocation_share": tier.get("allocation_share"),
                "max_members":      tier.get("max_members"),
            }
    return out


def _diff_dict(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Return {key: {from: x, to: y}} for differing keys (compared by ==)."""
    out: Dict[str, Any] = {}
    keys = set(a.keys()) | set(b.keys())
    for k in sorted(keys):
        av, bv = a.get(k), b.get(k)
        if av != bv:
            out[k] = {"from": av, "to": bv}
    return out


def _snapshot_drift(
    from_snap: Dict[str, Any], to_snap: Dict[str, Any],
) -> Dict[str, Any]:
    # Limit drift comparison to operator-meaningful fields. Volatile
    # captured_at timestamps are excluded.
    fields = (
        "pair", "timeframe", "style",
        "profit_factor", "win_rate", "pass_probability",
        "deploy_score", "candidate_score",
        "lifecycle_stage",
    )
    out: Dict[str, Any] = {}
    for f in fields:
        if (from_snap or {}).get(f) != (to_snap or {}).get(f):
            out[f] = {"from": (from_snap or {}).get(f), "to": (to_snap or {}).get(f)}
    return out


async def diff_revisions(
    master_bot_id: str,
    from_rev: Optional[int] = None,
    to_rev: Optional[int] = None,
    *,
    from_revision_id: Optional[str] = None,
    to_revision_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute the diff between two revisions.

    Resolution:
      * If `from_revision_id` / `to_revision_id` are given, they win.
      * Otherwise resolve by `(master_bot_id, rev)`.
      * `to_rev`=None → latest revision.
      * `from_rev`=None → `to_rev - 1` (previous).
    """
    if to_revision_id:
        to_doc = await mbd.get_definition(revision_id=to_revision_id)
    else:
        to_doc = await mbd.get_definition(master_bot_id=master_bot_id, rev=to_rev)
    if not to_doc:
        raise ValueError("'to' revision not found")

    if from_revision_id:
        from_doc = await mbd.get_definition(revision_id=from_revision_id)
    else:
        explicit_from = from_rev
        if explicit_from is None:
            explicit_from = int(to_doc.get("rev") or 1) - 1
        if explicit_from <= 0:
            from_doc = None
        else:
            from_doc = await mbd.get_definition(
                master_bot_id=master_bot_id, rev=explicit_from,
            )

    if not from_doc:
        # First-ever revision — return a "from-nothing" diff with full
        # to-side roster as "added".
        to_payload = to_doc.get("payload") or {}
        to_hash = _by_hash(to_payload)
        return {
            "from":            None,
            "to":              {"rev": to_doc.get("rev"),
                                "revision_id": to_doc.get("revision_id"),
                                "definition_hash": to_doc.get("definition_hash")},
            "hash_changed":    True,
            "is_initial":      True,
            "members_added":   [
                {"strategy_hash": h, "tier_key": m["tier_key"],
                 "snapshot": m.get("snapshot")} for h, m in to_hash.items()
            ],
            "members_removed": [],
            "tier_moves":      [],
            "enable_changes":  [],
            "snapshot_drifts": [],
            "ranker_changes":  _diff_dict({}, (to_payload.get("ranker") or {}).get("weights") or {}),
            "runtime_changes": _diff_dict({}, to_payload.get("runtime") or {}),
            "constraint_changes": _diff_dict({}, (to_payload.get("master_bot") or {}).get("constraints") or {}),
            "tier_metadata_changes": _diff_dict({}, _tiers_meta(to_payload)),
        }

    from_payload = from_doc.get("payload") or {}
    to_payload   = to_doc.get("payload") or {}

    from_hash = _by_hash(from_payload)
    to_hash   = _by_hash(to_payload)

    members_added: List[Dict[str, Any]] = []
    members_removed: List[Dict[str, Any]] = []
    tier_moves: List[Dict[str, Any]] = []
    enable_changes: List[Dict[str, Any]] = []
    snapshot_drifts: List[Dict[str, Any]] = []

    for h, m in to_hash.items():
        if h not in from_hash:
            members_added.append({
                "strategy_hash": h, "tier_key": m["tier_key"],
                "snapshot": m.get("snapshot"),
            })
            continue
        fm = from_hash[h]
        if fm["tier_key"] != m["tier_key"]:
            tier_moves.append({
                "strategy_hash": h,
                "from_tier": fm["tier_key"],
                "to_tier":   m["tier_key"],
            })
        if bool(fm.get("enabled")) != bool(m.get("enabled")):
            enable_changes.append({
                "strategy_hash": h,
                "from_enabled": bool(fm.get("enabled")),
                "to_enabled":   bool(m.get("enabled")),
            })
        drift = _snapshot_drift(fm.get("snapshot") or {}, m.get("snapshot") or {})
        if drift:
            snapshot_drifts.append({"strategy_hash": h, "fields": drift})

    for h, fm in from_hash.items():
        if h not in to_hash:
            members_removed.append({
                "strategy_hash": h, "tier_key": fm["tier_key"],
                "snapshot": fm.get("snapshot"),
            })

    return {
        "from": {"rev": from_doc.get("rev"),
                 "revision_id": from_doc.get("revision_id"),
                 "definition_hash": from_doc.get("definition_hash")},
        "to":   {"rev": to_doc.get("rev"),
                 "revision_id": to_doc.get("revision_id"),
                 "definition_hash": to_doc.get("definition_hash")},
        "hash_changed":   from_doc.get("definition_hash") != to_doc.get("definition_hash"),
        "is_initial":     False,
        "members_added":   members_added,
        "members_removed": members_removed,
        "tier_moves":      tier_moves,
        "enable_changes":  enable_changes,
        "snapshot_drifts": snapshot_drifts,
        "ranker_changes":  _diff_dict(
            (from_payload.get("ranker") or {}).get("weights") or {},
            (to_payload.get("ranker") or {}).get("weights") or {},
        ),
        "runtime_changes": _diff_dict(
            from_payload.get("runtime") or {}, to_payload.get("runtime") or {},
        ),
        "constraint_changes": _diff_dict(
            (from_payload.get("master_bot") or {}).get("constraints") or {},
            (to_payload.get("master_bot") or {}).get("constraints") or {},
        ),
        "tier_metadata_changes": _diff_dict(
            _tiers_meta(from_payload), _tiers_meta(to_payload),
        ),
    }
