/*
 * EvaluationHarness — /prototype/eval
 *
 * Phase 6 · walkable evaluation surface for the Interactive Prototype
 * Gate (P0 §9). Six dimensions, each with authored criteria; the
 * operator marks each verdict (pass · review · fail · unset).
 *
 * Anatomy:
 *   • Surface header with session label + reset controls
 *   • Overall readiness card (ready · nearly · blocked · unstarted)
 *   • Session Summary chip strip (per-dimension roll-up)
 *   • Six dimension sections, each with its criteria
 *   • Notes textarea (persisted to localStorage)
 *
 * PROTOTYPE ONLY. Removed at Design Freeze.
 */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles, Compass, Activity as ActivityIcon, Layers, Timer, ShieldCheck, Fingerprint,
  ChevronRight, RotateCcw, ClipboardCheck,
} from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { Chip, type ChipTone } from '../primitives/Chip';
import {
  useEvaluationStore, DIMENSIONS,
  summariseDimension, overallReadiness,
  type EvalVerdict, type DimensionKey,
} from '../workspace-state/evaluationStore';

const verdictLabel: Record<EvalVerdict, string> = {
  pass: 'pass', review: 'review', fail: 'fail', unset: 'unset',
};
const verdictTone: Record<EvalVerdict, ChipTone> = {
  pass: 'ok', review: 'advisory', fail: 'crit', unset: 'info',
};

const DIM_ICON: Record<DimensionKey, typeof Compass> = {
  'discoverability':          Compass,
  'navigation-predictability': ActivityIcon,
  'cognitive-load':            Layers,
  'interaction-rhythm':        Timer,
  'trust':                     ShieldCheck,
  'identity':                  Fingerprint,
};

const READINESS_TONE = {
  ready:     { tone: 'gold'     as const, chip: 'ok'       as ChipTone },
  nearly:    { tone: 'info'     as const, chip: 'info'     as ChipTone },
  blocked:   { tone: 'crit'     as const, chip: 'crit'     as ChipTone },
  unstarted: { tone: 'advisory' as const, chip: 'advisory' as ChipTone },
};

