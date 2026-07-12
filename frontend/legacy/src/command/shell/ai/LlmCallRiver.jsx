/**
 * COMMAND · Phase U.5.d — AI Workforce Live River
 * ============================================================================
 * The cinematic debut of the U.5.c eventRingStore. A premium institutional
 * telemetry stream that the operator can mount as a section of /c/ai.
 *
 * Posture contract:
 *   workstation : auto-live on first mount (if operator has never expressed
 *                 a preference) · 15 visible rows · full 5-col grid
 *   tablet      : auto-paused · 10 visible rows · 4-col (model column elided)
 *   briefing    : section is filtered out by modulesRegistry · NEVER renders
 *
 * Interaction:
 *   - Row click → existing LlmCallInspector (zero new inspector views)
 *   - LIVE/PAUSED pill toggles eventRingStore.setEnabled
 *   - "clear" purges ring + pending buffer (no destructive backend call)
 *
 * Doctrine respected:
 *   - One row revealed per drip tick (the store enforces this, not the UI)
 *   - Opacity-only entrance animation (cmd-fade-in 220ms)
 *   - No auto-scroll, no bounce, no urgency inflation
 *   - Premium frame (.panel--premium) for cinematic depth, not chrome noise
 */
import React, { useEffect, useMemo } from 'react';
import { useEventRing } from '../useEventRing';
import { eventRingStore } from '../eventRingStore';
import { usePosture } from '../usePosture';
import { useInspector } from '../inspector/InspectorProvider';

const VISIBLE_BY_POSTURE = {
  workstation: 15,
  tablet:      10,
  briefing:    0,
};

function timeShort(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  } catch (_) { return String(iso).slice(11, 19); }
}

function rowOutcomeTone(r) {
  const o = (r?.outcome || r?.status || '').toLowerCase();
  if (o === 'success' || o === 'ok')  return { tone: 'green', label: o || 'ok' };
  if (o === 'fail' || o === 'error')  return { tone: 'red',   label: o };
  if (o === '')                       return { tone: 'amber', label: 'unknown' };
  return { tone: 'amber', label: o };
}

export default function LlmCallRiver() {
  const posture  = usePosture();
  const snap     = useEventRing();
  const inspector = useInspector();
  const visibleN = VISIBLE_BY_POSTURE[posture] || 10;
  const rows     = useMemo(() => snap.ring.slice(0, visibleN), [snap.ring, visibleN]);

  // First-visit auto-live policy: workstation operators see the stream
  // immediately on first visit. Tablet operators must opt-in via the pill.
  // The check uses raw localStorage so we don't double-fire on every render.
  useEffect(() => {
    if (posture !== 'workstation') return;
    let pref = null;
    try { pref = localStorage.getItem('cmd-ui-river'); } catch (_) { pref = null; }
    if (pref === null && !snap.enabled) {
      eventRingStore.setEnabled(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posture]);

  const toggleLive = () => eventRingStore.setEnabled(!snap.enabled);
  const clear      = () => eventRingStore.clear();

  // Pill label semantics
  let pillKey;
  if (!snap.available && snap.enabled) pillKey = 'unavailable';
  else if (snap.enabled)               pillKey = 'live';
  else                                 pillKey = 'paused';

  return (
    <div className="llm-river panel--premium" data-testid="llm-call-river">
      <div className="llm-river__hd">
        <span className="llm-river__title cmd-font-display">AI Workforce</span>
        <span className="llm-river__sub">· live river</span>
        <div className="llm-river__hd-spacer" />

        {snap.pendingCount > 0 && (
          <span className="llm-river__pending" data-testid="river-pending">
            +{snap.pendingCount} pending
          </span>
        )}

        <button
          type="button"
          className={`llm-river__pill llm-river__pill--${pillKey}`}
          onClick={pillKey === 'unavailable' ? undefined : toggleLive}
          data-testid="river-toggle"
          data-state={pillKey}
          aria-pressed={snap.enabled}
          title={
            pillKey === 'live'        ? 'Streaming · click to pause' :
            pillKey === 'paused'      ? 'Paused · click to go live' :
            'Unavailable in this posture'
          }
        >
          <span className="llm-river__dot" />
          <span className="llm-river__pill-label">{pillKey}</span>
        </button>

        {snap.ring.length > 0 && (
          <button
            type="button"
            className="llm-river__clear"
            onClick={clear}
            data-testid="river-clear"
            title="Clear the visible ring (does not affect backend)"
          >
            clear
          </button>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="llm-river__empty" data-testid="river-empty">
          {snap.enabled && snap.available ? (
            <>
              <span className="llm-river__empty-strong">Awaiting first call</span>
              The river will populate as the runner invokes providers
            </>
          ) : !snap.available && snap.enabled ? (
            <>
              <span className="llm-river__empty-strong">Live river unavailable</span>
              This posture is intentionally calmer · open on a workstation to observe
            </>
          ) : (
            <>
              <span className="llm-river__empty-strong">Stream paused</span>
              Press the <b style={{ color: 'var(--cmd-cyan)' }}>PAUSED</b> pill above to begin observation
            </>
          )}
        </div>
      ) : (
        <ol className="llm-river__list" data-testid="river-list">
          {rows.map((r, i) => {
            const { tone, label } = rowOutcomeTone(r);
            return (
              <li
                key={`${r.ts || 'no-ts'}|${r.task || ''}|${i}`}
                className="llm-river__row"
                data-testid={`river-row-${i}`}
                onClick={() => inspector.inspect({ type: 'llm-call', call: r })}
              >
                <span className="llm-river__ts">{timeShort(r.ts)}</span>
                <span className="llm-river__task">{r.task || '—'}</span>
                <span className="llm-river__provider">
                  {r.provider || '—'}
                  <span className="llm-river__model">&nbsp;· {r.model || '—'}</span>
                </span>
                <span className={`chip chip--${tone} llm-river__outcome`}>
                  <span className="chip__dot" />
                  <span className="chip__label">{label}</span>
                </span>
                <span className="llm-river__lat">
                  {r.latency_ms != null ? `${r.latency_ms}ms` : '—'}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
