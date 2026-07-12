/**
 * COMMAND · Phase U.1 — CommandShell wrapper
 * ----------------------------------------------------------------------------
 * Single mount point that composes CommandBar + LeftRail + StatusRail +
 * mobile surfaces + command palette + focus-mode keyboard shortcuts.
 *
 * Usage:
 *   <CommandShell>
 *     <YourPage />          // host's content is the focus pane
 *   </CommandShell>
 *
 * The shell does NOT replace the operator's existing App.js routes. It is
 * only mounted by the foundations preview today (and by Phase U.2's
 * /c/* module routes later).
 *
 * Keyboard shortcuts wired here:
 *   ⌘K / Ctrl+K   open command palette
 *   ⌘⇧F / Ctrl+⇧+F   toggle Focus Mode
 *   ⌘B / Ctrl+B   (workstation) toggle LeftRail expand
 *   ⌘. / Ctrl+.   (reserved for Inspector toggle, lands in U.4)
 */
import React, { useState, useEffect, useCallback } from 'react';
import './shell.css';
import CommandBar from './CommandBar';
import LeftRail from './LeftRail';
import StatusRail, { worstStatus } from './StatusRail';
import TopTabBar from './TopTabBar';
import LifecycleRail from './LifecycleRail';
import DangerRibbon from './DangerRibbon';
import CommandPalette from './CommandPalette';
import ShortcutsOverlay from './ShortcutsOverlay';
import AsfNotificationDrawer from '../../components/ui-asf/AsfNotificationDrawer';
// Phase R5 — live-data overlays. NotificationDrawer consumes
// /api/monitoring/status + /api/admin/widening-proposals + /api/orchestrator/heartbeat.
// CopilotPanel consumes /api/orchestrator/heartbeat + /api/llm/call-log/recent.
// Both are global overlays per ASF_UI_Handoff Screens 38 + 39.
import NotificationDrawer from './NotificationDrawer';
import CopilotPanel from './CopilotPanel';
import OperatorInboxDrawer from './OperatorInboxDrawer';
import AriaLiveRegion from '../../components/a11y/AriaLiveRegion';
import EmergencyBanner from './EmergencyBanner';
import { push as pushNotification, getUnreadCount } from '../../stores/notificationsStore';
import { useNotifications } from '../../stores/notificationsStore';
import { useThemeStore } from '../../stores/themeStore';
import { cycleLocale, useLocaleStore } from '../../stores/localeStore';
import { ModuleDrawer, StatusSheet } from './MobileSurfaces';
import { usePosture } from './usePosture';
import { useDensity } from './useDensity';
import { usePremium } from './usePremium';
import { InspectorProvider, useInspector } from './inspector/InspectorProvider';
import InspectorPane from './inspector/InspectorPane';

/** Copy the current operator URL to clipboard and emit a tiny calm toast.
 *  Falls back to a manual prompt if the Clipboard API is unavailable
 *  (Safari without user gesture, http insecure contexts). */
function copyCurrentUrl() {
  if (typeof window === 'undefined') return;
  const url = window.location.href;
  const showToast = (msg, tone = 'cyan') => {
    try {
      const el = document.createElement('div');
      el.setAttribute('data-testid', 'cmd-toast');
      el.className = 'cmd-toast cmd-fade-in';
      el.dataset.tone = tone;
      el.textContent = msg;
      document.body.appendChild(el);
      // Auto-dismiss after 1800ms
      setTimeout(() => { el.style.opacity = '0'; }, 1500);
      setTimeout(() => { el.remove(); }, 1900);
    } catch (_) { /* noop */ }
  };
  const fallback = () => {
    try { window.prompt('Copy link:', url); } catch (_) { /* noop */ }
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url).then(
      () => showToast(`Copied · ${new URL(url).pathname}`, 'cyan'),
      () => { fallback(); showToast('Clipboard unavailable — link shown', 'amber'); },
    );
  } else {
    fallback();
    showToast('Clipboard unavailable — link shown', 'amber');
  }
}

