/*
 * Strategy Passport — Surface D5.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · SPRINT_2_PLANNING.md §2 N5 · Bible §10
 *
 * Anatomy:
 *   §1 Signature header       — SignatureFrame · gold · name + version + status chip + ambition
 *   §2 Identity strip         — Sharpe · Drawdown · Turnover · AUM (4 MetricBlocks)
 *   §3 Evidence stack         — ProvenanceTriple + LineageBar side-by-side
 *   §4 Guardrails             — grid of guardrail cells with chips
 *   §5 Equity curve           — ChartTile · gold
 *   §6 Backtest attestation   — Signed evidence card
 *   §7 Approval history       — Chronological list
 *
 * Data path:
 *   useParams() → fetchStrategy(id) → live `GET /api/strategies/{id}` first,
 *   falls back to STRATEGY_PASSPORT_FIXTURE or a documented FALLBACK shell.
 */
import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { AlertTriangle, Award, Landmark, LineChart as LineChartIcon, ScrollText, ShieldCheck } from 'lucide-react';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { MetricBlock } from '../primitives/MetricBlock';
import { Chip } from '../primitives/Chip';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { ProvenanceTriple } from '../primitives/ProvenanceTriple';
import { LineageBar } from '../primitives/LineageBar';
import { ChartTile } from '../primitives/ChartTile';
import { StateTemplate } from '../primitives/StateTemplate';
import { fetchStrategy } from '../adapters/factoryAdapter';

const STATUS_TONE = { live: 'ok', paper: 'info', archived: 'dormant', draft: 'dormant' };

