/*
 * SurfaceHeader — PROTOTYPE ONLY helper.
 * Consistent H1 anatomy: eyebrow · headline · optional briefing paragraph.
 * Every surface opens with purpose per Bible §2.1 "Purpose Before Status".
 */
export interface SurfaceHeaderProps {
  eyebrow: string;
  headline: string;
  briefing?: string;
  status?: string;   // mono trailer
  testId?: string;
}

export const SurfaceHeader: React.FC<SurfaceHeaderProps> = ({
  eyebrow, headline, briefing, status, testId,
}) => (
  <header
    data-testid={testId ?? 'surface-header'}
    style={{
      display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
      maxWidth: '76ch',
    }}
  >
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
        fontSize: 'var(--font-caption)',
        color: 'var(--content-lo)',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}
    >
      <span>{eyebrow}</span>
      {status && (
        <>
          <span aria-hidden="true">·</span>
          <span className="mono-num">{status}</span>
        </>
      )}
    </div>
    <h1
      style={{
        margin: 0,
        fontSize: 'var(--font-h2)',
        fontWeight: 500,
        color: 'var(--content-hi)',
        lineHeight: 1.2,
      }}
    >
      {headline}
    </h1>
    {briefing && (
      <p
        style={{
          margin: 0,
          fontSize: 'var(--font-body-sm)',
          color: 'var(--content-md)',
          lineHeight: 1.5,
        }}
      >
        {briefing}
      </p>
    )}
  </header>
);
