"""Phase 2 Stage 3.γ — Promote Bridge precondition checker (P2C.9 α).

Pure precondition evaluation over one UKIE-KB item. **No I/O.** Every
decision is deterministic given the (item, options, prod_dedup_id)
tuple. The writer (`promote_bridge.promote_item`) invokes this to
decide whether to compose + write the production `strategies` row.

Preconditions (all must hold — plan §2.2):

  1. Item exists and its `domain == "strategy"`.
  2. `trust_tier >= 4`  (T4 Curated or T5 Authoritative).
  3. `license_verdict.outcome ∈ {permissive, weak_copyleft}`.
  4. No production `strategies` row shares the item's `content_hash`
     — unless `override_dedup=True` (audited).

Every refusal returns a specific string reason that the router / audit
event stamps verbatim so the operator can diff refusal patterns.

Feature flag: `UKIE_PROMOTE_BRIDGE_ENABLED` (default OFF) — the router
enforces this before the checker runs. `UKIE_PROMOTE_DRY_RUN` (default
ON when set alongside `_ENABLED`) determines whether the writer commits
the composed document.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


# ── Flag helpers ─────────────────────────────────────────────────────

def _flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_promote_bridge_enabled() -> bool:
    """`UKIE_PROMOTE_BRIDGE_ENABLED` — the master switch. Default OFF."""
    return _flag("UKIE_PROMOTE_BRIDGE_ENABLED", False)


def is_promote_dry_run_default() -> bool:
    """`UKIE_PROMOTE_DRY_RUN` — default dry-run behaviour when
    `_ENABLED` is on. Default TRUE — the operator must explicitly opt
    into a real commit by setting `UKIE_PROMOTE_DRY_RUN=false` (or by
    passing `dry_run=false` on a request that overrides the default)."""
    return _flag("UKIE_PROMOTE_DRY_RUN", True)


# ── Refusal reason strings (audit signal — do not localise) ──────────

REFUSE_ITEM_NOT_FOUND    = "item_not_found"
REFUSE_ITEM_MALFORMED    = "item_malformed"
REFUSE_WRONG_DOMAIN      = "wrong_domain"
REFUSE_TRUST_TOO_LOW     = "trust_tier_too_low"
REFUSE_LICENSE_REFUSED   = "license_refused"
REFUSE_DEDUP_COLLISION   = "dedup_collision"
REFUSE_ALREADY_PROMOTED  = "already_promoted"


# ── Policy constants ─────────────────────────────────────────────────

PERMITTED_LICENSE_OUTCOMES = frozenset({"permissive", "weak_copyleft"})
MIN_TRUST_TIER = 4


# ── Data shapes ──────────────────────────────────────────────────────

@dataclass
class PromoteOptions:
    """Operator-supplied parameters for one promote attempt.

    `reason` and `requested_by` land verbatim in the promote_events
    audit row. `override_dedup=True` is a physical acknowledgement that
    the operator understands they are creating a duplicate — the flag
    is stamped on the audit row regardless of outcome.
    """
    reason:          str
    requested_by:    str
    override_dedup:  bool = False


@dataclass
class PromoteVerdict:
    """Precondition verdict for one attempted promote.

    Attributes:
        ok: True iff every precondition holds.
        refuse_reason: One of the `REFUSE_*` constants — None on `ok`.
        item_id: The KB row's `_id` (str) — populated when the item was
            found. None when `refuse_reason=item_not_found`.
        content_hash: The item's `content_hash` — populated when found.
        trust_tier: The item's trust tier — populated when found.
        license_outcome: The item's `license_verdict.outcome` — when found.
        dedup_conflict_id: The `_id` of the production `strategies` row
            that shares the content hash — populated on dedup refusal
            OR on an accepted `override_dedup=true` promote.
        override_dedup: Echoed from `PromoteOptions.override_dedup` —
            audit rows carry this bit forward.
        diagnostics: Free-form additional context; safe to serialise.
    """
    ok:                  bool
    refuse_reason:       Optional[str]
    item_id:             Optional[str]
    content_hash:        Optional[str]
    trust_tier:          Optional[int]
    license_outcome:     Optional[str]
    dedup_conflict_id:   Optional[str]         = None
    override_dedup:      bool                  = False
    diagnostics:         Dict[str, Any]        = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Pure evaluator ───────────────────────────────────────────────────

def evaluate_promote(
    item: Optional[Dict[str, Any]],
    opts: PromoteOptions,
    *,
    prod_dedup_id: Optional[str] = None,
) -> PromoteVerdict:
    """Return the precondition verdict for one promote attempt.

    Args:
        item: The UKIE-KB row (as a plain dict — the caller loaded it).
            None signals "item not found" — the checker returns the
            corresponding refusal without touching other fields.
        opts: Operator-supplied `PromoteOptions`.
        prod_dedup_id: `_id` of the production `strategies` row that
            already carries the same `content_hash`, or None. The
            caller (`promote_bridge`) queries production and passes
            the result — the checker itself is pure.

    Never raises.
    """
    if item is None:
        return PromoteVerdict(
            ok=False,
            refuse_reason=REFUSE_ITEM_NOT_FOUND,
            item_id=None,
            content_hash=None,
            trust_tier=None,
            license_outcome=None,
            override_dedup=opts.override_dedup,
        )

    # Basic shape validation — we tolerate a lot but not "no content_hash"
    item_id       = str(item.get("_id") or item.get("id") or "")
    content_hash  = str(item.get("content_hash") or "").strip()
    domain        = str(item.get("domain") or "").strip()
    trust_tier    = item.get("trust_tier")
    lv            = item.get("license_verdict") or {}
    lic_outcome   = str(lv.get("outcome") or "").strip()

    if not item_id or not content_hash:
        return PromoteVerdict(
            ok=False,
            refuse_reason=REFUSE_ITEM_MALFORMED,
            item_id=item_id or None,
            content_hash=content_hash or None,
            trust_tier=trust_tier if isinstance(trust_tier, int) else None,
            license_outcome=lic_outcome or None,
            override_dedup=opts.override_dedup,
        )

    diagnostics: Dict[str, Any] = {"domain": domain, "license_method": lv.get("method")}

    # 1. domain must be "strategy"
    if domain != "strategy":
        return PromoteVerdict(
            ok=False,
            refuse_reason=REFUSE_WRONG_DOMAIN,
            item_id=item_id,
            content_hash=content_hash,
            trust_tier=trust_tier if isinstance(trust_tier, int) else None,
            license_outcome=lic_outcome or None,
            override_dedup=opts.override_dedup,
            diagnostics=diagnostics,
        )

    # 2. trust tier ≥ 4
    tt = trust_tier if isinstance(trust_tier, int) else None
    if tt is None or tt < MIN_TRUST_TIER:
        return PromoteVerdict(
            ok=False,
            refuse_reason=REFUSE_TRUST_TOO_LOW,
            item_id=item_id,
            content_hash=content_hash,
            trust_tier=tt,
            license_outcome=lic_outcome or None,
            override_dedup=opts.override_dedup,
            diagnostics=diagnostics,
        )

    # 3. license outcome
    if lic_outcome not in PERMITTED_LICENSE_OUTCOMES:
        return PromoteVerdict(
            ok=False,
            refuse_reason=REFUSE_LICENSE_REFUSED,
            item_id=item_id,
            content_hash=content_hash,
            trust_tier=tt,
            license_outcome=lic_outcome or None,
            override_dedup=opts.override_dedup,
            diagnostics=diagnostics,
        )

    # 4. dedup — refuse only when NOT overridden
    if prod_dedup_id and not opts.override_dedup:
        return PromoteVerdict(
            ok=False,
            refuse_reason=REFUSE_DEDUP_COLLISION,
            item_id=item_id,
            content_hash=content_hash,
            trust_tier=tt,
            license_outcome=lic_outcome,
            dedup_conflict_id=str(prod_dedup_id),
            override_dedup=False,
            diagnostics=diagnostics,
        )

    return PromoteVerdict(
        ok=True,
        refuse_reason=None,
        item_id=item_id,
        content_hash=content_hash,
        trust_tier=tt,
        license_outcome=lic_outcome,
        dedup_conflict_id=str(prod_dedup_id) if (prod_dedup_id and opts.override_dedup) else None,
        override_dedup=opts.override_dedup,
        diagnostics=diagnostics,
    )
