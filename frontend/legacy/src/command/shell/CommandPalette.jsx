/**
 * COMMAND · Phase U-3 — CommandPalette (unified)
 * ----------------------------------------------------------------------------
 * Sections (in order):
 *   1. Recent       — localStorage-backed, capped at 5, deduped by id
 *   2. Modules      — registry-driven (LeftRail.MODULES)
 *   3. Workflow     — U-3 operator commands (Notifications / Retry / etc.)
 *   4. Posture      — Focus / Density / Premium / Inspector / Reset
 *   5. Legacy       — exit COMMAND mode
 *
 * Search is a naïve fuzzy match (each query char must appear in order).
 * Keyboard: ⌘K open · ↑↓ navigate · Enter select · Esc close.
 */
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { MODULES } from './LeftRail';
import useFocusTrap from '../../hooks/useFocusTrap';

const RECENT_KEY = 'asf.u3.palette.recent';
const RECENT_MAX = 5;

const WORKFLOW_COMMANDS = [
  { id: 'cmd:notifications', label: 'Open Notifications drawer',   hint: '⌘⇧N' },
  { id: 'cmd:shortcuts',     label: 'Show keyboard shortcuts',    hint: '?' },
  { id: 'cmd:retry-all',     label: 'Retry all loading panels',   hint: '' },
  { id: 'cmd:copy-url',      label: 'Copy current URL',           hint: '⌘⌥C' },
];

const POSTURE_COMMANDS = [
  { id: 'cmd:focus-toggle',   label: 'Toggle Focus Mode',                                 hint: '⌘⇧F' },
  { id: 'cmd:density-toggle', label: 'Toggle Density (comfortable / compact)',            hint: '' },
  { id: 'cmd:premium-toggle', label: 'Toggle Premium Aesthetic (cinematic / flat)',       hint: '' },
  { id: 'cmd:lang-cycle',     label: 'Cycle UI Language',                                 hint: '' },
  { id: 'cmd:inspector',      label: 'Toggle Inspector pane',                             hint: '⌘.' },
  { id: 'cmd:posture-reset',  label: 'Reset posture (auto)',                              hint: '' },
];

const LEGACY_COMMANDS = [
  { id: 'cmd:legacy', label: 'Exit COMMAND mode (legacy UI)', hint: '' },
];

// Pilot Restoration Step 3 (GATE 0) — palette deep-links to (module, section)
// pairs that are not top-nav chips. Handled in CommandShell via the
// `section:` id prefix.
const SECTION_COMMANDS = [
  { id: 'section:propfirm:challenge', label: 'Challenge Matching', hint: 'prop firm' },
];

function readRecent() {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (_) {
    return [];
  }
}

function writeRecent(items) {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, RECENT_MAX)));
  } catch (_) { /* noop */ }
}

function fuzzyMatch(needle, haystack) {
  if (!needle) return true;
  const n = needle.toLowerCase();
  const h = haystack.toLowerCase();
  if (h.includes(n)) return true;
  let hi = 0;
  for (let ni = 0; ni < n.length; ni += 1) {
    const ch = n.charCodeAt(ni);
    while (hi < h.length && h.charCodeAt(hi) !== ch) hi += 1;
    if (hi >= h.length) return false;
    hi += 1;
  }
  return true;
}

