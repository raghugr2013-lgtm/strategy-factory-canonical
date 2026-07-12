/**
 * Theme tokens — dual design system.
 *
 *   Light → BlockDAG-inspired clean SaaS
 *   Dark  → Binance-inspired trading terminal
 *
 * These objects are the single source of truth for the CSS variables
 * exposed in `index.css`. If you change a value here, update the matching
 * `--*` variable block. JS consumers (charts, inline styles, etc.) can
 * import this file directly and read colours without hitting the DOM.
 */

export const lightTheme = {
  name: 'light',

  // Surfaces — TRUE LIGHT (cool-gray canvas + white cards)
  bg:      '#F4F7FB',
  card:    '#FFFFFF',
  elevated:'#F9FBFF',
  sunken:  '#F1F5F9',

  // Text — strong contrast on white
  text:    '#0F172A',
  subtext: '#475569',
  muted:   '#94A3B8',

  // Borders
  border:        '#E2E8F0',
  borderMuted:   '#CBD5E1',
  borderStrong:  '#94A3B8',

  // Brand + semantic
  primary:    '#4F46E5',
  primaryDim: '#4338CA',
  success:    '#22C55E',
  warning:    '#F59E0B',
  danger:     '#EF4444',

  // Chart palette (qualitative)
  charts: ['#4F46E5', '#0EA5E9', '#22C55E', '#F59E0B', '#EF4444', '#A855F7'],
};

export const darkTheme = {
  name: 'dark',

  // Surfaces (Binance-inspired palette)
  bg:      '#0B0E11',
  card:    '#1E2329',
  elevated:'#2B3139',
  sunken:  '#080C11',

  // Text
  text:    '#EAECEF',
  subtext: '#848E9C',
  muted:   '#5E6673',

  // Borders
  border:        '#2B3139',
  borderMuted:   '#374151',
  borderStrong:  '#4B5563',

  // Brand + semantic (Binance palette)
  primary:    '#F0B90B',   // signature gold
  primaryDim: '#CA9A08',
  success:    '#0ECB81',
  warning:    '#F0B90B',
  danger:     '#F6465D',

  // Charts / data viz
  charts: ['#F0B90B', '#03A9F4', '#0ECB81', '#FF9800', '#F6465D', '#A855F7'],
};

export const themes = { light: lightTheme, dark: darkTheme };

/** Hex #RRGGBB → "R G B" triplet string, ready for `rgb(var(--x) / a)`. */
export function hexToRgbTriplet(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3
    ? h.split('').map((c) => c + c).join('')
    : h, 16);
  // eslint-disable-next-line no-bitwise
  return `${(n >> 16) & 0xFF} ${(n >> 8) & 0xFF} ${n & 0xFF}`;
}
