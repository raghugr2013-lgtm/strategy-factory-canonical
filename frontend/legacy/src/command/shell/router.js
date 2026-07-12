/**
 * COMMAND · Phase U.2 — Tiny URL router
 * ----------------------------------------------------------------------------
 * The COMMAND shell uses path-based module routing at /c/:moduleId.
 * We deliberately do NOT mount react-router-dom here — it would force us
 * to touch App.js's existing route tree. Instead we use a minimal
 * popstate/pushState wrapper that the shell components use:
 *
 *     useRoute()             returns { moduleId, navigate(id) }
 *
 * Why this is safe:
 *   • App.js inspects window.location.pathname BEFORE rendering its
 *     normal tree; if path starts with '/c/', it hands off to
 *     <CommandModuleApp/> (added in U.2).
 *   • This hook is only used INSIDE <CommandModuleApp/>; legacy paths
 *     never instantiate it.
 *   • Navigate uses pushState, so back/forward buttons work via popstate.
 *
 * Default module is 'dashboard'.
 */
import { useEffect, useState, useCallback } from 'react';
import { MODULES_BY_ID } from './modulesRegistry';

export const COMMAND_PATH_PREFIX = '/c';

export function pathToModuleId(pathname) {
  if (!pathname || !pathname.startsWith(`${COMMAND_PATH_PREFIX}/`)) return null;
  const seg = pathname.slice(COMMAND_PATH_PREFIX.length + 1).split('/')[0];
  if (!seg) return 'dashboard';
  return MODULES_BY_ID[seg] ? seg : 'dashboard';
}

export function moduleIdToPath(id) {
  return `${COMMAND_PATH_PREFIX}/${id}`;
}

export function useRoute() {
  const [moduleId, setModuleId] = useState(() => {
    if (typeof window === 'undefined') return 'dashboard';
    return pathToModuleId(window.location.pathname) || 'dashboard';
  });

  useEffect(() => {
    const onPop = () => {
      setModuleId(pathToModuleId(window.location.pathname) || 'dashboard');
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = useCallback((id, opts = {}) => {
    if (!MODULES_BY_ID[id]) return;
    const path = moduleIdToPath(id);
    if (typeof window === 'undefined') return;
    if (window.location.pathname === path) return;
    if (opts.replace) {
      window.history.replaceState({ moduleId: id }, '', path);
    } else {
      window.history.pushState({ moduleId: id }, '', path);
    }
    setModuleId(id);
    // pushState / replaceState do NOT fire 'popstate' natively. Without
    // this dispatch, sibling useRoute() consumers (LifecycleRail,
    // ModuleSurface, etc.) never learn about the navigation and the rendered
    // content gets stuck on whatever module loaded first. (M1 acceptance bug.)
    try {
      window.dispatchEvent(new PopStateEvent('popstate', { state: { moduleId: id } }));
    } catch (_) { /* IE/old-Safari: PopStateEvent constructor not available — noop */ }
  }, []);

  return { moduleId, navigate };
}
