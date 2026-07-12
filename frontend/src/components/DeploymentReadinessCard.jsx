import React, { useEffect, useState } from 'react';
import {
  Rocket,
  CheckCircle,
  Warning,
  XCircle,
  CircleNotch,
  Clock,
  HardDrives,
  Cpu,
  Memory,
  Package,
  Wrench,
  Database,
  Pulse,
  CaretRight,
  CaretDown,
} from '@phosphor-icons/react';
import { VerdictBadge, AsfEmptyState } from './ui-asf';

// Pass 15 — Deployment Readiness Card (read-only, advisory-only).
//
// Single-glance institutional answer to:
//   "Is this VPS environment actually ready for autonomous research
//    operation?"
//
// Composes THREE read-only endpoints in parallel:
//   1. /api/latent/deployment-readiness   (Pass 10):
//        python, env vars, mongo, supervisor, P0 invariants
//   2. /api/latent/deployment-extras      (Pass 15, this pass):
//        disk, packaging artifacts, recovery tooling,
//        supervisor service templates
//   3. /api/latent/activation-governance  (existing):
//        cpu pool / process pool readiness, compute headroom
//        (CPU% / mem% / load), dormant invariant snapshot
//
// Discipline:
//   • Read-only · advisory-only · no controls · no buttons that mutate.
//   • Composes existing surfaces — does NOT add new authority.
//   • Overall verdict is the most-severe component (FAIL > WARN > OK).
//   • Card never collapses (deployment-readiness is the operator's
//     most-frequent glance — collapsing would defeat its purpose).
//
// Aesthetic: matches GovernanceCard / ParityCertificationCard /
// IngestionHealthCard — zinc-on-black, monospaced labels, pill grid,
// drill-down collapsibles for the long lists.

const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8000`
  : (process.env.REACT_APP_BACKEND_URL || '');

async function fetchJson(path) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Accept: 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail?.error || body?.detail || '';
    } catch { /* ignore */ }
    throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`);
  }
  return res.json();
}

const VERDICT_TONE = {
  READY:   { dot: 'bg-emerald-400', text: 'text-emerald-300', label: 'READY' },
  WARN:    { dot: 'bg-amber-400',   text: 'text-amber-300',   label: 'WARN' },
  FAIL:    { dot: 'bg-rose-500',    text: 'text-rose-300',    label: 'FAIL' },
  UNKNOWN: { dot: 'bg-zinc-500',    text: 'text-zinc-400',    label: 'UNKNOWN' },
};

function StatusIcon({ ok, band, size = 12 }) {
  // Three-state: ok → emerald check, warn → amber warning, fail → rose X.
  const effectiveBand =
    band === 'critical' || band === 'error' ? 'fail' :
    band === 'warn'                          ? 'warn' :
    ok === true                              ? 'ok'   :
    ok === false                             ? 'fail' :
                                               'warn';
  if (effectiveBand === 'ok')
    return <CheckCircle size={size} weight="fill" className="text-emerald-400" />;
  if (effectiveBand === 'warn')
    return <Warning size={size} weight="fill" className="text-amber-400" />;
  return <XCircle size={size} weight="fill" className="text-rose-400" />;
}

function CheckRow({ icon, name, ok, band, detail, testId, children }) {
  const isOk = ok === true && (!band || band === 'ok');
  return (
    <div
      data-testid={testId}
      className="flex items-start gap-2 py-1.5 text-[10px] font-mono"
    >
      <StatusIcon ok={ok} band={band} size={12} />
      <div className="flex items-center gap-1.5 text-zinc-300 w-44 flex-shrink-0">
        {icon}
        <span className="uppercase tracking-wider">{name}</span>
      </div>
      <div className={`flex-1 ${isOk ? 'text-zinc-400' : 'text-amber-300'}`}>
        {detail}
        {children}
      </div>
    </div>
  );
}

