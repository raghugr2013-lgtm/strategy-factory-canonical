/**
 * MonitoringSuite — Phase R4 composition
 * --------------------------------------------------------------------------
 * Composes:
 *   - Runtime    : Monitoring & Control (Stop/Resume/Save Thresholds/Breach Log)
 *   - Soak       : Soak Diagnostics snapshot
 *   - Compute    : CPU Pool State
 *   - Cluster    : Scaling Controls (advanced / power-user)
 *
 * All four are existing components — this wrapper only composes them into
 * sub-tabs so the developer-console exposure is removed from primary
 * operator navigation per DEVELOPER_CONSOLE_REPLACEMENT_PLAN.md.
 */
import React, { Suspense, useState } from 'react';

const MonitoringControl  = React.lazy(() => import('./Monitoring'));
const {
  SoakDiagnosticsPanel,
  CpuPoolStatePanel,
  ScalingPanel,
} = require('./OperatorParityPanels');

const TABS = [
  { id: 'runtime', label: 'Runtime', description: 'Stop / Resume / Thresholds / Breach Log / Fleet' },
  { id: 'soak',    label: 'Soak',    description: 'Long-running soak snapshot' },
  { id: 'compute', label: 'Compute', description: 'CPU pool state · worker count · recent activity' },
  { id: 'cluster', label: 'Cluster', description: 'Scaling · admission · pressure (advanced)' },
];

export default function MonitoringSuite() {
  const [tab, setTab] = useState('runtime');

  return (
    <section
      data-testid="monitoring-suite"
      className="asf-section"
      aria-label="Monitoring & Control"
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 16px',
          borderBottom: '1px solid var(--cmd-line, #2A2D33)',
          background: 'var(--cmd-panel, #14171C)',
        }}
      >
        <div style={{ flex: 1 }}>
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
            Monitoring
          </h2>
          <p style={{ fontSize: 11, color: 'var(--cmd-ink-2, #A1A1AA)', margin: '4px 0 0' }}>
            Backend uptime · Mongo health · workers · breach log · soak · compute · cluster
          </p>
        </div>
      </header>

      <nav
        role="tablist"
        aria-label="Monitoring sub-sections"
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
              data-testid={`monitoring-tab-${t.id}`}
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
        {tab === 'runtime' && <MonitoringControl />}
        {tab === 'soak'    && <SoakDiagnosticsPanel />}
        {tab === 'compute' && <CpuPoolStatePanel />}
        {tab === 'cluster' && <ScalingPanel />}
      </Suspense>
    </section>
  );
}
