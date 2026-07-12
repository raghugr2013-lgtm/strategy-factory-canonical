/**
 * Phase U-4.2 · EmergencyBanner
 * ----------------------------------------------------------------------------
 * Renders a sticky amber banner on viewports ≤ 480px so on-call operators
 * coming in from a phone know they're on an emergency-access surface (read
 * mostly, limited controls). Listens to the `(max-width: 480px)` media query
 * and unmounts when the viewport grows back.
 */
import React, { useEffect, useState } from 'react';

function usePocketViewport() {
  const [isPocket, setIsPocket] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(max-width: 480px)').matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(max-width: 480px)');
    const onChange = (e) => setIsPocket(e.matches);
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else mq.addListener(onChange);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener('change', onChange);
      else mq.removeListener(onChange);
    };
  }, []);
  return isPocket;
}

export default function EmergencyBanner() {
  const isPocket = usePocketViewport();
  if (!isPocket) return null;
  return (
    <div
      data-testid="cmd-emergency-banner"
      role="alert"
      aria-live="polite"
    >
      Emergency access · open on desktop for full controls
    </div>
  );
}
