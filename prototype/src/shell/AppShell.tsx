/*
 * AppShell — Bible §4 · persistent chrome; never re-mounts on route change.
 * Prototype Phase 1 scaffold: header · status-rail placeholder · main outlet.
 * LeftRail · TopTabBar · RightRail · PinsTray arrive in Phase 2.
 */
import { Outlet } from 'react-router-dom';
import { useWorkspaceStore } from '../workspace-state/store';

export const AppShell: React.FC = () => {
  const mode = useWorkspaceStore((s) => s.mode);
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const killArmed = useWorkspaceStore((s) => s.killPostureArmed);
  const cmdkHintDismissed = useWorkspaceStore((s) => s.cmdkHintDismissed);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {killArmed && (
        <div
          role="alert"
          data-testid="danger-ribbon"
          style={{
            background: 'rgba(255,91,91,0.14)',
            borderBottom: '1px solid var(--sig-crit)',
            color: 'var(--sig-crit)',
            padding: 'var(--space-2) var(--space-5)',
            fontSize: 'var(--font-caption)',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontFamily: 'ui-monospace, monospace',
          }}
        >
          ⚠ DANGER · Kill posture armed · deliberate freeze
        </div>
      )}
      <header
        data-testid="app-header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-3) var(--space-5)',
          borderBottom: '1px solid var(--stroke-1)',
          background: 'var(--surface-1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
          <span style={{ fontSize: 'var(--font-body-md)', fontWeight: 500 }}>Strategy Factory</span>
          <span
            className="mono-num"
            style={{
              fontSize: 'var(--font-caption)',
              color: 'var(--content-lo)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            @v55
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
          {!cmdkHintDismissed && (
            <span
              data-testid="cmdk-hint"
              style={{
                fontSize: 'var(--font-caption)',
                color: 'var(--content-lo)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                fontFamily: 'ui-monospace, monospace',
              }}
            >
              ⌘K → find anything
            </span>
          )}
          <span
            data-testid="mode-chip"
            className="mono-num"
            style={{
              fontSize: 'var(--font-caption)',
              color: 'var(--content-md)',
              padding: '4px 8px',
              border: '1px solid var(--stroke-2)',
              borderRadius: 'var(--radius-1)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            mode · {mode} {advLens && '· advanced'}
          </span>
        </div>
      </header>
      <main
        role="main"
        tabIndex={-1}
        style={{ flex: 1, padding: 'var(--space-6) var(--space-5)', background: 'var(--surface-0)' }}
      >
        <Outlet />
      </main>
      <footer
        data-testid="status-rail"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-4)',
          padding: 'var(--space-2) var(--space-5)',
          borderTop: '1px solid var(--stroke-1)',
          background: 'var(--surface-1)',
          fontSize: 'var(--font-caption)',
          color: 'var(--content-lo)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontFamily: 'ui-monospace, monospace',
        }}
      >
        <span>● orchestrator</span>
        <span>● ingestion</span>
        <span>● scheduler</span>
        <span>● llm</span>
        <span>● governance</span>
        <span style={{ color: killArmed ? 'var(--sig-crit)' : 'var(--sig-dormant)' }}>
          {killArmed ? '⚠ kill posture armed' : '○ kill posture'}
        </span>
        <span style={{ marginLeft: 'auto' }} className="mono-num">
          {new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC · env prod
        </span>
      </footer>
    </div>
  );
};
