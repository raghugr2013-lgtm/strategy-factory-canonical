/**
 * Factory Supervisor FS-P1.3 — Architect Dashboard (read-only, advisory-only).
 *
 * Sole purpose: surface the JSON read-model from
 *   GET /api/factory-supervisor/architect/dashboard
 * to operators. Zero execution authority. Zero state mutation here.
 *
 * Sections (per operator FS-P1.3 directive):
 *   • Next Recommended Action  (top + full list)
 *   • Fleet health
 *   • Queue pressure
 *   • Submissions
 *   • Defer queue
 *   • Notifications (with unread count, severity / category filters,
 *                    history, acknowledge)
 *   • Scaling events
 *   • Admission statistics
 *   • Worker status
 *   • Routing statistics
 *   • Deployment readiness
 *
 * Banner clearly indicates `advisory_only=true` when consumption gate
 * (FS_ENABLE_ARCHITECT_DASHBOARD) is OFF — Copilot / FAG / Auto-Learning
 * MUST honour that flag before consuming this data.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';

const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8000`
  : (process.env.REACT_APP_BACKEND_URL || '');

function authHeaders() {
  const token = (typeof window !== 'undefined'
    && localStorage.getItem('auth_token')) || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function getJson(path) {
  const r = await fetch(`${API_URL}${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

async function postJson(path, body) {
  const r = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

// ─── Visual primitives (kept inline so the component is self-contained) ──

const SEV_COLOR = {
  info:       'text-zinc-300 bg-zinc-800/60 border-zinc-700',
  suggestion: 'text-blue-300 bg-blue-500/10 border-blue-500/30',
  warn:       'text-amber-300 bg-amber-500/10 border-amber-500/30',
  critical:   'text-red-300 bg-red-500/10 border-red-500/30',
  fatal:      'text-red-200 bg-red-600/20 border-red-500/50',
  debug:      'text-zinc-500 bg-zinc-900 border-zinc-800',
};
const HEALTH_COLOR = {
  ok:       'text-emerald-300 bg-emerald-500/10 border-emerald-500/30',
  warn:     'text-amber-300 bg-amber-500/10 border-amber-500/30',
  critical: 'text-red-300 bg-red-500/10 border-red-500/30',
  unknown:  'text-zinc-400 bg-zinc-800/40 border-zinc-700',
};

function SeverityChip({ severity }) {
  const cls = SEV_COLOR[severity] || SEV_COLOR.info;
  return (
    <span
      data-testid={`sev-chip-${severity}`}
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase tracking-wider ${cls}`}
    >
      {severity || 'info'}
    </span>
  );
}

function HealthChip({ health }) {
  const cls = HEALTH_COLOR[health] || HEALTH_COLOR.unknown;
  return (
    <span
      data-testid="architect-system-health"
      className={`inline-flex items-center px-2.5 py-1 rounded-md border text-xs font-mono ${cls}`}
    >
      system_health · {health || 'unknown'}
    </span>
  );
}

function Card({ title, testid, action, children }) {
  return (
    <section
      data-testid={testid}
      className="bg-surface-card border border-zinc-800 rounded-md p-4 mb-4"
    >
      <header className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100 tracking-tight">
          {title}
        </h3>
        {action}
      </header>
      <div className="text-xs text-zinc-300 font-mono">{children}</div>
    </section>
  );
}

function KV({ label, value, testid }) {
  return (
    <div className="flex items-baseline gap-2 py-0.5">
      <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 min-w-[120px]">
        {label}
      </span>
      <span data-testid={testid} className="text-xs text-zinc-100 font-mono break-all">
        {value === null || value === undefined || value === '' ? '—' : String(value)}
      </span>
    </div>
  );
}

// ─── Sections ────────────────────────────────────────────────────────────

function NextRecommendedActionCard({ payload, onRefresh, loading }) {
  const top = payload?.recommended_action;
  const recs = payload?.recommendations || [];
  return (
    <Card
      testid="architect-recommended-action-card"
      title="Next Recommended Action"
      action={
        <button
          data-testid="architect-refresh-btn"
          onClick={onRefresh}
          className="text-[10px] font-mono text-accent-primary hover:text-accent-primary/80 disabled:opacity-50"
          disabled={loading}
        >
          {loading ? 'refreshing…' : 'refresh'}
        </button>
      }
    >
      {top && (
        <div className="mb-3 p-3 rounded border border-zinc-700 bg-surface-elevated">
          <div className="flex items-center gap-2 mb-1">
            <SeverityChip severity={top.severity} />
            <span data-testid="architect-rec-code" className="text-[10px] font-mono text-zinc-500">
              {top.code}
            </span>
          </div>
          <div data-testid="architect-rec-title" className="text-sm text-zinc-100 font-semibold mb-1">
            {top.title}
          </div>
          <div className="text-xs text-zinc-400 mb-2">
            {top.detail}
          </div>
          {top.suggested_fix ? (
            <div className="text-[11px] text-accent-primary/90 font-mono">
              → {top.suggested_fix}
            </div>
          ) : null}
        </div>
      )}
      {recs.length > 1 && (
        <details className="mt-2">
          <summary className="text-[10px] uppercase tracking-wider text-zinc-500 cursor-pointer hover:text-zinc-300">
            All recommendations ({recs.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {recs.map((r) => (
              <li
                key={r.code}
                data-testid={`architect-rec-row-${r.code}`}
                className="flex items-start gap-2 text-[11px] text-zinc-300 border-l-2 border-zinc-800 pl-2"
              >
                <SeverityChip severity={r.severity} />
                <div>
                  <div className="text-zinc-100">{r.title}</div>
                  {r.suggested_fix && (
                    <div className="text-[10px] text-zinc-500">→ {r.suggested_fix}</div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function FleetHealthCard({ fleet }) {
  const hosts = fleet?.hosts || [];
  return (
    <Card testid="architect-fleet-health-card" title="Fleet Health">
      <KV testid="fleet-band" label="fleet_band" value={fleet?.fleet_band} />
      <KV label="local_host" value={fleet?.local_host_id} />
      <KV label="hosts" value={hosts.length} />
      {hosts.length > 0 && (
        <div className="mt-2 border-t border-zinc-800 pt-2 space-y-1 max-h-56 overflow-auto">
          {hosts.slice(0, 20).map((h, idx) => (
            <div
              key={h.host_id || `host-${idx}`}
              data-testid="architect-fleet-host-row"
              className="flex items-center justify-between text-[11px]"
            >
              <span className="text-zinc-300 truncate">{h.host_id}</span>
              <span className="text-zinc-500">
                {h.heartbeat_age_sec != null ? `${Math.round(h.heartbeat_age_sec)}s ago` : '—'}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function QueuePressureCard({ qp, submissions }) {
  const perClass = qp?.per_class || {};
  const subStats = submissions?.stats || {};
  return (
    <Card testid="architect-queue-pressure-card" title="Queue Pressure & Submissions">
      <KV label="local_band" value={qp?.band} />
      <KV label="overall_depth" value={qp?.overall_depth} />
      <KV testid="submissions-total" label="submissions_total" value={subStats.total} />
      {Object.keys(perClass).length > 0 && (
        <div className="mt-2 border-t border-zinc-800 pt-2 space-y-0.5">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">per_class</div>
          {Object.entries(perClass).map(([k, v]) => (
            <div key={k} className="flex justify-between text-[11px]">
              <span className="text-zinc-400">{k}</span>
              <span className="text-zinc-100">{JSON.stringify(v)}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function DeferQueueCard({ dq, blocked }) {
  const perStatus = dq?.stats?.per_status || {};
  return (
    <Card testid="architect-defer-queue-card" title="Defer Queue">
      <KV label="enabled" value={String(dq?.enabled)} />
      <KV testid="defer-pending" label="pending"  value={blocked?.defer_queue_pending} />
      <KV testid="defer-failed"  label="failed"   value={blocked?.defer_queue_failed} />
      <KV testid="defer-expired" label="expired"  value={blocked?.defer_queue_expired} />
      <div className="mt-2 border-t border-zinc-800 pt-2 grid grid-cols-2 gap-1">
        {Object.entries(perStatus).map(([k, v]) => (
          <div key={k} className="flex justify-between text-[11px]">
            <span className="text-zinc-400">{k}</span>
            <span className="text-zinc-100">{v}</span>
          </div>
        ))}
      </div>
      {(dq?.rows_preview || []).length > 0 && (
        <details className="mt-2">
          <summary className="text-[10px] uppercase tracking-wider text-zinc-500 cursor-pointer hover:text-zinc-300">
            Pending rows preview ({dq.rows_preview.length})
          </summary>
          <ul className="mt-1 space-y-1 max-h-40 overflow-auto">
            {dq.rows_preview.map((r) => (
              <li
                key={r.row_id}
                className="text-[11px] text-zinc-400 border-l-2 border-zinc-800 pl-2"
              >
                <span className="text-zinc-200">{r.workload_class}</span>
                {' · '}{r.status}
                {' · retries='}{r.retry_count}
                {' · reason='}<span className="text-amber-300">{r.last_block_reason || r.defer_reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function NotificationsCard({ section, onAck, onRefresh }) {
  const [severity, setSeverity] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus]     = useState('');
  const [rows, setRows]         = useState([]);
  const [unread, setUnread]     = useState(0);
  const [busy, setBusy]         = useState(false);

  const reload = useCallback(async () => {
    try {
      const qs = new URLSearchParams();
      if (severity) qs.set('severity', severity);
      if (category) qs.set('category', category);
      if (status)   qs.set('status', status);
      qs.set('limit', '50');
      setBusy(true);
      const [listRes, unreadRes] = await Promise.all([
        getJson(`/api/factory-supervisor/notifications?${qs.toString()}`),
        getJson('/api/factory-supervisor/notifications/unread-count'),
      ]);
      setRows(listRes.rows || []);
      setUnread(unreadRes.unread_count || 0);
    } catch (e) {
      console.error('[architect] notifications load failed', e);
    } finally {
      setBusy(false);
    }
  }, [severity, category, status]);

  useEffect(() => {
    let active = true;
    (async () => { if (active) await reload(); })();
    return () => { active = false; };
  }, [reload]);

  const ackRow = async (id) => {
    try {
      await postJson('/api/factory-supervisor/notifications/acknowledge',
                     { notification_ids: [id] });
      await reload();
      if (onAck) onAck();
    } catch (e) { console.error('[architect] ack failed', e); }
  };

  const recent = section?.recent_preview || rows;
  const stats  = section?.stats || {};

  return (
    <Card
      testid="architect-notifications-card"
      title={`Notification Center · ${unread} unread`}
      action={
        <button
          data-testid="architect-notif-refresh"
          onClick={reload}
          disabled={busy}
          className="text-[10px] font-mono text-accent-primary hover:text-accent-primary/80 disabled:opacity-50"
        >
          {busy ? 'loading…' : 'refresh'}
        </button>
      }
    >
      <div className="flex flex-wrap gap-2 mb-3">
        <select
          data-testid="architect-notif-severity-filter"
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-xs"
        >
          <option value="">all severities</option>
          <option value="debug">debug</option>
          <option value="info">info</option>
          <option value="warn">warn</option>
          <option value="critical">critical</option>
          <option value="fatal">fatal</option>
        </select>
        <select
          data-testid="architect-notif-category-filter"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-xs"
        >
          <option value="">all categories</option>
          <option value="scaling">scaling</option>
          <option value="supervisor">supervisor</option>
          <option value="compute_health">compute_health</option>
          <option value="deployment">deployment</option>
          <option value="recommendation">recommendation</option>
          <option value="system_health">system_health</option>
        </select>
        <select
          data-testid="architect-notif-status-filter"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-xs"
        >
          <option value="">all statuses</option>
          <option value="new">new</option>
          <option value="ack">ack</option>
          <option value="archived">archived</option>
        </select>
      </div>
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">
        per_severity ·{' '}
        {Object.entries(stats.per_severity || {}).map(([k, v]) =>
          `${k}=${v}`
        ).join(' · ') || '—'}
      </div>
      <ul className="space-y-1 max-h-72 overflow-auto" data-testid="architect-notif-list">
        {(recent.length === 0 ? rows : recent).map((n) => (
          <li
            key={n.id || n.ts}
            data-testid={`architect-notif-row-${n.id}`}
            className="flex items-start justify-between gap-2 p-2 rounded border border-zinc-800"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <SeverityChip severity={n.severity} />
                <span className="text-[10px] font-mono text-zinc-500">{n.event_type}</span>
                {n.status && n.status !== 'new' && (
                  <span className="text-[10px] text-zinc-500">[{n.status}]</span>
                )}
              </div>
              <div className="text-xs text-zinc-100 font-semibold truncate">
                {n.title}
              </div>
              <div className="text-[11px] text-zinc-400 truncate">
                {n.message}
              </div>
              {n.suggested_action && (
                <div className="text-[10px] text-accent-primary/90 mt-0.5 truncate">
                  → {n.suggested_action}
                </div>
              )}
            </div>
            {n.status === 'new' && (
              <button
                data-testid={`architect-notif-ack-${n.id}`}
                onClick={() => ackRow(n.id)}
                className="text-[10px] font-mono text-zinc-400 hover:text-emerald-300 border border-zinc-700 rounded px-1.5 py-0.5 flex-shrink-0"
              >
                ack
              </button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function WorkerStatusCard({ workers, scheduler }) {
  const manifest = workers?.manifest || [];
  const sTasks = scheduler?.tasks || (workers?.scheduler?.tasks) || [];
  return (
    <Card testid="architect-worker-status-card" title="Worker Status & Scheduler">
      <KV label="worker_runtime.enabled" value={String(workers?.enabled)} />
      <KV label="worker_id"              value={workers?.worker_id} />
      <KV label="scheduler.enabled" value={String(scheduler?.enabled ?? workers?.scheduler?.enabled)} />
      <KV label="scheduler.running" value={String(scheduler?.running ?? workers?.scheduler?.running)} />
      <div className="mt-2 border-t border-zinc-800 pt-2 space-y-1">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">workers</div>
        {manifest.map((w) => (
          <div
            key={w.name}
            data-testid={`architect-worker-${w.name}`}
            className="flex items-center justify-between text-[11px]"
          >
            <span className="text-zinc-300">{w.name}</span>
            <span className={w.active ? 'text-emerald-300' : 'text-zinc-500'}>
              {w.active ? 'active' : 'inactive'}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2 border-t border-zinc-800 pt-2 space-y-1">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">scheduler tasks</div>
        {sTasks.map((t) => (
          <div
            key={t.name}
            data-testid={`architect-sched-task-${t.name}`}
            className="flex items-center justify-between text-[11px]"
          >
            <span className="text-zinc-300">{t.name}</span>
            <span className="text-zinc-500">
              flag={String(t.flag_value)} · {t.interval_sec}s · running={String(t.running)}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function RoutingCard({ routing, remoteTransport }) {
  return (
    <Card testid="architect-routing-card" title="Routing & Transport">
      <KV label="active_policy"   value={routing?.active} />
      <KV label="default_policy"  value={routing?.default} />
      <KV label="transport.active" value={remoteTransport?.active} />
      <div className="mt-2 border-t border-zinc-800 pt-2 space-y-0.5">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">policies</div>
        {(routing?.manifest || []).map((p) => (
          <div key={p.name} className="flex justify-between text-[11px]">
            <span className="text-zinc-300">{p.name}</span>
            <span className="text-zinc-500">{p.kind}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function AdmissionScalingEventsCard({ admission, scalingEvents }) {
  const recent = scalingEvents?.recent_preview || [];
  return (
    <Card testid="architect-admission-card" title="Admission & Scaling Events">
      <KV label="admission_band" value={admission?.band} />
      <KV label="admission_total" value={admission?.stats?.total} />
      <div className="mt-2 border-t border-zinc-800 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">recent events</div>
        <ul className="space-y-0.5 max-h-40 overflow-auto">
          {recent.slice(0, 20).map((e, i) => (
            <li key={i} className="text-[11px] flex items-center gap-2">
              <SeverityChip severity={e.severity} />
              <span className="text-zinc-300">{e.event_type}</span>
              <span className="text-zinc-500 truncate">{e.target_id}</span>
            </li>
          ))}
          {recent.length === 0 && <li className="text-zinc-500 text-[11px]">No recent events.</li>}
        </ul>
      </div>
    </Card>
  );
}

function DeploymentReadinessSection({ dep, payload }) {
  const evidence = dep?.evidence || {};
  return (
    <Card testid="architect-deployment-card" title="Deployment Readiness">
      <KV label="ready" value={String(dep?.ready)} />
      <KV label="blockers" value={(dep?.blockers || []).length} />
      <div className="mt-2 border-t border-zinc-800 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">activation-ready features</div>
        <ul className="space-y-0.5">
          {(payload.activation_ready || []).map((f) => (
            <li key={f} className="text-[11px] text-emerald-300">{f}</li>
          ))}
          {(payload.activation_ready || []).length === 0 && (
            <li className="text-[11px] text-zinc-500">none</li>
          )}
        </ul>
      </div>
      {Object.keys(evidence).length > 0 && (
        <div className="mt-2 border-t border-zinc-800 pt-2">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">evidence</div>
          {Object.entries(evidence).map(([k, v]) => (
            <div key={k} className="flex justify-between text-[11px]">
              <span className="text-zinc-400">{k}</span>
              <span className="text-zinc-100">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function GovernancePanel() {
  const [manifest, setManifest] = useState(null);
  const [recsTop, setRecsTop]   = useState(null);
  const [verdicts, setVerdicts] = useState([]);
  const [answers, setAnswers]   = useState(null);
  const [proposals, setProposals] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [mf, top, el, ans, props] = await Promise.all([
        getJson('/api/factory-supervisor/copilot/advanced/manifest'),
        getJson('/api/factory-supervisor/recommendations/top'),
        getJson('/api/factory-supervisor/eligibility'),
        getJson('/api/factory-supervisor/copilot/answers'),
        getJson('/api/factory-supervisor/fag/proposals?limit=10'),
      ]);
      setManifest(mf);
      setRecsTop(top);
      setVerdicts(el?.verdicts || []);
      setAnswers(ans);
      setProposals(props?.rows || []);
    } catch (e) {
      console.warn('[architect-governance] load failed', e);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => { if (active) await load(); })();
    return () => { active = false; };
  }, [load]);

  return (
    <Card
      testid="architect-governance-card"
      title="FAG · Copilot · Eligibility (FS-P1.4 — advisory only)"
      action={(
        <button
          data-testid="governance-refresh-btn"
          onClick={load}
          disabled={busy}
          className="text-[10px] font-mono px-2 py-1 rounded border border-zinc-700 hover:border-zinc-500 text-zinc-300"
        >
          {busy ? 'loading…' : 'refresh'}
        </button>
      )}
    >
      {/* Manifest */}
      <div data-testid="governance-manifest" className="mb-3">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">copilot · advanced</div>
        <KV label="enabled" value={String(manifest?.enabled)} testid="gov-copilot-enabled" />
        <KV label="active provider" value={manifest?.active_provider} testid="gov-copilot-active-provider" />
        <KV label="registered" value={(manifest?.registered || []).join(', ') || '—'} testid="gov-copilot-registered" />
        <KV label="advisory_only" value={String(manifest?.advisory_only)} />
      </div>

      {/* Top recommendation */}
      {recsTop?.top && (
        <div className="mb-3 border-t border-zinc-800 pt-2">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">top recommendation</div>
          <KV label="code" value={recsTop.top.code} testid="gov-top-code" />
          <KV label="severity" value={recsTop.top.severity} />
          <KV label="message" value={recsTop.top.message} />
        </div>
      )}

      {/* Eligibility verdicts */}
      <div className="mb-3 border-t border-zinc-800 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">eligibility verdicts</div>
        <div className="space-y-0.5">
          {verdicts.map((v) => (
            <div key={v.feature} data-testid={`gov-verdict-${v.feature}`} className="flex items-center gap-2 text-[11px]">
              <span className={v.eligible ? 'text-emerald-300' : 'text-amber-300'}>
                {v.eligible ? '●' : '○'}
              </span>
              <span className="text-zinc-200 font-mono">{v.feature}</span>
              <span className="text-zinc-500 text-[10px]">
                {(v.reasons || []).slice(0, 2).join(', ')}
              </span>
            </div>
          ))}
          {verdicts.length === 0 && (
            <div className="text-[11px] text-zinc-500">no verdicts</div>
          )}
        </div>
      </div>

      {/* Canonical answers (Q3 + Q8 only — most actionable) */}
      {answers?.answers && (
        <div className="mb-3 border-t border-zinc-800 pt-2">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">copilot · operational answers</div>
          <KV
            label="what next?"
            value={answers.answers.what_should_i_do_next?.answer}
            testid="gov-answer-next"
          />
          <KV
            label="auto-learning?"
            value={answers.answers.is_auto_learning_ready?.answer}
            testid="gov-answer-auto-learning"
          />
        </div>
      )}

      {/* FAG proposals (read-only list) */}
      <div className="border-t border-zinc-800 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">fag proposals (latest)</div>
        {proposals.length === 0 ? (
          <div className="text-[11px] text-zinc-500" data-testid="gov-no-proposals">
            none — fag engine off / no observations
          </div>
        ) : (
          <ul className="space-y-0.5">
            {proposals.map((p) => (
              <li key={p.proposal_id} className="flex justify-between text-[11px]">
                <span className="text-zinc-200 font-mono">{p.feature}</span>
                <span className="text-zinc-400">{p.state}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

// ─── Auto-Learning Infrastructure (FS-P1.4) ─────────────────────────────


function AutoLearningPanel() {
  const [status, setStatus]     = useState(null);
  const [insights, setInsights] = useState([]);
  const [report, setReport]     = useState(null);
  const [busy, setBusy]         = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [st, ins, agg] = await Promise.all([
        getJson('/api/factory-supervisor/auto-learning/status'),
        getJson('/api/factory-supervisor/auto-learning/insights'),
        getJson('/api/factory-supervisor/auto-learning/aggregate'),
      ]);
      setStatus(st);
      setInsights(ins?.insights || []);
      setReport(agg);
    } catch (e) {
      console.warn('[architect-auto-learning] load failed', e);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => { if (active) await load(); })();
    return () => { active = false; };
  }, [load]);

  const sevTint = (s) => {
    if (s === 'critical') return 'text-rose-300';
    if (s === 'warn')     return 'text-amber-300';
    if (s === 'suggestion') return 'text-sky-300';
    return 'text-zinc-400';
  };

  const components = report?.components || {};

  return (
    <Card
      testid="architect-auto-learning-card"
      title="Auto-Learning Infrastructure (FS-P1.4 — advisory only)"
      action={(
        <button
          data-testid="auto-learning-refresh-btn"
          onClick={load}
          disabled={busy}
          className="text-[10px] font-mono px-2 py-1 rounded border border-zinc-700 hover:border-zinc-500 text-zinc-300"
        >
          {busy ? 'loading…' : 'refresh'}
        </button>
      )}
    >
      {/* Status row */}
      <div data-testid="auto-learning-status" className="mb-3">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">aggregator status</div>
        <KV label="enabled"
            value={String(status?.enabled)}
            testid="al-enabled" />
        <KV label="loop_enabled"
            value={String(status?.loop_enabled)}
            testid="al-loop-enabled" />
        <KV label="operator_directive"
            value={status?.operator_directive || 'off'}
            testid="al-directive" />
        <KV label="advisory_only"
            value={String(report?.advisory_only ?? true)} />
      </div>

      {/* Component sources */}
      <div className="mb-3 border-t border-zinc-800 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">connected components</div>
        {['risk_of_ruin', 'lifecycle_decay', 'calibration_framework', 'execution_realism_defaults'].map((c) => {
          const src = report?.sources?.[c];
          const comp = components[c] || {};
          const ok = src === 'ok';
          return (
            <div key={c}
                 data-testid={`al-component-${c}`}
                 className="flex items-center gap-2 text-[11px]">
              <span className={ok ? 'text-emerald-300' : 'text-amber-300'}>
                {ok ? '●' : '○'}
              </span>
              <span className="text-zinc-200 font-mono">{c}</span>
              <span className="text-zinc-500 text-[10px]">
                {comp.is_active ? 'active' : 'dormant'}
              </span>
            </div>
          );
        })}
      </div>

      {/* Insight list */}
      <div className="border-t border-zinc-800 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">
          insights ({insights.length})
        </div>
        {insights.length === 0 ? (
          <div className="text-[11px] text-zinc-500" data-testid="al-no-insights">
            none — aggregator returned no rows
          </div>
        ) : (
          <ul className="space-y-1">
            {insights.map((ins, idx) => (
              <li key={`${ins.kind}-${idx}`}
                  data-testid={`al-insight-${ins.kind}`}
                  className="text-[11px] leading-snug">
                <div className="flex items-center gap-2">
                  <span className={sevTint(ins.severity)}>●</span>
                  <span className="text-zinc-200 font-mono">{ins.kind}</span>
                  <span className="text-zinc-500 text-[10px]">{ins.severity}</span>
                </div>
                <div className="pl-4 text-zinc-300">{ins.title}</div>
                {ins.suggested_action ? (
                  <div className="pl-4 text-zinc-500 italic text-[10px]">
                    → {ins.suggested_action}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

// ─── Main component ─────────────────────────────────────────────────────


export default function ArchitectDashboard() {
  const [payload, setPayload] = useState(null);
  const [scheduler, setScheduler] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, s] = await Promise.all([
        getJson('/api/factory-supervisor/architect/dashboard?refresh=true'),
        getJson('/api/factory-supervisor/scheduler/status'),
      ]);
      setPayload(d);
      setScheduler(s);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => { if (active) await load(); })();
    const t = setInterval(() => { void load(); }, 15000);   // poll every 15 s
    return () => { active = false; clearInterval(t); };
  }, [load]);

  if (error) {
    return (
      <div data-testid="architect-error" className="p-6 text-sm text-red-300 font-mono">
        Architect Dashboard failed: {error}
      </div>
    );
  }
  if (!payload) {
    return (
      <div data-testid="architect-loading" className="p-6 text-sm text-zinc-400 font-mono">
        Loading Factory Supervisor read model…
      </div>
    );
  }

  const sections = payload.sections || {};

  return (
    <div data-testid="architect-dashboard" className="space-y-2">
      {/* Banner */}
      <div className="flex flex-wrap items-center gap-3 p-4 rounded-md border border-zinc-800 bg-surface-card">
        <h2 className="text-base font-semibold text-zinc-100 tracking-tight mr-2">
          Architect Dashboard
        </h2>
        <span className="text-[10px] font-mono text-accent-primary border border-accent-primary/30 bg-accent-primary-soft px-1.5 py-0.5 rounded">
          {payload.phase || 'FS-P1.4'}
        </span>
        <HealthChip health={payload.system_health} />
        <span
          data-testid="architect-advisory-badge"
          className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
            payload.advisory_only
              ? 'text-amber-300 border-amber-500/30 bg-amber-500/10'
              : 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10'
          }`}
          title={payload.advisory_only
            ? 'FS_ENABLE_ARCHITECT_DASHBOARD=OFF — Architect output is advisory only. Downstream consumers (Copilot/FAG/Auto-Learning) MUST NOT act on this data.'
            : 'FS_ENABLE_ARCHITECT_DASHBOARD=ON — downstream consumers permitted.'}
        >
          {payload.advisory_only ? 'advisory_only' : 'consumable'}
        </span>
        <span className="text-[10px] font-mono text-zinc-500 ml-auto">
          read-only · zero execution authority · evaluated&nbsp;{payload.evaluated_at}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <NextRecommendedActionCard
            payload={payload}
            onRefresh={load}
            loading={loading}
          />
          <FleetHealthCard fleet={sections.fleet_health} />
          <QueuePressureCard
            qp={sections.queue_pressure}
            submissions={sections.submissions}
          />
          <DeferQueueCard
            dq={sections.defer_queue}
            blocked={payload.blocked}
          />
          <RoutingCard
            routing={sections.routing_stats}
            remoteTransport={sections.remote_transport}
          />
        </div>
        <div>
          <NotificationsCard
            section={sections.notifications}
            onAck={load}
          />
          <AdmissionScalingEventsCard
            admission={sections.admission_stats}
            scalingEvents={sections.scaling_events}
          />
          <WorkerStatusCard
            workers={sections.worker_status}
            scheduler={scheduler}
          />
          <DeploymentReadinessSection
            dep={sections.deployment_readiness}
            payload={payload}
          />
          <GovernancePanel />
          <AutoLearningPanel />
        </div>
      </div>
    </div>
  );
}
