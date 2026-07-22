/*
 * WorkspaceContextChip — canonical §9 · shell integration.
 * refs docs/ARCHITECTURE.md §9 · Workspace context model
 *
 * Header-mounted chip that shows the four canonical context fields when
 * any of them are set. Clicking any pill removes that field from the
 * URL; the trailing × clears every context key at once. Fields the
 * context has not set are hidden so the chip disappears when the
 * workspace has no active filter.
 */
import React from 'react';
import { X } from 'lucide-react';
import { useWorkspaceContext } from '../hooks/useWorkspaceContext';

const PILL_STYLE = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '2px 8px',
  borderRadius: 999,
  background: 'color-mix(in oklab, var(--sig-info) 10%, transparent)',
  border: '1px solid color-mix(in oklab, var(--sig-info) 32%, transparent)',
  color: 'var(--sig-info)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  fontFamily: 'inherit',
  cursor: 'pointer',
  transition: 'background var(--dur-fast) var(--ease-standard)',
};

const KEY_LABEL = {
  pair: 'PAIR',
  timeframe: 'TF',
  strategy: 'SID',
  cycle: 'CYC',
};

const SHORT_VALUE = (key, value) => {
  if (key === 'strategy' || key === 'cycle') {
    return value.length > 8 ? `${value.slice(0, 8)}…` : value;
  }
  return value;
};

export const WorkspaceContextChip = () => {
  const { context, setContext, clearContext, isActive } = useWorkspaceContext();

  if (!isActive) return null;

  return (
    <div data-testid="workspace-context-chip"
         style={{
           display: 'inline-flex', alignItems: 'center', gap: 6,
           padding: '4px 6px 4px 10px',
           borderRadius: 999,
           background: 'var(--surface-2)',
           border: '1px solid var(--stroke-2)',
         }}>
      <span data-testid="workspace-context-eyebrow"
            style={{
              color: 'var(--content-lo)',
              fontSize: 'var(--font-caption)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              marginRight: 2,
            }}>
        Context
      </span>
      {Object.entries(context).map(([key, value]) => {
        if (!value) return null;
        return (
          <button key={key}
                  type="button"
                  data-testid={`workspace-context-${key}`}
                  onClick={() => setContext({ [key]: null })}
                  title={`Clear ${KEY_LABEL[key]} · ${value}`}
                  style={PILL_STYLE}>
            <span style={{ opacity: 0.7 }}>{KEY_LABEL[key]}</span>
            <span style={{ color: 'var(--content-hi)' }} className="mono-num">
              {SHORT_VALUE(key, value)}
            </span>
          </button>
        );
      })}
      <button type="button"
              data-testid="workspace-context-clear"
              onClick={clearContext}
              title="Clear workspace context"
              style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 20, height: 20,
                borderRadius: '50%',
                background: 'transparent',
                border: 'none',
                color: 'var(--content-lo)',
                cursor: 'pointer',
                transition: 'color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard)',
              }}>
        <X size={12} strokeWidth={1.75} />
      </button>
    </div>
  );
};
