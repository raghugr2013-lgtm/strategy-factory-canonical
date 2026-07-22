/*
 * EngineeringSurface — Phase-1 premium empty-state template.
 * refs UX-Review-2026-07-22 (Engineering Workspace) · DESIGN_FREEZE_v1.0.md §6
 *
 * Renders when an Engineering or Admin surface has been placed on the rail
 * but its live backend does not yet exist under Backend Feature Freeze
 * v1.1.0-stage4. The layout is deliberately structured to communicate:
 *   1) What the surface will present (capabilities list)
 *   2) Which Phase-2 endpoints will feed it (phase2Sources)
 *   3) Where the operator can go today for adjacent value (related)
 *
 * No fixture / mocked data is rendered — per the operator directive dated
 * 2026-07-22, Phase-1 surfaces show a professional "Scheduled for Phase 2"
 * state rather than placeholder content.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CircleDashed } from 'lucide-react';
import { ENGINEERING_SURFACES } from '../routing/navigation';

export const EngineeringSurface = ({ slug }) => {
  const meta = ENGINEERING_SURFACES[slug];

  if (!meta) {
    return (
      <section data-testid="engineering-surface-unknown"
               style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1200 }}>
        <h1 style={{ margin: 0, color: 'var(--content-hi)', fontSize: 'var(--font-h2)', fontWeight: 400 }}>Unknown engineering surface.</h1>
        <p style={{ color: 'var(--content-md)' }}>The URL slug &quot;{slug}&quot; does not resolve to a registered surface.</p>
      </section>
    );
  }

  const Icon = meta.icon;

  return (
    <section data-testid={`engineering-surface-${slug}`}
             aria-labelledby={`eng-title-${slug}`}
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1200 }}>
      {/* Eyebrow — group / title / phase tag */}
      <div data-testid={`engineering-eyebrow-${slug}`}
           style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
        <span style={eyebrowLabel}>{meta.group}</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrowLabel, color: 'var(--content-hi)' }}>{meta.title}</span>
        <span style={{ marginLeft: 'auto' }}>
          <PhaseTag />
        </span>
      </div>

      {/* Headline + briefing */}
      <h1 id={`eng-title-${slug}`}
          data-testid={`engineering-headline-${slug}`}
          style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        {meta.headline}
      </h1>
      <p data-testid={`engineering-briefing-${slug}`}
         style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 780, fontSize: 'var(--font-body-md)', lineHeight: 1.6, color: 'var(--content-md)' }}>
        {meta.briefing}
      </p>

      {/* Two-column: PHASE 2 SCOPE + LIVE DATA SOURCES */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
        {/* Capabilities */}
        <div data-testid={`engineering-scope-${slug}`}
             style={panelStyle}>
          <div style={panelHeader}>
            <Icon size={14} strokeWidth={1.5} color="var(--sig-info)" />
            <span>Phase 2 scope</span>
          </div>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {meta.capabilities.map((c, idx) => (
              <li key={idx}
                  data-testid={`engineering-capability-${slug}-${idx}`}
                  style={{ display: 'flex', gap: 'var(--space-3)', padding: 'var(--space-2) 0', borderTop: idx === 0 ? 'none' : '1px solid var(--stroke-1)' }}>
                <CircleDashed size={14} strokeWidth={1.5} color="var(--content-lo)" style={{ marginTop: 3, flexShrink: 0 }} />
                <span style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.5 }}>{c}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Phase-2 sources */}
        <div data-testid={`engineering-sources-${slug}`}
             style={panelStyle}>
          <div style={panelHeader}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--sig-warn)' }} />
            <span>Live data sources</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            {meta.phase2Sources.map((s, idx) => (
              <code key={idx}
                    data-testid={`engineering-source-${slug}-${idx}`}
                    style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)', fontFamily: 'var(--font-mono, ui-monospace, monospace)', lineHeight: 1.5, wordBreak: 'break-word' }}>
                {s}
              </code>
            ))}
          </div>
          <div style={{ marginTop: 'var(--space-3)', paddingTop: 'var(--space-3)', borderTop: '1px solid var(--stroke-1)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Held under<br />Backend Feature Freeze · v1.1.0-stage4
          </div>
        </div>
      </div>

      {/* Related */}
      {meta.related?.length > 0 && (
        <div data-testid={`engineering-related-${slug}`} style={{ marginTop: 'var(--space-5)' }}>
          <div style={{ ...eyebrowLabel, marginBottom: 'var(--space-3)' }}>Available today</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            {meta.related.map((r, idx) => (
              <Link key={idx}
                    to={r.path}
                    data-testid={`engineering-related-${slug}-${idx}`}
                    style={pillStyle}>
                <span>{r.label}</span>
                <ArrowRight size={12} strokeWidth={1.5} />
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};

const PhaseTag = () => (
  <span data-testid="phase-tag-phase-2"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '3px 10px',
          borderRadius: 999,
          background: 'color-mix(in oklab, var(--sig-info) 12%, transparent)',
          border: '1px solid color-mix(in oklab, var(--sig-info) 40%, transparent)',
          color: 'var(--sig-info)',
          fontSize: 'var(--font-caption)',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
        }}>
    <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor' }} />
    Scheduled for Phase 2
  </span>
);

const eyebrowLabel = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
};

const panelStyle = {
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-1)',
  borderRadius: 'var(--radius-3)',
  padding: 'var(--space-4)',
};

const panelHeader = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  marginBottom: 'var(--space-3)',
  paddingBottom: 'var(--space-3)',
  borderBottom: '1px solid var(--stroke-1)',
};

const pillStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '5px 12px',
  borderRadius: 999,
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-2)',
  color: 'var(--content-md)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  textDecoration: 'none',
  transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
};
