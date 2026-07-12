/**
 * COMMAND · Phase U.1 — LeftRail (skeleton)
 * ----------------------------------------------------------------------------
 * Workstation-only navigation rail. Tablet renders nothing (replaced by a
 * drawer in U.2). Briefing renders nothing.
 *
 * U.1 ships the visual skeleton only — the icons do not route anywhere
 * yet. Active state is local (operator can click to "preview" how the
 * rail will feel), but no module mounts behind the rail in this phase.
 *
 * Module-to-icon mapping is locked here so U.2's router can just import
 * the same array.
 */
import React, { useState } from 'react';
import {
  GlyphDashboard, GlyphLab, GlyphExplorer, GlyphMutate, GlyphPortfolio,
  GlyphPropFirm, GlyphExec, GlyphAI, GlyphDiag, GlyphGovernance,
} from './Glyphs';

export const MODULES = [
  { id: 'dashboard',  label: 'Dashboard',         Glyph: GlyphDashboard,  briefing: true,  tablet: true  },
  { id: 'lab',        label: 'Research Lab',      Glyph: GlyphLab,        briefing: false, tablet: false },
  { id: 'explorer',   label: 'Strategy Explorer', Glyph: GlyphExplorer,   briefing: false, tablet: true  },
  { id: 'mutate',     label: 'Mutation Engine',   Glyph: GlyphMutate,     briefing: false, tablet: false },
  { id: 'portfolio',  label: 'Portfolio OS',      Glyph: GlyphPortfolio,  briefing: true,  tablet: true  },
  { id: 'propfirm',   label: 'Prop Firm Intel',   Glyph: GlyphPropFirm,   briefing: false, tablet: true  },
  { id: 'exec',       label: 'Execution Center',  Glyph: GlyphExec,       briefing: true,  tablet: true  },
  { id: 'ai',         label: 'AI Workforce',      Glyph: GlyphAI,         briefing: false, tablet: true  },
  { id: 'diag',       label: 'Diagnostics',       Glyph: GlyphDiag,       briefing: true,  tablet: true  },
  { id: 'governance', label: 'Governance',        Glyph: GlyphGovernance, briefing: false, tablet: false },
];

export default function LeftRail({ posture, activeId, onSelect }) {
  // U.1 only renders the rail on workstation. Tablet/briefing handle
  // navigation via menu button + sheet (added in this phase too).
  const [hovered, setHovered] = useState(false);
  if (posture !== 'workstation') return null;

  const open = hovered;
  return (
    <aside
      className={`cmd-shell__rail${open ? ' cmd-shell__rail--open' : ''}`}
      data-testid="cmd-left-rail"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <nav
        aria-label="Modules"
        style={{ display: 'flex', flexDirection: 'column', paddingTop: 10 }}
      >
        {MODULES.map((m) => {
          const isActive = activeId === m.id;
          return (
            <button
              key={m.id}
              type="button"
              className={`cmd-rail__item${isActive ? ' cmd-rail__item--active' : ''}`}
              onClick={() => onSelect && onSelect(m.id)}
              data-testid={`cmd-rail-${m.id}`}
              title={m.label}
              aria-current={isActive ? 'page' : undefined}
              aria-label={m.label}
            >
              <span className="cmd-rail__glyph" aria-hidden="true">
                <m.Glyph />
              </span>
              <span className="cmd-rail__label">{m.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
