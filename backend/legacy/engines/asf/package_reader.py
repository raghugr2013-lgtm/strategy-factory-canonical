"""ASF package reader — in-memory variant (GATE 3 scope).

The full ZIP-on-disk reader is deferred until the exporter ships
(Phase 7.3 in `ASF_BACKEND_ARCHITECTURE.md`). For the 1-vCPU migration
adapter we only need to validate an in-memory payload built by the
adapter and return a `PackageReadResult`.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from engines.asf.schema import (
    CalibrationSnapshot,
    Manifest,
    PackageReadResult,
    StrategyDoc,
)

logger = logging.getLogger(__name__)


def parse_in_memory(payload: dict) -> PackageReadResult:
    """Validate a raw dict payload (as produced by `migration_adapter`)
    against the ASF v1.0 schema and return the parsed result.

    Raises:
        pydantic.ValidationError on schema violation.
    """
    manifest = Manifest.model_validate(payload["manifest"])
    calibration = CalibrationSnapshot.model_validate(payload["calibration"])

    strategies = [
        StrategyDoc.model_validate(s) for s in payload.get("strategies", [])
    ]
    result = PackageReadResult(
        manifest=manifest,
        strategies=strategies,
        mutation_events=payload.get("mutation_events", []),
        mutation_stability=payload.get("mutation_stability", []),
        lifecycle_history=payload.get("lifecycle_history", []),
        performance_history=payload.get("performance_history", []),
        alerts=payload.get("alerts", []),
        calibration=calibration,
        extensions=payload.get("extensions", {}),
    )
    return result


def compute_package_sha256(file_hashes: list[str]) -> str:
    """Spec §10.2 — SHA-256 over the sorted concatenation of per-file
    SHA-256 hex digests separated by ``\n``. Deterministic across
    filesystem byte orderings."""
    joined = "\n".join(sorted(file_hashes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_doc_sha256(doc: dict) -> str:
    """Per-file (or per-doc) SHA-256 over canonical JSON serialisation.
    Used to populate `manifest.integrity.files[].sha256` for in-memory
    packages produced by `migration_adapter`."""
    blob = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def short_subject_fp(fingerprint: Optional[str]) -> str:
    if not fingerprint or len(fingerprint) < 8:
        return "nonefp"
    return fingerprint[:8]
