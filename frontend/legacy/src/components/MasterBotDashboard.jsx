import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Robot, Plus, Trash, Pencil, ArrowUp, ArrowDown,
  Eye, EyeSlash, Sparkle, ArrowsClockwise, Spinner,
  Stack, Crown, Star, ShieldCheck, X,
} from '@phosphor-icons/react';
import MasterBotCompilePanel from './MasterBotCompilePanel';
import {
  listMasterBots, createMasterBot, getMasterBot, renameMasterBot,
  deleteMasterBot, getMasterBotCandidates, getMasterBotRankerConfig,
  setMasterBotRankerConfig, addMasterBotMember, removeMasterBotMember,
  setMasterBotMemberEnabled, promoteMasterBotMember, demoteMasterBotMember,
  autoFillMasterBot,
} from '../services/api';
import { AsfEmptyState } from './ui-asf';

/**
 * Master Bot Dashboard — MB-3.
 *
 * Three columns: Tier 1 / Tier 2 / Tier 3.
 * Per-row controls: enable / disable, promote, demote, remove.
 * Side panel: Candidate Pool (auto-fill or add individual).
 * Top bar: bot selector + create + rename + delete + ranker weights.
 *
 * Talks to /api/master-bot/* (engines/master_bot_engine.py
 *                              engines/master_bot_ranker.py).
 */

const TIER_META = {
  tier1: { label: 'Tier 1 — Primary',       icon: Crown,     accent: 'text-amber-300', ring: 'border-amber-500/40 bg-amber-500/5' },
  tier2: { label: 'Tier 2 — Secondary',     icon: Star,      accent: 'text-sky-300',   ring: 'border-sky-500/40 bg-sky-500/5' },
  tier3: { label: 'Tier 3 — Probationary',  icon: ShieldCheck, accent: 'text-zinc-300', ring: 'border-zinc-500/40 bg-zinc-500/5' },
};
const TIER_KEYS = ['tier1', 'tier2', 'tier3'];

function fmt(n, d = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return typeof n === 'number' ? n.toFixed(d) : String(n);
}

