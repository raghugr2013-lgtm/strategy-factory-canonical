/*
 * Motion presets — Bible §6.1.
 * Prototype uses framer-motion sparingly to validate interaction rhythm.
 * Reduced-motion is honoured both via CSS (tokens.css) and via the inspector.
 */
import type { Transition, Variants } from 'framer-motion';
import { useInspectorStore } from '../workspace-state/inspectorStore';

export const useMotionEnabled = () => {
  const forced = useInspectorStore((s) => s.reducedMotion);
  if (forced) return false;
  if (typeof window === 'undefined') return true;
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
};

const t = (ms: number): Transition => ({
  duration: ms / 1000,
  ease: [0.4, 0, 0.2, 1],
});

export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 4 },
  visible: { opacity: 1, y: 0, transition: t(200) },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: t(120) },
};

export const drawerSlide: Variants = {
  hidden: { opacity: 0, x: 24 },
  visible: { opacity: 1, x: 0, transition: t(320) },
};

export const stagger = (delay = 30): Variants => ({
  hidden: {},
  visible: { transition: { staggerChildren: delay / 1000 } },
});
