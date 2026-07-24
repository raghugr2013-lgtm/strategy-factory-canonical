/*
 * EvaluationHarness — Phase D2: interactions unlocked.
 *
 * D1 shipped the read-only visualization. D2 is a PURE UNLOCK — the
 * layout, testids, styles, and route are unchanged. The only diff is:
 *
 *   • Verdict buttons wire to setVerdict(criterionId, verdict).
 *   • Session-label input wires to setSession(str).
 *   • Notes textarea wires to setNotes(str).
 *   • Reset button wires to clearAll().
 *   • Mark-all-pass button wires to markAllPass().
 *   • Disabled / readOnly / aria-disabled attributes removed.
 *   • D2 tooltip removed.
 *
 * The store, DIMENSIONS catalogue, and derived helpers
 * (summariseDimension / overallReadiness) are the same file that D1
 * used — no store refactor was needed because D1 pre-declared all five
 * mutators.
 *
 * Architecture (see /app/docs/PHASE_D1_ARCHITECTURE.md · unchanged):
 *
 *     AppRouter (/c/evaluation)
 *          │
 *          ▼
 *     EvaluationHarness.jsx  ← this file
 *          │
 *          ├── useEvaluationStore  (read + write; persisted to
 *          │                        localStorage sf.eval.v1)
 *          │       └── DIMENSIONS  (24-criterion catalogue)
 *          │       └── summariseDimension / overallReadiness (derived)
 *          │
 *          ├── primitives/  (SurfaceHeader · SignatureFrame · Chip)
 *          │
 *          └── react-router  (useNavigate → back to /c/mission)
 *
 * No backend adapters. No API calls. Client-only surface.
 */
import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles, Compass, Activity as ActivityIcon, Layers, Timer,
  ShieldCheck, Fingerprint, ChevronRight, RotateCcw, ClipboardCheck,
} from 'lucide-react';
import { SurfaceHeader } from '../primitives/SurfaceHeader';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { Chip } from '../primitives/Chip';
import {
  useEvaluationStore, DIMENSIONS,
  summariseDimension, overallReadiness,
} from '../workspace-state/evaluationStore';

const VERDICT_ORDER = ['pass', 'review', 'fail', 'unset'];

const verdictLabel = {
  pass: 'pass', review: 'review', fail: 'fail', unset: 'unset',
};
const verdictTone = {
  pass: 'ok', review: 'advisory', fail: 'crit', unset: 'info',
};

const DIM_ICON = {
  'discoverability':           Compass,
  'navigation-predictability': ActivityIcon,
  'cognitive-load':            Layers,
  'interaction-rhythm':        Timer,
  'trust':                     ShieldCheck,
  'identity':                  Fingerprint,
};

const READINESS_TONE = {
  ready:     { tone: 'ok' },
  nearly:    { tone: 'info' },
  blocked:   { tone: 'crit' },
  unstarted: { tone: 'advisory' },
};