function fmtPct(n, d = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${(typeof n === 'number' ? n : Number(n)).toFixed(d)}%`;
}

function StatusPill({ label, tone = 'zinc', testId }) {
  const tones = {
    green:  'bg-emerald-500/10 border-emerald-500/40 text-emerald-300',
    red:    'bg-red-500/10 border-red-500/40 text-red-300',
    amber:  'bg-amber-500/10 border-amber-500/40 text-amber-300',
    sky:    'bg-sky-500/10 border-sky-500/40 text-sky-300',
    zinc:   'bg-zinc-700/40 border-zinc-600/60 text-zinc-300',
  };
  return (
    <span data-testid={testId} className={`text-[9px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border ${tones[tone]}`}>
      {label}
    </span>
  );
}

// ─── Create-bot modal ────────────────────────────────────────────────
function CreateBotModal({ open, onClose, onCreated }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { if (open) { setName(''); setDescription(''); setError(null); } }, [open]);

  if (!open) return null;
  const submit = async (e) => {
    e?.preventDefault?.();
    if (!name.trim()) { setError('name required'); return; }
    setBusy(true); setError(null);
    try {
      const bot = await createMasterBot({ name: name.trim(), description });
      onCreated(bot);
      onClose();
    } catch (err) {
      setError(err.message || 'create failed');
    } finally { setBusy(false); }
  };
  return (
    <div data-testid="mb-create-modal" className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <form onSubmit={submit} className="w-[440px] max-w-[95vw] bg-surface-card border border-zinc-700 rounded-md p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-heading font-bold text-white">Create Master Bot</h3>
          <button type="button" data-testid="mb-create-close" onClick={onClose} className="text-zinc-400 hover:text-zinc-200"><X size={16} /></button>
        </div>
        <label className="block text-[10px] font-mono uppercase text-zinc-400 mb-1">Name</label>
        <input
          data-testid="mb-create-name"
          value={name} onChange={(e) => setName(e.target.value)}
          className="w-full bg-surface-elevated border border-zinc-700 rounded px-2 py-1.5 text-xs text-white focus:border-accent-primary focus:outline-none"
          placeholder="MB_2026Q1_EURGBPUSDJPY" maxLength={120} autoFocus
        />
        <label className="block text-[10px] font-mono uppercase text-zinc-400 mt-3 mb-1">Description</label>
        <textarea
          data-testid="mb-create-desc"
          value={description} onChange={(e) => setDescription(e.target.value)}
          rows={2} maxLength={500}
          className="w-full bg-surface-elevated border border-zinc-700 rounded px-2 py-1.5 text-xs text-white focus:border-accent-primary focus:outline-none"
        />
        {error && <div data-testid="mb-create-error" className="mt-3 text-[10px] font-mono text-red-300">{error}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-xs font-mono text-zinc-300 hover:text-white border border-zinc-700 hover:border-zinc-500 rounded">Cancel</button>
          <button data-testid="mb-create-submit" type="submit" disabled={busy} className="px-3 py-1.5 text-xs font-mono text-[#061812] bg-accent-primary hover:bg-accent-primary-dim rounded font-bold disabled:opacity-50 flex items-center gap-1.5">
            {busy ? <Spinner size={12} className="animate-spin" /> : <Plus size={12} weight="bold" />} Create
          </button>
        </div>
      </form>
    </div>
  );
}

// ─── Member row ──────────────────────────────────────────────────────
function MemberRow({ member, isAdmin, onPromote, onDemote, onToggle, onRemove }) {
  const snap = member.snapshot || {};
  const enabled = !!member.enabled;
  return (
    <div
      data-testid={`mb-member-${member.strategy_hash}`}
      className={`group flex items-center gap-2 px-2 py-1.5 rounded border ${enabled ? 'border-zinc-800 bg-zinc-900/40' : 'border-zinc-800/60 bg-zinc-900/20 opacity-60'} hover:border-accent-primary/40 transition-colors`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-zinc-200 truncate">
          <span className="truncate" title={member.strategy_hash}>{(member.strategy_hash || '').slice(0, 18)}</span>
          {!enabled && <StatusPill label="OFF" tone="zinc" />}
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-[9px] font-mono text-zinc-500">
          <span className="text-zinc-400">{snap.pair || '—'}</span>
          <span>{snap.timeframe || '—'}</span>
          <span className="text-zinc-600">·</span>
          <span>{snap.style || 'mixed'}</span>
        </div>
      </div>
      <div className="flex flex-col items-end text-right shrink-0 min-w-[88px]">
        <div className="text-[10px] font-mono text-zinc-300">
          PF <span className="text-zinc-100">{fmt(snap.profit_factor)}</span>
        </div>
        <div className="text-[9px] font-mono text-zinc-500">
          WR {fmtPct(snap.win_rate, 0)} · PP {fmtPct(snap.pass_probability, 0)}
        </div>
      </div>
      {isAdmin && (
        <div className="flex items-center gap-0.5 shrink-0 opacity-70 group-hover:opacity-100 transition-opacity">
          <button data-testid={`mb-promote-${member.strategy_hash}`} title="Promote tier" onClick={onPromote}
                  className="p-1 text-zinc-400 hover:text-amber-300 hover:bg-amber-500/10 rounded"><ArrowUp size={12} weight="bold" /></button>
          <button data-testid={`mb-demote-${member.strategy_hash}`} title="Demote tier" onClick={onDemote}
                  className="p-1 text-zinc-400 hover:text-sky-300 hover:bg-sky-500/10 rounded"><ArrowDown size={12} weight="bold" /></button>
          <button data-testid={`mb-toggle-${member.strategy_hash}`} title={enabled ? 'Disable' : 'Enable'} onClick={onToggle}
                  className="p-1 text-zinc-400 hover:text-emerald-300 hover:bg-emerald-500/10 rounded">
            {enabled ? <EyeSlash size={12} weight="bold" /> : <Eye size={12} weight="bold" />}
          </button>
          <button data-testid={`mb-remove-${member.strategy_hash}`} title="Remove" onClick={onRemove}
                  className="p-1 text-zinc-400 hover:text-red-300 hover:bg-red-500/10 rounded"><Trash size={12} weight="bold" /></button>
        </div>
      )}
    </div>
  );
}

// ─── Tier column ─────────────────────────────────────────────────────
function TierColumn({ tier, label, allocation, members, isAdmin, onPromote, onDemote, onToggle, onRemove }) {
  const meta = TIER_META[tier];
  const Icon = meta.icon;
  return (
    <div data-testid={`mb-tier-${tier}`} className={`flex-1 min-w-0 flex flex-col border rounded-lg p-3 ${meta.ring}`}>
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Icon size={16} className={meta.accent} weight="duotone" />
          <h4 className={`text-xs font-mono font-bold uppercase tracking-wider ${meta.accent}`}>{label}</h4>
        </div>
        <div className="flex items-center gap-1.5">
          <StatusPill label={`${Math.round((allocation || 0) * 100)}%`} tone="zinc" testId={`mb-alloc-${tier}`} />
          <StatusPill label={`${members.length}`} tone={members.length ? 'green' : 'zinc'} testId={`mb-count-${tier}`} />
        </div>
      </div>
      <div className="flex flex-col gap-1.5 min-h-[80px]" data-testid={`mb-tier-list-${tier}`}>
        {members.length === 0 ? (
          <div className="text-[10px] font-mono text-zinc-600 italic text-center py-6">no strategies yet</div>
        ) : members.map((m) => (
          <MemberRow
            key={m.strategy_hash} member={m} isAdmin={isAdmin}
            onPromote={() => onPromote(m)} onDemote={() => onDemote(m)}
            onToggle={() => onToggle(m)} onRemove={() => onRemove(m)}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Candidate Pool side panel ───────────────────────────────────────
function CandidatePoolPanel({ candidates, loading, isAdmin, onAdd, takenHashes, busyHash }) {
  return (
    <aside data-testid="mb-candidate-pool" className="w-[360px] shrink-0 flex flex-col border border-zinc-800 bg-surface-card/60 rounded-lg p-3">
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Sparkle size={14} weight="duotone" className="text-accent-primary" />
          <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-white">Candidate Pool</h4>
        </div>
        <StatusPill label={`${candidates.length}`} tone="green" testId="mb-pool-count" />
      </div>
      <div className="flex-1 overflow-y-auto flex flex-col gap-1.5 max-h-[600px] pr-1">
        {loading && <div className="text-[10px] font-mono text-zinc-500 text-center py-4 flex items-center justify-center gap-1.5"><Spinner size={12} className="animate-spin" />ranking…</div>}
        {!loading && candidates.length === 0 && (
          <div className="text-[10px] font-mono text-zinc-600 italic text-center py-6">No candidates available. The pool sources from the Survivor Registry (elite+ stages).</div>
        )}
        {!loading && candidates.map((c, i) => {
          const taken = takenHashes.has(c.strategy_hash);
          const busy = busyHash === c.strategy_hash;
          return (
            <div
              key={c.strategy_hash}
              data-testid={`mb-candidate-${c.strategy_hash}`}
              className={`flex items-center gap-2 px-2 py-1.5 rounded border ${taken ? 'border-emerald-700/40 bg-emerald-500/5' : 'border-zinc-800 bg-zinc-900/30'} hover:border-accent-primary/40 transition-colors`}
            >
              <div className="w-5 text-[10px] font-mono text-zinc-500 text-center shrink-0">#{i + 1}</div>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-mono text-zinc-200 truncate" title={c.strategy_hash}>
                  {(c.strategy_hash || '').slice(0, 18)}
                </div>
                <div className="text-[9px] font-mono text-zinc-500 truncate">
                  {c.pair || '—'} · {c.timeframe || '—'} · {c.style || 'mixed'}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-[10px] font-mono text-accent-primary font-bold">{fmt(c.candidate_score, 3)}</div>
                <div className="text-[9px] font-mono text-zinc-500">
                  DS {fmt(c.deploy_score, 0)} · PP {fmt(c.pass_probability, 0)}
                </div>
              </div>
              {isAdmin && (
                taken ? (
                  <StatusPill label="ADDED" tone="green" />
                ) : (
                  <button
                    data-testid={`mb-add-candidate-${c.strategy_hash}`}
                    onClick={() => onAdd(c)}
                    disabled={busy}
                    className="p-1 text-zinc-400 hover:text-accent-primary hover:bg-accent-primary/10 rounded shrink-0 disabled:opacity-50"
                    title="Add to Tier 3"
                  >
                    {busy ? <Spinner size={12} className="animate-spin" /> : <Plus size={12} weight="bold" />}
                  </button>
                )
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}

// ─── Main component ─────────────────────────────────────────────────
export default function MasterBotDashboard({ isAdmin }) {
  const [bots, setBots]                 = useState([]);
  const [selectedId, setSelectedId]     = useState(null);
  const [selectedBot, setSelectedBot]   = useState(null);
  const [candidates, setCandidates]     = useState([]);
  const [rankerCfg, setRankerCfg]       = useState(null);
  const [loadingBots, setLoadingBots]   = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingPool, setLoadingPool]   = useState(false);
  const [error, setError]               = useState(null);
  const [createOpen, setCreateOpen]     = useState(false);
  const [busyAddHash, setBusyAddHash]   = useState(null);
  const [autoFillBusy, setAutoFillBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [renameInput, setRenameInput]   = useState('');

  // ── Data fetchers ─────────────────────────────────────────────
  const refreshBots = useCallback(async () => {
    setLoadingBots(true); setError(null);
    try {
      const data = await listMasterBots({ limit: 100 });
      const list = data.master_bots || [];
      setBots(list);
      if (list.length && !selectedId) setSelectedId(list[0].id);
      if (selectedId && !list.find((b) => b.id === selectedId)) {
        setSelectedId(list[0]?.id || null);
      }
    } catch (e) { setError(e.message || 'failed to list bots'); }
    finally { setLoadingBots(false); }
  }, [selectedId]);

  const refreshDetail = useCallback(async (id) => {
    if (!id) { setSelectedBot(null); return; }
    setLoadingDetail(true); setError(null);
    try {
      const doc = await getMasterBot(id);
      setSelectedBot(doc);
      setRenameInput(doc.name || '');
    } catch (e) { setError(e.message || 'failed to load bot'); setSelectedBot(null); }
    finally { setLoadingDetail(false); }
  }, []);

  const refreshPool = useCallback(async () => {
    setLoadingPool(true);
    try {
      const [pool, cfg] = await Promise.all([
        getMasterBotCandidates(30),
        getMasterBotRankerConfig().catch(() => null),
      ]);
      setCandidates(pool.candidates || []);
      if (cfg) setRankerCfg(cfg);
    } catch (e) { setError(e.message || 'failed to load candidates'); }
    finally { setLoadingPool(false); }
  }, []);

  useEffect(() => { refreshBots(); refreshPool(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (selectedId) refreshDetail(selectedId); }, [selectedId, refreshDetail]);

  // ── Derived ───────────────────────────────────────────────────
  const tierMap = useMemo(() => {
    if (!selectedBot?.members_by_tier) return { tier1: [], tier2: [], tier3: [] };
    return selectedBot.members_by_tier;
  }, [selectedBot]);

  const takenHashes = useMemo(() => {
    const set = new Set();
    Object.values(tierMap).forEach((arr) => arr?.forEach((m) => set.add(m.strategy_hash)));
    return set;
  }, [tierMap]);

  const tierAllocations = useMemo(() => {
    const map = {};
    (selectedBot?.tiers || []).forEach((t) => { map[t.tier_key] = t.allocation_share; });
    return map;
  }, [selectedBot]);

  // ── Actions ───────────────────────────────────────────────────
  const handleCreated = async (bot) => {
    await refreshBots();
    setSelectedId(bot.id);
  };

  const handleAdd = async (c) => {
    if (!selectedId) { setError('Select a Master Bot first'); return; }
    setBusyAddHash(c.strategy_hash);
    try {
      await addMasterBotMember(selectedId, {
        strategy_hash: c.strategy_hash, tier: 'tier3',
        snapshot: {
          pair: c.pair, timeframe: c.timeframe, style: c.style,
          profit_factor: c.profit_factor, win_rate: c.win_rate,
          pass_probability: c.pass_probability, deploy_score: c.deploy_score,
          lifecycle_stage: c.lifecycle_stage, candidate_score: c.candidate_score,
        },
      });
      await refreshDetail(selectedId);
    } catch (e) { setError(e.message); }
    finally { setBusyAddHash(null); }
  };

  const handlePromote = async (m) => {
    try { await promoteMasterBotMember(selectedId, m.strategy_hash); await refreshDetail(selectedId); }
    catch (e) { setError(e.message); }
  };
  const handleDemote = async (m) => {
    try { await demoteMasterBotMember(selectedId, m.strategy_hash); await refreshDetail(selectedId); }
    catch (e) { setError(e.message); }
  };
  const handleToggle = async (m) => {
    try { await setMasterBotMemberEnabled(selectedId, m.strategy_hash, !m.enabled); await refreshDetail(selectedId); }
    catch (e) { setError(e.message); }
  };
  const handleRemove = async (m) => {
    try { await removeMasterBotMember(selectedId, m.strategy_hash); await refreshDetail(selectedId); }
    catch (e) { setError(e.message); }
  };

  const handleAutoFill = async () => {
    if (!selectedId) { setError('Select a Master Bot first'); return; }
    setAutoFillBusy(true); setError(null);
    try {
      await autoFillMasterBot(selectedId, { tier1_count: 3, tier2_count: 7, tier3_count: 15, clear_existing: false });
      await refreshDetail(selectedId);
    } catch (e) { setError(e.message); }
    finally { setAutoFillBusy(false); }
  };

  const handleRename = async () => {
    if (!selectedId || !renameInput.trim() || renameInput === selectedBot?.name) return;
    try {
      await renameMasterBot(selectedId, { name: renameInput.trim() });
      await refreshBots();
      await refreshDetail(selectedId);
    } catch (e) { setError(e.message); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await deleteMasterBot(confirmDelete);
      setConfirmDelete(null);
      setSelectedId(null);
      setSelectedBot(null);
      await refreshBots();
    } catch (e) { setError(e.message); }
  };

  // ── Render ────────────────────────────────────────────────────
  return (
    <div data-testid="master-bot-dashboard" className="asf-section asf-u2-panel flex flex-col gap-4">
      {/* Header */}
      <div className="asf-section__hd flex items-center justify-between bg-surface-card border border-zinc-800 rounded-lg px-4 py-3">
        <div className="asf-legacy-title flex items-center gap-3">
          <Robot size={22} weight="duotone" className="text-accent-primary" />
          <div>
            <h2 className="text-base font-heading font-bold text-white tracking-tight">Master Bot Builder</h2>
            <p className="text-[10px] font-mono text-zinc-500 mt-0.5">Tier 1 / Tier 2 / Tier 3 assembly from Candidate Pool · MB-3</p>
          </div>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <select
            data-testid="mb-selector"
            value={selectedId || ''}
            onChange={(e) => setSelectedId(e.target.value || null)}
            className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1.5 text-xs text-zinc-200 font-mono focus:border-accent-primary focus:outline-none min-w-[200px]"
          >
            <option value="">— select master bot —</option>
            {bots.map((b) => (
              <option key={b.id} value={b.id}>{b.name} · {b.status}</option>
            ))}
          </select>
          <button
            data-testid="mb-refresh-btn"
            onClick={() => { refreshBots(); refreshPool(); if (selectedId) refreshDetail(selectedId); }}
            className="p-1.5 border border-zinc-700 rounded text-zinc-400 hover:text-white hover:border-accent-primary"
            title="Refresh"
          ><ArrowsClockwise size={14} /></button>
          {isAdmin && (
            <button
              data-testid="mb-create-btn"
              onClick={() => setCreateOpen(true)}
              className="px-3 py-1.5 text-xs font-mono text-[#061812] bg-accent-primary hover:bg-accent-primary-dim rounded font-bold flex items-center gap-1.5"
            ><Plus size={12} weight="bold" />New Master Bot</button>
          )}
        </div>
      </div>

      {error && (
        <AsfEmptyState
          slug="mb-error"
          testId="mb-error"
          title="Master Bot error"
          body={error}
          action={{ label: 'Dismiss', onClick: () => setError(null), testId: 'mb-error-dismiss' }}
        />
      )}

      {/* Bot detail header */}
      {selectedBot && (
        <div className="bg-surface-card border border-zinc-800 rounded-lg px-4 py-3 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <Stack size={18} weight="duotone" className="text-zinc-400" />
            {isAdmin ? (
              <input
                data-testid="mb-rename-input"
                value={renameInput}
                onChange={(e) => setRenameInput(e.target.value)}
                onBlur={handleRename}
                onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
                className="bg-transparent border-b border-transparent hover:border-zinc-700 focus:border-accent-primary focus:outline-none text-sm font-heading font-bold text-white px-1 max-w-[400px] min-w-[200px]"
              />
            ) : (
              <div className="text-sm font-heading font-bold text-white">{selectedBot.name}</div>
            )}
            <StatusPill label={selectedBot.status} tone={selectedBot.status === 'DRAFT' ? 'amber' : 'green'} testId="mb-status-pill" />
            <span className="text-[10px] font-mono text-zinc-500" data-testid="mb-owner">owner · {selectedBot.owner}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-[10px] font-mono text-zinc-400 flex items-center gap-2" data-testid="mb-counts">
              <span>T1 · <span className="text-amber-300">{selectedBot.member_counts?.tier1 ?? 0}</span></span>
              <span>T2 · <span className="text-sky-300">{selectedBot.member_counts?.tier2 ?? 0}</span></span>
              <span>T3 · <span className="text-zinc-300">{selectedBot.member_counts?.tier3 ?? 0}</span></span>
              <span className="text-zinc-600">·</span>
              <span>{selectedBot.member_counts?.enabled ?? 0}/{selectedBot.member_counts?.total ?? 0} enabled</span>
            </div>
            {isAdmin && (
              <>
                <button
                  data-testid="mb-autofill-btn"
                  onClick={handleAutoFill} disabled={autoFillBusy}
                  className="px-2.5 py-1.5 text-xs font-mono text-accent-primary border border-accent-primary/40 hover:bg-accent-primary/10 rounded flex items-center gap-1.5 disabled:opacity-50"
                  title="Auto-slot top candidates into tiers"
                >
                  {autoFillBusy ? <Spinner size={12} className="animate-spin" /> : <Sparkle size={12} weight="bold" />}
                  Auto-Fill
                </button>
                <button
                  data-testid="mb-delete-btn"
                  onClick={() => setConfirmDelete(selectedBot.id)}
                  className="p-1.5 border border-red-500/40 text-red-300 hover:bg-red-500/10 rounded"
                  title="Delete master bot"
                ><Trash size={12} /></button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Main grid */}
      {!selectedBot && !loadingBots && (
        <div data-testid="mb-empty-state" className="bg-surface-card border border-zinc-800 border-dashed rounded-lg p-12 text-center">
          <Robot size={32} weight="duotone" className="text-zinc-700 mx-auto mb-3" />
          <p className="text-sm font-mono text-zinc-400 mb-1">No Master Bot selected</p>
          <p className="text-[11px] font-mono text-zinc-600">
            {bots.length === 0
              ? 'Create your first Master Bot to begin assembling tiers from the Candidate Pool.'
              : 'Select an existing Master Bot above.'}
          </p>
        </div>
      )}

      {loadingBots && !selectedBot && (
        <div className="text-center py-8 text-xs font-mono text-zinc-500 flex items-center justify-center gap-2"><Spinner size={14} className="animate-spin" /> loading master bots…</div>
      )}

      {selectedBot && (
        <div className="flex gap-4">
          <div className="flex-1 flex flex-col lg:flex-row gap-3 min-w-0">
            {TIER_KEYS.map((tk) => (
              <TierColumn
                key={tk}
                tier={tk}
                label={TIER_META[tk].label}
                allocation={tierAllocations[tk]}
                members={tierMap[tk] || []}
                isAdmin={isAdmin}
                onPromote={handlePromote}
                onDemote={handleDemote}
                onToggle={handleToggle}
                onRemove={handleRemove}
              />
            ))}
          </div>
          <CandidatePoolPanel
            candidates={candidates}
            loading={loadingPool}
            isAdmin={isAdmin}
            onAdd={handleAdd}
            takenHashes={takenHashes}
            busyHash={busyAddHash}
          />
        </div>
      )}

      {/* Ranker weights summary */}
      {rankerCfg && (
        <div data-testid="mb-ranker-config" className="bg-surface-card border border-zinc-800 rounded-lg px-4 py-2.5 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Sparkle size={14} weight="duotone" className="text-accent-primary" />
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">Ranker</span>
            <span className="text-[10px] font-mono text-zinc-500">{rankerCfg.ranker_version}</span>
          </div>
          <div className="flex items-center gap-3 text-[10px] font-mono">
            {Object.entries(rankerCfg.weights || {}).map(([k, v]) => (
              <span key={k} className={v > 0 ? 'text-accent-primary' : 'text-zinc-600'}>
                {k}={fmt(v, 2)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* MB-4 / MB-7 / MB-8 — Compile · Export · Pack · Diff */}
      {selectedBot && (
        <MasterBotCompilePanel masterBotId={selectedBot.id} isAdmin={isAdmin} />
      )}

      {/* Delete confirm */}
      {confirmDelete && (
        <div data-testid="mb-delete-confirm" className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-[400px] bg-surface-card border border-red-500/40 rounded-md p-5 shadow-2xl">
            <h3 className="text-sm font-heading font-bold text-red-300 mb-2">Delete this Master Bot?</h3>
            <p className="text-[11px] font-mono text-zinc-400 mb-4">This soft-deletes the Master Bot (status → DELETED). Members and tier metadata remain in Mongo for audit.</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(null)} className="px-3 py-1.5 text-xs font-mono text-zinc-300 hover:text-white border border-zinc-700 hover:border-zinc-500 rounded">Cancel</button>
              <button data-testid="mb-delete-confirm-btn" onClick={handleDelete} className="px-3 py-1.5 text-xs font-mono text-white bg-red-500 hover:bg-red-600 rounded font-bold">Delete</button>
            </div>
          </div>
        </div>
      )}

      <CreateBotModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={handleCreated} />
    </div>
  );
}
