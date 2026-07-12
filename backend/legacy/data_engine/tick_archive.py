"""
P0A — Tier-1 raw .bi5 filesystem cache.

The archive is the **canonical, append-only** record of every byte we
received from Dukascopy. Mongo's 1m bars (Tier 2) are derived from it
and can always be rebuilt by re-running the aggregator over the archive.

Layout (rooted at ``BI5_ARCHIVE_PATH``, default ``/app/data/bi5``):

    {archive_root}/{source}/{SYMBOL}/{YYYY}/{MM:02d}/{DD:02d}/{HH:02d}h_ticks.bi5

(Note: ``MM`` here is **1-indexed** for human readability — Dukascopy's
0-indexed URL scheme stays inside the adapter.)

Concurrency-safe writes use a ``.tmp`` file + ``os.replace`` so a crash
mid-write can never leave a half-written .bi5 on disk.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from data_engine.adapters.base import BI5HourBlob, normalize_hour_utc

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_PATH = "/app/data/bi5"


def _resolve_archive_root(override: Optional[str] = None) -> Path:
    """Resolve archive root from arg > env > default. Creates it if missing."""
    root = override or os.environ.get("BI5_ARCHIVE_PATH") or DEFAULT_ARCHIVE_PATH
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class ArchiveWriteResult:
    path: Path
    bytes_written: int
    was_new: bool          # True iff the file did not exist before this write


class BI5TickArchive:
    """Filesystem cache for raw, undecompressed BI5 hour-blobs."""

    def __init__(self, root: Optional[str] = None) -> None:
        self._root = _resolve_archive_root(root)

    @property
    def root(self) -> Path:
        return self._root

    # ----- path math -----------------------------------------------------

    def path_for(self, symbol: str, hour_utc: datetime, source: str) -> Path:
        """Return the canonical archive path for one (symbol, hour, source) blob."""
        hour_utc = normalize_hour_utc(hour_utc)
        return (
            self._root
            / source
            / symbol.upper().strip()
            / f"{hour_utc.year:04d}"
            / f"{hour_utc.month:02d}"
            / f"{hour_utc.day:02d}"
            / f"{hour_utc.hour:02d}h_ticks.bi5"
        )

    # ----- read / write --------------------------------------------------

    def has(self, symbol: str, hour_utc: datetime, source: str) -> bool:
        return self.path_for(symbol, hour_utc, source).exists()

    def read(self, symbol: str, hour_utc: datetime, source: str) -> bytes:
        """Read a cached blob. Raises ``FileNotFoundError`` if not archived."""
        return self.path_for(symbol, hour_utc, source).read_bytes()

    def symbol_size_bytes(self, symbol: str, source: str) -> int:
        """Sum of all archived .bi5 bytes for one (source, symbol) on disk.

        Used by ``IngestReport.archive_size_bytes`` so operators can track
        Tier-1 storage growth without scanning the entire archive root.
        """
        base = self._root / source / symbol.upper().strip()
        if not base.exists():
            return 0
        total = 0
        for p in base.rglob("*.bi5"):
            try:
                total += p.stat().st_size
            except OSError:  # pragma: no cover — torn file mid-rotate
                continue
        return total

    def write(self, blob: BI5HourBlob) -> ArchiveWriteResult:
        """Atomically write ``blob`` to its canonical path. Idempotent.

        If a file already exists at that path, it is overwritten only if the
        contents differ — this lets us safely re-run an ingestion without
        churning mtimes.
        """
        target = self.path_for(blob.symbol, blob.hour_utc, blob.source)
        target.parent.mkdir(parents=True, exist_ok=True)

        existed = target.exists()
        if existed:
            # Cheap byte-identity check before rewriting.
            try:
                if target.stat().st_size == len(blob.payload) and target.read_bytes() == blob.payload:
                    return ArchiveWriteResult(path=target, bytes_written=0, was_new=False)
            except OSError:  # pragma: no cover — pathological FS state
                pass

        # Atomic write: temp file in same dir → os.replace.
        fd, tmp_name = tempfile.mkstemp(
            prefix=".bi5_tmp_", suffix=".part", dir=str(target.parent)
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob.payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target)
        except Exception:
            # Best-effort cleanup of the temp file.
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:  # pragma: no cover
                pass
            raise

        logger.info(
            "bi5.archive.wrote symbol=%s hour=%s source=%s bytes=%d new=%s",
            blob.symbol, blob.hour_utc.isoformat(), blob.source,
            len(blob.payload), not existed,
        )
        return ArchiveWriteResult(
            path=target, bytes_written=len(blob.payload), was_new=not existed
        )
