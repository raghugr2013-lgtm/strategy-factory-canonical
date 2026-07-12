/**
 * Phase U-3 · Notifications Store (SSOT)
 * ----------------------------------------------------------------------------
 * Lightweight pub/sub notification queue, theme-store style.
 *  • `push({ title, body, tone, slug, action })` → append a notification.
 *  • `dismiss(id)` / `dismissAll()` → remove items.
 *  • `useNotifications()` → React hook returning the live list.
 *  • `getUnreadCount()` / `markAllRead()` → bell badge management.
 *
 * Tones: 'info' | 'success' | 'warn' | 'danger'.
 * Notifications are ephemeral (in-memory only). No backend dependency.
 */
import { useSyncExternalStore } from 'react';

const listeners = new Set();
let _state = {
  items: [],         // newest first
  lastReadAt: 0,     // epoch ms
};

function emit() {
  for (const l of listeners) l();
}

function subscribe(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function getSnapshot() {
  return _state;
}

let _id = 0;
function nextId() {
  _id += 1;
  return `n-${Date.now().toString(36)}-${_id}`;
}

export function push({ title, body, tone = 'info', slug, action } = {}) {
  if (!title && !body) return null;
  const item = {
    id: nextId(),
    title: title || '',
    body: body || '',
    tone,
    slug: slug || null,
    action: action || null,    // { label, onClick, testId }
    at: Date.now(),
  };
  _state = { ..._state, items: [item, ..._state.items].slice(0, 50) };
  emit();
  return item.id;
}

export function dismiss(id) {
  _state = { ..._state, items: _state.items.filter((i) => i.id !== id) };
  emit();
}

export function dismissAll() {
  _state = { ..._state, items: [] };
  emit();
}

export function markAllRead() {
  _state = { ..._state, lastReadAt: Date.now() };
  emit();
}

export function getUnreadCount() {
  return _state.items.filter((i) => i.at > _state.lastReadAt).length;
}

export function useNotifications() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
