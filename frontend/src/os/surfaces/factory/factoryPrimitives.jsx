/*
 * factoryPrimitives — small, dashboard-local composition helpers that layer
 * on top of the canonical primitives (MetricBlock, Chip, StateTemplate,
 * SignalStateBadge, FreezeCaption). These are NOT new design primitives —
 * they are dashboard-scope compositions of existing tokens + tokens-only
 * styling so every Factory-group surface stays visually consistent.
 * refs docs/FE_B_PROPOSAL.md · Backend Feature Freeze v1.1.0-stage4.
 */
import React from 'react';
import { Chip } from '../../primitives/Chip';
import { SignalStateBadge, FreezeCaption } from '../engineering/LivenessBadge';

export const eyebrowLabel = {
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: 'var(--content-md)',
};

export const sectionPanel = {
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-1)',
  borderRadius: 'var(--radius-3)',
  padding: 'var(--space-4)',
};

export const cellHead = { padding: 'var(--space-3) var(--space-2)', fontWeight: 500 };
export const cell     = { padding: 'var(--space-3) var(--space-2)', verticalAlign: 'top' };

export const fmtISO = (iso) => (iso ? String(iso).replace('T', ' ').replace('Z', 'Z').slice(5, 22) : '—');
export const fmtRel = (iso) => {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return '—';
  const dSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (dSec < 60) return `${dSec}s ago`;
  if (dSec < 3600) return `${Math.floor(dSec / 60)}m ago`;
  if (dSec < 86_400) return `${Math.floor(dSec / 3600)}h ago`;
  return `${Math.floor(dSec / 86_400)}d ago`;
};

/* Renders the "OPERATOR SUMMARY" panel with N Chip cells. */
export const SummaryPanel = ({ testId, signalState, signalReason, cells }) => (
  <div data-testid={testId}
       style={{
         padding: 'var(--space-4)',
         background: 'var(--surface-2)',
         border: '1px solid var(--stroke-1)',
         borderRadius: 'var(--radius-3)',
         marginBottom: 'var(--space-6)',
       }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
      <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--content-md)' }}>Operator Summary</span>
      <SignalStateBadge state={signalState} reason={signalReason} testId={`${testId}-signal`} />
      <span style={{ marginLeft: 'auto' }}>
        <FreezeCaption />
      </span>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-3)' }}>
      {cells.map((c, i) => (
        <div key={i} data-testid={c.testId || `${testId}-cell-${i}`} style={{
          display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
          padding: 'var(--space-4)', minWidth: 180,
          background: 'var(--surface-1)', border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)',
        }}>
          <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--content-lo)' }}>{c.label}</span>
          <Chip tone={c.tone} label={c.value} />
          {c.sub && <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)' }}>{c.sub}</span>}
        </div>
      ))}
    </div>
  </div>
);

export const SectionHeader = ({ icon: Icon, title, testId, right }) => (
  <div data-testid={testId} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
    {Icon && <Icon size={14} color="var(--content-md)" aria-hidden />}
    <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--content-md)' }}>{title}</span>
    {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
  </div>
);

/* Utility: safely coerce an array-ish payload (list, {items:[]}, {data:[]}) */
export const asArray = (raw, ...keys) => {
  if (Array.isArray(raw)) return raw;
  if (!raw || typeof raw !== 'object') return [];
  for (const k of ['items', 'data', 'results', 'rows', ...keys]) {
    if (Array.isArray(raw[k])) return raw[k];
  }
  return [];
};

/* Utility: mode string → tone. observe/dryrun = ok; enforce/enabled = warn; else dormant */
export const modeToTone = (mode) => {
  const m = String(mode || '').toLowerCase();
  if (m === 'observe' || m === 'dry-run' || m === 'dryrun' || m === 'off' || m === 'disabled') return 'ok';
  if (m === 'enforce' || m === 'active' || m === 'enabled' || m === 'on' || m === 'live') return 'warn';
  return 'dormant';
};

/**
 * Normalises a subsystem "health" payload from the Autonomous Factory.
 * Backend variations we need to accept:
 *   - explicit ok         → { ok:true } | { healthy:true } | { status:'ok' }
 *   - "feature disabled"  → { detail: '<..> is off' }         (dormant, NOT crit)
 *   - "no data yet"       → { status: 'empty' }               (dormant, NOT crit)
 *   - explicit failure    → { error:'...' } | { status:'error'|'degraded' }
 *   - missing/unreachable → null                              (dormant)
 * Returns { tone, label } with tone ∈ 'ok' | 'crit' | 'dormant'.
 */
export const deriveHealth = (raw) => {
  if (raw == null) return { tone: 'dormant', label: 'UNKNOWN' };
  if (typeof raw !== 'object') return { tone: 'dormant', label: 'UNKNOWN' };
  // Explicit disabled/off → dormant (feature not activated in this env)
  if (typeof raw.detail === 'string' && raw.detail) return { tone: 'dormant', label: 'DISABLED' };
  // Explicit failure
  if (raw.error) return { tone: 'crit', label: 'ERROR' };
  const status = String(raw.status || '').toLowerCase();
  if (status === 'error' || status === 'degraded' || status === 'critical' || status === 'failed') return { tone: 'crit', label: status.toUpperCase() };
  if (status === 'empty' || status === 'idle' || status === 'unknown') return { tone: 'dormant', label: status.toUpperCase() };
  // Positive signals
  if (raw.ok === true || raw.healthy === true || status === 'ok' || status === 'healthy' || status === 'active' || status === 'ready') return { tone: 'ok', label: 'HEALTHY' };
  // Anything else = live but unclassified
  return { tone: 'info', label: 'LIVE' };
};
