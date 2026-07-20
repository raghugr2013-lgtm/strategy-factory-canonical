"""Phase 2 Stage 4 P4C.5 — Governance policy language (ADVISORY).

Rule-based promote policy on top of the Stage-3.γ hard gate
(T4+/permissive/dedup). This module is **ADVISORY ONLY**:

  * Policies produce `advisory_tag` values (e.g.
    `"auto_promote_candidate"`, `"needs_review"`) that are stamped on
    the KB row.
  * Nothing here automatically calls the promote bridge. Every promote
    remains per-item, operator-approved — Stage-3.γ invariant preserved.

Feature flag: `UKIE_GOVERNANCE_POLICY_ENABLED` (default OFF). When off,
`evaluate()` returns `[]` — no advisory tags are produced.

Policy shape (§5.5):

```
{
  "policy_id":     "v1",
  "policy_version": 1,
  "rules": [
    {
      "name":    "high-confidence auto-promote candidate",
      "all_of": [
        {"field": "trust_tier",       "op": ">=", "value": 5},
        {"field": "license_outcome",  "op": "in", "value": ["permissive"]},
        {"field": "endorsements_30d", "op": ">=", "value": 3},
        {"field": "contested",        "op": "==", "value": false}
      ],
      "action": "flag_as_auto_promote_candidate"
    }
  ]
}
```
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_governance_policy_enabled() -> bool:
    return _flag("UKIE_GOVERNANCE_POLICY_ENABLED", False)


POLICIES_COLLECTION = "promote_policies"


# ── Rule evaluation ──────────────────────────────────────────────────

_OPERATORS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in"}


def _get_field(row: Dict[str, Any], field_name: str) -> Any:
    """Read a possibly-nested field from a KB row.

    Understands:
      * `trust_tier`
      * `license_verdict.outcome` → alias `license_outcome`
      * `endorsements_30d`
      * `contested`
      * `extras.<key>` for `extras.pair`, etc.
    """
    if field_name == "license_outcome":
        lv = row.get("license_verdict") or {}
        return lv.get("outcome")
    if field_name.startswith("extras."):
        key = field_name.split(".", 1)[1]
        return (row.get("extras") or {}).get(key)
    return row.get(field_name)


def _eval_condition(row: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    field_name = str(cond.get("field") or "")
    op = str(cond.get("op") or "==").strip()
    if op not in _OPERATORS:
        return False
    target = cond.get("value")
    got = _get_field(row, field_name)
    try:
        if op == "==": return got == target
        if op == "!=": return got != target
        if op == "in":     return got in (target or [])
        if op == "not_in": return got not in (target or [])
        # Numeric comparisons — require both sides to be non-None
        if got is None or target is None:
            return False
        if op == ">":  return got >  target
        if op == ">=": return got >= target
        if op == "<":  return got <  target
        if op == "<=": return got <= target
    except TypeError:
        return False
    return False


@dataclass
class PolicyVerdict:
    kb_id:           str
    policy_id:       str
    policy_version:  int
    matched_rules:   List[str]        = field(default_factory=list)
    actions:         List[str]        = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GovernancePolicyEngine:
    """Evaluates KB rows against operator-authored policies (advisory).

    Never calls the promote bridge. Never mutates trust tier or licence.
    Its only mutation is to stamp an `advisory_tags[]` array on the KB
    row (persisted by `write_verdict()`).
    """

    def __init__(
        self,
        *,
        kb_db_getter: Optional[Callable] = None,
        policy_loader: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    ) -> None:
        self._kb_db_getter = kb_db_getter
        self._policy_loader = policy_loader

    def _kb_db(self):
        if self._kb_db_getter is not None:
            return self._kb_db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            from .constants import KNOWLEDGE_DB_NAME
            return get_db().client[KNOWLEDGE_DB_NAME]
        except Exception:                                       # pragma: no cover
            return None

    async def _load_policy(self) -> Optional[Dict[str, Any]]:
        if self._policy_loader is not None:
            return self._policy_loader()
        db = self._kb_db()
        if db is None:
            return None
        try:
            # Latest by policy_version
            cur = db[POLICIES_COLLECTION].find({}).sort("policy_version", -1).limit(1)
            async for row in cur:
                return row
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[governance_policy] load failed: %s", e)
        return None

    async def evaluate(self, row: Dict[str, Any]) -> PolicyVerdict:
        verdict = PolicyVerdict(
            kb_id=str(row.get("_id") or row.get("id") or ""),
            policy_id="", policy_version=0,
        )
        if not is_governance_policy_enabled():
            return verdict
        policy = await self._load_policy()
        if not policy:
            return verdict
        verdict.policy_id = str(policy.get("policy_id") or "")
        verdict.policy_version = int(policy.get("policy_version") or 0)
        for rule in policy.get("rules") or []:
            name = str(rule.get("name") or "")
            conds = rule.get("all_of") or []
            if not conds:
                continue
            if all(_eval_condition(row, c) for c in conds):
                verdict.matched_rules.append(name)
                action = str(rule.get("action") or "")
                if action:
                    verdict.actions.append(action)
        return verdict

    async def write_verdict(self, verdict: PolicyVerdict, *, domain: str) -> Dict[str, Any]:
        """Stamp `advisory_tags[]` + `governance_policy_id` on the KB row.

        Never mutates trust tier, licence, or hard-rail flags.
        """
        if not is_governance_policy_enabled():
            return {"status": "flag_off"}
        if not verdict.actions:
            return {"status": "no_actions"}
        db = self._kb_db()
        if db is None:
            return {"status": "error", "reason": "db_unavailable"}
        try:
            from .domains import KnowledgeDomain, storage_collection_for
            coll = storage_collection_for(KnowledgeDomain(domain.strip().lower()))
        except Exception:                                       # noqa: BLE001
            return {"status": "error", "reason": "unknown_domain"}
        try:
            await db[coll].update_one(
                {"_id": verdict.kb_id},
                {"$set": {
                    "advisory_tags":         verdict.actions,
                    "governance_policy_id":  verdict.policy_id,
                    "governance_policy_version": verdict.policy_version,
                }},
            )
        except Exception as e:                                 # noqa: BLE001
            return {"status": "error", "reason": str(e)[:120]}
        return {"status": "stamped", "kb_id": verdict.kb_id, "tags": verdict.actions}


_ENGINE: Optional[GovernancePolicyEngine] = None


def get_governance_policy_engine() -> GovernancePolicyEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = GovernancePolicyEngine()
    return _ENGINE


def _reset_for_tests() -> None:
    global _ENGINE
    _ENGINE = None