function ProgressBar({ pct, tone = 'cyan' }) {
  const clamped = Math.max(0, Math.min(100, pct || 0));
  const toneClass = {
    cyan:    'bg-cyan-500/70',
    emerald: 'bg-emerald-500/70',
    amber:   'bg-amber-500/70',
    rose:    'bg-rose-500/70',
  }[tone] || 'bg-cyan-500/70';
  return (
    <div className="relative h-1 w-24 bg-zinc-800/80 rounded overflow-hidden inline-block ml-2 align-middle">
      <div
        className={`absolute inset-y-0 left-0 ${toneClass} transition-[width] duration-500`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export default function DeploymentReadinessCard() {
  const [core, setCore] = useState(null);
  const [extras, setExtras] = useState(null);
  const [governance, setGovernance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);
  const [showDetail, setShowDetail] = useState(false);

  const refresh = async () => {
    setError(null);
    try {
      // Compose all three endpoints in parallel — each one is small,
      // read-only, and cached server-side where applicable.
      const [c, e, g] = await Promise.all([
        fetchJson('/api/latent/deployment-readiness').catch((err) => ({ _err: err.message })),
        fetchJson('/api/latent/deployment-extras').catch((err) => ({ _err: err.message })),
        fetchJson('/api/latent/activation-governance').catch((err) => ({ _err: err.message })),
      ]);
      setCore(c);
      setExtras(e);
      setGovernance(g);
      setRefreshedAt(new Date().toISOString());
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // 60s polling — deployment-readiness changes slowly but is the
    // operator's most-frequent glance.
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, []);

  // Derive the unified verdict — most-severe wins.
  const coreStatus = core?.status;
  const extrasStatus = extras?.status;
  const headroomOk = governance?.compute?.headroom?.ok;
  const allDormant = governance?.feature_flags?.all_dormant;

  let verdict = 'UNKNOWN';
  if (core?._err || extras?._err) {
    verdict = 'FAIL';
  } else if (
    coreStatus === 'ready'
    && extrasStatus === 'ok'
    && headroomOk === true
    && allDormant === true
  ) {
    verdict = 'READY';
  } else if (
    coreStatus === 'not_ready'
    || extrasStatus === 'critical'
    || headroomOk === false
    || allDormant === false
  ) {
    verdict = 'FAIL';
  } else if (coreStatus || extrasStatus) {
    verdict = 'WARN';
  }
  const tone = VERDICT_TONE[verdict] || VERDICT_TONE.UNKNOWN;

  const coreChecks = core?.checks || [];
  const extrasChecks = extras?.checks || [];
  const cpuPool = governance?.cpu_pool || {};
  const compute = governance?.compute || {};
  const snap = compute?.snapshot || {};
  const head = compute?.headroom || {};

  // Pull individual core-check rows by name for the operator pills.
  const byName = Object.fromEntries(coreChecks.map((c) => [c.name, c]));
  const pyCheck       = byName.python_version;
  const envCheck      = byName.required_env_vars;
  const mongoCheck    = byName.mongo;
  const supCheck      = byName.supervisor;
  const p0Check       = byName.p0_invariants;

  // Pull extras-check rows by name.
  const extrasByName  = Object.fromEntries(extrasChecks.map((c) => [c.name, c]));
  const diskCheck     = extrasByName.disk;
  const packagingCheck = extrasByName.packaging;
  const recoveryCheck = extrasByName.recovery_tooling;
  const supTplCheck   = extrasByName.supervisor_templates;

  // Verdict-bar rationale (one line, operator-facing).
  let rationale = '—';
  if (verdict === 'READY') {
    rationale = 'All readiness checks pass · packaging present · recovery tooling intact · CPU/mem headroom healthy · all_dormant=true. Backend is institutionally cleared for VPS production operation.';
  } else if (verdict === 'FAIL') {
    rationale = [
      core?._err && `core: ${core._err}`,
      extras?._err && `extras: ${extras._err}`,
      coreStatus === 'not_ready' && (core?.summary || 'core readiness failed'),
      extrasStatus === 'critical' && 'storage or recovery tooling critical',
      headroomOk === false && 'host headroom exhausted',
      allDormant === false && 'dormancy invariant broken',
    ].filter(Boolean).join(' · ') || 'one or more checks failed';
  } else if (verdict === 'WARN') {
    rationale = (
      extrasStatus === 'warn'
        ? 'one or more deployment artifacts missing or storage low'
        : (core?.summary || 'partial readiness — operator review required')
    );
  }

  return (
    <div
      data-testid="deployment-readiness-card"
      className="asf-section asf-u2-panel card-premium p-4 border border-zinc-800/80 bg-zinc-950/40 mb-4"
    >
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="asf-section__hd flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="asf-legacy-title flex items-center gap-2">
          <Rocket size={14} weight="fill" className="text-cyan-400" />
          <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-300">
            Deployment Readiness · Pass 15
          </h3>
          <span className="text-[9px] font-mono text-zinc-600 uppercase tracking-wider">
            read-only · advisory-only
          </span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2 text-[10px] font-mono text-zinc-500">
          {loading && <CircleNotch size={11} className="animate-spin" />}
          {refreshedAt && !loading && (
            <span data-testid="deployment-readiness-refreshed" className="flex items-center gap-1">
              <Clock size={10} />
              {new Date(refreshedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            data-testid="deployment-readiness-refresh"
            onClick={refresh}
            className="px-2 py-0.5 border border-zinc-700/60 rounded hover:border-zinc-500 hover:text-zinc-300 transition-colors"
            title="Refresh now"
          >
            refresh
          </button>
        </div>
      </div>

      {error && (
        <AsfEmptyState
          slug="deployment-readiness-error"
          testId="deployment-readiness-error"
          title="Deployment readiness probe failed"
          body={error}
        />
      )}

      {/* ── Verdict + rationale ─────────────────────────────────── */}
      <div className="mb-3 flex items-start gap-2 flex-wrap">
        <VerdictBadge
          verdict={
            verdict === 'READY' ? 'success' :
            verdict === 'WARN'  ? 'warn'    :
            verdict === 'FAIL'  ? 'danger'  : 'neutral'
          }
          label={tone.label}
          testId="deployment-readiness-verdict"
        />
        <span
          data-testid="deployment-readiness-rationale"
          className="text-[10px] font-mono text-zinc-400 flex-1 min-w-[300px] mt-0.5"
        >
          {rationale}
        </span>
      </div>

      {/* ── Pills row: top-5 dimensions ────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3 pt-2 border-t border-zinc-800/60">
        <div data-testid="deployment-readiness-pill-runtime" className="flex items-start gap-1.5">
          <StatusIcon ok={pyCheck?.ok} size={11} />
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">Runtime</span>
            <span className="font-mono text-zinc-200 text-[11px] font-semibold">
              Python {pyCheck?.value || '—'}
            </span>
          </div>
        </div>

        <div data-testid="deployment-readiness-pill-mongo" className="flex items-start gap-1.5">
          <StatusIcon ok={mongoCheck?.ok} size={11} />
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">Mongo</span>
            <span className="font-mono text-zinc-200 text-[11px] font-semibold">
              {mongoCheck?.db_name || '—'} · {mongoCheck?.collection_count ?? '—'} colls
            </span>
          </div>
        </div>

        <div data-testid="deployment-readiness-pill-supervisor" className="flex items-start gap-1.5">
          <StatusIcon ok={supCheck?.ok} size={11} />
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">Supervisor</span>
            <span className="font-mono text-zinc-200 text-[11px] font-semibold">
              {supCheck?.ok ? 'RUNNING' : 'NOT_RUNNING'}
            </span>
          </div>
        </div>

        <div data-testid="deployment-readiness-pill-disk" className="flex items-start gap-1.5">
          <StatusIcon ok={diskCheck?.ok} band={diskCheck?.band} size={11} />
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">Disk</span>
            <span className="font-mono text-zinc-200 text-[11px] font-semibold">
              {diskCheck?.free_pct != null
                ? `${diskCheck.free_pct.toFixed(1)}% free`
                : '—'}
            </span>
          </div>
        </div>

        <div data-testid="deployment-readiness-pill-dormancy" className="flex items-start gap-1.5">
          <StatusIcon ok={p0Check?.ok && allDormant === true} size={11} />
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">Dormancy</span>
            <span className="font-mono text-zinc-200 text-[11px] font-semibold">
              {governance?.feature_flags?.flag_count ?? '—'} flags · all_dormant={String(allDormant ?? '—')}
            </span>
          </div>
        </div>
      </div>

      {/* ── Compute headroom row ─────────────────────────────────── */}
      <div
        data-testid="deployment-readiness-headroom"
        className="mb-3 pt-2 border-t border-zinc-800/60 grid grid-cols-1 md:grid-cols-3 gap-3 text-[10px] font-mono"
      >
        <div className="flex items-center gap-2">
          <Cpu size={11} weight="bold" className="text-zinc-500" />
          <span className="text-zinc-500 uppercase tracking-wider">cpu:</span>
          <span className={head.cpu_headroom_pct >= 50 ? 'text-emerald-300' : head.cpu_headroom_pct >= 20 ? 'text-amber-300' : 'text-rose-300'}>
            {head.cpu_headroom_pct != null ? `${head.cpu_headroom_pct.toFixed(1)}%` : '—'} headroom
          </span>
          <ProgressBar pct={head.cpu_headroom_pct} tone={head.cpu_headroom_pct >= 50 ? 'emerald' : head.cpu_headroom_pct >= 20 ? 'amber' : 'rose'} />
          <span className="text-zinc-500">· {snap.cpu_count || '—'} cores</span>
          {snap.load_avg && snap.load_avg.length >= 1 && (
            <span className="text-zinc-500">· load {snap.load_avg[0]?.toFixed(2)}</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Memory size={11} weight="bold" className="text-zinc-500" />
          <span className="text-zinc-500 uppercase tracking-wider">mem:</span>
          <span className={head.mem_headroom_pct >= 30 ? 'text-emerald-300' : head.mem_headroom_pct >= 15 ? 'text-amber-300' : 'text-rose-300'}>
            {head.mem_headroom_pct != null ? `${head.mem_headroom_pct.toFixed(1)}%` : '—'} headroom
          </span>
          <ProgressBar pct={head.mem_headroom_pct} tone={head.mem_headroom_pct >= 30 ? 'emerald' : head.mem_headroom_pct >= 15 ? 'amber' : 'rose'} />
          <span className="text-zinc-500">
            · {snap.mem_available_gb != null ? `${snap.mem_available_gb.toFixed(1)}` : '—'} / {snap.mem_total_gb != null ? `${snap.mem_total_gb.toFixed(1)}` : '—'} GB
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Pulse size={11} weight="bold" className="text-zinc-500" />
          <span className="text-zinc-500 uppercase tracking-wider">process-pool:</span>
          <span className={cpuPool.pool_initialized ? 'text-emerald-300' : 'text-zinc-400'}>
            {cpuPool.pool_initialized ? 'initialized' : 'dormant'}
          </span>
          <span className="text-zinc-500">
            · {cpuPool.worker_count ?? 0} / {cpuPool.pool_size_configured ?? 0} workers
          </span>
          {cpuPool.enabled === false && (
            <span className="text-zinc-500">· flag OFF</span>
          )}
        </div>
      </div>

      {/* ── Drill-down toggle: full check list ─────────────────── */}
      <div className="pt-2 border-t border-zinc-800/60">
        <button
          data-testid="deployment-readiness-toggle-detail"
          onClick={() => setShowDetail(!showDetail)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-cyan-300 hover:text-cyan-200"
        >
          {showDetail ? <CaretDown size={10} weight="bold" /> : <CaretRight size={10} weight="bold" />}
          <span className="uppercase tracking-wider">
            full check detail ({coreChecks.length + extrasChecks.length})
          </span>
        </button>
        {showDetail && (
          <div data-testid="deployment-readiness-detail-list" className="mt-2 divide-y divide-zinc-800/40">
            {/* ── Core checks (Pass 10) ─────────────────────── */}
            <CheckRow
              icon={<Cpu size={11} weight="bold" />} name="Python"
              ok={pyCheck?.ok}
              detail={`${pyCheck?.value || '—'} (required ${pyCheck?.required || '—'}) · ${pyCheck?.detail || ''}`}
              testId="deployment-readiness-detail-python"
            />
            <CheckRow
              icon={<Database size={11} weight="bold" />} name="Env vars"
              ok={envCheck?.ok}
              detail={`required=${envCheck?.required_count ?? '—'} · missing-required=${(envCheck?.missing_required || []).length} · missing-recommended=${(envCheck?.missing_recommended || []).length}`}
              testId="deployment-readiness-detail-env"
            >
              {(envCheck?.missing_required || []).length > 0 && (
                <div className="text-rose-300 mt-0.5">missing-required: {envCheck.missing_required.join(', ')}</div>
              )}
            </CheckRow>
            <CheckRow
              icon={<Database size={11} weight="bold" />} name="Mongo"
              ok={mongoCheck?.ok}
              detail={`${mongoCheck?.detail || '—'} · db=${mongoCheck?.db_name || '—'} · ${mongoCheck?.collection_count ?? '—'} collections`}
              testId="deployment-readiness-detail-mongo"
            />
            <CheckRow
              icon={<Pulse size={11} weight="bold" />} name="Supervisor"
              ok={supCheck?.ok}
              detail={supCheck?.raw || supCheck?.detail || '—'}
              testId="deployment-readiness-detail-supervisor"
            />
            <CheckRow
              icon={<CheckCircle size={11} weight="bold" />} name="P0 invariants"
              ok={p0Check?.ok}
              detail={`legacy retired=${String(p0Check?.p0_1_legacy_generator_retired ?? '—')} · scaffold importable=${String(p0Check?.p0_2_3_scaffold_importable ?? '—')} · all_dormant=${String(p0Check?.all_dormant ?? '—')}`}
              testId="deployment-readiness-detail-p0"
            />
            {/* ── Extras (Pass 15) ─────────────────────────── */}
            <CheckRow
              icon={<HardDrives size={11} weight="bold" />} name="Disk"
              ok={diskCheck?.ok} band={diskCheck?.band}
              detail={`${diskCheck?.detail || '—'} · ${diskCheck?.used_gb ?? '—'} GB used / ${diskCheck?.total_gb ?? '—'} GB total`}
              testId="deployment-readiness-detail-disk"
            />
            <CheckRow
              icon={<Package size={11} weight="bold" />} name="Packaging"
              ok={packagingCheck?.ok}
              detail={packagingCheck?.detail || '—'}
              testId="deployment-readiness-detail-packaging"
            >
              {(packagingCheck?.missing || []).length > 0 && (
                <div className="text-rose-300 mt-0.5">missing: {packagingCheck.missing.join(', ')}</div>
              )}
            </CheckRow>
            <CheckRow
              icon={<Wrench size={11} weight="bold" />} name="Recovery tooling"
              ok={recoveryCheck?.ok}
              detail={recoveryCheck?.detail || '—'}
              testId="deployment-readiness-detail-recovery"
            >
              {(recoveryCheck?.missing || []).length > 0 && (
                <div className="text-rose-300 mt-0.5">missing: {recoveryCheck.missing.join(', ')}</div>
              )}
              {(recoveryCheck?.not_executable || []).length > 0 && (
                <div className="text-amber-300 mt-0.5">not executable: {recoveryCheck.not_executable.join(', ')}</div>
              )}
              {recoveryCheck?.present && recoveryCheck.present.length > 0 && (
                <div className="text-zinc-500 mt-0.5">
                  scripts: {recoveryCheck.present.join(' · ')}
                </div>
              )}
            </CheckRow>
            <CheckRow
              icon={<Pulse size={11} weight="bold" />} name="Supervisor templates"
              ok={supTplCheck?.ok}
              detail={supTplCheck?.detail || '—'}
              testId="deployment-readiness-detail-sup-templates"
            >
              {(supTplCheck?.present || []).length > 0 && (
                <div className="text-zinc-500 mt-0.5">
                  templates: {supTplCheck.present.join(' · ')}
                </div>
              )}
            </CheckRow>
          </div>
        )}
      </div>
    </div>
  );
}
