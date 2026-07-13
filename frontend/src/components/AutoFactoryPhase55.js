/* eslint-disable */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useMarketUniverse } from '../hooks/useMarketUniverse';
import { API_URL } from '../services/api';

// ════════════════════════════════════════════════════════════════════
// Auto Factory — Phase 5.5
//
// Orchestrates the full pipeline via the (already-allow-listed) existing
// /api/auto-factory/* endpoints using the `phase=5.5` discriminator.
//
//   • POST /api/auto-factory/run        { phase:"5.5", ...overrides }
//   • GET  /api/auto-factory/status     ?phase=5.5
//   • POST /api/auto-factory/schedule   { phase:"5.5", enabled, interval_hours }
//   • GET  /api/auto-factory/saved      ?phase=5.5&view=history|config|run_id=...
//   • POST /api/auto-factory/saved      { phase:"5.5", op:"update_config", patch }
// ════════════════════════════════════════════════════════════════════


const AF = `${API_URL}/api/auto-factory`;

const PAIRS_LEGACY = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'US100', 'BTCUSD', 'ETHUSD', 'NAS100'];
const TIMEFRAMES = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1'];
const STYLES = ['trend-following', 'mean-reversion', 'breakout', 'scalping'];
const FIRMS = ['ftmo', 'myforexfunds', 'topstep', 'fundednext', 'the5ers'];

// ─── API thin wrappers ─────────────────────────────────────────────
async function fetchJson(url, opts = {}) {
  const res = await fetch(url, { cache: 'no-store', ...opts });
  const text = await res.text();
  let body;
  try { body = text ? JSON.parse(text) : {}; } catch { body = { raw: text }; }
  if (!res.ok) {
    // Surface the full response body on the Error so callers can render
    // structured failures (e.g. the 412 readiness-gate payload).
    const msg = typeof body?.detail === 'string'
      ? body.detail
      : (body?.detail?.message || `HTTP ${res.status}`);
    const err = new Error(msg);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}
const api = {
  status: () => fetchJson(`${AF}/status?phase=5.5`),
  // Cross-phase status (no phase filter) — reads /api/auto-factory/status
  // which always carries the full run history via the .history field.
  // This is the single source of truth for "Run history" even when no
  // phase=5.5 runs exist yet.
  statusAll: () => fetchJson(`${AF}/status`),
  config: () => fetchJson(`${AF}/saved?phase=5.5&view=config`),
  // Run history now comes from /status.history (not /saved?view=history,
  // which returns an empty `runs:[]` for phase=5.5 until the first 5.5
  // cycle actually runs). We hit /status without the phase filter so the
  // legacy runs surface too.
  history: async (limit = 25) => {
    const s = await fetchJson(`${AF}/status`);
    return { runs: (s.history || []).slice(0, limit) };
  },
  runStrategies: (runId) =>
    fetchJson(`${AF}/saved?run_id=${encodeURIComponent(runId)}&limit=500`),
  run: (overrides = {}, wait = false) =>
    fetchJson(`${AF}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase: '5.5', wait, ...overrides }),
    }),
  toggle: (enabled, interval_hours) =>
    fetchJson(`${AF}/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase: '5.5', enabled, interval_hours }),
    }),
  saveConfig: (patch) =>
    fetchJson(`${AF}/saved`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase: '5.5', op: 'update_config', patch }),
    }),
  testAlert: () =>
    fetchJson(`${AF}/saved`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase: '5.5', op: 'test_alert' }),
    }),
  alertsLog: (limit = 25) =>
    fetchJson(`${AF}/saved`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase: '5.5', op: 'alerts_log', limit }),
    }),
};