export default function CommandShell({ children, activeId: activeIdProp, onNavigate, defaultActiveId = 'dashboard', user = null }) {
  // Wrap the whole shell tree in <InspectorProvider/> so any descendant
  // (rail, module surface, briefing, lineage strip) can call useInspector().
  return (
    <InspectorProvider>
      <CommandShellInner
        activeId={activeIdProp}
        onNavigate={onNavigate}
        defaultActiveId={defaultActiveId}
        user={user}
      >{children}</CommandShellInner>
    </InspectorProvider>
  );
}

function CommandShellInner({ children, activeId: activeIdProp, onNavigate, defaultActiveId = 'dashboard', user = null }) {
  const posture = usePosture();
  const { density, toggle: toggleDensity } = useDensity();
  const { premium, toggle: togglePremium } = usePremium();
  const inspector = useInspector();
  const [activeIdLocal, setActiveIdLocal] = useState(defaultActiveId);
  const activeId = activeIdProp !== undefined ? activeIdProp : activeIdLocal;
  const setActiveId = useCallback((id) => {
    if (onNavigate) onNavigate(id);
    else setActiveIdLocal(id);
  }, [onNavigate]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [statusSheetOpen, setStatusSheetOpen] = useState(false);
  // Phase U-3 — notification drawer + shortcuts overlay state.
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  // Phase R5 — live-data Notification Drawer + Copilot Panel.
  const [liveNotifOpen, setLiveNotifOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  // M4 — Operator Inbox drawer (categorised event stream).
  const [inboxOpen, setInboxOpen] = useState(false);
  const notifications = useNotifications();
  const unreadCount = notifications.items.filter((n) => n.at > notifications.lastReadAt).length;
  const [focusOn, setFocusOn] = useState(() =>
    document.body.getAttribute('data-ui-focus') === 'on'
  );
  const [chips, setChips] = useState(null);
  const [llmActive, setLlmActive] = useState(false);

  // Phase U-3 — one-shot welcome notification so the bell wire is observable.
  useEffect(() => {
    if (getUnreadCount() === 0 && notifications.items.length === 0) {
      pushNotification({
        slug: 'u3-welcome',
        title: 'Phase U-3 active',
        body: 'Command palette unification, notifications drawer, drill-through and interaction polish are live. Press ? for shortcuts.',
        tone: 'info',
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Mirror focusOn to body attribute (and localStorage via __cmd.focus())
  useEffect(() => {
    if (typeof window !== 'undefined' && window.__cmd && typeof window.__cmd.focus === 'function') {
      window.__cmd.focus(focusOn);
    } else {
      document.body.setAttribute('data-ui-focus', focusOn ? 'on' : 'off');
    }
  }, [focusOn]);

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e) {
      const cmd = e.metaKey || e.ctrlKey;
      if (cmd && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      } else if (cmd && e.shiftKey && (e.key === 'f' || e.key === 'F')) {
        e.preventDefault();
        setFocusOn((v) => !v);
      } else if (cmd && e.altKey && (e.key === 'c' || e.key === 'C' || e.code === 'KeyC')) {
        // ⌘⌥C / Ctrl+Alt+C — Copy current URL (institutional share-link).
        e.preventDefault();
        copyCurrentUrl();
      } else if (cmd && (e.key === '.' || e.code === 'Period')) {
        // ⌘. / Ctrl+. — toggle Inspector pane open/closed.
        e.preventDefault();
        inspector.toggle();
      } else if (cmd && e.shiftKey && (e.key === 'n' || e.key === 'N')) {
        // U-3 — ⌘⇧N toggles the notifications drawer.
        e.preventDefault();
        setNotificationsOpen((v) => !v);
      } else if (cmd && (e.key === 'j' || e.key === 'J')) {
        // R5 — ⌘J toggles the Copilot panel.
        e.preventDefault();
        setCopilotOpen((v) => !v);
      } else if (cmd && e.altKey && (e.key === 'n' || e.key === 'N')) {
        // R5 — ⌘⌥N toggles the live-data Notification Drawer.
        e.preventDefault();
        setLiveNotifOpen((v) => !v);
      } else if (cmd && e.shiftKey && (e.key === 'i' || e.key === 'I')) {
        // M4 — ⌘⇧I toggles the Operator Inbox drawer.
        e.preventDefault();
        setInboxOpen((v) => !v);
      } else if (!cmd && !e.altKey && (e.key === '?' || (e.shiftKey && e.key === '/'))) {
        // U-3 — `?` opens the shortcuts overlay (ignored when typing in inputs).
        const tag = (e.target && e.target.tagName) || '';
        const editable = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable);
        if (!editable) {
          e.preventDefault();
          setShortcutsOpen((v) => !v);
        }
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handlePaletteSelect = useCallback((item) => {
    if (!item) return;
    if (item.id.startsWith('module:')) {
      setActiveId(item.id.replace('module:', ''));
    } else if (item.id.startsWith('section:')) {
      // Pilot Restoration Step 3 (GATE 0) — palette deep-link to a
      // (module, section) pair. Mirrors TopTabBar.navTab: navigate the
      // module, then set the section hash + scroll the section into view.
      const [, modId, sectionId] = item.id.split(':');
      setActiveId(modId);
      if (typeof window !== 'undefined' && sectionId) {
        setTimeout(() => {
          window.history.replaceState({}, '', `${window.location.pathname}#${sectionId}`);
          try { window.dispatchEvent(new HashChangeEvent('hashchange')); } catch (_) { /* noop */ }
          const el = document.querySelector(`[data-testid="cmd-section-${modId}-${sectionId}"]`);
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 250);
      }
    } else if (item.id === 'cmd:focus-toggle') {
      setFocusOn((v) => !v);
    } else if (item.id === 'cmd:density-toggle') {
      // U.5.a — bar + palette parity with focus mode.
      toggleDensity();
    } else if (item.id === 'cmd:premium-toggle') {
      // U.6.a — operator-elective premium aesthetic.
      togglePremium();
    } else if (item.id === 'cmd:posture-reset') {
      if (typeof window !== 'undefined' && window.__cmd && window.__cmd.posture) {
        window.__cmd.posture(null);
      }
    } else if (item.id === 'cmd:copy-url') {
      // Phase U.2/U.3 — institutional collaboration affordance. Copies the
      // current operator URL (including module path) so it can be pasted
      // into Slack/Telegram/audit notes for anomaly investigation,
      // governance review, or AI auditability handoffs.
      copyCurrentUrl();
    } else if (item.id === 'cmd:notifications') {
      // U-3 — surface the notifications drawer from the palette.
      setNotificationsOpen(true);
    } else if (item.id === 'cmd:shortcuts') {
      // U-3 — surface the shortcuts overlay from the palette.
      setShortcutsOpen(true);
    } else if (item.id === 'cmd:retry-all') {
      // U-3 — fire a synthetic 'asf:retry-all' window event. Module-level
      // AsfEmptyState retry handlers may opt-in by listening for this event
      // (forward-compatible — modules without listeners ignore it harmlessly).
      try {
        window.dispatchEvent(new CustomEvent('asf:retry-all'));
        pushNotification({
          slug: 'retry-all-fired',
          title: 'Retry-all fired',
          body: 'Modules listening for asf:retry-all have been re-fetched.',
          tone: 'info',
        });
      } catch (_) { /* noop */ }
    } else if (item.id === 'cmd:inspector') {
      // U-3 — toggle Inspector pane from palette.
      inspector.toggle();
    } else if (item.id === 'cmd:lang-cycle') {
      // U-4.4 — cycle through SUPPORTED_LOCALES (en-US → de-DE → en-US).
      cycleLocale();
      pushNotification({
        slug: 'locale-cycled',
        title: 'Language cycled',
        body: 'UI strings re-render with the next registered locale.',
        tone: 'info',
      });
    } else if (item.id === 'cmd:legacy') {
      if (typeof window !== 'undefined' && window.__cmd && window.__cmd.off) {
        window.__cmd.off();
        // soft reload to legacy
        setTimeout(() => { window.location.href = '/'; }, 200);
      }
    }
  }, []);

  return (
    <div className="cmd-shell" data-testid="cmd-shell" data-leftrail={
      (typeof window !== 'undefined' && window.localStorage && window.localStorage.getItem('ui.leftrail') === 'on')
        ? 'on' : 'off'
    }>
      {/* M4.5 — Persistent Danger Ribbon. Hidden when inbox is all-clear;
       *  surfaces ONLY the latest highest-priority warning. Click opens
       *  the Operator Inbox. Status-only — NO chat functionality.
       *  Slots in at the very top of the shell so the operator sees it
       *  before anything else, including the TopTabBar. */}
      <DangerRibbon onOpenInbox={() => setInboxOpen(true)} />
      {/* M1 — Top Tab Bar (locked 11 CORE + 6 MORE roster). Sticky-top. */}
      <TopTabBar isAdmin={!!(user && (user.role === 'admin' || user.is_admin))} />
      {/* M1 — Lifecycle Rail (10-step operator-journey GPS). Sticky-below-topbar. */}
      <LifecycleRail />
      {/* U-4.1 — polite SR-only live region that mirrors the newest
       *  notification title/body to assistive tech. */}
      <AriaLiveRegion />
      {/* U-4.2 — emergency-access banner is rendered on viewports below
       *  480px so the operator knows they're on a degraded surface
       *  (read-mostly, limited controls). The banner is purely visual;
       *  the underlying shell remains fully wired. */}
      <EmergencyBanner />
      <CommandBar
        posture={posture}
        onPaletteOpen={() => setPaletteOpen(true)}
        onMenuOpen={() => setDrawerOpen(true)}
        onStatusPillTap={() => setStatusSheetOpen(true)}
        worstStatus={chips ? worstStatus(chips) : 'amber'}
        llmActive={llmActive}
        focusOn={focusOn}
        onFocusToggle={() => setFocusOn((v) => !v)}
        density={density}
        onDensityToggle={toggleDensity}
        premium={premium}
        onPremiumToggle={togglePremium}
        uptimeSecs={4 * 86400 + 2 * 3600 + 11 * 60 + 38}
        env="PROD"
        user={user}
        notificationsUnread={unreadCount}
        onNotificationsOpen={() => setNotificationsOpen(true)}
        inboxUnread={3}
        onInboxOpen={() => setInboxOpen(true)}
      />

      <div className="cmd-shell__body" data-cmd-inspector-open={inspector.open ? '1' : '0'}>
        <LeftRail
          posture={posture}
          activeId={activeId}
          onSelect={setActiveId}
        />
        <main className="cmd-shell__main" data-testid="cmd-shell-main">
          {children}
        </main>
      </div>

      <StatusRail
        posture={posture}
        onChipsChange={setChips}
        onLlmActiveChange={setLlmActive}
      />

      {/* Floating surfaces */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={handlePaletteSelect}
        posture={posture}
      />
      <ModuleDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSelect={setActiveId}
        posture={posture}
        activeId={activeId}
      />
      <StatusSheet
        open={statusSheetOpen}
        onClose={() => setStatusSheetOpen(false)}
        chips={chips}
      />

      {/* Phase U-3 — legacy notification store drawer (kept for store-driven toasts). */}
      <AsfNotificationDrawer
        open={notificationsOpen && !liveNotifOpen}
        onClose={() => setNotificationsOpen(false)}
      />
      {/* Phase R5 — live-data Notification Drawer (operator overlay backed by
          real backend endpoints). Opens via ⌘⇧N or via Command Palette. */}
      <NotificationDrawer
        open={liveNotifOpen}
        onClose={() => setLiveNotifOpen(false)}
      />
      {/* Phase R5 — Copilot Panel (advisory, no execution authority). ⌘J. */}
      <CopilotPanel
        open={copilotOpen}
        onClose={() => setCopilotOpen(false)}
      />
      <ShortcutsOverlay
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />

      {/* M4 — Operator Inbox drawer. Toggled via topbar icon or ⌘⇧I.
       *  Renders 5 categorised event sections (Factory · Validation ·
       *  Deployment · Infrastructure · Marketplace [Phase 15 reserved]). */}
      <OperatorInboxDrawer
        open={inboxOpen}
        onClose={() => setInboxOpen(false)}
      />

      {/* Phase U.4 — Inspector pane. Reads selection from InspectorProvider
          context. Posture-aware (push pane / overlay / sheet). */}
      <InspectorPane
        onNavigate={(p) => {
          if (typeof window !== 'undefined') {
            // Use the same router as the rail/palette
            const target = p && p.startsWith('/c/') ? p.replace('/c/', '') : null;
            if (target) setActiveId(target);
            else window.location.href = p;
          }
        }}
      />
    </div>
  );
}
