/*
 * AppShell — Bible §4 · persistent chrome; never re-mounts on route change.
 * Phase 3 update: adds LeftRailStub + auth-aware chrome per E2 §3.1 & §9.
 * Pre-auth chrome renders header brand, LeftRail-locked, StatusRail (6 chips
 * + kill posture), and hides the ⌘K hint & user menu.
 */
import { Outlet, useLocation } from 'react-router-dom';
import { useWorkspaceStore } from '../workspace-state/store';
import { useAuthStore } from '../workspace-state/authStore';
import { useInspectorStore } from '../workspace-state/inspectorStore';
import { LeftRail } from './LeftRail';
import { InspectorSheet } from './InspectorSheet';
import { UserMenu } from '../auth/UserMenu';

export const AppShell: React.FC = () => {
  const mode = useWorkspaceStore((s) => s.mode);
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const killArmed = useWorkspaceStore((s) => s.killPostureArmed);
  const cmdkHintDismissed = useWorkspaceStore((s) => s.cmdkHintDismissed);
  const authStance = useAuthStore((s) => s.stance);
  const toggleSheet = useInspectorStore((s) => s.toggleSheet);
  const activeScenario = useInspectorStore((s) => s.scenarioKey);
  const loc = useLocation();

  const isAuthed = authStance === 'authenticated';
  // Danger ribbon fires only post-auth per E2 §9.4.
  const showDangerRibbon = isAuthed && killArmed;
  // Suppress ⌘K hint on the login screen per E2 §3.1.
  const onLoginRoute = loc.pathname.startsWith('/auth');

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {showDangerRibbon && (
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
            data-testid="app-version"
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
          <span
            className="mono-num"
            data-testid="header-utc"
            style={{
              fontSize: 'var(--font-caption)',
              color: 'var(--content-lo)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            {new Date().toISOString().slice(11, 16)} UTC
          </span>
          {isAuthed && !cmdkHintDismissed && !onLoginRoute && (
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
          {!isAuthed && onLoginRoute && (
            <span
              data-testid="cmdk-disabled"
              aria-disabled="true"
              style={{
                fontSize: 'var(--font-caption)',
                color: 'var(--content-lo)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                fontFamily: 'ui-monospace, monospace',
                opacity: 0.5,
              }}
            >
              ⌘K disabled
            </span>
          )}
          {isAuthed && (
            <button
              data-testid="proto-toggle"
              onClick={toggleSheet}
              title="Prototype inspector · scenarios & state toggles"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: activeScenario ? 'var(--sig-info)' : 'transparent',
                color: activeScenario ? 'var(--surface-0)' : 'var(--content-md)',
                border: '1px solid var(--stroke-2)',
                borderRadius: 'var(--radius-1)',
                padding: '4px 8px',
                fontFamily: 'ui-monospace, monospace',
                fontSize: 'var(--font-caption)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                cursor: 'pointer',
              }}
            >
              ◆ proto{activeScenario && ' · active'}
            </button>
          )}
          {isAuthed ? (
            <UserMenu />
          ) : (
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
          )}
        </div>
      </header>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <LeftRail />
        <main
          role="main"
          tabIndex={-1}
          style={{ flex: 1, padding: 'var(--space-6) var(--space-5)', background: 'var(--surface-0)', overflowY: 'auto' }}
        >
          <Outlet />
        </main>
      </div>

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
        <span
          data-testid="kill-posture-chip"
          title={!isAuthed ? 'Kill posture is public information.' : undefined}
          style={{ color: killArmed ? 'var(--sig-crit)' : 'var(--sig-dormant)' }}
        >
          {killArmed ? '⚠ kill posture armed' : '○ kill posture'}
        </span>
        <span style={{ marginLeft: 'auto' }} className="mono-num">
          env prod · @v55
        </span>
      </footer>

      <InspectorSheet />
    </div>
  );
};
