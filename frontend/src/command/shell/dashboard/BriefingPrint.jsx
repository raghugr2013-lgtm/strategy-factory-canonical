/**
 * COMMAND · Phase U.5.b — Briefing Print Mode
 * ============================================================================
 * Paper-light, audit-stable, mission-control executive dossier rendered when
 * the URL carries `?print=1`. NEVER polls. Performs exactly one fetch on
 * mount via `fetchBriefingOnce()` so the snapshot is reproducible for
 * institutional review, governance handoff, or PDF export.
 *
 * DOCTRINE
 * ---------
 *  • Deep-linkable: `?print=1` is canonical.
 *  • Calm, executive, legible-on-paper. No glow. No dark surfaces. No charts.
 *  • Narrative-first: attention is the lead section; telemetry follows.
 *  • Responsive doctrine: tablet reflows to 2-col, briefing to 1-col.
 *    NEVER a squashed desktop layout — the print is its own posture.
 *  • Reversible: deleting this file + briefing-print.css removes U.5.b.
 *  • Inspector intentionally not available — print mode is read-only.
 *
 * BODY HOOK
 * ---------
 * On mount, sets `<body data-cmd-print="1">`. The print stylesheet (also
 * scoped under `[data-ui="command"]`) hides the bar/rail/status/inspector
 * and substitutes paper-light token values. On unmount we restore the
 * previous attribute.
 */
import React, { useEffect, useState } from 'react';
import { fetchBriefingOnce, synthesizeAttention } from './briefingData';

function iso(d) {
  if (!d) return '—';
  try { return new Date(d).toISOString(); } catch (_) { return String(d); }
}

function PrintHeader({ data }) {
  const ts = iso(data?.fetched_at);
  const env = (data?.health?.env || data?.readiness?.env || 'PROD').toUpperCase();
  const provider = data?.llm?.primary_provider || '—';
  return (
    <header className="brief-print__hd" data-testid="print-header">
      <div className="brief-print__hd-row">
        <div className="brief-print__title-block">
          <div className="brief-print__eyebrow">strategy factory · operations briefing</div>
          <h1 className="brief-print__title">Mission Briefing</h1>
        </div>
        <dl className="brief-print__meta">
          <div><dt>generated</dt><dd>{ts}</dd></div>
          <div><dt>environment</dt><dd>{env}</dd></div>
          <div><dt>ai provider</dt><dd>{provider}</dd></div>
        </dl>
      </div>
      <hr className="brief-print__rule" />
    </header>
  );
}

