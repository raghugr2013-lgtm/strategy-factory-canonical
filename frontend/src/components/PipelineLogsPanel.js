import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, CheckCircle2, AlertTriangle, XCircle, Info, Pause, Play,
} from 'lucide-react';
import { getPipelineLogs } from '../services/api';
import { AsfEmptyState } from './ui-asf';

// Phase 14.4 — Pipeline Logs Panel
// Live tail of the pipeline_logs collection. Auto-refresh every 3s.
// Uses the existing log-line-* classes from index.css for coloring.

const REFRESH_MS = 3000;
const LIMIT = 80;

const LEVEL_META = {
  info:    { cls: 'log-line-info',    Icon: Info,           label: 'INFO'    },
  success: { cls: 'log-line-success', Icon: CheckCircle2,   label: 'SUCCESS' },
  warn:    { cls: 'log-line-warn',    Icon: AlertTriangle,  label: 'WARN'    },
  error:   { cls: 'log-line-error',   Icon: XCircle,        label: 'ERROR'   },
};

function _formatTime(iso) {
  if (!iso) return '--:--';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  } catch { return '--:--'; }
}

function LogRow({ log }) {
  const m = LEVEL_META[log.level] || LEVEL_META.info;
  const { Icon } = m;
  return (
    <div
      data-testid={`pipeline-log-row-${log.level}`}
      className={`log-line ${m.cls} items-start`}
    >
      <span className="shrink-0 text-zinc-500 font-mono tabular-nums">
        [{_formatTime(log.ts)}]
      </span>
      <Icon size={12} strokeWidth={2.4} className="mt-[3px] shrink-0" />
      <span className="shrink-0 uppercase tracking-wider font-semibold min-w-[60px]">
        {m.label}
      </span>
      <span className="shrink-0 text-zinc-500 uppercase min-w-[78px]">
        {log.stage}
      </span>
      <span className="flex-1 truncate">{log.message}</span>
      {(log.pair || log.timeframe) && (
        <span className="shrink-0 text-zinc-500">
          {log.pair}{log.pair && log.timeframe ? '·' : ''}{log.timeframe}
        </span>
      )}
    </div>
  );
}

export default function PipelineLogsPanel({ runId = null, compact = false }) {
  const [logs, setLogs] = useState([]);
  const [err, setErr] = useState(null);
  const [paused, setPaused] = useState(false);
  const [levelFilter, setLevelFilter] = useState('all');
  const [stageFilter, setStageFilter] = useState('all');
  const timerRef = useRef(null);

  const fetchOnce = useCallback(async () => {
    try {
      const res = await getPipelineLogs({ limit: LIMIT, run_id: runId || undefined });
      setLogs(res.logs || []);
      setErr(null);
    } catch (e) {
      setErr(e.message || 'Failed to load logs');
    }
  }, [runId]);

  useEffect(() => {
    fetchOnce();
    if (paused) return undefined;
    timerRef.current = setInterval(fetchOnce, REFRESH_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [fetchOnce, paused]);

  const filtered = useMemo(() => {
    return logs.filter((x) =>
      (levelFilter === 'all' || x.level === levelFilter) &&
      (stageFilter === 'all' || x.stage === stageFilter)
    );
  }, [logs, levelFilter, stageFilter]);

  const counts = useMemo(() => {
    const c = { info: 0, success: 0, warn: 0, error: 0 };
    logs.forEach((x) => { if (c[x.level] != null) c[x.level] += 1; });
    return c;
  }, [logs]);

  return (
    <section
      data-testid="pipeline-logs-panel"
      className="asf-section asf-u2-panel card-premium p-4 flex flex-col gap-3"
    >
      {/* Header */}
      <header className="asf-section__hd flex items-center justify-between gap-3 flex-wrap">
        <div className="asf-legacy-title flex items-center gap-2.5">
          <span className="inline-flex w-7 h-7 rounded-md bg-accent-primary-soft border border-accent-primary/20 items-center justify-center text-accent-primary">
            <Activity size={14} />
          </span>
          <div>
            <h3 className="font-heading text-sm font-semibold text-white tracking-tight">
              Pipeline Logs
            </h3>
            <p className="text-[11px] font-mono text-zinc-500 mt-0.5">
              {runId
                ? <>Run · <span className="text-accent-primary">{runId}</span></>
                : <>Live tail · refresh {REFRESH_MS/1000}s</>}
            </p>
          </div>
        </div>

        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <div className="hidden md:flex items-center gap-1 text-[10px] font-mono">
            <span className="px-1.5 py-0.5 rounded border border-border-subtle text-zinc-400">
              i {counts.info}
            </span>
            <span className="px-1.5 py-0.5 rounded border border-accent-primary/30 bg-accent-primary-soft text-accent-primary">
              ✓ {counts.success}
            </span>
            <span className="px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/5 text-amber-300">
              ! {counts.warn}
            </span>
            <span className="px-1.5 py-0.5 rounded border border-rose-500/30 bg-rose-500/5 text-rose-300">
              × {counts.error}
            </span>
          </div>

          {/* Filters */}
          <select
            data-testid="logs-level-filter"
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="bg-surface-sunken border border-border-subtle text-zinc-200 rounded-md px-2 py-1 text-[11px] font-mono focus:outline-none focus:border-accent-primary/50"
          >
            <option value="all">all levels</option>
            <option value="info">info</option>
            <option value="success">success</option>
            <option value="warn">warn</option>
            <option value="error">error</option>
          </select>
          <select
            data-testid="logs-stage-filter"
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="bg-surface-sunken border border-border-subtle text-zinc-200 rounded-md px-2 py-1 text-[11px] font-mono focus:outline-none focus:border-accent-primary/50"
          >
            <option value="all">all stages</option>
            <option value="generation">generation</option>
            <option value="backtest">backtest</option>
            <option value="validation">validation</option>
            <option value="mutation">mutation</option>
            <option value="save">save</option>
            <option value="auto_save">auto_save</option>
          </select>

          <button
            data-testid="logs-pause-toggle"
            onClick={() => setPaused((p) => !p)}
            title={paused ? 'Resume live tail' : 'Pause live tail'}
            className="btn-ghost"
          >
            {paused ? <><Play size={12}/> Paused</> : <><Pause size={12}/> Live</>}
          </button>
        </div>
      </header>

      {err && (
        <AsfEmptyState
          slug="pipeline-logs-error"
          testId="pipeline-logs-error"
          title="Log tail failed"
          body={err}
        />
      )}

      {/* Body */}
      <div
        data-testid="pipeline-logs-body"
        className={`flex flex-col gap-1.5 overflow-y-auto pr-1 ${
          compact ? 'max-h-[260px]' : 'max-h-[420px]'
        }`}
      >
        {filtered.length === 0 ? (
          <div className="text-[11px] font-mono text-zinc-500 py-6 text-center">
            No log entries yet. Start a pipeline run — events will stream here live.
          </div>
        ) : (
          filtered.map((log, i) => (
            <LogRow key={`${log.ts}-${i}`} log={log} />
          ))
        )}
      </div>
    </section>
  );
}
