/*
 * Motion presets — Bible §6.1.
 * refs DESIGN_FREEZE_v1.0.md §1.2 (motion tokens · reduced-motion honour)
 * refs prototype/src/primitives/motion.ts
 */
import { useInspectorStore } from '../workspace-state/inspectorStore';

export const useMotionEnabled = () => {
  const forced = useInspectorStore((s) => s.reducedMotion);
  if (forced) return false;
  if (typeof window === 'undefined') return true;
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
};

const t = (ms) => ({ duration: ms / 1000, ease: [0.4, 0, 0.2, 1] });

export const fadeInUp = {
  hidden: { opacity: 0, y: 4 },
  visible: { opacity: 1, y: 0, transition: t(200) },
};
export const fadeIn = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: t(120) },
};
export const drawerSlide = {
  hidden: { opacity: 0, x: 24 },
  visible: { opacity: 1, x: 0, transition: t(320) },
};
export const stagger = (delay = 30) => ({
  hidden: {},
  visible: { transition: { staggerChildren: delay / 1000 } },
});
