/*
 * SignalStateBadge — canonical §7 primitive.
 * refs docs/ARCHITECTURE.md §7 · Canonical SignalState vocabulary
 *
 * Six-state taxonomy replacing the ad-hoc LIVE / PARTIAL LIVE / GATED / ERROR
 * chip set. Every "how live / how trusted is this?" indicator across the
 * product uses this component.
 *
 *   live      · Endpoint responded, payload is meaningful, data is current.
 *   partial   · Endpoint responded 200 but data is sparse or preliminary.
 *   deferred  · Capability exists in the roadmap but its endpoint is not
 *               yet live under the current freeze.
 *   gated     · Endpoint exists but caller lacks the role, or a feature
 *               flag is off.
 *   empty     · Endpoint responded 200 with an empty collection AND the
 *               collection is expected to fill within normal operation.
 *   error     · Network failure, 5xx, or unexpected schema.
 *
 * Chip anatomy is identical everywhere:
 *   [ • STATE_LABEL ]   title = short human reason
 *
 * Backwards compatibility: the legacy `partial-live` value is accepted and
 * treated as `partial` so the migration can proceed incrementally.
 */
import React from 'react';

const TONES = {
  live:     { color: 'var(--sig-ok)',       label: 'LIVE'     },
  partial:  { color: 'var(--sig-warn)',     label: 'PARTIAL'  },
  deferred: { color: 'var(--sig-advisory)', label: 'DEFERRED' },
  gated:    { color: 'var(--sig-dormant)',  label: 'GATED'    },
  empty:    { color: 'var(--sig-dormant)',  label: 'EMPTY'    },
  error:    { color: 'var(--sig-crit)',     label: 'ERROR'    },
};

// Legacy → canonical shim. Keep until the next architecture change trigger.
const CANONICAL = (v) => (v === 'partial-live' ? 'partial' : v);

export const SignalStateBadge = ({ state = 'partial', reason, testId = 'signal-state-badge' }) => {
  const canonical = CANONICAL(state);
  const t = TONES[canonical] || TONES.partial;
  return (
    <span data-testid={testId}
          data-signal-state={canonical}
          title={reason || undefined}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '3px 10px', borderRadius: 999,
            background: `color-mix(in oklab, ${t.color} 12%, transparent)`,
            border: `1px solid color-mix(in oklab, ${t.color} 40%, transparent)`,
            color: t.color,
            fontSize: 'var(--font-caption)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            fontWeight: 500,
            whiteSpace: 'nowrap',
          }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor' }} />
      {t.label}
    </span>
  );
};

/**
 * LivenessBadge — legacy alias. Accepts the historical `liveness` prop and
 * forwards to the canonical component. Kept so existing callers compile
 * unchanged during the Slice-α migration. Do not use in new code.
 */
export const LivenessBadge = ({ liveness, reason, testId }) => (
  <SignalStateBadge state={liveness} reason={reason} testId={testId} />
);

export const FreezeCaption = ({ testId = 'freeze-caption' }) => (
  <div data-testid={testId}
       style={{
         fontSize: 'var(--font-caption)',
         color: 'var(--content-lo)',
         letterSpacing: '0.08em',
         textTransform: 'uppercase',
       }}>
    Backend Feature Freeze · v1.1.0-stage4
  </div>
);
