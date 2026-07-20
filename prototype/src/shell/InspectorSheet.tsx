/*
 * InspectorSheet — PROTOTYPE ONLY.
 * A floating right-side sheet reachable from every surface via the "PROTO"
 * button in the header. Wraps the existing Inspector component so scenario
 * presets and state toggles are one keystroke away during walkthroughs.
 * Removed at Design Freeze.
 */
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useEffect } from 'react';
import { Inspector } from '../gallery/Inspector';
import { useInspectorStore } from '../workspace-state/inspectorStore';
import { useMotionEnabled, drawerSlide, fadeIn } from '../primitives/motion';

export const InspectorSheet: React.FC = () => {
  const { showSheet, setShowSheet } = useInspectorStore();
  const motionEnabled = useMotionEnabled();

  useEffect(() => {
    if (!showSheet) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowSheet(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showSheet, setShowSheet]);

  return (
    <AnimatePresence>
      {showSheet && (
        <>
          <motion.div
            data-testid="inspector-sheet-overlay"
            initial="hidden" animate="visible" exit="hidden"
            variants={motionEnabled ? fadeIn : { hidden: { opacity: 1 }, visible: { opacity: 1 } }}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(5,7,10,0.55)',
              backdropFilter: 'blur(4px)', zIndex: 40,
            }}
            onClick={() => setShowSheet(false)}
          />
          <motion.aside
            data-testid="inspector-sheet"
            role="dialog" aria-label="Prototype inspector"
            initial="hidden" animate="visible" exit="hidden"
            variants={motionEnabled ? drawerSlide : { hidden: { opacity: 1, x: 0 }, visible: { opacity: 1, x: 0 } }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0,
              width: 'min(320px, 92vw)',
              background: 'var(--surface-1)',
              borderLeft: '1px solid var(--stroke-2)',
              boxShadow: 'var(--elev-2)',
              zIndex: 50,
              display: 'flex', flexDirection: 'column',
              overflowY: 'auto',
            }}
          >
            <header
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: 'var(--space-3) var(--space-4)',
                borderBottom: '1px solid var(--stroke-1)',
              }}
            >
              <span
                style={{
                  fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                  textTransform: 'uppercase', letterSpacing: '0.08em',
                }}
              >
                Prototype inspector
              </span>
              <button
                data-testid="inspector-sheet-close"
                aria-label="Close inspector"
                onClick={() => setShowSheet(false)}
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
            <div style={{ padding: 'var(--space-3)', flex: 1 }}>
              <Inspector />
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
};
