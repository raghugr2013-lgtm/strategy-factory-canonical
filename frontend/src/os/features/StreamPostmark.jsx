/*
 * StreamPostmark — Sprint 2 N3.
 * Small visual affordance rendered next to every streaming surface header.
 * Shows the transport mode + last tick timestamp.
 * refs Design Freeze §1.4 (postmarks are already part of the system).
 */
import React from 'react';
import { Radio, RefreshCw } from 'lucide-react';

const formatTime = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}:${String(d.getUTCSeconds()).padStart(2, '0')}Z`;
};

export const StreamPostmark = ({ status, testId = 'stream-postmark' }) => {
  const isLive = status.mode === 'wss';
  const Icon = isLive ? Radio : RefreshCw;
  const modeLabel = isLive ? 'stream · WSS' : status.mode === 'poll' ? 'stream · poll fallback' : status.mode === 'initial' ? 'stream · warming' : 'stream · idle';
  return (
    <span data-testid={testId}
          data-stream-mode={status.mode}
          data-stream-tick-count={status.tickCount}
          data-stream-tick-at={status.tickAt ?? ''}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)',
                   padding: '2px 8px', borderRadius: 'var(--radius-1)',
                   background: 'var(--surface-2)', border: '1px solid var(--stroke-1)',
                   fontSize: 'var(--font-caption)', color: 'var(--content-md)',
                   textTransform: 'uppercase', letterSpacing: '0.06em' }}>
      <Icon size={11} strokeWidth={1.6} aria-hidden />
      <span>{modeLabel}</span>
      <span aria-hidden style={{ color: 'var(--content-lo)' }}>·</span>
      <span className="mono-num">{formatTime(status.tickAt)}</span>
    </span>
  );
};
