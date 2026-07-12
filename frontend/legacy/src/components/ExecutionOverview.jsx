/**
 * ExecutionOverview — Restoration Step 4a (GATE 0 follow-up)
 * --------------------------------------------------------------------------
 * Restores the 1-vCPU "one glance" Execution landing (old Phase 9
 * ExecutionDashboard intent) as a thin, READ-ONLY status strip mounted as
 * the first section of the `exec` module. The detailed panels (Brokers ·
 * Paper · Runner · Live) remain stacked below as their own sections —
 * this composite only answers "what is the execution layer doing?" in
 * one row of KPI cards.
 *
 * Data sources (all pre-existing endpoints, read-only GETs, JWT attached
 * by the global fetch interceptor):
 *   • GET /api/execution/paper/runs?limit=5   → { count, runs[] }
 *   • GET /api/trade-runner/runs?limit=5      → { count, runs[] }
 *   • GET /api/live/strategies                → { tracked[] }
 *
 * No backend changes. No new endpoints. No mutations.
 */
import React, { useCallback, useEffect, useState } from 'react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

async function getJson(path) {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function KpiCard({ id, label, value, sub, tone = 'neutral' }) {
  const toneColor = {
    neutral: 'var(--cmd-ink-1, #E4E4E7)',
    good:    'var(--cmd-green, #34D399)',
    warn:    'var(--cmd-amber, #FBBF24)',
    err:     'var(--cmd-red, #F87171)',
  }[tone];
  return (
    <div
      data-testid={`exec-overview-${id}`}
      style={{
        flex: '1 1 180px',
        minWidth: 160,
        padding: '12px 14px',
        borderRadius: 6,
        border: '1px solid var(--cmd-hairline, #2A2D33)',
        background: 'var(--cmd-surface-0, #0E1116)',
      }}
    >
      <div style={{ fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--cmd-ink-2, #A1A1AA)' }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: toneColor, margin: '4px 0 2px', fontFamily: 'JetBrains Mono, monospace' }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: 'var(--cmd-ink-2, #A1A1AA)' }}>{sub}</div>
    </div>
  );
}

export default function ExecutionOverview() {
  const [paper, setPaper]   = useState(null);
  const [runner, setRunner] = useState(null);
  const [live, setLive]     = useState(null);
  const [err, setErr]       = useState(null);
  const [ts, setTs]         = useState(null);

  const refresh = useCallback(async () => {
    setErr(null);
    const [p, r, l] = await Promise.allSettled([
      getJson('/api/execution/paper/runs?limit=5'),
      getJson('/api/trade-runner/runs?limit=5'),
      getJson('/api/live/strategies'),
    ]);
    if (p.status === 'fulfilled') setPaper(p.value); else setErr((e) => e || p.reason.message);
    if (r.status === 'fulfilled') setRunner(r.value); else setErr((e) => e || r.reason.message);
    if (l.status === 'fulfilled') setLive(l.value); else setErr((e) => e || l.reason.message);
    setTs(new Date().toISOString().slice(11, 19));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const paperCount  = paper ? (paper.count ?? (paper.runs || []).length) : '—';
  const runnerCount = runner ? (runner.count ?? (runner.runs || []).length) : '—';
  const tracked     = live ? (live.tracked || []) : null;
  const liveCount   = tracked ? tracked.length : '—';
  const liveWarn    = tracked ? tracked.filter((t) => t && (t.status === 'WARNING' || t.status === 'FAILING' || t.status === 'AUTO_DISABLED')).length : 0;

  const lastOf = (obj) => {
    const runs = (obj && obj.runs) || [];
    const first = runs[0] || {};
    return first.status || first.state || (runs.length ? 'recorded' : 'none yet');
  };

  return (
    <div data-testid="exec-overview" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--cmd-ink-2, #A1A1AA)' }}>
          One-glance execution status — detail panels stacked below.
        </span>
        <div style={{ flex: 1 }} />
        {ts && (
          <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono, monospace', color: 'var(--cmd-ink-2, #A1A1AA)' }}>
            as of {ts}Z
          </span>
        )}
        <button
          type="button"
          data-testid="exec-overview-refresh"
          onClick={refresh}
          style={{
            fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase',
            padding: '4px 10px', borderRadius: 4, cursor: 'pointer',
            border: '1px solid var(--cmd-hairline, #2A2D33)',
            background: 'transparent', color: 'var(--cmd-ink-1, #E4E4E7)',
          }}
        >
          Refresh
        </button>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <KpiCard
          id="paper"
          label="Paper Execution"
          value={paperCount}
          sub={`runs recorded · latest: ${lastOf(paper)}`}
          tone={paper && paperCount > 0 ? 'good' : 'neutral'}
        />
        <KpiCard
          id="runner"
          label="Trade Runner"
          value={runnerCount}
          sub={`runs recorded · latest: ${lastOf(runner)}`}
          tone={runner && runnerCount > 0 ? 'good' : 'neutral'}
        />
        <KpiCard
          id="live"
          label="Live Tracking"
          value={liveCount}
          sub={tracked ? `${liveWarn} need attention` : 'tracked strategies'}
          tone={tracked && liveWarn > 0 ? 'warn' : (tracked && tracked.length > 0 ? 'good' : 'neutral')}
        />
      </div>
      {err && (
        <div data-testid="exec-overview-error" style={{ fontSize: 11, color: 'var(--cmd-amber, #FBBF24)' }}>
          partial data · {err}
        </div>
      )}
    </div>
  );
}
