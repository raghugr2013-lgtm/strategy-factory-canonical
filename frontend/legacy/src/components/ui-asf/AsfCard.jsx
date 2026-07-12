/**
 * ASF · AsfCard — Phase U-1 (C-09)
 * ----------------------------------------------------------------------------
 * Card with 1 px border, 6 px radius, no shadow, no glass.
 *
 * Wraps existing shadcn Card semantics but binds to the ASF token sheet.
 * Use AsfCard for new ASF surfaces inside the command shell. The legacy
 * `shadcn Card` remains untouched for the rest of the codebase.
 *
 * Tokens consumed: --asf-bg-surface, --asf-border-default,
 *                  --asf-border-emphasized (hover), --asf-radius-card,
 *                  --asf-text-primary, --asf-font-sans, --asf-space-*.
 */
import React from 'react';

export const AsfCard = React.forwardRef(function AsfCard(
  { children, className = '', testId, hoverable = true, ...rest }, ref,
) {
  return (
    <div
      ref={ref}
      className={`asf-card ${hoverable ? '' : 'asf-card--static'} ${className}`.trim()}
      data-testid={testId || 'asf-card'}
      {...rest}
    >
      {children}
    </div>
  );
});

export function AsfCardHeader({ children, className = '', testId, ...rest }) {
  return (
    <div
      className={`asf-card__hd ${className}`.trim()}
      data-testid={testId || 'asf-card-header'}
      {...rest}
    >
      {children}
    </div>
  );
}

export function AsfCardBody({ children, className = '', testId, ...rest }) {
  return (
    <div
      className={`asf-card__body ${className}`.trim()}
      data-testid={testId || 'asf-card-body'}
      {...rest}
    >
      {children}
    </div>
  );
}

export default AsfCard;
