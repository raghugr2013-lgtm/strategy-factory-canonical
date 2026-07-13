/**
 * DSR-1 · Symbol Registry Panel
 * ----------------------------------------------------------------------------
 * Operator-facing UI for the Dynamic Market Universe registry. Lets an
 * operator register, edit and decree per-symbol metadata for the entire
 * pipeline (Ingestion · Factory · Validation · Marketplace) without code
 * changes.
 *
 * Surface: /c/governance#symbol-registry  (new section, sibling to
 *          Universe Governance and Admin).
 *
 * Backend contract:
 *   GET  /api/latent/market-universe        — list + enum metadata
 *   POST /api/admin/market-universe         — upsert symbol
 *   POST /api/admin/market-universe/{sym}/enable  — toggle enabled
 *   POST /api/admin/market-universe/{sym}/tier    — tier transition
 *   DELETE /api/admin/market-universe       — delete (with force flag)
 *
 * Discipline:
 *   • Live preview before submit (no surprise writes).
 *   • Operator-friendly 6-button asset-class picker (Forex / Metal /
 *     Index / Crypto / CFD / Futures) — sub-class behind a secondary
 *     dropdown.
 *   • 4-bucket eligibility (Ingestion · Factory · Validation ·
 *     Marketplace) compiled down to the 8 granular flags on submit.
 *   • Multi-select execution platforms (cTrader · MT4 · MT5 ·
 *     MatchTrader · TradeLocker · DXTrade).
 *   • Reserved future-phase fields (broker_compatibility, strategy_
 *     compatibility, masterbot_compatibility, marketplace_visibility,
 *     propfirm_eligibility) NOT exposed in the form — stored as empty
 *     dicts by the engine.
 */
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import './SymbolRegistryPanel.css';
import { API_URL } from '../services/api';


/** 6 operator-facing asset-class buckets. Each maps to one or more
 *  fine-grained backend asset_class values. Forex collapses 3 sub-
 *  classes; the rest are 1-to-1. */
const ASSET_BUCKETS = [
  { id: 'forex',   label: 'Forex',   subClasses: ['fx_major', 'fx_cross', 'fx_exotic'], hint: 'EUR/USD · GBP/USD · USD/JPY · exotic crosses' },
  { id: 'metal',   label: 'Metal',   subClasses: ['commodity_metal'],                     hint: 'XAU/USD · XAG/USD · platinum · palladium' },
  { id: 'index',   label: 'Index',   subClasses: ['index'],                                hint: 'US100 · NAS100 · DAX · DJIA · S&P' },
  { id: 'crypto',  label: 'Crypto',  subClasses: ['crypto'],                               hint: 'BTC/USD · ETH/USD · alt-coins' },
  { id: 'cfd',     label: 'CFD',     subClasses: ['cfd'],                                  hint: 'CFD contracts (oil · stocks · commodities)' },
  { id: 'futures', label: 'Futures', subClasses: ['futures'],                              hint: 'futures contracts (FX · index · commodity)' },
];

/** Map fine-grained asset_class → operator bucket id. */
const SUBCLASS_TO_BUCKET = (() => {
  const m = {};
  ASSET_BUCKETS.forEach(b => b.subClasses.forEach(sc => { m[sc] = b.id; }));
  return m;
})();

/** Default sub-class per bucket (used when operator picks the bucket
 *  without expanding the secondary dropdown). */
const DEFAULT_SUBCLASS = Object.fromEntries(
  ASSET_BUCKETS.map(b => [b.id, b.subClasses[0]]),
);

/** 4 operator-facing eligibility buckets compile down to 8 granular flags. */
const ELIG_BUCKETS = [
  { id: 'ingestion',   label: 'Ingestion',   flags: ['ingestion_enabled'],
    hint: 'BI5 + bar ingest schedulers iterate this symbol' },
  { id: 'factory',     label: 'Factory',     flags: ['discovery_enabled', 'mutation_enabled'],
    hint: 'Auto Factory generates + mutates strategies on this symbol' },
  { id: 'validation',  label: 'Validation',  flags: ['validation_enabled', 'certification_enabled'],
    hint: 'Validation suite + BI5 realism certify strategies on this symbol' },
  { id: 'marketplace', label: 'Marketplace', flags: ['marketplace_enabled'],
    hint: 'Phase 15 · public marketplace surfaces strategies on this symbol' },
];

