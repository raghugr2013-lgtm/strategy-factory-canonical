/* eslint-disable */
/**
 * COMMAND · Phase U.0 — Dev Toggle
 * ----------------------------------------------------------------------------
 * Foundation-only utility. Exposes a single dev-tools hook:
 *
 *     window.__cmd.on()       enable [data-ui="command"]
 *     window.__cmd.off()      restore legacy
 *     window.__cmd.focus()    toggle [data-ui-focus="on"]
 *     window.__cmd.state()    log current state
 *
 * Also reads ?cmd=1 / ?cmd=0 from the URL for shareable preview links
 * AND localStorage so the preference survives a refresh.
 *
 * NO operator-facing UI is added in U.0 — the toggle button arrives in
 * U.1 alongside the Command Bar.
 */

const KEY = 'cmd-ui-mode';
const FOCUS_KEY = 'cmd-ui-focus';

function applyMode(on) {
  const body = document.body;
  if (!body) return;
  if (on) {
    body.setAttribute('data-ui', 'command');
  } else {
    body.removeAttribute('data-ui');
  }
}

function applyFocus(on) {
  const body = document.body;
  if (!body) return;
  if (on) {
    body.setAttribute('data-ui-focus', 'on');
  } else {
    body.removeAttribute('data-ui-focus');
  }
}

export function installCommandToggle() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  // URL override wins (?cmd=1, ?cmd=0)
  const params = new URLSearchParams(window.location.search);
  const urlCmd = params.get('cmd');

  let initialOn;
  if (urlCmd === '1') {
    initialOn = true;
    try { localStorage.setItem(KEY, '1'); } catch (_) {}
  } else if (urlCmd === '0') {
    initialOn = false;
    try { localStorage.setItem(KEY, '0'); } catch (_) {}
  } else {
    let stored = null;
    try { stored = localStorage.getItem(KEY); } catch (_) {}
    initialOn = stored === '1';
  }

  applyMode(initialOn);

  let storedFocus = null;
  try { storedFocus = localStorage.getItem(FOCUS_KEY); } catch (_) {}
  applyFocus(storedFocus === '1');

  // Expose dev hooks (no operator UI in U.0)
  window.__cmd = {
    on() {
      applyMode(true);
      try { localStorage.setItem(KEY, '1'); } catch (_) {}
      // eslint-disable-next-line no-console
      console.info('[command] mode = ON  (data-ui="command")');
      return true;
    },
    off() {
      applyMode(false);
      try { localStorage.setItem(KEY, '0'); } catch (_) {}
      // eslint-disable-next-line no-console
      console.info('[command] mode = OFF (legacy UI restored)');
      return false;
    },
    focus(force) {
      const cur = document.body.getAttribute('data-ui-focus') === 'on';
      const next = typeof force === 'boolean' ? force : !cur;
      applyFocus(next);
      try { localStorage.setItem(FOCUS_KEY, next ? '1' : '0'); } catch (_) {}
      // eslint-disable-next-line no-console
      console.info(`[command] focus = ${next ? 'ON' : 'OFF'}`);
      return next;
    },
    state() {
      const m = document.body.getAttribute('data-ui') || 'legacy';
      const f = document.body.getAttribute('data-ui-focus') === 'on';
      // eslint-disable-next-line no-console
      console.info(`[command] state · mode=${m} · focus=${f}`);
      return { mode: m, focus: f };
    },
  };
}
