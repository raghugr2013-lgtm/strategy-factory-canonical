import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchDatasets, loadMarketData } from '../services/api';
import { useMarketUniverse } from './useMarketUniverse';

// R4 — Static master lists are preserved as the *deep* fallback used
// only when both the market-universe registry AND the dataset API are
// unreachable. The primary master list now flows through
// `useMarketUniverse({ eligibility: 'ingestion' })` so newly registered
// symbols (e.g. AUDJPY) appear in the dropdown automatically — no
// frontend code change required.
//
// The exports below are intentionally retained so existing consumers
// and tests can keep importing them.
export const DATASET_MASTER_PAIRS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'US100', 'BTCUSD', 'ETHUSD',
];

export const DATASET_MASTER_TIMEFRAMES = [
  'M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1',
];

/**
 * useDatasetAvailability(pair, setPair, timeframe, setTimeframe)
 *
 * Single source of truth for dataset discovery + availability status
 * across the whole dashboard. Every consumer (StrategyDashboard,
 * AutoMutationRunner, future surfaces) uses this one hook so the
 * pair/timeframe selection UX is identical everywhere.
 *
 * Returns:
 *   availablePairs      : list of pair codes for the pair-dropdown
 *                         (DB pairs first, then master list).
 *   availableTFs        : list of TF codes for the TF-dropdown
 *                         (DB TFs for current pair first, then master
 *                         list).
 *   currentDataset      : the DB entry for the current pair, or null.
 *   tfsForPair          : list of TF codes known to have DB data.
 *   dataStatus          : { level: 'ok'|'insufficient'|'missing'|'unknown',
 *                           label, candles }
 *   isDataReady         : dataStatus.level === 'ok'
 *   minCandles          : backend minimum candle count.
 *   datasets            : raw API response (for advanced consumers).
 *   refreshDatasets     : manual refresh trigger.
 *   downloading         : boolean, true while Load Data is in flight.
 *   downloadResult      : success payload from the last Load Data call.
 *   downloadError       : error message from the last Load Data call.
 *   loadData            : () => Promise<void>   run ingestion for
 *                         (pair, timeframe), then refresh datasets.
 *   clearDownload       : () => void            reset success/error.
 *
 * Side-effect: when the current pair's currently-selected TF has no
 * data but other TFs do, auto-snaps `timeframe` to the MAX-candle
 * sufficient TF. This prevents the "pick new pair → 422" footgun.
 */
export function useDatasetAvailability(pair, setPair, timeframe, setTimeframe) {
  const [datasets, setDatasets] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadResult, setDownloadResult] = useState(null);
  const [downloadError, setDownloadError] = useState(null);

  const refreshDatasets = useCallback(async () => {
    try {
      const data = await fetchDatasets();
      setDatasets(data);
    } catch (e) {
      // Non-fatal — UI falls back to master lists.
      // eslint-disable-next-line no-console
      console.warn('Failed to load datasets:', e);
    }
  }, []);

  useEffect(() => { refreshDatasets(); }, [refreshDatasets]);

  // R4 — registry-backed ingestion pairs. `useMarketUniverse` always
  // returns a non-empty array (legacy 7-pair fallback on API failure /
  // timeout / empty registry), so dropdowns never blank out.
  const { options: registryPairs } = useMarketUniverse({ eligibility: 'ingestion' });

  const discoveredPairs = useMemo(
    () => (datasets?.pairs || []).map((p) => p.pair),
    [datasets],
  );

  const masterPairs = useMemo(() => (
    (registryPairs && registryPairs.length) ? registryPairs : DATASET_MASTER_PAIRS
  ), [registryPairs]);

  const availablePairs = useMemo(() => (
    discoveredPairs.length
      ? [...discoveredPairs, ...masterPairs.filter((p) => !discoveredPairs.includes(p))]
      : masterPairs
  ), [discoveredPairs, masterPairs]);

  const currentDataset = useMemo(
    () => (datasets?.pairs || []).find((p) => p.pair === pair) || null,
    [datasets, pair],
  );

  const tfsForPair = useMemo(
    () => (currentDataset?.timeframes || []).map((t) => t.tf),
    [currentDataset],
  );

  const availableTFs = useMemo(() => (
    tfsForPair.length
      ? [...tfsForPair, ...DATASET_MASTER_TIMEFRAMES.filter((t) => !tfsForPair.includes(t))]
      : DATASET_MASTER_TIMEFRAMES
  ), [tfsForPair]);

  const currentTFEntry = useMemo(
    () => (currentDataset?.timeframes || []).find((t) => t.tf === timeframe) || null,
    [currentDataset, timeframe],
  );

  const minCandles = datasets?.min_candles || 200;

  const dataStatus = useMemo(() => {
    if (!datasets) return { level: 'unknown', label: 'Checking…', candles: null };
    if (!currentDataset) {
      return { level: 'missing', label: `No ${pair} data in DB`, candles: 0 };
    }
    if (!currentTFEntry) {
      const have = tfsForPair.join(', ') || 'none';
      return {
        level: 'missing',
        label: `No ${pair}/${timeframe} data (have ${have})`,
        candles: 0,
      };
    }
    if (!currentTFEntry.sufficient) {
      return {
        level: 'insufficient',
        label: `Only ${currentTFEntry.candles} candles — need ≥${minCandles}`,
        candles: currentTFEntry.candles,
      };
    }
    return {
      level: 'ok',
      label: `${currentTFEntry.candles} candles ready`,
      candles: currentTFEntry.candles,
    };
  }, [datasets, currentDataset, currentTFEntry, tfsForPair, pair, timeframe, minCandles]);

  const isDataReady = dataStatus.level === 'ok';

  // Auto-switch TF on pair change when the current TF isn't usable.
  useEffect(() => {
    if (!datasets || !currentDataset) return;
    if (currentTFEntry && currentTFEntry.sufficient) return;
    const bestTF = (currentDataset.timeframes || [])
      .filter((t) => t.sufficient)
      .sort((a, b) => b.candles - a.candles)[0];
    if (bestTF && bestTF.tf !== timeframe && typeof setTimeframe === 'function') {
      setTimeframe(bestTF.tf);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pair, datasets]);

  const loadData = useCallback(async () => {
    setDownloadError(null);
    setDownloadResult(null);
    setDownloading(true);
    try {
      const res = await loadMarketData({ pair, timeframe });
      setDownloadResult(res);
      await refreshDatasets();
    } catch (e) {
      setDownloadError(e.message || String(e));
    } finally {
      setDownloading(false);
    }
  }, [pair, timeframe, refreshDatasets]);

  const clearDownload = useCallback(() => {
    setDownloadResult(null);
    setDownloadError(null);
  }, []);

  return {
    datasets,
    availablePairs,
    availableTFs,
    currentDataset,
    tfsForPair,
    dataStatus,
    isDataReady,
    minCandles,
    refreshDatasets,
    downloading,
    downloadResult,
    downloadError,
    loadData,
    clearDownload,
  };
}
