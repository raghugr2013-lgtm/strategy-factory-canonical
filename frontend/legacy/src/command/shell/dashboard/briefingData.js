/**
 * COMMAND · Phase U.3 — Mission Briefing data layer
 * ----------------------------------------------------------------------------
 * One hook, eight read-only endpoints, posture-aware polling cadence:
 *
 *   /api/health                       (anonymous, always polled)
 *   /api/admin/readiness              (overall + checks)
 *   /api/orchestrator/heartbeat       (scheduler state + audit log size)
 *   /api/llm/diagnostics              (provider routing + unknown-provider hint)
 *   /api/llm/runner-state             (active semaphores + caps)
 *   /api/llm/call-log/recent?limit=10 (admin-only LLM tail)
 *   /api/governance/survivor-registry (top survivors)
 *   /api/ingestion/status             (last run + accept/reject counts)
 *
 * Failures degrade the chip to amber/red rather than throwing — the
 * briefing must always render something calm.
 */
import { useEffect, useState, useCallback, useRef } from 'react';

const BACKEND = process.env.REACT_APP_BACKEND_URL || '';

function authHeaders() {
  try {
    const t = localStorage.getItem('asf_auth_token');
    return t ? { Authorization: `Bearer ${t}` } : {};
  } catch (_) { return {}; }
}

async function fetchJSON(path, opts = {}) {
  try {
    const r = await fetch(`${BACKEND}${path}`, {
      credentials: 'omit',
      headers: { ...authHeaders(), ...(opts.headers || {}) },
    });
    if (!r.ok) return { __err: r.status };
    return await r.json();
  } catch (e) {
    return { __err: e.message || 'network' };
  }
}

const POLL_MS = {
  workstation: 8000,
  tablet:     14000,
  briefing:   30000,
};

/**
 * synthesizeAttention — turn raw endpoint output into a calm, prioritised
 * list of operator-attention items. Each item: { tone, key, label, hint }.
 * Returns an empty list when nothing needs operator attention.
 */
export function synthesizeAttention({ health, readiness, llm, runner, heartbeat, ingestion }) {
  const out = [];

  // 1. Backend health
  if (!health || health.__err) {
    out.push({ tone: 'red', key: 'backend', label: 'Backend health unreachable',
               hint: typeof (health && health.__err) === 'number' ? `HTTP ${health.__err}` : 'network' });
  }

  // 2. LLM provider key
  if (llm && !llm.__err) {
    const prov = llm.primary_provider;
    const configured = !!(llm.providers && llm.providers[prov] && llm.providers[prov].configured);
    if (!configured) {
      out.push({ tone: 'red', key: 'llm-key',
                 label: `AI provider missing key · ${prov}`,
                 hint: 'set the appropriate API key in backend .env and restart' });
    }
    const unknown = Array.isArray(llm.unknown_providers_referenced) ? llm.unknown_providers_referenced : [];
    if (unknown.length > 0) {
      out.push({ tone: 'amber', key: 'llm-unknown',
                 label: `Unknown provider referenced in routing · ${unknown.length}`,
                 hint: unknown.slice(0, 3).map((u) => `${u.var}=${u.value}`).join(' · ') });
    }
  }

  // 3. Readiness rollup
  if (readiness && !readiness.__err) {
    const overall = (readiness.overall || '').toLowerCase();
    if (overall === 'fail') {
      out.push({ tone: 'red', key: 'readiness',
                 label: 'Deployment readiness · FAIL',
                 hint: 'open /c/diag for full checklist' });
    } else if (overall === 'warn') {
      out.push({ tone: 'amber', key: 'readiness',
                 label: 'Deployment readiness · WARN',
                 hint: `${(readiness.checks || []).filter((c) => c.status === 'warn').length} warning(s)` });
    }
  }

  // 4. Ingestion last-run
  if (ingestion && !ingestion.__err) {
    const status = ingestion.last_run_status;
    if (status && status !== 'ok') {
      out.push({ tone: 'amber', key: 'ingestion',
                 label: `Ingestion last-run · ${status}`,
                 hint: `at ${ingestion.last_run_at || '—'}` });
    }
    const stats = ingestion.last_run_stats || {};
    const rejected = stats.total_rejected || 0;
    const accepted = stats.total_injected || 0;
    if (rejected > 0 && accepted === 0) {
      out.push({ tone: 'amber', key: 'ingestion-reject',
                 label: `Ingestion · 100% rejected last run`,
                 hint: `${rejected} candidate(s) rejected, 0 injected` });
    }
  }

  // 5. Heartbeat duplicates
  if (heartbeat && !heartbeat.__err) {
    if (heartbeat.duplicate_tick_warning) {
      out.push({ tone: 'amber', key: 'duplicate-ticks',
                 label: 'Duplicate orchestrator ticks detected',
                 hint: `${heartbeat.duplicate_tick_count_last_24h || 0} in last 24h` });
    }
  }

  // 6. Runner stuck calls (>120s)
  if (runner && !runner.__err) {
    const active = runner.active_semaphores || {};
    const stuckCount = Object.values(active).filter((v) => (v.held_for_s || 0) > 120).length;
    if (stuckCount > 0) {
      out.push({ tone: 'amber', key: 'stuck-llm',
                 label: `${stuckCount} long-running LLM call(s)`,
                 hint: 'open /c/ai for the call-log river' });
    }
  }

  return out;
}

