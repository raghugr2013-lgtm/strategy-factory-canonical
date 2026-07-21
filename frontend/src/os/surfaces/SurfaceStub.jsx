/*
 * SurfaceStub — reusable M1 empty surface.
 * refs DESIGN_FREEZE_v1.0.md §1.4 (surfaces) · D8 §6 (StateTemplate contract)
 *
 * Each surface renders a SurfaceHeader + StateTemplate empty until its
 * milestone (M4) ships. Copy is authored in Division voice per D2 Addendum
 * so that the Freeze §1.2 principle E4 (Continuity of Voice) is satisfied
 * even in Sprint 1 M1.
 */
import React from 'react';
import { useLocation } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { ROUTES } from '../routing/routes';

export const SurfaceStub = ({ headline, briefing, milestone = 'M4', testId }) => {
  const location = useLocation();
  const route = ROUTES.find((r) => location.pathname.startsWith(r.path));
  const eyebrow = route?.label ?? '—';

  return (
    <section data-testid={testId ?? 'surface-stub'}
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1200 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{eyebrow}</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ color: 'var(--sig-info)', fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Sprint 1 · {milestone}</span>
      </div>
      <h1 data-testid={`${testId}-headline`}
          style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        {headline}
      </h1>
      <p data-testid={`${testId}-briefing`}
         style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 720, fontSize: 'var(--font-body-md)', lineHeight: 1.55, color: 'var(--content-md)' }}>
        {briefing}
      </p>

      <div style={{
        background: 'var(--surface-1)',
        border: '1px dashed var(--stroke-2)',
        borderRadius: 'var(--radius-3)',
        padding: 'var(--space-6)',
        display: 'grid',
        placeItems: 'center',
        gap: 'var(--space-3)',
        color: 'var(--content-md)',
        textAlign: 'center',
      }}>
        <Compass size={28} strokeWidth={1.25} color="var(--content-lo)" />
        <div style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--content-lo)' }}>Empty · scheduled for {milestone}</div>
        <div style={{ fontSize: 'var(--font-body-sm)' }}>
          The Foundation shell is live. This surface ships its full layout in Sprint 1 · {milestone}.
        </div>
      </div>
    </section>
  );
};
