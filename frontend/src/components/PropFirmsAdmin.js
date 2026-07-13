import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ShieldCheck, CheckCircle, XCircle, Warning, CaretDown, CaretRight,
  ArrowsClockwise, Spinner, Plus, MagnifyingGlass,
} from '@phosphor-icons/react';
import RulesReviewPanel, { StatusBadge } from './RulesReviewPanel';
import { API_URL, listPropFirmReviewRules } from '../services/api';
import { AsfKpiTile, AsfEmptyState } from './ui-asf';

/**
 * Prop Firms admin dashboard.
 * Lists every firm with its review/approval status and expands to show
 * the full `RulesReviewPanel` inline (approve / reject / reset in-place).
 * Also surfaces pending parser jobs via /api/prop-firms/extract-jobs.
 */
export default function PropFirmsAdmin({ onOpenAddFirm }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [search, setSearch] = useState('');
  const [jobs, setJobs] = useState([]);
  const [loadingJobs, setLoadingJobs] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await listPropFirmReviewRules();
      setRows(d.rules || []);
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      const API = API_URL;
      const res = await fetch(`${API}/api/prop-firms/extract-jobs?limit=10`);
      const raw = await res.text().catch(() => '');
      let d = {};
      if (raw) { try { d = JSON.parse(raw); } catch { d = {}; } }
      setJobs(d.jobs || []);
    } catch (e) {
      // silent — jobs are informational
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  useEffect(() => { fetchData(); fetchJobs(); }, [fetchData, fetchJobs]);

  // Auto-refresh jobs while any are in-flight
  useEffect(() => {
    const running = jobs.some((j) => j.status === 'queued' || j.status === 'running');
    if (!running) return;
    const id = setInterval(fetchJobs, 3000);
    return () => clearInterval(id);
  }, [jobs, fetchJobs]);

  const counts = useMemo(() => {
    const c = { total: rows.length, approved: 0, parsed: 0, rejected: 0, auto_approved: 0 };
    rows.forEach((r) => {
      const s = r.status || 'parsed';
      if (c[s] !== undefined) c[s] += 1;
      if (r.auto_approved) c.auto_approved += 1;
    });
    return c;
  }, [rows]);

  const filtered = useMemo(() => {
    if (!search.trim()) return rows;
    const q = search.trim().toLowerCase();
    return rows.filter((r) =>
      (r.firm_slug || '').toLowerCase().includes(q) ||
      (r.firm_name || '').toLowerCase().includes(q) ||
      (r.status || '').toLowerCase().includes(q),
    );
  }, [rows, search]);

  const toggle = (slug) => setExpanded((p) => ({ ...p, [slug]: !p[slug] }));

  return (
    <div className="asf-section asf-u2-panel" data-testid="prop-firms-admin">
      {/* Header (legacy title hidden when wrapped by .asf-u2-panel; panel__hd
         already names the section). Refresh / Add CTAs become the action slot. */}
      <div className="asf-section__hd">
        <div className="asf-legacy-title">
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <ShieldCheck size={20} className="text-accent-primary" /> Prop Firms
          </h2>
          <p className="text-xs text-zinc-500 mt-1">
            Review, approve, reject, or reset every prop-firm rule set. Only approved
            firms are used by the analysis &amp; challenge-matching engines.
          </p>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions">
          <button
            data-testid="admin-refresh-btn"
            onClick={() => { fetchData(); fetchJobs(); }}
            disabled={loading}
            className="text-xs font-medium px-3 py-1.5 rounded border border-zinc-700 hover:border-accent-primary/50 hover:text-accent-primary text-zinc-300 bg-[#121821] disabled:opacity-50 flex items-center gap-1.5"
          >
            <ArrowsClockwise size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          {onOpenAddFirm && (
            <button
              data-testid="admin-add-firm-btn"
              onClick={onOpenAddFirm}
              className="text-xs font-medium px-3 py-1.5 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary flex items-center gap-1.5"
            >
              <Plus size={12} /> Add New Firm
            </button>
          )}
        </div>
      </div>

      {/* Stat cards — AsfKpiTile primitive (U-2). */}
      <div className="asf-kpi-grid" data-testid="admin-counts">
        <AsfKpiTile label="Total" value={counts.total} verdict="neutral" />
        <AsfKpiTile label="Approved" value={counts.approved} verdict="success" />
        <AsfKpiTile label="Parsed (pending)" value={counts.parsed} verdict="warn" />
        <AsfKpiTile label="Rejected" value={counts.rejected} verdict="danger" />
      </div>

      {/* Background extract jobs */}
      {jobs.length > 0 && (
        <div className="rounded-md border border-zinc-800 bg-[#121821] p-3" data-testid="admin-jobs">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400">
              Recent extract jobs {loadingJobs && <Spinner size={10} className="animate-spin inline ml-1" />}
            </p>
          </div>
          <div className="space-y-1 text-[11px] font-mono">
            {jobs.slice(0, 5).map((j) => (
              <div
                key={j.job_id}
                className="flex items-center justify-between px-2 py-1 rounded bg-zinc-900/50"
                data-testid={`admin-job-${j.job_id}`}
              >
                <span className="text-zinc-300">
                  {j.firm_name || j.firm_slug}{' '}
                  <span className="text-zinc-500 text-[9px]">· {j.job_id.slice(0, 8)}</span>
                </span>
                <span
                  className={
                    j.status === 'done' ? 'text-emerald-300' :
                    j.status === 'error' ? 'text-red-300' :
                    j.status === 'running' ? 'text-accent-primary' :
                    'text-yellow-300'
                  }
                >
                  {j.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Search */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] p-2 flex items-center gap-2">
        <MagnifyingGlass size={12} className="text-zinc-500 ml-2" />
        <input
          data-testid="admin-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search firm, slug, status…"
          className="flex-1 bg-transparent border-0 text-xs text-zinc-200 focus:outline-none py-1"
        />
      </div>

      {error && (
        <AsfEmptyState
          slug="propfirm-error"
          testId="admin-error"
          title="Couldn’t load prop firms"
          body={error}
          action={{ label: 'Retry', onClick: () => { fetchData(); fetchJobs(); }, testId: 'admin-error-retry' }}
        />
      )}

      {/* Firm list */}
      <div className="space-y-2" data-testid="admin-firm-list">
        {loading && rows.length === 0 && (
          <p className="text-center text-xs font-mono text-zinc-500 py-6">
            <Spinner size={14} className="animate-spin inline mr-2" /> Loading…
          </p>
        )}
        {!loading && filtered.length === 0 && (
          <p className="text-center text-xs font-mono text-zinc-500 py-6" data-testid="admin-empty">
            No firms match.
          </p>
        )}
        {filtered.map((r) => {
          const open = !!expanded[r.firm_slug];
          return (
            <div
              key={r.firm_slug}
              className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden"
              data-testid={`admin-firm-${r.firm_slug}`}
            >
              <button
                onClick={() => toggle(r.firm_slug)}
                data-testid={`admin-firm-toggle-${r.firm_slug}`}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-900/40 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {open ? <CaretDown size={12} className="text-zinc-500" /> : <CaretRight size={12} className="text-zinc-500" />}
                  <div className="text-left">
                    <p className="font-medium text-zinc-200 text-sm">{r.firm_name || r.firm_slug}</p>
                    <p className="text-[9px] font-mono text-zinc-500 mt-0.5">
                      {r.firm_slug}
                      {r.source_type ? ` · ${r.source_type}` : ''}
                      {typeof r.parser_confidence === 'number'
                        ? ` · conf ${(r.parser_confidence * 100).toFixed(0)}%`
                        : ''}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {r.auto_approved && (
                    <span className="text-[9px] font-mono text-zinc-500">auto</span>
                  )}
                  <StatusBadge status={r.status} />
                </div>
              </button>
              {open && (
                <div className="border-t border-zinc-800 p-4">
                  <RulesReviewPanel
                    firmSlug={r.firm_slug}
                    showTitle={false}
                    onChange={() => fetchData()}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
