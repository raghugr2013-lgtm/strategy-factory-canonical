/*
 * useStateMemory — per-pathname surface-state snapshot hook.
 * refs DESIGN_FREEZE_v1.0.md §1.2 principle E5 · D8 §3.2 (I3)
 *
 * Each surface calls useStateMemory(defaults) with its own key defaults.
 * On mount, the hook restores prior state from sessionStorage via
 * useNavigationStore. On update it persists.
 */
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useNavigationStore } from './navigationStore';

export function useStateMemory(defaults) {
  const { pathname } = useLocation();
  const saveSurface = useNavigationStore((s) => s.saveSurface);
  const readSurface = useNavigationStore((s) => s.readSurface);
  const stored = useRef(null);

  if (stored.current === null) {
    const prior = readSurface(pathname);
    stored.current = prior ? { ...defaults, ...prior } : { ...defaults };
  }

  const commit = (slice) => {
    stored.current = { ...stored.current, ...slice };
    saveSurface(pathname, stored.current);
  };

  return [stored.current, commit];
}

export function useReturnCrumb() {
  const { pathname, search } = useLocation();
  const setCrumb = useNavigationStore((s) => s.setCrumb);
  const consumeCrumb = useNavigationStore((s) => s.consumeCrumb);

  const dropCrumb = (label) =>
    setCrumb({ path: `${pathname}${search}`, label, ts: Date.now() });

  return { dropCrumb, consumeCrumb };
}
