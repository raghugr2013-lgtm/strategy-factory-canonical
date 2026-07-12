/**
 * COMMAND · Phase U.0 — BrandMark
 * ----------------------------------------------------------------------------
 * The institutional brand mark that replaces the ⚡ emoji + Binance-gold
 * "v10" pill. Pure SVG, no asset. 22×22. Reads as a "control grid":
 *
 *      ░░░░░░░░░░░░░░░░
 *      ▢ ▢ ▢ ▢ ▢ ▢
 *      ▢ ▢ ▢ ▢ ▢ ▢
 *      ▢ ▢ ▢ ▢ ▢ ▣      ← one cell lit cyan (top-right "active control")
 *      ▢ ▢ ▢ ▢ ▢ ▢
 *      ▢ ▢ ▢ ▢ ▢ ▢      one or two muted-violet cells (AI memory)
 *
 * Used inside the CommandBar (Phase U.1). U.0 ships it so the brand
 * identity is locked and tested before the shell lands.
 */
import React from 'react';

export default function BrandMark({ size = 22, glow = true }) {
  const tile = 3;          // tile size (px in viewBox units)
  const gap  = 1;          // gap between tiles
  const cols = 4;
  const rows = 3;
  const offX = 1;
  const offY = 2;

  // Lit cell pattern — top-right cyan + two muted violet "memory" cells
  // The pattern is deterministic so the mark renders identically every load.
  const cyanCell   = { r: 0, c: 3 };          // top-right
  const violetCells = [{ r: 2, c: 0 }, { r: 1, c: 1 }];

  const cells = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      let fill = 'var(--cmd-surface-3, #1A2334)';
      let strokeOpacity = 0.5;
      let filter = undefined;
      if (cyanCell.r === r && cyanCell.c === c) {
        fill = 'var(--cmd-cyan, #00D4FF)';
        strokeOpacity = 1;
        if (glow) filter = 'url(#cmd-brand-glow)';
      } else if (violetCells.some((v) => v.r === r && v.c === c)) {
        fill = 'var(--cmd-violet, #7C5CFF)';
        strokeOpacity = 0.85;
      }
      cells.push(
        <rect
          key={`${r}-${c}`}
          x={offX + c * (tile + gap)}
          y={offY + r * (tile + gap)}
          width={tile}
          height={tile}
          rx={0.6}
          fill={fill}
          stroke="rgba(255,255,255,0.04)"
          strokeOpacity={strokeOpacity}
          filter={filter}
        />,
      );
    }
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 22 22"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Strategy Factory"
      role="img"
      data-testid="brand-mark"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <defs>
        <filter id="cmd-brand-glow" x="-200%" y="-200%" width="500%" height="500%">
          <feGaussianBlur stdDeviation="0.9" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* faint frame to anchor the glyph */}
      <rect
        x="0.5"
        y="0.5"
        width="21"
        height="21"
        rx="3"
        fill="var(--cmd-surface-1, #0E141F)"
        stroke="var(--cmd-hairline, #1F2A3B)"
        strokeWidth="1"
      />
      {cells}
    </svg>
  );
}
