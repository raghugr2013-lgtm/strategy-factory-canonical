/**
 * NotificationDrawer — Phase R5
 * --------------------------------------------------------------------------
 * Global right-side drawer (480px) consuming existing backend data:
 *   - /api/monitoring/status        → breaches[] · recent_actions[]
 *   - /api/admin/widening-proposals → pending proposals
 *   - /api/orchestrator/heartbeat   → orchestrator advisory entries
 *
 * No new endpoints; no mock data. If a source returns empty arrays the
 * drawer shows a labelled empty-state. Severity tabs filter the merged list.
 */
import React, { useEffect, useMemo, useState } from 'react';

const API = process.env.REACT_APP_BACKEND_URL;

function getToken() {
  try { return localStorage.getItem('asf_auth_token'); } catch (_) { return null; }
}

async function authedJson(path) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetch(`${API}${path}`, { headers, cache: 'no-store' });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

const SEVERITY_COLOR = {
  critical: '#FF6B6B',
  fatal:    '#FF6B6B',
  warn:     '#FFB454',
  info:     '#7AB8FF',
  ok:       '#69D58C',
};

function normalize(items) {
  return items.map((it, idx) => ({
    id:        it.id || `notif-${idx}`,
    severity:  (it.severity || it.level || 'info').toLowerCase(),
    timestamp: it.timestamp || it.created_at || it.ts || null,
    module:    it.module || it.source || '—',
    message:   it.message || it.summary || it.description || JSON.stringify(it).slice(0, 120),
  }));
}

export default function NotificationDrawer({ open, onClose }) {
  const [tab, setTab] = useState('all');
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      const collected = [];
      // 1) Monitoring breaches + recent actions
      try {
        const ms = await authedJson('/api/monitoring/status');
        (ms.breaches || []).forEach((b) =>
          collected.push({ ...b, severity: 'warn', module: 'monitoring' })
        );
        (ms.recent_actions || []).forEach((a) =>
          collected.push({ ...a, severity: 'info', module: 'monitoring' })
        );
      } catch (_) { /* tolerate */ }
      // 2) Widening proposals
      try {
        const wp = await authedJson('/api/admin/widening-proposals');
        const list = wp.proposals || wp.items || wp || [];
        list.forEach((p) =>
          collected.push({
            id: p.id,
            severity: p.status === 'pending' ? 'info' : 'ok',
            timestamp: p.created_at,
            module: 'governance',
            message: p.summary || `Widening proposal: ${p.flag || ''}`,
          })
        );
      } catch (_) { /* tolerate */ }
      // 3) Orchestrator advisory recent
      try {
        const oh = await authedJson('/api/orchestrator/heartbeat');
        if (oh && oh.last_advisory) {
          collected.push({
            id: 'orch-last',
            severity: 'info',
            timestamp: oh.last_ts,
            module: 'ai',
            message: oh.last_advisory,
          });
        }
      } catch (_) { /* tolerate */ }

      if (cancelled) return;
      const norm = normalize(collected);
      setItems(norm);
      setLoading(false);
      if (norm.length === 0) setError(null);
    })().catch((e) => { if (!cancelled) { setError(String(e)); setLoading(false); } });

    return () => { cancelled = true; };
  }, [open]);

  const filtered = useMemo(() => {
    if (tab === 'all') return items;
    return items.filter((it) => it.severity === tab || (tab === 'critical' && it.severity === 'fatal'));
  }, [items, tab]);

  if (!open) return null;

  return (
    <>
      <div
        data-testid="notification-scrim"
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
          backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
          zIndex: 999,
        }}
      />
      <aside
        data-testid="notification-drawer"
        role="dialog"
        aria-label="Notifications"
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, width: 480,
          maxWidth: '100vw',
          background: 'var(--cmd-canvas, #0A0C10)',
          borderLeft: '1px solid var(--cmd-line, #2A2D33)',
          zIndex: 1000, display: 'flex', flexDirection: 'column',
          boxShadow: '-12px 0 32px rgba(0,0,0,0.45)',
        }}
      >
        <header style={{ padding: '14px 16px', borderBottom: '1px solid var(--cmd-line)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ margin: 0, fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--cmd-ink-1, #E4E4E7)' }}>
              Notifications
            </h2>
            <button
              data-testid="notification-close"
              onClick={onClose}
              aria-label="Close notifications"
              style={{ background: 'none', border: 'none', color: 'var(--cmd-ink-2)', fontSize: 18, cursor: 'pointer' }}
            >×</button>
          </div>
          <div style={{ display: 'flex', gap: 4, marginTop: 12 }}>
            {['all', 'warn', 'critical', 'info'].map((t) => (
              <button
                key={t}
                data-testid={`notification-tab-${t}`}
                onClick={() => setTab(t)}
                style={{
                  padding: '4px 10px', fontSize: 10, fontWeight: 600,
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  borderRadius: 3,
                  border: '1px solid',
                  borderColor: tab === t ? 'var(--cmd-accent, #7AB8FF)' : 'var(--cmd-line)',
                  background: tab === t ? 'rgba(122,184,255,0.12)' : 'transparent',
                  color: tab === t ? 'var(--cmd-accent, #7AB8FF)' : 'var(--cmd-ink-1, #E4E4E7)',
                  cursor: 'pointer',
                }}
              >{t}</button>
            ))}
          </div>
        </header>

        <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
          {loading && <div style={{ padding: 16, fontSize: 11, color: 'var(--cmd-ink-2)' }}>Loading…</div>}
          {error && (
            <div data-testid="notification-error" style={{
              padding: 12, fontSize: 11, color: '#FF6B6B', borderLeft: '3px solid #FF6B6B',
              background: 'rgba(255,107,107,0.08)', margin: 8,
            }}>{error}</div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div data-testid="notification-empty" style={{ padding: 24, fontSize: 11, color: 'var(--cmd-ink-2)' }}>
              No notifications. The system is quiet — well done.
            </div>
          )}
          {!loading && filtered.map((it) => (
            <article
              key={it.id}
              data-testid={`notification-row-${it.id}`}
              style={{
                display: 'flex', gap: 10, padding: '10px 12px',
                borderBottom: '1px solid var(--cmd-line)',
              }}
            >
              <span
                aria-hidden
                style={{
                  width: 8, height: 8, borderRadius: 4, marginTop: 6,
                  background: SEVERITY_COLOR[it.severity] || SEVERITY_COLOR.info,
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 10, color: 'var(--cmd-ink-2)' }}>
                  <span style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>{it.module}</span>
                  {it.timestamp && <span style={{ fontFamily: 'ui-monospace, monospace' }}>{it.timestamp}</span>}
                </div>
                <div style={{ fontSize: 12, color: 'var(--cmd-ink-1, #E4E4E7)', marginTop: 4, overflowWrap: 'break-word' }}>
                  {it.message}
                </div>
              </div>
            </article>
          ))}
        </div>
      </aside>
    </>
  );
}
