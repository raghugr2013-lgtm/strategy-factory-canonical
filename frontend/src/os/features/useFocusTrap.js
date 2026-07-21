/*
 * useFocusTrap — Sprint 2 N4 focus manager.
 * refs SPRINT_2_PLANNING.md §2 N4 (focus manager for palette + drawer)
 *
 * Behaviour when `active` is true:
 *   1. Records the previously-focused element on mount.
 *   2. Focuses the first tabbable element inside `ref` (or `ref` itself).
 *   3. Tab / Shift+Tab cycle stays inside `ref`.
 *   4. On unmount / deactivation, focus returns to the previously-focused
 *      element (the trigger button, cmd+K etc.), satisfying WCAG 2.1 §2.4.3.
 *
 * Zero-dependency implementation. Guards against `document` being undefined
 * (SSR safety, though Sprint 2 does not SSR).
 */
import { useEffect } from 'react';

const TABBABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export const useFocusTrap = (ref, active) => {
  useEffect(() => {
    if (!active || !ref?.current || typeof document === 'undefined') return undefined;
    const prev = document.activeElement;
    const node = ref.current;

    const collectTabbable = () => Array.from(node.querySelectorAll(TABBABLE_SELECTOR))
      .filter((el) => !el.hasAttribute('inert'));

    const focusFirst = () => {
      const list = collectTabbable();
      (list[0] || node).focus();
    };

    focusFirst();

    const onKeyDown = (e) => {
      if (e.key !== 'Tab') return;
      const list = collectTabbable();
      if (list.length === 0) { e.preventDefault(); node.focus(); return; }
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    node.addEventListener('keydown', onKeyDown);
    return () => {
      node.removeEventListener('keydown', onKeyDown);
      if (prev && typeof prev.focus === 'function') {
        try { prev.focus(); } catch { /* noop */ }
      }
    };
  }, [ref, active]);
};