const EXECUTION_PLATFORMS = [
  { id: 'ctrader',    label: 'cTrader'     },
  { id: 'mt4',        label: 'MT4'         },
  { id: 'mt5',        label: 'MT5'         },
  { id: 'matchtrader',label: 'MatchTrader' },
  { id: 'tradelocker',label: 'TradeLocker' },
  { id: 'dxtrade',    label: 'DXTrade'     },
];

const TIERS = ['active', 'candidate', 'dormant', 'experimental', 'regime_activated'];

function emptyDraft() {
  return {
    symbol: '',
    aliases: '',
    broker_class: 'dukascopy',
    display_name: '',
    bucket: 'forex',
    asset_class: DEFAULT_SUBCLASS.forex,
    tier: 'candidate',
    enabled: true,
    pip_size: 0.0001,
    eligibility_buckets: { ingestion: true, factory: false, validation: true, marketplace: false },
    execution_platforms: ['ctrader'],
    calendar_market_type: 'forex',
    notes: '',
  };
}

function bucketsToFlags(buckets) {
  const flags = {};
  ELIG_BUCKETS.forEach(b => {
    const on = !!buckets[b.id];
    b.flags.forEach(f => { flags[f] = on; });
  });
  return flags;
}

function flagsToBuckets(flags = {}) {
  const out = {};
  ELIG_BUCKETS.forEach(b => {
    out[b.id] = b.flags.every(f => !!flags[f]);
  });
  return out;
}

