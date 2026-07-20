/*
 * LeftRail — Bible §4.2, E2 §3.1.
 * Vertical primary navigation. When anonymous, all modules render locked
 * per E2 §9.3. When authenticated, each module is an active NavLink with
 * a "current" indicator (2 px accent bar on the left).
 *
 * Phase 4: 6 routable modules + Settings placeholder.
 */
import { NavLink } from 'react-router-dom';
import {
  Activity, Bot, Briefcase, ClipboardCheck, Compass, Lock, Settings, ClipboardList,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuthStore } from '../workspace-state/authStore';

interface RailModule { key: string; label: string; icon: LucideIcon; to: string; testId: string; }

const MODULES: RailModule[] = [
  { key: 'mission',    label: 'mission',    icon: Compass,        to: '/c/mission',    testId: 'nav-mission'    },
  { key: 'timeline',   label: 'timeline',   icon: Activity,       to: '/c/timeline',   testId: 'nav-timeline'   },
  { key: 'approvals',  label: 'approvals',  icon: ClipboardCheck, to: '/c/approvals',  testId: 'nav-approvals'  },
  { key: 'workforce',  label: 'workforce',  icon: Bot,            to: '/c/workforce',  testId: 'nav-workforce'  },
  { key: 'strategies', label: 'strategies', icon: Briefcase,      to: '/c/strategies', testId: 'nav-strategies' },
  { key: 'settings',   label: 'settings',   icon: Settings,       to: '/c/settings',   testId: 'nav-settings'   },
  { key: 'eval',       label: 'eval',       icon: ClipboardList,  to: '/prototype/eval', testId: 'nav-eval'      },
];

export const LeftRail: React.FC = () => {
  const stance = useAuthStore((s) => s.stance);
  const locked = stance !== 'authenticated';

  return (
    <nav
      data-testid="left-rail"
      aria-label="Primary navigation"
      style={{
        display: 'flex', flexDirection: 'column', gap: 'var(--space-1)',
        width: 68,
        padding: 'var(--space-3) var(--space-2)',
        background: 'var(--surface-1)',
        borderRight: '1px solid var(--stroke-1)',
      }}
    >
      {MODULES.map((m) => {
        const I = m.icon;
        if (locked) {
          return (
            <div
              key={m.key}
              data-testid={`${m.testId}-locked`}
              aria-disabled="true"
              title={`${m.label} · locked`}
              style={lockedStyle}
            >
              <I size={18} strokeWidth={1.5} aria-hidden="true" />
              <span style={labelStyle}>{m.label}</span>
              <Lock size={8} aria-hidden="true"
                style={{ position: 'absolute', top: 4, right: 4, color: 'var(--content-lo)' }}
              />
            </div>
          );
        }
        return (
          <NavLink
            key={m.key}
            to={m.to}
            data-testid={m.testId}
            style={({ isActive }) => ({
              ...activeableStyle,
              color: isActive ? 'var(--content-hi)' : 'var(--content-md)',
              background: isActive ? 'var(--surface-2)' : 'transparent',
              borderLeft: `2px solid ${isActive ? 'var(--sig-info)' : 'transparent'}`,
            })}
          >
            <I size={18} strokeWidth={1.5} aria-hidden="true" />
            <span style={labelStyle}>{m.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
};

const lockedStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
  padding: '8px 4px',
  borderRadius: 'var(--radius-1)',
  color: 'var(--content-lo)',
  opacity: 0.4,
  cursor: 'not-allowed',
  pointerEvents: 'none',
  position: 'relative',
};

const activeableStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
  padding: '8px 4px',
  borderRadius: 'var(--radius-1)',
  textDecoration: 'none',
  transition: 'background-color var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard)',
};

const labelStyle: React.CSSProperties = {
  fontSize: 9,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  fontFamily: 'ui-monospace, monospace',
};
