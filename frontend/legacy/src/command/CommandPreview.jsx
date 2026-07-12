/**
 * COMMAND · Phase U.0 + U.1 — Foundations & Shell Preview
 * ----------------------------------------------------------------------------
 * Renders the full COMMAND shell (CommandBar + LeftRail + StatusRail) and
 * inside it shows every primitive shipped in U.0 (tokens, panels, chips,
 * motion) plus the U.1 LineageStrip + LineageInline widgets.
 *
 * Routed at /command-preview. No auth. No live operator data. Backend
 * endpoints are read for status chips and runner state via REACT_APP_BACKEND_URL.
 *
 * This page is the operator's "did we ship correctly?" surface.
 */
import React, { useEffect, useState } from 'react';
import BrandMark from './BrandMark';
import CommandShell from './shell/CommandShell';
import LineageStrip, { LineageInline, mockLineage } from './shell/LineageStrip';
import { useInspector } from './shell/inspector/InspectorProvider';

function InspectorDemoTrigger() {
  // U.6.e — demo trigger so the operator can open the inspector from
  // /command-preview without authenticating. Renders a single mono
  // button that opens an unknown-type selection (Inspector renders a
  // mono fallback view), letting us audit the chrome depth refinement
  // (gradient + ambient cast + inner top highlight) and verify that
  // the mono-label preservation decision still reads correctly.
  const insp = useInspector();
  return (
    <button
      type="button"
      data-testid="u6e-open-inspector"
      className="cmd-btn"
      onClick={() => insp.inspect({
        type: 'u6e-demo',
        label: 'chrome depth refinement',
      })}
      style={{ height: 26, padding: '0 12px', fontSize: 11 }}
    >
      open inspector · u.6.e demo
    </button>
  );
}

