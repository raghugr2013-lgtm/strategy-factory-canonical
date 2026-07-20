/*
 * EvidenceDrawer — Bible §10.
 * Right-side sliding surface that shows the receipts behind any artefact.
 * Header · ProvenanceTriple · LineageBar · body sections (Metrics / Data / Notes).
 * Esc closes; overlay click closes. Context Never Lost preserved on the base surface.
 */
import { motion, AnimatePresence } from 'framer-motion';
import { X, FileText, AlertTriangle, MinusCircle } from 'lucide-react';
import { useEffect } from 'react';
import { useMotionEnabled, drawerSlide, fadeIn } from './motion';
import { ProvenanceTriple, type ProvenanceTripleProps } from './ProvenanceTriple';
import { LineageBar, type LineageNode } from './LineageBar';
import { StateTemplate } from './StateTemplate';

export type EvidenceState = 'happy' | 'loading' | 'empty' | 'error';

export interface EvidenceSection {
  heading: string;
  body: React.ReactNode;
}

export interface EvidenceDrawerAction {
  label: string;
  onClick: () => void;
  testId?: string;
}

export interface EvidenceDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  provenance: ProvenanceTripleProps;
  lineage: { self: LineageNode; ancestors?: LineageNode[]; descendants?: LineageNode[] };
  sections?: EvidenceSection[];
  state?: EvidenceState;
  footerAction?: EvidenceDrawerAction;
  testId?: string;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  open, onClose, title, subtitle, provenance, lineage, sections = [], state = 'happy', footerAction, testId,
}) => {
  const motionEnabled = useMotionEnabled();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            data-testid={`${testId ?? 'evidence-drawer'}-overlay`}
            initial="hidden" animate="visible" exit="hidden"
            variants={motionEnabled ? fadeIn : { hidden: { opacity: 1 }, visible: { opacity: 1 } }}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(5,7,10,0.6)',
              backdropFilter: 'blur(4px)', zIndex: 40,
            }}
            onClick={onClose}
          />
          <motion.aside
            data-testid={testId ?? 'evidence-drawer'}
            role="dialog" aria-label={`Evidence · ${title}`}
            initial="hidden" animate="visible" exit="hidden"
            variants={motionEnabled ? drawerSlide : { hidden: { opacity: 1, x: 0 }, visible: { opacity: 1, x: 0 } }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(560px, 90vw)',
              background: 'var(--surface-1)',
              borderLeft: '1px solid var(--stroke-2)',
              boxShadow: 'var(--elev-2)',
              zIndex: 50,
              display: 'flex', flexDirection: 'column',
            }}
          >
            <header
              style={{
                display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
                gap: 'var(--space-3)',
                padding: 'var(--space-4) var(--space-5)',
                borderBottom: '1px solid var(--stroke-1)',
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                  }}
                >
                  Evidence
                </div>
                <div style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)', marginTop: 4 }}>
                  {title}
                </div>
                {subtitle && (
                  <div className="mono-num" style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)', marginTop: 4 }}>
                    {subtitle}
                  </div>
                )}
              </div>
              <button
                data-testid="evidence-drawer-close"
                aria-label="Close evidence drawer"
                onClick={onClose}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--stroke-2)',
                  color: 'var(--content-md)',
                  borderRadius: 'var(--radius-1)',
                  padding: 4,
                  cursor: 'pointer',
                }}
              >
                <X size={14} />
              </button>
            </header>

            <div
              style={{
                overflowY: 'auto',
                padding: 'var(--space-4) var(--space-5)',
                display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
              }}
            >
              <ProvenanceTriple {...provenance} />
              <LineageBar {...lineage} />

              {state === 'error' ? (
                <StateTemplate
                  variant="error" code="evidence-error" icon={AlertTriangle} tone="crit"
                  headline="Evidence unavailable."
                  purpose="The evidence store returned an error."
                />
              ) : state === 'empty' ? (
                <StateTemplate
                  variant="empty" code="evidence-empty" icon={MinusCircle} tone="dormant"
                  headline="No sections attached."
                  purpose="This artefact has provenance but no attached notes yet."
                />
              ) : state === 'loading' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  {[0,1,2].map((i) => (
                    <div key={i}
                      aria-hidden="true"
                      style={{
                        height: 40,
                        background: 'linear-gradient(90deg, var(--surface-2) 0%, var(--surface-3) 50%, var(--surface-2) 100%)',
                        backgroundSize: '200% 100%',
                        animation: 'sf-skeleton 1.6s var(--ease-standard) infinite',
                        borderRadius: 'var(--radius-2)',
                      }}
                    />
                  ))}
                </div>
              ) : (
                sections.map((s) => (
                  <section key={s.heading} data-testid={`evidence-section-${s.heading.replace(/\W+/g, '-').toLowerCase()}`}>
                    <div
                      style={{
                        fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                        textTransform: 'uppercase', letterSpacing: '0.08em',
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                        marginBottom: 'var(--space-2)',
                      }}
                    >
                      <FileText size={12} /> {s.heading}
                    </div>
                    <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.5 }}>
                      {s.body}
                    </div>
                  </section>
                ))
              )}
            </div>

            {footerAction && (
              <footer
                style={{
                  padding: 'var(--space-3) var(--space-5)',
                  borderTop: '1px solid var(--stroke-1)',
                  display: 'flex', justifyContent: 'flex-end',
                }}
              >
                <button
                  data-testid={footerAction.testId ?? 'evidence-drawer-footer-action'}
                  onClick={footerAction.onClick}
                  style={{
                    background: 'var(--sig-info)',
                    color: 'var(--surface-0)',
                    border: 'none',
                    borderRadius: 'var(--radius-1)',
                    padding: '8px 14px',
                    fontSize: 'var(--font-body-sm)',
                    fontFamily: 'inherit',
                    cursor: 'pointer',
                  }}
                >
                  {footerAction.label} →
                </button>
              </footer>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
};
