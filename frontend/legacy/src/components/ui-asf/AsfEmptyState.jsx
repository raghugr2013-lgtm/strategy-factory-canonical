/**
 * ASF · AsfEmptyState — Phase U-1 (C-12)
 * ----------------------------------------------------------------------------
 * Empty-state primitive: icon · one-line title · explanation · next-action
 * button · optional doc link.
 *
 * Tokens consumed: --asf-bg-surface, --asf-border-default,
 *                  --asf-text-secondary, --asf-accent-primary.
 */
import React from 'react';

export default function AsfEmptyState({
  title,
  body,
  icon,
  action,            // { label, onClick, testId? }
  doc,               // { label, href, testId? }
  slug = 'empty',
  className = '',
  testId,
  ...rest
}) {
  return (
    <div
      className={`asf-empty ${className}`.trim()}
      data-testid={testId || `empty-state-${slug}`}
      role="status"
      {...rest}
    >
      {icon && <span className="asf-empty__icon" aria-hidden="true">{icon}</span>}
      {title && <div className="asf-empty__title">{title}</div>}
      {body && <div className="asf-empty__body">{body}</div>}
      {action && (
        <button
          type="button"
          className="asf-empty__action"
          onClick={action.onClick}
          data-testid={action.testId || `empty-state-action-${slug}`}
        >
          {action.label}
        </button>
      )}
      {doc && (
        <a
          className="asf-empty__doc"
          href={doc.href}
          target="_blank"
          rel="noreferrer noopener"
          data-testid={doc.testId || `empty-state-doc-${slug}`}
        >
          {doc.label}
        </a>
      )}
    </div>
  );
}

export { AsfEmptyState };
