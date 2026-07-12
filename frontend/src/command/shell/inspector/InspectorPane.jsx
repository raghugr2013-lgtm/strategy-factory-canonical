/**
 * COMMAND · Phase U.4 — Inspector slide-over chrome
 * ----------------------------------------------------------------------------
 * Right-side intelligence microscope. Posture behaviour:
 *
 *   workstation ≥ 1600  · default-open · 360px push pane
 *   workstation 1280–1599 · default-closed · 360px overlay (no push)
 *   tablet              · slide-over sheet 420px with backdrop
 *   briefing            · bottom sheet, full-screen, pull-down dismissal
 *
 * Keyboard: ⌘. toggles. Selection survives module navigation; closes
 * cleanly on Escape.
 */
import React, { useEffect } from 'react';
import { useInspector } from './InspectorProvider';
import { usePosture } from '../usePosture';
import { AttentionInspector, LlmCallInspector, StrategyInspector } from './views';

export default function InspectorPane({ onNavigate, fetchedAt }) {
  const { selection, open, close } = useInspector();
  const posture = usePosture();

  useEffect(() => {
    function onKey(e) {
      if (!open) return;
      if (e.key === 'Escape') close();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, close]);

  if (!open || !selection) return null;

  // Render the appropriate view
  let body = null;
  if (selection.type === 'attention') {
    body = (
      <AttentionInspector
        item={selection.item}
        fetchedAt={fetchedAt}
        onNavigate={(p) => {
          if (onNavigate) onNavigate(p);
          if (posture === 'briefing' || posture === 'tablet') close();
        }}
      />
    );
  } else if (selection.type === 'llm-call') {
    body = <LlmCallInspector call={selection.call} />;
  } else if (selection.type === 'strategy') {
    body = <StrategyInspector strategyId={selection.strategyId} />;
  } else if (selection.type === 'u6e-demo') {
    // U.6.e — chrome depth demo. Renders a representative mono body so
    // the operator can validate that the mono-label preservation
    // decision still reads correctly against the new gradient + ambient
    // chrome. This branch is reachable only via the /command-preview
    // U.6.e demo trigger; never enters operator flow.
    body = (
      <div data-testid="insp-u6e-demo">
        <div style={{
          fontFamily: 'JetBrains Mono', fontSize: 10,
          color: 'var(--cmd-ink-2)', letterSpacing: '0.14em',
          textTransform: 'uppercase', marginBottom: 8,
        }}>· about</div>
        <p style={{
          margin: '0 0 18px 0', fontSize: 12, lineHeight: 1.55,
          color: 'var(--cmd-ink-1)',
        }}>
          Inspector chrome adopts a calm vertical depth gradient,
          a left-cast ambient shadow on workstation, and a 1px inner
          top highlight. Every mono label here remains on JetBrains
          Mono — the mono-label preservation decision is preserved
          verbatim.
        </p>

        <div style={{
          fontFamily: 'JetBrains Mono', fontSize: 10,
          color: 'var(--cmd-cyan)', letterSpacing: '0.14em',
          textTransform: 'uppercase', marginBottom: 8,
        }}>· telemetry · representative</div>
        <dl style={{
          margin: '0 0 18px 0', fontFamily: 'JetBrains Mono', fontSize: 11,
          display: 'grid', gridTemplateColumns: '92px 1fr',
          rowGap: 6, columnGap: 12,
        }}>
          {[
            ['id',         'STR-2C1A47F9'],
            ['provider',   'openai · gpt-5.2'],
            ['posture',    'workstation'],
            ['lineage',    '· seed → mutate → certify'],
            ['updated',    '02:11:41Z · 2026-01-27'],
          ].map(([k, v]) => (
            <React.Fragment key={k}>
              <dt style={{ color: 'var(--cmd-ink-2)' }}>{k}</dt>
              <dd style={{ margin: 0, color: 'var(--cmd-ink-0)' }}>{v}</dd>
            </React.Fragment>
          ))}
        </dl>

        <div style={{
          fontFamily: 'JetBrains Mono', fontSize: 10,
          color: 'var(--cmd-amber)', letterSpacing: '0.14em',
          textTransform: 'uppercase', marginBottom: 8,
        }}>· audit · ref</div>
        <code style={{
          fontFamily: 'JetBrains Mono', fontSize: 11,
          color: 'var(--cmd-ink-1)', letterSpacing: '0.02em',
        }}>U.6.e · chrome · 2026-01-27T02:11:41Z</code>
      </div>
    );
  } else {
    body = (
      <div style={{ fontSize: 12, color: 'var(--cmd-ink-2)' }}>
        Unknown selection type: <code>{selection.type}</code>
      </div>
    );
  }

  const title = selection.type === 'attention' ? 'attention' :
                selection.type === 'llm-call' ? 'llm call' :
                selection.type === 'strategy' ? 'strategy' :
                selection.type === 'u6e-demo' ? selection.label || 'demo' :
                'inspector';

  return (
    <>
      {/* Backdrop on tablet+briefing only */}
      {(posture === 'tablet' || posture === 'briefing') && (
        <div
          data-testid="inspector-backdrop"
          onClick={close}
          style={{
            position: 'fixed', inset: 0, zIndex: 55,
            background: 'rgba(7, 10, 18, 0.55)',
            animation: 'cmd-fade-in var(--cmd-dur) var(--cmd-ease)',
          }}
        />
      )}

      <aside
        className="panel--inspector cmd-fade-in"
        data-testid="inspector-pane"
        data-cmd-posture={posture}
        style={{
          position: 'fixed',
          top: posture === 'briefing' ? 'auto'   : 'var(--cmd-bar-h)',
          right: 0,
          bottom: posture === 'briefing' ? 0 : 'var(--cmd-status-h)',
          left: posture === 'briefing' ? 0 : 'auto',
          width: posture === 'briefing' ? '100vw'
               : posture === 'tablet'   ? '420px'
               : 'var(--cmd-inspector-w)',
          maxHeight: posture === 'briefing' ? '85vh' : 'none',
          /* U.6.e — background governed by .panel--inspector cascade
             (panels.css base + identity.css depth refinement). Removing
             the inline restate unblocks the cascade; current rendering
             on premium-off is identical (both resolve to surface-2). */
          borderTop: posture === 'briefing' ? '1px solid var(--cmd-hairline)' : 'none',
          borderTopLeftRadius:  posture === 'briefing' ? 14 : 0,
          borderTopRightRadius: posture === 'briefing' ? 14 : 0,
          borderLeft: posture === 'briefing' ? 'none' : '1px solid var(--cmd-hairline)',
          zIndex: 56,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Inspector header — minimal, mono, microscope-like */}
        <header
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '12px 16px',
            borderBottom: '1px solid var(--cmd-hairline)',
            background: 'var(--cmd-surface-1)',
          }}
        >
          <span
            style={{
              fontFamily: 'JetBrains Mono', fontSize: 10,
              color: 'var(--cmd-cyan)', letterSpacing: '0.18em',
              textTransform: 'uppercase',
            }}
          >
            · inspector · {title}
          </span>
          <span style={{ flex: 1 }} />
          <button
            type="button"
            className="cmd-btn"
            data-testid="inspector-close"
            onClick={close}
            style={{ height: 22, padding: '0 8px', fontSize: 10 }}
          >
            close · esc
          </button>
        </header>

        <div
          style={{
            flex: 1, overflow: 'auto', padding: 16,
          }}
        >
          {body}
        </div>
      </aside>
    </>
  );
}