export function useBriefingData(posture = 'workstation') {
  const [data, setData] = useState({
    health: null, readiness: null, llm: null, runner: null,
    heartbeat: null, calls: null, survivors: null, ingestion: null,
    fetched_at: null,
  });
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  const tick = useCallback(async () => {
    const [health, readiness, llm, runner, heartbeat, calls, survivors, ingestion] = await Promise.all([
      fetchJSON('/api/health'),
      fetchJSON('/api/admin/readiness'),
      fetchJSON('/api/llm/diagnostics'),
      fetchJSON('/api/llm/runner-state'),
      fetchJSON('/api/orchestrator/heartbeat'),
      fetchJSON('/api/llm/call-log/recent?limit=10'),
      fetchJSON('/api/governance/survivor-registry?limit=3'),
      fetchJSON('/api/ingestion/status'),
    ]);
    if (!mounted.current) return;
    setData({ health, readiness, llm, runner, heartbeat, calls, survivors, ingestion,
              fetched_at: new Date().toISOString() });
    setLoading(false);
  }, []);

  useEffect(() => {
    mounted.current = true;
    const ms = POLL_MS[posture] || POLL_MS.workstation;
    let timer;
    (async () => {
      await tick();
      if (!mounted.current) return;
      timer = setInterval(tick, ms);
    })();
    return () => { mounted.current = false; if (timer) clearInterval(timer); };
  }, [posture, tick]);

  return { data, loading, refresh: tick };
}

/**
 * fetchBriefingOnce — Phase U.5.b — Briefing Print Mode.
 * Standalone one-shot fetch used by BriefingPrint. NEVER polls. NEVER
 * reuses or competes with useBriefingData's interval. Designed so the
 * `?print=1` surface produces a single, deterministic, audit-stable
 * snapshot at the moment the operator opens it.
 *
 * Returns the same shape as useBriefingData's `data` (plus fetched_at).
 */
export async function fetchBriefingOnce() {
  const [health, readiness, llm, runner, heartbeat, calls, survivors, ingestion] = await Promise.all([
    fetchJSON('/api/health'),
    fetchJSON('/api/admin/readiness'),
    fetchJSON('/api/llm/diagnostics'),
    fetchJSON('/api/llm/runner-state'),
    fetchJSON('/api/orchestrator/heartbeat'),
    fetchJSON('/api/llm/call-log/recent?limit=10'),
    fetchJSON('/api/governance/survivor-registry?limit=3'),
    fetchJSON('/api/ingestion/status'),
  ]);
  return {
    health, readiness, llm, runner, heartbeat, calls, survivors, ingestion,
    fetched_at: new Date().toISOString(),
  };
}
