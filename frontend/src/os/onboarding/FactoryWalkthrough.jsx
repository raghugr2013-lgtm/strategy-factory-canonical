/*
 * FactoryWalkthrough — first-login + version-bump onboarding overlay.
 * refs UX-Review-2026-07-22 · Sprint 3 Phase-1 · onboarding follow-up
 *
 * Trigger rules (see openIfFirstTime / openIfVersionBump):
 *   1) First authenticated arrival — localStorage key `sf-walkthrough-seen-
 *      version` unset.
 *   2) Major-version bump — stored version differs from WALKTHROUGH_VERSION.
 *   3) Manual — user menu "Factory Walkthrough".
 *
 * Interaction:
 *   - Left/Right arrow keys advance
 *   - Esc dismisses immediately (counts as `skipped`)
 *   - Dot navigation
 *   - "Skip walkthrough" button on every slide (`skipped`)
 *   - "Get started" on the final slide marks-and-closes (`completed`)
 *   - Last-slide ArrowRight also completes
 *   - X close button dismisses (`skipped`)
 *
 * The overlay dismisses to Mission Control if the user was not already
 * on a canonical surface. No routing side-effects otherwise.
 *
 * ─── Lifecycle events (frontend-only, framework-agnostic) ─────────────
 * The component is an event PRODUCER only. It dispatches four DOM
 * CustomEvents on `window` so any future analytics adapter can subscribe
 * without touching this file:
 *
 *   walkthrough_started        (open transitions false → true)
 *   walkthrough_slide_changed  (idx changes while open)
 *   walkthrough_completed      (Get started or last-slide ArrowRight)
 *   walkthrough_skipped        (Skip / X / Esc / dismiss before end)
 *
 * Each event carries a `detail` payload with:
 *   {
 *     productVersion:     PRODUCT_VERSION,
 *     walkthroughVersion: WALKTHROUGH_VERSION,
 *     slidesViewed:       <int, unique slides visited so far>,
 *     totalSlides:        <int, steps.length for the active variant>,
 *     completed:          <boolean>,   // true only on _completed
 *     skipped:            <boolean>,   // true only on _skipped
 *     elapsedMs:          <int>,       // ms since walkthrough_started
 *     // slide_changed only:
 *     currentSlideId, currentSlideIndex, previousSlideId, previousSlideIndex,
 *   }
 *
 * No fixture / demo data is inspected. The walkthrough is pure prose.
 * No network calls. No SDK. No persistent tracking beyond the existing
 * sf-walkthrough-seen-version localStorage key.
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, ChevronLeft, ChevronRight } from 'lucide-react';
import { WALKTHROUGH_STEPS, WALKTHROUGH_VERSION, PRODUCT_VERSION } from './walkthroughSteps';
import { useAuthStore } from '../workspace-state/authStore';

const STORAGE_KEY = 'sf-walkthrough-seen-version';

const isAdminEmail = (email) => !!email && /(^admin@|admin)/i.test(email);

const readSeen = () => {
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
};
const writeSeen = () => {
  try { localStorage.setItem(STORAGE_KEY, WALKTHROUGH_VERSION); } catch {}
};

/**
 * Framework-agnostic lifecycle-event emitter. Uses standard DOM
 * CustomEvent on `window`. Safe no-op in non-browser environments
 * (SSR / unit tests without jsdom).
 */
const emitLifecycle = (name, detail) => {
  if (typeof window === 'undefined' || typeof window.CustomEvent !== 'function') return;
  try {
    window.dispatchEvent(new window.CustomEvent(name, { detail }));
  } catch {
    /* Never let analytics failures reach the user. */
  }
};

/**
 * Global controller — subscribe with subscribeOpen() to react to
 * external "open" requests (used by Header user-menu).
 */
const openListeners = new Set();
export const openWalkthrough = () => {
  openListeners.forEach((fn) => fn());
};
const subscribeOpen = (fn) => {
  openListeners.add(fn);
  return () => openListeners.delete(fn);
};

export const shouldAutoOpenWalkthrough = () => {
  const seen = readSeen();
  return seen !== WALKTHROUGH_VERSION;
};

