"""ASF — Strategy Archive Framework (GATE 3 build).

Permanent, schema-versioned bundle framework for strategies + lineage +
evidence + calibration. The 1-vCPU migration adapter is the first
concrete user of the framework; subsequent phases ship the exporter,
disaster-recovery, and marketplace surfaces.

See `/app/memory/ASF_PACKAGE_V1_SPEC.md` (wire-format contract) and
`/app/memory/ASF_BACKEND_ARCHITECTURE.md` (module layout) for the
authoritative specs. Both are LOCKED.
"""
from __future__ import annotations

ASF_VERSION = "1.0"
ASF_SCHEMA_VERSION = "1.0"
