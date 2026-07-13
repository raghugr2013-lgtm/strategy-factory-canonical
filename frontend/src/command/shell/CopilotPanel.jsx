/**
 * CopilotPanel — Phase R5
 * --------------------------------------------------------------------------
 * Global right-side panel (480-640px) backed by existing AI workforce data:
 *   - /api/orchestrator/heartbeat        → last_advisory + history
 *   - /api/llm/call-log/recent           → 9-tile activity summary
 *
 * Read-only advisory surface. Carries the advisory badge "no execution
 * authority" required by Handoff Screen 39. No new backend, no mock data.
 */
import React, { useEffect, useState } from 'react';
import { API_URL as API } from '../../services/api';


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

export default function CopilotPanel({ open, onClose }) {
  const [hb, setHb] = useState(null);
  const [calls, setCalls] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.allSettled([
      authedJson('/api/orchestrator/heartbeat'),
      authedJson('/api/llm/call-log/recent'),
    ]).then(([h, c]) => {
      if (cancelled) return;
      if (h.status === 'fulfilled') setHb(h.value);
      if (c.status === 'fulfilled') {
        const rows = c.value.rows || c.value.items || c.value || [];
        setCalls(Array.isArray(rows) ? rows.slice(0, 9) : []);
      }
      setLoading(false);
    }).catch((e) => { if (!cancelled) { setError(String(e)); setLoading(false); } });

    return () => { cancelled = true; };
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div
        data-testid="copilot-scrim"
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
          backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
          zIndex: 998,
        }}
      />
      <aside
        data-testid="copilot-panel"
        role="dialog"
        aria-label="Copilot"
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, width: 560,
          maxWidth: '100vw',
          background: 'var(--cmd-canvas, #0A0C10)',
          borderLeft: '1px solid var(--cmd-line, #2A2D33)',
          zIndex: 999, display: 'flex', flexDirection: 'column',
          boxShadow: '-12px 0 32px rgba(0,0,0,0.45)',
        }}
      >
        <header style={{ padding: '14px 16px', borderBottom: '1px solid var(--cmd-line)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ margin: 0, fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              Copilot
            </h2>
            <button
              data-testid="copilot-close"
              onClick={onClose}
              aria-label="Close copilot"
              style={{ background: 'none', border: 'none', color: 'var(--cmd-ink-2)', fontSize: 18, cursor: 'pointer' }}
            >×</button>
          </div>
          <div style={{ marginTop: 8 }}>
            <span
              data-testid="copilot-advisory-badge"
              style={{
                display: 'inline-block', padding: '2px 8px', fontSize: 9,
                fontWeight: 700, letterSpacing: '0.10em', textTransform: 'uppercase',
                borderRadius: 3, border: '1px solid #FFB454', color: '#FFB454',
                background: 'rgba(255,180,84,0.08)',
              }}
            >Advisory · no execution authority</span>
          </div>
        </header>

        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
          {loading && <div style={{ fontSize: 11, color: 'var(--cmd-ink-2)' }}>Loading…</div>}
          {error && (
            <div data-testid="copilot-error" style={{
              padding: 12, fontSize: 11, color: '#FF6B6B', borderLeft: '3px solid #FF6B6B',
              background: 'rgba(255,107,107,0.08)',
            }}>{error}</div>
          )}

          {!loading && (
            <>
              <section style={{ marginBottom: 24 }} data-testid="copilot-last-advisory">
                <h3 style={{ fontSize: 10, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--cmd-ink-2)', margin: '0 0 8px' }}>
                  Last advisory
                </h3>
                <p style={{ fontSize: 13, color: 'var(--cmd-ink-1, #E4E4E7)', margin: 0, lineHeight: 1.5 }}>
                  {hb?.last_advisory || hb?.message || 'No advisory yet — orchestrator is idle or unreachable.'}
                </p>
              </section>

              <section data-testid="copilot-activity">
                <h3 style={{ fontSize: 10, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--cmd-ink-2)', margin: '0 0 8px' }}>
                  Recent LLM activity ({calls.length})
                </h3>
                {calls.length === 0 && (
                  <div style={{ fontSize: 11, color: 'var(--cmd-ink-2)' }}>
                    No recent calls. The AI workforce is quiet.
                  </div>
                )}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                  {calls.map((c, idx) => (
                    <article
                      key={idx}
                      data-testid={`copilot-call-${idx}`}
                      style={{
                        padding: 8, border: '1px solid var(--cmd-line)', borderRadius: 4,
                        fontSize: 10, lineHeight: 1.35, background: 'var(--cmd-panel, #14171C)',
                      }}
                    >
                      <div style={{ color: 'var(--cmd-accent, #7AB8FF)', fontFamily: 'ui-monospace, monospace' }}>
                        {c.provider || c.model || 'llm'}
                      </div>
                      <div style={{ color: 'var(--cmd-ink-1)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {c.intent || c.purpose || c.kind || 'call'}
                      </div>
                      <div style={{ color: 'var(--cmd-ink-2)', marginTop: 4, fontFamily: 'ui-monospace, monospace' }}>
                        {c.latency_ms != null ? `${c.latency_ms}ms` : (c.ts || c.timestamp || '')}
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              <section style={{ marginTop: 24, padding: 12, border: '1px dashed var(--cmd-line)', borderRadius: 4 }}>
                <p style={{ fontSize: 10, color: 'var(--cmd-ink-2)', margin: 0 }}>
                  Conversational chat is a deferred surface. This panel currently shows the
                  read-only advisory feed and call activity; chat input will be wired in a
                  follow-up phase once the LLM adapter is provisioned.
                </p>
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