export const FactoryWalkthrough = () => {
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const email = useAuthStore((s) => s.email);
  const stance = useAuthStore((s) => s.stance);
  const navigate = useNavigate();

  const steps = WALKTHROUGH_STEPS.filter((s) => !s.adminOnly || isAdminEmail(email));
  const step = steps[idx];
  const last = idx === steps.length - 1;
  const first = idx === 0;

  // Lifecycle-event refs — persist across renders without triggering re-render.
  const startedAtRef = useRef(0);
  const visitedRef   = useRef(new Set());
  const prevIdxRef   = useRef(0);

  /** Build a common event payload; individual events add reason-specific keys. */
  const buildPayload = useCallback((extra = {}) => ({
    productVersion:     PRODUCT_VERSION,
    walkthroughVersion: WALKTHROUGH_VERSION,
    slidesViewed:       visitedRef.current.size,
    totalSlides:        steps.length,
    completed:          false,
    skipped:            false,
    elapsedMs:          startedAtRef.current ? Date.now() - startedAtRef.current : 0,
    ...extra,
  }), [steps.length]);

  // Auto-open on first authenticated arrival OR when version has bumped.
  useEffect(() => {
    if (stance === 'authenticated' && shouldAutoOpenWalkthrough()) {
      // Small delay so the shell paints before the overlay covers it.
      const t = setTimeout(() => setOpen(true), 700);
      return () => clearTimeout(t);
    }
  }, [stance]);

  // External-open subscription (user-menu → openWalkthrough()).
  useEffect(() => subscribeOpen(() => { setIdx(0); setOpen(true); }), []);

  // On open transition: reset trackers, mark the first slide as visited,
  // and emit walkthrough_started.
  useEffect(() => {
    if (!open) return;
    startedAtRef.current = Date.now();
    visitedRef.current = new Set([steps[0]?.id].filter(Boolean));
    prevIdxRef.current = 0;
    emitLifecycle('walkthrough_started', buildPayload({
      currentSlideId: steps[0]?.id,
      currentSlideIndex: 0,
    }));
    // steps identity is stable within a single open session (email doesn't
    // change while overlay is up), so eslint-disable-next-line is safe here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // On idx change while open: mark visited, emit walkthrough_slide_changed.
  useEffect(() => {
    if (!open) return;
    const prev = prevIdxRef.current;
    if (prev === idx) return;
    const currentSlide = steps[idx];
    const previousSlide = steps[prev];
    if (currentSlide) visitedRef.current.add(currentSlide.id);
    emitLifecycle('walkthrough_slide_changed', buildPayload({
      currentSlideId:     currentSlide?.id,
      currentSlideIndex:  idx,
      previousSlideId:    previousSlide?.id,
      previousSlideIndex: prev,
    }));
    prevIdxRef.current = idx;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, open]);

  /**
   * Close the walkthrough with a semantic reason. Both reasons persist the
   * seen-version so the walkthrough doesn't re-auto-open for the same
   * major version — only the emitted event differs.
   */
  const close = useCallback((reason /* 'completed' | 'skipped' */) => {
    if (!open) { setIdx(0); return; }
    const eventName = reason === 'completed' ? 'walkthrough_completed' : 'walkthrough_skipped';
    emitLifecycle(eventName, buildPayload({
      completed: reason === 'completed',
      skipped:   reason === 'skipped',
      currentSlideId:    step?.id,
      currentSlideIndex: idx,
    }));
    writeSeen();
    setOpen(false);
    setIdx(0);
  }, [open, step, idx, buildPayload]);

  const next = useCallback(() => {
    setIdx((i) => Math.min(i + 1, steps.length - 1));
  }, [steps.length]);
  const prev = useCallback(() => setIdx((i) => Math.max(i - 1, 0)), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') { close('skipped'); }
      else if (e.key === 'ArrowRight') { last ? close('completed') : next(); }
      else if (e.key === 'ArrowLeft') { prev(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, last, next, prev, close]);

  if (!open || !step) return null;
  const Icon = step.icon;

  const accentColor =
    step.tone === 'engineering' ? 'var(--sig-warn)' :
    step.tone === 'accent'      ? 'var(--sig-info)' :
    step.tone === 'warn'        ? 'var(--sig-warn)' :
                                  'var(--sig-info)';

  const finish = () => {
    close('completed');
    // If the operator is not currently on a canonical surface, land on Mission.
    if (!window.location.pathname.startsWith('/c/')) navigate('/c/mission');
  };

  return (
    <div data-testid="walkthrough-overlay"
         role="dialog"
         aria-modal="true"
         aria-labelledby="walkthrough-title"
         style={{
           position: 'fixed',
           inset: 0,
           background: 'rgba(5, 7, 10, 0.86)',
           backdropFilter: 'blur(10px)',
           WebkitBackdropFilter: 'blur(10px)',
           zIndex: 60,
           display: 'grid',
           placeItems: 'center',
           padding: 'var(--space-5)',
         }}>
      <div data-testid={`walkthrough-slide-${step.id}`}
           style={{
             width: 720,
             maxWidth: '92vw',
             background: 'var(--surface-1)',
             border: '1px solid var(--stroke-2)',
             borderRadius: 'var(--radius-3)',
             boxShadow: 'var(--elev-2)',
             padding: 'var(--space-6)',
             color: 'var(--content-hi)',
             position: 'relative',
             overflow: 'hidden',
           }}>
        {/* Accent bar */}
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, width: 4,
          background: accentColor, opacity: 0.9,
        }} />

        {/* Close */}
        <button data-testid="walkthrough-close"
                onClick={() => close('skipped')}
                aria-label="Close walkthrough"
                style={closeBtnStyle}>
          <X size={14} strokeWidth={1.5} />
        </button>

        {/* Eyebrow row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 32, height: 32, borderRadius: 'var(--radius-2)',
            background: 'color-mix(in oklab, ' + accentColor + ' 14%, transparent)',
            border: '1px solid color-mix(in oklab, ' + accentColor + ' 40%, transparent)',
            color: accentColor,
          }}>
            <Icon size={16} strokeWidth={1.5} />
          </span>
          <span style={eyebrowStyle}>{step.eyebrow}</span>
        </div>

        {/* Title */}
        <h2 id="walkthrough-title"
            data-testid={`walkthrough-title-${step.id}`}
            style={{
              margin: 0, marginBottom: 'var(--space-4)',
              fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em',
              color: 'var(--content-hi)', lineHeight: 1.25,
            }}>
          {step.title}
        </h2>

        {/* Body — one paragraph per array entry */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          {step.body.map((p, i) => (
            <p key={i}
               data-testid={`walkthrough-body-${step.id}-${i}`}
               style={{
                 margin: 0,
                 marginBottom: i === step.body.length - 1 ? 0 : 'var(--space-3)',
                 fontSize: 'var(--font-body-md)',
                 lineHeight: 1.6,
                 color: 'var(--content-md)',
               }}>
              {p}
            </p>
          ))}
        </div>

        {/* Optional surface hint pill */}
        {step.surfaceHint && (
          <div style={{ marginBottom: 'var(--space-5)' }}>
            <code data-testid={`walkthrough-hint-${step.id}`}
                  style={{
                    display: 'inline-flex',
                    padding: '3px 10px',
                    borderRadius: 999,
                    background: 'var(--surface-2)',
                    border: '1px solid var(--stroke-2)',
                    color: 'var(--content-lo)',
                    fontSize: 'var(--font-caption)',
                    letterSpacing: '0.08em',
                    fontFamily: 'var(--font-mono, ui-monospace, monospace)',
                  }}>
              {step.surfaceHint}
            </code>
          </div>
        )}

        {/* Footer — progress + nav */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          {/* Dots */}
          <div data-testid="walkthrough-progress"
               role="progressbar"
               aria-valuenow={idx + 1}
               aria-valuemax={steps.length}
               style={{ display: 'flex', gap: 6 }}>
            {steps.map((s, i) => (
              <button key={s.id}
                      data-testid={`walkthrough-dot-${s.id}`}
                      onClick={() => setIdx(i)}
                      aria-label={`Go to slide ${i + 1} of ${steps.length}`}
                      style={{
                        width: 22, height: 6, padding: 0,
                        borderRadius: 3,
                        background: i === idx ? accentColor : 'var(--stroke-2)',
                        opacity: i === idx ? 1 : 0.55,
                        border: 'none', cursor: 'pointer',
                        transition: 'background var(--dur-fast) var(--ease-standard), opacity var(--dur-fast) var(--ease-standard)',
                      }} />
            ))}
          </div>

          <span style={{ marginLeft: 'auto' }}>
            <button data-testid="walkthrough-skip"
                    onClick={() => close('skipped')}
                    style={ghostBtnStyle}>
              Skip walkthrough
            </button>
          </span>

          {!first && (
            <button data-testid="walkthrough-prev"
                    onClick={prev}
                    aria-label="Previous slide"
                    style={secondaryBtnStyle}>
              <ChevronLeft size={12} strokeWidth={1.5} />
              Back
            </button>
          )}

          {last ? (
            <button data-testid="walkthrough-finish"
                    onClick={finish}
                    style={primaryBtnStyle}>
              Get started
            </button>
          ) : (
            <button data-testid="walkthrough-next"
                    onClick={next}
                    aria-label="Next slide"
                    style={primaryBtnStyle}>
              Next
              <ChevronRight size={12} strokeWidth={1.5} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

/* ---- styles ---- */

const eyebrowStyle = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const btnBase = {
  fontFamily: 'inherit',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  padding: '6px 14px',
  borderRadius: 'var(--radius-1)',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
};

const primaryBtnStyle = {
  ...btnBase,
  background: 'var(--sig-info)',
  color: 'var(--surface-0)',
  border: '1px solid var(--sig-info)',
  fontWeight: 500,
};

const secondaryBtnStyle = {
  ...btnBase,
  background: 'transparent',
  color: 'var(--content-md)',
  border: '1px solid var(--stroke-2)',
};

const ghostBtnStyle = {
  ...btnBase,
  background: 'transparent',
  color: 'var(--content-lo)',
  border: '1px solid transparent',
};

const closeBtnStyle = {
  position: 'absolute',
  top: 'var(--space-3)',
  right: 'var(--space-3)',
  width: 28, height: 28,
  background: 'transparent',
  color: 'var(--content-md)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-1)',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
};
