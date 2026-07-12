import React, { useEffect, useState, useCallback } from 'react';
import {
  CheckCircle, XCircle, ArrowsClockwise, Warning, ShieldCheck, Spinner,
  PencilSimple, FloppyDisk,
} from '@phosphor-icons/react';
import {
  getPropFirmReviewRule,
  approvePropFirmRules,
  rejectPropFirmRules,
  resetPropFirmRules,
} from '../services/api';
import { AsfEmptyState } from './ui-asf';

/**
 * Review / Approve / Reject / Reset panel for prop_firm_rules.
 * Wraps the approval state machine: parsed → approved | rejected.
 * Can be used standalone or embedded inside the AddFirmModal after extract.
 */

// Editable fields spec — covers the full reviewable schema
const FIELDS = [
  { key: 'profit_target_pct',   label: 'Profit Target (%)',    type: 'number', step: 0.1 },
  { key: 'max_daily_loss_pct',  label: 'Max Daily Loss (%)',   type: 'number', step: 0.1 },
  { key: 'max_total_loss_pct',  label: 'Max Total Loss (%)',   type: 'number', step: 0.1 },
  { key: 'min_trading_days',    label: 'Min Trading Days',     type: 'number', step: 1 },
  { key: 'time_limit_days',     label: 'Max Trading Days',     type: 'number', step: 1 },
  { key: 'consistency_rule',    label: 'Consistency Rule',     type: 'bool' },
  { key: 'daily_loss_type',     label: 'Daily Loss Type',      type: 'select', options: ['equity', 'balance', 'intraday_equity'] },
  { key: 'trailing_drawdown',   label: 'Trailing Drawdown',    type: 'bool' },
  { key: 'max_trades_per_day',  label: 'Max Trades / Day',     type: 'number', step: 1 },
  { key: 'leverage',            label: 'Leverage (1:x)',       type: 'number', step: 1 },
  { key: 'news_trading_allowed', label: 'News trading allowed', type: 'bool' },
  { key: 'weekend_holding_allowed', label: 'Weekend holding allowed', type: 'bool' },
];

