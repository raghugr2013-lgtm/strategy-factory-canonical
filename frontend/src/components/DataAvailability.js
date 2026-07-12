import React from 'react';

/**
 * Shared UI components for the dataset availability system.
 * Consumed by both StrategyDashboard and AutoMutationRunner so the
 * pair/TF selection experience is byte-for-byte identical.
 *
 * Accepts the return value of `useDatasetAvailability(...)` plus
 * the current `pair` / `timeframe` so the banner can display them.
 *
 * `testIdPrefix` lets each consumer namespace its test-ids (default
 * "data-availability" — used by StrategyDashboard). AutoMutationRunner
 * passes "amr-data-availability" so we don't clash when both surfaces
 * are on the same page.
 */
export function DataAvailabilityBanner({
  pair,
  timeframe,
  dataStatus,
  currentDataset,
  downloading,
  onLoadData,
  testIdPrefix = 'data-availability',
  className = '',
}) {
  const levelCls =
    dataStatus.level === 'ok'
      ? 'border-emerald-700/40 bg-emerald-950/20 text-emerald-300'
      : dataStatus.level === 'insufficient'
      ? 'border-amber-700/40 bg-amber-950/20 text-amber-300'
      : dataStatus.level === 'missing'
      ? 'border-red-700/40 bg-red-950/20 text-red-300'
      : 'border-zinc-700/40 bg-zinc-900/40 text-zinc-400';

  const levelLabel =
    dataStatus.level === 'ok'
      ? '✓ Data ready'
      : dataStatus.level === 'insufficient'
      ? '⚠ Insufficient data'
      : dataStatus.level === 'missing'
      ? '✕ Missing data'
      : '…';

  const sufficientTFs = (currentDataset?.timeframes || [])
    .filter((t) => t.sufficient)
    .map((t) => t.tf)
    .join(', ') || '—';

  const canLoad = dataStatus.level !== 'ok' && dataStatus.level !== 'unknown';

  return (
    <div
      data-testid={testIdPrefix}
      className={`flex items-center gap-2 text-[10px] font-mono px-2.5 py-1.5 rounded border ${levelCls} ${className}`}
    >
      <span className="font-semibold uppercase tracking-[0.14em]">{levelLabel}</span>
      <span data-testid={`${testIdPrefix}-label`} className="text-zinc-400">
        {pair}/{timeframe} · {dataStatus.label}
      </span>
      {currentDataset && currentDataset.timeframes.length > 0 && (
        <span className="ml-auto text-zinc-500">
          available TFs:{' '}
          <span data-testid={`${testIdPrefix}-tfs`} className="text-zinc-300">
            {sufficientTFs}
          </span>
        </span>
      )}
      {canLoad && typeof onLoadData === 'function' && (
        <button
          data-testid={`${testIdPrefix}-load-btn`}
          type="button"
          onClick={onLoadData}
          disabled={downloading}
          title={`Fetch the last 2 years of ${pair}/${timeframe} from Dukascopy and store in MongoDB`}
          className={`${
            currentDataset && currentDataset.timeframes.length > 0 ? '' : 'ml-auto'
          } inline-flex items-center gap-1 px-2 py-1 text-[10px] font-mono uppercase tracking-wider rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
            downloading
              ? 'bg-zinc-800 text-zinc-300 border border-zinc-700'
              : 'bg-cyan-900/40 hover:bg-cyan-800/50 text-cyan-200 border border-cyan-700/60 hover:border-cyan-500'
          }`}
        >
          {downloading ? `Loading ${pair}/${timeframe}…` : 'Load Data'}
        </button>
      )}
    </div>
  );
}


/**
 * Success/failure banner shown after a Load Data call. Emerald on
 * success with inserted/downloaded counts; amber on failure with a
 * manual fallback command + Copy-to-clipboard button.
 */
