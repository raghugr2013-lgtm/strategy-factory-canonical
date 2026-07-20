/*
 * Fixture data — PROTOTYPE ONLY.
 * Deterministic sample rows/points used by the Primitive Gallery.
 * Backend is frozen; nothing here talks to the wire.
 */

export const priceSeries = [
  100, 101.2, 100.5, 102.1, 103.4, 102.8, 104.6, 105.9,
  106.2, 105.1, 106.8, 108.1, 107.3, 108.9, 110.4, 109.7,
  111.2, 112.6, 111.8, 113.5, 114.7, 113.9, 115.3, 116.2,
];

export const spark = [12, 15, 11, 14, 17, 16, 19, 22, 21, 24, 26, 28];

export interface ArtefactRow {
  id: string;
  kind: string;
  worker: string;
  status: string;
  age: number;   // hours
}

export const artefactRows: ArtefactRow[] = [
  { id: 'sig-8f2', kind: 'signal',   worker: 'signal-forge@v2',  status: 'active',   age: 0.3 },
  { id: 'bt-19a',  kind: 'backtest', worker: 'backtest-suite@v4',status: 'pending',  age: 1.2 },
  { id: 'ftr-77c', kind: 'feature',  worker: 'feature-mill@v6',  status: 'done',     age: 3.4 },
  { id: 'cdl-90d', kind: 'candle',   worker: 'candle-pipe@v3',   status: 'done',     age: 6.1 },
  { id: 'sig-8f3', kind: 'signal',   worker: 'signal-forge@v2',  status: 'blocked',  age: 8.7 },
  { id: 'ftr-77d', kind: 'feature',  worker: 'feature-mill@v6',  status: 'done',     age: 12.4 },
  { id: 'sig-8f4', kind: 'signal',   worker: 'signal-forge@v2',  status: 'idle',     age: 22.5 },
  { id: 'bt-19b',  kind: 'backtest', worker: 'backtest-suite@v4',status: 'done',     age: 33.9 },
];

export const longText = `
Adversarial replay engaged. The Master Bot escalated because a competing
worker (candle-pipe@v3) reported partial ingestion between 08:00Z and 09:00Z.
Impact: 4 downstream signals could not be evaluated against the shadowed
book. Recovery: candle backfill scheduled at 15:04Z; the affected signals
will be re-scored automatically. No human action required unless the
backfill remains blocked at 15:15Z, in which case Governance will surface
this decision for approval with full lineage attached.
`.trim();
