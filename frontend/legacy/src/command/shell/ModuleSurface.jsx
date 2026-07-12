/**
 * COMMAND · Phase U.2 — ModuleSurface
 * ----------------------------------------------------------------------------
 * Renders a single module inside the COMMAND shell. The module is described
 * declaratively by the registry: header + list of sections, each wrapped in
 * a `.panel`. Sections are filtered by posture (some panels are workstation
 * only — see `only` field in the registry).
 *
 * For posture-restricted modules in briefing/tablet, a read-only badge is
 * shown in the header and an inert backdrop hint at the bottom.
 */
import React, { Suspense } from 'react';
import { MODULES_BY_ID, visibleSections, moduleAvailableInPosture } from './modulesRegistry';
import { IndicatorLegend } from '../../components/ui-asf';

// Phase U-1 (+S2): screens that surface verdict-coloured indicators get a
// one-line legend directly under the module title belt. Engineering can
// add screens to this set as composite indicators ship in U-2 / U-3.
const LEGEND_SCREENS = new Set(['dashboard', 'explorer', 'mutate']);

function SectionLoader({ title }) {
  return (
    <section className="panel" data-testid="cmd-section-loader">
      <div className="panel__hd">
        <span>· loading · {title}</span>
        <div className="panel__hd-spacer" />
        <span className="chip chip--cyan">
          <span className="chip__dot cmd-dot--live" />
          <span className="chip__label">streaming</span>
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="cmd-skel-line" style={{ width: '38%' }} />
        <span className="cmd-skel-line" style={{ width: '74%' }} />
        <span className="cmd-skel-line" style={{ width: '56%' }} />
      </div>
    </section>
  );
}

function SectionErrorBoundaryWrapper({ name, children }) {
  // Per-section error boundary so a single component crash does not take
  // down the whole module. Uses a class component because hooks cannot
  // catch render errors.
  class B extends React.Component {
    constructor(props) { super(props); this.state = { err: null }; }
    static getDerivedStateFromError(err) { return { err }; }
    componentDidCatch(err, info) {
      // eslint-disable-next-line no-console
      console.error(`[command:section:${name}]`, err, info);
    }
    render() {
      if (this.state.err) {
        return (
          <section className="panel" data-testid={`cmd-section-error-${name}`}>
            <div className="panel__hd">
              <span>· section error · {name}</span>
              <div className="panel__hd-spacer" />
              <span className="chip chip--red">
                <span className="chip__dot" />
                <span className="chip__label">failed</span>
              </span>
            </div>
            <pre
              style={{
                margin: 0, padding: 10, borderRadius: 6,
                background: 'var(--cmd-surface-0)',
                border: '1px solid var(--cmd-hairline)',
                color: 'var(--cmd-red)',
                fontFamily: 'JetBrains Mono', fontSize: 11,
                whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              }}
            >
              {String(this.state.err && (this.state.err.message || this.state.err))}
            </pre>
            <div style={{ fontSize: 11, color: 'var(--cmd-ink-2)', marginTop: 8 }}>
              This section failed to render. The rest of the module is unaffected.
              Use the legacy UI at <code>/</code> if you need this panel urgently.
            </div>
          </section>
        );
      }
      return this.props.children;
    }
  }
  return <B>{children}</B>;
}

export default function ModuleSurface({ moduleId, posture }) {
  const m = MODULES_BY_ID[moduleId];
  if (!m) {
    return (
      <div className="panel" data-testid="cmd-module-unknown">
        <div className="panel__hd">· unknown module · {moduleId}</div>
        <div style={{ fontSize: 12, color: 'var(--cmd-ink-2)' }}>
          Module ID was not recognised. Open the palette (⌘K) or the left rail to choose another.
        </div>
      </div>
    );
  }

  const allowedHere = moduleAvailableInPosture(m, posture);

  if (!allowedHere) {
    return (
      <section className="panel panel--tactical" data-testid={`cmd-module-blocked-${moduleId}`}>
        <div className="panel__hd">
          <m.Glyph />
          <span>· {m.label.toLowerCase()}</span>
          <div className="panel__hd-spacer" />
          <span className="chip chip--amber">
            <span className="chip__dot" />
            <span className="chip__label">workstation only</span>
          </span>
        </div>
        <p
          style={{
            margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--cmd-ink-1)',
          }}
        >
          The <b>{m.label}</b> module is intentionally not surfaced in&nbsp;
          <span style={{ color: 'var(--cmd-cyan)' }}>{posture}</span> mode.
          Open this site on a desktop or run&nbsp;
          <span className="kbd">window.__cmd.posture('workstation')</span>
          &nbsp;to override.
        </p>
        <p style={{ marginTop: 12, fontSize: 11, color: 'var(--cmd-ink-2)' }}>
          {m.subtitle}
        </p>
      </section>
    );
  }

  const sections = visibleSections(m, posture);

  return (
    <div data-testid={`cmd-module-${moduleId}`} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Module header (always tactical, signals "live module") */}
      <section className="panel panel--tactical panel--premium" data-testid={`cmd-module-header-${moduleId}`}>
        <div className="panel__hd">
          <m.Glyph />
          <span className="cmd-font-display">· {m.label.toLowerCase()}</span>
          {m.briefingReadOnly && (posture === 'briefing' || posture === 'tablet') && (
            <span className="chip chip--amber" style={{ marginLeft: 6 }}>
              <span className="chip__dot" />
              <span className="chip__label">read-only</span>
            </span>
          )}
          <div className="panel__hd-spacer" />
          <span className="chip">
            <span className="chip__label">{sections.length} section{sections.length === 1 ? '' : 's'}</span>
          </span>
        </div>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--cmd-ink-2)', lineHeight: 1.5 }}>
          {m.subtitle}
        </p>
      </section>

      {/* Phase U-1 (+S2) — verdict legend on screens that use composite
          indicators. Hidden in briefing posture to keep the briefing
          surface free of training affordances. */}
      {LEGEND_SCREENS.has(moduleId) && posture !== 'briefing' && (
        <IndicatorLegend screen={moduleId} />
      )}

      {/* Sections — each rendered inside its own panel + error boundary */}
      {sections.map((s) => (
        <SectionErrorBoundaryWrapper key={s.id} name={`${moduleId}:${s.id}`}>
          <section className="panel" data-testid={`cmd-section-${moduleId}-${s.id}`}>
            <div className="panel__hd">
              <span>· {s.title.toLowerCase()}</span>
            </div>
            <Suspense fallback={<SectionLoader title={s.title} />}>
              <s.Component />
            </Suspense>
          </section>
        </SectionErrorBoundaryWrapper>
      ))}
    </div>
  );
}
