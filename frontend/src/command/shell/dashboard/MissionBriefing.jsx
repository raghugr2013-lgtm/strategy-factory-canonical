/**
 * COMMAND · Phase U.3 — Mission Briefing Dashboard
 * ----------------------------------------------------------------------------
 * "What requires operator attention RIGHT NOW?" — answered in 4 zones:
 *
 *   ZONE 1 · ATTENTION   — synthesized list of issues OR "ALL SYSTEMS NOMINAL"
 *   ZONE 2 · POSTURE     — 4 calm tiles: AI workforce / system / governance / ingestion
 *   ZONE 3 · MISSION     — top 3 survivors (read-only) + recent ingestion summary
 *   ZONE 4 · AUDIT TAIL  — last 8 LLM call-log rows (mono, compact)
 *
 * Deliberately NOT a metrics wall. Each zone has ONE purpose. Long-session
 * ergonomics over visual density.
 */
import React, { useMemo } from 'react';
import { useBriefingData, synthesizeAttention } from './briefingData';
import { usePosture } from '../usePosture';
import { useInspector } from '../inspector/InspectorProvider';
import BriefingPrint from './BriefingPrint';

/* U.5.b — `?print=1` detection. Done at module scope so the redirect happens
   before any data hook is mounted, ensuring zero double-fetch. */
function isPrintRequested() {
  if (typeof window === 'undefined') return false;
  try {
    return new URLSearchParams(window.location.search).get('print') === '1';
  } catch (_) { return false; }
}

