/*
 * LeftRailStub — E2 §3.1 · Phase 3 scaffolding.
 * A minimal vertical rail rendered by AppShell so the pre-auth chrome
 * matches the shape of the post-auth shell. Modules render at 40% opacity
 * with a lock icon; interaction is disabled per §9.3.
 *
 * Phase 4 will replace this with real modules + real routing.
 */
import {
  Activity, Bot, ClipboardCheck, Compass, GitBranch, Lock, Settings, Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuthStore } from '../workspace-state/authStore';

interface RailModule { key: string; label: string; icon: LucideIcon; }

const MODULES: RailModule[] = [
  { key: 'mission',   label: 'mission',   icon: Compass },
  { key: 'timeline',  label: 'timeline',  icon: Activity },
  { key: 'approvals', label: 'approvals', icon: ClipboardCheck },
  { key: 'workforce', label: 'workforce', icon: Bot },
  { key: 'workers',   label: 'workers',   icon: Users },
  { key: 'lineage',   label: 'lineage',   icon: GitBranch },
  { key: 'settings',  label: 'settings',  icon: Settings },
];

export const LeftRailStub: React.FC = () => {
  const stance = useAuthStore((s) => s.stance);
  const locked = stance !== 'authenticated';

  return (
    <nav
      data-testid="left-rail-stub"
      aria-label="Primary navigation"
      style={{
        display: 'flex', flexDirection: 'column', gap: 'var(--space-1)',
        width: 60,
        padding: 'var(--space-3) var(--space-2)',
        background: 'var(--surface-1)',
        borderRight: '1px solid var(--stroke-1)',
      }}
    >
      {MODULES.map((m) => {
        const I = m.icon;
        return (
          <div
            key={m.key}
            data-testid={`left-rail-${m.key}${locked ? '-locked' : ''}`}
            aria-disabled={locked ? true : undefined}
            title={locked ? `${m.label} · locked` : m.label}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 2,
              padding: '8px 4px',
              borderRadius: 'var(--radius-1)',
              color: locked ? 'var(--content-lo)' : 'var(--content-md)',
              opacity: locked ? 0.4 : 1,
              cursor: locked ? 'not-allowed' : 'pointer',
              pointerEvents: locked ? 'none' : 'auto',
              position: 'relative',
              transition: `background-color var(--dur-fast) var(--ease-standard)`,
            }}
          >
            <I size={18} strokeWidth={1.5} aria-hidden="true" />
            <span
              style={{
                fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em',
              }}
            >
              {m.label}
            </span>
            {locked && (
              <Lock
                size={8}
                aria-hidden="true"
                style={{ position: 'absolute', top: 4, right: 4, color: 'var(--content-lo)' }}
              />
            )}
          </div>
        );
      })}
    </nav>
  );
};
