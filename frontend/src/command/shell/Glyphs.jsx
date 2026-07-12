/**
 * COMMAND · Phase U.1 — Iconography (CSS-drawn glyphs)
 * ----------------------------------------------------------------------------
 * 20×20 SVG glyphs for the 10 modules + utility glyphs. Zero asset deps.
 * Stroke uses currentColor so colour comes from token state (hover/active).
 */
import React from 'react';

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.4,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

export function GlyphDashboard() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <circle cx="10" cy="10" r="2" {...stroke} />
      <circle cx="10" cy="10" r="6" {...stroke} strokeDasharray="2 2" />
    </svg>
  );
}
export function GlyphLab() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <path d="M8 3v4l-3 7a3 3 0 0 0 2.7 4.3h4.6A3 3 0 0 0 15 14l-3-7V3" {...stroke} />
      <path d="M7 3h6" {...stroke} />
    </svg>
  );
}
export function GlyphExplorer() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <circle cx="10" cy="4" r="1.6" {...stroke} />
      <circle cx="5"  cy="14" r="1.6" {...stroke} />
      <circle cx="15" cy="14" r="1.6" {...stroke} />
      <path d="M10 5.6L5 12.6M10 5.6L15 12.6" {...stroke} />
    </svg>
  );
}
export function GlyphMutate() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <path d="M5 3c5 4 5 10 10 14M5 17c5-4 5-10 10-14" {...stroke} />
    </svg>
  );
}
export function GlyphPortfolio() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <rect x="3"  y="3"  width="6" height="6" rx="1" {...stroke} />
      <rect x="11" y="3"  width="6" height="6" rx="1" {...stroke} />
      <rect x="3"  y="11" width="6" height="6" rx="1" {...stroke} />
      <rect x="11" y="11" width="6" height="6" rx="1" {...stroke} />
    </svg>
  );
}
export function GlyphPropFirm() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <path d="M10 3l6 2.5v4.5c0 4-2.7 6.5-6 7-3.3-.5-6-3-6-7V5.5L10 3z" {...stroke} />
    </svg>
  );
}
export function GlyphExec() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <path d="M11 3L5 11h4l-1 6 6-8h-4l1-6z" {...stroke} />
    </svg>
  );
}
export function GlyphAI() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <circle cx="10" cy="10" r="2.5" {...stroke} />
      <circle cx="4"  cy="5"  r="1.4" {...stroke} />
      <circle cx="16" cy="5"  r="1.4" {...stroke} />
      <circle cx="4"  cy="15" r="1.4" {...stroke} />
      <circle cx="16" cy="15" r="1.4" {...stroke} />
      <path d="M5  6 L8  9 M15 6 L12 9 M5 14 L8 11 M15 14 L12 11" {...stroke} />
    </svg>
  );
}
export function GlyphDiag() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <path d="M3 10h3l2-5 4 10 2-5h3" {...stroke} />
    </svg>
  );
}
export function GlyphGovernance() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <circle cx="10" cy="10" r="7" {...stroke} />
      <path d="M10 3v7l4 2" {...stroke} />
    </svg>
  );
}

/* Utility glyphs */
export function GlyphMenu() {
  return (
    <svg width="18" height="18" viewBox="0 0 20 20">
      <path d="M3 6h14M3 10h14M3 14h14" {...stroke} />
    </svg>
  );
}
export function GlyphFocus() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20">
      <path d="M3 7V4h3M17 7V4h-3M3 13v3h3M17 13v3h-3" {...stroke} />
      <circle cx="10" cy="10" r="2" {...stroke} />
    </svg>
  );
}
export function GlyphSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20">
      <circle cx="9" cy="9" r="5" {...stroke} />
      <path d="M13 13l4 4" {...stroke} />
    </svg>
  );
}
/* U.5.a — Tactical density toggle.
   Two-state glyph: when comfortable, draws wider-spaced bars (3 rows · 4px gap).
   When compact, the CSS class .cmd-density-on collapses the gap to 2px via
   currentColor — we keep both states visually identical at SVG level for
   simplicity; tonal change comes from the button's --cyan accent. */
export function GlyphDensity() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20">
      <path d="M3 5h14M3 10h14M3 15h14" {...stroke} />
    </svg>
  );
}
/* U.6.a — Premium toggle glyph. Layered diamond hint (depth metaphor). */
export function GlyphPremium() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20">
      <path d="M10 3l5 4-5 4-5-4 5-4z" {...stroke} />
      <path d="M5 11l5 4 5-4" {...stroke} />
    </svg>
  );
}


/* RC1 parity closure — Master Bot · controller-with-fleet-orbit metaphor. */
export function GlyphMasterBot() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <rect x="6" y="6" width="8" height="8" rx="2" {...stroke} />
      <path d="M10 6V3M10 17v-3M6 10H3M17 10h-3" {...stroke} />
      <circle cx="10" cy="10" r="1.2" {...stroke} />
    </svg>
  );
}

/* RC1 parity closure — Admin · key-and-ring metaphor. */
export function GlyphAdmin() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <circle cx="7" cy="10" r="3" {...stroke} />
      <path d="M10 10h7M14 10v3M17 10v2" {...stroke} />
    </svg>
  );
}

/* RC1 parity closure — Scaling · vertical bars ascending. */
export function GlyphScaling() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20">
      <path d="M4 16V12M9 16V9M14 16V6" {...stroke} />
      <path d="M3 17h14" {...stroke} />
    </svg>
  );
}
