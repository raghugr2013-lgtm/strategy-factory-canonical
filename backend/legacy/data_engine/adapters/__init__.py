"""
P0A — pluggable BI5 source adapters.

Today the only concrete adapter is ``dukascopy_bi5.DukascopyBI5Adapter``.
The abstract base in ``adapters.base`` exists so that future tick sources
(broker FIX feed, replay engine, etc.) can be slotted in without touching
``tick_archive`` / ``tick_aggregator`` / ``bi5_ingest_runner``.
"""

from data_engine.adapters.base import BI5Adapter, BI5HourBlob

__all__ = ["BI5Adapter", "BI5HourBlob"]
