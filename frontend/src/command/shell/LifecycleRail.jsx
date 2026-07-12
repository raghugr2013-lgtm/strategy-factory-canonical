/**
 * COMMAND · M1 — Lifecycle Rail
 * ----------------------------------------------------------------------------
 * 10-step operator-journey GPS rail rendered between TopTabBar and the main
 * content area on every screen.
 *
 * States per pill:
 *   - done    (white-grey, light-green check on the number circle)
 *   - current (gold ring + glow)
 *   - next    (cyan dashed border, the immediately-following step)
 *   - future  (muted, hairline border)
 *   - hub     (Dashboard's special "all-surface" state — no current marked)
 *
 * Spec source: /app/memory/visual_approval_package/09_OPERATOR_LIFECYCLE.md
 * Future-phase reservation: 10 pills only (Phase 13/14/15 will append 5a/5b/5c).
 */
import React, { useState, useEffect } from 'react';
import { useRoute } from './router';
import { resolveActiveTabId } from './TopTabBar';

export const LIFECYCLE_STEPS = [
  { n:  1, label: 'Market Data',    tabId: 'data' },
  { n:  2, label: 'Generate',       tabId: 'auto-factory' },
  { n:  3, label: 'Mutate',         tabId: 'auto-factory' },
  { n:  4, label: 'Validate',       tabId: 'auto-factory' },
  { n:  5, label: 'Select',         tabId: 'auto-select' },
  { n:  6, label: 'Portfolio',      tabId: 'portfolio' },
  { n:  7, label: 'Master Bot',     tabId: 'auto-factory' },   // compile accordion lives in Auto Factory
  { n:  8, label: 'Trade Runner',   tabId: 'trade-runner' },
  { n:  9, label: 'Monitoring',     tabId: 'monitoring' },
  { n: 10, label: 'Deployment',     tabId: 'monitoring' },     // Cluster sub-tab post-M3
];

/** Per-tab state map: which step is "current" and what's "next" when on this tab. */
const TAB_TO_CURRENT_STEP = {
  'dashboard':    null,   // hub
  'data':         1,
  'execution':    8,      // Execution = Trade Runner-ish flow
  'auto-factory': 2,      // current spans 2/3/4
  'auto-select':  5,
  'portfolio':    6,
  'trade-runner': 8,
  'paper-exec':   4,
  'monitoring':   9,
  'explorer':     null,   // research; no current
  'live':         8,
  'workspace':    null,
  'pipeline':     null,
  'prop-firms':   null,
  'optimization': null,
  'saved':        null,
  'admin-users':  null,
};

/** Compute pill state given current step + index. */
function pillState(current, index) {
  if (current === null) return 'hub';
  // index is 0-based; current is 1-based step number
  if (index < current - 1) return 'done';
  if (index === current - 1) return 'current';
  if (index === current) return 'next';
  return 'future';
}

export default function LifecycleRail() {
  const { moduleId, navigate } = useRoute();
  // Track URL hash explicitly so the rail re-renders on section change
  // (hash updates do not propagate through React state on their own).
  const [hash, setHash] = useState(() =>
    (typeof window !== 'undefined' ? window.location.hash : '')
  );
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onChange = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onChange);
    window.addEventListener('popstate', onChange);
    return () => {
      window.removeEventListener('hashchange', onChange);
      window.removeEventListener('popstate', onChange);
    };
  }, []);
  const activeTabId = resolveActiveTabId(moduleId, hash);
  const current = TAB_TO_CURRENT_STEP[activeTabId] ?? null;
  const isHub   = activeTabId === 'dashboard';

  // Special states for auto-factory: marks 2/3/4 all as current.
  const isAutoFactory = activeTabId === 'auto-factory';

  const onJump = (step) => {
    // Look up the tab and navigate via the same router; section hash matched.
    const tab = (() => {
      // Inline mapping — same as TopTabBar's roster
      const TOP = {
        data:          { module: 'diag',       section: 'market-data' },
        'auto-factory':{ module: 'mutate',     section: 'factory-55' },
        'auto-select': { module: 'mutate',     section: 'auto-select' },
        portfolio:     { module: 'portfolio',  section: 'builder' },
        'trade-runner':{ module: 'exec',       section: 'runner' },
        monitoring:    { module: 'diag',       section: 'monitoring' },
      };
      return TOP[step.tabId];
    })();
    if (!tab) return;
    navigate(tab.module);
    if (tab.section && typeof window !== 'undefined') {
      window.history.replaceState({}, '', `${window.location.pathname}#${tab.section}`);
      setTimeout(() => {
        const el = document.querySelector(`[data-testid="cmd-section-${tab.module}-${tab.section}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 250);
      // Force a re-render of the rail via popstate dispatch (since replaceState doesn't fire popstate)
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    }
  };

  return (
    <nav className="cmd-lcrail" data-testid="lifecycle-rail" aria-label="Operator lifecycle">
      <div className="cmd-lcrail__inner">
        {/* Pre-compute Factory Zone bounds (steps 2-4) so we can render a
            single highlighted segmented progression instead of 3 independent
            gold pills. Operator immediately reads "you are inside the
            Strategy Factory pipeline". */}
        {LIFECYCLE_STEPS.map((step, idx) => {
          let state = pillState(current, idx);
          if (isHub) state = 'hub';
          if (isAutoFactory && (idx === 1 || idx === 2 || idx === 3)) state = 'factory-zone';
          if (isAutoFactory && idx === 4) state = 'next';
          if (isAutoFactory && idx === 0) state = 'done';
          const isFactoryStart = isAutoFactory && idx === 1;
          const isFactoryEnd   = isAutoFactory && idx === 3;
          const isInsideZone   = isAutoFactory && idx >= 1 && idx <= 3;
          return (
            <React.Fragment key={step.n}>
              {isFactoryStart && (
                <span className="cmd-lcrail__zone-label" data-testid="lcrail-zone-factory">
                  <span className="cmd-lcrail__zone-bracket">⟦</span>
                  <span className="cmd-lcrail__zone-text">STRATEGY FACTORY</span>
                </span>
              )}
              <button
                type="button"
                className={`cmd-lcrail__step cmd-lcrail__step--${state}${isInsideZone ? ' cmd-lcrail__step--inzone' : ''}${isFactoryStart ? ' cmd-lcrail__step--zonestart' : ''}${isFactoryEnd ? ' cmd-lcrail__step--zoneend' : ''}`}
                data-state={state}
                data-testid={`lcrail-step-${step.n}`}
                onClick={() => onJump(step)}
                aria-current={state === 'current' || state === 'factory-zone' ? 'step' : undefined}
              >
                <span className="cmd-lcrail__num">{step.n}</span>
                <span className="cmd-lcrail__label">{step.label}</span>
              </button>
              {isFactoryEnd && (
                <span className="cmd-lcrail__zone-bracket">⟧</span>
              )}
              {idx < LIFECYCLE_STEPS.length - 1 && (
                <span className={`cmd-lcrail__arrow cmd-lcrail__arrow--${state}${isInsideZone && idx < 3 ? ' cmd-lcrail__arrow--inzone' : ''}`} aria-hidden="true">→</span>
              )}
            </React.Fragment>
          );
        })}
        {isHub && (
          <span className="cmd-lcrail__hub-note">◆ Mission Control · all 10 steps surfaced below</span>
        )}
      </div>
    </nav>
  );
}
