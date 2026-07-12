/**
 * COMMAND · Phase U.1 — CommandBar (posture-aware)
 * ----------------------------------------------------------------------------
 * Workstation : 32px · BrandMark · wordmark · build · ⌘K palette · env · uptime · LLM throb · user · focus
 * Tablet      : 40px · BrandMark · wordmark · icon-only ⌘K · LLM throb · user · focus
 * Briefing    : 44px · BrandMark · menu button · status pill · LLM throb · user
 *
 * All conditional rendering happens via CSS in shell.css (using
 * [data-cmd-posture]). JSX renders every element; CSS hides what doesn't
 * belong in that posture. This keeps a single render path and no flicker
 * on resize.
 */
import React, { useState, useEffect, useRef } from 'react';
import BrandMark from '../BrandMark';
import { GlyphMenu, GlyphFocus, GlyphSearch, GlyphDensity, GlyphPremium } from './Glyphs';

function fmtUptime(secs) {
  if (!secs && secs !== 0) return '—';
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  return `${d}d ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function CommandBar({
  posture,
  onPaletteOpen,
  onMenuOpen,
  onStatusPillTap,
  worstStatus = 'green',
  llmActive = false,
  focusOn = false,
  onFocusToggle,
  density = 'comfortable',
  onDensityToggle,
  premium = 'on',
  onPremiumToggle,
  uptimeSecs = 0,
  env = 'PROD',
  user = null,
  notificationsUnread = 0,
  onNotificationsOpen,
  inboxUnread = 0,
  onInboxOpen,
}) {
  // Local uptime ticker so the bar feels alive even between data refreshes
  const [tickedUptime, setTickedUptime] = useState(uptimeSecs);
  useEffect(() => { setTickedUptime(uptimeSecs); }, [uptimeSecs]);
  useEffect(() => {
    const t = setInterval(() => setTickedUptime((u) => u + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // LLM throb — re-fire animation each time llmActive flips false→true
  const throbRef = useRef(null);
  const prev = useRef(false);
  useEffect(() => {
    if (llmActive && !prev.current && throbRef.current) {
      const el = throbRef.current;
      el.classList.remove('cmd-throb--fire');
      // force reflow to restart animation
      // eslint-disable-next-line no-unused-expressions
      el.offsetHeight;
      el.classList.add('cmd-throb--fire');
    }
    prev.current = llmActive;
  }, [llmActive]);

  const statusColour = {
    green:  'var(--cmd-green)',
    amber:  'var(--cmd-amber)',
    red:    'var(--cmd-red)',
    cyan:   'var(--cmd-cyan)',
  }[worstStatus] || 'var(--cmd-ink-2)';

  return (
    <header className="cmd-shell__bar" data-testid="cmd-bar">
      <BrandMark size={posture === 'briefing' ? 24 : 22} />

      <span className="cmd-bar__wordmark" data-testid="cmd-bar-wordmark">
        STRATEGY&nbsp;FACTORY
      </span>

      <span className="cmd-bar__build" data-testid="cmd-bar-build">BUILD 30.4</span>

      {/* Mobile menu button (briefing only) */}
      <button
        type="button"
        className="cmd-bar__menubtn"
        data-testid="cmd-bar-menu"
        onClick={onMenuOpen}
        title="Modules"
      >
        <GlyphMenu />
      </button>

      {/* Mobile status pill (briefing only) */}
      <button
        type="button"
        className="cmd-bar__statpill"
        data-testid="cmd-bar-statpill"
        onClick={onStatusPillTap}
        title="Subsystem status"
      >
        <span
          style={{
            width: 8, height: 8, borderRadius: 999,
            background: statusColour,
            boxShadow: `0 0 6px ${statusColour}`,
          }}
        />
        STATUS
      </button>

      {/* Palette trigger (workstation = full pill, tablet = icon-only) */}
      <button
        type="button"
        className="cmd-bar__palette"
        data-testid="cmd-bar-palette"
        onClick={onPaletteOpen}
      >
        <GlyphSearch />
        <span className="cmd-bar__palette-label">Quick command…</span>
        <span style={{ flex: 1 }} />
        <span className="kbd cmd-bar__palette-label">⌘K</span>
      </button>

      <span className="cmd-bar__spacer" />

      <span className="cmd-bar__env" data-testid="cmd-bar-env">
        <span
          style={{
            display: 'inline-block', width: 6, height: 6, borderRadius: 999,
            background: 'var(--cmd-green)', boxShadow: 'var(--cmd-glow-green)',
            marginRight: 6, verticalAlign: 'middle',
          }}
        />
        {env}
      </span>

      <span className="cmd-bar__uptime" data-testid="cmd-bar-uptime">
        UP {fmtUptime(tickedUptime)}
      </span>

      {/* AI heartbeat throbber — one-shot flash on each new LLM call */}
      <span
        ref={throbRef}
        className="cmd-throb"
        data-testid="cmd-bar-llm-throb"
        title="LLM runner heartbeat"
      />

      {/* Focus mode toggle */}
      <button
        type="button"
        className={focusOn ? 'cmd-btn cmd-btn--cyan' : 'cmd-btn'}
        onClick={onFocusToggle}
        data-testid="cmd-bar-focus-toggle"
        style={{ height: 24, padding: '0 8px' }}
        title={focusOn ? 'Focus mode ON (⌘⇧F)' : 'Focus mode OFF (⌘⇧F)'}
      >
        <GlyphFocus />
      </button>

      {/* U.5.a — Density toggle. Hidden on briefing (touch ergonomics
          remain comfortable). On tablet it's icon-only via the same
          CSS posture rules that hide the focus label space. */}
      <button
        type="button"
        className={density === 'compact' ? 'cmd-btn cmd-btn--cyan cmd-bar__density' : 'cmd-btn cmd-bar__density'}
        onClick={onDensityToggle}
        data-testid="cmd-bar-density-toggle"
        data-density-state={density}
        style={{ height: 24, padding: '0 8px' }}
        title={density === 'compact' ? 'Density: COMPACT (click → comfortable)' : 'Density: COMFORTABLE (click → compact)'}
      >
        <GlyphDensity />
      </button>

      {/* U.6.a — Premium aesthetic toggle. Operator-elective; persists in
          localStorage. Hidden on briefing (touch ergonomics). Same posture
          rules as density. */}
      <button
        type="button"
        className={premium === 'off' ? 'cmd-btn cmd-bar__premium' : 'cmd-btn cmd-btn--cyan cmd-bar__premium'}
        onClick={onPremiumToggle}
        data-testid="cmd-bar-premium-toggle"
        data-premium-state={premium}
        style={{ height: 24, padding: '0 8px' }}
        title={premium === 'on' ? 'Premium aesthetic ON (click → flat focus mode)' : 'Premium aesthetic OFF (click → cinematic mode)'}
      >
        <GlyphPremium />
      </button>

      {/* U-3 — Notifications bell (unread badge animates on new arrivals).
       *  U-4.1 — exposes unread count via aria-label so screen readers
       *  announce "Notifications, N unread, shortcut Cmd Shift N". */}
      <button
        type="button"
        className="cmd-btn"
        data-testid="cmd-bar-notifications"
        data-unread={notificationsUnread || 0}
        onClick={onNotificationsOpen}
        style={{ height: 24, padding: '0 8px' }}
        aria-label={notificationsUnread > 0
          ? `Notifications, ${notificationsUnread} unread, shortcut Command Shift N`
          : 'Notifications, no unread, shortcut Command Shift N'}
        aria-haspopup="dialog"
        title={notificationsUnread > 0
          ? `${notificationsUnread} unread notification${notificationsUnread === 1 ? '' : 's'} (⌘⇧N)`
          : 'Notifications (⌘⇧N)'}
      >
        <span className="asf-bell-wrap" aria-hidden="true">
          {/* simple bell glyph (no external icon import) */}
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
            <path d="M3 11h10l-1.2-1.5V6a4 4 0 1 0-8 0v3.5L3 11z" />
            <path d="M6.5 13a1.5 1.5 0 0 0 3 0" />
          </svg>
          {notificationsUnread > 0 && (
            <span className="asf-bell-badge" key={notificationsUnread} data-testid="cmd-bar-notifications-badge">
              {notificationsUnread > 9 ? '9+' : notificationsUnread}
            </span>
          )}
        </span>
      </button>

      {/* M4 — Operator Inbox button (📥). Distinct from notifications:
       *  the inbox surfaces curated, categorised operator-meaningful events
       *  (Factory · Validation · Deployment · Infrastructure · Marketplace).
       *  Toggle via the topbar or ⌘⇧I. */}
      <button
        type="button"
        className="cmd-btn"
        data-testid="cmd-bar-inbox"
        data-unread={inboxUnread || 0}
        onClick={onInboxOpen}
        style={{ height: 24, padding: '0 8px' }}
        aria-label={inboxUnread > 0
          ? `Operator inbox, ${inboxUnread} unread, shortcut Command Shift I`
          : 'Operator inbox, shortcut Command Shift I'}
        aria-haspopup="dialog"
        title={inboxUnread > 0
          ? `Operator inbox · ${inboxUnread} unread (⌘⇧I)`
          : 'Operator inbox (⌘⇧I)'}
      >
        <span className="asf-bell-wrap" aria-hidden="true">
          {/* Inbox / tray glyph — tray + sloped arrow into it */}
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 9.5V13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.5" />
            <path d="M2 9.5h3l1 1.5h4l1-1.5h3" />
            <path d="M8 2v6M5.5 5.5L8 8l2.5-2.5" />
          </svg>
          {inboxUnread > 0 && (
            <span className="asf-bell-badge" key={inboxUnread} data-testid="cmd-bar-inbox-badge">
              {inboxUnread > 9 ? '9+' : inboxUnread}
            </span>
          )}
        </span>
      </button>

      {user && (
        <span className="cmd-bar__user" data-testid="cmd-bar-user">
          {user.email || 'operator'}
        </span>
      )}
    </header>
  );
}
