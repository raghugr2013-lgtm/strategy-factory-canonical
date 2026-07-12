import React, { useCallback, useEffect, useState } from 'react';
import { AsfEmptyState } from './ui-asf';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TIER_TONE = {
  core:        { dot: 'bg-emerald-400', text: 'text-emerald-300', border: 'border-emerald-500/40' },
  secondary:   { dot: 'bg-amber-400',   text: 'text-amber-300',   border: 'border-amber-500/40' },
  exploratory: { dot: 'bg-sky-400',     text: 'text-sky-300',     border: 'border-sky-500/40' },
};

async function _safeJson(res) {
  const raw = await res.text().catch(() => '');
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

/**
 * Phase 23 — Adaptive Environment Priority Panel.
 *
 * Collapsible section embedded inside the Orchestrator Panel. Shows
 * per-environment adaptive multipliers + lets the operator edit tier
 * weights, knobs, and pause/reset adaptation.
 *
 * Endpoints:
 *   GET  /api/orchestrator/env-priority/config
 *   POST /api/orchestrator/env-priority/config
 *   GET  /api/orchestrator/env-priority/stats
 *   POST /api/orchestrator/env-priority/sample
 *   POST /api/orchestrator/env-priority/reset
 */
export default function EnvPriorityPanel() {
  const [open, setOpen] = useState(false);
  const [cfg, setCfg] = useState(null);
  const [stats, setStats] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(null);   // editable copy of cfg
  const [savedAt, setSavedAt] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/env-priority/stats`);
      const d = await _safeJson(res);
      if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
      setCfg(d.config);
      setStats(d.envs || []);
      setError(null);
      // Hydrate draft once on first load.
      setDraft((curr) => curr || cloneCfg(d.config));
    } catch (e) {
      setError(e.message || 'failed to load env priority');
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!open) return;
    const id = setInterval(refresh, 7000);
    return () => clearInterval(id);
  }, [open, refresh]);

  const saveConfig = async () => {
    if (!draft) return;
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/env-priority/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tiers: draft.tiers,
          knobs: draft.knobs,
        }),
      });
      const d = await _safeJson(res);
      if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
      setCfg(d);
      setDraft(cloneCfg(d));
      setSavedAt(new Date().toISOString());
      await refresh();
    } catch (e) {
      setError(e.message || 'save failed');
    } finally {
      setBusy(false);
    }
  };

  const toggleAdaptation = async () => {
    if (!draft) return;
    const newDraft = cloneCfg(draft);
    newDraft.knobs.adaptation_enabled = !newDraft.knobs.adaptation_enabled;
    setDraft(newDraft);
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/env-priority/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ knobs: { adaptation_enabled: newDraft.knobs.adaptation_enabled } }),
      });
      const d = await _safeJson(res);
      if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
      await refresh();
    } catch (e) {
      setError(e.message || 'toggle failed');
    } finally {
      setBusy(false);
    }
  };

  const resetMultipliers = async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/env-priority/reset`, {
        method: 'POST',
      });
      const d = await _safeJson(res);
      if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
      await refresh();
    } catch (e) {
      setError(e.message || 'reset failed');
    } finally {
      setBusy(false);
    }
  };

  if (!cfg || !draft) {
    return null;
  }

  const tierWeights = draft.tiers;
  const tierSum = Object.values(tierWeights).reduce(
    (s, t) => s + Number(t.weight || 0), 0,
  );
  const dirty = JSON.stringify(draft) !== JSON.stringify(cloneCfg(cfg));

  return (
    <div
      data-testid="env-priority-panel"
      className="asf-section asf-u2-panel border-t border-zinc-700/40 mt-4 pt-3"
    >
      <button
        type="button"
        data-testid="env-priority-toggle"
        onClick={() => setOpen((o) => !o)}
        className="asf-section__hd w-full flex items-center justify-between gap-2 text-left group"
      >
        <span className="asf-legacy-title flex items-center gap-2">
          <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 group-hover:text-zinc-300">
            Environment Priority
          </span>
          <span
            data-testid="env-priority-adaptation-state"
            className={
              'text-[9px] font-mono px-1.5 py-0.5 rounded-full border ' +
              (cfg.knobs.adaptation_enabled
                ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
                : 'border-zinc-600 text-zinc-400 bg-zinc-800/40')
            }
          >
            {cfg.knobs.adaptation_enabled ? 'ADAPTIVE' : 'PAUSED'}
          </span>
          {cfg.knobs.allow_noisy_scans && (
            <span
              data-testid="env-priority-noisy-state"
              className="text-[9px] font-mono px-1.5 py-0.5 rounded-full border border-amber-500/40 text-amber-300 bg-amber-500/10"
            >
              NOISY ON
            </span>
          )}
        </span>
        <span className="text-[10px] text-zinc-500">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="mt-3 space-y-4">
          {error && (
            <AsfEmptyState
              slug="env-priority-error"
              testId="env-priority-error"
              title="Environment priority error"
              body={error}
            />
          )}

          {/* ── Knob row ─────────────────────────────────── */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="env-priority-toggle-adaptation"
              onClick={toggleAdaptation}
              disabled={busy}
              className={
                'text-[11px] font-mono px-2.5 py-1 rounded border transition-colors disabled:opacity-50 ' +
                (cfg.knobs.adaptation_enabled
                  ? 'border-zinc-600 text-zinc-300 bg-zinc-800/40 hover:bg-zinc-700/40'
                  : 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20')
              }
            >
              {cfg.knobs.adaptation_enabled ? 'Pause Adaptation' : 'Resume Adaptation'}
            </button>
            <button
              type="button"
              data-testid="env-priority-reset"
              onClick={resetMultipliers}
              disabled={busy}
              className="text-[11px] font-mono px-2.5 py-1 rounded border border-amber-500/40 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 disabled:opacity-50"
            >
              Reset Multipliers
            </button>
            <label className="flex items-center gap-2 text-[11px] font-mono text-zinc-400 ml-2">
              <input
                type="checkbox"
                data-testid="env-priority-noisy-toggle"
                checked={!!draft.knobs.allow_noisy_scans}
                onChange={(e) => setDraft({
                  ...draft,
                  knobs: { ...draft.knobs, allow_noisy_scans: e.target.checked },
                })}
                className="w-3 h-3 accent-amber-400"
              />
              Allow noisy scans (1m + crypto brute-force)
            </label>
          </div>

          {/* ── Tier editor ──────────────────────────────── */}
          <div className="space-y-2">
            {['core', 'secondary', 'exploratory'].map((tname) => (
              <TierEditor
                key={tname}
                name={tname}
                tier={draft.tiers[tname]}
                tierSum={tierSum}
                onChange={(patch) => setDraft({
                  ...draft,
                  tiers: {
                    ...draft.tiers,
                    [tname]: { ...draft.tiers[tname], ...patch },
                  },
                })}
              />
            ))}
          </div>

          {/* ── Knob row #2 ──────────────────────────────── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KnobInput
              label="Exploratory floor"
              hint="min share reserved for exploratory tier"
              testId="env-priority-knob-floor"
              value={draft.knobs.exploratory_floor}
              min={0} max={0.5} step={0.01}
              onChange={(v) => setDraft({ ...draft, knobs: { ...draft.knobs, exploratory_floor: v } })}
            />
            <KnobInput
              label="Max env share"
              hint="anti-runaway cap per environment"
              testId="env-priority-knob-cap"
              value={draft.knobs.max_env_share}
              min={0.1} max={1} step={0.05}
              onChange={(v) => setDraft({ ...draft, knobs: { ...draft.knobs, max_env_share: v } })}
            />
            <KnobInput
              label="EMA α"
              hint="adaptation strength (lower = slower)"
              testId="env-priority-knob-alpha"
              value={draft.knobs.ema_alpha}
              min={0.01} max={0.9} step={0.01}
              onChange={(v) => setDraft({ ...draft, knobs: { ...draft.knobs, ema_alpha: v } })}
            />
            <KnobInput
              label="Decay rate"
              hint="per-tick pull of idle envs back to neutral"
              testId="env-priority-knob-decay"
              value={draft.knobs.decay_rate}
              min={0} max={0.5} step={0.005}
              onChange={(v) => setDraft({ ...draft, knobs: { ...draft.knobs, decay_rate: v } })}
            />
          </div>

          {/* ── Save row ─────────────────────────────────── */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-mono text-zinc-500">
              Tier weight sum: {tierSum.toFixed(2)} {tierSum <= 0 && (
                <span className="text-red-300 ml-1">(must be &gt; 0)</span>
              )}
              {savedAt && <span className="ml-2 text-emerald-400/70">saved {fmtRel(savedAt)}</span>}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                data-testid="env-priority-revert"
                onClick={() => setDraft(cloneCfg(cfg))}
                disabled={!dirty || busy}
                className="text-[11px] font-mono px-2.5 py-1 rounded border border-zinc-600 text-zinc-400 bg-zinc-800/40 disabled:opacity-30 hover:bg-zinc-700/40"
              >
                Revert
              </button>
              <button
                type="button"
                data-testid="env-priority-save"
                onClick={saveConfig}
                disabled={!dirty || busy || tierSum <= 0}
                className="text-[11px] font-mono px-3 py-1 rounded border border-accent-primary/40 text-accent-primary bg-accent-primary/10 hover:bg-accent-primary/20 disabled:opacity-30"
              >
                {busy ? 'Saving…' : 'Save Config'}
              </button>
            </div>
          </div>

          {/* ── Stats table ──────────────────────────────── */}
          <EnvStatsTable rows={stats} />
        </div>
      )}
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────

function cloneCfg(c) {
  return c ? JSON.parse(JSON.stringify(c)) : null;
}

function fmtRel(iso) {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 5_000) return 'just now';
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
  if (ms < 3_600_000) return `${Math.round(ms / 60000)}m ago`;
  return `${Math.round(ms / 3_600_000)}h ago`;
}

function fmtTs(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function clamp(v, min, max) {
  if (Number.isNaN(v)) return min;
  return Math.max(min, Math.min(max, v));
}

// ─── Sub-components ───────────────────────────────────────────────

function TierEditor({ name, tier, tierSum, onChange }) {
  if (!tier) return null;
  const tone = TIER_TONE[name] || TIER_TONE.core;
  const sharePct = tierSum > 0 ? (tier.weight / tierSum) * 100 : 0;
  return (
    <div
      data-testid={`env-tier-${name}`}
      className={`rounded border ${tone.border} bg-zinc-900/30 p-2`}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${tone.dot}`} />
          <span className={`text-[11px] font-mono uppercase tracking-wider ${tone.text}`}>
            {name}
          </span>
          <span className="text-[10px] font-mono text-zinc-500">
            {(tier.pairs || []).length} pair × {(tier.timeframes || []).length} tf
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number" step={0.05} min={0} max={1}
            data-testid={`env-tier-${name}-weight`}
            value={tier.weight}
            onChange={(e) => onChange({ weight: clamp(parseFloat(e.target.value), 0, 1) })}
            className="w-16 bg-zinc-950/40 border border-zinc-700 rounded px-1.5 py-0.5 text-[11px] font-mono text-zinc-200 focus:outline-none focus:border-zinc-500"
          />
          <span className="text-[10px] font-mono text-zinc-500 w-14 text-right">
            {sharePct.toFixed(0)}% base
          </span>
        </div>
      </div>
      <CsvField
        label="Pairs"
        testId={`env-tier-${name}-pairs`}
        value={(tier.pairs || []).join(', ')}
        onChange={(arr) => onChange({ pairs: arr.map((s) => s.toUpperCase()) })}
      />
      <CsvField
        label="Timeframes"
        testId={`env-tier-${name}-timeframes`}
        value={(tier.timeframes || []).join(', ')}
        onChange={(arr) => onChange({ timeframes: arr.map((s) => s.toLowerCase()) })}
      />
    </div>
  );
}

function CsvField({ label, value, onChange, testId }) {
  return (
    <div className="flex items-center gap-2 mb-1">
      <label className="w-20 text-[10px] font-mono uppercase tracking-wider text-zinc-500">
        {label}
      </label>
      <input
        type="text"
        data-testid={testId}
        value={value}
        onChange={(e) => onChange(
          e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
        )}
        className="flex-1 bg-zinc-950/40 border border-zinc-700 rounded px-2 py-1 text-[11px] font-mono text-zinc-200 focus:outline-none focus:border-zinc-500"
      />
    </div>
  );
}

function KnobInput({ label, hint, value, min, max, step, onChange, testId }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      <input
        type="number"
        data-testid={testId}
        value={value}
        min={min} max={max} step={step}
        onChange={(e) => onChange(clamp(parseFloat(e.target.value), min, max))}
        className="bg-zinc-950/40 border border-zinc-700 rounded px-1.5 py-0.5 text-[11px] font-mono text-zinc-200 focus:outline-none focus:border-zinc-500"
      />
      <span className="text-[9px] font-mono text-zinc-600 mt-0.5">{hint}</span>
    </div>
  );
}

function EnvStatsTable({ rows }) {
  const sorted = [...(rows || [])].sort(
    (a, b) => (b.allocation || 0) - (a.allocation || 0),
  );
  return (
    <div
      data-testid="env-priority-stats-table"
      className="border border-zinc-700/40 rounded overflow-hidden"
    >
      <div className="grid grid-cols-12 gap-2 px-2 py-1.5 text-[9px] font-mono uppercase tracking-wider text-zinc-500 bg-zinc-900/40 border-b border-zinc-700/40">
        <div className="col-span-2">Env</div>
        <div className="col-span-1">Tier</div>
        <div className="col-span-2">Allocation</div>
        <div className="col-span-1">Mult</div>
        <div className="col-span-1">Score</div>
        <div className="col-span-1">PF</div>
        <div className="col-span-1">Surv</div>
        <div className="col-span-1">OOS</div>
        <div className="col-span-1">DD</div>
        <div className="col-span-1">Last</div>
      </div>
      {sorted.length === 0 && (
        <div className="px-2 py-3 text-[10px] font-mono text-zinc-500">No environments configured.</div>
      )}
      {sorted.map((r) => {
        const tone = TIER_TONE[r.tier] || TIER_TONE.core;
        const allocPct = (r.allocation || 0) * 100;
        const m = r.metrics || {};
        return (
          <div
            key={r.key}
            data-testid={`env-stat-${r.pair}-${r.timeframe}`}
            className="grid grid-cols-12 gap-2 px-2 py-1.5 text-[10px] font-mono items-center border-b border-zinc-800/60 last:border-b-0 hover:bg-zinc-800/30"
          >
            <div className="col-span-2 flex items-center gap-1.5 text-zinc-200 truncate">
              <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
              <span>{r.pair}</span>
              <span className="text-zinc-500">·</span>
              <span className="text-zinc-300">{r.timeframe}</span>
              {r.noisy && (
                <span className="text-[8px] px-1 rounded border border-amber-500/40 text-amber-300 bg-amber-500/10">
                  NOISY
                </span>
              )}
            </div>
            <div className={`col-span-1 ${tone.text} truncate`}>{r.tier}</div>
            <div className="col-span-2">
              <div className="flex items-center gap-1.5">
                <div className="flex-1 h-1.5 bg-zinc-800 rounded overflow-hidden">
                  <div
                    className={`h-full ${tone.dot}`}
                    style={{ width: `${Math.max(0, Math.min(100, allocPct))}%` }}
                  />
                </div>
                <span className="text-zinc-300 w-10 text-right">{allocPct.toFixed(1)}%</span>
              </div>
            </div>
            <div className={`col-span-1 ${r.multiplier > 1.05 ? 'text-emerald-300' : r.multiplier < 0.95 ? 'text-red-300' : 'text-zinc-300'}`}>
              ×{Number(r.multiplier).toFixed(2)}
            </div>
            <div className="col-span-1 text-zinc-300">
              {r.score_ema != null ? Number(r.score_ema).toFixed(2) : '—'}
            </div>
            <div className="col-span-1 text-zinc-400">{m.pf_ema != null ? Number(m.pf_ema).toFixed(2) : '—'}</div>
            <div className="col-span-1 text-zinc-400">{m.survivors_ema != null ? Number(m.survivors_ema).toFixed(1) : '—'}</div>
            <div className="col-span-1 text-zinc-400">{m.oos_pf_ema != null ? Number(m.oos_pf_ema).toFixed(2) : '—'}</div>
            <div className="col-span-1 text-zinc-400">{m.dd_ema != null ? `${(Number(m.dd_ema) * 100).toFixed(0)}%` : '—'}</div>
            <div className="col-span-1 text-zinc-500 truncate" title={r.last_used_at || ''}>
              {fmtTs(r.last_used_at)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
