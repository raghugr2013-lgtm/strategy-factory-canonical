/*
 * StrategyLab — Sprint 3 Phase-2 live authoring surface.
 * refs UX-Review-2026-07-22 · Backend Feature Freeze v1.1.0-stage4
 *
 * Composed from three live endpoints under the freeze:
 *   POST /api/strategies/generate  — LLM-composed CNL skeleton
 *   POST /api/strategies           — persist as draft (status=draft)
 *   POST /api/knowledge/nearest    — historical KB neighbours
 *   GET  /api/knowledge/statistics — corpus size hint chip
 *
 * No synthetic data. Empty-state → real interface with PARTIAL LIVE
 * chips and operator-legible reasons.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, FlaskConical, Save, Sparkles, Layers } from 'lucide-react';
import {
  generateStrategy,
  saveStrategyDraft,
  findNearestStrategies,
  fetchKnowledgeStatistics,
} from '../../adapters/strategyLabAdapter';
import { LivenessBadge, FreezeCaption } from './LivenessBadge';
import { useWorkspaceContext } from '../../hooks/useWorkspaceContext';

const PAIR_OPTIONS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD', 'ETHUSD', 'SPX', 'NDX'];
const TIMEFRAME_OPTIONS = ['M15', 'M30', 'H1', 'H4', 'D1'];
const STYLE_OPTIONS = ['trend-following', 'mean-reversion', 'breakout', 'range-bound', 'momentum'];

export const StrategyLab = () => {
  // Workspace context (§9) — Strategy Lab is both a reader and a writer of
  // the URL-scoped context. Selectors initialise from context and every
  // change is written back so downstream surfaces (Coverage, Datasets,
  // Pipeline) can filter automatically.
  const { context, setContext } = useWorkspaceContext();

  const [pair, setPair] = useState(context.pair || 'XAUUSD');
  const [timeframe, setTimeframe] = useState(context.timeframe || 'H4');
  const [style, setStyle] = useState('trend-following');
  const [draftName, setDraftName] = useState('');

  const [generateState, setGenerateState] = useState({ status: 'idle', liveness: 'partial', reason: null, text: '' });
  const [saveState, setSaveState] = useState({ status: 'idle', liveness: 'partial', reason: null, strategy: null });
  const [nearestState, setNearestState] = useState({ status: 'idle', liveness: 'partial', reason: null, matches: [], total: 0 });
  const [kbStats, setKbStats] = useState({ total_strategies: 0, canonical_families: 0, backend_available: {} });

  // Corpus size chip — helpful signal for "is the KB warm enough for nearest?"
  useEffect(() => {
    (async () => {
      const res = await fetchKnowledgeStatistics();
      if (res.payload) setKbStats(res.payload);
    })();
  }, []);

  // Push pair + timeframe back into the workspace context (§9) so other
  // surfaces filter automatically. This is a fire-and-forget effect —
  // clearing context in the header is honoured on the next mount.
  useEffect(() => {
    setContext({ pair, timeframe });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pair, timeframe]);

  const onGenerate = useCallback(async () => {
    setGenerateState({ status: 'loading', liveness: 'partial', reason: null, text: '' });
    setSaveState({ status: 'idle', liveness: 'partial', reason: null, strategy: null });
    const res = await generateStrategy({ pair, timeframe, style });
    const text = res.payload?.strategy || '';
    setGenerateState({ status: 'ready', liveness: res.liveness, reason: res.reason, text });
    // Seed a draft name from the generated skeleton (first non-empty line-ish)
    if (text && !draftName.trim()) {
      const first = text.split('\n').find((l) => l.trim().length > 0) || '';
      const parsed = first.replace(/^STRATEGY:\s*/i, '').trim().slice(0, 80);
      setDraftName(parsed || `${pair} · ${timeframe} · ${style}`);
    }
    // Auto-run nearest-neighbour lookup against the generated text
    if (text) {
      setNearestState({ status: 'loading', liveness: 'partial', reason: null, matches: [], total: 0 });
      const nn = await findNearestStrategies({ strategy_text: text, pair, timeframe, top_k: 5 });
      setNearestState({
        status: 'ready',
        liveness: nn.liveness,
        reason: nn.reason,
        matches: nn.payload?.matches || [],
        total: nn.payload?.total_corpus || 0,
      });
    }
  }, [pair, timeframe, style, draftName]);

  const onSaveDraft = useCallback(async () => {
    if (!generateState.text) return;
    const name = draftName.trim() || `${pair} · ${timeframe} · ${style}`;
    setSaveState({ status: 'loading', liveness: 'partial', reason: null, strategy: null });
    const res = await saveStrategyDraft({
      name,
      description: `Composed via Strategy Lab · ${style} · ${pair} ${timeframe}`,
      symbol: pair,
      timeframe,
      tags: ['draft', 'lab', style],
    });
    setSaveState({
      status: 'ready',
      liveness: res.liveness,
      reason: res.reason,
      strategy: res.payload,
    });
    // Bind the freshly persisted draft into the workspace context so
    // downstream surfaces (Pipeline, Passport once available) light up
    // the correct row.
    if (res.payload?.strategy_id) {
      setContext({ strategy: res.payload.strategy_id });
    }
  }, [draftName, generateState.text, pair, timeframe, style, setContext]);

  const aggregate = useMemo(() => {
    if (generateState.status === 'ready' && generateState.liveness === 'live') {
      return { liveness: 'live', reason: null };
    }
    if (generateState.status === 'ready' && generateState.liveness !== 'live') {
      return { liveness: generateState.liveness, reason: generateState.reason };
    }
    return { liveness: 'partial', reason: 'Compose a strategy to hit the live pipeline.' };
  }, [generateState]);

  return (
    <section data-testid="engineering-surface-strategy-lab"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrow}>Engineering</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }}>Strategy Lab</span>
        <span style={{ marginLeft: 'auto' }}>
          <LivenessBadge liveness={aggregate.liveness} reason={aggregate.reason} testId="strategy-lab-liveness" />
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="strategy-lab-headline"
              style={{ margin: 0, fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            <FlaskConical size={20} strokeWidth={1.5} color="var(--sig-info)" style={{ verticalAlign: '-3px', marginRight: 8 }} />
            Compose a strategy skeleton and drop it into the pipeline.
          </h1>
          <p data-testid="strategy-lab-subhead"
             style={{ margin: 'var(--space-2) 0 0 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 780 }}>
            Composed under Backend Feature Freeze v1.1.0-stage4 from
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>POST /api/strategies/generate</code>,
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>POST /api/strategies</code>, and
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>POST /api/knowledge/nearest</code>.
            Every draft is real — persisted with lineage — and never eligible for deploy until it earns a Passport.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <div data-testid="strategy-lab-kb-chip" style={kbChip}>
            <Layers size={11} strokeWidth={1.75} color="var(--accent-gold)" />
            <span>KB · {kbStats.total_strategies} · {kbStats.canonical_families} families</span>
          </div>
        </div>
      </div>

      {/* COMPOSER */}
      <div data-testid="strategy-lab-composer" style={{ ...panel, marginBottom: 'var(--space-5)' }}>
        <div style={panelHeader}>Compressed natural language · composer</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', alignItems: 'end' }}>
          <Field label="Pair">
            <select data-testid="strategy-lab-pair"
                    value={pair}
                    onChange={(e) => setPair(e.target.value)}
                    style={select}>
              {PAIR_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Timeframe">
            <select data-testid="strategy-lab-timeframe"
                    value={timeframe}
                    onChange={(e) => setTimeframe(e.target.value)}
                    style={select}>
              {TIMEFRAME_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Style">
            <select data-testid="strategy-lab-style"
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                    style={select}>
              {STYLE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label=" ">
            <button type="button"
                    data-testid="strategy-lab-generate"
                    onClick={onGenerate}
                    disabled={generateState.status === 'loading'}
                    style={primaryBtn}>
              <Sparkles size={12} strokeWidth={1.75} />
              <span>{generateState.status === 'loading' ? 'Composing…' : 'Compose skeleton'}</span>
            </button>
          </Field>
        </div>
      </div>

      {/* SKELETON PREVIEW + SAVE */}
      <div data-testid="strategy-lab-preview" style={{ ...panel, marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeader, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Generated skeleton</span>
          <LivenessBadge liveness={generateState.status === 'idle' ? 'partial' : generateState.liveness}
                         reason={generateState.status === 'idle' ? 'Hit `Compose skeleton` to fetch a live sample.' : generateState.reason}
                         testId="strategy-lab-generate-liveness" />
        </div>
        {generateState.status === 'idle' ? (
          <div data-testid="strategy-lab-preview-idle"
               style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, padding: 'var(--space-3) 0' }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>Idle</div>
            Compose a skeleton to hit the live <code style={{ color: 'var(--sig-info)' }}>POST /api/strategies/generate</code> endpoint.
            The response will be persisted as a draft only when you press <em>Save draft</em>.
          </div>
        ) : generateState.status === 'loading' ? (
          <div data-testid="strategy-lab-preview-loading" style={{ padding: 'var(--space-3) 0', color: 'var(--content-lo)', fontFamily: 'ui-monospace, SFMono-Regular, monospace', fontSize: 'var(--font-body-sm)' }}>
            Composing…
          </div>
        ) : (
          <>
            <pre data-testid="strategy-lab-preview-text"
                 style={{
                   whiteSpace: 'pre-wrap',
                   background: 'var(--surface-0)',
                   border: '1px solid var(--stroke-1)',
                   borderRadius: 'var(--radius-2)',
                   padding: 'var(--space-4)',
                   fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                   fontSize: 'var(--font-body-sm)',
                   color: 'var(--content-hi)',
                   lineHeight: 1.55,
                   margin: 0,
                   maxHeight: 320,
                   overflow: 'auto',
                 }}>
              {generateState.text || '— no output —'}
            </pre>
            <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', marginTop: 'var(--space-4)' }}>
              <input data-testid="strategy-lab-draft-name"
                     value={draftName}
                     onChange={(e) => setDraftName(e.target.value)}
                     placeholder="Draft name (auto-filled from skeleton)"
                     style={inputStyle} />
              <button type="button"
                      data-testid="strategy-lab-save"
                      onClick={onSaveDraft}
                      disabled={saveState.status === 'loading' || !generateState.text || !draftName.trim()}
                      style={primaryBtn}>
                <Save size={12} strokeWidth={1.75} />
                <span>{saveState.status === 'loading' ? 'Saving…' : 'Save draft'}</span>
              </button>
            </div>
            {saveState.status === 'ready' && saveState.strategy && (
              <div data-testid="strategy-lab-save-receipt"
                   style={{
                     marginTop: 'var(--space-3)',
                     padding: 'var(--space-3) var(--space-4)',
                     border: '1px solid color-mix(in oklab, var(--sig-ok) 40%, transparent)',
                     background: 'color-mix(in oklab, var(--sig-ok) 6%, transparent)',
                     borderRadius: 'var(--radius-2)',
                     display: 'flex',
                     gap: 'var(--space-3)',
                     alignItems: 'center',
                     fontSize: 'var(--font-body-sm)',
                   }}>
                <span style={{ color: 'var(--sig-ok)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 'var(--font-caption)' }}>
                  Persisted
                </span>
                <span style={{ color: 'var(--content-md)' }}>
                  <code className="mono-num" style={{ color: 'var(--content-hi)' }}>{saveState.strategy.strategy_id}</code>
                  {' · '}status <code style={{ color: 'var(--sig-info)' }}>{saveState.strategy.status}</code>
                  {' · '}<Link to="/c/strategies" data-testid="strategy-lab-save-receipt-link" style={{ color: 'var(--sig-info)' }}>open in Strategy Passports →</Link>
                </span>
              </div>
            )}
            {saveState.status === 'ready' && saveState.liveness !== 'live' && (
              <div data-testid="strategy-lab-save-error"
                   style={{
                     marginTop: 'var(--space-3)',
                     padding: 'var(--space-3) var(--space-4)',
                     border: '1px solid color-mix(in oklab, var(--sig-crit) 40%, transparent)',
                     background: 'color-mix(in oklab, var(--sig-crit) 6%, transparent)',
                     borderRadius: 'var(--radius-2)',
                     color: 'var(--sig-crit)',
                     fontSize: 'var(--font-body-sm)',
                   }}>
                Save failed · {saveState.reason || 'unknown error'}
              </div>
            )}
          </>
        )}
      </div>

      {/* NEAREST NEIGHBOURS */}
      <div data-testid="strategy-lab-nearest" style={{ ...panel, marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeader, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Historical neighbours</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <LivenessBadge liveness={nearestState.status === 'idle' ? 'partial' : nearestState.liveness}
                           reason={nearestState.status === 'idle' ? 'Runs automatically after Compose.' : nearestState.reason}
                           testId="strategy-lab-nearest-liveness" />
            <span className="mono-num" data-testid="strategy-lab-nearest-count" style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)' }}>
              {nearestState.matches.length} / {nearestState.total || kbStats.total_strategies} corpus
            </span>
          </div>
        </div>
        {nearestState.status === 'idle' ? (
          <div style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', padding: 'var(--space-3) 0' }}>
            Compose a skeleton to trigger a rule-based similarity search across the historical KB
            (<code style={{ color: 'var(--sig-info)' }}>POST /api/knowledge/nearest</code>).
          </div>
        ) : nearestState.matches.length === 0 ? (
          <div data-testid="strategy-lab-nearest-empty"
               style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', padding: 'var(--space-3) 0', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>Corpus · {nearestState.total || 0}</div>
            The historical KB has no neighbours to return. The interface is live — as soon as historical strategies
            are imported into <code style={{ color: 'var(--sig-info)' }}>strategy_kb_view</code>, similarity matches
            will appear here.
          </div>
        ) : (
          <div role="table" aria-label="Nearest historical strategies">
            <div role="row" style={nnHead}>
              <span>Strategy id</span>
              <span>Pair · TF</span>
              <span>Type</span>
              <span style={{ textAlign: 'right' }}>Score</span>
              <span style={{ textAlign: 'right' }}>Learning only</span>
            </div>
            {nearestState.matches.map((m, i) => (
              <div key={m.strategy_id || i} role="row" data-testid={`strategy-lab-nearest-row-${i}`} style={nnBody}>
                <span className="mono-num" style={{ color: 'var(--content-hi)', fontSize: 'var(--font-caption)' }}>{m.strategy_id}</span>
                <span>{[m.pair, m.timeframe].filter(Boolean).join(' · ') || '—'}</span>
                <span style={{ color: 'var(--content-md)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>{m.strategy_type || '—'}</span>
                <span className="mono-num" style={{ textAlign: 'right' }}>{typeof m.similarity_score === 'number' ? m.similarity_score.toFixed(3) : '—'}</span>
                <span style={{ textAlign: 'right', color: 'var(--sig-warn)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>
                  {m.learning_only !== false ? 'yes' : 'no'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* FOOTER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <RelatedPill to="/c/strategies"                    label="Strategy Passports" testId="strategy-lab-related-passports" />
          <RelatedPill to="/c/engineering/strategy-pipeline" label="Strategy Pipeline"  testId="strategy-lab-related-pipeline" />
          <RelatedPill to="/c/engineering/optimization"      label="Optimization"       testId="strategy-lab-related-optimization" />
        </div>
      </div>
    </section>
  );
};

const Field = ({ label, children }) => (
  <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    <span style={{ ...eyebrow, color: 'var(--content-lo)' }}>{label}</span>
    {children}
  </label>
);

const RelatedPill = ({ to, label, testId }) => (
  <Link to={to} data-testid={testId} style={pill}>
    <span>{label}</span>
    <ArrowRight size={11} strokeWidth={1.75} />
  </Link>
);

const eyebrow = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
};

const panel = {
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-1)',
  borderRadius: 'var(--radius-3)',
  padding: 'var(--space-4)',
};

const panelHeader = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  marginBottom: 'var(--space-3)',
  paddingBottom: 'var(--space-3)',
  borderBottom: '1px solid var(--stroke-1)',
};

const select = {
  background: 'var(--surface-2)',
  color: 'var(--content-hi)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-2)',
  padding: 'var(--space-2) var(--space-3)',
  fontSize: 'var(--font-body-sm)',
  fontFamily: 'inherit',
  outline: 'none',
};

const inputStyle = {
  flex: 1,
  background: 'var(--surface-2)',
  color: 'var(--content-hi)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-2)',
  padding: 'var(--space-2) var(--space-3)',
  fontSize: 'var(--font-body-sm)',
  fontFamily: 'inherit',
  outline: 'none',
};

const primaryBtn = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: 'var(--space-2) var(--space-4)',
  background: 'var(--sig-info)',
  color: 'var(--surface-0)',
  border: 'none',
  borderRadius: 'var(--radius-2)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  fontWeight: 600,
  fontFamily: 'inherit',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  transition: 'opacity var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard)',
};

const kbChip = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '5px 10px',
  borderRadius: 999,
  background: 'color-mix(in oklab, var(--accent-gold) 8%, transparent)',
  border: '1px solid color-mix(in oklab, var(--accent-gold) 40%, transparent)',
  color: 'var(--accent-gold)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
};

const nnHead = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.2fr 1.2fr 1fr 1fr',
  padding: '8px 0',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const nnBody = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.2fr 1.2fr 1fr 1fr',
  padding: '10px 0',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-md)',
};

const pill = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '5px 12px',
  borderRadius: 999,
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-2)',
  color: 'var(--content-md)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  textDecoration: 'none',
  transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
};
