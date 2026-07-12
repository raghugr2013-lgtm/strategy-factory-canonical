/**
 * ASF · AsfTable — Phase U-2 (C-08 token-driven table primitive)
 * ----------------------------------------------------------------------------
 * Lightweight wrapper around a native <table> that applies the ASF table
 * tokens (sticky header, 36 px rows, no zebra, mono numeric cells, sans
 * label cells, hairline borders). Drop-in replacement for legacy `<table>`
 * blocks inside the command shell.
 *
 * Usage:
 *   <AsfTable testId="strategy-table">
 *     <AsfTableHead>
 *       <AsfTableRow>
 *         <AsfTableHeader>Strategy</AsfTableHeader>
 *         <AsfTableHeader align="right">Best PF</AsfTableHeader>
 *       </AsfTableRow>
 *     </AsfTableHead>
 *     <AsfTableBody>
 *       <AsfTableRow>
 *         <AsfTableCell>EURUSD_H1_mean_revert</AsfTableCell>
 *         <AsfTableCell numeric>1.27</AsfTableCell>
 *       </AsfTableRow>
 *     </AsfTableBody>
 *   </AsfTable>
 *
 * Tokens consumed: --asf-bg-surface, --asf-border-default,
 *                  --asf-text-primary / --asf-text-secondary, --asf-font-mono,
 *                  --asf-row-default, --asf-pad-default.
 */
import React from 'react';

export default function AsfTable({ children, className = '', testId = 'asf-table', ...rest }) {
  return (
    <div className="asf-table-wrap" data-testid={testId}>
      <table className={`asf-table ${className}`.trim()} {...rest}>
        {children}
      </table>
    </div>
  );
}

export function AsfTableHead({ children }) {
  return <thead className="asf-table__head">{children}</thead>;
}

export function AsfTableBody({ children }) {
  return <tbody className="asf-table__body">{children}</tbody>;
}

export function AsfTableRow({ children, onClick, className = '', testId, ...rest }) {
  return (
    <tr
      className={`asf-table__row ${className}`.trim()}
      onClick={onClick}
      data-testid={testId}
      {...rest}
    >
      {children}
    </tr>
  );
}

export function AsfTableHeader({ children, align = 'left', className = '', ...rest }) {
  return (
    <th
      className={`asf-table__th ${className}`.trim()}
      data-align={align}
      {...rest}
    >
      {children}
    </th>
  );
}

export function AsfTableCell({ children, numeric = false, align, className = '', ...rest }) {
  const a = align || (numeric ? 'right' : 'left');
  return (
    <td
      className={`asf-table__td ${numeric ? 'asf-mono' : ''} ${className}`.trim()}
      data-align={a}
      {...rest}
    >
      {children}
    </td>
  );
}

export { AsfTable };
