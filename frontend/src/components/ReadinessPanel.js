import React, { useCallback, useEffect, useState } from 'react';
import {
  ShieldCheck,
  CheckCircle,
  Warning,
  XCircle,
  ArrowsClockwise,
  Spinner,
  CaretDown,
  CaretRight,
} from '@phosphor-icons/react';
import { adminReadinessCheck } from '../services/auth';
import { AsfEmptyState, VerdictBadge } from './ui-asf';

const STATUS_VERDICT = { green: 'success', yellow: 'warn', red: 'danger' };

/**
 * System Readiness Check — Admin Tab.
 *
 * Fully additive safety + visibility layer. Read-only: never mutates
 * any collection, never triggers a pipeline. Intended to be consulted
 * BEFORE running Auto Factory, deploying to VPS, or enabling live
 * trading.
 *
 * Surfaces 5 checks:
 *   1. Market data coverage
 *   2. LLM key / budget
 *   3. Alerts configuration
 *   4. Active run integrity
 *   5. Drawdown / risk limits
 *
 * Each check returns green / yellow / red + a one-line summary +
 * structured details (collapsible).
 */

const STATUS_META = {
  green: {
    label: 'Ready',
    Icon: CheckCircle,
    // Light + dark tokens from the existing palette.
    badge: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300',
    dot: 'bg-emerald-400',
  },
  yellow: {
    label: 'Warning',
    Icon: Warning,
    badge: 'bg-yellow-500/10 border-yellow-500/40 text-yellow-300',
    dot: 'bg-yellow-400',
  },
  red: {
    label: 'Blocked',
    Icon: XCircle,
    badge: 'bg-red-500/10 border-red-500/40 text-red-300',
    dot: 'bg-red-400',
  },
};

function StatusPill({ status, big = false }) {
  const meta = STATUS_META[status] || STATUS_META.yellow;
  const Icon = meta.Icon;
  const size = big ? 14 : 12;
  return (
    <span
      data-testid={`readiness-status-${status}`}
      className={`inline-flex items-center gap-1.5 font-mono font-bold uppercase rounded border ${meta.badge} ${
        big ? 'text-[11px] px-2.5 py-1' : 'text-[10px] px-2 py-0.5'
      }`}
    >
      <Icon size={size} weight="bold" />
      {meta.label}
    </span>
  );
}

function CheckRow({ check }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      data-testid={`readiness-check-${check.id}`}
      className="border border-zinc-800 bg-[#121821] rounded-md overflow-hidden"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        data-testid={`readiness-check-${check.id}-toggle`}
        className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-zinc-900/40 transition-colors"
      >
        <span className={`w-2 h-2 rounded-full ${STATUS_META[check.status]?.dot || 'bg-zinc-400'}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-zinc-100">{check.label}</span>
            <StatusPill status={check.status} />
          </div>
          <p
            data-testid={`readiness-check-${check.id}-summary`}
            className="mt-0.5 text-[11px] text-zinc-400 truncate"
          >
            {check.summary}
          </p>
        </div>
        {open ? (
          <CaretDown size={14} className="text-zinc-500 flex-shrink-0" />
        ) : (
          <CaretRight size={14} className="text-zinc-500 flex-shrink-0" />
        )}
      </button>
      {open && (
        <div
          data-testid={`readiness-check-${check.id}-details`}
          className="px-4 pb-3 border-t border-zinc-800/70"
        >
          <pre className="mt-2 max-h-64 overflow-auto text-[10px] font-mono text-zinc-400 whitespace-pre-wrap break-all bg-black/20 rounded p-2 border border-zinc-800/60">
{JSON.stringify(check.details ?? {}, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export default function ReadinessPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastRunAt, setLastRunAt] = useState(null);

  const runCheck = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminReadinessCheck();
      setData(res);
      setLastRunAt(new Date());
    } catch (e) {
      setError(e?.message || 'Failed to run readiness check');
    } finally {
      setLoading(false);
    }
  }, []);

  // Run once on mount so the panel is immediately useful.
  useEffect(() => {
    runCheck();
  }, [runCheck]);

  const overall = data?.overall;
  const overallMeta = overall ? STATUS_META[overall] : null;

  return (
    <div className="asf-section asf-u2-panel space-y-4" data-testid="readiness-panel">
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="asf-section__hd flex items-start justify-between flex-wrap gap-3">
        <div className="asf-legacy-title">
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <ShieldCheck size={20} className="text-accent-primary" weight="bold" />
            System Readiness Check
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-3xl">
            Read-only pre-flight safety panel. Consult before running <span className="font-mono">Auto Factory</span>,
            promoting to a VPS, or enabling live trading. All checks are additive — they never modify state.
          </p>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          {overall && overallMeta && (
            <div data-testid="readiness-overall-badge" className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Overall</span>
              <VerdictBadge verdict={STATUS_VERDICT[overall] || 'neutral'} testId={`readiness-overall-${overall}`}>
                {overallMeta.label}
              </VerdictBadge>
            </div>
          )}
          <button
            data-testid="readiness-run-btn"
            onClick={runCheck}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? (
              <Spinner size={12} className="animate-spin" />
            ) : (
              <ArrowsClockwise size={12} weight="bold" />
            )}
            {loading ? 'Checking…' : 'Run check'}
          </button>
        </div>
      </div>

      {/* ── Error banner ─────────────────────────────────────────── */}
      {error && (
        <AsfEmptyState
          slug="readiness-error"
          testId="readiness-error"
          title="Readiness check failed"
          body={error}
          action={{ label: 'Retry', onClick: runCheck, testId: 'readiness-error-retry' }}
        />
      )}

      {/* ── Loading skeleton ─────────────────────────────────────── */}
      {loading && !data && (
        <div
          data-testid="readiness-loading"
          className="rounded-md border border-zinc-800 bg-[#121821] px-4 py-8 text-center text-xs font-mono text-zinc-500"
        >
          <Spinner size={16} className="inline animate-spin mr-2" /> Running checks…
        </div>
      )}

      {/* ── Checks list ──────────────────────────────────────────── */}
      {data && (
        <div className="space-y-2" data-testid="readiness-checks-list">
          {(data.checks || []).map((c) => (
            <CheckRow key={c.id} check={c} />
          ))}
        </div>
      )}

      {/* ── Footer / meta ────────────────────────────────────────── */}
      {data && (
        <div className="text-[10px] font-mono text-zinc-500 flex items-center gap-4 flex-wrap">
          <span data-testid="readiness-generated-at">
            Generated: {data.generated_at ? new Date(data.generated_at).toLocaleString() : '—'}
          </span>
          {lastRunAt && (
            <span>Last refreshed: {lastRunAt.toLocaleTimeString()}</span>
          )}
        </div>
      )}

      {/* ── Tip ──────────────────────────────────────────────────── */}
      <div className="rounded-md border border-accent-primary/20 bg-accent-primary/5 px-3 py-2 text-[11px] text-zinc-300 flex items-start gap-2">
        <ShieldCheck size={14} className="mt-0.5 text-accent-primary flex-shrink-0" weight="bold" />
        <span>
          <span className="font-semibold">Tip:</span> treat <span className="font-mono text-red-300">Blocked</span> results as hard stops —
          do not run Auto Factory or deploy to a VPS while any check is red.
          <span className="font-mono text-yellow-300"> Warnings</span> are safe to proceed on
          in paper mode, but should be resolved before live trading.
        </span>
      </div>
    </div>
  );
}
