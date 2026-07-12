/**
 * COMMAND · M1 — Top Tab Bar
 * ----------------------------------------------------------------------------
 * Restored 11 CORE + 6 MORE roster from the locked 1-vCPU spec
 * (see /app/memory/visual_approval_package/01_TAB_ROSTER.md).
 *
 * Each tab routes to a (module, section) pair. Multiple tabs can share the
 * same module (e.g. Execution / Paper Exec / Trade Runner all map to the
 * `exec` module) — they are distinguished by an in-URL hash that the
 * ModuleSurface uses to scroll to a specific section.
 *
 * This component is mounted in CommandShell ABOVE the existing CommandBar
 * (which remains for the right-side controls: density, palette, etc).
 *
 * Architecture lock: /app/memory/visual_approval_package/12_M1_ARCHITECTURAL_PRINCIPLES.md
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useRoute } from './router';
import { getLibraryStrategies } from '../../services/api';

// P1.2 — Library count badge. Polls /api/auto-factory/saved on mount,
// on window focus, and on a custom `asf:library-changed` event so the
// `Library (N)` label stays current without a global store.
function useLibraryCount() {
  const [count, setCount] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const rows = await getLibraryStrategies({});
        if (!cancelled) setCount(Array.isArray(rows) ? rows.length : 0);
      } catch (_) {
        if (!cancelled) setCount(null);
      }
    };
    refresh();
    const onFocus = () => refresh();
    const onChanged = () => refresh();
    window.addEventListener('focus', onFocus);
    window.addEventListener('asf:library-changed', onChanged);
    return () => {
      cancelled = true;
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('asf:library-changed', onChanged);
    };
  }, []);
  return count;
}

export const CORE_TABS = [
  { id: 'dashboard',     label: 'Dashboard',     module: 'dashboard',  section: null,            adminOnly: false },
  { id: 'execution',     label: 'Execution',     module: 'exec',       section: null,            adminOnly: false },
  { id: 'auto-factory',  label: 'Auto Factory',  module: 'mutate',     section: 'factory-55',    adminOnly: false },
  { id: 'monitoring',    label: 'Monitoring',    module: 'diag',       section: 'monitoring',    adminOnly: false },
  { id: 'paper-exec',    label: 'Paper Exec',    module: 'exec',       section: 'paper',         adminOnly: false },
  { id: 'trade-runner',  label: 'Trade Runner',  module: 'exec',       section: 'runner',        adminOnly: false },
  { id: 'portfolio',     label: 'Portfolio',     module: 'portfolio',  section: 'builder',       adminOnly: false },
  { id: 'explorer',      label: 'Explorer',      module: 'explorer',   section: 'explorer',      adminOnly: false },
  { id: 'data',          label: 'Market Data',   module: 'diag',       section: 'market-data',   adminOnly: false },
  { id: 'auto-select',   label: 'Auto Select',   module: 'mutate',     section: 'auto-select',   adminOnly: false },
  { id: 'admin-users',   label: 'Admin',         module: 'governance', section: 'admin',         adminOnly: true  },
];

export const MORE_TABS = [
  { id: 'workspace',     label: 'Workspace',                 module: 'lab',        section: 'workspace' },
  { id: 'pipeline',      label: 'Auto Factory (Legacy)',     module: 'mutate',     section: 'factory' },
  { id: 'prop-firms',    label: 'Prop Firms',                module: 'propfirm',   section: 'admin'   },
  { id: 'live',          label: 'Live Tracking',             module: 'exec',       section: 'live'    },
  { id: 'optimization',  label: 'Optimization',              module: 'lab',        section: 'optim'   },
  { id: 'saved',         label: 'Library',                   module: 'explorer',   section: 'saved'   },
];

/** Resolve the active top-tab id from the current moduleId + URL hash.
 *  Multiple tabs can share a module; the hash disambiguates them.
 *  A tab.section of `null` is treated as equivalent to an empty hash so
 *  the "overview" tab (e.g. Execution) does not collide with its
 *  hash-specific siblings (Paper Exec #paper, Trade Runner #runner). */
