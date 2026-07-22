/*
 * LeftRail — top-level surface navigation, grouped for Phase-1 Engineering.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · UX-Review-2026-07-22
 *
 * Three groups: MISSION CONTROL · ENGINEERING · ADMIN. The ADMIN group is
 * role-gated. Sprint 3 Phase-2 hydrates the real role from
 * `/api/auth/me` at login time (see authStore.login) so the Admin group
 * is only visible for role === 'admin'. When the app is running in the
 * fixture auth mode (no live backend), we fall back to the historical
 * email-regex heuristic so the developer preview still surfaces the
 * Admin section.
 */
import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { NAV_GROUPS } from '../routing/navigation';
import { useAuthStore } from '../workspace-state/authStore';

const isAdminByEmail = (email) => !!email && /(^admin@|admin)/i.test(email);

/**
 * roleFor — derive the effective role.
 *
 *   live auth  → the role returned by /api/auth/me (source of truth).
 *   fixture    → email-regex heuristic (backwards-compat for dev preview).
 *   anonymous  → 'operator' (safe default; Admin group hidden).
 */
const roleFor = ({ role, email, authMode }) => {
  if (role) return role;
  if (authMode === 'fixture' && isAdminByEmail(email)) return 'admin';
  return 'operator';
};

// Flat list of every deep-link item across all groups. Used to disambiguate
// active-state when a deep-link's pathname == a canonical item's pathname.
const DEEP_LINK_PATHS = NAV_GROUPS
  .flatMap((g) => g.items)
  .filter((i) => i.path.includes('?'))
  .map((i) => i.path);

const isActivePath = (loc, itemPath) => {
  // Deep-link item — require exact pathname + search match.
  if (itemPath.includes('?')) {
    return (loc.pathname + loc.search) === itemPath;
  }
  // Canonical item — active if pathname matches AND no sibling deep-link
  // rooted at the same pathname currently owns the query string.
  const pathnameMatches = loc.pathname === itemPath || loc.pathname.startsWith(itemPath + '/');
  if (!pathnameMatches) return false;
  const currentUrl = loc.pathname + loc.search;
  const capturedByDeepLink = DEEP_LINK_PATHS.some(
    (dp) => dp.startsWith(itemPath + '?') && dp === currentUrl,
  );
  return !capturedByDeepLink;
};

export const LeftRail = () => {
  const email = useAuthStore((s) => s.email);
  const role = useAuthStore((s) => s.role);
  const authMode = useAuthStore((s) => s.authMode);
  const effectiveRole = roleFor({ role, email, authMode });
  const location = useLocation();

  return (
    <nav data-testid="left-rail"
         aria-label="Primary"
         style={{ padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
      {NAV_GROUPS
        .filter((g) => !g.roles || g.roles.includes(effectiveRole))
        .map((group) => (
          <div key={group.id} data-testid={group.testId}>
            <div style={groupHeaderStyle}>{group.label}</div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {group.items.map((item) => (
                <li key={item.path} style={{ marginBottom: 'var(--space-1)' }}>
                  <NavLink to={item.path}
                           data-testid={item.testId}
                           end={!item.path.includes('?')}
                           style={() => {
                             const active = isActivePath(location, item.path);
                             return {
                               display: 'flex',
                               alignItems: 'center',
                               gap: 'var(--space-2)',
                               padding: 'var(--space-2) var(--space-3)',
                               color: active ? 'var(--content-hi)' : 'var(--content-md)',
                               background: active ? 'var(--surface-2)' : 'transparent',
                               borderLeft: active ? '2px solid var(--sig-info)' : '2px solid transparent',
                               borderRadius: 'var(--radius-1)',
                               fontSize: 'var(--font-body-sm)',
                               letterSpacing: '0.08em',
                               textTransform: 'uppercase',
                               textDecoration: 'none',
                               transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard)',
                             };
                           }}>
                    <item.icon size={14} strokeWidth={1.5} />
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
    </nav>
  );
};

const groupHeaderStyle = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  marginBottom: 'var(--space-3)',
  paddingBottom: 'var(--space-2)',
  borderBottom: '1px solid var(--stroke-1)',
};
