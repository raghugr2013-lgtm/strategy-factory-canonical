"""Canonical structural fingerprint for strategies.

The legacy ``fingerprint`` on ``strategy_library`` is a per-strategy hash
that includes constants — two strategies that share entry/exit logic but
differ in a single ATR multiplier hash to different values. That's
useful for exact-dup detection but useless for family-level analytics.

``canonical_hash`` collapses constants to placeholders so that mutation
variants of the same structural idea collide onto the same key. Formal
properties:

* **Deterministic.** Same (text, parameters) input → same 16-char hex.
* **Constant-invariant.** Any run of digits (integer or decimal) in the
  ``strategy_text`` is replaced with the placeholder ``N`` before
  hashing. Two variants differing only in tuning constants collide.
* **Parameter-shape aware.** The *sorted set* of parameter keys is
  folded into the hash; two strategies whose text is identical but
  whose parameter set differs will not collide.
* **Provenance-neutral.** Lineage annotations (``DERIVED FROM:``,
  ``SOURCE:``, ``ORIGIN:``) are stripped before hashing so the same
  logical strategy imported through two different pipelines still
  collides.

The function is a pure, side-effect-free primitive suitable for use in
insert-time uniqueness checks, family aggregation, and similarity
retrieval.
"""

from __future__ import annotations

import hashlib
import re
from typing import Mapping

# Matches integers, decimals, and scientific notation.
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
# Matches provenance annotations that must be scrubbed BEFORE hashing.
_PROVENANCE_RE = re.compile(
    r"^(?:derived from|source|origin|pair|tf|mutation[_ ]run[_ ]id)\s*:.*$",
    re.IGNORECASE | re.MULTILINE,
)
_WS_RE = re.compile(r"\s+")


def normalise_strategy_text(text: str | None) -> str:
    """Return the constants-collapsed, provenance-scrubbed form of ``text``.

    Exposed publicly so callers that need a canonical *string* (for
    display / debugging) can obtain one without recomputing a hash.
    """
    if not text:
        return ""
    t = text.lower()
    t = _PROVENANCE_RE.sub("", t)
    t = _NUMBER_RE.sub("N", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def canonical_hash(
    strategy_text: str | None,
    parameters: Mapping[str, object] | None = None,
) -> str:
    """Compute the 16-hex canonical structural fingerprint.

    Only the *keys* of ``parameters`` participate — not the values —
    because parameter *values* are already collapsed inside the text
    normalisation. Including values would defeat family clustering.
    """
    norm = normalise_strategy_text(strategy_text)
    param_keys = "|".join(sorted((parameters or {}).keys()))
    payload = f"{norm}||{param_keys}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]
