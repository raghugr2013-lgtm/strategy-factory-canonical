/**
 * COMMAND · Phase U.1 — Posture detector
 * ----------------------------------------------------------------------------
 * Three operational postures (locked by the Responsive Doctrine):
 *   • workstation — desktop / large laptop / iPad Pro 12.9 landscape
 *   • tablet      — regular iPad, smaller laptops, larger phones in landscape
 *   • briefing    — mobile portrait / small tablets in portrait
 *
 * Detection rule:
 *   width ≥ 1280  → workstation
 *   width ≥  768  → tablet
 *   otherwise     → briefing
 *
 * The hook writes the resolved posture onto `document.body[data-cmd-posture]`
 * so CSS in panels.css / shell.css can branch on it without React props
 * threading. Operator can override via `window.__cmd.posture(name)` — the
 * override survives until cleared with `window.__cmd.posture(null)`.
 */
import { useEffect, useState } from 'react';

const KEY_OVERRIDE = 'cmd-ui-posture-override';

function resolveFromWidth(w) {
  if (w >= 1280) return 'workstation';
  if (w >= 768)  return 'tablet';
  return 'briefing';
}

function applyPosture(p) {
  if (typeof document === 'undefined') return;
  document.body.setAttribute('data-cmd-posture', p);
}

function readOverride() {
  try {
    const v = localStorage.getItem(KEY_OVERRIDE);
    if (v === 'workstation' || v === 'tablet' || v === 'briefing') return v;
  } catch (_) { /* noop */ }
  return null;
}

export function usePosture() {
  const [posture, setPosture] = useState(() => {
    if (typeof window === 'undefined') return 'workstation';
    return readOverride() || resolveFromWidth(window.innerWidth);
  });

  useEffect(() => {
    applyPosture(posture);
  }, [posture]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    let raf = 0;
    const onResize = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const override = readOverride();
        if (override) {
          setPosture(override);
        } else {
          setPosture(resolveFromWidth(window.innerWidth));
        }
      });
    };
    window.addEventListener('resize', onResize);

    // Expose operator override hook
    window.__cmd = window.__cmd || {};
    window.__cmd.posture = (name) => {
      if (name === null) {
        try { localStorage.removeItem(KEY_OVERRIDE); } catch (_) {}
        const next = resolveFromWidth(window.innerWidth);
        setPosture(next);
        // eslint-disable-next-line no-console
        console.info(`[command] posture override cleared → ${next}`);
        return next;
      }
      if (!['workstation', 'tablet', 'briefing'].includes(name)) {
        // eslint-disable-next-line no-console
        console.warn('[command] posture must be workstation|tablet|briefing|null');
        return null;
      }
      try { localStorage.setItem(KEY_OVERRIDE, name); } catch (_) {}
      setPosture(name);
      // eslint-disable-next-line no-console
      console.info(`[command] posture override → ${name}`);
      return name;
    };

    return () => {
      window.removeEventListener('resize', onResize);
      cancelAnimationFrame(raf);
    };
  }, []);

  return posture;
}
