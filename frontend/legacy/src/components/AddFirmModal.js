import React, { useRef, useState } from 'react';
import {
  CircleNotch, Lightning, Upload, CheckCircle, Warning, Trash, Plus,
} from '@phosphor-icons/react';
import {
  extractPropFirm, savePropFirm,
  discoverChallenges, saveChallenges,
} from '../services/api';
import RulesReviewPanel from './RulesReviewPanel';

/**
 * Add New Firm Modal — unified Phase 2 + Phase 3.
 *
 *  Step 1 — Firm basics (name, URL, PDF, optional challenge_size)
 *  Step 2 — Two actions:
 *             • EXTRACT RULES (Phase 2): single-challenge config
 *             • DISCOVER CHALLENGES (Phase 3): multi-plan discovery
 *           Both can be run independently and their results shown together.
 *  Step 3 — Each result section has its own editor + Save button.
 *             Phase 2 saves a single firm config.
 *             Phase 3 saves every plan as its own firm entry in the dropdown.
 */
export default function AddFirmModal({ open, onClose, onSaved }) {
  // Shared inputs
  const [firmName, setFirmName] = useState('');
  const [website, setWebsite] = useState('');
  const [challengeSize, setChallengeSize] = useState(100000);
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfError, setPdfError] = useState(null);

  // Phase 2 state
  const [extracting, setExtracting] = useState(false);
  const [savingRules, setSavingRules] = useState(false);
  const [rulesError, setRulesError] = useState(null);
  const [extractPreview, setExtractPreview] = useState(null);
  const [editedRules, setEditedRules] = useState(null);

  // Phase 3 state
  const [discovering, setDiscovering] = useState(false);
  const [savingPlans, setSavingPlans] = useState(false);
  const [discoverError, setDiscoverError] = useState(null);
  const [discoverPreview, setDiscoverPreview] = useState(null);
  const [plans, setPlans] = useState([]);
  const [mirrorRules, setMirrorRules] = useState(true);

  // Shared
  const [topError, setTopError] = useState(null);
  const fileInputRef = useRef();

  const resetAll = () => {
    setFirmName(''); setWebsite(''); setChallengeSize(100000);
    setPdfFile(null); setPdfError(null);
    setExtracting(false); setSavingRules(false); setRulesError(null);
    setExtractPreview(null); setEditedRules(null);
    setDiscovering(false); setSavingPlans(false); setDiscoverError(null);
    setDiscoverPreview(null); setPlans([]); setMirrorRules(true);
    setTopError(null);
  };
  const handleClose = () => { resetAll(); onClose?.(); };

  const handlePdfSelect = (e) => {
    const f = e.target.files?.[0];
    setPdfError(null);
    if (!f) { setPdfFile(null); return; }
    if (f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) {
      setPdfError('File must be a PDF.'); return;
    }
    if (f.size > 5 * 1024 * 1024) {
      setPdfError('PDF must be ≤ 5 MB.'); return;
    }
    setPdfFile(f);
  };

  // ── Phase 2: Extract single config ─────────────────────────────
  const handleExtract = async () => {
    setTopError(null); setRulesError(null);
    if (!firmName.trim()) return setTopError('Firm name is required.');
    if (!website && !pdfFile) return setTopError('Provide a website URL or upload a PDF.');
    if (!challengeSize || Number(challengeSize) < 1000) {
      return setTopError('Challenge size must be ≥ 1000 for Extract Rules.');
    }
    setExtracting(true);
    try {
      const data = await extractPropFirm({
        firm_name: firmName.trim(),
        challenge_size: Number(challengeSize),
        website_url: website || undefined,
        pdf: pdfFile || undefined,
      });
      setExtractPreview(data);
      const ex = data.extracted || {};
      setEditedRules({
        // CORE
        max_total_drawdown: ex.max_total_drawdown?.value ?? '',
        max_daily_drawdown: ex.max_daily_drawdown?.value ?? '',
        profit_target: ex.profit_target?.value ?? '',
        // OPTIONAL — min_trading_days + consistency can be populated by the
        // extractor; the rest (news, lot, scaling) always start disabled.
        min_trading_days_enabled: (ex.min_trading_days?.value ?? 0) > 0,
        min_trading_days: ex.min_trading_days?.value ?? '',
        consistency_enabled:
          ex.consistency_rules?.value?.max_daily_profit_pct != null,
        consistency_pct: ex.consistency_rules?.value?.max_daily_profit_pct ?? '',
        news_enabled: false,
        news_blackout_minutes: '',
        lot_enabled: false,
        lot_max_per_trade: '',
        lot_max_total: '',
        scaling_enabled: false,
        scaling_threshold_dd_pct: 5.0,
        scaling_risk_multiplier: 0.5,
        // Metadata
        fees: ex.fees?.value ?? '',
      });
    } catch (e) {
      setRulesError(e.message || 'Extraction failed');
    } finally {
      setExtracting(false);
    }
  };

  const handleSaveRules = async () => {
    if (!editedRules) return;
    setRulesError(null); setSavingRules(true);
    try {
      // Build the save payload — CORE fields are always sent as raw
      // numbers; OPTIONAL fields are sent as toggled objects so the
      // backend can honour enabled=true/false per the new schema.
      const payload = {
        firm_name: firmName.trim(),
        website: website || null,
        challenge_size: Number(challengeSize),
        rules: {
          // CORE (required)
          max_total_drawdown: toNum(editedRules.max_total_drawdown),
          max_daily_drawdown: toNum(editedRules.max_daily_drawdown),
          profit_target: toNum(editedRules.profit_target),
          // OPTIONAL (toggle-based)
          min_trading_days: {
            enabled: !!editedRules.min_trading_days_enabled,
            days: editedRules.min_trading_days_enabled
              ? (toInt(editedRules.min_trading_days) ?? 0) : 0,
          },
          consistency_rule: {
            enabled: !!editedRules.consistency_enabled,
            max_daily_profit_pct: editedRules.consistency_enabled
              ? toNum(editedRules.consistency_pct) : null,
          },
          news_restriction: {
            enabled: !!editedRules.news_enabled,
            blackout_minutes: editedRules.news_enabled
              ? (toInt(editedRules.news_blackout_minutes) ?? null) : null,
          },
          lot_size_limit: {
            enabled: !!editedRules.lot_enabled,
            max_lot_per_trade: editedRules.lot_enabled
              ? toNum(editedRules.lot_max_per_trade) : null,
            max_total_exposure: editedRules.lot_enabled
              ? toNum(editedRules.lot_max_total) : null,
          },
          scaling_rule: {
            enabled: !!editedRules.scaling_enabled,
            type: 'risk_reduction',
            threshold_dd_pct: editedRules.scaling_enabled
              ? toNum(editedRules.scaling_threshold_dd_pct) : null,
            risk_multiplier: editedRules.scaling_enabled
              ? toNum(editedRules.scaling_risk_multiplier) : null,
          },
          fees: toNum(editedRules.fees),
          confidence_score: extractPreview?.confidence ?? null,
        },
        extraction_meta: extractPreview ? {
          confidence: extractPreview.confidence,
          sources_used: extractPreview.sources_used,
          missing_fields: extractPreview.missing_fields,
          website_meta: extractPreview.website_meta,
          pdf_meta: extractPreview.pdf_meta,
        } : null,
        pdf_path: extractPreview?.pdf_path || null,
      };
      if (payload.rules.max_total_drawdown == null) throw new Error('Max total drawdown is required.');
      if (payload.rules.max_daily_drawdown == null) throw new Error('Max daily drawdown is required.');
      if (payload.rules.profit_target == null) throw new Error('Profit target is required.');
      const res = await savePropFirm(payload);
      onSaved?.({ kind: 'rules', config: res.config });
      handleClose();
    } catch (e) {
      setRulesError(e.message || 'Save failed');
    } finally {
      setSavingRules(false);
    }
  };

  // ── Phase 3: Discover multi-plan challenges ────────────────────
  const handleDiscover = async () => {
    setTopError(null); setDiscoverError(null);
    if (!firmName.trim()) return setTopError('Firm name is required.');
    if (!website && !pdfFile) return setTopError('Provide a website URL or upload a PDF.');
    setDiscovering(true);
    try {
      const data = await discoverChallenges({
        firm_name: firmName.trim(),
        website_url: website || undefined,
        pdf: pdfFile || undefined,
      });
      setDiscoverPreview(data);
      const rows = (data.challenges || []).map((c) => ({
        account_size: c.account_size,
        type: c.type || 'unknown',
        fee: c.fee ?? '',
        profit_target: c.rules?.profit_target ?? '',
        profit_target_phase2: c.rules?.profit_target_phase2 ?? '',
        max_total_drawdown: c.rules?.max_total_drawdown ?? '',
        max_daily_drawdown: c.rules?.max_daily_drawdown ?? '',
        min_trading_days: c.rules?.min_trading_days ?? '',
        confidence: c.confidence ?? 0,
        source: c.source ?? 'manual',
      }));
      setPlans(rows);
    } catch (e) {
      setDiscoverError(e.message || 'Discovery failed');
    } finally {
      setDiscovering(false);
    }
  };

  const updatePlan = (i, field, val) => {
    const next = [...plans]; next[i] = { ...next[i], [field]: val }; setPlans(next);
  };
  const addPlan = () => {
    setPlans([...plans, {
      account_size: 10000, type: 'unknown', fee: '',
      profit_target: '', profit_target_phase2: '',
      max_total_drawdown: '', max_daily_drawdown: '',
      min_trading_days: '', confidence: 0, source: 'manual',
    }]);
  };
  const removePlan = (i) => setPlans(plans.filter((_, idx) => idx !== i));

  const handleSavePlans = async () => {
    setDiscoverError(null);
    if (!plans.length) return setDiscoverError('Add at least one challenge plan.');
    for (const p of plans) {
      if (!p.account_size || Number(p.account_size) < 1000) {
        return setDiscoverError(`Each plan needs account_size ≥ 1000 (found ${p.account_size}).`);
      }
    }
    setSavingPlans(true);
    try {
      const payload = {
        firm_name: firmName.trim(),
        website: website || null,
        mirror_to_rules: mirrorRules,
        challenges: plans.map((p) => ({
          account_size: parseInt(p.account_size, 10),
          type: p.type || 'unknown',
          fee: toNum(p.fee),
          rules: {
            profit_target: toNum(p.profit_target),
            profit_target_phase2: toNum(p.profit_target_phase2),
            max_total_drawdown: toNum(p.max_total_drawdown),
            max_daily_drawdown: toNum(p.max_daily_drawdown),
            min_trading_days: toInt(p.min_trading_days),
          },
          confidence: p.confidence ?? 0,
          source: p.source ?? 'manual',
        })),
        discovery_meta: discoverPreview ? {
          sources_used: discoverPreview.sources_used,
          pages: discoverPreview.pages,
          crawl_meta: discoverPreview.crawl_meta,
        } : null,
      };
      const res = await saveChallenges(payload);
      onSaved?.({ kind: 'plans', result: res });
      handleClose();
    } catch (e) {
      setDiscoverError(e.message || 'Save failed');
    } finally {
      setSavingPlans(false);
    }
  };

  if (!open) return null;

  const inputCls = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-zinc-600 focus:border-zinc-600 focus:outline-none";
  const labelCls = "text-[10px] font-medium text-zinc-400 uppercase tracking-wider";
  const cellCls = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-2 py-1 text-[11px] font-mono focus:ring-1 focus:ring-zinc-600 focus:border-zinc-600 focus:outline-none w-full";

  return (
    <div
      data-testid="add-firm-modal"
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={handleClose}
    >
      <div
        className="bg-surface-card border border-zinc-800 rounded-lg w-full max-w-5xl max-h-[92vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-surface-card border-b border-zinc-800 px-5 py-3 flex items-center justify-between z-10">
          <div>
            <h3 className="text-sm font-semibold text-white">Add New Prop Firm</h3>
            <p className="text-[10px] font-mono text-zinc-500 mt-0.5">
              Single config (Phase 2) or full multi-plan discovery (Phase 3) — run either or both
            </p>
          </div>
          <button
            data-testid="modal-close-btn"
            onClick={handleClose}
            className="text-zinc-400 hover:text-white text-xs font-mono uppercase"
          >
            Close
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* ── STEP 1 — Firm basics ───────────────────────────── */}
          <section className="space-y-3">
            <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">1. Firm details</h4>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className={labelCls}>Firm name *</label>
                <input
                  data-testid="firm-name-input"
                  value={firmName}
                  onChange={(e) => setFirmName(e.target.value)}
                  placeholder="e.g. FTMO, MyFundedFX"
                  className={`${inputCls} w-full`}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Website URL (rules / challenges page)</label>
                <input
                  data-testid="firm-website-input"
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                  placeholder="https://example-propfirm.com/challenges"
                  className={`${inputCls} w-full`}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className={labelCls}>Challenge size ($) — required for Extract Rules only</label>
                <input
                  data-testid="challenge-size-input"
                  type="number"
                  min={1000}
                  step={1000}
                  value={challengeSize}
                  onChange={(e) => setChallengeSize(e.target.value)}
                  className={`${inputCls} w-full`}
                />
              </div>

              <div className="space-y-1">
                <label className={labelCls}>Rules / challenges PDF (optional, ≤ 5 MB)</label>
                <div className="flex items-center gap-2">
                  <button
                    data-testid="pdf-upload-btn"
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex-1 inline-flex items-center gap-2 bg-zinc-950 border border-zinc-800 text-zinc-200 hover:border-zinc-600 rounded-md px-2.5 py-1.5 text-xs font-mono"
                  >
                    <Upload size={12} weight="bold" />
                    {pdfFile ? pdfFile.name.slice(0, 28) : 'Choose PDF'}
                  </button>
                  {pdfFile && (
                    <button
                      onClick={() => setPdfFile(null)}
                      className="text-[10px] font-mono text-zinc-500 hover:text-red-400"
                    >
                      clear
                    </button>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="hidden"
                  onChange={handlePdfSelect}
                  data-testid="pdf-file-input"
                />
                {pdfError && <p data-testid="pdf-error" className="text-[10px] font-mono text-red-400">{pdfError}</p>}
              </div>
            </div>

            {topError && (
              <div data-testid="modal-error" className="text-[11px] font-mono text-red-400 bg-red-950/40 border border-red-900/60 rounded p-2">
                {topError}
              </div>
            )}

            <div className="flex items-center gap-2 pt-1">
              <button
                data-testid="extract-btn"
                onClick={handleExtract}
                disabled={extracting}
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-white text-black hover:bg-zinc-200 disabled:bg-zinc-700 disabled:text-zinc-500 rounded-md transition-colors"
              >
                {extracting ? (
                  <><CircleNotch size={14} weight="bold" className="animate-spin" /> Extracting…</>
                ) : (
                  <><Lightning size={14} weight="fill" /> Extract Rules</>
                )}
              </button>
              <button
                data-testid="discover-btn"
                onClick={handleDiscover}
                disabled={discovering}
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-cyan-500/20 text-cyan-200 border border-cyan-500/40 hover:bg-cyan-500/30 disabled:bg-zinc-800 disabled:text-zinc-500 rounded-md transition-colors"
              >
                {discovering ? (
                  <><CircleNotch size={14} weight="bold" className="animate-spin" /> Crawling…</>
                ) : (
                  <><Lightning size={14} weight="fill" /> Discover Challenges</>
                )}
              </button>
              <span className="text-[10px] font-mono text-zinc-500 ml-2">
                Extract = single config · Discover = multi-plan (each plan becomes its own firm entry)
              </span>
            </div>
          </section>

          {/* ── STEP 2a — Phase 2 preview (single config) ──────── */}
          {extractPreview && editedRules && (
            <section className="space-y-3 pt-2 border-t border-zinc-800">
              <div className="flex items-center justify-between">
                <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  2a. Extracted rules (single config)
                </h4>
                <ConfidenceBadge confidence={extractPreview.confidence} missing={extractPreview.missing_fields} />
              </div>

              <p className="text-[10px] font-mono text-zinc-500" data-testid="sources-used">
                Sources: <span className="text-zinc-300">{(extractPreview.sources_used || []).join(' + ') || 'none'}</span>
                {extractPreview.website_meta?.method && extractPreview.website_meta.method !== 'none' && (
                  <> · web via <span className="text-zinc-300">{extractPreview.website_meta.method}</span></>
                )}
                {extractPreview.pdf_meta?.pages > 0 && (
                  <> · pdf <span className="text-zinc-300">{extractPreview.pdf_meta.pages}p</span></>
                )}
              </p>

              <div className="space-y-4">
                {/* ── CORE rules (always enforced) ─── */}
                <div data-testid="core-rules-section">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-300">Core rules</span>
                    <span className="text-[9px] font-mono text-zinc-500">always enforced</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <EditField label="Max total drawdown (%)" testId="edit-max-total-dd"
                      value={editedRules.max_total_drawdown}
                      onChange={(v) => setEditedRules({ ...editedRules, max_total_drawdown: v })}
                      source={extractPreview.extracted?.max_total_drawdown?.source} />
                    <EditField label="Max daily drawdown (%)" testId="edit-max-daily-dd"
                      value={editedRules.max_daily_drawdown}
                      onChange={(v) => setEditedRules({ ...editedRules, max_daily_drawdown: v })}
                      source={extractPreview.extracted?.max_daily_drawdown?.source} />
                    <EditField label="Profit target (%)" testId="edit-profit-target"
                      value={editedRules.profit_target}
                      onChange={(v) => setEditedRules({ ...editedRules, profit_target: v })}
                      source={extractPreview.extracted?.profit_target?.source} />
                    <div className="flex flex-col gap-1" data-testid="edit-reset-time">
                      <label className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">Daily reset</label>
                      <div className="h-8 px-2 flex items-center text-[11px] font-mono text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded">
                        17:00 America/New_York
                      </div>
                      <span className="text-[9px] font-mono text-zinc-500">read-only (broker-day anchor)</span>
                    </div>
                  </div>
                </div>

                {/* ── OPTIONAL rules (toggle-based) ── */}
                <div data-testid="optional-rules-section" className="pt-2 border-t border-zinc-800">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-amber-300">Optional rules</span>
                    <span className="text-[9px] font-mono text-zinc-500">off by default · enable to enforce</span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <OptionalRule
                      testId="opt-min-trading-days"
                      label="Min trading days"
                      enabled={!!editedRules.min_trading_days_enabled}
                      onToggle={(v) => setEditedRules({ ...editedRules, min_trading_days_enabled: v })}
                    >
                      <EditField label="Days" testId="edit-min-days"
                        value={editedRules.min_trading_days}
                        onChange={(v) => setEditedRules({ ...editedRules, min_trading_days: v })} />
                    </OptionalRule>

                    <OptionalRule
                      testId="opt-consistency-rule"
                      label="Consistency rule"
                      enabled={!!editedRules.consistency_enabled}
                      onToggle={(v) => setEditedRules({ ...editedRules, consistency_enabled: v })}
                    >
                      <EditField label="Max daily profit (%)" testId="edit-consistency"
                        value={editedRules.consistency_pct}
                        onChange={(v) => setEditedRules({ ...editedRules, consistency_pct: v })} />
                    </OptionalRule>

                    <OptionalRule
                      testId="opt-news-restriction"
                      label="News restriction"
                      enabled={!!editedRules.news_enabled}
                      onToggle={(v) => setEditedRules({ ...editedRules, news_enabled: v })}
                      hint="Stored only — not enforced by engine yet"
                    >
                      <EditField label="Blackout (minutes)" testId="edit-news-blackout"
                        value={editedRules.news_blackout_minutes}
                        onChange={(v) => setEditedRules({ ...editedRules, news_blackout_minutes: v })} />
                    </OptionalRule>

                    <OptionalRule
                      testId="opt-lot-size-limit"
                      label="Lot size limit"
                      enabled={!!editedRules.lot_enabled}
                      onToggle={(v) => setEditedRules({ ...editedRules, lot_enabled: v })}
                    >
                      <EditField label="Max lot/trade" testId="edit-lot-per-trade"
                        value={editedRules.lot_max_per_trade}
                        onChange={(v) => setEditedRules({ ...editedRules, lot_max_per_trade: v })} />
                      <EditField label="Max total exposure" testId="edit-lot-total"
                        value={editedRules.lot_max_total}
                        onChange={(v) => setEditedRules({ ...editedRules, lot_max_total: v })} />
                    </OptionalRule>

                    <OptionalRule
                      testId="opt-scaling-rule"
                      label="Scaling rule (risk reduction)"
                      enabled={!!editedRules.scaling_enabled}
                      onToggle={(v) => setEditedRules({ ...editedRules, scaling_enabled: v })}
                    >
                      <EditField label="Threshold DD (%)" testId="edit-scaling-threshold"
                        value={editedRules.scaling_threshold_dd_pct}
                        onChange={(v) => setEditedRules({ ...editedRules, scaling_threshold_dd_pct: v })} />
                      <EditField label="Risk multiplier" testId="edit-scaling-multiplier"
                        value={editedRules.scaling_risk_multiplier}
                        onChange={(v) => setEditedRules({ ...editedRules, scaling_risk_multiplier: v })} />
                    </OptionalRule>

                    <OptionalRule
                      testId="opt-fees"
                      label="Challenge fee (USD)"
                      enabled={editedRules.fees !== '' && editedRules.fees != null}
                      onToggle={(v) => setEditedRules({ ...editedRules, fees: v ? (editedRules.fees || 0) : '' })}
                    >
                      <EditField label="Fee ($)" testId="edit-fees"
                        value={editedRules.fees}
                        onChange={(v) => setEditedRules({ ...editedRules, fees: v })}
                        source={extractPreview.extracted?.fees?.source} />
                    </OptionalRule>
                  </div>
                </div>
              </div>

              {rulesError && (
                <div data-testid="modal-error-save" className="text-[11px] font-mono text-red-400 bg-red-950/40 border border-red-900/60 rounded p-2">
                  {rulesError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  data-testid="save-firm-btn"
                  onClick={handleSaveRules}
                  disabled={savingRules}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30 disabled:opacity-50 disabled:cursor-wait rounded-md transition-colors"
                >
                  {savingRules ? (
                    <><CircleNotch size={14} weight="bold" className="animate-spin" /> Saving…</>
                  ) : (
                    <><CheckCircle size={14} weight="fill" /> Save single config</>
                  )}
                </button>
              </div>
            </section>
          )}

          {/* ── REVIEW & APPROVAL (Phase 20) — shown when extract ran ── */}
          {extractPreview?.firm_slug && (
            <section className="space-y-2 pt-2 border-t border-zinc-800" data-testid="review-approval-section">
              <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                Review & Approve
              </h4>
              <RulesReviewPanel firmSlug={extractPreview.firm_slug} showTitle={false} />
              <p className="text-[10px] font-mono text-zinc-500">
                The extraction pipeline has persisted the parsed rules.
                Approve here to unlock prop-firm analysis and challenge matching.
              </p>
            </section>
          )}

          {/* ── STEP 2b — Phase 3 preview (multi-plan table) ──── */}
          {discoverPreview && (
            <section className="space-y-2 pt-2 border-t border-zinc-800">
              <div className="flex items-center justify-between">
                <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  2b. Detected challenges ({plans.length})
                </h4>
                <button
                  data-testid="disc-add-plan"
                  onClick={addPlan}
                  className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-white border border-zinc-800 hover:border-zinc-700 rounded px-2 py-1"
                >
                  <Plus size={10} weight="bold" /> Add row
                </button>
              </div>

              <div data-testid="disc-summary" className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono">
                <SummaryCell label="Pages crawled" value={discoverPreview.crawl_meta?.pages_crawled ?? 0} />
                <SummaryCell label="Regex hits" value={discoverPreview.crawl_meta?.regex_hits ?? 0} color="text-emerald-400" />
                <SummaryCell label="LLM hits" value={discoverPreview.crawl_meta?.llm_hits ?? 0} color="text-cyan-400" />
                <SummaryCell label="Sources" value={(discoverPreview.sources_used || []).join(' + ') || '—'} />
              </div>

              {plans.length === 0 ? (
                <div data-testid="disc-empty" className="text-[11px] font-mono text-zinc-500 bg-zinc-900/60 border border-zinc-800 rounded p-4 text-center">
                  No plans detected. Add one manually or try a different URL/PDF.
                </div>
              ) : (
                <div className="overflow-x-auto" data-testid="disc-plans-table">
                  <table className="w-full text-[11px] font-mono">
                    <thead className="text-zinc-500 uppercase text-[9px] tracking-wider">
                      <tr>
                        <th className="text-left py-1 pr-2">Size ($)</th>
                        <th className="text-left py-1 pr-2">Type</th>
                        <th className="text-left py-1 pr-2">Fee ($)</th>
                        <th className="text-left py-1 pr-2">Target%</th>
                        <th className="text-left py-1 pr-2">P2 Target%</th>
                        <th className="text-left py-1 pr-2">Total DD%</th>
                        <th className="text-left py-1 pr-2">Daily DD%</th>
                        <th className="text-left py-1 pr-2">Min d</th>
                        <th className="text-left py-1 pr-2">Src</th>
                        <th className="text-left py-1 pr-2">Conf</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {plans.map((p, i) => (
                        <tr key={i} data-testid={`disc-plan-row-${i}`} className="border-t border-zinc-900">
                          <td className="pr-1 py-1"><input type="number" min={1000} step={1000} value={p.account_size}
                            onChange={(e) => updatePlan(i, 'account_size', e.target.value)}
                            className={cellCls} data-testid={`disc-size-${i}`} /></td>
                          <td className="pr-1 py-1">
                            <select value={p.type} onChange={(e) => updatePlan(i, 'type', e.target.value)}
                              className={cellCls} data-testid={`disc-type-${i}`}>
                              <option value="1-step">1-step</option>
                              <option value="2-step">2-step</option>
                              <option value="instant">instant</option>
                              <option value="unknown">unknown</option>
                            </select>
                          </td>
                          <td className="pr-1 py-1"><input type="number" step="any" value={p.fee}
                            onChange={(e) => updatePlan(i, 'fee', e.target.value)}
                            className={cellCls} data-testid={`disc-fee-${i}`} /></td>
                          <td className="pr-1 py-1"><input type="number" step="any" value={p.profit_target}
                            onChange={(e) => updatePlan(i, 'profit_target', e.target.value)}
                            className={cellCls} data-testid={`disc-target-${i}`} /></td>
                          <td className="pr-1 py-1"><input type="number" step="any" value={p.profit_target_phase2}
                            onChange={(e) => updatePlan(i, 'profit_target_phase2', e.target.value)}
                            className={cellCls} data-testid={`disc-p2-${i}`} /></td>
                          <td className="pr-1 py-1"><input type="number" step="any" value={p.max_total_drawdown}
                            onChange={(e) => updatePlan(i, 'max_total_drawdown', e.target.value)}
                            className={cellCls} data-testid={`disc-tdd-${i}`} /></td>
                          <td className="pr-1 py-1"><input type="number" step="any" value={p.max_daily_drawdown}
                            onChange={(e) => updatePlan(i, 'max_daily_drawdown', e.target.value)}
                            className={cellCls} data-testid={`disc-ddd-${i}`} /></td>
                          <td className="pr-1 py-1"><input type="number" step="1" value={p.min_trading_days}
                            onChange={(e) => updatePlan(i, 'min_trading_days', e.target.value)}
                            className={cellCls} data-testid={`disc-days-${i}`} /></td>
                          <td className="pr-1 py-1 whitespace-nowrap">
                            <span className={p.source === 'regex' ? 'text-emerald-400' : p.source === 'llm' ? 'text-cyan-400' : 'text-zinc-500'}>{p.source}</span>
                          </td>
                          <td className="pr-1 py-1">
                            <span className={p.confidence >= 75 ? 'text-emerald-400' : p.confidence >= 50 ? 'text-amber-400' : 'text-red-400'}>{p.confidence}%</span>
                          </td>
                          <td className="pl-1 py-1">
                            <button
                              data-testid={`disc-remove-${i}`}
                              onClick={() => removePlan(i)}
                              className="text-zinc-500 hover:text-red-400"
                              title="Remove plan"
                            ><Trash size={12} weight="bold" /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <label className="inline-flex items-center gap-2 text-[10px] font-mono text-zinc-400 mt-2">
                <input type="checkbox" checked={mirrorRules} onChange={(e) => setMirrorRules(e.target.checked)}
                  data-testid="disc-mirror-toggle" />
                Mirror each plan into the main firm dropdown (<code>challenge_rules</code>)
              </label>

              {discoverError && (
                <div data-testid="disc-error" className="text-[11px] font-mono text-red-400 bg-red-950/40 border border-red-900/60 rounded p-2">
                  {discoverError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  data-testid="disc-save-btn"
                  onClick={handleSavePlans}
                  disabled={savingPlans || !plans.length}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed rounded-md transition-colors"
                >
                  {savingPlans ? (
                    <><CircleNotch size={14} weight="bold" className="animate-spin" /> Saving…</>
                  ) : (
                    <><CheckCircle size={14} weight="fill" /> Save {plans.length} plan{plans.length !== 1 ? 's' : ''}</>
                  )}
                </button>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfidenceBadge({ confidence, missing }) {
  const level = confidence >= 75 ? 'high' : confidence >= 50 ? 'med' : 'low';
  const map = {
    high: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40',
    med: 'bg-amber-500/15 text-amber-400 border-amber-500/40',
    low: 'bg-red-500/15 text-red-400 border-red-500/40',
  };
  return (
    <span
      data-testid="extraction-confidence"
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider border rounded ${map[level]}`}
    >
      <Warning size={11} weight="bold" /> confidence {confidence}%
      {missing?.length > 0 && ` · ${missing.length} missing`}
    </span>
  );
}

function OptionalRule({ label, enabled, onToggle, children, hint, testId }) {
  return (
    <div
      data-testid={testId}
      className={`border rounded-md p-3 space-y-2 transition-colors ${
        enabled
          ? 'border-amber-500/40 bg-amber-500/5'
          : 'border-zinc-800 bg-zinc-900/40 opacity-80'
      }`}
    >
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          data-testid={`${testId}-toggle`}
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="accent-amber-400 w-3.5 h-3.5"
        />
        <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-200">
          Enable {label}
        </span>
      </label>
      {hint && (
        <p className="text-[9px] font-mono text-amber-400/80">{hint}</p>
      )}
      {enabled && (
        <div className="grid grid-cols-2 gap-2 pt-1">
          {children}
        </div>
      )}
    </div>
  );
}


function EditField({ label, value, onChange, source, testId, optional }) {
  const sourceColor = source === 'regex' ? 'text-emerald-400' : source === 'llm' ? 'text-cyan-400' : 'text-zinc-500';
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider">
          {label}{!optional && ' *'}
        </label>
        <span className={`text-[9px] font-mono uppercase ${sourceColor}`}>
          {source || 'manual'}
        </span>
      </div>
      <input
        data-testid={testId}
        type="number"
        step="any"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-zinc-600 focus:border-zinc-600 focus:outline-none w-full"
      />
    </div>
  );
}

function SummaryCell({ label, value, color = 'text-white' }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`text-[12px] font-bold ${color}`}>{value ?? '—'}</p>
    </div>
  );
}

function toNum(v) {
  if (v === '' || v == null) return null;
  const n = Number(v); return Number.isFinite(n) ? n : null;
}
function toInt(v) {
  if (v === '' || v == null) return null;
  const n = parseInt(v, 10); return Number.isFinite(n) ? n : null;
}
