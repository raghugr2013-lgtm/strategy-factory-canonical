/**
 * Phase U-4.1 · useFocusTrap
 * ----------------------------------------------------------------------------
 * Lightweight, dependency-free focus trap for modal-ish surfaces (drawers,
 * palettes, overlays). Keeps Tab navigation inside the container while
 * `active === true`, and restores focus to the previously-focused element
 * when deactivated.
 *
 * Usage:
 *   const ref = useRef(null);
 *   useFocusTrap(ref, open, { initialFocus: 'first' });
 *   return <div ref={ref}>…</div>;
 *
 * Options:
 *   initialFocus — 'first' (default) | 'container' | HTMLElement | null
 *   onEscape    — optional callback invoked on Escape (in addition to the
 *                 surface's own Esc handler — useful when the surface itself
 *                 doesn't listen for Esc inside its own scope).
 *
 * Notes:
 *   • Selector covers the standard tabbable set, including [tabindex="0"]
 *     and contentEditable.
 *   • Disabled / hidden / aria-hidden / inert elements are skipped.
 *   • SSR-safe — every DOM access is guarded by `typeof document`.
 */
import { useEffect, useRef } from 'react';

const TABBABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(',');

function isVisible(el) {
  if (!el) return false;
  if (el.hasAttribute('inert')) return false;
  if (el.getAttribute('aria-hidden') === 'true') return false;
  const style = typeof window !== 'undefined' ? window.getComputedStyle(el) : null;
  if (style && (style.display === 'none' || style.visibility === 'hidden')) return false;
  // offsetParent is null for `display:none` ancestors; also catches detached nodes.
  if (el.offsetParent === null && style && style.position !== 'fixed') return false;
  return true;
}

function getTabbables(container) {
  if (!container) return [];
  return Array.from(container.querySelectorAll(TABBABLE_SELECTOR)).filter(isVisible);
}

export default function useFocusTrap(containerRef, active, options = {}) {
  const { initialFocus = 'first', onEscape } = options;
  const previousActive = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    if (typeof document === 'undefined') return undefined;
    const container = containerRef.current;
    if (!container) return undefined;

    previousActive.current = document.activeElement;

    // Defer the initial focus to next frame so the surface has rendered.
    const focusFrame = window.requestAnimationFrame(() => {
      const tabbables = getTabbables(container);
      let target = null;
      if (initialFocus instanceof HTMLElement) {
        target = initialFocus;
      } else if (initialFocus === 'container') {
        target = container;
        if (!container.hasAttribute('tabindex')) container.setAttribute('tabindex', '-1');
      } else {
        target = tabbables[0] || container;
        if (target === container && !container.hasAttribute('tabindex')) {
          container.setAttribute('tabindex', '-1');
        }
      }
      try { target.focus({ preventScroll: true }); } catch (_) { /* noop */ }
    });

    function onKey(e) {
      if (e.key === 'Escape') {
        if (typeof onEscape === 'function') onEscape(e);
        return;
      }
      if (e.key !== 'Tab') return;
      const tabbables = getTabbables(container);
      if (tabbables.length === 0) {
        e.preventDefault();
        try { container.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        return;
      }
      const first = tabbables[0];
      const last = tabbables[tabbables.length - 1];
      const activeEl = document.activeElement;
      if (e.shiftKey) {
        if (activeEl === first || !container.contains(activeEl)) {
          e.preventDefault();
          try { last.focus({ preventScroll: true }); } catch (_) { /* noop */ }
        }
      } else if (activeEl === last) {
        e.preventDefault();
        try { first.focus({ preventScroll: true }); } catch (_) { /* noop */ }
      }
    }

    container.addEventListener('keydown', onKey);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      container.removeEventListener('keydown', onKey);
      const previous = previousActive.current;
      if (previous && typeof previous.focus === 'function') {
        try { previous.focus({ preventScroll: true }); } catch (_) { /* noop */ }
      }
      previousActive.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}