export const EvaluationHarness = () => {
  const nav = useNavigate();
  // D2 unlock: bind read AND write. Store mutators persist to localStorage.
  const verdicts     = useEvaluationStore((s) => s.verdicts);
  const notes        = useEvaluationStore((s) => s.notes);
  const session      = useEvaluationStore((s) => s.session);
  const setVerdict   = useEvaluationStore((s) => s.setVerdict);
  const setNotes     = useEvaluationStore((s) => s.setNotes);
  const setSession   = useEvaluationStore((s) => s.setSession);
  const clearAll     = useEvaluationStore((s) => s.clearAll);
  const markAllPass  = useEvaluationStore((s) => s.markAllPass);

  const summaries = useMemo(
    () => DIMENSIONS.map((d) => summariseDimension(d, verdicts)),
    [verdicts],
  );
  const readiness = useMemo(() => overallReadiness(verdicts), [verdicts]);
  const rt = READINESS_TONE[readiness.verdict];

  return (
    <section
      data-testid="evaluation-harness"
      data-phase="d2"
      style={{
        padding: 'var(--space-6) var(--space-5)', maxWidth: 1200,
        display: 'flex', flexDirection: 'column', gap: 'var(--space-6)',
      }}
    >
      <SurfaceHeader
        eyebrow="Evaluation Harness · Interactive Prototype Gate"
        headline="Six dimensions. One walkable checklist. Design Freeze on the far side."
        briefing="Walk each surface with the criteria below. Mark pass / review / fail as you go — the overall readiness verdict updates live and is the go/no-go signal for Design Freeze declaration."
        status="P0 §9 · 6 dimensions · 24 criteria"
        testId="eval-header"
      />

      {/* Session controls */}
      <div
        data-testid="eval-controls"
        style={{
          display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)',
          alignItems: 'center',
        }}
      >
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
          type="button"
          onClick={clearAll}
          style={secondaryBtn(false)}
        >
          <RotateCcw size={12} /> reset verdicts
        </button>
        <button
          data-testid="eval-mark-all-pass"
          type="button"
          onClick={markAllPass}
          title="Diagnostic-only shortcut; use only when every criterion has been verified."
          style={secondaryBtn(false)}
        >
          <ClipboardCheck size={12} /> mark all pass
        </button>
      </div>

      {/* Overall readiness card */}
      <SignatureFrame
        tone={rt.tone}
        icon={Sparkles}
        caption={`Overall readiness · ${readiness.verdict.toUpperCase()}`}
        testId="eval-readiness-frame"
      >
        <div
          data-testid="eval-readiness"
          data-verdict={readiness.verdict}
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
        >
          <div
            data-testid="eval-readiness-headline"
            style={{
              fontSize: 'var(--font-h2)', color: 'var(--content-hi)',
              fontWeight: 500, lineHeight: 1.2,
            }}
          >
            {readiness.headline}
          </div>
          <div
            data-testid="eval-readiness-detail"
            style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.5 }}
          >
            {readiness.detail}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}>
            <Chip tone="ok"       label={`${readiness.pass} pass`}    showGlyph={false} testId="eval-count-pass" />
            <Chip tone="advisory" label={`${readiness.review} review`} showGlyph={false} testId="eval-count-review" />
            <Chip tone="crit"     label={`${readiness.fail} fail`}    showGlyph={false} testId="eval-count-fail" />
            <Chip tone="info"     label={`${readiness.unset} unset`}  showGlyph={false} testId="eval-count-unset" />
            <span
              className="mono-num"
              data-testid="eval-readiness-pct"
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
            const t = verdictTone[s.verdict];
            const borderColor =
              t === 'ok'       ? 'var(--sig-ok)' :
              t === 'crit'     ? 'var(--sig-crit)' :
              t === 'advisory' ? 'var(--accent-gold)' :
                                 'var(--sig-info)';
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
                  borderLeft: `2px solid ${borderColor}`,
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
                  {I ? <I size={12} /> : null} {s.title}
                  <ChevronRight size={12} style={{ marginLeft: 'auto' }} />
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <Chip tone={verdictTone[s.verdict]} label={verdictLabel[s.verdict]} showGlyph={false}
                        testId={`eval-summary-verdict-${s.key}`} />
                  <span className="mono-num"
                        style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)' }}>
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

      {/* Per-dimension checklists (24 criteria total) */}
      {DIMENSIONS.map((d) => {
        const I = DIM_ICON[d.key];
        const s = summaries.find((x) => x.key === d.key);
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
                {I ? <I size={12} /> : null} Dimension · {d.title}
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
              data-testid={`eval-dim-${d.key}-purpose`}
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
                const borderColor =
                  v === 'pass'   ? 'var(--sig-ok)' :
                  v === 'fail'   ? 'var(--sig-crit)' :
                  v === 'review' ? 'var(--accent-gold)' :
                                   'var(--stroke-2)';
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
                      borderLeft: `2px solid ${borderColor}`,
                      borderRadius: 'var(--radius-2)',
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div
                        data-testid={`eval-criterion-${c.id}-headline`}
                        style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)', lineHeight: 1.4 }}
                      >
                        {c.headline}
                      </div>
                      <div
                        data-testid={`eval-criterion-${c.id}-detail`}
                        style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)', lineHeight: 1.5 }}
                      >
                        {c.detail}
                      </div>
                      {c.reference && (
                        <div
                          data-testid={`eval-criterion-${c.id}-reference`}
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
                    <div
                      data-testid={`eval-verdict-group-${c.id}`}
                      role="group"
                      aria-label={`Verdict for ${c.headline}`}
                      style={{ display: 'flex', gap: 4 }}
                    >
                      {VERDICT_ORDER.map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          data-testid={`eval-verdict-${c.id}-${opt}`}
                          aria-pressed={v === opt}
                          onClick={() => setVerdict(c.id, opt)}
                          style={verdictBtn(v === opt, opt, false)}
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
      <SignatureFrame tone="info" caption="Walk-through notes" testId="eval-notes-frame">
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
          type="button"
          onClick={() => nav('/c/mission')}
          style={secondaryBtn(false)}
        >
          ← back to Mission Control
        </button>
      </div>
    </section>
  );
};

// ─── styles ──────────────────────────────────────────────────────────────
const secondaryBtn = (isDisabled) => ({
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
  cursor: isDisabled ? 'not-allowed' : 'pointer',
  opacity: isDisabled ? 0.5 : 1,
});

const verdictBtn = (active, verdict, isDisabled) => {
  const activeBg =
    verdict === 'pass'   ? 'var(--sig-ok)' :
    verdict === 'fail'   ? 'var(--sig-crit)' :
    verdict === 'review' ? 'var(--accent-gold)' :
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
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    minWidth: 60,
    opacity: isDisabled ? 0.55 : 1,
  };
};

export default EvaluationHarness;
