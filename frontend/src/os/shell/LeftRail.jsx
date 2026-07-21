/*
 * LeftRail — top-level surface navigation.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · D8 §3.5
 */
import React from 'react';
import { NavLink } from 'react-router-dom';
import { ROUTES } from '../routing/routes';

export const LeftRail = () => (
  <nav data-testid="left-rail"
       aria-label="Primary"
       style={{ padding: 'var(--space-4)' }}>
    <div style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 'var(--space-4)' }}>
      Navigation
    </div>
    <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {ROUTES.map((r) => (
        <li key={r.path} style={{ marginBottom: 'var(--space-1)' }}>
          <NavLink to={r.path}
                   data-testid={r.testId}
                   end
                   style={({ isActive }) => ({
                     display: 'flex',
                     alignItems: 'center',
                     gap: 'var(--space-2)',
                     padding: 'var(--space-2) var(--space-3)',
                     color: isActive ? 'var(--content-hi)' : 'var(--content-md)',
                     background: isActive ? 'var(--surface-2)' : 'transparent',
                     borderLeft: isActive ? '2px solid var(--sig-info)' : '2px solid transparent',
                     borderRadius: 'var(--radius-1)',
                     fontSize: 'var(--font-body-sm)',
                     letterSpacing: '0.08em',
                     textTransform: 'uppercase',
                     textDecoration: 'none',
                     transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard)',
                   })}>
            <r.icon size={14} strokeWidth={1.5} />
            <span>{r.label}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  </nav>
);
