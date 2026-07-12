/**
 * Phase U-4.1 · AriaLiveRegion
 * ----------------------------------------------------------------------------
 * Mounts a single off-screen polite live-region at the shell root. When a
 * new notification is pushed via the notifications store, its title+body
 * are mirrored into this region so screen readers announce the event.
 *
 * Implementation note: the announcement string is *derived* directly from
 * the newest notification (no internal setState in effect). To force the
 * screen reader to re-announce when an identical string repeats, we set
 * `key={newest.id}` on the region — SRs treat re-mounted aria-live nodes
 * as a fresh announcement.
 */
import React from 'react';
import { useNotifications } from '../../stores/notificationsStore';

const SR_ONLY_STYLE = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0,0,0,0)',
  whiteSpace: 'nowrap',
  border: 0,
};

const TONE_PREFIX = {
  danger: 'Alert.',
  warn: 'Warning.',
  success: 'Success.',
  info: '',
  neutral: '',
};

function buildMessage(item) {
  if (!item) return '';
  const parts = [];
  const prefix = TONE_PREFIX[item.tone] || '';
  if (prefix) parts.push(prefix);
  if (item.title) parts.push(item.title);
  if (item.body) parts.push(item.body);
  return parts.join(' ').trim();
}

export default function AriaLiveRegion() {
  const { items } = useNotifications();
  const newest = items[0];
  const msg = buildMessage(newest);
  return (
    <div
      key={newest ? newest.id : 'empty'}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid="asf-aria-live"
      style={SR_ONLY_STYLE}
    >
      {msg}
    </div>
  );
}