// ─── small UI atoms ────────────────────────────────────────────────
function Section({ title, children, action }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-card p-4 md:p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-heading text-sm font-semibold text-zinc-100 uppercase tracking-wider">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

function NumberField({ label, value, onChange, step = 1, min, max, testid }) {
  return (
    <label className="flex flex-col text-xs">
      <span className="text-zinc-400 mb-1">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        data-testid={testid}
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        className="bg-surface-elevated border border-border-subtle rounded px-2 py-1.5 text-sm text-zinc-100 focus:border-accent-primary focus:outline-none"
      />
    </label>
  );
}

function MultiChips({ label, options, value, onChange, testidPrefix }) {
  const toggle = (opt) => {
    const has = value.includes(opt);
    onChange(has ? value.filter((v) => v !== opt) : [...value, opt]);
  };
  return (
    <div>
      <div className="text-xs text-zinc-400 mb-1.5">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = value.includes(o);
          return (
            <button
              key={o}
              type="button"
              data-testid={`${testidPrefix}-${o}`}
              onClick={() => toggle(o)}
              className={`text-[11px] font-mono px-2 py-0.5 rounded border transition-colors ${
                on
                  ? 'bg-accent-primary-soft text-accent-primary border-accent-primary/30'
                  : 'bg-surface-elevated text-zinc-400 border-border-subtle hover:text-zinc-200'
              }`}
            >
              {o}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SelectField({ label, value, onChange, options, testid }) {
  return (
    <label className="flex flex-col text-xs">
      <span className="text-zinc-400 mb-1">{label}</span>
      <select
        value={value}
        data-testid={testid}
        onChange={(e) => onChange(e.target.value)}
        className="bg-surface-elevated border border-border-subtle rounded px-2 py-1.5 text-sm text-zinc-100 focus:border-accent-primary focus:outline-none"
      >
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}

function StepPill({ name, state }) {
  const cfg = {
    pending:  'border-border-subtle text-zinc-500 bg-surface-elevated',
    active:   'border-accent-primary/60 text-accent-primary bg-accent-primary-soft animate-pulse',
    done:     'border-emerald-500/40 text-emerald-400 bg-emerald-500/10',
    error:    'border-red-500/40 text-red-400 bg-red-500/10',
    skipped:  'border-zinc-600 text-zinc-500 bg-surface-elevated italic',
  };
  return (
    <span
      data-testid={`step-${name}-${state}`}
      className={`px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider border rounded ${cfg[state] || cfg.pending}`}
    >
      {name}
    </span>
  );
}

const STEPS = ['data', 'generate', 'mutate', 'validate', 'select', 'store'];

function ProgressRail({ current }) {
  // current can be one of STEPS, or 'init' / 'done'
  const idx = STEPS.indexOf(current);
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="progress-rail">
      {STEPS.map((s, i) => {
        let state = 'pending';
        if (current === 'done') state = 'done';
        else if (idx === -1) state = 'pending';
        else if (i < idx) state = 'done';
        else if (i === idx) state = 'active';
        return <StepPill key={s} name={s} state={state} />;
      })}
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────
export default function AutoFactoryPhase55() {
  // R4 — registry-backed pair list. The legacy hard-coded list was the
  // 7 canonical symbols plus the NAS100 alias; the registry exposes
  // both through alias-aware reads.
  const { options: PAIRS } = useMarketUniverse({ eligibility: 'discovery' });
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Editable draft of the config
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');

  // Toggle state
  const [intervalHours, setIntervalHours] = useState(6);
  const [toggleBusy, setToggleBusy] = useState(false);

  // Run-specific drawer
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [runStrategies, setRunStrategies] = useState([]);
  const [runLoading, setRunLoading] = useState(false);

  // Alerts section
  const [alertsLog, setAlertsLog] = useState([]);
  const [alertTestMsg, setAlertTestMsg] = useState('');
  const [alertTestBusy, setAlertTestBusy] = useState(false);

  // Readiness gate — holds the structured 412 payload when a run is
  // blocked by the pre-flight readiness check.
  const [readinessBlock, setReadinessBlock] = useState(null);

  const pollingRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [st, cfgR, hist, alog] = await Promise.all([
        api.status(),
        api.config(),
        api.history(25),
        api.alertsLog(25).catch(() => ({ alerts: [] })),
      ]);
      setStatus(st);
      setConfig(cfgR.config);
      if (!draft) setDraft(cfgR.config);
      setHistory(hist.runs || []);
      setIntervalHours(cfgR.config.scheduler_interval_hours || 6);
      setAlertsLog(alog.alerts || []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [draft]);

  useEffect(() => { refresh(); }, [refresh]);

  // Live poll when a run is in-flight
  useEffect(() => {
    if (status?.running) {
      if (!pollingRef.current) {
        pollingRef.current = setInterval(async () => {
          try {
            const st = await api.status();
            setStatus(st);
            if (!st.running) {
              clearInterval(pollingRef.current); pollingRef.current = null;
              const [hist] = await Promise.all([api.history(25)]);
              setHistory(hist.runs || []);
            }
          } catch { /* ignore transient */ }
        }, 2500);
      }
    } else if (pollingRef.current) {
      clearInterval(pollingRef.current); pollingRef.current = null;
    }
    return () => { if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; } };
  }, [status?.running]);

  const triggerRun = async () => {
    try {
      setError(null);
      setReadinessBlock(null);
      await api.run({}, false);   // async — poll /status
      await refresh();
    } catch (e) {
      // Detect the structured 412 readiness-gate payload and surface it
      // via a blocking modal instead of a generic error line.
      const detail = e?.body?.detail;
      if (e?.status === 412 && detail && detail.code === 'readiness_blocked') {
        setReadinessBlock(detail);
        return;
      }
      setError(e.message);
    }
  };

  const toggleScheduler = async (enabled) => {
    try {
      setToggleBusy(true); setError(null);
      await api.toggle(enabled, Number(intervalHours) || 6);
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setToggleBusy(false); }
  };

  const saveDraft = async () => {
    if (!draft) return;
    try {
      setSaving(true); setSavedMsg(''); setError(null);
      const cleaned = {
        pairs: draft.pairs,
        timeframes: draft.timeframes,
        styles: draft.styles,
        firm: draft.firm,
        min_pf: Number(draft.min_pf),
        min_runs: Number(draft.min_runs),
        max_drawdown: Number(draft.max_drawdown),
        top_n_store: Number(draft.top_n_store),
        ingestion_max_strategies: Number(draft.ingestion_max_strategies),
        mutation_iterations: Number(draft.mutation_iterations),
        mutation_per_cycle: Number(draft.mutation_per_cycle),
        run_data_maintenance: !!draft.run_data_maintenance,
        run_ingestion: !!draft.run_ingestion,
        run_mutation: !!draft.run_mutation,
        run_validation: !!draft.run_validation,
        run_selection: !!draft.run_selection,
        step_timeout_sec: Number(draft.step_timeout_sec) || 600,
        // ── Alert fields (additive) ─────────────────────────────
        alerts_enabled: !!draft.alerts_enabled,
        webhook_url: draft.webhook_url || '',
        telegram_enabled: !!draft.telegram_enabled,
        telegram_bot_token: draft.telegram_bot_token || '',
        telegram_chat_id: draft.telegram_chat_id || '',
        alert_min_pass_probability: Number(draft.alert_min_pass_probability ?? 0.6),
        alert_min_env_confidence: Number(draft.alert_min_env_confidence ?? 0.6),
        // ── Monitoring → Alerts bridge (Phase 6 × 5.5) ───────────
        monitoring_alerts_enabled: !!draft.monitoring_alerts_enabled,
        alert_on_daily_dd: !!draft.alert_on_daily_dd,
        alert_on_total_dd: !!draft.alert_on_total_dd,
        alert_on_underperformance: !!draft.alert_on_underperformance,
        alert_on_loss_streak: !!draft.alert_on_loss_streak,
      };
      const res = await api.saveConfig(cleaned);
      setConfig(res.config);
      setDraft(res.config);
      setSavedMsg('Saved ✓');
      setTimeout(() => setSavedMsg(''), 2000);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const openRun = async (runId) => {
    setSelectedRunId(runId);
    setRunLoading(true);
    try {
      const r = await api.runStrategies(runId);
      setRunStrategies(r.strategies || []);
    } catch (e) { setError(e.message); }
    finally { setRunLoading(false); }
  };

  const testAlert = async () => {
    try {
      setAlertTestBusy(true); setAlertTestMsg(''); setError(null);
      // Save any pending alert-field edits first so the test uses the
      // currently-visible config.
      if (draft) {
        try {
          await api.saveConfig({
            alerts_enabled: !!draft.alerts_enabled,
            webhook_url: draft.webhook_url || '',
            telegram_enabled: !!draft.telegram_enabled,
            telegram_bot_token: draft.telegram_bot_token || '',
            telegram_chat_id: draft.telegram_chat_id || '',
          });
        } catch { /* non-fatal */ }
      }
      const r = await api.testAlert();
      const sent = !!r?.result?.sent;
      const reason = r?.result?.reason;
      setAlertTestMsg(sent ? 'Alert sent ✓' : `Not sent — ${reason || 'check config'}`);
      const alog = await api.alertsLog(25).catch(() => ({ alerts: [] }));
      setAlertsLog(alog.alerts || []);
      setTimeout(() => setAlertTestMsg(''), 4000);
    } catch (e) { setError(e.message); }
    finally { setAlertTestBusy(false); }
  };

  if (loading) return <div className="p-6 text-sm text-zinc-400" data-testid="af55-loading">Loading Auto Factory…</div>;

  const running = !!status?.running;
  const currentStep = status?.current_run?.progress?.current_step || (running ? 'init' : null);
  const last = status?.last_run;

  return (
    <div className="asf-section asf-u2-panel space-y-5" data-testid="auto-factory-phase55-root">
      {/* ── Header ── */}
      <div className="asf-section__hd flex items-start justify-between flex-wrap gap-4">
        <div className="asf-legacy-title">
          <div className="text-[10px] font-mono text-accent-primary/80 tracking-widest uppercase">Phase 5.5</div>
          <h2 className="font-heading text-2xl font-bold text-zinc-100">Auto Factory Engine</h2>
          <p className="text-xs text-zinc-400 mt-1 max-w-xl">
            Continuous orchestration:&nbsp;
            <span className="font-mono text-zinc-300">Data → Generate → Mutate → Validate → Select → Store</span>.
            Calls existing pipeline APIs only — no engine duplication.
          </p>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <button
            data-testid="af55-run-btn"
            onClick={triggerRun}
            disabled={running}
            className={`px-4 py-2 rounded text-sm font-semibold transition-colors ${
              running
                ? 'bg-surface-elevated text-zinc-500 cursor-not-allowed border border-border-subtle'
                : 'bg-accent-primary text-[#061812] hover:bg-accent-primary-dim'
            }`}
          >
            {running ? 'Running…' : 'Run cycle'}
          </button>
          <button
            data-testid="af55-refresh-btn"
            onClick={refresh}
            className="px-3 py-2 rounded text-xs text-zinc-300 border border-border-subtle hover:bg-surface-elevated"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div data-testid="af55-error" className="text-xs text-red-400 border border-red-500/30 bg-red-500/5 rounded p-2">
          {error}
        </div>
      )}

      {/* ── Live status ── */}
      <Section
        title="Live status"
        action={
          <span
            data-testid="af55-running-badge"
            className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
              running ? 'border-accent-primary/40 text-accent-primary bg-accent-primary-soft'
                      : 'border-border-subtle text-zinc-500 bg-surface-elevated'
            }`}
          >
            {running ? 'RUNNING' : 'IDLE'}
          </span>
        }
      >
        <div className="space-y-3">
          <ProgressRail current={running ? (currentStep || 'init') : 'done'} />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <Stat label="Current run" value={status?.current_run?.run_id?.slice(0, 8) || '—'} testid="af55-curr-runid" />
            <Stat label="Completed steps"
                  value={status?.current_run?.progress
                    ? `${status.current_run.progress.completed}/${status.current_run.progress.total}`
                    : '—'} testid="af55-curr-progress" />
            <Stat label="Last runtime" value={last ? `${last.runtime_sec}s` : '—'} testid="af55-last-runtime" />
            <Stat label="Last stored" value={last ? String(last.stored_count ?? 0) : '—'} testid="af55-last-stored" />
          </div>
          {last && (
            <div className="text-[11px] text-zinc-500 font-mono" data-testid="af55-last-runid">
              Last run: {last.run_id} · {last.status} · finished {new Date(last.finished_at).toLocaleString()}
            </div>
          )}
        </div>
      </Section>

      {/* ── Scheduler toggle ── */}
      <Section title="Continuous mode">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-400">Status:</span>
            <span
              data-testid="af55-sched-status"
              className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                status?.scheduler?.enabled
                  ? 'border-accent-primary/40 text-accent-primary bg-accent-primary-soft'
                  : 'border-border-subtle text-zinc-500 bg-surface-elevated'
              }`}
            >
              {status?.scheduler?.enabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            Interval (hours)
            <input
              type="number" min="0.25" step="0.25" max="168"
              value={intervalHours}
              data-testid="af55-interval-input"
              onChange={(e) => setIntervalHours(Number(e.target.value))}
              className="w-20 bg-surface-elevated border border-border-subtle rounded px-2 py-1 text-sm text-zinc-100"
            />
          </label>
          <button
            data-testid="af55-toggle-on"
            disabled={toggleBusy}
            onClick={() => toggleScheduler(true)}
            className="px-3 py-1.5 rounded text-xs border border-accent-primary/30 text-accent-primary bg-accent-primary-soft hover:bg-accent-primary/20 disabled:opacity-50"
          >
            Enable
          </button>
          <button
            data-testid="af55-toggle-off"
            disabled={toggleBusy}
            onClick={() => toggleScheduler(false)}
            className="px-3 py-1.5 rounded text-xs border border-border-subtle text-zinc-300 hover:bg-surface-elevated disabled:opacity-50"
          >
            Disable
          </button>
          {status?.scheduler?.next_run_at && (
            <span className="text-[11px] text-zinc-500 font-mono" data-testid="af55-next-run">
              Next: {new Date(status.scheduler.next_run_at).toLocaleString()}
            </span>
          )}
        </div>
      </Section>

      {/* ── Config editor ── */}
      {draft && (
        <Section
          title="Configuration"
          action={
            <div className="flex items-center gap-2">
              {savedMsg && <span className="text-[11px] text-emerald-400" data-testid="af55-saved-msg">{savedMsg}</span>}
              <button
                data-testid="af55-save-config-btn"
                onClick={saveDraft}
                disabled={saving}
                className="px-3 py-1.5 rounded text-xs bg-accent-primary text-[#061812] font-semibold hover:bg-accent-primary-dim disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Save config'}
              </button>
            </div>
          }
        >
          <div className="space-y-4">
            <MultiChips label="Pairs" options={PAIRS} value={draft.pairs || []}
              onChange={(v) => setDraft({ ...draft, pairs: v })} testidPrefix="af55-pair" />
            <MultiChips label="Timeframes" options={TIMEFRAMES} value={draft.timeframes || []}
              onChange={(v) => setDraft({ ...draft, timeframes: v })} testidPrefix="af55-tf" />
            <MultiChips label="Styles" options={STYLES} value={draft.styles || []}
              onChange={(v) => setDraft({ ...draft, styles: v })} testidPrefix="af55-style" />

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <SelectField label="Firm" value={draft.firm} options={FIRMS}
                onChange={(v) => setDraft({ ...draft, firm: v })} testid="af55-firm" />
              <NumberField label="Min PF"        value={draft.min_pf}        step={0.05} min={0}
                onChange={(v) => setDraft({ ...draft, min_pf: v })}        testid="af55-min-pf" />
              <NumberField label="Min runs"      value={draft.min_runs}      step={1}    min={1}
                onChange={(v) => setDraft({ ...draft, min_runs: v })}      testid="af55-min-runs" />
              <NumberField label="Max drawdown (fraction)" value={draft.max_drawdown} step={0.01} min={0} max={1}
                onChange={(v) => setDraft({ ...draft, max_drawdown: v })} testid="af55-max-dd" />
              <NumberField label="Top N to store" value={draft.top_n_store}   step={1}    min={1}  max={200}
                onChange={(v) => setDraft({ ...draft, top_n_store: v })}   testid="af55-top-n" />
              <NumberField label="Ingestion / cycle" value={draft.ingestion_max_strategies} step={1} min={1} max={50}
                onChange={(v) => setDraft({ ...draft, ingestion_max_strategies: v })} testid="af55-ing-max" />
              <NumberField label="Mutation iters"  value={draft.mutation_iterations} step={1}    min={0}  max={50}
                onChange={(v) => setDraft({ ...draft, mutation_iterations: v })} testid="af55-mut-iter" />
              <NumberField label="Mut per cycle"   value={draft.mutation_per_cycle}  step={1}    min={1}  max={20}
                onChange={(v) => setDraft({ ...draft, mutation_per_cycle: v })}   testid="af55-mut-percycle" />
              <NumberField label="Step timeout (s)" value={draft.step_timeout_sec}   step={30}   min={30} max={3600}
                onChange={(v) => setDraft({ ...draft, step_timeout_sec: v })}     testid="af55-step-timeout" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 pt-2 border-t border-border-subtle">
              {[
                ['run_data_maintenance', 'Data'],
                ['run_ingestion', 'Generate'],
                ['run_mutation', 'Mutate'],
                ['run_validation', 'Validate'],
                ['run_selection', 'Select'],
              ].map(([k, lbl]) => (
                <label key={k} className="flex items-center gap-2 text-xs text-zinc-300">
                  <input
                    type="checkbox"
                    checked={!!draft[k]}
                    data-testid={`af55-step-${k}`}
                    onChange={(e) => setDraft({ ...draft, [k]: e.target.checked })}
                  />
                  {lbl}
                </label>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* ── Alerts ── */}
      {draft && (
        <Section
          title="Alerts"
          action={
            <div className="flex items-center gap-2">
              {alertTestMsg && (
                <span
                  data-testid="af55-alert-test-msg"
                  className={`text-[11px] ${alertTestMsg.startsWith('Alert sent') ? 'text-emerald-400' : 'text-yellow-400'}`}
                >
                  {alertTestMsg}
                </span>
              )}
              <button
                data-testid="af55-test-alert-btn"
                onClick={testAlert}
                disabled={alertTestBusy}
                className="px-3 py-1.5 rounded text-xs border border-accent-primary/30 text-accent-primary bg-accent-primary-soft hover:bg-accent-primary/20 disabled:opacity-50"
              >
                {alertTestBusy ? 'Testing…' : 'Test alert'}
              </button>
            </div>
          }
        >
          <div className="space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <label className="flex items-center gap-2 text-xs text-zinc-300">
                <input
                  type="checkbox"
                  data-testid="af55-alerts-enabled"
                  checked={!!draft.alerts_enabled}
                  onChange={(e) => setDraft({ ...draft, alerts_enabled: e.target.checked })}
                />
                Alerts enabled
              </label>
              <span className="text-[11px] font-mono text-zinc-500">
                Fires when: PF ≥ {draft.min_pf} · DD ≤ {draft.max_drawdown} · runs ≥ {draft.min_runs} ·
                pass ≥ {draft.alert_min_pass_probability ?? 0.6} · env ≥ {draft.alert_min_env_confidence ?? 0.6}
              </span>
            </div>

            <label className="flex flex-col text-xs">
              <span className="text-zinc-400 mb-1">Webhook URL (primary channel)</span>
              <input
                type="url"
                placeholder="https://hooks.example.com/…"
                data-testid="af55-webhook-url"
                value={draft.webhook_url || ''}
                onChange={(e) => setDraft({ ...draft, webhook_url: e.target.value })}
                className="bg-surface-elevated border border-border-subtle rounded px-2 py-1.5 text-sm text-zinc-100 font-mono focus:border-accent-primary focus:outline-none"
              />
            </label>

            <div className="border-t border-border-subtle pt-3">
              <label className="flex items-center gap-2 text-xs text-zinc-300 mb-2">
                <input
                  type="checkbox"
                  data-testid="af55-telegram-enabled"
                  checked={!!draft.telegram_enabled}
                  onChange={(e) => setDraft({ ...draft, telegram_enabled: e.target.checked })}
                />
                Telegram channel
              </label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="flex flex-col text-xs">
                  <span className="text-zinc-400 mb-1">Bot token</span>
                  <input
                    type="password"
                    placeholder="123456:AA…"
                    data-testid="af55-tg-token"
                    value={draft.telegram_bot_token || ''}
                    onChange={(e) => setDraft({ ...draft, telegram_bot_token: e.target.value })}
                    className="bg-surface-elevated border border-border-subtle rounded px-2 py-1.5 text-sm text-zinc-100 font-mono focus:border-accent-primary focus:outline-none"
                  />
                </label>
                <label className="flex flex-col text-xs">
                  <span className="text-zinc-400 mb-1">Chat ID</span>
                  <input
                    type="text"
                    placeholder="-100…"
                    data-testid="af55-tg-chatid"
                    value={draft.telegram_chat_id || ''}
                    onChange={(e) => setDraft({ ...draft, telegram_chat_id: e.target.value })}
                    className="bg-surface-elevated border border-border-subtle rounded px-2 py-1.5 text-sm text-zinc-100 font-mono focus:border-accent-primary focus:outline-none"
                  />
                </label>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 border-t border-border-subtle pt-3">
              <NumberField
                label="Min pass probability for alert"
                value={draft.alert_min_pass_probability ?? 0.6}
                step={0.05} min={0} max={1}
                onChange={(v) => setDraft({ ...draft, alert_min_pass_probability: v })}
                testid="af55-alert-min-pp"
              />
              <NumberField
                label="Min env confidence for alert"
                value={draft.alert_min_env_confidence ?? 0.6}
                step={0.05} min={0} max={1}
                onChange={(v) => setDraft({ ...draft, alert_min_env_confidence: v })}
                testid="af55-alert-min-ec"
              />
            </div>

            {/* ── Monitoring → Alerts bridge (Phase 6 × 5.5) ─────── */}
            <div className="border-t border-border-subtle pt-3">
              <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                <label className="flex items-center gap-2 text-xs text-zinc-300">
                  <input
                    type="checkbox"
                    data-testid="af55-monitoring-alerts-enabled"
                    checked={!!draft.monitoring_alerts_enabled}
                    onChange={(e) => setDraft({ ...draft, monitoring_alerts_enabled: e.target.checked })}
                  />
                  <span className="font-semibold">Monitoring alerts</span>
                  <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
                    risk / breach events
                  </span>
                </label>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {[
                  ['alert_on_total_dd', 'Total DD breach'],
                  ['alert_on_daily_dd', 'Daily DD breach'],
                  ['alert_on_underperformance', 'Underperformance'],
                  ['alert_on_loss_streak', 'Loss streak'],
                ].map(([k, lbl]) => (
                  <label key={k} className="flex items-center gap-2 text-xs text-zinc-300">
                    <input
                      type="checkbox"
                      data-testid={`af55-${k.replace(/_/g, '-')}`}
                      checked={!!draft[k]}
                      disabled={!draft.monitoring_alerts_enabled}
                      onChange={(e) => setDraft({ ...draft, [k]: e.target.checked })}
                    />
                    {lbl}
                  </label>
                ))}
              </div>
            </div>

            <div className="border-t border-border-subtle pt-3">
              <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-2">
                Recent alerts ({alertsLog.length})
              </div>
              {alertsLog.length === 0 ? (
                <div className="text-xs text-zinc-500 italic" data-testid="af55-alerts-empty">
                  No alerts sent yet. Configure channels above and click "Test alert".
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs" data-testid="af55-alerts-table">
                    <thead>
                      <tr className="text-zinc-500 border-b border-border-subtle">
                        <th className="text-left py-1.5 px-2">Sent</th>
                        <th className="text-left py-1.5 px-2">Env</th>
                        <th className="text-right py-1.5 px-2">PF</th>
                        <th className="text-right py-1.5 px-2">DD</th>
                        <th className="text-right py-1.5 px-2">Pass</th>
                        <th className="text-left py-1.5 px-2">Firm</th>
                        <th className="text-left py-1.5 px-2">Channels</th>
                      </tr>
                    </thead>
                    <tbody>
                      {alertsLog.map((a, i) => {
                        const p = a.payload || {};
                        const chans = (a.channels || [])
                          .map((c) => `${c.channel}${c.ok ? '✓' : '✗'}`)
                          .join(' · ');
                        return (
                          <tr key={`${a.strategy_hash}-${i}`} className="border-b border-border-subtle/50">
                            <td className="py-1.5 px-2 text-zinc-400 font-mono">
                              {a.sent_at ? new Date(a.sent_at).toLocaleString() : '—'}
                            </td>
                            <td className="py-1.5 px-2 text-zinc-200 font-mono">{p.environment || '—'}</td>
                            <td className="py-1.5 px-2 text-right text-zinc-200">{fmt(p.pf)}</td>
                            <td className="py-1.5 px-2 text-right text-zinc-200">{fmt(p.dd)}</td>
                            <td className="py-1.5 px-2 text-right text-zinc-200">{fmt(p.pass_probability)}</td>
                            <td className="py-1.5 px-2 text-zinc-300">{p.firm || '—'}</td>
                            <td className="py-1.5 px-2 text-zinc-300 font-mono">{chans || '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* ── History ── */}
      <Section
        title={`Run history (${history.length})`}
        action={
          <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
            {history.length ? `${history.length} runs` : 'No runs yet'}
          </span>
        }
      >
        {history.length === 0 ? (
          <div className="text-xs text-zinc-500 italic" data-testid="af55-history-empty">
            No runs yet. Click "Run cycle" to start the first orchestration.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="af55-history-table">
              <thead>
                <tr className="text-zinc-500 border-b border-border-subtle">
                  <th className="text-left py-2 px-2 font-medium">Run ID</th>
                  <th className="text-left py-2 px-2 font-medium">Started</th>
                  <th className="text-left py-2 px-2 font-medium">Runtime</th>
                  <th className="text-left py-2 px-2 font-medium">Trigger</th>
                  <th className="text-left py-2 px-2 font-medium">Status</th>
                  <th className="text-right py-2 px-2 font-medium">Selected</th>
                  <th className="text-right py-2 px-2 font-medium">Stored</th>
                  <th className="py-2 px-2"></th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => {
                  // Shape differs depending on source:
                  //   /status.history rows →  totals.{combos_complete,
                  //     combos_errored, strategies_saved, ...}
                  //   legacy /saved?view=history rows → flat
                  //     selected_count / stored_count / status.
                  const t = r.totals || {};
                  const rowStatus = r.status || (
                    t.combos_errored > 0 ? 'errored'
                      : t.combos_complete > 0 ? 'complete'
                      : 'partial'
                  );
                  const selected = r.selected_count
                    ?? t.strategies_returned
                    ?? t.strategies_generated
                    ?? 0;
                  const stored = r.stored_count
                    ?? t.strategies_saved
                    ?? 0;
                  return (
                    <tr key={r.run_id}
                        data-testid={`af55-history-row-${r.run_id}`}
                        className="border-b border-border-subtle/50 hover:bg-surface-elevated/50">
                      <td className="py-2 px-2 font-mono text-zinc-300">{(r.run_id || '').slice(0, 10)}</td>
                      <td className="py-2 px-2 text-zinc-400">{r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                      <td className="py-2 px-2 text-zinc-400">{r.runtime_sec}s</td>
                      <td className="py-2 px-2 text-zinc-400">{r.triggered_by || '—'}</td>
                      <td className="py-2 px-2">
                        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                          rowStatus === 'complete'
                            ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/5'
                            : rowStatus === 'errored'
                            ? 'border-red-500/30 text-red-400 bg-red-500/5'
                            : 'border-yellow-500/30 text-yellow-400 bg-yellow-500/5'
                        }`}>
                          {rowStatus}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right text-zinc-200">{selected}</td>
                      <td className="py-2 px-2 text-right text-zinc-200">{stored}</td>
                      <td className="py-2 px-2 text-right">
                        <button
                          data-testid={`af55-open-run-${r.run_id}`}
                          onClick={() => openRun(r.run_id)}
                          className="text-[11px] text-accent-primary hover:underline"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* ── Selected-strategies drawer ── */}
      {selectedRunId && (
        <Section
          title={`Run ${selectedRunId.slice(0, 10)} — selected strategies`}
          action={
            <button
              data-testid="af55-close-run"
              onClick={() => { setSelectedRunId(null); setRunStrategies([]); }}
              className="text-xs text-zinc-400 hover:text-zinc-200"
            >
              Close
            </button>
          }
        >
          {runLoading ? (
            <div className="text-xs text-zinc-500 italic">Loading…</div>
          ) : runStrategies.length === 0 ? (
            <div className="text-xs text-zinc-500 italic" data-testid="af55-run-empty">
              No strategies stored for this run.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="af55-run-strategies-table">
                <thead>
                  <tr className="text-zinc-500 border-b border-border-subtle">
                    <th className="text-left py-2 px-2">#</th>
                    <th className="text-left py-2 px-2">Pair</th>
                    <th className="text-left py-2 px-2">TF</th>
                    <th className="text-left py-2 px-2">Style</th>
                    <th className="text-right py-2 px-2">PF</th>
                    <th className="text-right py-2 px-2">Runs</th>
                    <th className="text-right py-2 px-2">Max DD</th>
                    <th className="text-right py-2 px-2">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {runStrategies.map((s) => (
                    <tr key={s.rank} className="border-b border-border-subtle/50">
                      <td className="py-1.5 px-2 text-zinc-400">{s.rank}</td>
                      <td className="py-1.5 px-2 text-zinc-200 font-mono">{s.pair || '—'}</td>
                      <td className="py-1.5 px-2 text-zinc-300 font-mono">{s.timeframe || '—'}</td>
                      <td className="py-1.5 px-2 text-zinc-300">{s.style || '—'}</td>
                      <td className="py-1.5 px-2 text-right text-zinc-200">
                        {fmt(s.profit_factor ?? s.metrics?.profit_factor ?? s.pf)}
                      </td>
                      <td className="py-1.5 px-2 text-right text-zinc-200">
                        {s.runs ?? s.total_trades ?? s.metrics?.total_trades ?? '—'}
                      </td>
                      <td className="py-1.5 px-2 text-right text-zinc-200">
                        {fmt(s.max_drawdown ?? s.max_drawdown_pct ?? s.metrics?.max_drawdown_pct)}
                      </td>
                      <td className="py-1.5 px-2 text-right text-zinc-200">
                        {fmt(s.score ?? s.composite_score)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {/* ── Readiness gate modal (non-overridable) ── */}
      {readinessBlock && (
        <div
          data-testid="af55-readiness-block-modal"
          className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="af55-readiness-block-title"
        >
          <div className="w-full max-w-xl rounded-lg border border-red-500/40 bg-[#121821] shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-red-500/30 bg-red-500/10 flex items-start gap-3">
              <div className="w-9 h-9 rounded-full bg-red-500/20 border border-red-500/40 flex items-center justify-center flex-shrink-0">
                <span className="text-red-300 text-lg font-bold">!</span>
              </div>
              <div className="flex-1 min-w-0">
                <h3
                  id="af55-readiness-block-title"
                  className="text-sm font-bold text-red-200"
                  data-testid="af55-readiness-block-title"
                >
                  System is not ready. Fix issues before running Auto Factory.
                </h3>
                <p className="text-[11px] text-red-300/80 mt-0.5">
                  The pre-flight readiness check failed. This block cannot be overridden.
                </p>
              </div>
            </div>
            <div className="px-5 py-4 space-y-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
                Failed checks ({(readinessBlock.failed_checks || []).length})
              </div>
              <ul
                data-testid="af55-readiness-block-list"
                className="space-y-2"
              >
                {(readinessBlock.failed_checks || []).map((c) => (
                  <li
                    key={c.id}
                    data-testid={`af55-readiness-block-item-${c.id}`}
                    className="border border-red-500/25 bg-red-500/5 rounded px-3 py-2"
                  >
                    <div className="text-xs font-semibold text-zinc-100">
                      {c.label || c.id}
                    </div>
                    <div className="mt-0.5 text-[11px] text-zinc-400">{c.summary}</div>
                  </li>
                ))}
              </ul>
              <div className="text-[11px] text-zinc-400 pt-2 border-t border-zinc-800">
                Resolve each red check in the <span className="font-mono text-accent-primary">Admin → System Readiness</span> panel,
                then click <span className="font-mono text-zinc-200">Run cycle</span> again.
              </div>
            </div>
            <div className="px-5 py-3 bg-[#0B0F14] border-t border-zinc-800 flex items-center justify-end gap-2">
              <button
                data-testid="af55-readiness-block-close"
                onClick={() => setReadinessBlock(null)}
                className="text-xs font-semibold px-3 py-1.5 rounded border border-zinc-700 bg-zinc-800/60 hover:bg-zinc-800 text-zinc-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, testid }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</span>
      <span className="text-sm font-mono text-zinc-100" data-testid={testid}>{value}</span>
    </div>
  );
}

function fmt(v) {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (!isFinite(n)) return String(v);
  if (Math.abs(n) >= 100) return n.toFixed(0);
  if (Math.abs(n) >= 10)  return n.toFixed(1);
  return n.toFixed(2);
}