function PrintAttention({ items }) {
  return (
    <section className="brief-print__sect" data-testid="print-attention">
      <h2 className="brief-print__h2">1 · Attention</h2>
      {items.length === 0 ? (
        <p className="brief-print__body">
          All monitored subsystems are within tolerance at the time of this
          briefing. No operator action is required.
        </p>
      ) : (
        <ol className="brief-print__attn-list">
          {items.map((it) => (
            <li
              key={it.key}
              className={`brief-print__attn brief-print__attn--${it.tone}`}
              data-testid={`print-attn-${it.key}`}
            >
              <span className="brief-print__attn-tone">
                {it.tone === 'red' ? 'CRITICAL' : 'WARN'}
              </span>
              <div className="brief-print__attn-body">
                <span className="brief-print__attn-label">{it.label}</span>
                {it.hint && <span className="brief-print__attn-hint">{it.hint}</span>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function PrintPosture({ data }) {
  const llm = data?.llm || {};
  const runner = data?.runner || {};
  const heartbeat = data?.heartbeat || {};
  const ingestion = data?.ingestion || {};

  const provider = llm.primary_provider || '—';
  const configured = !!(llm.providers && llm.providers[provider]?.configured);
  const activeCalls = runner.active_semaphores ? Object.keys(runner.active_semaphores).length : 0;
  const schedOn = !!heartbeat.scheduler_active;
  const govOwned = heartbeat.factory_runner_owns_schedulers ? 'factory' : 'operator';
  const lastStatus = ingestion.last_run_status || '—';
  const stats = ingestion.last_run_stats || {};

  const tiles = [
    { k: 'ai',  label: 'AI workforce', head: configured ? provider : 'no key',
      sub: configured ? `${llm.providers[provider]?.model || '—'} · ${activeCalls} active` : 'missing API key' },
    { k: 'sys', label: 'System pulse', head: schedOn ? 'live' : 'dormant',
      sub: `${heartbeat.ticks_in_last_hour || 0} ticks/h · ${heartbeat.audit_log_size || 0} audits` },
    { k: 'gov', label: 'Governance',   head: govOwned,
      sub: govOwned === 'operator' ? 'sealed · advisory-only' : 'autonomous' },
    { k: 'ing', label: 'Ingestion',    head: lastStatus.toLowerCase(),
      sub: `${stats.total_injected || 0} inj · ${stats.total_rejected || 0} rej` },
  ];

  return (
    <section className="brief-print__sect" data-testid="print-posture">
      <h2 className="brief-print__h2">2 · Operational Posture</h2>
      <div className="brief-print__posture-grid">
        {tiles.map((t) => (
          <div key={t.k} className="brief-print__tile" data-testid={`print-tile-${t.k}`}>
            <div className="brief-print__tile-label">{t.label}</div>
            <div className="brief-print__tile-head">{t.head}</div>
            <div className="brief-print__tile-sub">{t.sub}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function PrintMission({ data }) {
  const survivors = Array.isArray(data?.survivors?.rows)
    ? data.survivors.rows
    : Array.isArray(data?.survivors) ? data.survivors
    : Array.isArray(data?.survivors?.survivors) ? data.survivors.survivors : [];
  const top = survivors.slice(0, 3);
  const ingestion = data?.ingestion;

  return (
    <section className="brief-print__sect" data-testid="print-mission">
      <h2 className="brief-print__h2">3 · Mission — Current Priorities</h2>
      {top.length === 0 ? (
        <p className="brief-print__body">
          No registered survivor strategies at the time of this briefing.
        </p>
      ) : (
        <table className="brief-print__table" data-testid="print-mission-table">
          <thead>
            <tr>
              <th>#</th><th>Strategy</th><th>Pair</th><th>Timeframe</th><th className="brief-print__num">Score</th>
            </tr>
          </thead>
          <tbody>
            {top.map((s, i) => (
              <tr key={s.strategy_id || s.strategy_hash || i}>
                <td>{String(i + 1).padStart(2, '0')}</td>
                <td className="brief-print__mono">{s.strategy_id || s.strategy_hash || '—'}</td>
                <td>{s.pair || '—'}</td>
                <td>{s.timeframe || '—'}</td>
                <td className="brief-print__num brief-print__mono">{s.score != null ? Number(s.score).toFixed(2) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ingestion && !ingestion.__err && (
        <p className="brief-print__body brief-print__body--note">
          Last ingestion run <span className="brief-print__mono">{ingestion.last_run_id || '—'}</span> at{' '}
          <span className="brief-print__mono">{iso(ingestion.last_run_at)}</span>.
        </p>
      )}
    </section>
  );
}

function PrintAudit({ data }) {
  const rows = Array.isArray(data?.calls?.rows) ? data.calls.rows : [];
  const top = rows.slice(0, 8);

  return (
    <section className="brief-print__sect brief-print__sect--break" data-testid="print-audit">
      <h2 className="brief-print__h2">4 · Audit Tail — Last {top.length} LLM Call{top.length === 1 ? '' : 's'}</h2>
      {top.length === 0 ? (
        <p className="brief-print__body">
          No LLM calls recorded at the time of this briefing.
        </p>
      ) : (
        <table className="brief-print__table brief-print__table--mono" data-testid="print-audit-table">
          <thead>
            <tr>
              <th>Timestamp</th><th>Task</th><th>Provider · Model</th><th>Outcome</th><th className="brief-print__num">ms</th>
            </tr>
          </thead>
          <tbody>
            {top.map((r, i) => {
              const outcome = (r.outcome || r.status || '?').toLowerCase();
              return (
                <tr key={i} data-testid={`print-audit-row-${i}`}>
                  <td>{iso(r.ts).replace('T', ' ').replace('Z', '')}</td>
                  <td>{r.task || '—'}</td>
                  <td>{(r.provider || '—')} · {r.model || '—'}</td>
                  <td className={`brief-print__outcome brief-print__outcome--${outcome}`}>{outcome}</td>
                  <td className="brief-print__num">{r.latency_ms != null ? r.latency_ms : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function PrintFooter({ data }) {
  return (
    <footer className="brief-print__footer" data-testid="print-footer">
      <hr className="brief-print__rule" />
      <div className="brief-print__footer-row">
        <div className="brief-print__signature">
          <div className="brief-print__sig-label">operator signature</div>
          <div className="brief-print__sig-line" />
        </div>
        <div className="brief-print__signature">
          <div className="brief-print__sig-label">reviewed by</div>
          <div className="brief-print__sig-line" />
        </div>
        <div className="brief-print__signature">
          <div className="brief-print__sig-label">date</div>
          <div className="brief-print__sig-line" />
        </div>
      </div>
      <div className="brief-print__provenance">
        Snapshot deep-link: <span className="brief-print__mono">/c/dashboard?print=1</span> ·
        Generated <span className="brief-print__mono">{iso(data?.fetched_at)}</span>
      </div>
    </footer>
  );
}

export default function BriefingPrint() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  // One-shot fetch on mount. No interval, no refresh, no inspector wiring.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await fetchBriefingOnce();
        if (alive) setData(d);
      } catch (e) {
        if (alive) setErr(e.message || String(e));
      }
    })();
    return () => { alive = false; };
  }, []);

  // Body attribute toggle — drives briefing-print.css overrides.
  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const prev = document.body.getAttribute('data-cmd-print');
    document.body.setAttribute('data-cmd-print', '1');
    return () => {
      if (prev === null) document.body.removeAttribute('data-cmd-print');
      else document.body.setAttribute('data-cmd-print', prev);
    };
  }, []);

  // Auto-trigger native print dialog when query param requests it.
  // ?print=1&auto=1  — for institutional one-click PDF export.
  useEffect(() => {
    if (!data) return;
    if (typeof window === 'undefined') return;
    const sp = new URLSearchParams(window.location.search);
    if (sp.get('auto') === '1') {
      const t = setTimeout(() => window.print(), 350);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [data]);

  if (err) {
    return (
      <main className="brief-print" data-testid="briefing-print-error">
        <p className="brief-print__body">Briefing unavailable: {err}</p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="brief-print" data-testid="briefing-print-loading">
        <PrintHeader data={{ fetched_at: new Date().toISOString() }} />
        <p className="brief-print__body">Synthesizing briefing…</p>
      </main>
    );
  }

  const attention = synthesizeAttention(data);

  return (
    <main className="brief-print" data-testid="briefing-print-root">
      <div className="brief-print__sheet">
        <PrintHeader data={data} />
        <PrintAttention items={attention} />
        <PrintPosture data={data} />
        <PrintMission data={data} />
        <PrintAudit data={data} />
        <PrintFooter data={data} />
      </div>

      {/* Screen-only toolbar — never printed (CSS hides under @media print). */}
      <div className="brief-print__toolbar" data-testid="briefing-print-toolbar">
        <button
          type="button"
          onClick={() => window.print()}
          className="brief-print__toolbar-btn"
          data-testid="print-dialog-btn"
        >
          Print / Save PDF
        </button>
        <a
          href="/c/dashboard"
          className="brief-print__toolbar-link"
          data-testid="print-back-link"
        >
          ← back to live briefing
        </a>
      </div>
    </main>
  );
}
