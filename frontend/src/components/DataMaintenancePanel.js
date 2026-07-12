import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Database, Spinner, Play, Power, FloppyDisk, DownloadSimple,
  UploadSimple, Broom, ChartBar, CheckCircle, Warning, ClockCounterClockwise,
} from '@phosphor-icons/react';
import { useMarketUniverse } from '../hooks/useMarketUniverse';
import {
  getDataMaintenanceStatus, toggleDataMaintenance, runDataMaintenance,
  getDataMaintenanceConfig, saveDataMaintenanceConfig,
  getDataMaintenanceCoverage, dataExportSingleUrl,
  importDataBackup, backfillDataMaintenance, exportMarketData,
} from '../services/api';
import { AsfEmptyState } from './ui-asf';

/**
 * Phase 5.2 — Data Maintenance Panel.
 *
 * Rendered BELOW the existing DataUpload panel in the Market Data tab.
 * Additive only — the original manual download / CSV upload UI is
 * untouched.
 */

const PAIR_OPTIONS_LEGACY = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'US100', 'BTCUSD', 'ETHUSD'];
const TF_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];
const FREQ_OPTIONS = ['manual', 'hourly', 'daily'];

function Badge({ tone = 'zinc', children }) {
  const cls = {
    zinc: 'bg-zinc-800/60 border-zinc-700 text-zinc-300',
    emerald: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300',
    yellow: 'bg-yellow-500/10 border-yellow-500/40 text-yellow-300',
    red: 'bg-red-500/10 border-red-500/40 text-red-300',
    primary: 'bg-accent-primary/10 border-accent-primary/40 text-accent-primary',
  }[tone];
  return (
    <span className={`inline-flex items-center gap-1 text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${cls}`}>
      {children}
    </span>
  );
}

/**
 * Compact "history coverage" widget for the coverage table:
 *   N.NN m / TARGETm    [████░░░░] PCT%
 * Color-codes by progress: red <30%, yellow 30-80%, green ≥80%.
 */
function BackfillProgress({ actualMonths, targetMonths, progressPct }) {
  if (targetMonths == null || targetMonths === 0) {
    return <span className="text-[10px] font-mono text-zinc-500">—</span>;
  }
  const am = Number(actualMonths || 0);
  const tm = Number(targetMonths || 0);
  const pct = Math.max(0, Math.min(100, Number(progressPct || 0)));
  const tone =
    pct >= 80 ? 'bg-emerald-400'
    : pct >= 30 ? 'bg-yellow-400'
    : 'bg-red-400';
  const textTone =
    pct >= 80 ? 'text-emerald-300'
    : pct >= 30 ? 'text-yellow-300'
    : 'text-red-300';
  return (
    <div className="inline-flex flex-col items-end gap-0.5 min-w-[72px]">
      <span className={`text-[10px] font-mono tabular-nums ${textTone}`}>
        {am.toFixed(2)}m / {tm}m
      </span>
      <div className="w-16 h-1 bg-zinc-800 rounded overflow-hidden">
        <div className={`h-full ${tone} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[9px] font-mono tabular-nums text-zinc-500">{pct.toFixed(1)}%</span>
    </div>
  );
}

function MultiSelect({ value, options, onChange, testId }) {
  const toggle = (v) => {
    const has = value.includes(v);
    onChange(has ? value.filter((x) => x !== v) : [...value, v]);
  };
  return (
    <div data-testid={testId} className="flex flex-wrap gap-1">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button
            key={o}
            data-testid={`${testId}-${o}`}
            type="button"
            onClick={() => toggle(o)}
            className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${
              on
                ? 'bg-accent-primary/15 border-accent-primary/50 text-accent-primary'
                : 'bg-[#0B0F14] border-zinc-800 text-zinc-400 hover:border-zinc-600'
            }`}
          >
            {o}
          </button>
        );
      })}
    </div>
  );
}