export function DataLoadStatus({
  result,
  error,
  pair,
  timeframe,
  onDismiss,
  testIdPrefix = 'data-load',
}) {
  if (!result && !error) return null;

  const cmd = `python -m data_engine.dukascopy_downloader --symbol ${pair} --timeframe ${String(timeframe || '').toLowerCase()}`;

  const copyCommand = async () => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(cmd);
      }
    } catch {
      /* Clipboard blocked — the visible <code> line is still selectable. */
    }
  };

  if (error) {
    return (
      <div
        data-testid={`${testIdPrefix}-status`}
        className="mt-2 rounded border border-amber-700/40 bg-amber-950/20 px-2.5 py-2 space-y-1.5"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="text-[10px] font-mono text-amber-300">
            <span className="font-semibold uppercase tracking-[0.14em]">Load failed</span>
            <span className="ml-2 text-amber-200/90" data-testid={`${testIdPrefix}-error`}>
              {error}
            </span>
          </div>
          <button
            data-testid={`${testIdPrefix}-dismiss`}
            onClick={onDismiss}
            className="text-[10px] font-mono text-zinc-400 hover:text-zinc-200"
          >
            Dismiss
          </button>
        </div>
        <div className="text-[10px] font-mono text-zinc-400">
          Manual fallback — run from terminal:
        </div>
        <div className="flex items-center gap-1.5">
          <code
            data-testid={`${testIdPrefix}-fallback-cmd`}
            className="flex-1 text-[10px] font-mono text-zinc-200 bg-zinc-900 border border-zinc-800 rounded px-2 py-1 overflow-x-auto whitespace-nowrap"
          >
            {cmd}
          </code>
          <button
            data-testid={`${testIdPrefix}-copy-cmd`}
            type="button"
            onClick={copyCommand}
            className="text-[10px] font-mono px-2 py-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 hover:border-zinc-700 rounded transition-colors"
          >
            Copy
          </button>
        </div>
      </div>
    );
  }

  const inserted = result?.rows_inserted ?? 0;
  const downloaded = result?.rows_downloaded ?? 0;
  const message = result?.message || `Fetched ${downloaded} rows · inserted ${inserted}`;

  return (
    <div
      data-testid={`${testIdPrefix}-status`}
      className="mt-2 rounded border border-emerald-700/40 bg-emerald-950/20 px-2.5 py-1.5 flex items-center justify-between gap-2"
    >
      <div className="text-[10px] font-mono text-emerald-300">
        <span className="font-semibold uppercase tracking-[0.14em]">✓ Load complete</span>
        <span className="ml-2 text-emerald-200/90" data-testid={`${testIdPrefix}-message`}>
          {pair}/{timeframe} · {message}
        </span>
      </div>
      <button
        data-testid={`${testIdPrefix}-dismiss`}
        onClick={onDismiss}
        className="text-[10px] font-mono text-zinc-400 hover:text-zinc-200"
      >
        Dismiss
      </button>
    </div>
  );
}


/**
 * Helper: render <option>s for the pair dropdown using the
 * hook's datasets + availablePairs, mirroring the exact labelling
 * StrategyDashboard uses so the UX is consistent.
 */
export function PairOptions({ datasets, availablePairs }) {
  return availablePairs.map((p) => {
    const d = (datasets?.pairs || []).find((x) => x.pair === p);
    const hasData = !!d && d.has_sufficient_data;
    const label = d ? (hasData ? p : `${p} (no data)`) : p;
    return <option key={p} value={p}>{label}</option>;
  });
}


/**
 * Helper: render <option>s for the timeframe dropdown restricted to
 * the current pair's DB entries + master list.
 */
export function TimeframeOptions({ currentDataset, availableTFs }) {
  return availableTFs.map((t) => {
    const tfInfo = (currentDataset?.timeframes || []).find((x) => x.tf === t);
    const label = tfInfo
      ? (tfInfo.sufficient ? `${t} (${tfInfo.candles})` : `${t} · ${tfInfo.candles} (low)`)
      : t;
    return <option key={t} value={t}>{label}</option>;
  });
}