export default function SymbolRegistryPanel() {
  const [draft, setDraft] = useState(emptyDraft());
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState(null);   // flag_active + enums
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [editingSymbol, setEditingSymbol] = useState(null);

  const loadRegistry = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/latent/market-universe?limit=500`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRows(Array.isArray(data.rows) ? data.rows : []);
      setMeta({
        flag_active:         !!data.flag_active,
        tiers:               data.tiers || TIERS,
        asset_classes:       data.asset_classes || [],
        execution_platforms: data.execution_platforms || EXECUTION_PLATFORMS.map(p => p.id),
        eligibility_keys:    data.eligibility_keys || [],
        tier_summary:        data.tier_summary || {},
      });
    } catch (e) {
      setError(e.message || 'load_failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadRegistry(); }, [loadRegistry]);

  // Build the API payload from the current draft. Pure function — no
  // hooks, no closures over state setters. Called by both the live
  // preview pane (via useMemo) and the submit handler.
  const previewPayload = useMemo(() => {
    const aliases = (draft.aliases || '')
      .split(/[,\s]+/).map(a => a.trim()).filter(Boolean);
    return {
      symbol:       (draft.symbol || '').trim().toUpperCase(),
      broker_class: (draft.broker_class || 'unknown').trim(),
      display_name: draft.display_name || draft.symbol,
      asset_class:  draft.asset_class,
      tier:         draft.tier,
      enabled:      !!draft.enabled,
      pip_size:     Number(draft.pip_size) || 0,
      aliases,
      eligibility:  bucketsToFlags(draft.eligibility_buckets),
      execution_platforms: draft.execution_platforms || [],
      calendar:     { market_type: draft.calendar_market_type },
      notes:        draft.notes || null,
      // Reserved future-phase fields — auto-stored as empty containers
      // by the engine so the document shape is uniform across the
      // collection. Surfaced here so operators see the full payload
      // contract before submit.
      broker_compatibility:   {},  // reserved · Phase 14 Auto Valuation
      strategy_compatibility: {},  // reserved · Phase 13 Strategy Dossier
      masterbot_compatibility:{},  // reserved · Phase 14 Master Bot bundling
      marketplace_visibility: {},  // reserved · Phase 15 Marketplace listing rules
      propfirm_eligibility:   {},  // reserved · Phase 14 Dual Scorecards
    };
  }, [draft]);

  const submit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      if (!previewPayload.symbol) throw new Error('symbol is required');
      const res = await fetch(`${API_URL}/api/admin/market-universe`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(previewPayload),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}${body ? ' · ' + body.slice(0, 240) : ''}`);
      }
      const data = await res.json();
      setSuccess(`Saved · ${data?.stored?.symbol} (${data?.stored?.broker_class})`);
      setEditingSymbol(null);
      setDraft(emptyDraft());
      await loadRegistry();
    } catch (e) {
      setError(e.message || 'submit_failed');
    } finally {
      setSubmitting(false);
    }
  }, [previewPayload, loadRegistry]);

  const startEdit = useCallback((row) => {
    const bucket = SUBCLASS_TO_BUCKET[row.asset_class] || 'forex';
    setDraft({
      symbol: row.symbol || '',
      aliases: (row.aliases || []).join(', '),
      broker_class: row.broker_class || 'dukascopy',
      display_name: row.display_name || '',
      bucket,
      asset_class: row.asset_class || DEFAULT_SUBCLASS[bucket],
      tier: row.tier || 'candidate',
      enabled: row.enabled !== false,
      pip_size: row.pip_size ?? 0.0001,
      eligibility_buckets: flagsToBuckets(row.eligibility),
      execution_platforms: row.execution_platforms || [],
      calendar_market_type: (row.calendar?.market_type) || 'forex',
      notes: row.notes || '',
    });
    setEditingSymbol(row.symbol);
    setSuccess(null);
    setError(null);
  }, []);

  return (
    <div className="dsr1-symreg" data-testid="dsr1-symbol-registry-panel">
      {/* Header */}
      <header className="dsr1-symreg__hd">
        <div className="dsr1-symreg__hd-row">
          <span className="dsr1-symreg__badge">DSR-1</span>
          <h2 className="dsr1-symreg__title">Symbol Registry</h2>
          <span className={`dsr1-symreg__flag dsr1-symreg__flag--${meta?.flag_active ? 'on' : 'off'}`}
                data-testid="dsr1-flag-state">
            FLAG · {meta?.flag_active ? 'ON (live)' : 'OFF (legacy fallback)'}
          </span>
          <button
            type="button"
            className="dsr1-symreg__refresh"
            data-testid="dsr1-refresh"
            onClick={loadRegistry}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
        <p className="dsr1-symreg__sub">
          Register any new symbol — Forex, Metal, Index, Crypto, CFD or Futures —
          and ASF&apos;s entire pipeline (Ingestion · Factory · Validation · Marketplace)
          picks it up automatically. <b>ASF stays private</b>; customers never
          access this surface.
        </p>
      </header>

      {/* Form */}
      <div className="dsr1-symreg__grid">
        <section className="dsr1-symreg__form" data-testid="dsr1-symbol-form">
          <h3 className="dsr1-symreg__form-title">
            {editingSymbol ? `Editing · ${editingSymbol}` : 'Register a new symbol'}
          </h3>

          {/* Identity */}
          <div className="dsr1-symreg__row">
            <label className="dsr1-symreg__field">
              <span>Symbol *</span>
              <input
                type="text"
                value={draft.symbol}
                onChange={(e) => setDraft({ ...draft, symbol: e.target.value })}
                placeholder="EURUSD · NAS100 · BTCUSD · …"
                data-testid="dsr1-input-symbol"
                disabled={!!editingSymbol}
              />
            </label>
            <label className="dsr1-symreg__field">
              <span>Display name</span>
              <input
                type="text"
                value={draft.display_name}
                onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
                placeholder="EUR/USD · NASDAQ 100 · Bitcoin"
                data-testid="dsr1-input-display"
              />
            </label>
            <label className="dsr1-symreg__field">
              <span>Broker class</span>
              <input
                type="text"
                value={draft.broker_class}
                onChange={(e) => setDraft({ ...draft, broker_class: e.target.value })}
                data-testid="dsr1-input-broker"
              />
            </label>
            <label className="dsr1-symreg__field">
              <span>Pip size</span>
              <input
                type="number"
                step="0.00001"
                value={draft.pip_size}
                onChange={(e) => setDraft({ ...draft, pip_size: e.target.value })}
                data-testid="dsr1-input-pip"
              />
            </label>
          </div>

          {/* Asset class buckets */}
          <div className="dsr1-symreg__section">
            <span className="dsr1-symreg__section-label">Asset class</span>
            <div className="dsr1-symreg__bucket-row">
              {ASSET_BUCKETS.map(b => (
                <button
                  key={b.id}
                  type="button"
                  className={`dsr1-symreg__bucket${draft.bucket === b.id ? ' dsr1-symreg__bucket--active' : ''}`}
                  data-testid={`dsr1-bucket-${b.id}`}
                  onClick={() => setDraft({ ...draft, bucket: b.id, asset_class: DEFAULT_SUBCLASS[b.id] })}
                  title={b.hint}
                >
                  {b.label}
                </button>
              ))}
            </div>
            {/* Sub-class dropdown only for Forex (3 subclasses) */}
            {ASSET_BUCKETS.find(b => b.id === draft.bucket)?.subClasses.length > 1 && (
              <label className="dsr1-symreg__field dsr1-symreg__subclass">
                <span>Sub-class</span>
                <select
                  value={draft.asset_class}
                  onChange={(e) => setDraft({ ...draft, asset_class: e.target.value })}
                  data-testid="dsr1-input-subclass"
                >
                  {ASSET_BUCKETS.find(b => b.id === draft.bucket).subClasses.map(sc => (
                    <option key={sc} value={sc}>{sc.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {/* Eligibility buckets */}
          <div className="dsr1-symreg__section">
            <span className="dsr1-symreg__section-label">Eligibility · 4 buckets</span>
            <div className="dsr1-symreg__elig-row">
              {ELIG_BUCKETS.map(b => {
                const on = !!draft.eligibility_buckets[b.id];
                return (
                  <button
                    key={b.id}
                    type="button"
                    className={`dsr1-symreg__elig${on ? ' dsr1-symreg__elig--on' : ''}`}
                    data-testid={`dsr1-elig-${b.id}`}
                    onClick={() => setDraft({
                      ...draft,
                      eligibility_buckets: { ...draft.eligibility_buckets, [b.id]: !on },
                    })}
                    title={b.hint}
                  >
                    <span className="dsr1-symreg__elig-dot" />
                    {b.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Execution platforms */}
          <div className="dsr1-symreg__section">
            <span className="dsr1-symreg__section-label">
              Execution platforms · operator-verified
            </span>
            <div className="dsr1-symreg__plat-row">
              {EXECUTION_PLATFORMS.map(p => {
                const on = (draft.execution_platforms || []).includes(p.id);
                return (
                  <button
                    key={p.id}
                    type="button"
                    className={`dsr1-symreg__plat${on ? ' dsr1-symreg__plat--on' : ''}`}
                    data-testid={`dsr1-plat-${p.id}`}
                    onClick={() => {
                      const cur = new Set(draft.execution_platforms || []);
                      if (on) cur.delete(p.id); else cur.add(p.id);
                      setDraft({ ...draft, execution_platforms: Array.from(cur) });
                    }}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tier + calendar */}
          <div className="dsr1-symreg__row">
            <label className="dsr1-symreg__field">
              <span>Tier</span>
              <select
                value={draft.tier}
                onChange={(e) => setDraft({ ...draft, tier: e.target.value })}
                data-testid="dsr1-input-tier"
              >
                {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="dsr1-symreg__field">
              <span>Calendar</span>
              <select
                value={draft.calendar_market_type}
                onChange={(e) => setDraft({ ...draft, calendar_market_type: e.target.value })}
                data-testid="dsr1-input-calendar"
              >
                <option value="forex">forex (5-day week)</option>
                <option value="crypto">crypto (24/7)</option>
              </select>
            </label>
            <label className="dsr1-symreg__field">
              <span>Aliases (comma-sep)</span>
              <input
                type="text"
                value={draft.aliases}
                onChange={(e) => setDraft({ ...draft, aliases: e.target.value })}
                placeholder="NAS100, NDX100"
                data-testid="dsr1-input-aliases"
              />
            </label>
            <label className="dsr1-symreg__field dsr1-symreg__field--toggle">
              <span>Enabled</span>
              <button
                type="button"
                className={`dsr1-symreg__toggle${draft.enabled ? ' dsr1-symreg__toggle--on' : ''}`}
                data-testid="dsr1-input-enabled"
                onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
              >
                {draft.enabled ? 'ON' : 'OFF'}
              </button>
            </label>
          </div>

          {/* Notes */}
          <label className="dsr1-symreg__field dsr1-symreg__field--full">
            <span>Notes</span>
            <textarea
              rows={2}
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              placeholder="Internal operator notes (max 2000 chars)"
              data-testid="dsr1-input-notes"
            />
          </label>

          {/* Submit */}
          <div className="dsr1-symreg__actions">
            <button
              type="button"
              className="dsr1-symreg__btn dsr1-symreg__btn--primary"
              onClick={submit}
              disabled={submitting || !draft.symbol.trim()}
              data-testid="dsr1-submit"
            >
              {submitting ? 'Saving…' : (editingSymbol ? 'Save changes' : 'Register symbol')}
            </button>
            {editingSymbol && (
              <button
                type="button"
                className="dsr1-symreg__btn"
                onClick={() => { setDraft(emptyDraft()); setEditingSymbol(null); }}
                data-testid="dsr1-cancel-edit"
              >
                Cancel edit
              </button>
            )}
          </div>

          {error && (
            <div className="dsr1-symreg__msg dsr1-symreg__msg--err" data-testid="dsr1-error">
              {error}
            </div>
          )}
          {success && (
            <div className="dsr1-symreg__msg dsr1-symreg__msg--ok" data-testid="dsr1-success">
              {success}
            </div>
          )}
        </section>

        {/* Live preview pane */}
        <aside className="dsr1-symreg__preview" data-testid="dsr1-preview">
          <h3 className="dsr1-symreg__form-title">Live preview</h3>
          <p className="dsr1-symreg__preview-note">
            Exact payload that will hit <code>POST /api/admin/market-universe</code>.
          </p>
          <pre className="dsr1-symreg__json" data-testid="dsr1-preview-json">
{JSON.stringify(previewPayload, null, 2)}
          </pre>
          <div className="dsr1-symreg__preview-reserved">
            <span className="dsr1-symreg__preview-reserved-label">
              Reserved future-phase fields (auto-stored as empty)
            </span>
            <ul>
              <li><code>broker_compatibility</code> · Phase 14</li>
              <li><code>strategy_compatibility</code> · Phase 13</li>
              <li><code>masterbot_compatibility</code> · Phase 14</li>
              <li><code>marketplace_visibility</code> · Phase 15</li>
              <li><code>propfirm_eligibility</code> · Phase 14</li>
            </ul>
          </div>
        </aside>
      </div>

      {/* Registered symbols table */}
      <section className="dsr1-symreg__table-wrap" data-testid="dsr1-symbol-list">
        <header className="dsr1-symreg__table-hd">
          <h3>Registered symbols · {rows.length}</h3>
          {meta?.tier_summary && (
            <span className="dsr1-symreg__tier-summary">
              {Object.entries(meta.tier_summary).map(([t, n]) => (
                <span key={t} className="dsr1-symreg__tier-pill">
                  {t}:<strong>{n}</strong>
                </span>
              ))}
            </span>
          )}
        </header>
        <div className="dsr1-symreg__table" role="table">
          <div className="dsr1-symreg__trow dsr1-symreg__trow--head" role="row">
            <span>Symbol</span>
            <span>Broker</span>
            <span>Class</span>
            <span>Tier</span>
            <span>Enabled</span>
            <span>Eligibility</span>
            <span>Platforms</span>
            <span></span>
          </div>
          {rows.length === 0 && !loading && (
            <div className="dsr1-symreg__empty" data-testid="dsr1-empty">
              No symbols registered yet. Use the form above to add one.
            </div>
          )}
          {rows.map(r => {
            const eligOn = ELIG_BUCKETS.filter(b => b.flags.every(f => r.eligibility?.[f])).map(b => b.label);
            return (
              <div
                key={`${r.symbol}::${r.broker_class}`}
                className="dsr1-symreg__trow"
                role="row"
                data-testid={`dsr1-row-${r.symbol}`}
              >
                <span className="dsr1-symreg__cell-sym">{r.symbol}</span>
                <span>{r.broker_class}</span>
                <span>{r.asset_class}</span>
                <span className={`dsr1-symreg__cell-tier dsr1-symreg__cell-tier--${r.tier}`}>{r.tier}</span>
                <span className={r.enabled ? 'dsr1-symreg__cell-on' : 'dsr1-symreg__cell-off'}>
                  {r.enabled ? 'ON' : 'OFF'}
                </span>
                <span className="dsr1-symreg__cell-elig">
                  {eligOn.length ? eligOn.join(' · ') : <em>none</em>}
                </span>
                <span className="dsr1-symreg__cell-plat">
                  {(r.execution_platforms || []).length
                    ? (r.execution_platforms || []).join(' · ')
                    : <em>none</em>}
                </span>
                <span>
                  <button
                    type="button"
                    className="dsr1-symreg__btn dsr1-symreg__btn--small"
                    data-testid={`dsr1-edit-${r.symbol}`}
                    onClick={() => startEdit(r)}
                  >
                    Edit
                  </button>
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
