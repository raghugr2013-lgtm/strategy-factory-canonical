import React, { useEffect, useState, useMemo } from 'react';
import { Globe, CircleNotch, FloppyDisk, ArrowClockwise } from '@phosphor-icons/react';
import { useMarketUniverse } from '../hooks/useMarketUniverse';
import { AsfEmptyState } from './ui-asf';
import { API_URL } from '../services/api';

// Phase 30.2 · Universe Governance Panel.
//
// Operator decree:
//   • The panel defines the ALLOWED RESEARCH UNIVERSE.
//   • It does NOT force equal allocation — env_priority + orchestrator
//     keep adaptive authority WITHIN the allowed boundary.
//   • Manual `scan=[...]` payloads bypass this layer entirely.
//
// Endpoints:
//   GET  /api/governance/universe          (read, any user)
//   POST /api/governance/universe          (write, admin-only)
//   GET  /api/governance/universe/preview  (effective-intersection diagnostic)
//   GET  /api/market-data                  (dataset inventory for pair list)


const CANON_TFS = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'];
const STYLE_OPTIONS = ['trend-following', 'mean-reversion', 'breakout', 'scalping'];

async function fetchJson(path, opts = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Accept': 'application/json' },
    credentials: 'include',
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}${body ? ' · ' + body.slice(0, 160) : ''}`);
  }
  return res.json();
}

function CheckPill({ label, checked, onToggle, testId, disabled }) {
  return (
    <label
      data-testid={testId}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-[11px] font-mono uppercase tracking-wider cursor-pointer transition-colors ${
        checked
          ? 'bg-cyan-500/15 border-cyan-500/50 text-cyan-200'
          : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-700'
      } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
    >
      <input
        type="checkbox"
        className="accent-cyan-400 w-3 h-3"
        checked={checked}
        disabled={disabled}
        onChange={onToggle}
      />
      {label}
    </label>
  );
}

function NumberField({ label, value, onChange, min, max, step, testId, suffix }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">{label}</span>
      <div className="flex items-center gap-1.5">
        <input
          data-testid={testId}
          type="number"
          min={min} max={max} step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-20 bg-surface-sunken border border-border-subtle text-zinc-100 rounded-md px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-accent-primary/40 focus:border-accent-primary/50 focus:outline-none"
        />
        {suffix && <span className="text-[10px] font-mono text-zinc-500">{suffix}</span>}
      </div>
    </div>
  );
}

export default function UniverseGovernancePanel() {
  // R4 — universe-aware fallback: the registry serves as a richer
  // backstop than the legacy 4-pair literal when the market_data
  // collection is empty.
  const { all: REGISTRY_FALLBACK } = useMarketUniverse();
  const [universe, setUniverse] = useState(null);
  const [preview, setPreview] = useState(null);
  const [availablePairs, setAvailablePairs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saveMsg, setSaveMsg] = useState(null);

  // local edit buffer
  const [pairsSel, setPairsSel] = useState([]);
  const [tfsSel, setTfsSel] = useState([]);
  const [stylesSel, setStylesSel] = useState([]);
  const [floor, setFloor] = useState(5);
  const [maxCells, setMaxCells] = useState(8);
  const [breadth, setBreadth] = useState(0.5);

  const refresh = async () => {
    setError(null);
    try {
      const [u, p, mkt] = await Promise.all([
        fetchJson('/api/governance/universe'),
        fetchJson('/api/governance/universe/preview'),
        fetchJson('/api/market-data').catch(() => ({ datasets: [] })),
      ]);
      setUniverse(u);
      setPreview(p);
      const ds = (mkt.datasets || []).map((d) => d.symbol);
      const uniq = Array.from(new Set(ds)).sort();
      setAvailablePairs(uniq.length ? uniq : REGISTRY_FALLBACK);
      setPairsSel(u.pairs || []);
      setTfsSel(u.timeframes || []);
      setStylesSel(u.styles || []);
      setFloor(u.exploration_floor_pct ?? 5);
      setMaxCells(u.max_active_cells ?? 8);
      setBreadth(u.breadth_vs_depth ?? 0.5);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const dirty = useMemo(() => {
    if (!universe) return false;
    const eq = (a, b) => JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort());
    return !eq(pairsSel, universe.pairs)
      || !eq(tfsSel, universe.timeframes)
      || !eq(stylesSel, universe.styles)
      || Number(floor) !== Number(universe.exploration_floor_pct)
      || Number(maxCells) !== Number(universe.max_active_cells)
      || Number(breadth) !== Number(universe.breadth_vs_depth);
  }, [universe, pairsSel, tfsSel, stylesSel, floor, maxCells, breadth]);

  const toggle = (list, value) => list.includes(value)
    ? list.filter((x) => x !== value)
    : [...list, value];

  const save = async () => {
    setSaveMsg(null);
    setSaving(true);
    setError(null);
    try {
      const fresh = await fetchJson('/api/governance/universe', {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pairs:                 pairsSel,
          timeframes:            tfsSel,
          styles:                stylesSel,
          exploration_floor_pct: Number(floor),
          max_active_cells:      Number(maxCells),
          breadth_vs_depth:      Number(breadth),
        }),
      });
      setUniverse(fresh);
      setSaveMsg('Universe updated · audit row appended.');
      // re-pull preview so the effective-cells grid updates
      const p = await fetchJson('/api/governance/universe/preview');
      setPreview(p);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      data-testid="universe-governance-panel"
      className="asf-section asf-u2-panel card-premium p-4 border border-zinc-800/80 bg-zinc-950/40 mb-4"
    >
      <div className="asf-section__hd flex items-center justify-between mb-3">
        <div className="asf-legacy-title flex items-center gap-2">
          <Globe size={14} weight="fill" className="text-cyan-400" />
          <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-300">
            Universe Governance · Phase 30.2
          </h3>
          <span className="text-[9px] font-mono text-zinc-600 uppercase tracking-wider">
            allowed ecosystem · admin write
          </span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2 text-[10px] font-mono text-zinc-500">
          {loading && <CircleNotch size={11} className="animate-spin" />}
          <button
            data-testid="universe-refresh-btn"
            onClick={refresh}
            disabled={loading}
            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-40"
          >
            <ArrowClockwise size={10} weight="bold" /> refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3">
          <AsfEmptyState
            slug="universe-error"
            testId="universe-error"
            title="Universe failed to load"
            body={error}
            action={{ label: 'Retry', onClick: refresh, testId: 'universe-error-retry' }}
          />
        </div>
      )}
      {saveMsg && (
        <div data-testid="universe-save-msg" className="mb-3 p-2 text-[10px] font-mono text-emerald-300 bg-emerald-950/40 border border-emerald-900/60 rounded">
          {saveMsg}
        </div>
      )}

      {/* Pairs */}
      <div className="mb-3">
        <div className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono mb-2">Pairs</div>
        <div className="flex flex-wrap gap-2" data-testid="universe-pairs-row">
          {availablePairs.map((p) => (
            <CheckPill
              key={p}
              label={p}
              testId={`universe-pair-${p}`}
              checked={pairsSel.includes(p)}
              onToggle={() => setPairsSel(toggle(pairsSel, p))}
            />
          ))}
        </div>
      </div>

      {/* Timeframes */}
      <div className="mb-3">
        <div className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono mb-2">Timeframes</div>
        <div className="flex flex-wrap gap-2" data-testid="universe-tfs-row">
          {CANON_TFS.map((t) => (
            <CheckPill
              key={t}
              label={t}
              testId={`universe-tf-${t}`}
              checked={tfsSel.includes(t)}
              onToggle={() => setTfsSel(toggle(tfsSel, t))}
            />
          ))}
        </div>
      </div>

      {/* Styles */}
      <div className="mb-3">
        <div className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono mb-2">Styles</div>
        <div className="flex flex-wrap gap-2" data-testid="universe-styles-row">
          {STYLE_OPTIONS.map((s) => (
            <CheckPill
              key={s}
              label={s}
              testId={`universe-style-${s}`}
              checked={stylesSel.includes(s)}
              onToggle={() => setStylesSel(toggle(stylesSel, s))}
            />
          ))}
        </div>
      </div>

      {/* Exploration governance */}
      <div className="mb-3 pt-3 border-t border-zinc-800/60">
        <div className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono mb-2">Exploration Governance</div>
        <div className="flex items-end gap-6 flex-wrap">
          <NumberField
            label="Floor"
            value={floor} min={0} max={50} step={1}
            onChange={setFloor}
            testId="universe-floor-input"
            suffix="%"
          />
          <NumberField
            label="Max Active Cells"
            value={maxCells} min={1} max={64} step={1}
            onChange={setMaxCells}
            testId="universe-max-cells-input"
          />
          <div className="flex flex-col gap-1">
            <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">
              Breadth ◄──► Depth ({breadth.toFixed(2)})
            </span>
            <input
              data-testid="universe-breadth-slider"
              type="range" min={0} max={1} step={0.05}
              value={breadth}
              onChange={(e) => setBreadth(Number(e.target.value))}
              className="w-44 accent-cyan-400"
            />
          </div>
        </div>
      </div>

      {/* Effective preview */}
      {preview?.effective && (
        <div className="mb-3 pt-3 border-t border-zinc-800/60">
          <div className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono mb-2">
            Effective cells (intersection preview)
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-[10px] font-mono" data-testid="universe-preview-grid">
            {Object.entries(preview.effective).map(([k, v]) => (
              <div
                key={k}
                data-testid={`universe-preview-${k}`}
                className="flex justify-between items-center px-2 py-1.5 bg-zinc-900/60 border border-zinc-800 rounded"
              >
                <span className="text-zinc-400">{k.replace(/_/g, ' ')}</span>
                <span className={v.kept > 0 ? 'text-cyan-300' : 'text-amber-300'}>
                  {v.kept} / {v.total}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between pt-3 border-t border-zinc-800/60">
        <div className="text-[9px] font-mono text-zinc-600">
          {universe && (
            <>last updated <span className="text-zinc-400">{new Date(universe.updated_at).toLocaleString()}</span> by <span className="text-zinc-400">{universe.updated_by}</span> · audit entries: <span className="text-zinc-400">{(universe.audit_log || []).length}</span></>
          )}
        </div>
        <button
          data-testid="universe-save-btn"
          onClick={save}
          disabled={!dirty || saving}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-30 disabled:cursor-not-allowed rounded transition-colors"
        >
          {saving ? <CircleNotch size={11} className="animate-spin" /> : <FloppyDisk size={11} weight="fill" />}
          {saving ? 'saving…' : 'save universe'}
        </button>
      </div>
    </div>
  );
}