function Swatch({ name, varName, hex }) {  return (
    <div
      className="panel"
      style={{ padding: 10, display: 'flex', alignItems: 'center', gap: 10 }}
      data-testid={`swatch-${name}`}
    >
      <span
        style={{
          width: 26, height: 26, borderRadius: 4,
          background: `var(${varName})`,
          border: '1px solid var(--cmd-hairline)',
          flexShrink: 0,
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span style={{ fontSize: 11, color: 'var(--cmd-ink-0)', fontWeight: 600 }}>{name}</span>
        <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono', color: 'var(--cmd-ink-2)' }}>
          {hex}
        </span>
      </div>
    </div>
  );
}

export default function CommandPreview() {
  const [throbKey, setThrobKey] = useState(0);

  // Force COMMAND mode on this page only.
  useEffect(() => {
    const body = document.body;
    const had = body.getAttribute('data-ui');
    body.setAttribute('data-ui', 'command');
    return () => {
      if (had) body.setAttribute('data-ui', had);
      else body.removeAttribute('data-ui');
    };
  }, []);

  const swatches = [
    ['surface-0',  '--cmd-surface-0',  '#070A12'],
    ['surface-1',  '--cmd-surface-1',  '#0E141F'],
    ['surface-2',  '--cmd-surface-2',  '#141B28'],
    ['surface-3',  '--cmd-surface-3',  '#1A2334'],
    ['hairline',   '--cmd-hairline',   '#1F2A3B'],
    ['ink-0',      '--cmd-ink-0',      '#F2F5F9'],
    ['ink-1',      '--cmd-ink-1',      '#B6C0CC'],
    ['ink-2',      '--cmd-ink-2',      '#6B7686'],
    ['cyan',       '--cmd-cyan',       '#00D4FF'],
    ['green',      '--cmd-green',      '#00E676'],
    ['amber',      '--cmd-amber',      '#FFB020'],
    ['red',        '--cmd-red',        '#FF4D6D'],
    ['violet',     '--cmd-violet',     '#7C5CFF'],
  ];

  const lineage = mockLineage('STR-2C1A47F9');

  return (
    <CommandShell defaultActiveId="dashboard" user={{ email: 'operator@local' }}>
      <div data-testid="command-preview-root" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        {/* Hero strip */}
        <section className="panel panel--tactical" data-testid="section-hero">
          <div className="panel__hd">
            <BrandMark size={18} />
            <span>· u.0 + u.1 · foundations & shell</span>
            <div className="panel__hd-spacer" />
            <span className="chip chip--cyan">
              <span className="chip__dot cmd-dot--live" />
              <span className="chip__label">live preview</span>
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--cmd-ink-1)' }}>
            This is the COMMAND shell running in real time — bar above, rail at left
            (workstation only), status chips below (tablet+workstation), and the
            mission pane in the middle. Resize the window: at &lt;1280px the rail
            collapses to a drawer (tablet posture), at &lt;768px the shell goes
            into briefing posture and the status rail collapses into a single pill
            in the bar. Try{' '}
            <span className="kbd">⌘K</span> to open the palette,{' '}
            <span className="kbd">⌘⇧F</span> to toggle focus mode.
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 4 }}>
            <LineageInline lineage={lineage} />
            <span className="chip">
              <span className="chip__label">posture · auto</span>
            </span>
            <button
              className="cmd-btn"
              data-testid="cmd-preview-throb-btn"
              onClick={() => setThrobKey((k) => k + 1)}
              style={{ height: 24 }}
            >
              Fire AI throb
            </button>
          </div>
        </section>

        {/* Lineage hero strip — U.1 widget */}
        <LineageStrip lineage={lineage} height={150} onNodeClick={(n) => {
          // eslint-disable-next-line no-console
          console.log('[lineage] node clicked', n);
        }} />

        {/* Tokens swatch */}
        <section className="panel" data-testid="section-tokens">
          <div className="panel__hd">
            <span>· tokens · command palette</span>
            <div className="panel__hd-spacer" />
            <span className="chip" data-testid="chip-tokens-count">
              <span className="chip__label">{swatches.length} tokens</span>
            </span>
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: 10,
            }}
          >
            {swatches.map(([n, v, h]) => (
              <Swatch key={n} name={n} varName={v} hex={h} />
            ))}
          </div>
        </section>

        {/* Panels showcase */}
        <section className="panel" data-testid="section-base-panel">
          <div className="panel__hd">
            <span>· panel · base · throb · ribbon</span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="cmd-btn" data-testid="cmd-btn-default">Default</button>
            <button className="cmd-btn cmd-btn--cyan" data-testid="cmd-btn-cyan">Cyan action</button>
            <span className="kbd">⌘K</span>
            <span className="kbd">⌘B</span>
            <span className="kbd">⌘⇧F</span>
            <span style={{ flex: 1 }} />
            <span
              key={throbKey}
              className="cmd-throb cmd-throb--fire"
              data-testid="cmd-throb-target"
              style={{ width: 6, height: 14 }}
            />
            <span style={{ fontSize: 11, color: 'var(--cmd-ink-2)' }}>
              cmd-throb · 280ms one-shot
            </span>
          </div>
        </section>

        {/* Posture / responsive cheat sheet */}
        <section className="panel" data-testid="section-posture">
          <div className="panel__hd">
            <span>· responsive · postures</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            {[
              ['workstation', '≥ 1280', 'Full shell · bar · rail · status · inspector'],
              ['tablet',      '768 – 1279', 'Bar 40px · rail → drawer · status compressed'],
              ['briefing',    '≤ 767', 'Bar 44px · status → pill · only briefing modules'],
            ].map(([name, bp, desc]) => (
              <div key={name} className="panel" style={{ padding: 12 }} data-testid={`posture-card-${name}`}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{
                    fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-cyan)',
                    letterSpacing: '0.06em', textTransform: 'uppercase',
                  }}>{name}</span>
                  <span className="kbd">{bp}</span>
                </div>
                <p style={{ margin: 0, fontSize: 12, color: 'var(--cmd-ink-2)', lineHeight: 1.5 }}>{desc}</p>
              </div>
            ))}
          </div>
          <p style={{ marginTop: 10, fontSize: 11, color: 'var(--cmd-ink-2)' }}>
            Operator override: <span className="kbd">window.__cmd.posture('tablet'|'workstation'|'briefing'|null)</span>
          </p>
        </section>

        {/* U.6.d preview · Briefing PostureTile premium frame ──
            Doctrine demo only. Mirrors the exact markup PostureTile uses
            in Mission Briefing zone 2 so the operator can review the
            premium-frame adoption without authenticating into /c/briefing.
            Left side = old flat .panel rendering (for visual contrast).
            Right side = new .panel--premium .panel--briefing-tile frame. */}
        <section className="panel panel--premium" data-testid="section-u6d-tile-frame">
          <div className="panel__hd">
            <span className="cmd-font-display">· u.6.d · briefing tile · premium frame</span>
          </div>
          <p style={{ margin: '0 0 14px 0', fontSize: 12, color: 'var(--cmd-ink-2)', lineHeight: 1.55 }}>
            The 4 posture tiles in Mission Briefing zone 2 adopt depth +
            border but suppress the top-edge reflection — keeping the 3
            hero strips (attention · mission · audit) as the briefing's
            operational voice. Below: left row is the old flat tile, right
            row is the new premium-framed tile.
          </p>

          {/* U.6.e — Inspector chrome depth refinement demo trigger. */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14,
            padding: '10px 12px', borderRadius: 6,
            background: 'var(--cmd-surface-1)',
            border: '1px solid var(--cmd-hairline)',
          }}>
            <span style={{
              fontFamily: 'JetBrains Mono', fontSize: 10,
              color: 'var(--cmd-cyan)', letterSpacing: '0.14em',
              textTransform: 'uppercase',
            }}>· u.6.e · inspector chrome</span>
            <span style={{ flex: 1, fontSize: 11, color: 'var(--cmd-ink-2)' }}>
              Vertical depth gradient · workstation ambient cast · mono labels preserved.
            </span>
            <InspectorDemoTrigger />
          </div>
          <div
            className="u6d-preview-grid"
            style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16,
              alignItems: 'stretch',
            }}
          >
            {/* OLD — flat .panel */}
            <div>
              <div style={{
                fontFamily: 'JetBrains Mono', fontSize: 10,
                color: 'var(--cmd-ink-2)', letterSpacing: '0.14em',
                textTransform: 'uppercase', marginBottom: 8,
              }}>· before · flat panel</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                {[
                  ['ai workforce', 'openai · ready', '3 active calls', 'cyan'],
                  ['system pulse', 'healthy',       'p95 220ms',      'green'],
                  ['governance',   '2 to review',   'within slo',     'amber'],
                  ['ingestion',    'idle',          'last 12m ago',   'ink-1'],
                ].map(([label, head, sub, tone], i) => (
                  <div key={i} className="panel"
                       style={{ padding: '14px 16px', minHeight: 96 }}
                       data-testid={`u6d-old-tile-${i}`}>
                    <span style={{
                      fontFamily: 'JetBrains Mono', fontSize: 10,
                      color: 'var(--cmd-ink-2)', letterSpacing: '0.14em',
                      textTransform: 'uppercase',
                    }}>{label}</span>
                    <div style={{ marginTop: 6 }}>
                      <span style={{
                        fontFamily: 'JetBrains Mono', fontSize: 22,
                        color: `var(--cmd-${tone})`, letterSpacing: '-0.01em',
                        fontWeight: 500,
                      }}>{head}</span>
                    </div>
                    <span style={{
                      marginTop: 6, display: 'block', fontSize: 11,
                      color: 'var(--cmd-ink-1)', fontFamily: 'JetBrains Mono',
                      letterSpacing: '0.04em',
                    }}>{sub}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* NEW — .panel--premium .panel--briefing-tile */}
            <div>
              <div style={{
                fontFamily: 'JetBrains Mono', fontSize: 10,
                color: 'var(--cmd-cyan)', letterSpacing: '0.14em',
                textTransform: 'uppercase', marginBottom: 8,
              }}>· after · premium tile</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                {[
                  ['ai workforce', 'openai · ready', '3 active calls', 'cyan'],
                  ['system pulse', 'healthy',       'p95 220ms',      'green'],
                  ['governance',   '2 to review',   'within slo',     'amber'],
                  ['ingestion',    'idle',          'last 12m ago',   'ink-1'],
                ].map(([label, head, sub, tone], i) => (
                  <div key={i} className="panel panel--premium panel--briefing-tile"
                       style={{ padding: '14px 16px', minHeight: 96 }}
                       data-testid={`u6d-new-tile-${i}`}>
                    <span style={{
                      fontFamily: 'JetBrains Mono', fontSize: 10,
                      color: 'var(--cmd-ink-2)', letterSpacing: '0.14em',
                      textTransform: 'uppercase',
                    }}>{label}</span>
                    <div style={{ marginTop: 6 }}>
                      <span style={{
                        fontFamily: 'JetBrains Mono', fontSize: 22,
                        color: `var(--cmd-${tone})`, letterSpacing: '-0.01em',
                        fontWeight: 500,
                      }}>{head}</span>
                    </div>
                    <span style={{
                      marginTop: 6, display: 'block', fontSize: 11,
                      color: 'var(--cmd-ink-1)', fontFamily: 'JetBrains Mono',
                      letterSpacing: '0.04em',
                    }}>{sub}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </CommandShell>
  );
}