export function resolveActiveTabId(moduleId, hash) {
  const cleanHash = (hash || '').replace(/^#/, '');
  const all = [...CORE_TABS, ...MORE_TABS];
  // Exact match treating null section as ''.
  const exact = all.find(t => t.module === moduleId && (t.section || '') === cleanHash);
  if (exact) return exact.id;
  // Module match; default to first occurrence.
  const fallback = all.find(t => t.module === moduleId);
  return fallback ? fallback.id : 'dashboard';
}

export default function TopTabBar({ isAdmin = false }) {
  const { moduleId, navigate } = useRoute();
  const [hash, setHash] = useState(() => (typeof window !== 'undefined' ? window.location.hash : ''));
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef(null);
  const libraryCount = useLibraryCount();

  // ── Restoration Step 5 — navbar a11y helpers ported from the locked
  //    1-vCPU App.js (LL 126–145). Behaviour, not layout:
  //    • navMenuRef    → the scrollable tab strip
  //    • tabRefs       → per-tab refs so the active tab is NEVER off-screen
  //    • handleNavWheel → vertical mouse-wheel becomes horizontal scroll
  //      while the pointer is over the strip (users never think to
  //      shift+wheel to reach Auto Select / Admin).
  const navMenuRef = useRef(null);
  const tabRefs = useRef({});
  const handleNavWheel = useCallback((e) => {
    const el = navMenuRef.current;
    if (!el) return;
    // Only hijack pure-vertical wheels; let native horizontal wheels pass.
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && el.scrollWidth > el.clientWidth) {
      el.scrollLeft += e.deltaY;
      e.preventDefault();
    }
  }, []);

  // Compute MORE tab label (Library shows count badge when available).
  const labelFor = (t) => {
    if (t.id === 'saved' && libraryCount !== null) {
      return `${t.label} (${libraryCount})`;
    }
    return t.label;
  };

  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHash);
    window.addEventListener('popstate', onHash);
    return () => {
      window.removeEventListener('hashchange', onHash);
      window.removeEventListener('popstate', onHash);
    };
  }, []);

  useEffect(() => {
    if (!moreOpen) return;
    const onDocClick = (e) => {
      if (moreRef.current && !moreRef.current.contains(e.target)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [moreOpen]);

  const activeId = resolveActiveTabId(moduleId, hash);

  // Restoration Step 5 — keep the active tab scrolled into view after every
  // activation (old App.js LL 139–145). MORE-menu tabs scroll the More
  // trigger into view instead (the items live in a popover).
  useEffect(() => {
    const isMore = MORE_TABS.some((t) => t.id === activeId);
    const el = isMore ? moreRef.current : tabRefs.current[activeId];
    if (el && typeof el.scrollIntoView === 'function') {
      try { el.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' }); }
      catch (_) { /* older browsers */ }
    }
  }, [activeId]);

  const navTab = (tab) => {
    // Navigate the module via the existing router (pushState).
    navigate(tab.module);
    // Update URL hash for section so resolveActiveTabId picks the correct tab.
    if (tab.section && typeof window !== 'undefined') {
      window.history.replaceState({}, '', `${window.location.pathname}#${tab.section}`);
      setHash(`#${tab.section}`);
      // Force a re-render of sibling consumers (LifecycleRail, ModuleSurface)
      // since replaceState does not fire popstate or hashchange natively.
      try { window.dispatchEvent(new HashChangeEvent('hashchange')); } catch (_) { /* noop */ }
      // Best-effort: scroll to the section after the module mounts.
      setTimeout(() => {
        const el = document.querySelector(`[data-testid="cmd-section-${tab.module}-${tab.section}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 250);
    } else if (typeof window !== 'undefined') {
      window.history.replaceState({}, '', window.location.pathname);
      setHash('');
      try { window.dispatchEvent(new HashChangeEvent('hashchange')); } catch (_) { /* noop */ }
    }
    setMoreOpen(false);
  };

  const visibleCore = CORE_TABS.filter(t => !t.adminOnly || isAdmin);

  return (
    <div className="cmd-toptabs" data-testid="top-tab-bar" role="tablist" aria-label="Top tab navigation">
      <div className="cmd-toptabs__inner" ref={navMenuRef} onWheel={handleNavWheel}>
        {visibleCore.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            ref={(el) => { tabRefs.current[t.id] = el; }}
            aria-selected={activeId === t.id}
            className={`cmd-toptab ${activeId === t.id ? 'cmd-toptab--active' : ''}`}
            data-testid={`top-tab-${t.id}`}
            onClick={() => navTab(t)}
          >
            {t.label}
          </button>
        ))}
        <div className="cmd-toptabs__more" ref={moreRef}>
          <button
            type="button"
            className={`cmd-toptab cmd-toptab--more ${MORE_TABS.some(t => t.id === activeId) ? 'cmd-toptab--active' : ''}`}
            data-testid="top-tab-more"
            onClick={() => setMoreOpen(o => !o)}
            aria-expanded={moreOpen}
            aria-haspopup="menu"
          >
            More <span className="cmd-toptab__caret">▾</span>
          </button>
          {moreOpen && (
            <div className="cmd-toptabs__menu" role="menu" data-testid="top-tab-more-menu">
              {MORE_TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="menuitem"
                  className={`cmd-toptabs__menu-item ${activeId === t.id ? 'cmd-toptabs__menu-item--active' : ''}`}
                  data-testid={`top-tab-${t.id}`}
                  onClick={() => navTab(t)}
                >
                  {labelFor(t)}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