const formatSigned = (n, digits = 2) => {
  if (typeof n !== 'number' || Number.isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;
};

export const StrategyPassport = () => {
  const { id } = useParams();
  const [strat, setStrat] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    setStrat(null);
    setErr(null);
    fetchStrategy(id)
      .then((s) => { if (live) setStrat(s); })
      .catch((e) => { if (live) setErr(e); });
    return () => { live = false; };
  }, [id]);

  if (err) {
    return (
      <div style={{ padding: 'var(--space-6) var(--space-5)' }}>
        <StateTemplate variant="error" code="passport-error" icon={AlertTriangle} tone="crit"
                       headline={`Passport for ${id} could not load.`}
                       purpose="The strategy adapter failed. Retrying every 60s."
                       advancedFootnote={`factoryAdapter@v1 · ${err.message}`} />
      </div>
    );
  }

  if (!strat) {
    return (
      <div style={{ padding: 'var(--space-6) var(--space-5)' }}>
        <StateTemplate variant="empty" code="passport-loading" icon={LineChartIcon} tone="info"
                       headline="Assembling passport…"
                       purpose="Fetching strategy record, guardrails, evidence, and approvals." />
      </div>
    );
  }

  return (
    <section data-testid="strategy-passport" data-strategy-id={strat.id} data-source={strat._source || 'fixture'}
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400,
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>

      {/* Breadcrumb · back to explorer */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                    fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                    textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        <Link to="/c/strategies" data-testid="passport-back-link"
              style={{ color: 'var(--sig-info)', textDecoration: 'none' }}>
          ← Strategy Explorer
        </Link>
        <span aria-hidden>·</span>
        <span data-testid="passport-crumb-id" className="mono-num">{strat.id}</span>
      </div>

      {/* §1 Signature header */}
      <SignatureFrame tone={strat.tone || STATUS_TONE[strat.status] || 'info'}
                      icon={Award}
                      caption={`Strategy passport · ${strat.version}`}
                      testId="passport-signature">
        <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'baseline', marginBottom: 'var(--space-2)' }}>
          <h1 data-testid="passport-name"
              style={{ margin: 0, fontSize: 'var(--font-h1)', fontWeight: 400,
                       letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            {strat.name}
          </h1>
          <span data-testid="passport-status">
            <Chip tone={STATUS_TONE[strat.status] || 'info'} label={strat.status} />
          </span>
          {strat._fallback && (
            <span data-testid="passport-fallback-notice">
              <Chip tone="dormant" label="fallback shell" showGlyph={false} />
            </span>
          )}
        </div>
        <p data-testid="passport-ambition"
           style={{ margin: 0, maxWidth: 900, fontSize: 'var(--font-body-md)',
                    lineHeight: 1.55, color: 'var(--content-md)' }}>
          {strat.ambition}
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-4)', marginTop: 'var(--space-3)',
                      fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                      textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          <span>id · <span className="mono-num" style={{ color: 'var(--content-md)' }}>{strat.id}</span></span>
          <span aria-hidden>·</span>
          <span>sha · <span className="mono-num" style={{ color: 'var(--content-md)' }}>{strat.codeSha}</span></span>
          <span aria-hidden>·</span>
          <span>since · <span className="mono-num" style={{ color: 'var(--content-md)' }}>{strat.inceptionDate}</span></span>
        </div>
      </SignatureFrame>

      {/* §2 Identity strip */}
      <div data-testid="passport-metrics"
           style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
        <MetricBlock variant="A" eyebrow="Sharpe (ann.)"
                     value={formatSigned(strat.sharpe)}
                     deltaLabel={strat.sharpe >= 1.5 ? 'top decile' : strat.sharpe >= 1 ? 'above target' : 'below target'}
                     deltaTone={strat.sharpe >= 1.5 ? 'ok' : strat.sharpe >= 1 ? 'info' : 'warn'}
                     footnote="rolling 90d" />
        <MetricBlock variant="B" eyebrow="Max drawdown"
                     value={`${strat.drawdown.toFixed(1)}%`}
                     deltaLabel={strat.drawdown > -5 ? 'within band' : 'aged'}
                     deltaTone={strat.drawdown > -5 ? 'ok' : 'warn'}
                     footnote="closed peak-to-trough" />
        <MetricBlock variant="A" eyebrow="Turnover"
                     value={`${strat.turnover.toFixed(1)}x`}
                     deltaLabel="annualised"
                     deltaTone="info"
                     footnote="per unit AUM" />
        <MetricBlock variant="C" eyebrow="AUM"
                     value={strat.aum}
                     deltaLabel={strat.status === 'live' ? 'live capital' : 'paper only'}
                     deltaTone={strat.status === 'live' ? 'ok' : 'info'}
                     footnote={strat.version} />
      </div>

      {/* §3 Evidence stack */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
        <div data-testid="passport-provenance"
             style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                      borderRadius: 'var(--radius-3)', padding: 'var(--space-4)' }}>
          <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                        textTransform: 'uppercase', letterSpacing: '0.08em',
                        marginBottom: 'var(--space-2)' }}>
            Provenance
          </div>
          <ProvenanceTriple source={strat.provenance?.source}
                            transform={strat.provenance?.transform}
                            attested={strat.provenance?.attested} />
        </div>
        <div data-testid="passport-lineage"
             style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                      borderRadius: 'var(--radius-3)', padding: 'var(--space-4)' }}>
          <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                        textTransform: 'uppercase', letterSpacing: '0.08em',
                        marginBottom: 'var(--space-2)' }}>
            Lineage
          </div>
          <LineageBar self={strat.lineage?.self ?? { id: strat.id, label: strat.name, kind: 'strategy' }}
                      ancestors={strat.lineage?.ancestors ?? []}
                      descendants={strat.lineage?.descendants ?? []} />
        </div>
      </div>

      {/* §4 Guardrails */}
      {strat.guardrails?.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <DivisionCaption eyebrow="Guardrails" icon={ShieldCheck}
                           status={`${strat.guardrails.length} tracked`}
                           purpose="Policy-enforced boundaries. A breach here would auto-pause the strategy." />
          <div data-testid="passport-guardrails"
               style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-3)' }}>
            {strat.guardrails.map((g) => (
              <div key={g.key} data-testid={`passport-guardrail-${g.key}`}
                   style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)',
                            padding: 'var(--space-3)', background: 'var(--surface-1)',
                            border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)' }}>
                <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                               textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {g.label}
                </span>
                <span className="mono-num"
                      style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)' }}>
                  {g.value}
                </span>
                <div style={{ marginTop: 'var(--space-1)' }}>
                  <Chip tone={g.tone}
                        label={g.tone === 'ok' ? 'passing' : g.tone === 'advisory' ? 'advisory' : g.tone} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* §5 Equity curve */}
      {strat.equityCurve?.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <DivisionCaption eyebrow="Equity curve" icon={LineChartIcon}
                           status={`${strat.equityCurve.length} points`}
                           purpose="Cumulative attested equity since inception." />
          <ChartTile caption={`Equity curve · ${strat.name}`}
                     points={strat.equityCurve}
                     tone="gold"
                     variant="line"
                     timeWindow="since inception"
                     testId="passport-equity" />
        </div>
      )}

      {/* §6 Backtest attestation */}
      {strat.backtest && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <DivisionCaption eyebrow="Backtest attestation" icon={ScrollText}
                           status={strat.backtest.id}
                           purpose="Signed evidence produced by the validator worker." />
          <div data-testid="passport-backtest"
               style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                        borderRadius: 'var(--radius-3)', padding: 'var(--space-4)',
                        display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap',
                          fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                          textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              <span>window · <span className="mono-num" style={{ color: 'var(--content-md)' }}>{strat.backtest.window}</span></span>
              <span aria-hidden>·</span>
              <span>regime coverage · <span className="mono-num" style={{ color: 'var(--content-md)' }}>{strat.backtest.regimeCoverage}</span></span>
              <span aria-hidden>·</span>
              <span>attested by · <span className="mono-num" style={{ color: 'var(--content-md)' }}>{strat.backtest.attestedBy}</span></span>
            </div>
            <p style={{ margin: 0, fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.6 }}>
              {strat.backtest.notes}
            </p>
          </div>
        </div>
      )}

      {/* §7 Approval history */}
      {strat.approvals?.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <DivisionCaption eyebrow="Approval history" icon={Landmark}
                           status={`${strat.approvals.length} recorded`}
                           purpose="Chronological ledger of every human decision on this strategy." />
          <ol data-testid="passport-approvals"
              aria-label="Approval history"
              style={{ listStyle: 'none', margin: 0, padding: 0,
                       background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                       borderRadius: 'var(--radius-3)', overflow: 'hidden' }}>
            {strat.approvals.map((a) => (
              <li key={a.id} data-testid={`passport-approval-${a.id}`}
                  style={{ display: 'grid', gridTemplateColumns: '140px 1fr 120px 200px',
                           gap: 'var(--space-3)', alignItems: 'center',
                           padding: 'var(--space-3) var(--space-4)',
                           borderBottom: '1px solid var(--stroke-1)' }}>
                <span className="mono-num"
                      style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                               textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {a.at.slice(0, 10)}
                </span>
                <span style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)' }}>{a.title}</span>
                <Chip tone={a.verdict === 'approved' ? 'ok' : a.verdict === 'blocked' ? 'crit' : 'info'}
                      label={a.verdict} showGlyph={false} />
                <span className="mono-num"
                      style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)' }}>
                  {a.by}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
};