export const EvaluationHarness: React.FC = () => {
  const nav = useNavigate();
  const { verdicts, notes, session, setVerdict, setNotes, setSession, clearAll, markAllPass } =
    useEvaluationStore();

  const summaries = useMemo(
    () => DIMENSIONS.map((d) => summariseDimension(d, verdicts)),
    [verdicts],
  );
  const readiness = useMemo(() => overallReadiness(verdicts), [verdicts]);
  const rt = READINESS_TONE[readiness.verdict];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <SurfaceHeader
        eyebrow="Evaluation Harness · Interactive Prototype Gate"
        headline="Six dimensions. One walkable checklist. Design Freeze on the far side."
        briefing="Walk each surface with the criteria below. Mark pass / review / fail as you go. The overall readiness verdict updates live and is the go/no-go signal for Design Freeze declaration."
        status="P0 §9 · 6 dimensions"
        testId="eval-header"
      />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'center' }}>
        <label
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          session ·
          <input
            data-testid="eval-session-label"
            value={session}
            placeholder="e.g. 2026-02-04 walk-through #1"
            onChange={(e) => setSession(e.target.value)}
            style={{
              background: 'var(--surface-2)',
              color: 'var(--content-hi)',
              border: '1px solid var(--stroke-2)',
              borderRadius: 'var(--radius-1)',
              padding: '4px 8px',
              fontFamily: 'ui-monospace, monospace',
              fontSize: 'var(--font-caption)',
              minWidth: 280,
            }}
          />
        </label>
        <button
          data-testid="eval-reset"
          onClick={clearAll}
          style={secondaryBtn}
        >
          <RotateCcw size={12} /> reset verdicts
        </button>
        <button
          data-testid="eval-mark-all-pass"
          onClick={markAllPass}
          title="Diagnostic-only shortcut; use only when every criterion has been verified."
          style={secondaryBtn}
        >
          <ClipboardCheck size={12} /> mark all pass
        </button>
      </div>

      {/* Readiness card */}
      <SignatureFrame
        tone={rt.tone}
        icon={Sparkles}
        caption={`Overall readiness · ${readiness.verdict.toUpperCase()}`}
      >
        <div
          data-testid="eval-readiness"
          data-verdict={readiness.verdict}
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
        >
          <div
            style={{
              fontSize: 'var(--font-h2)', color: 'var(--content-hi)',
              fontWeight: 500, lineHeight: 1.2,
            }}
          >
            {readiness.headline}
          </div>
          <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.5 }}>
            {readiness.detail}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            <Chip tone="ok"       label={`${readiness.pass} pass`}   showGlyph={false} testId="eval-count-pass" />
            <Chip tone="advisory" label={`${readiness.review} review`} showGlyph={false} testId="eval-count-review" />
            <Chip tone="crit"     label={`${readiness.fail} fail`}   showGlyph={false} testId="eval-count-fail" />
            <Chip tone="info"     label={`${readiness.unset} unset`} showGlyph={false} testId="eval-count-unset" />
            <span
              className="mono-num"
              style={{
                marginLeft: 'auto', fontSize: 'var(--font-caption)',
                color: 'var(--content-md)', textTransform: 'uppercase', letterSpacing: '0.08em',
              }}
            >
              {readiness.passPct}% of {readiness.total}
            </span>
          </div>
        </div>
      </SignatureFrame>

      {/* Session summary strip */}
      <section
        data-testid="eval-session-summary"
        style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
      >
        <div
          style={{
            fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          Evaluation Session Summary
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: 'var(--space-3)',
          }}
        >
          {summaries.map((s) => {
            const I = DIM_ICON[s.key];
            return (
              <a
                key={s.key}
                href={`#dim-${s.key}`}
                data-testid={`eval-summary-${s.key}`}
                data-verdict={s.verdict}
                style={{
                  display: 'flex', flexDirection: 'column', gap: 8,
                  padding: 'var(--space-3)',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--stroke-1)',
                  borderLeft: `2px solid var(--sig-${verdictTone[s.verdict] === 'ok' ? 'ok' : verdictTone[s.verdict] === 'crit' ? 'crit' : verdictTone[s.verdict] === 'advisory' ? 'gold' : 'info'})`,
                  borderRadius: 'var(--radius-2)',
                  textDecoration: 'none',
                  color: 'inherit',
                }}
              >
                <div
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                  }}
                >
                  <I size={12} /> {s.title}
                  <ChevronRight size={12} style={{ marginLeft: 'auto' }} />
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <Chip tone={verdictTone[s.verdict]} label={verdictLabel[s.verdict]} showGlyph={false} />
                  <span className="mono-num" style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)' }}>
                    {s.pass}/{s.total} passing
                  </span>
                </div>
                <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)' }}>
                  {s.review} review · {s.fail} fail · {s.unset} unset
                </div>
              </a>
            );
          })}
        </div>
      </section>

      {/* Per-dimension checklists */}
      {DIMENSIONS.map((d) => {
        const I = DIM_ICON[d.key];
        const s = summaries.find((x) => x.key === d.key)!;
        return (
          <section
            key={d.key}
            id={`dim-${d.key}`}
            data-testid={`eval-dim-${d.key}`}
            style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
              <div
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                  textTransform: 'uppercase', letterSpacing: '0.08em',
                }}
              >
                <I size={12} /> Dimension · {d.title}
              </div>
              <Chip tone={verdictTone[s.verdict]} label={verdictLabel[s.verdict]} showGlyph={false} />
              <span
                className="mono-num"
                style={{
                  fontSize: 'var(--font-caption)', color: 'var(--content-md)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}
              >
                {s.pass}/{s.total} passing
              </span>
            </div>
            <h2
              style={{
                margin: 0, fontSize: 'var(--font-body-md)',
                color: 'var(--content-hi)', fontWeight: 500, lineHeight: 1.4,
              }}
            >
              {d.purpose}
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {d.criteria.map((c) => {
                const v = verdicts[c.id] ?? 'unset';
                return (
                  <div
                    key={c.id}
                    data-testid={`eval-criterion-${c.id}`}
                    data-verdict={v}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr auto',
                      gap: 'var(--space-3)',
                      alignItems: 'flex-start',
                      padding: 'var(--space-3) var(--space-4)',
                      background: 'var(--surface-1)',
                      border: '1px solid var(--stroke-1)',
                      borderLeft: `2px solid ${
                        v === 'pass'   ? 'var(--sig-ok)' :
                        v === 'fail'   ? 'var(--sig-crit)' :
                        v === 'review' ? 'var(--sig-gold)' :
                        'var(--stroke-2)'}`,
                      borderRadius: 'var(--radius-2)',
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)', lineHeight: 1.4 }}>
                        {c.headline}
                      </div>
                      <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)', lineHeight: 1.5 }}>
                        {c.detail}
                      </div>
                      {c.reference && (
                        <div
                          style={{
                            fontFamily: 'ui-monospace, monospace',
                            fontSize: 10, color: 'var(--content-lo)',
                            textTransform: 'uppercase', letterSpacing: '0.06em',
                          }}
                        >
                          {c.reference}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {(['pass', 'review', 'fail', 'unset'] as EvalVerdict[]).map((opt) => (
                        <button
                          key={opt}
                          data-testid={`eval-verdict-${c.id}-${opt}`}
                          aria-pressed={v === opt}
                          onClick={() => setVerdict(c.id, opt)}
                          style={verdictBtn(v === opt, opt)}
                        >
                          {verdictLabel[opt]}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}

      {/* Notes */}
      <SignatureFrame tone="info" caption="Walk-through notes">
        <textarea
          data-testid="eval-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any refinements to author as D-series or E-series addenda before Design Freeze."
          rows={5}
          style={{
            width: '100%',
            resize: 'vertical',
            background: 'var(--surface-2)',
            color: 'var(--content-hi)',
            border: '1px solid var(--stroke-2)',
            borderRadius: 'var(--radius-1)',
            padding: 'var(--space-3)',
            fontFamily: 'inherit',
            fontSize: 'var(--font-body-sm)',
            lineHeight: 1.5,
          }}
        />
      </SignatureFrame>

      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        <button
          data-testid="eval-back-mission"
          onClick={() => nav('/c/mission')}
          style={secondaryBtn}
        >
          ← back to Mission Control
        </button>
      </div>
    </div>
  );
};

const secondaryBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  background: 'transparent',
  color: 'var(--content-md)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-1)',
  padding: '4px 10px',
  fontSize: 'var(--font-caption)',
  fontFamily: 'ui-monospace, monospace',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  cursor: 'pointer',
};

const verdictBtn = (active: boolean, verdict: EvalVerdict): React.CSSProperties => {
  const activeBg =
    verdict === 'pass'   ? 'var(--sig-ok)' :
    verdict === 'fail'   ? 'var(--sig-crit)' :
    verdict === 'review' ? 'var(--sig-gold)' :
    'var(--surface-3)';
  return {
    background: active ? activeBg : 'var(--surface-2)',
    color: active ? 'var(--surface-0)' : 'var(--content-md)',
    border: `1px solid ${active ? activeBg : 'var(--stroke-2)'}`,
    borderRadius: 'var(--radius-1)',
    padding: '4px 8px',
    fontFamily: 'ui-monospace, monospace',
    fontSize: 'var(--font-caption)',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    cursor: 'pointer',
    minWidth: 60,
  };
};