export function StatusBadge({ status }) {
  const cfg = {
    parsed:   { bg: 'bg-yellow-500/15', border: 'border-yellow-500/50', text: 'text-yellow-300', Icon: PencilSimple, label: 'Parsed' },
    approved: { bg: 'bg-emerald-500/15', border: 'border-emerald-500/50', text: 'text-emerald-300', Icon: CheckCircle, label: 'Approved' },
    rejected: { bg: 'bg-red-500/15', border: 'border-red-500/50', text: 'text-red-300', Icon: XCircle, label: 'Rejected' },
  };
  const c = cfg[status] || cfg.parsed;
  const Icon = c.Icon;
  return (
    <span
      data-testid={`rules-status-${status || 'unknown'}`}
      className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded border ${c.bg} ${c.border} ${c.text}`}
    >
      <Icon size={10} weight="bold" /> {c.label}
    </span>
  );
}

function ConfidenceChip({ value }) {
  if (value === null || value === undefined) {
    return <span className="text-[10px] font-mono text-zinc-500">confidence —</span>;
  }
  const pct = Math.round((Number(value) || 0) * 100);
  const col = pct >= 70 ? 'text-emerald-400' : pct >= 40 ? 'text-yellow-300' : 'text-red-300';
  return <span className={`text-[10px] font-mono ${col}`}>confidence {pct}%</span>;
}

function coerceValue(v, type) {
  if (v === '' || v === null || v === undefined) return null;
  if (type === 'number') return Number.isFinite(Number(v)) ? Number(v) : null;
  if (type === 'bool') return Boolean(v);
  return v;
}

export default function RulesReviewPanel({ firmSlug, initialData, onChange, showTitle = true }) {
  const [data, setData] = useState(initialData || null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({});

  // Load latest doc
  const load = useCallback(async () => {
    if (!firmSlug) return;
    setLoading(true); setError(null);
    try {
      const d = await getPropFirmReviewRule(firmSlug);
      setData(d);
      // Seed the editable form from approved_rules ∪ parsed_rules ∪ flat
      const baseline = {
        ...(d?.parsed_rules || {}),
        ...(d || {}),
        ...(d?.approved_rules || {}),
      };
      setForm(
        FIELDS.reduce((acc, f) => {
          const v = baseline[f.key];
          acc[f.key] =
            v === null || v === undefined
              ? (f.type === 'bool' ? false : '')
              : f.type === 'bool' ? Boolean(v) : v;
          return acc;
        }, {}),
      );
      onChange?.(d);
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [firmSlug, onChange]);

  useEffect(() => { load(); }, [load]);

  const updateField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleApprove = async () => {
    setSaving(true); setError(null);
    try {
      const approved = FIELDS.reduce((acc, f) => {
        acc[f.key] = coerceValue(form[f.key], f.type);
        return acc;
      }, {});
      const res = await approvePropFirmRules(firmSlug, approved);
      setData(res);
      onChange?.(res);
    } catch (e) {
      setError(e.message || 'Approve failed');
    } finally {
      setSaving(false);
    }
  };

  const handleReject = async () => {
    setSaving(true); setError(null);
    try {
      const res = await rejectPropFirmRules(firmSlug);
      setData(res);
      onChange?.(res);
    } catch (e) {
      setError(e.message || 'Reject failed');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true); setError(null);
    try {
      const res = await resetPropFirmRules(firmSlug);
      setData(res);
      onChange?.(res);
    } catch (e) {
      setError(e.message || 'Reset failed');
    } finally {
      setSaving(false);
    }
  };

  if (!firmSlug) return null;

  return (
    <div className="asf-section asf-u2-panel rounded-md border border-zinc-800 bg-[#121821] p-4 space-y-3" data-testid="rules-review-panel">
      {showTitle && (
        <div className="asf-section__hd flex items-center justify-between">
          <p className="asf-legacy-title text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 flex items-center gap-2">
            <ShieldCheck size={12} /> Review Extracted Rules
          </p>
          <div className="asf-section__hd-spacer" />
          <div className="asf-section__hd-actions flex items-center gap-2">
            <StatusBadge status={data?.status} />
            {data?.auto_approved && (
              <span className="text-[9px] font-mono text-zinc-500">(auto-approved)</span>
            )}
          </div>
        </div>
      )}

      {/* Metadata */}
      <div className="flex items-center gap-3 text-[10px] font-mono text-zinc-500">
        <span>{data?.firm_name || firmSlug}</span>
        <span>·</span>
        <ConfidenceChip value={data?.parser_confidence} />
        {data?.source_type && (
          <>
            <span>·</span>
            <span>source: <span className="text-zinc-300">{data.source_type}</span></span>
          </>
        )}
        {data?.source_url && (
          <>
            <span>·</span>
            <a
              href={data.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-primary truncate max-w-[200px] underline"
            >
              {data.source_url}
            </a>
          </>
        )}
      </div>

      {loading && (
        <p className="text-xs font-mono text-zinc-500 py-3 text-center">
          <Spinner size={12} className="animate-spin inline mr-2" /> Loading…
        </p>
      )}

      {error && (
        <AsfEmptyState
          slug="rules-review-error"
          testId="rules-review-error"
          title="Rules review failed"
          body={error}
        />
      )}

      {/* Editable form */}
      <div className="grid grid-cols-2 gap-3" data-testid="rules-review-form">
        {FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1 text-[10px] font-mono text-zinc-400">
            <span className="uppercase tracking-[0.15em]">{f.label}</span>
            {f.type === 'bool' ? (
              <input
                type="checkbox"
                data-testid={`rules-field-${f.key}`}
                checked={!!form[f.key]}
                onChange={(e) => updateField(f.key, e.target.checked)}
                disabled={data?.status === 'approved'}
                className="accent-accent-primary self-start mt-1"
              />
            ) : f.type === 'select' ? (
              <select
                data-testid={`rules-field-${f.key}`}
                value={form[f.key] ?? ''}
                onChange={(e) => updateField(f.key, e.target.value)}
                disabled={data?.status === 'approved'}
                className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 disabled:opacity-60"
              >
                <option value="">—</option>
                {f.options.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            ) : (
              <input
                type="number"
                step={f.step}
                data-testid={`rules-field-${f.key}`}
                value={form[f.key] ?? ''}
                onChange={(e) => updateField(f.key, e.target.value)}
                disabled={data?.status === 'approved'}
                className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 disabled:opacity-60 tabular-nums"
              />
            )}
          </label>
        ))}
      </div>

      {data?.status === 'approved' && (
        <div className="rounded border border-emerald-500/30 bg-emerald-500/5 text-[11px] font-mono text-emerald-300 px-2 py-1.5 flex items-center gap-2">
          <CheckCircle size={12} weight="bold" /> These rules are approved and actively used by the analysis & matching engines.
        </div>
      )}
      {data?.status === 'rejected' && (
        <div className="rounded border border-red-500/30 bg-red-500/5 text-[11px] font-mono text-red-300 px-2 py-1.5 flex items-center gap-2">
          <Warning size={12} weight="bold" /> Rejected — firm is excluded from all analyses and challenge matching.
        </div>
      )}
      {data?.status === 'parsed' && (
        <div className="rounded border border-yellow-500/30 bg-yellow-500/5 text-[11px] font-mono text-yellow-300 px-2 py-1.5 flex items-center gap-2">
          <Warning size={12} weight="bold" /> Parsed but NOT verified — analysis is blocked until you Approve.
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-2">
        <button
          data-testid="rules-reset-btn"
          onClick={handleReset}
          disabled={saving}
          className="text-xs font-medium px-3 py-1.5 rounded border border-zinc-700 hover:border-zinc-500 text-zinc-300 bg-[#0B0F14] disabled:opacity-50 flex items-center gap-1"
        >
          <ArrowsClockwise size={12} /> Reset
        </button>
        <button
          data-testid="rules-reject-btn"
          onClick={handleReject}
          disabled={saving || data?.status === 'rejected'}
          className="text-xs font-medium px-3 py-1.5 rounded border border-red-500/40 bg-red-500/10 hover:bg-red-500/20 text-red-300 disabled:opacity-50 flex items-center gap-1"
        >
          <XCircle size={12} /> Reject
        </button>
        <button
          data-testid="rules-approve-btn"
          onClick={handleApprove}
          disabled={saving}
          className="text-xs font-medium px-3 py-1.5 rounded border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 disabled:opacity-50 flex items-center gap-1"
        >
          {saving ? <Spinner size={12} className="animate-spin" /> : <FloppyDisk size={12} />}
          Approve
        </button>
      </div>
    </div>
  );
}
