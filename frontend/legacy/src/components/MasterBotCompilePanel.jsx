import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Code, Package, GitDiff, Download, Spinner, ArrowsClockwise,
  X, ArrowRight, Plus, Minus, ArrowsLeftRight, FileText, ArrowSquareOut,
} from '@phosphor-icons/react';
import {
  compileMasterBot, listMasterBotDefinitions,
  exportMasterBotCs, listMasterBotExports, downloadMasterBotExportUrl,
  buildMasterBotPack, listMasterBotPacks, downloadMasterBotPackUrl,
  diffMasterBotRevisions,
} from '../services/api';
import { getToken } from '../services/auth';
import { AsfEmptyState } from './ui-asf';

/**
 * Master Bot Compile / Export / Pack / Diff panel — MB-4 / MB-7 / MB-8.
 *
 * Lives below the tier columns inside MasterBotDashboard. Provides:
 *   - Compile (mode dropdown) → new revision
 *   - Export latest → .cs + sidecar JSON (downloadable)
 *   - Build .cbotpack → zip
 *   - Revision diff viewer (modal)
 *
 * All write actions are admin-gated server-side; UI buttons are hidden
 * for non-admins.
 */

const RUNTIME_MODES = [
  { key: 'multi_strategy', label: 'Multi Strategy (default)' },
  { key: 'single_active',  label: 'Single Active (failover)' },
  { key: 'regime_aware',   label: 'Regime Aware (future)' },
];

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return `${d.toISOString().slice(0, 16).replace('T', ' ')}Z`;
  } catch { return iso; }
}

function StatusPill({ label, tone = 'zinc', testId }) {
  const tones = {
    green: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300',
    amber: 'bg-amber-500/10 border-amber-500/40 text-amber-300',
    red:   'bg-red-500/10 border-red-500/40 text-red-300',
    sky:   'bg-sky-500/10 border-sky-500/40 text-sky-300',
    zinc:  'bg-zinc-700/40 border-zinc-600/60 text-zinc-300',
  };
  return (
    <span data-testid={testId} className={`text-[9px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border ${tones[tone]}`}>
      {label}
    </span>
  );
}

// ─── Authenticated download (browser fetch + blob) ───────────────────
async function downloadAuthed(url, filenameFallback = 'download') {
  const token = getToken?.();
  const resp = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(`download failed (${resp.status}) ${txt}`.trim());
  }
  // Try to read Content-Disposition filename.
  const cd = resp.headers.get('content-disposition') || '';
  const m = /filename="([^"]+)"/i.exec(cd);
  const filename = (m && m[1]) || filenameFallback;
  const blob = await resp.blob();
  const obj = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = obj; a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(obj); a.remove(); }, 500);
}