export default function CommandPalette({ open, onClose, onSelect, posture = 'workstation' }) {
  const [q, setQ] = useState('');
  const [idx, setIdx] = useState(0);
  const [recentIds, setRecentIds] = useState(() => readRecent());
  const inputRef = useRef(null);
  const cardRef = useRef(null);

  // U-4.1 — focus trap (initial focus goes to the input via the existing
  // open-effect; trap restores focus to the previously-focused element).
  useFocusTrap(cardRef, open, { initialFocus: null });

  // Pre-compute the master catalog of items (id + label + hint + section).
  const catalog = useMemo(() => {
    const moduleItems = MODULES.map((m) => ({
      id: `module:${m.id}`, label: m.label, hint: 'module', section: 'Modules',
    }));
    const sectionItems = SECTION_COMMANDS.map((c) => ({ ...c, section: 'Sections' }));
    const workflow = WORKFLOW_COMMANDS.map((c) => ({ ...c, section: 'Workflow' }));
    const posturei = POSTURE_COMMANDS.map((c) => ({ ...c, section: 'Posture' }));
    const legacy = LEGACY_COMMANDS.map((c) => ({ ...c, section: 'Legacy' }));
    const byId = new Map();
    [...moduleItems, ...sectionItems, ...workflow, ...posturei, ...legacy].forEach((i) => byId.set(i.id, i));
    return { moduleItems, sectionItems, workflow, posture: posturei, legacy, byId };
  }, []);

  // Sections (filtered by query)
  const sections = useMemo(() => {
    const needle = q.trim();
    const f = (arr) => (needle ? arr.filter((i) => fuzzyMatch(needle, i.label)) : arr);
    const recentItems = recentIds
      .map((id) => catalog.byId.get(id))
      .filter(Boolean)
      .map((i) => ({ ...i, section: 'Recent' }));
    const list = [
      { title: 'Recent', items: f(recentItems) },
      { title: 'Modules', items: f(catalog.moduleItems) },
      { title: 'Sections', items: f(catalog.sectionItems) },
      { title: 'Workflow', items: f(catalog.workflow) },
      { title: 'Posture', items: f(catalog.posture) },
      { title: 'Legacy', items: f(catalog.legacy) },
    ].filter((s) => s.items.length > 0);
    return list;
  }, [q, catalog, recentIds]);

  // Flat list (for keyboard nav).
  const flat = useMemo(() => sections.flatMap((s) => s.items), [sections]);

  useEffect(() => { if (open) { setQ(''); setIdx(0); setTimeout(() => inputRef.current?.focus(), 30); } }, [open]);

  useEffect(() => {
    function onKey(e) {
      if (!open) return;
      if (e.key === 'Escape') { onClose(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, flat.length - 1)); }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
      if (e.key === 'Enter')     {
        e.preventDefault();
        const it = flat[idx];
        if (it) {
          const next = [it.id, ...recentIds.filter((id) => id !== it.id)].slice(0, RECENT_MAX);
          setRecentIds(next);
          writeRecent(next);
          if (onSelect) onSelect(it);
        }
        onClose();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, flat, idx, onClose, onSelect, recentIds]);

  if (!open) return null;

  const widthStyle = posture === 'briefing'
    ? { width: '92vw', maxWidth: 640 }
    : posture === 'tablet'
      ? { width: '80vw', maxWidth: 640 }
      : { width: 640 };

  // Map flat index → highlight state.
  let flatCursor = 0;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 80,
        background: 'rgba(7, 10, 18, 0.62)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        paddingTop: posture === 'briefing' ? '12vh' : '14vh',
      }}
      onClick={onClose}
      data-testid="cmd-palette-overlay"
    >
      <div
        ref={cardRef}
        className="panel cmd-fade-in"
        onClick={(e) => e.stopPropagation()}
        data-testid="cmd-palette"
        data-asf-modal=""
        role="dialog"
        aria-modal="true"
        aria-labelledby="cmd-palette-title"
        style={{ ...widthStyle, padding: 0, overflow: 'hidden', position: 'relative', zIndex: 81 }}
      >
        <h2 id="cmd-palette-title" className="sr-only">Command palette</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderBottom: '1px solid var(--cmd-hairline)' }}>
          <span
            style={{
              fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-cyan)',
              letterSpacing: '0.14em', textTransform: 'uppercase',
            }}
          >
            ⌘K
          </span>
          <input
            ref={inputRef}
            data-testid="cmd-palette-input"
            value={q}
            onChange={(e) => { setQ(e.target.value); setIdx(0); }}
            placeholder="Quick command, module, or strategy…"
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              color: 'var(--cmd-ink-0)', fontSize: 13, padding: '6px 0',
            }}
          />
          <span className="kbd">esc</span>
        </div>
        <div style={{ maxHeight: '52vh', overflow: 'auto' }}>
          {sections.length === 0 && (
            <div data-testid="cmd-palette-empty" style={{ padding: 18, fontSize: 12, color: 'var(--cmd-ink-2)' }}>
              No matches.
            </div>
          )}
          {sections.map((sec) => (
            <div key={sec.title} data-testid={`cmd-palette-section-${sec.title.toLowerCase()}`}>
              <div className="cmd-palette-section">{sec.title}</div>
              {sec.items.map((it) => {
                const cursor = flatCursor;
                flatCursor += 1;
                const active = cursor === idx;
                return (
                  <button
                    key={`${sec.title}:${it.id}`}
                    data-testid={`cmd-palette-item-${it.id}`}
                    onMouseEnter={() => setIdx(cursor)}
                    onClick={() => {
                      const next = [it.id, ...recentIds.filter((id) => id !== it.id)].slice(0, RECENT_MAX);
                      setRecentIds(next);
                      writeRecent(next);
                      if (onSelect) onSelect(it);
                      onClose();
                    }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      width: '100%', textAlign: 'left',
                      padding: '10px 14px',
                      background: active ? 'var(--cmd-surface-3)' : 'transparent',
                      border: 'none',
                      color: active ? 'var(--cmd-ink-0)' : 'var(--cmd-ink-1)',
                      cursor: 'pointer',
                      fontSize: 12,
                      fontFamily: 'Inter, sans-serif',
                    }}
                  >
                    <span
                      style={{
                        width: 18, textAlign: 'center', color: active ? 'var(--cmd-cyan)' : 'var(--cmd-ink-2)',
                      }}
                    >›</span>
                    <span>{it.label}</span>
                    <span style={{ flex: 1 }} />
                    {it.hint && (
                      <span className="kbd" style={{ marginLeft: 8 }}>{it.hint}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
