/**
 * ASF · RC1 Parity Closure — Reusable Operator Endpoint Panel
 * ----------------------------------------------------------------------------
 * A thin, design-system-consistent surface that exposes a group of backend
 * endpoints to the operator without bespoke per-route UI. Used by the new
 * parity-closure modules:
 *   • Master Bot       (MasterBotDashboard.jsx is the existing rich UI,
 *                       wrapped directly — no OperatorEndpointPanel needed.)
 *   • Factory Supervisor   → /api/factory-supervisor/*
 *   • Scaling controls     → /api/scaling/*
 *   • Phase 12 tuning      → /api/phase12-tuning/*
 *   • GEM Factory          → /api/gem-factory/*
 *   • Admin Flag Governance → /api/admin/flag-governance/*
 *   • Admin Execution Realism → /api/admin/execution-realism/*
 *   • Data backup          → /api/data/backup/*
 *   • Soak diagnostics     → /api/soak/diagnostics/*
 *   • CPU pool state       → /api/cpu-pool-state
 *
 * Design contract:
 *   • Uses asf-section / asf-u2-panel surfaces — inherits the U-2 design system.
 *   • Uses VerdictChip + sr-only tone labels — inherits U-4.1 a11y.
 *   • Light + dark themes both supported via existing tokens.
 *   • No mutation of backend state on render — operator must explicitly press
 *     "Run" on any non-GET endpoint.
 *   • Returns the raw JSON response so the operator can read the truth.
 *
 * Guardrails:
 *   • No backend / API / DB / strategy-engine changes (this is a UI viewer).
 *   • No authentication bypass — runs under the same preview auth as the rest
 *     of the workstation.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';

const API_BASE = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');

const METHOD_TONE = {
  GET:    { tone: 'info',    label: 'GET'    },
  POST:   { tone: 'warn',    label: 'POST'   },
  PUT:    { tone: 'warn',    label: 'PUT'    },
  PATCH:  { tone: 'warn',    label: 'PATCH'  },
  DELETE: { tone: 'danger',  label: 'DELETE' },
};

function MethodPill({ method }) {
  const m = METHOD_TONE[method] || { tone: 'neutral', label: method };
  return (
    <span
      className="asf-vchip"
      data-verdict={m.tone}
      data-testid={`operator-endpoint-method-${method.toLowerCase()}`}
      style={{
        display: 'inline-block', padding: '2px 8px',
        borderRadius: 4, fontSize: 11, fontWeight: 600,
        border: '1px solid currentColor', minWidth: 56, textAlign: 'center',
      }}
    >
      <span className="sr-only">HTTP method </span>{m.label}
    </span>
  );
}

function PayloadEditor({ value, onChange, testid }) {
  return (
    <textarea
      data-testid={testid}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder='{"key": "value"} — optional JSON payload'
      aria-label="Request payload"
      spellCheck={false}
      rows={4}
      style={{
        width: '100%', padding: 8,
        background: 'var(--cmd-surface-0, #0a0f19)',
        border: '1px solid var(--cmd-hairline, #1f2a3b)',
        borderRadius: 4, color: 'inherit',
        fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, monospace',
        fontSize: 12, lineHeight: 1.5,
      }}
    />
  );
}

function ResponseView({ status, body, error }) {
  if (status == null && !error) {
    return (
      <div
        data-testid="operator-endpoint-response-empty"
        style={{ padding: 8, fontSize: 12, color: 'var(--cmd-ink-3, #94A3B8)' }}
      >
        — no response yet —
      </div>
    );
  }
  return (
    <div data-testid="operator-endpoint-response">
      <div style={{ marginBottom: 6, fontSize: 11, color: 'var(--cmd-ink-2, #8A93A4)' }}>
        STATUS: <strong>{status ?? 'network error'}</strong>
        {error && <span style={{ marginLeft: 8, color: '#FCA5A5' }}> · {error}</span>}
      </div>
      <pre
        style={{
          margin: 0, padding: 8,
          background: 'var(--cmd-surface-0, #0a0f19)',
          border: '1px solid var(--cmd-hairline, #1f2a3b)',
          borderRadius: 4,
          maxHeight: 320, overflow: 'auto',
          fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, monospace',
          fontSize: 11, lineHeight: 1.45, color: 'var(--cmd-ink-1, #E4E4E7)',
        }}
      >{typeof body === 'string' ? body : JSON.stringify(body, null, 2)}</pre>
    </div>
  );
}

function EndpointRow({ ep }) {
  const [open, setOpen] = useState(ep.method === 'GET' && ep.runOnMount === true);
  const [payload, setPayload] = useState(ep.samplePayload ? JSON.stringify(ep.samplePayload, null, 2) : '');
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState({ status: null, body: null, error: null });

  const run = useCallback(async () => {
    setLoading(true);
    setResp({ status: null, body: null, error: null });
    try {
      const headers = { 'Content-Type': 'application/json' };
      const init = { method: ep.method, headers };
      if (ep.method !== 'GET' && ep.method !== 'HEAD' && payload.trim()) {
        init.body = payload;
      }
      const url = `${API_BASE}${ep.path}`;
      const r = await fetch(url, init);
      const txt = await r.text();
      let body = txt;
      try { body = JSON.parse(txt); } catch (_) { /* keep as text */ }
      setResp({ status: r.status, body, error: null });
    } catch (e) {
      setResp({ status: null, body: null, error: String(e && e.message ? e.message : e) });
    } finally {
      setLoading(false);
    }
  }, [ep.method, ep.path, payload]);

  useEffect(() => {
    if (ep.method === 'GET' && ep.runOnMount === true) {
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const epTid = `operator-endpoint-${ep.method.toLowerCase()}-${ep.path.replace(/[^\w]+/g, '-').replace(/^-|-$/g, '')}`;

  return (
    <div
      className="asf-section"
      data-testid={`${epTid}-row`}
      style={{
        padding: 12, marginBottom: 8,
        background: 'var(--cmd-surface-1, #0F141B)',
        border: '1px solid var(--cmd-hairline, #1f2a3b)',
        borderRadius: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <MethodPill method={ep.method} />
        <code
          style={{
            fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, monospace',
            fontSize: 13, color: 'var(--cmd-ink-0, #E4E4E7)',
            flex: 1, wordBreak: 'break-all',
          }}
        >{ep.path}</code>
        <button
          data-testid={`${epTid}-toggle`}
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-label={`${open ? 'Collapse' : 'Expand'} endpoint ${ep.method} ${ep.path}`}
          style={{
            padding: '4px 10px', fontSize: 11,
            background: 'transparent',
            border: '1px solid var(--cmd-hairline, #1f2a3b)',
            color: 'var(--cmd-ink-1, #E4E4E7)',
            borderRadius: 4, cursor: 'pointer',
          }}
        >{open ? '−' : '+'}</button>
      </div>
      {ep.description && (
        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--cmd-ink-2, #8A93A4)' }}>
          {ep.description}
        </div>
      )}
      {open && (
        <div style={{ marginTop: 10 }}>
          {ep.method !== 'GET' && ep.method !== 'HEAD' && (
            <div style={{ marginBottom: 8 }}>
              <PayloadEditor
                value={payload}
                onChange={setPayload}
                testid={`${epTid}-payload`}
              />
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <button
              data-testid={`${epTid}-run`}
              onClick={run}
              disabled={loading}
              aria-label={`Run ${ep.method} ${ep.path}`}
              style={{
                padding: '6px 14px', fontSize: 12, fontWeight: 600,
                background: ep.method === 'GET' ? '#0E7490' : '#B45309',
                color: '#FFFFFF', border: 'none', borderRadius: 4,
                cursor: loading ? 'wait' : 'pointer',
                opacity: loading ? 0.7 : 1,
              }}
            >{loading ? 'Running…' : 'Run'}</button>
          </div>
          <ResponseView {...resp} />
        </div>
      )}
    </div>
  );
}

export default function OperatorEndpointPanel({ title, subtitle, endpoints, surfaceTestid }) {
  const grouped = useMemo(() => {
    const g = {};
    for (const ep of endpoints || []) {
      const key = ep.group || '';
      if (!g[key]) g[key] = [];
      g[key].push(ep);
    }
    return g;
  }, [endpoints]);

  return (
    <section
      className="asf-section asf-u2-panel"
      data-testid={surfaceTestid || 'operator-endpoint-panel'}
      style={{ padding: 16 }}
    >
      <header style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: 'var(--cmd-ink-0)' }}>
          {title}
        </h2>
        {subtitle && (
          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--cmd-ink-2)' }}>
            {subtitle}
          </div>
        )}
        <div style={{ marginTop: 6, fontSize: 11, color: 'var(--cmd-ink-3)' }}>
          {(endpoints || []).length} endpoint{(endpoints || []).length !== 1 ? 's' : ''}
          · expand a row to inspect or run · responses returned as raw JSON
        </div>
      </header>
      {Object.entries(grouped).map(([group, eps]) => (
        <div key={group || 'default'} style={{ marginBottom: 14 }}>
          {group && (
            <div
              style={{
                fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.6,
                color: 'var(--cmd-ink-2)', marginBottom: 6,
              }}
            >{group}</div>
          )}
          {eps.map((ep) => (
            <EndpointRow key={`${ep.method} ${ep.path}`} ep={ep} />
          ))}
        </div>
      ))}
    </section>
  );
}
