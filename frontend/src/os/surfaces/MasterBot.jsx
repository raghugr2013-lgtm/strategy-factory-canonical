/*
 * Master Bot Dashboard — Surface D4 · standalone.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · SPRINT_2_PLANNING.md §2 N2
 *
 * Anatomy:
 *   §1 Identity strip     — codename · role · version · stance · trust budget · uptime
 *   §2 Current plan card  — plan id · epoch · guardrails · ambition
 *   §3 Last decisions log — ranked feed of the last 5 Master Bot decisions
 *
 * Sprint 2 N2 constraint: fixture-only. `masterBotAdapter.js` will pivot to
 * live traffic without any surface-side change once `/api/master-bot/*`
 * lands on the Backend Activation Roadmap.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bot, GitBranch, ShieldCheck, Clock, Sparkles, Activity } from 'lucide-react';
import { useWorkspaceStore } from '../workspace-state/store';
import { MetricBlock } from '../primitives/MetricBlock';
import { Chip } from '../primitives/Chip';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { StateTemplate } from '../primitives/StateTemplate';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { aggregateMasterBot } from '../adapters/masterBotAdapter';

const formatUptime = (seconds) => {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
};

const STANCE_TONE = { observe: 'info', advise: 'advisory', act: 'warn' };

export const MasterBot = () => {
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const [bundle, setBundle] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    aggregateMasterBot()
      .then((b) => { if (live) setBundle(b); })
      .catch((e) => { if (live) setErr(e); });
    return () => { live = false; };
  }, []);

  if (err) {
    return (
      <div style={{ padding: 'var(--space-6) var(--space-5)' }}>
        <StateTemplate variant="error" code="master-bot-error" icon={Bot} tone="crit"
                       headline="Master Bot dashboard could not load."
                       purpose="The master-bot aggregator failed. Retrying every 60s."
                       advancedFootnote={`master-bot-adapter@v1 · ${err.message}`} />
      </div>
    );
  }

  if (!bundle) {
    return (
      <div style={{ padding: 'var(--space-6) var(--space-5)' }}>
        <StateTemplate variant="empty" code="master-bot-loading" icon={Bot} tone="info"
                       headline="Loading Master Bot state…"
                       purpose="Fetching identity, current plan, and recent decisions." />
      </div>
    );
  }

  const { identity, currentPlan, decisions } = bundle;
  const trustPct = Math.round((identity.trustBudget.spent / identity.trustBudget.cap) * 100);
  const trustTone = trustPct >= 80 ? 'warn' : trustPct >= 60 ? 'advisory' : 'ok';

  return (
    <section data-testid="master-bot" data-mode="operations"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400,
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>

      {/* Eyebrow · Headline · Briefing */}
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
          <span data-testid="mb-eyebrow"
                style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
                         letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Master bot · dashboard
          </span>
        </div>
        <h1 data-testid="mb-headline"
            style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)',
                     fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
          {identity.codename} · {identity.role}
        </h1>
        <p data-testid="mb-briefing"
           style={{ margin: 0, maxWidth: 780, fontSize: 'var(--font-body-md)',
                    lineHeight: 1.55, color: 'var(--content-md)' }}>
          The overseer that orchestrates the Factory. Its stance, budget, and
          recent decisions live here. Everything else the Factory does is
          answerable to what this bot chose to run.
        </p>
        <Link
          to="/c/workforce/explorer"
          data-testid="masterbot-try-workforce-explorer"
          style={{ display: 'inline-block', marginTop: 'var(--space-3)',
                   fontSize: 'var(--font-caption)', color: 'var(--sig-info)',
                   textDecoration: 'none', textTransform: 'uppercase',
                   letterSpacing: '0.08em', fontFamily: 'ui-monospace, monospace' }}
        >
          Try Workforce Explorer →
        </Link>
      </div>

      {/* §1 Identity strip */}
      <div data-testid="mb-identity-strip"
           style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
        <MetricBlock variant="B" eyebrow="Stance"
                     value={identity.stance.toUpperCase()}
                     deltaLabel={identity.version} deltaTone={STANCE_TONE[identity.stance]}
                     footnote={`stance authority · plan-owner`} />
        <MetricBlock variant="A" eyebrow="Trust budget"
                     value={`${identity.trustBudget.spent}`} unit={`/ ${identity.trustBudget.cap} ${identity.trustBudget.unit}`}
                     deltaLabel={`${trustPct}% spent`} deltaTone={trustTone}
                     footnote="cap resets weekly · plan #47" />
        <MetricBlock variant="A" eyebrow="Uptime"
                     value={formatUptime(identity.uptimeSeconds)}
                     deltaLabel={`last seen ${identity.lastSeen.slice(11, 16)}Z`} deltaTone="info"
                     footnote={identity.version} />
        <MetricBlock variant="C" eyebrow="Current plan"
                     value={currentPlan.strategies}
                     unit={`strategies · epoch ${currentPlan.epoch}`}
                     deltaLabel={currentPlan.name} deltaTone="info"
                     footnote={`horizon ${currentPlan.horizonHours}h`} />
      </div>

      {/* §2 Current plan card */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <DivisionCaption eyebrow="Current plan" icon={GitBranch}
                         status={`${currentPlan.id} · epoch ${currentPlan.epoch}`}
                         purpose={currentPlan.ambition} />
        <SignatureFrame tone="gold" icon={Sparkles} caption={currentPlan.name} testId="mb-plan-card">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
            {currentPlan.guardrails.map((g) => (
              <div key={g.key} data-testid={`mb-guardrail-${g.key}`}
                   style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)',
                            padding: 'var(--space-3)', background: 'var(--surface-2)',
                            border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)' }}>
                <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                              textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {g.label}
                </div>
                <div className="mono-num"
                     style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)' }}>
                  {g.value}
                </div>
                <div style={{ marginTop: 'var(--space-1)' }}>
                  <Chip tone={g.tone} label={g.tone === 'ok' ? 'passing' : g.tone === 'info' ? 'noted' : g.tone} />
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                        fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', flexWrap: 'wrap' }}>
            <Clock size={12} strokeWidth={1.5} aria-hidden />
            <span data-testid="mb-plan-started" className="mono-num">started {currentPlan.startedAt.slice(11, 16)}Z</span>
            <span aria-hidden style={{ color: 'var(--content-lo)' }}>·</span>
            <ShieldCheck size={12} strokeWidth={1.5} aria-hidden />
            <span>{currentPlan.guardrails.length} guardrails · all reporting</span>
            {currentPlan.nextTickAt && (
              <>
                <span aria-hidden style={{ color: 'var(--content-lo)' }}>·</span>
                <span data-testid="mb-plan-next-tick"
                      data-next-tick-at={currentPlan.nextTickAt}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                               padding: '2px 8px', borderRadius: 'var(--radius-1)',
                               background: 'var(--surface-2)', border: '1px solid var(--stroke-1)',
                               fontSize: 'var(--font-caption)', color: 'var(--content-md)',
                               textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {currentPlan.nextTickLabel ?? 'next tick'}
                  <span aria-hidden style={{ color: 'var(--content-lo)' }}>·</span>
                  <span className="mono-num">{currentPlan.nextTickAt.slice(11, 16)}Z</span>
                </span>
              </>
            )}
          </div>
        </SignatureFrame>
      </div>

      {/* §3 Last decisions log */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <DivisionCaption eyebrow="Last decisions" icon={Activity}
                         status={`${decisions.length} most recent`}
                         purpose="What the Master Bot chose to do, defer, or block — most recent first." />
        <ol data-testid="mb-decisions"
            aria-label="Master Bot last decisions"
            style={{ listStyle: 'none', margin: 0, padding: 0,
                     background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                     borderRadius: 'var(--radius-3)', overflow: 'hidden' }}>
          {decisions.map((d) => (
            <li key={d.id} data-testid={`mb-decision-${d.id}`}
                style={{ display: 'grid', gridTemplateColumns: '80px 100px 1fr auto',
                         gap: 'var(--space-3)', alignItems: 'start',
                         padding: 'var(--space-3) var(--space-4)',
                         borderBottom: '1px solid var(--stroke-1)' }}>
              <span className="mono-num"
                    style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                             textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {d.ts}
              </span>
              <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)',
                             textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                {d.verb}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                <span style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)' }}>{d.subject}</span>
                {advLens && (
                  <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)', lineHeight: 1.5 }}>
                    {d.rationale}
                  </span>
                )}
              </div>
              <Chip tone={d.tone}
                    label={d.tone === 'ok' ? 'shipped' : d.tone === 'warn' ? 'deferred' : d.tone === 'crit' ? 'blocked' : 'noted'} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
};