function tsCompact(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${hh}:${mm}:${ss}Z`;
  } catch (_) { return iso.slice(11, 19); }
}

function compactFromSecs(secs) {
  if (secs == null) return '—';
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// ────────────────────────────── ZONE 1 ────────────────────────────────
function AttentionStrip({ items, fetchedAt, onInspect }) {
  const ok = items.length === 0;
  return (
    <section
      className={`panel panel--premium${ok ? '' : ' panel--tactical'}`}
      data-testid="briefing-attention"
    >
      <div className="panel__hd">
        <span className="cmd-font-display">· attention · briefing</span>
        <div className="panel__hd-spacer" />
        <span className={`chip chip--${ok ? 'green' : items.some((i) => i.tone === 'red') ? 'red' : 'amber'}`}>
          <span className={`chip__dot ${ok ? 'cmd-dot--live' : ''}`} />
          <span className="chip__label">{ok ? 'nominal' : `${items.length} item${items.length === 1 ? '' : 's'}`}</span>
        </span>
        <span style={{ color: 'var(--cmd-ink-2)', fontFamily: 'JetBrains Mono', fontSize: 10, marginLeft: 10 }}>
          {tsCompact(fetchedAt)}
        </span>
      </div>

      {ok ? (
        <p style={{ margin: 0, fontSize: 14, color: 'var(--cmd-ink-1)', lineHeight: 1.55 }}>
          All monitored subsystems are within tolerance. No operator action required at this time.
        </p>
      ) : (
        <ul
          style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}
          data-testid="briefing-attention-list"
        >
          {items.map((it) => (
            <li
              key={it.key}
              data-testid={`briefing-attention-item-${it.key}`}
              onClick={() => onInspect && onInspect({ type: 'attention', item: it })}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 12,
                padding: '10px 12px',
                background: 'var(--cmd-surface-0)',
                border: '1px solid var(--cmd-hairline)',
                borderRadius: 6,
                cursor: onInspect ? 'pointer' : 'default',
                transition: 'border-color var(--cmd-dur-fast) var(--cmd-ease), background var(--cmd-dur-fast) var(--cmd-ease)',
              }}
              onMouseEnter={(e) => { if (onInspect) e.currentTarget.style.borderColor = 'var(--cmd-hairline-2)'; }}
              onMouseLeave={(e) => { if (onInspect) e.currentTarget.style.borderColor = 'var(--cmd-hairline)'; }}
            >
              <span className={`chip chip--${it.tone}`} style={{ height: 22, flexShrink: 0 }}>
                <span className="chip__dot" />
                <span className="chip__label">{it.tone === 'red' ? 'critical' : 'warn'}</span>
              </span>
              <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
                <span style={{ fontSize: 13, color: 'var(--cmd-ink-0)', fontWeight: 500 }}>
                  {it.label}
                </span>
                {it.hint && (
                  <span
                    style={{
                      fontSize: 11, color: 'var(--cmd-ink-2)',
                      fontFamily: 'JetBrains Mono', letterSpacing: '0.04em',
                    }}
                  >
                    {it.hint}
                  </span>
                )}
              </div>
              {onInspect && (
                <span
                  style={{
                    fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--cmd-cyan)',
                    letterSpacing: '0.08em', alignSelf: 'center',
                  }}
                >
                  inspect →
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ────────────────────────────── ZONE 2 ────────────────────────────────
function PostureTile({ label, head, sub, tone = 'cyan', testid }) {
  return (
    <div
      className="panel panel--premium panel--briefing-tile"
      data-testid={testid}
      style={{ padding: '14px 16px', minHeight: 96 }}
    >
      <span
        style={{
          fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--cmd-ink-2)',
          letterSpacing: '0.14em', textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
      <div style={{ marginTop: 6, display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span
          style={{
            fontFamily: 'JetBrains Mono', fontSize: 22,
            color: `var(--cmd-${tone})`,
            letterSpacing: '-0.01em', fontWeight: 500,
          }}
        >
          {head}
        </span>
      </div>
      <span
        style={{
          marginTop: 6, display: 'block',
          fontSize: 11, color: 'var(--cmd-ink-1)',
          fontFamily: 'JetBrains Mono', letterSpacing: '0.04em',
        }}
      >
        {sub}
      </span>
    </div>
  );
}

function PostureTiles({ data }) {
  const { llm, runner, heartbeat, ingestion } = data;

  // AI Workforce
  const provider = llm?.primary_provider || '—';
  const configured = !!(llm?.providers && llm.providers[provider]?.configured);
  const activeCalls = runner?.active_semaphores ? Object.keys(runner.active_semaphores).length : 0;
  const aiHead = configured ? provider : 'no key';
  const aiSub = configured
    ? `${llm.providers[provider].model || '—'} · ${activeCalls} active`
    : 'configure provider key in .env';
  const aiTone = configured ? 'cyan' : 'red';

  // System
  const schedOn = !!heartbeat?.scheduler_active;
  const sysHead = schedOn ? 'live' : 'dormant';
  const sysSub = heartbeat
    ? `${heartbeat.ticks_in_last_hour || 0} ticks/h · ${heartbeat.audit_log_size || 0} audits`
    : '—';
  const sysTone = schedOn ? 'green' : 'cyan';

  // Governance (using ecosystem-maturity-style signal from heartbeat flag + readiness)
  const govOwned = heartbeat?.factory_runner_owns_schedulers ? 'factory' : 'operator';
  const govHead = govOwned;
  const govSub = govOwned === 'operator' ? 'sealed · advisory-only' : 'autonomous';
  const govTone = govOwned === 'operator' ? 'cyan' : 'amber';

  // Ingestion
  const lastStatus = ingestion?.last_run_status || '—';
  const stats = ingestion?.last_run_stats || {};
  const injected = stats.total_injected || 0;
  const rejected = stats.total_rejected || 0;
  const ingHead = lastStatus.toLowerCase();
  const ingSub = `${injected} inj · ${rejected} rej`;
  const ingTone = lastStatus === 'ok' ? (injected > 0 ? 'green' : 'amber') : 'amber';

  return (
    <section
      data-testid="briefing-posture"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 12,
      }}
    >
      <PostureTile testid="briefing-tile-ai"         label="ai workforce"   head={aiHead}  sub={aiSub}  tone={aiTone} />
      <PostureTile testid="briefing-tile-system"     label="system pulse"   head={sysHead} sub={sysSub} tone={sysTone} />
      <PostureTile testid="briefing-tile-governance" label="governance"     head={govHead} sub={govSub} tone={govTone} />
      <PostureTile testid="briefing-tile-ingestion"  label="ingestion"      head={ingHead} sub={ingSub} tone={ingTone} />
    </section>
  );
}

// ────────────────────────────── ZONE 3 ────────────────────────────────
function MissionStrip({ data, onInspect }) {
  const survivors = Array.isArray(data?.survivors?.rows)
    ? data.survivors.rows
    : Array.isArray(data?.survivors)
      ? data.survivors
      : Array.isArray(data?.survivors?.survivors)
        ? data.survivors.survivors
        : [];
  const top = survivors.slice(0, 3);

  const ingestion = data?.ingestion;
  const stats = ingestion?.last_run_stats || {};
  const sources = stats.by_source || {};
  const sourceList = Object.entries(sources).slice(0, 3);

  return (
    <section className="panel panel--premium" data-testid="briefing-mission">
      <div className="panel__hd">
        <span className="cmd-font-display">· mission · current priorities</span>
        <div className="panel__hd-spacer" />
        <span className="chip">
          <span className="chip__label">{top.length} survivor{top.length === 1 ? '' : 's'}</span>
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16 }}>
        {/* Survivors */}
        <div>
          <div
            style={{
              fontSize: 10, color: 'var(--cmd-ink-2)',
              fontFamily: 'JetBrains Mono', letterSpacing: '0.14em',
              textTransform: 'uppercase', marginBottom: 8,
            }}
          >
            top survivors
          </div>
          {top.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--cmd-ink-2)', padding: '12px 0' }}>
              No survivors registered yet. Generate strategies in&nbsp;
              <a href="/c/lab" style={{ color: 'var(--cmd-cyan)' }}>/c/lab</a>
              &nbsp;or run a mutation cycle from&nbsp;
              <a href="/c/mutate" style={{ color: 'var(--cmd-cyan)' }}>/c/mutate</a>.
            </div>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {top.map((s, i) => (
                <li
                  key={s.strategy_hash || s.strategy_id || i}
                  data-testid={`briefing-survivor-${i}`}
                  onClick={() => {
                    const sid = s.strategy_id || s.strategy_hash;
                    if (sid && onInspect) onInspect({ type: 'strategy', strategyId: sid });
                  }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 10px',
                    background: 'var(--cmd-surface-0)',
                    border: '1px solid var(--cmd-hairline)',
                    borderRadius: 5,
                    fontFamily: 'JetBrains Mono', fontSize: 11,
                    letterSpacing: '0.02em', color: 'var(--cmd-ink-1)',
                    cursor: onInspect ? 'pointer' : 'default',
                  }}
                >
                  <span style={{ color: 'var(--cmd-cyan)', minWidth: 18 }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span>{s.strategy_id || s.strategy_hash || 'STR-—'}</span>
                  <span style={{ flex: 1 }} />
                  {s.pair && (<span style={{ color: 'var(--cmd-ink-2)' }}>{s.pair}</span>)}
                  {s.timeframe && (<span style={{ color: 'var(--cmd-ink-2)' }}>· {s.timeframe}</span>)}
                  {(s.score != null) && (
                    <span className="chip chip--cyan" style={{ height: 20 }}>
                      <span className="chip__label">{Number(s.score).toFixed(1)}</span>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Ingestion sources */}
        <div>
          <div
            style={{
              fontSize: 10, color: 'var(--cmd-ink-2)',
              fontFamily: 'JetBrains Mono', letterSpacing: '0.14em',
              textTransform: 'uppercase', marginBottom: 8,
            }}
          >
            ingestion · last run
          </div>
          {!ingestion ? (
            <div style={{ fontSize: 12, color: 'var(--cmd-ink-2)' }}>—</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 11, color: 'var(--cmd-ink-2)', fontFamily: 'JetBrains Mono' }}>
                run · <span style={{ color: 'var(--cmd-ink-0)' }}>{ingestion.last_run_id || '—'}</span>
              </span>
              <span style={{ fontSize: 11, color: 'var(--cmd-ink-2)', fontFamily: 'JetBrains Mono' }}>
                at · <span style={{ color: 'var(--cmd-ink-0)' }}>{tsCompact(ingestion.last_run_at)}</span>
              </span>
              {sourceList.length > 0 && (
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {sourceList.map(([src, val]) => (
                    <span
                      key={src}
                      style={{
                        fontSize: 11, color: 'var(--cmd-ink-1)',
                        fontFamily: 'JetBrains Mono',
                      }}
                    >
                      <span style={{ color: 'var(--cmd-ink-2)' }}>{src.padEnd(10)}</span>
                      &nbsp;{(val && val.fetched) || 0} fetched
                      {val && val.injected ? ` · ${val.injected} inj` : ''}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

// ────────────────────────────── ZONE 4 ────────────────────────────────
function AuditTail({ data, onInspect }) {
  const rows = Array.isArray(data?.calls?.rows) ? data.calls.rows : [];
  const top = rows.slice(0, 8);

  return (
    <section className="panel panel--premium" data-testid="briefing-audit">
      <div className="panel__hd">
        <span className="cmd-font-display">· audit · last {top.length} llm call{top.length === 1 ? '' : 's'}</span>
        <div className="panel__hd-spacer" />
        <a
          href="/c/ai"
          style={{ color: 'var(--cmd-cyan)', textDecoration: 'none', fontSize: 10,
                   fontFamily: 'JetBrains Mono', letterSpacing: '0.06em' }}
        >
          open ai workforce →
        </a>
      </div>

      {top.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--cmd-ink-2)' }}>
          No LLM calls recorded yet. The runner will populate this list when ingestion or mutation invokes a provider.
        </div>
      ) : (
        <table
          style={{
            width: '100%', borderCollapse: 'collapse',
            fontFamily: 'JetBrains Mono', fontSize: 11,
            color: 'var(--cmd-ink-1)',
          }}
          data-testid="briefing-audit-table"
        >
          <thead>
            <tr style={{ color: 'var(--cmd-ink-2)', textAlign: 'left' }}>
              <th style={{ padding: '6px 8px', borderBottom: '1px solid var(--cmd-hairline)', fontWeight: 500 }}>ts</th>
              <th style={{ padding: '6px 8px', borderBottom: '1px solid var(--cmd-hairline)', fontWeight: 500 }}>task</th>
              <th style={{ padding: '6px 8px', borderBottom: '1px solid var(--cmd-hairline)', fontWeight: 500 }}>provider · model</th>
              <th style={{ padding: '6px 8px', borderBottom: '1px solid var(--cmd-hairline)', fontWeight: 500 }}>outcome</th>
              <th style={{ padding: '6px 8px', borderBottom: '1px solid var(--cmd-hairline)', fontWeight: 500, textAlign: 'right' }}>ms</th>
            </tr>
          </thead>
          <tbody>
            {top.map((r, i) => {
              const outcome = (r.outcome || r.status || '?').toLowerCase();
              const tone = outcome === 'success' || outcome === 'ok' ? 'green'
                : outcome === 'fail' || outcome === 'error' ? 'red'
                : 'amber';
              return (
                <tr
                  key={i}
                  data-testid={`briefing-audit-row-${i}`}
                  onClick={() => onInspect && onInspect({ type: 'llm-call', call: r })}
                  style={{ cursor: onInspect ? 'pointer' : 'default' }}
                >
                  <td style={{ padding: '6px 8px', color: 'var(--cmd-ink-2)' }}>{tsCompact(r.ts)}</td>
                  <td style={{ padding: '6px 8px' }}>{r.task || '—'}</td>
                  <td style={{ padding: '6px 8px' }}>
                    {(r.provider || '—')}
                    <span style={{ color: 'var(--cmd-ink-2)' }}>
                      &nbsp;· {r.model || '—'}
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px' }}>
                    <span className={`chip chip--${tone}`} style={{ height: 18, fontSize: 9 }}>
                      <span className="chip__dot" />
                      <span className="chip__label">{outcome}</span>
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', color: 'var(--cmd-ink-0)' }}>
                    {r.latency_ms != null ? r.latency_ms : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ──────────────────────── ROOT ────────────────────────────────────────
/**
 * U.5.b — Top-level branch.
 * `?print=1` → BriefingPrint (paper-light, one-shot fetch, no polling).
 * default    → MissionBriefingLive (interactive briefing with polling).
 * Branching at this layer keeps both sub-components hook-order-stable.
 */
export default function MissionBriefing() {
  if (isPrintRequested()) {
    return <BriefingPrint />;
  }
  return <MissionBriefingLive />;
}

function MissionBriefingLive() {
  const posture = usePosture();
  const { data, loading, refresh } = useBriefingData(posture);
  const inspector = useInspector();

  const attention = useMemo(() => synthesizeAttention(data), [data]);
  const onInspect = (sel) => inspector.inspect(sel);

  if (loading) {
    return (
      <div data-testid="briefing-loading" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <section className="panel">
          <div className="panel__hd">· briefing · synthesizing</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <span className="cmd-skel-line" style={{ width: '42%' }} />
            <span className="cmd-skel-line" style={{ width: '78%' }} />
            <span className="cmd-skel-line" style={{ width: '60%' }} />
          </div>
        </section>
      </div>
    );
  }

  return (
    <div data-testid="briefing-root" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AttentionStrip items={attention} fetchedAt={data.fetched_at} onInspect={onInspect} />
      <PostureTiles data={data} />
      <MissionStrip data={data} onInspect={onInspect} />
      <AuditTail data={data} onInspect={onInspect} />

      {/* Footer hint — calm, never advertised twice */}
      <div
        style={{
          fontSize: 10, color: 'var(--cmd-ink-2)',
          fontFamily: 'JetBrains Mono', letterSpacing: '0.04em',
          textAlign: 'center', padding: '2px 0 8px',
          display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 14, flexWrap: 'wrap',
        }}
      >
        <span>
          briefing auto-refreshes every {Math.round((posture === 'workstation' ? 8000 : posture === 'tablet' ? 14000 : 30000) / 1000)}s
        </span>
        <span style={{ opacity: 0.45 }}>·</span>
        <button
          type="button"
          onClick={refresh}
          style={{ background: 'none', border: 'none', color: 'var(--cmd-cyan)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 10, padding: 0 }}
          data-testid="briefing-refresh"
        >
          refresh now
        </button>
        <span style={{ opacity: 0.45 }}>·</span>
        {/* U.5.b — Print mode export. Appends ?print=1 (canonical deep-link). */}
        <a
          href="/c/dashboard?print=1"
          style={{ color: 'var(--cmd-cyan)', textDecoration: 'none', fontFamily: 'inherit', fontSize: 10 }}
          data-testid="briefing-export"
          title="Open paper-light executive briefing (?print=1)"
        >
          export briefing →
        </a>
      </div>
    </div>
  );
}
