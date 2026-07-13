/**
 * COMMAND · Phase U.4 — Inspector views
 * ----------------------------------------------------------------------------
 * Three narrative views, one per selection type. Discipline:
 *   • Each view answers ONE question (why does this exist? why did it fail?
 *     what's its lineage?).
 *   • Mono details follow narrative prose, never replace it.
 *   • No charts, no metrics walls — interpretability over complexity.
 *
 *   StrategyInspector   ·  "why does this strategy exist?"
 *   LlmCallInspector    ·  "why did this AI call fail / succeed?"
 *   AttentionInspector  ·  "why is this issue surfaced + where to fix it?"
 */
import React, { useEffect, useState } from 'react';
import { API_URL as BACKEND } from '../../../services/api';


function authHeaders() {
  try {
    const t = localStorage.getItem('asf_auth_token');
    return t ? { Authorization: `Bearer ${t}` } : {};
  } catch (_) { return {}; }
}

function tsCompact(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}:${String(d.getUTCSeconds()).padStart(2,'0')}Z · ${d.toISOString().slice(0,10)}`;
  } catch (_) { return iso; }
}

/* ────────────── tiny shared layout helpers ────────────── */
function Section({ label, children, tone }) {
  return (
    <div data-testid={`insp-section-${label.replace(/\s+/g, '-').toLowerCase()}`} style={{ marginBottom: 18 }}>
      <div
        style={{
          fontFamily: 'JetBrains Mono', fontSize: 10,
          color: tone ? `var(--cmd-${tone})` : 'var(--cmd-ink-2)',
          letterSpacing: '0.14em', textTransform: 'uppercase',
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function KV({ rows }) {
  return (
    <dl style={{
      margin: 0, fontFamily: 'JetBrains Mono', fontSize: 11,
      display: 'grid', gridTemplateColumns: '92px 1fr', rowGap: 6, columnGap: 12,
    }}>
      {rows.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt style={{ color: 'var(--cmd-ink-2)' }}>{k}</dt>
          <dd style={{ margin: 0, color: 'var(--cmd-ink-0)', overflow: 'hidden', textOverflow: 'ellipsis', wordBreak: 'break-all' }}>
            {v ?? '—'}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

/* ──────────────────────────────────────────────────────────────────────
   ATTENTION INSPECTOR
   ────────────────────────────────────────────────────────────────────── */
const ATTENTION_TARGETS = {
  'backend':          { path: null,        title: 'Backend reachability', what: 'The frontend cannot reach /api/health. This is a network or process-health issue.' },
  'llm-key':          { path: '/c/ai',     title: 'AI provider key missing', what: 'The primary provider does not have a configured API key. The orchestrator cannot make LLM calls.' },
  'llm-unknown':      { path: '/c/diag',   title: 'Unknown provider in routing', what: 'A LLM_TASK_* environment variable points to a provider not registered in the catalogue. The router will silently fall through.' },
  'readiness':        { path: '/c/diag',   title: 'Deployment readiness', what: 'One or more readiness checks regressed. Open the readiness panel for the failing check list.' },
  'ingestion':        { path: '/c/diag',   title: 'Ingestion last-run', what: 'The most recent ingestion run did not complete with status=ok.' },
  'ingestion-reject': { path: '/c/diag',   title: 'Ingestion 100% reject', what: 'Every candidate from the last ingestion run was rejected. Likely a schema drift or provider-side outage.' },
  'duplicate-ticks':  { path: '/c/ai',     title: 'Duplicate orchestrator ticks', what: 'The orchestrator heartbeat is recording duplicate ticks. May indicate two scheduler processes or a clock-skew issue.' },
  'stuck-llm':        { path: '/c/ai',     title: 'Long-running LLM call', what: 'A semaphore has been held >120s. Either the upstream provider is slow or the request is genuinely stuck.' },
};

export function AttentionInspector({ item, fetchedAt, onNavigate }) {
  const target = ATTENTION_TARGETS[item.key] || { path: null, title: item.label, what: '' };
  const auditRef = `[ATTN ${item.key} ${(fetchedAt || new Date().toISOString())}] ${item.label}${item.hint ? ` · ctx=${item.hint}` : ''}`;
  const [copied, setCopied] = useState(false);

  const copyRef = async () => {
    try { await navigator.clipboard.writeText(auditRef); setCopied(true); setTimeout(() => setCopied(false), 1800); }
    catch (_) { window.prompt('Audit reference:', auditRef); }
  };

  return (
    <div data-testid="inspector-view-attention">
      <Section label={`attention · ${item.tone}`} tone={item.tone}>
        <div style={{
          fontSize: 14, color: 'var(--cmd-ink-0)', fontWeight: 500, lineHeight: 1.45, marginBottom: 6,
        }}>{item.label}</div>
        {item.hint && (
          <div style={{
            fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-ink-2)',
            wordBreak: 'break-all',
          }}>
            {item.hint}
          </div>
        )}
      </Section>

      <Section label="why this is surfaced">
        <p style={{ margin: 0, fontSize: 12, color: 'var(--cmd-ink-1)', lineHeight: 1.55 }}>
          {target.what || 'This subsystem reported a non-nominal state. See the source module for details.'}
        </p>
      </Section>

      <Section label="audit reference">
        <div style={{
          padding: 10, borderRadius: 5,
          background: 'var(--cmd-surface-0)', border: '1px solid var(--cmd-hairline)',
          fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--cmd-ink-1)',
          lineHeight: 1.55, wordBreak: 'break-all', marginBottom: 8,
        }}>
          {auditRef}
        </div>
        <button
          type="button"
          className={copied ? 'cmd-btn cmd-btn--cyan' : 'cmd-btn'}
          onClick={copyRef}
          data-testid="inspector-attention-copy"
        >
          {copied ? 'copied' : 'copy audit reference'}
        </button>
      </Section>

      {target.path && (
        <Section label="where to fix">
          <button
            type="button"
            className="cmd-btn cmd-btn--cyan"
            onClick={() => onNavigate && onNavigate(target.path)}
            data-testid="inspector-attention-jump"
          >
            open {target.path} →
          </button>
        </Section>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────
   LLM CALL INSPECTOR
   ────────────────────────────────────────────────────────────────────── */
export function LlmCallInspector({ call }) {
  const outcome = (call.outcome || call.status || '?').toLowerCase();
  const tone = outcome === 'success' || outcome === 'ok' ? 'green'
    : outcome === 'fail' || outcome === 'error' || outcome === 'exception' ? 'red'
    : 'amber';

  // Narrative reasoning — synthesise based on outcome
  let narrative = null;
  if (outcome === 'exception' || outcome === 'fail' || outcome === 'error') {
    narrative = call.error
      ? 'The provider rejected this call. The error string below contains the upstream provider response — typically actionable.'
      : 'The call did not complete and no error string was captured.';
  } else if (outcome === 'success' || outcome === 'ok') {
    narrative = 'Call completed successfully. Token counts and latency are recorded for cost / SLA analysis.';
  } else {
    narrative = 'Outcome is non-standard; check the LLM runner state for context.';
  }

  return (
    <div data-testid="inspector-view-llm-call">
      <Section label={`llm call · ${outcome}`} tone={tone}>
        <div style={{ fontSize: 14, color: 'var(--cmd-ink-0)', fontWeight: 500, marginBottom: 4 }}>
          {call.task || 'unknown task'}
        </div>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-ink-2)' }}>
          {(call.provider || '—')} · {call.model || '—'}
        </div>
      </Section>

      <Section label="why this matters">
        <p style={{ margin: 0, fontSize: 12, color: 'var(--cmd-ink-1)', lineHeight: 1.55 }}>
          {narrative}
        </p>
      </Section>

      <Section label="telemetry">
        <KV rows={[
          ['ts',         tsCompact(call.ts)],
          ['task',       call.task || '—'],
          ['provider',   call.provider || '—'],
          ['model',      call.model || '—'],
          ['outcome',    outcome],
          ['latency.ms', call.latency_ms != null ? String(call.latency_ms) : '—'],
          ['tokens.in',  call.tokens_in != null ? String(call.tokens_in) : '—'],
          ['tokens.out', call.tokens_out != null ? String(call.tokens_out) : '—'],
        ]}/>
      </Section>

      {call.error && (
        <Section label="upstream error">
          <pre style={{
            margin: 0, padding: 10, borderRadius: 5,
            background: 'var(--cmd-surface-0)', border: '1px solid var(--cmd-hairline)',
            color: 'var(--cmd-red)', fontFamily: 'JetBrains Mono', fontSize: 11,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 240, overflow: 'auto',
          }}>
            {call.error}
          </pre>
        </Section>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────
   STRATEGY INSPECTOR
   ────────────────────────────────────────────────────────────────────── */
function fetchLineage(strategyId) {
  return fetch(`${BACKEND}/api/strategies/${encodeURIComponent(strategyId)}/lineage`, {
    headers: authHeaders(),
  }).then(async (r) => {
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      const err = new Error('lineage_fetch_failed');
      err.status = r.status;
      err.detail = body.detail;
      throw err;
    }
    return r.json();
  });
}

export function StrategyInspector({ strategyId }) {
  const [state, setState] = useState({ loading: true, data: null, err: null });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, err: null });
    fetchLineage(strategyId).then(
      (data) => { if (!cancelled) setState({ loading: false, data, err: null }); },
      (err)  => { if (!cancelled) setState({ loading: false, data: null, err }); },
    );
    return () => { cancelled = true; };
  }, [strategyId]);

  if (state.loading) {
    return (
      <div data-testid="inspector-view-strategy-loading">
        <Section label={`strategy · ${strategyId}`}>
          <span className="cmd-skel-line" style={{ display: 'block', width: '60%', marginBottom: 6 }} />
          <span className="cmd-skel-line" style={{ display: 'block', width: '40%' }} />
        </Section>
      </div>
    );
  }

  if (state.err) {
    const detail = state.err.detail || {};
    return (
      <div data-testid="inspector-view-strategy-empty">
        <Section label={`strategy · ${strategyId}`} tone="amber">
          <div style={{ fontSize: 13, color: 'var(--cmd-ink-0)', marginBottom: 8 }}>
            No lineage recorded.
          </div>
          <div style={{ fontSize: 12, color: 'var(--cmd-ink-2)', lineHeight: 1.5 }}>
            {detail.hint || 'The strategy is not present in `strategies` or `research_runs`.'}
          </div>
        </Section>
        <Section label="next">
          <a href="/c/lab" className="cmd-btn cmd-btn--cyan" style={{ textDecoration: 'none' }}>
            open /c/lab →
          </a>
        </Section>
      </div>
    );
  }

  const d = state.data;
  const head = d.head || {};
  const aiCount = (d.nodes || []).filter((n) => n.ai).length;

  return (
    <div data-testid="inspector-view-strategy">
      <Section label={`strategy · ${d.strategy_id}`} tone="cyan">
        <div style={{ fontSize: 14, color: 'var(--cmd-ink-0)', fontWeight: 500, marginBottom: 4 }}>
          {head.pair || 'unknown pair'}
          {head.timeframe && <span style={{ color: 'var(--cmd-ink-2)' }}> · {head.timeframe}</span>}
        </div>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-ink-2)' }}>
          depth {d.depth} · {aiCount} AI-derived
        </div>
      </Section>

      <Section label="why it exists">
        <p style={{ margin: 0, fontSize: 12, color: 'var(--cmd-ink-1)', lineHeight: 1.55 }}>
          {d.nodes && d.nodes.length > 0
            ? `This strategy is the head of a ${d.depth}-step research lineage. ${aiCount} step${aiCount === 1 ? '' : 's'} were AI-derived; the rest are operator or orchestrator actions.`
            : 'This strategy has no recorded research lineage. It may have been created outside the orchestrator.'}
        </p>
      </Section>

      <Section label="head telemetry">
        <KV rows={[
          ['strategy.id',     head.strategy_id || d.strategy_id],
          ['strategy.hash',   head.strategy_hash || '—'],
          ['pair',            head.pair || '—'],
          ['timeframe',       head.timeframe || '—'],
          ['score',           head.score != null ? String(head.score) : '—'],
          ['confidence',      head.confidence != null ? String(head.confidence) : '—'],
        ]}/>
      </Section>

      <Section label={`lineage · ${d.nodes.length} node${d.nodes.length === 1 ? '' : 's'}`}>
        {d.nodes.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--cmd-ink-2)' }}>
            No research-run nodes recorded.
          </div>
        ) : (
          <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {d.nodes.map((n, i) => {
              const active = i === d.active_index;
              return (
                <li
                  key={n.id + i}
                  data-testid={`inspector-strategy-node-${i}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 10px',
                    background: 'var(--cmd-surface-0)',
                    border: `1px solid ${active ? 'rgba(0,212,255,.45)' : 'var(--cmd-hairline)'}`,
                    borderRadius: 5,
                    boxShadow: active ? 'var(--cmd-glow-cyan)' : 'none',
                  }}
                >
                  <span style={{
                    width: 18, textAlign: 'right',
                    fontFamily: 'JetBrains Mono', fontSize: 10,
                    color: 'var(--cmd-ink-2)',
                  }}>{String(i + 1).padStart(2, '0')}</span>
                  <span
                    className={n.ai ? 'lineage__node lineage__node--ai' : active ? 'lineage__node lineage__node--active' : 'lineage__node'}
                    style={{ display: 'inline-block' }}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-ink-0)' }}>
                      {n.id}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--cmd-ink-2)' }}>
                      {n.actor || '—'} · {tsCompact(n.ts)}
                    </div>
                  </div>
                  {n.outcome && (
                    <span className={`chip chip--${n.outcome === 'success' || n.outcome === 'ok' ? 'green' : n.outcome === 'fail' ? 'red' : 'cyan'}`} style={{ height: 18, fontSize: 9 }}>
                      <span className="chip__dot" />
                      <span className="chip__label">{n.outcome}</span>
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </Section>
    </div>
  );
}
