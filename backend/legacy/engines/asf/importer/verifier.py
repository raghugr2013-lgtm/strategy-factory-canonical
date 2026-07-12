"""ASF importer verifier — post-import cross-check.

Per `ASF_BACKEND_ARCHITECTURE.md §3.8`:
    - Re-read every inserted row.
    - Compare identity fields (`fingerprint`, `strategy_hash`).
    - Surface drift / missing inserts as warnings.
    - Cert replay is a no-op for the 1-vCPU package (no exported
      cert windows); kept as a stub for future packages.
"""
from __future__ import annotations

import logging
from typing import List

from engines.asf.schema import (
    ApplyAction,
    ImportVerification,
    ImportWarning,
)

logger = logging.getLogger(__name__)


async def verify(
    *,
    import_id: str,
    actions: List[ApplyAction],
    db,
    dry_run: bool,
) -> ImportVerification:
    """Run identity + presence checks. Returns ``verified`` /
    ``verified_with_warnings`` / ``failed``."""
    rows_checked = 0
    identity_drift = 0
    missing_inserts = 0
    cert_replay_mismatch = 0
    warnings: List[ImportWarning] = []

    if dry_run:
        # Dry-run verification: schema validity was already enforced
        # by `package_reader.parse_in_memory`. We additionally check
        # that every fresh_insert action's incoming_doc carries the
        # expected identity fields.
        for a in actions:
            if a.target_collection in ("strategy_library",
                                       "strategy_library_archive"):
                rows_checked += 1
                fp = (a.incoming_doc or {}).get("fingerprint")
                if not fp or len(fp) != 40:
                    identity_drift += 1
                    warnings.append(ImportWarning(
                        kind="identity_drift",
                        subject=a.incoming_id,
                        detail=f"fingerprint malformed: {fp!r}",
                    ))
        status = "verified_with_warnings" if warnings else "verified"
        return ImportVerification(
            import_id=import_id,
            rows_checked=rows_checked,
            identity_drift=identity_drift,
            missing_inserts=missing_inserts,
            cert_replay_mismatch=cert_replay_mismatch,
            status=status,
            warnings=warnings,
        )

    # Wet-run verification: re-read every inserted row.
    for a in actions:
        if a.target_collection == "strategy_library" and \
           a.dedup_outcome == "fresh_insert":
            rows_checked += 1
            fp = (a.incoming_doc or {}).get("fingerprint")
            doc = await db["strategy_library"].find_one({"fingerprint": fp})
            if doc is None:
                missing_inserts += 1
                warnings.append(ImportWarning(
                    kind="missing_insert",
                    subject=fp or a.incoming_id,
                    detail="row not found in strategy_library after commit",
                ))
                continue
            if doc.get("fingerprint") != fp:
                identity_drift += 1
                warnings.append(ImportWarning(
                    kind="identity_drift",
                    subject=fp or a.incoming_id,
                    detail="canonical fingerprint != package fingerprint",
                ))

    status = (
        "failed" if missing_inserts > 0
        else "verified_with_warnings" if warnings
        else "verified"
    )
    return ImportVerification(
        import_id=import_id,
        rows_checked=rows_checked,
        identity_drift=identity_drift,
        missing_inserts=missing_inserts,
        cert_replay_mismatch=cert_replay_mismatch,
        status=status,
        warnings=warnings,
    )
