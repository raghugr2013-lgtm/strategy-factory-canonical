/**
 * GovernanceAdminSuite — Phase R1 composition
 * --------------------------------------------------------------------------
 * Folds the previous separate sections into one operator surface:
 *   - Users      : Admin Users (approve / reject)
 *   - Flags      : Flag Governance (advanced)
 *   - Realism    : Execution Realism defaults (advanced)
 *   - Tuning     : Phase 12 Tuning (advanced)
 *
 * Backend wiring untouched; this is a pure composition.
 */
import React, { Suspense, useEffect, useState } from 'react';
import { API_URL } from '../services/api';

const AdminUsers = React.lazy(() => import('./AdminUsers'));
const {
  AdminFlagGovernancePanel,
  AdminExecutionRealismPanel,
  Phase12TuningPanel,
} = require('./OperatorParityPanels');


/**
 * Restoration Step 4d — readiness one-liner. Mirrors the old 1-vCPU Admin
 * tab where ReadinessPanel sat directly above AdminUsers: the admin sees
 * the gate verdict without leaving this tab, and one click jumps to the
 * full panel at governance/readiness. Read-only GET; admin-gated endpoint.
 */
function ReadinessOneLiner() {
  const [overall, setOverall] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/admin/readiness`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setOverall(data.overall || null);
      } catch (_) {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const jumpToReadiness = () => {
    // Same-module hash navigation (the suite renders inside /c/governance).
    window.history.replaceState({}, '', `${window.location.pathname}#readiness`);
    try { window.dispatchEvent(new HashChangeEvent('hashchange')); } catch (_) { /* noop */ }
    const el = document.querySelector('[data-testid="cmd-section-governance-readiness"]');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (failed) return null; // pure affordance — never block the Admin tab

  const color = overall === 'green' ? 'var(--cmd-green, #34D399)'
    : overall === 'amber' ? 'var(--cmd-amber, #FBBF24)'
    : overall === 'red' ? 'var(--cmd-red, #F87171)'
    : 'var(--cmd-ink-2, #A1A1AA)';

  return (
    <div
      data-testid="gov-admin-readiness-line"
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 16px',
        borderBottom: '1px solid var(--cmd-line, #2A2D33)',
        background: 'var(--cmd-panel, #14171C)',
        fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
      <span style={{ color: 'var(--cmd-ink-1, #E4E4E7)', letterSpacing: '0.08em' }}>
        READINESS · {(overall || 'checking…').toUpperCase()}
      </span>
      <div style={{ flex: 1 }} />
      <button
        type="button"
        data-testid="gov-admin-readiness-jump"
        onClick={jumpToReadiness}
        style={{
          fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase',
          padding: '3px 10px', borderRadius: 4, cursor: 'pointer',
          border: '1px solid var(--cmd-line, #2A2D33)',
          background: 'transparent', color: 'var(--cmd-accent, #7AB8FF)',
        }}
      >
        open readiness →
      </button>
    </div>
  );
}

const TABS = [
  { id: 'users',   label: 'Users',   description: 'Approve / reject pending registrations' },
  { id: 'flags',   label: 'Flags',   description: 'Feature flags · widening proposals' },
  { id: 'realism', label: 'Realism', description: 'Execution realism defaults (advanced)' },
  { id: 'tuning',  label: 'Tuning',  description: 'Phase 12 tuning recommendations (advanced)' },
];

export default function GovernanceAdminSuite() {
  const [tab, setTab] = useState('users');

  return (
    <section
      data-testid="governance-admin-suite"
      className="asf-section"
      aria-label="Governance Admin"
    >
      <header
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid var(--cmd-line, #2A2D33)',
          background: 'var(--cmd-panel, #14171C)',
        }}
      >
        <h2
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--cmd-ink-1, #E4E4E7)',
            margin: 0,
          }}
        >
          Admin
        </h2>
        <p style={{ fontSize: 11, color: 'var(--cmd-ink-2, #A1A1AA)', margin: '4px 0 0' }}>
          Operator users, feature flags, realism defaults, tuning recommendations.
        </p>
      </header>

      {/* Restoration Step 4d — readiness verdict without leaving Admin. */}
      <ReadinessOneLiner />

      <nav
        role="tablist"
        aria-label="Admin sub-sections"
        style={{
          display: 'flex',
          gap: 4,
          padding: '8px 16px',
          borderBottom: '1px solid var(--cmd-line, #2A2D33)',
          background: 'var(--cmd-panel, #14171C)',
        }}
      >
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              data-testid={`gov-admin-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              title={t.description}
              style={{
                padding: '6px 12px',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                borderRadius: 4,
                border: '1px solid',
                borderColor: active ? 'var(--cmd-accent, #7AB8FF)' : 'var(--cmd-line, #2A2D33)',
                background: active ? 'rgba(122,184,255,0.12)' : 'transparent',
                color: active ? 'var(--cmd-accent, #7AB8FF)' : 'var(--cmd-ink-1, #E4E4E7)',
                cursor: 'pointer',
              }}
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      <Suspense fallback={<div style={{ padding: 24, fontSize: 11 }}>Loading…</div>}>
        {tab === 'users'   && <AdminUsers />}
        {tab === 'flags'   && <AdminFlagGovernancePanel />}
        {tab === 'realism' && <AdminExecutionRealismPanel />}
        {tab === 'tuning'  && <Phase12TuningPanel />}
      </Suspense>
    </section>
  );
}
