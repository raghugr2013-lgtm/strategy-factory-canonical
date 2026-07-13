/**
 * COMMAND · Phase U.1 — StatusRail (posture-aware)
 * ----------------------------------------------------------------------------
 * Workstation : 28px bottom rail, 6 chips, telemetry shimmer
 * Tablet      : 28px bottom rail, 6 chips compressed, no shimmer
 * Briefing    : hidden (replaced by status pill in CommandBar)
 *
 * Reads the existing backend endpoints in a posture-aware polling cadence:
 *   /api/llm/diagnostics      (every 5/10/30s)
 *   /api/llm/runner-state     (every 8/15s, briefing pulls on demand)
 *   /api/health               (every 5/10/30s)
 *
 * Each endpoint is best-effort — failures degrade the chip to amber rather
 * than crashing. Operator visibility is the goal.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { API_URL as BACKEND } from '../../services/api';


const INITIAL = {
  orch:   { tone: 'amber',  label: 'orch',     hint: 'init…' },
  ingest: { tone: 'amber',  label: 'ingest',   hint: 'init…' },
  sched:  { tone: 'amber',  label: 'sched',    hint: 'dormant' },
  llm:    { tone: 'amber',  label: 'llm',      hint: '—' },
  govern: { tone: 'amber',  label: 'govern',   hint: '—' },
  kill:   { tone: 'green',  label: 'kill',     hint: 'armed' },
};

const POLL_MS = {
  workstation: { fast: 5000, slow: 8000 },
  tablet:      { fast: 10000, slow: 15000 },
  briefing:    { fast: 30000, slow: 30000 },
};

function chipClass(tone) {
  return `chip chip--${tone}`;
}

export function worstStatus(chips) {
  const order = ['red', 'amber', 'cyan', 'green'];
  let worstIdx = order.length;
  for (const k of Object.keys(chips)) {
    const idx = order.indexOf(chips[k].tone);
    if (idx >= 0 && idx < worstIdx) worstIdx = idx;
  }
  return order[Math.min(worstIdx, order.length - 1)];
}

export default function StatusRail({ posture, onChipsChange, onLlmActiveChange }) {
  const [chips, setChips] = useState(INITIAL);

  const tick = useCallback(async () => {
    const next = { ...chips };

    // /api/health
    try {
      const r = await fetch(`${BACKEND}/api/health`, { credentials: 'omit' });
      if (r.ok) {
        next.orch = { tone: 'green', label: 'orch',   hint: 'healthy' };
      } else {
        next.orch = { tone: 'red',   label: 'orch',   hint: `http ${r.status}` };
      }
    } catch (_) {
      next.orch = { tone: 'red', label: 'orch', hint: 'unreachable' };
    }

    // /api/llm/diagnostics
    try {
      const r = await fetch(`${BACKEND}/api/llm/diagnostics`, { credentials: 'omit' });
      if (r.ok) {
        const d = await r.json();
        const prov = d?.primary_provider || '—';
        const configured = !!(d?.providers?.[prov]?.configured);
        next.llm = {
          tone:  configured ? 'cyan' : 'amber',
          label: `llm:${prov}`,
          hint:  configured ? d?.providers?.[prov]?.model || '—' : 'no key',
        };
        const unknown = Array.isArray(d?.unknown_providers_referenced) && d.unknown_providers_referenced.length > 0;
        next.ingest = {
          tone:  unknown ? 'amber' : 'green',
          label: 'ingest',
          hint:  unknown ? 'unknown provider' : 'ready',
        };
        next.govern = {
          tone:  d?.llm_router_enabled ? 'amber' : 'green',
          label: 'govern',
          hint:  d?.llm_router_enabled ? 'router on' : 'governed',
        };
        next.sched = {
          tone:  d?.auto_failover_enabled ? 'amber' : 'green',
          label: 'sched',
          hint:  d?.auto_failover_enabled ? 'failover on' : 'dormant',
        };
      }
    } catch (_) {
      next.llm = { tone: 'amber', label: 'llm', hint: 'offline' };
    }

    // /api/llm/runner-state — drives the "AI just thought" throb
    try {
      const r = await fetch(`${BACKEND}/api/llm/runner-state`, { credentials: 'omit' });
      if (r.ok) {
        const d = await r.json();
        const active = d?.active_semaphores && Object.keys(d.active_semaphores).length > 0;
        if (onLlmActiveChange) onLlmActiveChange(!!active);
      }
    } catch (_) { /* noop */ }

    setChips(next);
    if (onChipsChange) onChipsChange(next);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posture]);

  useEffect(() => {
    let cancelled = false;
    const ms = POLL_MS[posture]?.fast ?? POLL_MS.workstation.fast;
    let interval;
    (async () => {
      await tick();
      if (cancelled) return;
      interval = setInterval(tick, ms);
    })();
    return () => { cancelled = true; if (interval) clearInterval(interval); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posture]);

  if (posture === 'briefing') return null; // briefing renders pill in CommandBar instead

  return (
    <footer className="cmd-shell__status" data-testid="cmd-status-rail">
      <div className="cmd-status__chips">
        {['orch', 'ingest', 'sched', 'llm', 'govern', 'kill'].map((k) => {
          const c = chips[k];
          return (
            <span
              key={k}
              className={chipClass(c.tone)}
              data-testid={`cmd-status-chip-${k}`}
              title={`${c.label}: ${c.hint}`}
            >
              <span
                className={`chip__dot ${c.tone === 'red' ? '' : 'cmd-dot--live'}`}
              />
              <span className="chip__label">{c.label}</span>
              {posture === 'workstation' && (
                <span style={{ color: 'var(--cmd-ink-2)' }}>· {c.hint}</span>
              )}
            </span>
          );
        })}
      </div>
      <span className="cmd-status__spacer" />
      {posture === 'workstation' && (
        <span className="cmd-flow-line" data-testid="cmd-status-flow" />
      )}
    </footer>
  );
}
