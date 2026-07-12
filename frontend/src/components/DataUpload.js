import React, { useState, useEffect, useCallback, useRef } from 'react';
import { UploadSimple, CircleNotch, Database, CheckCircle, File, X, CloudArrowDown, ArrowsClockwise, MagnifyingGlass, Wrench, Warning, ShieldCheck, HardDrives, FolderOpen, ArrowRight } from '@phosphor-icons/react';
import { uploadMarketData, getMarketData, downloadMarketData, checkDataGaps, fixDataGaps, getServerFiles, importServerFile,
  getAutoMaintenanceStatus, toggleAutoMaintenance, runAutoMaintenanceNow } from '../services/api';
import { useMarketUniverse } from '../hooks/useMarketUniverse';

const SYMBOLS_LEGACY = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'US100', 'BTCUSD', 'ETHUSD'];
const TIMEFRAMES = [
  { value: '1m', label: '1 Min' }, { value: '5m', label: '5 Min' }, { value: '15m', label: '15 Min' },
  { value: '30m', label: '30 Min' }, { value: '1h', label: '1 Hour' }, { value: '4h', label: '4 Hour' }, { value: '1d', label: '1 Day' },
];
const SOURCES = [
  { value: 'bid_1m', label: 'BID Data', desc: 'Candle stream' },
  { value: 'bi5',    label: 'BI5 Tick Data', desc: 'Raw ticks' },
];

const MAX_UPLOAD_MB = 500;