// ─── Diff modal ─────────────────────────────────────────────────────
function RevisionDiffModal({ open, onClose, masterBotId, revisions }) {
  const [fromRev, setFromRev] = useState('');
  const [toRev,   setToRev]   = useState('');
  const [diff,    setDiff]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    if (!open) { setDiff(null); setError(null); return; }
    if (revisions.length >= 2) {
      setFromRev(String(revisions[1].rev));
      setToRev(String(revisions[0].rev));
    } else if (revisions.length === 1) {
      setFromRev('');
      setToRev(String(revisions[0].rev));
    }
  }, [open, revisions]);

  const run = useCallback(async () => {
    if (!masterBotId) return;
    setLoading(true); setError(null);
    try {
      const params = {};
      if (fromRev) params.fromRev = parseInt(fromRev, 10);
      if (toRev)   params.toRev   = parseInt(toRev, 10);
      const d = await diffMasterBotRevisions(masterBotId, params);
      setDiff(d);
    } catch (e) { setError(e.message); setDiff(null); }
    finally { setLoading(false); }
  }, [masterBotId, fromRev, toRev]);

  useEffect(() => { if (open && toRev) run(); }, [open, toRev, fromRev, run]);

  if (!open) return null;

  const sectionTitle = (label, count, tone) => (
    <div className="flex items-center gap-2 mb-1.5 mt-3">
      <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-300">{label}</h4>
      <StatusPill label={String(count)} tone={count > 0 ? tone : 'zinc'} />
    </div>
  );

  return (
    <div data-testid="mb-diff-modal" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-[860px] max-w-[95vw] max-h-[90vh] flex flex-col bg-surface-card border border-zinc-700 rounded-lg shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <GitDiff size={16} weight="duotone" className="text-accent-primary" />
            <h3 className="text-sm font-heading font-bold text-white">Revision Diff</h3>
          </div>
          <button data-testid="mb-diff-close" onClick={onClose} className="text-zinc-400 hover:text-zinc-200"><X size={16} /></button>
        </div>

        {/* Selector */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800 bg-zinc-900/30">
          <label className="text-[10px] font-mono uppercase text-zinc-500">From</label>
          <select data-testid="mb-diff-from-select" value={fromRev} onChange={(e) => setFromRev(e.target.value)}
                  className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 font-mono">
            <option value="">— initial —</option>
            {revisions.map((r) => <option key={r.revision_id} value={r.rev}>rev {r.rev}</option>)}
          </select>
          <ArrowRight size={14} className="text-zinc-600" />
          <label className="text-[10px] font-mono uppercase text-zinc-500">To</label>
          <select data-testid="mb-diff-to-select" value={toRev} onChange={(e) => setToRev(e.target.value)}
                  className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 font-mono">
            {revisions.map((r) => <option key={r.revision_id} value={r.rev}>rev {r.rev}</option>)}
          </select>
          <button data-testid="mb-diff-run" onClick={run} disabled={loading}
                  className="ml-auto px-3 py-1 text-xs font-mono text-accent-primary border border-accent-primary/40 hover:bg-accent-primary/10 rounded disabled:opacity-50 flex items-center gap-1.5">
            {loading ? <Spinner size={12} className="animate-spin" /> : <ArrowsLeftRight size={12} />} Compare
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-3 min-h-[200px]">
          {error && <div className="text-[11px] font-mono text-red-300 mb-2">{error}</div>}
          {!diff && !loading && <div className="text-[11px] font-mono text-zinc-500 italic">No diff yet. Select revisions above and click Compare.</div>}
          {diff && (
            <div data-testid="mb-diff-body" className="space-y-1">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-zinc-900/40 border border-zinc-800 rounded p-2">
                  <div className="text-[9px] font-mono uppercase text-zinc-500 mb-1">From</div>
                  <div className="text-[11px] font-mono text-zinc-300">
                    {diff.from ? `rev ${diff.from.rev} · ${(diff.from.definition_hash || '').slice(7, 23)}…` : '— initial (no prior rev) —'}
                  </div>
                </div>
                <div className="bg-zinc-900/40 border border-zinc-800 rounded p-2">
                  <div className="text-[9px] font-mono uppercase text-zinc-500 mb-1">To</div>
                  <div className="text-[11px] font-mono text-zinc-300">
                    rev {diff.to.rev} · {(diff.to.definition_hash || '').slice(7, 23)}…
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-400">
                <StatusPill label={diff.hash_changed ? 'HASH CHANGED' : 'HASH STABLE'} tone={diff.hash_changed ? 'amber' : 'green'} />
                {diff.is_initial && <StatusPill label="INITIAL" tone="sky" />}
              </div>

              {sectionTitle('Members Added',   (diff.members_added || []).length,   'green')}
              {(diff.members_added || []).length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">none</div>}
              {(diff.members_added || []).map((m) => (
                <div key={m.strategy_hash} className="flex items-center gap-2 px-2 py-1 bg-emerald-500/5 border border-emerald-500/20 rounded text-[11px] font-mono">
                  <Plus size={11} className="text-emerald-400" weight="bold" />
                  <span className="text-zinc-200">{m.strategy_hash.slice(0, 18)}</span>
                  <span className="text-zinc-500">{m.tier_key}</span>
                  <span className="text-zinc-500 ml-auto">{m.snapshot?.pair} / {m.snapshot?.timeframe}</span>
                </div>
              ))}

              {sectionTitle('Members Removed', (diff.members_removed || []).length, 'red')}
              {(diff.members_removed || []).length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">none</div>}
              {(diff.members_removed || []).map((m) => (
                <div key={m.strategy_hash} className="flex items-center gap-2 px-2 py-1 bg-red-500/5 border border-red-500/20 rounded text-[11px] font-mono">
                  <Minus size={11} className="text-red-400" weight="bold" />
                  <span className="text-zinc-200">{m.strategy_hash.slice(0, 18)}</span>
                  <span className="text-zinc-500">{m.tier_key}</span>
                </div>
              ))}

              {sectionTitle('Tier Moves', (diff.tier_moves || []).length, 'amber')}
              {(diff.tier_moves || []).length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">none</div>}
              {(diff.tier_moves || []).map((m) => (
                <div key={m.strategy_hash} className="flex items-center gap-2 px-2 py-1 bg-amber-500/5 border border-amber-500/20 rounded text-[11px] font-mono">
                  <span className="text-zinc-200">{m.strategy_hash.slice(0, 18)}</span>
                  <span className="text-amber-300">{m.from_tier}</span>
                  <ArrowRight size={11} className="text-zinc-500" />
                  <span className="text-amber-300">{m.to_tier}</span>
                </div>
              ))}

              {sectionTitle('Enable Changes', (diff.enable_changes || []).length, 'sky')}
              {(diff.enable_changes || []).length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">none</div>}
              {(diff.enable_changes || []).map((m) => (
                <div key={m.strategy_hash} className="flex items-center gap-2 px-2 py-1 bg-sky-500/5 border border-sky-500/20 rounded text-[11px] font-mono">
                  <span className="text-zinc-200">{m.strategy_hash.slice(0, 18)}</span>
                  <span className={m.from_enabled ? 'text-emerald-400' : 'text-zinc-500'}>{m.from_enabled ? 'ON' : 'OFF'}</span>
                  <ArrowRight size={11} className="text-zinc-500" />
                  <span className={m.to_enabled ? 'text-emerald-400' : 'text-zinc-500'}>{m.to_enabled ? 'ON' : 'OFF'}</span>
                </div>
              ))}

              {sectionTitle('Snapshot Drift', (diff.snapshot_drifts || []).length, 'zinc')}
              {(diff.snapshot_drifts || []).length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">none</div>}
              {(diff.snapshot_drifts || []).map((m) => (
                <div key={m.strategy_hash} className="px-2 py-1 bg-zinc-900/30 border border-zinc-800 rounded text-[11px] font-mono">
                  <div className="text-zinc-300">{m.strategy_hash.slice(0, 18)}</div>
                  <div className="ml-3 mt-0.5 text-[10px] text-zinc-500">
                    {Object.entries(m.fields).map(([f, v]) => (
                      <span key={f} className="mr-3">{f}: <span className="text-zinc-400">{String(v.from)}</span> → <span className="text-zinc-200">{String(v.to)}</span></span>
                    ))}
                  </div>
                </div>
              ))}

              {Object.keys(diff.ranker_changes || {}).length > 0 && (
                <>
                  {sectionTitle('Ranker Weight Changes', Object.keys(diff.ranker_changes).length, 'amber')}
                  {Object.entries(diff.ranker_changes).map(([k, v]) => (
                    <div key={k} className="px-2 py-1 text-[11px] font-mono text-zinc-300">
                      <span className="text-zinc-200">{k}</span>: <span className="text-zinc-500">{String(v.from)}</span> → <span className="text-accent-primary">{String(v.to)}</span>
                    </div>
                  ))}
                </>
              )}

              {Object.keys(diff.runtime_changes || {}).length > 0 && (
                <>
                  {sectionTitle('Runtime Changes', Object.keys(diff.runtime_changes).length, 'amber')}
                  {Object.entries(diff.runtime_changes).map(([k, v]) => (
                    <div key={k} className="px-2 py-1 text-[11px] font-mono text-zinc-300">
                      <span className="text-zinc-200">{k}</span>: <span className="text-zinc-500">{JSON.stringify(v.from)}</span> → <span className="text-accent-primary">{JSON.stringify(v.to)}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main panel ─────────────────────────────────────────────────────
export default function MasterBotCompilePanel({ masterBotId, isAdmin }) {
  const [revisions, setRevisions] = useState([]);
  const [exports, setExports]     = useState([]);
  const [packs, setPacks]         = useState([]);
  const [mode, setMode]           = useState('multi_strategy');
  const [loading, setLoading]     = useState(false);
  const [busy, setBusy]           = useState(null); // 'compile'|'export'|'pack'
  const [error, setError]         = useState(null);
  const [info, setInfo]           = useState(null);
  const [diffOpen, setDiffOpen]   = useState(false);

  const refresh = useCallback(async () => {
    if (!masterBotId) {
      setRevisions([]); setExports([]); setPacks([]); return;
    }
    setLoading(true); setError(null);
    try {
      const [d, e, p] = await Promise.all([
        listMasterBotDefinitions(masterBotId, 50).catch(() => ({ definitions: [] })),
        listMasterBotExports(masterBotId, 50).catch(() => ({ exports: [] })),
        listMasterBotPacks(masterBotId, 50).catch(() => ({ packs: [] })),
      ]);
      setRevisions(d.definitions || []);
      setExports(e.exports || []);
      setPacks(p.packs || []);
    } catch (e) { setError(e.message || 'failed to load compile state'); }
    finally { setLoading(false); }
  }, [masterBotId]);

  useEffect(() => { refresh(); }, [refresh]);

  const latestRev = revisions[0] || null;
  const latestExport = exports[0] || null;
  const latestPack = packs[0] || null;

  const handleCompile = async () => {
    setBusy('compile'); setError(null); setInfo(null);
    try {
      const r = await compileMasterBot(masterBotId, { runtime_mode: mode });
      setInfo(`Compiled rev ${r.rev}  ·  ${(r.definition_hash || '').slice(7, 23)}…`);
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(null); }
  };

  const handleExport = async () => {
    setBusy('export'); setError(null); setInfo(null);
    try {
      const r = await exportMasterBotCs(masterBotId, {});
      setInfo(`Exported ${r.filename_cs}  ·  ${(r.sha256_cs || '').slice(7, 23)}…`);
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(null); }
  };

  const handlePack = async () => {
    setBusy('pack'); setError(null); setInfo(null);
    try {
      const r = await buildMasterBotPack(masterBotId, {});
      setInfo(`Packed ${r.filename}  ·  ${r.size_bytes} bytes  ·  ${(r.sha256 || '').slice(7, 23)}…`);
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(null); }
  };

  const downloadCs = (exp) => downloadAuthed(
    downloadMasterBotExportUrl(exp.export_id, 'cs'), exp.filename_cs,
  ).catch((e) => setError(e.message));
  const downloadMeta = (exp) => downloadAuthed(
    downloadMasterBotExportUrl(exp.export_id, 'meta'), exp.filename_meta,
  ).catch((e) => setError(e.message));
  const downloadPack = (p) => downloadAuthed(
    downloadMasterBotPackUrl(p.pack_id), p.filename,
  ).catch((e) => setError(e.message));

  if (!masterBotId) return null;

  return (
    <div data-testid="mb-compile-panel" className="asf-section asf-u2-panel bg-surface-card border border-zinc-800 rounded-lg p-4 space-y-3">
      <div className="asf-section__hd flex items-center justify-between flex-wrap gap-2">
        <div className="asf-legacy-title flex items-center gap-2">
          <Code size={16} weight="duotone" className="text-accent-primary" />
          <h3 className="text-sm font-heading font-bold text-white">Compile · Export · Pack</h3>
          <span className="text-[10px] font-mono text-zinc-500">MB-4 / MB-7 / MB-8</span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <button data-testid="mb-compile-refresh" onClick={refresh}
                  className="p-1.5 border border-zinc-700 rounded text-zinc-400 hover:text-white hover:border-accent-primary"
                  title="Refresh"><ArrowsClockwise size={12} /></button>
          <button data-testid="mb-diff-open" onClick={() => setDiffOpen(true)}
                  disabled={revisions.length === 0}
                  className="px-2.5 py-1.5 text-xs font-mono border border-zinc-700 text-zinc-300 hover:text-white hover:border-accent-primary rounded flex items-center gap-1.5 disabled:opacity-50">
            <GitDiff size={12} /> Diff
          </button>
        </div>
      </div>

      {error && (
        <AsfEmptyState
          slug="mb-compile-error"
          testId="mb-compile-error"
          title="Compile error"
          body={error}
          action={{ label: 'Dismiss', onClick: () => setError(null), testId: 'mb-compile-error-dismiss' }}
        />
      )}
      {info && (
        <div data-testid="mb-compile-info" className="bg-emerald-500/10 border border-emerald-500/40 rounded px-3 py-2 text-[11px] font-mono text-emerald-200 flex items-center justify-between">
          <span>{info}</span>
          <button onClick={() => setInfo(null)} className="text-emerald-300 hover:text-white"><X size={12} /></button>
        </div>
      )}

      {/* Actions */}
      {isAdmin && (
        <div className="flex flex-wrap items-end gap-3 pb-3 border-b border-zinc-800">
          <div className="flex flex-col gap-1">
            <label className="text-[9px] font-mono uppercase text-zinc-500">Runtime mode</label>
            <select data-testid="mb-mode-select" value={mode} onChange={(e) => setMode(e.target.value)}
                    className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono min-w-[220px]">
              {RUNTIME_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
          <button data-testid="mb-compile-btn" onClick={handleCompile} disabled={busy != null}
                  className="px-3 py-1.5 text-xs font-mono text-accent-primary border border-accent-primary/40 hover:bg-accent-primary/10 rounded font-bold flex items-center gap-1.5 disabled:opacity-50">
            {busy === 'compile' ? <Spinner size={12} className="animate-spin" /> : <Code size={12} weight="bold" />}
            Compile Revision
          </button>
          <button data-testid="mb-export-btn" onClick={handleExport} disabled={busy != null || revisions.length === 0}
                  title={revisions.length === 0 ? 'Compile a revision first' : 'Export latest revision to .cs + JSON sidecar'}
                  className="px-3 py-1.5 text-xs font-mono text-[#061812] bg-accent-primary hover:bg-accent-primary-dim rounded font-bold flex items-center gap-1.5 disabled:opacity-50">
            {busy === 'export' ? <Spinner size={12} className="animate-spin" /> : <FileText size={12} weight="bold" />}
            Export .cs
          </button>
          <button data-testid="mb-pack-btn" onClick={handlePack} disabled={busy != null || revisions.length === 0}
                  title={revisions.length === 0 ? 'Compile a revision first' : 'Build .cbotpack from latest export'}
                  className="px-3 py-1.5 text-xs font-mono text-amber-200 border border-amber-500/40 hover:bg-amber-500/10 rounded font-bold flex items-center gap-1.5 disabled:opacity-50">
            {busy === 'pack' ? <Spinner size={12} className="animate-spin" /> : <Package size={12} weight="bold" />}
            Build .cbotpack
          </button>
        </div>
      )}

      {/* Latest snapshots */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Revisions */}
        <div data-testid="mb-revisions-card" className="border border-zinc-800 rounded-md p-3 bg-zinc-900/30 flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">Revisions</span>
            <StatusPill label={`${revisions.length}`} tone={revisions.length ? 'green' : 'zinc'} testId="mb-revisions-count" />
          </div>
          {loading && <Spinner size={14} className="animate-spin text-zinc-500" />}
          {!loading && revisions.length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">No revisions yet. Click Compile to create rev 1.</div>}
          {!loading && latestRev && (
            <div className="text-[11px] font-mono">
              <div className="text-zinc-200">rev <span className="text-accent-primary font-bold">{latestRev.rev}</span></div>
              <div className="text-zinc-500 text-[10px]">{(latestRev.definition_hash || '').slice(7, 23)}…</div>
              <div className="text-zinc-500 text-[10px] mt-1">{fmtDate(latestRev.compiled_at)}</div>
              <div className="text-zinc-500 text-[10px] mt-1">by {latestRev.compiled_by}</div>
            </div>
          )}
        </div>

        {/* Exports */}
        <div data-testid="mb-exports-card" className="border border-zinc-800 rounded-md p-3 bg-zinc-900/30 flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">Exports (.cs)</span>
            <StatusPill label={`${exports.length}`} tone={exports.length ? 'green' : 'zinc'} testId="mb-exports-count" />
          </div>
          {!loading && exports.length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">No exports yet.</div>}
          {!loading && latestExport && (
            <div className="text-[11px] font-mono">
              <div className="text-zinc-200 truncate" title={latestExport.filename_cs}>{latestExport.filename_cs}</div>
              <div className="text-zinc-500 text-[10px]">{(latestExport.sha256_cs || '').slice(7, 23)}…</div>
              <div className="text-zinc-500 text-[10px] mt-1">{fmtDate(latestExport.created_at)}</div>
              <div className="flex items-center gap-2 mt-2">
                <button data-testid="mb-download-cs-btn" onClick={() => downloadCs(latestExport)}
                        className="text-[10px] font-mono text-accent-primary hover:underline flex items-center gap-1">
                  <Download size={11} /> .cs
                </button>
                <button data-testid="mb-download-meta-btn" onClick={() => downloadMeta(latestExport)}
                        className="text-[10px] font-mono text-accent-primary hover:underline flex items-center gap-1">
                  <Download size={11} /> .json
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Packs */}
        <div data-testid="mb-packs-card" className="border border-zinc-800 rounded-md p-3 bg-zinc-900/30 flex flex-col">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">cBot Packs</span>
            <StatusPill label={`${packs.length}`} tone={packs.length ? 'green' : 'zinc'} testId="mb-packs-count" />
          </div>
          {!loading && packs.length === 0 && <div className="text-[10px] font-mono text-zinc-600 italic">No packs yet.</div>}
          {!loading && latestPack && (
            <div className="text-[11px] font-mono">
              <div className="text-zinc-200 truncate" title={latestPack.filename}>{latestPack.filename}</div>
              <div className="text-zinc-500 text-[10px]">{(latestPack.sha256 || '').slice(7, 23)}… · {latestPack.size_bytes} B</div>
              <div className="text-zinc-500 text-[10px] mt-1">{fmtDate(latestPack.created_at)}</div>
              <div className="flex items-center gap-2 mt-2">
                <button data-testid="mb-download-pack-btn" onClick={() => downloadPack(latestPack)}
                        className="text-[10px] font-mono text-accent-primary hover:underline flex items-center gap-1">
                  <Download size={11} /> .cbotpack
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <RevisionDiffModal open={diffOpen} onClose={() => setDiffOpen(false)}
                         masterBotId={masterBotId} revisions={revisions} />
    </div>
  );
}