export default function DataMaintenancePanel() {
  // R4 — registry-backed pair options. Falls back to legacy 7 when API down.
  const { options: PAIR_OPTIONS } = useMarketUniverse({ eligibility: 'ingestion' });
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [coverage, setCoverage] = useState([]);
  const [runResult, setRunResult] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [exportResult, setExportResult] = useState(null);
  const [loading, setLoading] = useState({
    status: false, toggle: false, run: false, save: false, import: false, backfill: false, exportZip: false,
  });
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  const refreshAll = useCallback(async () => {
    setLoading((l) => ({ ...l, status: true }));
    setError(null);
    try {
      const [s, c, cov] = await Promise.all([
        getDataMaintenanceStatus(),
        getDataMaintenanceConfig(),
        getDataMaintenanceCoverage(),
      ]);
      setStatus(s);
      setConfig(c);
      setCoverage(cov.coverage || []);
    } catch (e) {
      setError(e.message || 'Failed to load maintenance status');
    } finally {
      setLoading((l) => ({ ...l, status: false }));
    }
  }, []);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  const updateConfigField = (patch) => {
    setConfig((c) => ({ ...(c || {}), ...patch }));
  };

  const saveConfig = async () => {
    if (!config) return;
    setLoading((l) => ({ ...l, save: true })); setError(null);
    try {
      const payload = {
        pairs: config.pairs,
        timeframes: config.timeframes,
        retention: config.retention,
        frequency: config.frequency,
      };
      const r = await saveDataMaintenanceConfig(payload);
      setConfig(r.config || config);
    } catch (e) {
      setError(e.message || 'Save failed');
    } finally {
      setLoading((l) => ({ ...l, save: false }));
    }
  };

  const toggle = async (nextEnabled) => {
    setLoading((l) => ({ ...l, toggle: true })); setError(null);
    try {
      await toggleDataMaintenance(nextEnabled);
      await refreshAll();
    } catch (e) {
      setError(e.message || 'Toggle failed');
    } finally {
      setLoading((l) => ({ ...l, toggle: false }));
    }
  };

  const runNow = async () => {
    setLoading((l) => ({ ...l, run: true })); setError(null);
    try {
      const res = await runDataMaintenance({
        pairs: config?.pairs, timeframes: config?.timeframes, enforce: true,
      });
      setRunResult(res);
      await refreshAll();
    } catch (e) {
      setError(e.message || 'Run failed');
    } finally {
      setLoading((l) => ({ ...l, run: false }));
    }
  };

  const runBackfill = async () => {
    setLoading((l) => ({ ...l, backfill: true })); setError(null);
    try {
      const res = await backfillDataMaintenance({
        pairs: config?.pairs, timeframes: ['1h'],
      });
      setRunResult({
        ran_at: new Date().toISOString(),
        new_records: res?.total_candles_added ?? 0,
        backfill: true, target_months: res?.target_months,
        results: res?.results,
      });
      await refreshAll();
    } catch (e) {
      setError(e.message || 'Backfill failed');
    } finally {
      setLoading((l) => ({ ...l, backfill: false }));
    }
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading((l) => ({ ...l, import: true })); setError(null);
    try {
      const res = await importDataBackup(file);
      setImportResult(res);
      await refreshAll();
    } catch (err) {
      setError(err.message || 'Import failed');
    } finally {
      setLoading((l) => ({ ...l, import: false }));
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleExportMarketData = async () => {
    if (loading.exportZip) return;
    setLoading((l) => ({ ...l, exportZip: true })); setError(null);
    setExportResult(null);
    try {
      const res = await exportMarketData({});
      setExportResult(res);
    } catch (err) {
      setError(err.message || 'Export failed');
    } finally {
      setLoading((l) => ({ ...l, exportZip: false }));
    }
  };

  const enabled = Boolean(status?.enabled);

  return (
    <div
      className="asf-section asf-u2-panel rounded-md border border-zinc-800 bg-surface-card p-4 mt-4"
      data-testid="data-maintenance-panel"
    >
      {/* Header */}
      <div className="asf-section__hd flex items-center justify-between flex-wrap gap-3 mb-3">
        <div className="asf-legacy-title flex items-center gap-2">
          <Database size={18} className="text-accent-primary" weight="bold" />
          <h3 className="font-heading text-base font-bold text-zinc-100">
            Auto Data Maintenance
            <span className="ml-2 text-[10px] font-mono text-zinc-500">Phase 5.2</span>
          </h3>
          {enabled
            ? <Badge tone="emerald">scheduler ON</Badge>
            : <Badge tone="zinc">scheduler OFF</Badge>}
          {status?.frequency && <Badge tone="primary">{status.frequency}</Badge>}
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <button
            data-testid="dm-refresh-btn"
            onClick={refreshAll}
            disabled={loading.status}
            className="text-xs font-semibold px-3 py-1.5 rounded border border-zinc-700 hover:border-zinc-500 text-zinc-300 bg-[#0B0F14] disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading.status
              ? <Spinner size={12} className="animate-spin" />
              : <ClockCounterClockwise size={12} />}
            Refresh
          </button>
          <button
            data-testid="dm-toggle-btn"
            onClick={() => toggle(!enabled)}
            disabled={loading.toggle}
            className={`text-xs font-semibold px-3 py-1.5 rounded border flex items-center gap-1.5 ${
              enabled
                ? 'border-red-500/40 bg-red-500/10 hover:bg-red-500/20 text-red-300'
                : 'border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300'
            } disabled:opacity-50`}
          >
            {loading.toggle
              ? <Spinner size={12} className="animate-spin" />
              : <Power size={12} weight="bold" />}
            {enabled ? 'Turn OFF' : 'Turn ON'}
          </button>
          <button
            data-testid="dm-run-btn"
            onClick={runNow}
            disabled={loading.run}
            className="text-xs font-semibold px-3 py-1.5 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading.run ? <Spinner size={12} className="animate-spin" /> : <Play size={12} weight="fill" />}
            Run Now
          </button>
          <button
            data-testid="dm-backfill-btn"
            onClick={runBackfill}
            disabled={loading.backfill}
            title={`Backfill historical data for configured pairs (target = retention.bid_months = ${config?.retention?.bid_months ?? 36} months)`}
            className="text-xs font-semibold px-3 py-1.5 rounded border border-cyan-500/40 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading.backfill ? <Spinner size={12} className="animate-spin" /> : <DownloadSimple size={12} weight="bold" />}
            Backfill
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3">
          <AsfEmptyState
            slug="dm-error"
            testId="dm-error"
            title="Data maintenance error"
            body={error}
          />
        </div>
      )}

      {/* Status strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3" data-testid="dm-status-strip">
        <div className="rounded border border-zinc-800 bg-[#0F141A] px-3 py-2">
          <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Last Run</p>
          <p className="text-[11px] font-mono text-zinc-200 mt-1 truncate">
            {status?.last_run ? new Date(status.last_run).toLocaleString() : '—'}
          </p>
        </div>
        <div className="rounded border border-zinc-800 bg-[#0F141A] px-3 py-2">
          <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Next Run</p>
          <p className="text-[11px] font-mono text-zinc-200 mt-1 truncate">
            {status?.next_run ? new Date(status.next_run).toLocaleString() : '—'}
          </p>
        </div>
        <div className="rounded border border-zinc-800 bg-[#0F141A] px-3 py-2">
          <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Pairs</p>
          <p className="text-[11px] font-mono text-zinc-200 mt-1">{(status?.pairs || []).length}</p>
        </div>
        <div className="rounded border border-zinc-800 bg-[#0F141A] px-3 py-2">
          <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Coverage Rows</p>
          <p className="text-[11px] font-mono text-zinc-200 mt-1">{coverage.length}</p>
        </div>
      </div>

      {/* Configuration */}
      <div
        className="rounded border border-zinc-800 bg-[#0F141A] p-3 mb-3"
        data-testid="dm-config"
      >
        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-2">
          Configuration
        </p>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-start">
          <div className="md:col-span-4">
            <p className="text-[9px] font-mono text-zinc-500 mb-1">Pairs</p>
            <MultiSelect
              testId="dm-pairs"
              value={config?.pairs || []}
              options={PAIR_OPTIONS}
              onChange={(v) => updateConfigField({ pairs: v })}
            />
          </div>
          <div className="md:col-span-4">
            <p className="text-[9px] font-mono text-zinc-500 mb-1">Timeframes</p>
            <MultiSelect
              testId="dm-timeframes"
              value={config?.timeframes || []}
              options={TF_OPTIONS}
              onChange={(v) => updateConfigField({ timeframes: v })}
            />
          </div>
          <div className="md:col-span-2 flex flex-col gap-1">
            <label className="text-[9px] font-mono text-zinc-500">BID months</label>
            <input
              data-testid="dm-retention-bid"
              type="number" min={1} max={120}
              value={config?.retention?.bid_months ?? 36}
              onChange={(e) => updateConfigField({
                retention: { ...(config?.retention || {}), bid_months: Number(e.target.value) },
              })}
              className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 tabular-nums focus:outline-none focus:border-accent-primary/40"
            />
            <label className="text-[9px] font-mono text-zinc-500 mt-1">BI5 months</label>
            <input
              data-testid="dm-retention-bi5"
              type="number" min={1} max={60}
              value={config?.retention?.bi5_months ?? 6}
              onChange={(e) => updateConfigField({
                retention: { ...(config?.retention || {}), bi5_months: Number(e.target.value) },
              })}
              className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 tabular-nums focus:outline-none focus:border-accent-primary/40"
            />
          </div>
          <div className="md:col-span-2 flex flex-col gap-1">
            <label className="text-[9px] font-mono text-zinc-500">Frequency</label>
            <select
              data-testid="dm-frequency"
              value={config?.frequency || 'manual'}
              onChange={(e) => updateConfigField({ frequency: e.target.value })}
              className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-accent-primary/40"
            >
              {FREQ_OPTIONS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <button
              data-testid="dm-save-config-btn"
              onClick={saveConfig}
              disabled={loading.save}
              className="mt-2 text-xs font-semibold px-3 py-1.5 rounded border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 disabled:opacity-50 flex items-center justify-center gap-1.5"
            >
              {loading.save ? <Spinner size={12} className="animate-spin" /> : <FloppyDisk size={12} weight="bold" />}
              Save
            </button>
          </div>
        </div>
      </div>

      {/* Coverage table */}
      <div
        className="rounded border border-zinc-800 bg-[#0F141A] overflow-hidden mb-3"
        data-testid="dm-coverage"
      >
        <div className="px-3 py-2 bg-zinc-900/60 text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 flex items-center gap-1">
          <ChartBar size={10} /> Data Coverage ({coverage.length})
        </div>
        <table className="w-full text-xs">
          <thead className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            <tr>
              <th className="text-left px-3 py-2">Symbol · Source · TF</th>
              <th className="text-left px-3 py-2">Range</th>
              <th className="text-right px-3 py-2">Rows</th>
              <th className="text-right px-3 py-2">Completeness</th>
              <th className="text-right px-3 py-2">History</th>
              <th className="text-right px-3 py-2">Gaps</th>
              <th className="text-right px-3 py-2">Export</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {coverage.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-zinc-500 font-mono text-xs">
                  Run maintenance to populate coverage.
                </td>
              </tr>
            )}
            {coverage.map((c) => (
              <tr
                key={`${c.symbol}-${c.source}-${c.timeframe}`}
                data-testid={`dm-coverage-${c.symbol}-${c.source}-${c.timeframe}`}
                className="hover:bg-zinc-900/40 transition-colors"
              >
                <td className="px-3 py-2 font-mono text-zinc-200">
                  {c.symbol} · {c.source} · {c.timeframe}
                </td>
                <td className="px-3 py-2 font-mono text-[10px] text-zinc-400">
                  {c.start_date ? new Date(c.start_date).toLocaleDateString() : '—'}
                  {' → '}
                  {c.end_date ? new Date(c.end_date).toLocaleDateString() : '—'}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300">{c.rows}</td>
                <td className="px-3 py-2 text-right">
                  <span className={`font-mono text-xs tabular-nums ${
                    (c.completeness || 0) >= 0.98
                      ? 'text-emerald-300'
                      : (c.completeness || 0) >= 0.9 ? 'text-yellow-300' : 'text-red-300'
                  }`}>
                    {(((c.completeness || 0) * 100)).toFixed(2)}%
                  </span>
                </td>
                <td className="px-3 py-2 text-right" data-testid={`dm-history-${c.symbol}-${c.source}-${c.timeframe}`}>
                  <BackfillProgress
                    actualMonths={c.actual_months}
                    targetMonths={c.target_months}
                    progressPct={c.backfill_progress_pct}
                  />
                </td>
                <td className="px-3 py-2 text-right">
                  {c.has_gaps
                    ? <Badge tone="yellow"><Warning size={9} /> GAPS</Badge>
                    : <Badge tone="emerald"><CheckCircle size={9} /> CLEAN</Badge>}
                </td>
                <td className="px-3 py-2 text-right">
                  <a
                    href={dataExportSingleUrl({ symbol: c.symbol, timeframe: c.timeframe, source: c.source })}
                    download
                    data-testid={`dm-export-${c.symbol}-${c.source}-${c.timeframe}`}
                    className="text-[9px] font-mono px-2 py-1 rounded border border-zinc-700 hover:border-accent-primary/50 hover:text-accent-primary text-zinc-300 bg-[#0B0F14] inline-flex items-center gap-1"
                  >
                    <DownloadSimple size={9} /> CSV
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Backup / restore */}
      <div
        className="rounded border border-zinc-800 bg-[#0F141A] p-3 mb-3 flex flex-wrap items-center gap-3"
        data-testid="dm-backup"
      >
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400">
          Backup & Restore
        </span>
        <button
          type="button"
          data-testid="dm-export-market-data-btn"
          onClick={handleExportMarketData}
          disabled={loading.exportZip}
          aria-busy={loading.exportZip}
          title="Export every BID + BI5 dataset as a portable ZIP (with manifest) for migration to another Emergent account"
          className="text-xs font-semibold px-3 py-1.5 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 disabled:opacity-50 disabled:cursor-not-allowed text-accent-primary flex items-center gap-1.5"
        >
          {loading.exportZip
            ? <Spinner size={12} className="animate-spin" />
            : <DownloadSimple size={12} weight="bold" />}
          {loading.exportZip ? 'Building ZIP…' : 'Export Market Data'}
        </button>
        <label
          data-testid="dm-import-btn"
          className={`text-xs font-semibold px-3 py-1.5 rounded border border-yellow-500/40 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-300 cursor-pointer flex items-center gap-1.5 ${loading.exportZip ? 'opacity-50 pointer-events-none' : ''}`}
        >
          {loading.import ? <Spinner size={12} className="animate-spin" /> : <UploadSimple size={12} weight="bold" />}
          Import ZIP
          <input
            ref={fileRef}
            type="file"
            accept=".zip,application/zip"
            onChange={handleImport}
            className="hidden"
            disabled={loading.exportZip}
          />
        </label>
        {exportResult && (
          <span className="text-[11px] font-mono text-zinc-400" data-testid="dm-export-result">
            exported <span className="text-emerald-300">{exportResult.totalDatasets}</span> dataset(s) ·
            <span className="text-emerald-300"> {exportResult.totalRows.toLocaleString()}</span> rows
          </span>
        )}
        {importResult && (
          <span className="text-[11px] font-mono text-zinc-400" data-testid="dm-import-result">
            imported <span className="text-emerald-300">{importResult.inserted}</span> ·
            skipped <span className="text-zinc-300">{importResult.skipped_duplicates}</span>
          </span>
        )}
      </div>

      {/* Last run summary */}
      {runResult && (
        <div
          className="rounded border border-zinc-800 bg-[#0F141A] p-3"
          data-testid="dm-run-summary"
        >
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-2 flex items-center gap-1">
            <Broom size={10} /> Last Maintenance Run
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono">
            <div>
              <p className="text-[9px] text-zinc-500">Updated Pairs</p>
              <p className="text-zinc-200">{(runResult.updated_pairs || []).length}</p>
            </div>
            <div>
              <p className="text-[9px] text-zinc-500">New Records</p>
              <p className="text-emerald-300">{runResult.new_records ?? 0}</p>
            </div>
            <div>
              <p className="text-[9px] text-zinc-500">Deleted Old</p>
              <p className="text-zinc-300">{runResult.deleted_old_records ?? 0}</p>
            </div>
            <div>
              <p className="text-[9px] text-zinc-500">Gaps Detected</p>
              <p className={
                (runResult.gaps_detected || []).length ? 'text-yellow-300' : 'text-emerald-300'
              }>
                {(runResult.gaps_detected || []).length}
              </p>
            </div>
          </div>
          {(runResult.errors || []).length > 0 && (
            <p className="text-[10px] font-mono text-red-300 mt-2">
              {runResult.errors.length} error(s) — see API response for details.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