function formatFullDate(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDateWithTime(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

function calcDuration(startIso, endIso) {
  if (!startIso || !endIso) return '';
  const start = new Date(startIso);
  const end = new Date(endIso);
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return '';
  const diffMs = end - start;
  const days = diffMs / (1000 * 60 * 60 * 24);
  if (days < 1) {
    const hours = Math.round(diffMs / (1000 * 60 * 60));
    return `${hours}h`;
  }
  if (days < 30) return `${Math.round(days)}d`;
  if (days < 365) {
    const months = (days / 30.44).toFixed(1);
    return `${months}mo`;
  }
  const years = (days / 365.25).toFixed(1);
  return `${years}y`;
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function QualityBadge({ status, testId }) {
  if (!status) return null;
  const config = {
    Good: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', border: 'border-emerald-500/20' },
    Moderate: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/20' },
    Poor: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/20' },
  };
  const c = config[status] || config.Poor;
  return (
    <span data-testid={testId} className={`text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${c.bg} ${c.text} ${c.border}`}>
      {status}
    </span>
  );
}

function CoverageBar({ pct, testId }) {
  const color = pct >= 98 ? 'bg-emerald-500' : pct >= 90 ? 'bg-yellow-500' : 'bg-red-500';
  const textColor = pct >= 98 ? 'text-emerald-500' : pct >= 90 ? 'text-yellow-500' : 'text-red-500';
  return (
    <div data-testid={testId} className="flex items-center gap-1.5">
      <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-300`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className={`text-[9px] font-bold font-mono ${textColor}`}>{pct}%</span>
    </div>
  );
}

export default function DataUpload() {
  // R4 — registry-backed ingestion symbol list.
  const { options: SYMBOLS } = useMarketUniverse({ eligibility: 'ingestion' });
  const [symbol, setSymbol] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('1h');
  const [source, setSource] = useState('bid_1m');           // CRITICAL: bid_1m | bi5 (per-source isolation)
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const fileInputRef = useRef(null);

  // Auto-maintenance state
  const [autoStatus, setAutoStatus] = useState(null);
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoError, setAutoError] = useState(null);

  const [dlSymbol, setDlSymbol] = useState('EURUSD');
  const [dlTimeframe, setDlTimeframe] = useState('1h');
  const [dlDateFrom, setDlDateFrom] = useState('');
  const [dlDateTo, setDlDateTo] = useState('');
  const [dlLoading, setDlLoading] = useState(false);
  const [dlResult, setDlResult] = useState(null);
  const [dlError, setDlError] = useState(null);
  const [activeTab, setActiveTab] = useState('download');

  const [gapSymbol, setGapSymbol] = useState('');
  const [gapTimeframe, setGapTimeframe] = useState('');
  const [gapLoading, setGapLoading] = useState(false);
  const [gapResult, setGapResult] = useState(null);
  const [gapError, setGapError] = useState(null);
  const [fixLoading, setFixLoading] = useState(false);
  const [fixResult, setFixResult] = useState(null);

  // Server import state
  const [serverFiles, setServerFiles] = useState([]);
  const [serverImportDir, setServerImportDir] = useState('/app/data_imports');
  const [siSymbol, setSiSymbol] = useState('EURUSD');
  const [siTimeframe, setSiTimeframe] = useState('1m');
  const [siSelected, setSiSelected] = useState(null);
  const [siLoading, setSiLoading] = useState(false);
  const [siResult, setSiResult] = useState(null);
  const [siError, setSiError] = useState(null);
  const [siListLoading, setSiListLoading] = useState(false);

  const fetchDatasets = useCallback(async () => {
    try { const data = await getMarketData(); setDatasets(data.datasets || []); } catch (e) { console.error(e); }
  }, []);
  useEffect(() => { fetchDatasets(); }, [fetchDatasets]);

  const fetchAutoStatus = useCallback(async () => {
    try { setAutoStatus(await getAutoMaintenanceStatus()); setAutoError(null); }
    catch (e) { setAutoError(e.message); }
  }, []);
  useEffect(() => {
    fetchAutoStatus();
    const id = setInterval(fetchAutoStatus, 30000);   // refresh every 30s
    return () => clearInterval(id);
  }, [fetchAutoStatus]);
  useEffect(() => {
    const now = new Date();
    setDlDateTo(now.toISOString().split('T')[0]);
    setDlDateFrom(new Date(now.getFullYear(), now.getMonth() - 3, now.getDate()).toISOString().split('T')[0]);
  }, []);

  const fetchServerFiles = useCallback(async () => {
    setSiListLoading(true);
    try {
      const data = await getServerFiles();
      setServerFiles(data.files || []);
      setServerImportDir(data.import_directory || '/app/data_imports');
    } catch (e) { console.error(e); }
    finally { setSiListLoading(false); }
  }, []);

  useEffect(() => {
    if (activeTab === 'server') fetchServerFiles();
  }, [activeTab, fetchServerFiles]);

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.csv')) {
      setError('Only CSV files are accepted');
      setFile(null);
      return;
    }
    const sizeMb = f.size / (1024 * 1024);
    if (sizeMb > MAX_UPLOAD_MB) {
      setError(`File too large (${formatFileSize(f.size)}). Max upload is ${MAX_UPLOAD_MB} MB. Use Server Import for very large files.`);
      setFile(null);
      return;
    }
    setFile(f);
    setError(null);
    setResult(null);
  };
  const handleRemoveFile = () => { setFile(null); setResult(null); setError(null); if (fileInputRef.current) fileInputRef.current.value = ''; };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true); setError(null); setResult(null);
    // Snapshot current record count so we can detect "backend committed even
    // though HTTP failed/timed out" (ingress 502/504). Backend truth > transport.
    const prevRecords = (datasets.find(d => d.symbol === symbol && d.timeframe === timeframe && d.source === source)?.records) || 0;

    const reconcile = async (reasonLabel) => {
      try {
        const fresh = await getMarketData();
        const after = (fresh.datasets || []).find(d => d.symbol === symbol && d.timeframe === timeframe && d.source === source);
        const afterRecords = after?.records || 0;
        setDatasets(fresh.datasets || []);
        if (afterRecords > prevRecords) {
          setResult({
            status: 'success',
            verified_after_timeout: true,
            rows_inserted: afterRecords - prevRecords,
            symbol,
            source,
            timeframe,
            previous_row_count: prevRecords,
            total_rows_after: afterRecords,
            note: `Upload successful (verified after ${reasonLabel})`,
          });
          setFile(null);
          if (fileInputRef.current) fileInputRef.current.value = '';
          return true;
        }
      } catch (reconcileErr) {
        console.error('[handleUpload] reconciliation failed', reconcileErr);
      }
      return false;
    };

    try {
      const data = await uploadMarketData(file, symbol, timeframe, source);

      // "unknown" = gateway error / network drop → backend may have committed.
      if (data && data.status === 'unknown') {
        const reasonLabel = data.http ? `HTTP ${data.http}` : 'network error';
        const verified = await reconcile(reasonLabel);
        if (verified) return;
        // Reconciliation shows no new rows → true failure.
        setError(data.reason || `Upload failed (HTTP ${data.http || 'network'})`);
        return;
      }

      // Confirmed 2xx success path.
      setResult(data);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      fetchDatasets();
    } catch (e) {
      console.error('[handleUpload] upload threw', e);
      // Real 4xx / other thrown error — still try reconciliation as safety net.
      const verified = await reconcile('error');
      if (!verified) setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.csv')) { setError('Only CSV files are accepted'); return; }
    const sizeMb = f.size / (1024 * 1024);
    if (sizeMb > MAX_UPLOAD_MB) {
      setError(`File too large (${formatFileSize(f.size)}). Max upload is ${MAX_UPLOAD_MB} MB. Use Server Import for very large files.`);
      return;
    }
    setFile(f);
    setError(null);
    setResult(null);
  };

  const handleDownload = async () => {
    if (!dlDateFrom || !dlDateTo) { setDlError('Select dates'); return; }
    setDlLoading(true); setDlError(null); setDlResult(null);
    try { const data = await downloadMarketData(dlSymbol, dlTimeframe, dlDateFrom, dlDateTo); setDlResult(data); fetchDatasets(); }
    catch (e) { setDlError(e.message); } finally { setDlLoading(false); }
  };

  const handleCheckGaps = async (sym, tf) => {
    const s = sym || gapSymbol, t = tf || gapTimeframe;
    if (!s || !t) return;
    setGapSymbol(s); setGapTimeframe(t); setGapLoading(true); setGapError(null); setGapResult(null); setFixResult(null);
    try { const data = await checkDataGaps(s, t); setGapResult(data); } catch (e) { setGapError(e.message); } finally { setGapLoading(false); }
  };

  const handleFixGaps = async () => {
    if (!gapSymbol || !gapTimeframe) return; setFixLoading(true); setFixResult(null);
    try { const data = await fixDataGaps(gapSymbol, gapTimeframe); setFixResult(data); await handleCheckGaps(gapSymbol, gapTimeframe); fetchDatasets(); }
    catch (e) { setGapError(e.message); } finally { setFixLoading(false); }
  };

  const handleServerImport = async () => {
    if (!siSelected) return;
    setSiLoading(true); setSiError(null); setSiResult(null);
    try {
      const data = await importServerFile(siSelected, siSymbol, siTimeframe);
      setSiResult(data);
      fetchDatasets();
      fetchServerFiles();
    } catch (e) { setSiError(e.message); } finally { setSiLoading(false); }
  };

  const handleAutoToggle = async () => {
    const nextEnabled = !(autoStatus?.enabled);
    setAutoLoading(true); setAutoError(null);
    try {
      const resp = await toggleAutoMaintenance(nextEnabled);
      setAutoStatus(resp.status);
      fetchDatasets();
    } catch (e) { setAutoError(e.message); }
    finally { setAutoLoading(false); }
  };

  const handleAutoRunNow = async () => {
    setAutoLoading(true); setAutoError(null);
    try {
      const resp = await runAutoMaintenanceNow();
      setAutoStatus(resp.status);
      fetchDatasets();
    } catch (e) { setAutoError(e.message); }
    finally { setAutoLoading(false); }
  };

  // Datasets filtered by currently selected source (bid_1m / bi5).
  const visibleDatasets = datasets.filter(d => (d.source || 'bid_1m') === source);

  const selectClass = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-3 py-2 text-sm font-mono focus:ring-1 focus:ring-zinc-600 focus:outline-none transition-colors w-full";
  const inputClass = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-3 py-2 text-sm font-mono focus:ring-1 focus:ring-zinc-600 focus:outline-none transition-colors w-full";

  return (
    <div data-testid="data-upload-section" className="bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
        <Database size={14} weight="bold" className="text-yellow-500" />
        <h2 className="text-sm font-semibold text-white">Market Data</h2>
        <span className="ml-auto text-xs font-mono text-zinc-500">{visibleDatasets.length} / {datasets.length} datasets</span>
      </div>

      {/* Data source toggle — CRITICAL: bid_1m and bi5 are independent streams. */}
      <div className="px-4 pt-3 pb-1 flex items-center gap-3">
        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Source</span>
        <div data-testid="source-toggle" className="flex border border-zinc-800 rounded-md overflow-hidden">
          {SOURCES.map(s => (
            <button
              key={s.value}
              data-testid={`source-${s.value}`}
              onClick={() => setSource(s.value)}
              className={`px-3 py-1.5 text-[11px] font-mono transition-colors ${
                source === s.value
                  ? 'bg-yellow-500/15 text-yellow-400 border-r border-yellow-500/30 last:border-r-0'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 border-r border-zinc-800 last:border-r-0'
              }`}
              title={s.desc}
            >
              {source === s.value ? '● ' : '○ '}{s.label}
            </button>
          ))}
        </div>
        <span className="text-[9px] font-mono text-zinc-600 italic ml-1">
          {source === 'bid_1m' ? 'Candle data — from Dukascopy / CSV uploads' : 'Raw tick data — CSV uploads only (no auto-fetch yet)'}
        </span>
      </div>

      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Left: Source Tabs */}
        <div className="flex flex-col gap-4">
          <div className="flex border border-zinc-800 rounded-md overflow-hidden">
            <button data-testid="tab-download" onClick={() => setActiveTab('download')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors ${activeTab === 'download' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'}`}>
              <CloudArrowDown size={12} /> Download
            </button>
            <button data-testid="tab-upload" onClick={() => setActiveTab('upload')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors ${activeTab === 'upload' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'}`}>
              <UploadSimple size={12} /> CSV Upload
            </button>
            <button data-testid="tab-server" onClick={() => setActiveTab('server')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium transition-colors ${activeTab === 'server' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'}`}>
              <HardDrives size={12} /> Server Import
            </button>
          </div>

          {activeTab === 'download' && (
            <div className="flex flex-col gap-3">
              <p className="text-[10px] font-mono text-zinc-600">Download real data from Dukascopy</p>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Symbol</label>
                  <select data-testid="dl-symbol-select" value={dlSymbol} onChange={(e) => setDlSymbol(e.target.value)} className={selectClass}>
                    {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select></div>
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Timeframe</label>
                  <select data-testid="dl-timeframe-select" value={dlTimeframe} onChange={(e) => setDlTimeframe(e.target.value)} className={selectClass}>
                    {TIMEFRAMES.map((tf) => <option key={tf.value} value={tf.value}>{tf.label}</option>)}
                  </select></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">From</label>
                  <input data-testid="dl-date-from" type="date" value={dlDateFrom} onChange={(e) => setDlDateFrom(e.target.value)} className={inputClass} /></div>
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">To</label>
                  <input data-testid="dl-date-to" type="date" value={dlDateTo} onChange={(e) => setDlDateTo(e.target.value)} className={inputClass} /></div>
              </div>
              <button data-testid="download-data-btn" onClick={handleDownload} disabled={dlLoading || !dlDateFrom || !dlDateTo}
                className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-4 py-2.5 text-sm transition-colors duration-150 flex items-center justify-center gap-2 disabled:opacity-30">
                {dlLoading ? <><CircleNotch size={14} className="animate-spin" /> Downloading...</> : <><CloudArrowDown size={14} /> Download</>}
              </button>
              {dlResult && (
                <div data-testid="download-success" className="flex items-start gap-2 bg-emerald-500/5 border border-emerald-500/20 rounded-md p-3">
                  <CheckCircle size={14} className="text-emerald-500 mt-0.5 flex-shrink-0" />
                  <div className="text-[11px] font-mono text-zinc-300">
                    <p className="text-emerald-500 font-semibold mb-0.5">Download complete</p>
                    <p>{dlResult.rows_downloaded} fetched, {dlResult.rows_inserted} inserted for {dlResult.symbol} ({dlResult.timeframe})</p>
                    {dlResult.rows_skipped > 0 && <p className="text-yellow-500">{dlResult.rows_skipped} duplicates skipped</p>}
                  </div>
                </div>
              )}
              {dlError && <p data-testid="download-error" className="text-red-500 text-xs font-mono">{dlError}</p>}
            </div>
          )}

          {activeTab === 'upload' && (
            <div className="flex flex-col gap-3">
              <p className="text-[10px] font-mono text-zinc-600">Upload CSV data (max {MAX_UPLOAD_MB} MB). For larger files, use Server Import.</p>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Symbol</label>
                  <select data-testid="data-symbol-select" value={symbol} onChange={(e) => setSymbol(e.target.value)} className={selectClass}>
                    {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select></div>
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Timeframe</label>
                  <select data-testid="data-timeframe-select" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className={selectClass}>
                    {TIMEFRAMES.map((tf) => <option key={tf.value} value={tf.value}>{tf.label}</option>)}
                  </select></div>
              </div>
              <div data-testid="data-drop-zone" onDrop={handleDrop} onDragOver={(e) => e.preventDefault()} onClick={() => fileInputRef.current?.click()}
                className="border border-dashed border-zinc-700 hover:border-zinc-500 rounded-md p-6 flex flex-col items-center justify-center gap-2 cursor-pointer transition-colors group">
                <input ref={fileInputRef} type="file" accept=".csv" onChange={handleFileChange} className="hidden" data-testid="data-file-input" />
                {file ? (
                  <div className="flex items-center gap-2">
                    <File size={16} className="text-emerald-500" />
                    <span className="text-sm font-mono text-white">{file.name}</span>
                    <span className="text-xs font-mono text-zinc-500">({formatFileSize(file.size)})</span>
                    <button data-testid="remove-file-btn" onClick={(e) => { e.stopPropagation(); handleRemoveFile(); }} className="text-zinc-500 hover:text-red-500 transition-colors"><X size={12} /></button>
                  </div>
                ) : (
                  <><UploadSimple size={20} className="text-zinc-600 group-hover:text-zinc-400 transition-colors" />
                  <p className="text-xs font-mono text-zinc-600">Drop CSV or click to browse</p>
                  <p className="text-[9px] font-mono text-zinc-700">Max {MAX_UPLOAD_MB} MB per upload</p></>
                )}
              </div>
              {file && file.size > 50 * 1024 * 1024 && (
                <div data-testid="large-file-warning" className="flex items-start gap-2 bg-yellow-500/5 border border-yellow-500/20 rounded-md p-2">
                  <Warning size={12} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                  <span className="text-[10px] font-mono text-yellow-500">Large file ({formatFileSize(file.size)}). Upload may take several minutes. For files over {MAX_UPLOAD_MB} MB, use Server Import.</span>
                </div>
              )}
              <button data-testid="upload-data-btn" onClick={handleUpload} disabled={!file || loading}
                className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-4 py-2.5 text-sm transition-colors duration-150 flex items-center justify-center gap-2 disabled:opacity-30">
                {loading ? <><CircleNotch size={14} className="animate-spin" /> Uploading...</> : <><UploadSimple size={14} /> Upload</>}
              </button>
              {result && (
                <div data-testid="upload-success" className="flex items-start gap-2 bg-emerald-500/5 border border-emerald-500/20 rounded-md p-3">
                  <CheckCircle size={14} className="text-emerald-500 mt-0.5 flex-shrink-0" />
                  <div className="text-[11px] font-mono text-zinc-300">
                    <p className="text-emerald-500 font-semibold">
                      {result.verified_after_timeout ? 'Upload successful (verified after timeout)' : 'Upload successful'}
                    </p>
                    <p>{result.rows_inserted} rows inserted for {result.symbol} ({result.timeframe})</p>
                    {result.file_size_mb && <p className="text-zinc-500">File size: {result.file_size_mb} MB</p>}
                    {result.note && <p data-testid="upload-success-note" className="text-zinc-500">{result.note}</p>}
                  </div>
                </div>
              )}
              {error && <p data-testid="upload-error" className="text-red-500 text-xs font-mono">{error}</p>}
            </div>
          )}

          {activeTab === 'server' && (
            <div className="flex flex-col gap-3">
              <p className="text-[10px] font-mono text-zinc-600">
                Import large CSV files directly from the server. Place files in:
              </p>
              <div data-testid="server-import-path" className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 flex items-center gap-2">
                <FolderOpen size={12} className="text-yellow-500 flex-shrink-0" />
                <code className="text-xs font-mono text-zinc-300 select-all">{serverImportDir}</code>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Symbol</label>
                  <select data-testid="si-symbol-select" value={siSymbol} onChange={(e) => setSiSymbol(e.target.value)} className={selectClass}>
                    {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select></div>
                <div><label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Timeframe</label>
                  <select data-testid="si-timeframe-select" value={siTimeframe} onChange={(e) => setSiTimeframe(e.target.value)} className={selectClass}>
                    {TIMEFRAMES.map((tf) => <option key={tf.value} value={tf.value}>{tf.label}</option>)}
                  </select></div>
              </div>

              <div className="flex items-center justify-between mb-1">
                <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Available Files</p>
                <button data-testid="refresh-server-files-btn" onClick={fetchServerFiles} className="text-zinc-600 hover:text-white transition-colors">
                  <ArrowsClockwise size={12} className={siListLoading ? 'animate-spin' : ''} />
                </button>
              </div>

              {serverFiles.length === 0 ? (
                <div className="bg-zinc-950 border border-zinc-800 border-dashed rounded-md p-4 text-center">
                  <p className="text-xs font-mono text-zinc-600">No CSV files found</p>
                  <p className="text-[9px] font-mono text-zinc-700 mt-1">Place .csv files in {serverImportDir}/</p>
                </div>
              ) : (
                <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto">
                  {serverFiles.map((sf) => (
                    <button key={sf.filename} data-testid={`server-file-${sf.filename}`}
                      onClick={() => setSiSelected(sf.filename)}
                      className={`text-left bg-zinc-950 border rounded-md px-3 py-2 flex items-center justify-between transition-colors ${
                        siSelected === sf.filename ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-zinc-800 hover:bg-zinc-800/50'
                      }`}>
                      <div className="flex items-center gap-2">
                        <File size={12} className={siSelected === sf.filename ? 'text-emerald-500' : 'text-zinc-500'} />
                        <span className="text-xs font-mono text-white truncate max-w-[200px]">{sf.filename}</span>
                      </div>
                      <span className="text-[10px] font-mono text-zinc-500">{sf.size_mb} MB</span>
                    </button>
                  ))}
                </div>
              )}

              <button data-testid="server-import-btn" onClick={handleServerImport} disabled={!siSelected || siLoading}
                className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-4 py-2.5 text-sm transition-colors duration-150 flex items-center justify-center gap-2 disabled:opacity-30">
                {siLoading ? <><CircleNotch size={14} className="animate-spin" /> Importing...</> : <><HardDrives size={14} /> Import from Server</>}
              </button>

              {siResult && (
                <div data-testid="server-import-success" className="flex items-start gap-2 bg-emerald-500/5 border border-emerald-500/20 rounded-md p-3">
                  <CheckCircle size={14} className="text-emerald-500 mt-0.5 flex-shrink-0" />
                  <div className="text-[11px] font-mono text-zinc-300">
                    <p className="text-emerald-500 font-semibold">Import complete (streaming)</p>
                    <p>{siResult.rows_inserted?.toLocaleString()} rows inserted for {siResult.symbol} ({siResult.timeframe})</p>
                    {siResult.file_size_mb && <p className="text-zinc-500">File: {siResult.file_size_mb} MB</p>}
                  </div>
                </div>
              )}
              {siError && <p data-testid="server-import-error" className="text-red-500 text-xs font-mono">{siError}</p>}
            </div>
          )}
        </div>

        {/* Right: Datasets + Quality */}
        <div className="flex flex-col gap-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Available Datasets</p>
              <button data-testid="refresh-datasets-btn" onClick={fetchDatasets} className="text-zinc-600 hover:text-white transition-colors"><ArrowsClockwise size={12} /></button>
            </div>
            {visibleDatasets.length === 0 ? (
              <p className="text-xs font-mono text-zinc-600 py-4">No {source === 'bid_1m' ? 'BID candle' : 'BI5 tick'} data yet</p>
            ) : (
              <div className="flex flex-col gap-2 max-h-[400px] overflow-y-auto">
                {visibleDatasets.map((ds, i) => {
                  const duration = calcDuration(ds.first_timestamp, ds.last_timestamp);
                  const hasCoverage = ds.coverage_pct !== undefined;
                  return (
                    <div key={`${ds.symbol}-${ds.timeframe}`} data-testid={`dataset-card-${i}`}
                      className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2.5 group hover:bg-zinc-800/50 transition-colors">
                      {/* Row 1: Symbol, TF, Quality Badge, Candle Count */}
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{ds.symbol}</span>
                          {ds.market_type && (
                            <span data-testid={`dataset-market-${i}`}
                              className={`text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${
                                ds.market_type === 'crypto'
                                  ? 'bg-orange-500/10 text-orange-400 border-orange-500/20'
                                  : 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                              }`}>
                              {ds.market_type === 'crypto' ? 'Crypto' : 'Forex'}
                            </span>
                          )}
                          <span className="text-[10px] font-mono text-zinc-500">{ds.timeframe}</span>
                          {duration && <span className="text-[9px] font-mono text-zinc-600 bg-zinc-800/50 px-1.5 py-0.5 rounded">{duration}</span>}
                          {hasCoverage && <QualityBadge status={ds.quality_status} testId={`dataset-quality-${i}`} />}
                        </div>
                        <div className="flex items-center gap-2">
                          <span data-testid={`dataset-candles-${i}`} className="text-xs font-bold font-mono text-white">{ds.records.toLocaleString()}</span>
                          <span className="text-[9px] font-mono text-zinc-600">candles</span>
                          <button data-testid={`check-gaps-btn-${i}`} onClick={() => handleCheckGaps(ds.symbol, ds.timeframe)}
                            className="text-zinc-600 hover:text-yellow-500 transition-colors opacity-0 group-hover:opacity-100" title="Check quality">
                            <MagnifyingGlass size={12} weight="bold" />
                          </button>
                        </div>
                      </div>

                      {/* Row 2: Date Range (full with year) */}
                      <div className="flex items-center gap-1 mb-1">
                        <span data-testid={`dataset-date-start-${i}`} className="text-[10px] font-mono text-zinc-400">
                          {formatFullDate(ds.first_timestamp)}
                        </span>
                        <ArrowRight size={8} className="text-zinc-600" />
                        <span data-testid={`dataset-date-end-${i}`} className="text-[10px] font-mono text-zinc-400">
                          {formatFullDate(ds.last_timestamp)}
                        </span>
                      </div>

                      {/* Row 3: Coverage bar + stats */}
                      {hasCoverage && (
                        <div className="flex flex-col gap-1">
                          <CoverageBar pct={ds.coverage_pct} testId={`dataset-coverage-${i}`} />
                          <div className="flex items-center gap-3 text-[9px] font-mono text-zinc-500">
                            <span>Expected: <strong className="text-zinc-400">{ds.expected_candles?.toLocaleString()}</strong></span>
                            {ds.gaps_count > 0 && (
                              <span className="text-yellow-500">
                                {ds.gaps_count} gap{ds.gaps_count !== 1 ? 's' : ''}
                                {ds.missing_candles > 0 && ` (~${ds.missing_candles.toLocaleString()} missing)`}
                              </span>
                            )}
                            {ds.gaps_count === 0 && <span className="text-emerald-500">No gaps</span>}
                          </div>
                          {ds.market_type && (
                            <p data-testid={`dataset-coverage-context-${i}`} className="text-[9px] font-mono text-zinc-600 italic">
                              {ds.market_type === 'crypto' ? '(24/7 market)' : '(Weekends excluded)'}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Gap Analysis */}
          {(gapLoading || gapResult || gapError) && (
            <div data-testid="gap-analysis-panel" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
              <div className="flex items-center gap-2 mb-2">
                {gapResult?.severity === 'ok' ? <ShieldCheck size={14} className="text-emerald-500" /> : <Warning size={14} className="text-yellow-500" />}
                <p className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider">Quality Check — {gapSymbol} ({gapTimeframe})</p>
                {gapResult && <QualityBadge status={gapResult.quality_status} testId="gap-quality-badge" />}
              </div>
              {gapLoading && <div className="flex items-center gap-2 py-2"><CircleNotch size={12} className="animate-spin text-zinc-500" /><span className="text-xs font-mono text-zinc-500">Scanning...</span></div>}
              {gapError && <p data-testid="gap-error" className="text-red-500 text-xs font-mono">{gapError}</p>}
              {gapResult && !gapLoading && (
                <div className="flex flex-col gap-2">
                  <div className="grid grid-cols-4 gap-2">
                    <div className="text-center bg-zinc-900 rounded p-1.5">
                      <p data-testid="gap-actual-candles" className="text-sm font-bold font-mono text-white">{gapResult.total_candles?.toLocaleString()}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Actual</p>
                    </div>
                    <div className="text-center bg-zinc-900 rounded p-1.5">
                      <p data-testid="gap-expected-candles" className="text-sm font-bold font-mono text-zinc-400">{gapResult.expected_candles?.toLocaleString()}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Expected</p>
                    </div>
                    <div className="text-center bg-zinc-900 rounded p-1.5">
                      <p data-testid="gap-count" className={`text-sm font-bold font-mono ${gapResult.gaps_found === 0 ? 'text-emerald-500' : 'text-yellow-500'}`}>{gapResult.gaps_found}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Gaps</p>
                    </div>
                    <div className="text-center bg-zinc-900 rounded p-1.5">
                      <p data-testid="gap-coverage" className={`text-sm font-bold font-mono ${gapResult.coverage_pct >= 98 ? 'text-emerald-500' : gapResult.coverage_pct >= 90 ? 'text-yellow-500' : 'text-red-500'}`}>{gapResult.coverage_pct}%</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Coverage</p>
                    </div>
                  </div>

                  {/* Coverage bar */}
                  <CoverageBar pct={gapResult.coverage_pct} testId="gap-coverage-bar" />

                  {gapResult.date_range && (
                    <p data-testid="gap-date-range" className="text-[9px] font-mono text-zinc-500">
                      {gapResult.date_range.start} <ArrowRight size={8} className="inline text-zinc-600" /> {gapResult.date_range.end}
                      {' '}<span className="text-zinc-600">({calcDuration(gapResult.date_range.start_full, gapResult.date_range.end_full)})</span>
                    </p>
                  )}

                  <div className="flex items-center gap-2">
                    <span data-testid="gap-severity" className={`text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border w-fit ${
                      gapResult.severity === 'ok' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' :
                      gapResult.severity === 'low' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' :
                      gapResult.severity === 'medium' ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' :
                      'bg-red-500/10 text-red-500 border-red-500/20'
                    }`}>{gapResult.severity}</span>
                    {gapResult.missing_candles > 0 && (
                      <span className="text-[9px] font-mono text-zinc-500">{gapResult.missing_candles.toLocaleString()} missing candles</span>
                    )}
                  </div>

                  {/* Gap list (top 5) */}
                  {gapResult.gaps && gapResult.gaps.length > 0 && (
                    <div className="mt-1">
                      <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1">Top Gaps</p>
                      <div className="flex flex-col gap-1 max-h-[120px] overflow-y-auto">
                        {gapResult.gaps.slice(0, 5).map((g, gi) => (
                          <div key={gi} data-testid={`gap-item-${gi}`} className="flex items-center justify-between text-[9px] font-mono bg-zinc-900 rounded px-2 py-1">
                            <span className="text-zinc-400">{g.gap_start} <ArrowRight size={7} className="inline text-zinc-600" /> {g.gap_end}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-yellow-500">{g.missing_candles} missing</span>
                              <span className="text-zinc-600">{g.duration_hours}h</span>
                            </div>
                          </div>
                        ))}
                        {gapResult.gaps.length > 5 && (
                          <p className="text-[8px] font-mono text-zinc-600 text-center">+{gapResult.gaps.length - 5} more gaps</p>
                        )}
                      </div>
                    </div>
                  )}

                  {gapResult.gaps_found > 0 && (
                    <button data-testid="fix-gaps-btn" onClick={handleFixGaps} disabled={fixLoading}
                      className="bg-yellow-500/10 text-yellow-500 hover:bg-yellow-500/20 border border-yellow-500/20 rounded-md font-medium text-xs px-3 py-2 transition-colors flex items-center justify-center gap-1.5 disabled:opacity-30">
                      {fixLoading ? <><CircleNotch size={12} className="animate-spin" /> Fixing...</> : <><Wrench size={12} /> Fix Missing Data ({gapResult.missing_candles})</>}
                    </button>
                  )}
                  {fixResult && (
                    <div data-testid="fix-result" className="flex items-start gap-2 bg-emerald-500/5 border border-emerald-500/20 rounded-md p-2">
                      <CheckCircle size={12} className="text-emerald-500 mt-0.5 flex-shrink-0" />
                      <div className="text-[10px] font-mono text-zinc-300">
                        <p>{fixResult.message}</p>
                        {fixResult.coverage_before !== undefined && fixResult.coverage_after !== undefined && (
                          <p className="text-zinc-500 mt-0.5">
                            Coverage: <span className="text-yellow-500">{fixResult.coverage_before}%</span> <ArrowRight size={8} className="inline text-zinc-600" /> <span className="text-emerald-500">{fixResult.coverage_after}%</span>
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                  {gapResult.gaps_found === 0 && (
                    <div data-testid="no-gaps-msg" className="flex items-center gap-2 bg-emerald-500/5 border border-emerald-500/20 rounded-md p-2">
                      <ShieldCheck size={12} className="text-emerald-500" />
                      <span className="text-[10px] font-mono text-emerald-500 font-semibold">Clean — no gaps detected (weekends excluded)</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ───────── Auto Data Maintenance panel ───────── */}
      <div data-testid="auto-maintenance-panel" className="border-t border-zinc-800 px-4 py-3 bg-zinc-950/30">
        <div className="flex items-center gap-3 flex-wrap">
          <ArrowsClockwise size={14} weight="bold" className={`${autoStatus?.enabled ? 'text-emerald-400 animate-[spin_6s_linear_infinite]' : 'text-zinc-600'}`} />
          <p className="text-[11px] font-medium text-zinc-300 uppercase tracking-wider">Auto Data Maintenance</p>

          <label data-testid="auto-toggle-label" className="ml-auto flex items-center gap-2 cursor-pointer">
            <span className={`text-[10px] font-mono ${autoStatus?.enabled ? 'text-emerald-400' : 'text-zinc-500'}`}>
              {autoStatus?.enabled ? 'ON' : 'OFF'}
            </span>
            <button
              data-testid="auto-toggle-btn"
              onClick={handleAutoToggle}
              disabled={autoLoading}
              aria-pressed={!!autoStatus?.enabled}
              className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors disabled:opacity-40 ${
                autoStatus?.enabled ? 'bg-emerald-500/80' : 'bg-zinc-700'
              }`}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                autoStatus?.enabled ? 'translate-x-5' : 'translate-x-1'
              }`} />
            </button>
          </label>

          <button
            data-testid="auto-run-now-btn"
            onClick={handleAutoRunNow}
            disabled={autoLoading}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-md px-2.5 py-1 text-[10px] font-mono flex items-center gap-1 disabled:opacity-40"
          >
            {autoLoading ? <CircleNotch size={10} className="animate-spin" /> : <ArrowsClockwise size={10} />} Run now
          </button>
        </div>

        {autoError && <p data-testid="auto-error" className="text-red-500 text-[10px] font-mono mt-2">{autoError}</p>}

        {autoStatus && (
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <div data-testid="auto-next-runs" className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-[10px] font-mono text-zinc-400">
              <p className="text-zinc-500 mb-1">Schedule</p>
              <p>BID track: every {autoStatus.bid_interval_minutes} min</p>
              <p>BI5 track: every {autoStatus.bi5_interval_minutes} min</p>
              {autoStatus.next_runs?.bid_track && (
                <p className="mt-1 text-zinc-500">Next BID run: <span className="text-zinc-300">{new Date(autoStatus.next_runs.bid_track).toLocaleTimeString()}</span></p>
              )}
              {autoStatus.next_runs?.bi5_track && (
                <p className="text-zinc-500">Next BI5 run: <span className="text-zinc-300">{new Date(autoStatus.next_runs.bi5_track).toLocaleTimeString()}</span></p>
              )}
              {!autoStatus.enabled && <p className="text-zinc-600 italic">Scheduler OFF — toggle ON to start recurring runs.</p>}
            </div>

            <div data-testid="auto-status-list" className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-[10px] font-mono">
              <p className="text-zinc-500 mb-1">Per-symbol status</p>
              {(!autoStatus.statuses || autoStatus.statuses.length === 0) ? (
                <p className="text-zinc-600 italic">No runs yet.</p>
              ) : (
                <div className="flex flex-col gap-0.5 max-h-[120px] overflow-y-auto">
                  {autoStatus.statuses.map((s, i) => {
                    const colour = s.state === 'ok' ? 'text-emerald-400'
                      : s.state === 'error' ? 'text-red-400'
                      : s.state === 'manual_only' ? 'text-zinc-500' : 'text-zinc-400';
                    const icon = s.state === 'ok' ? '✔' : s.state === 'error' ? '✘' : '•';
                    return (
                      <div key={i} data-testid={`auto-status-row-${i}`} className="flex items-center gap-2">
                        <span className={`${colour}`}>{icon}</span>
                        <span className="text-zinc-300">{s.symbol}</span>
                        <span className="text-zinc-600">/</span>
                        <span className="text-zinc-400">{s.source}</span>
                        {s.coverage_pct !== undefined && s.coverage_pct !== null && (
                          <span className="text-zinc-500 ml-auto">{s.coverage_pct}%</span>
                        )}
                        {typeof s.gaps_count === 'number' && s.gaps_count > 0 && (
                          <span className="text-yellow-500">{s.gaps_count} gaps</span>
                        )}
                        {s.state === 'manual_only' && <span className="text-zinc-600 italic">manual</span>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
