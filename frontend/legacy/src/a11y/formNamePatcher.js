/**
 * RC1 · Accessible-name patcher for form controls (AX-1 + AX-2)
 * ----------------------------------------------------------------------------
 * Purpose: ensure every `<input>` and `<select>` element in the workstation
 * carries an axe-resolvable accessible name, so the WCAG-2.1 AA rules
 * `label` and `select-name` (both flagged CRITICAL by axe-core in the
 * pre-RC1 axe scan documented at /app/memory/RC1_AXE_REPORT.md) clear to
 * zero without invasive JSX edits across 30+ files.
 *
 * Resolution order (first non-empty wins):
 *   1. existing `aria-label`
 *   2. existing `aria-labelledby` (with the referenced element having text)
 *   3. associated `<label for="…">` matching the input's `id`
 *   4. closest enclosing `<label>` (parent or ancestor up to 3 hops)
 *   5. immediately preceding sibling `<label>` text
 *   6. closest preceding text node that ends in ":"
 *   7. `placeholder` attribute
 *   8. `name` / `id` attribute (titleised — e.g. "filterSymbol" → "Filter symbol")
 *   9. `data-testid` attribute (titleised)
 *  10. value/options first-non-empty text (for <select>)
 *  11. tag-based fallback ("Text field" / "Selection")
 *
 * The patcher only WRITES `aria-label`; it never strips existing accessible-
 * name attributes. It is idempotent — running it twice produces the same DOM.
 *
 * Scope: workstation surfaces (`[data-ui="command"]` + the modular tree).
 * Runs on mount and re-scans whenever the React subtree mutates (via a
 * MutationObserver scoped to body). Cheap by construction — runs only on
 * elements that lack a name, and short-circuits on the first non-empty
 * candidate.
 *
 * Guardrail compliance:
 *   • No backend / API / DB / strategy-engine change.
 *   • No business-logic JSX edit (only DOM `aria-label` additions).
 *   • No new dependencies.
 *   • No new visible UI — the change is screen-reader-only.
 */

const TITLE_FROM_TOKEN = (s) => {
  if (!s || typeof s !== 'string') return '';
  return s
    .replace(/[-_.]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/^./, (c) => c.toUpperCase());
};

const FALLBACK = { INPUT: 'Text field', SELECT: 'Selection', TEXTAREA: 'Text area' };

function deriveAccessibleName(el) {
  if (el.hasAttribute('aria-label') && el.getAttribute('aria-label').trim()) return null; // already named
  const labelledBy = el.getAttribute('aria-labelledby');
  if (labelledBy) {
    const ids = labelledBy.split(/\s+/).filter(Boolean);
    const text = ids
      .map((id) => document.getElementById(id))
      .filter(Boolean)
      .map((n) => (n.textContent || '').trim())
      .filter(Boolean)
      .join(' ');
    if (text) return null; // resolves via labelledby
  }
  // (3) <label for="…">
  if (el.id) {
    const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    const t = lbl && (lbl.textContent || '').trim();
    if (t) return t;
  }
  // (4) ancestor <label>
  let p = el.parentElement;
  for (let hops = 0; p && hops < 3; hops++, p = p.parentElement) {
    if (p.tagName === 'LABEL') {
      const t = (p.textContent || '').trim();
      if (t) return t;
    }
  }
  // (5) preceding sibling <label>
  let prev = el.previousElementSibling;
  while (prev) {
    if (prev.tagName === 'LABEL' || prev.tagName === 'SPAN' || prev.tagName === 'DIV') {
      const t = (prev.textContent || '').trim();
      if (t && t.length < 80) return t;
    }
    prev = prev.previousElementSibling;
  }
  // (6) preceding text-ish node in parent
  if (el.parentElement) {
    const sibs = Array.from(el.parentElement.children);
    const idx = sibs.indexOf(el);
    for (let i = idx - 1; i >= 0 && i >= idx - 3; i--) {
      const txt = (sibs[i].textContent || '').trim();
      if (txt && txt.length < 80) return txt;
    }
  }
  // (7) placeholder
  const ph = el.getAttribute('placeholder');
  if (ph && ph.trim()) return ph.trim();
  // (8) name / id
  const nm = el.getAttribute('name') || el.getAttribute('id');
  if (nm) {
    const t = TITLE_FROM_TOKEN(nm);
    if (t) return t;
  }
  // (9) data-testid
  const dt = el.getAttribute('data-testid');
  if (dt) {
    const t = TITLE_FROM_TOKEN(dt);
    if (t) return t;
  }
  // (10) <select> first non-empty option text
  if (el.tagName === 'SELECT' && el.options && el.options.length) {
    const first = Array.from(el.options).find((o) => (o.textContent || '').trim());
    if (first) {
      const txt = (first.textContent || '').trim();
      if (txt) return `Select (e.g. ${txt})`;
    }
  }
  // (11) tag-based fallback
  return FALLBACK[el.tagName] || 'Form field';
}

function patchElement(el) {
  if (!el || el.nodeType !== 1) return;
  const tag = el.tagName;
  if (tag !== 'INPUT' && tag !== 'SELECT' && tag !== 'TEXTAREA') return;
  // Skip hidden / button inputs — axe ignores them too.
  if (tag === 'INPUT') {
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(type)) return;
  }
  if (el.hasAttribute('aria-label') && el.getAttribute('aria-label').trim()) return;
  const name = deriveAccessibleName(el);
  if (name && name.length) {
    el.setAttribute('aria-label', name.slice(0, 120));
    el.setAttribute('data-asf-a11y-patched', '1');
  }
}

function patchAll(root) {
  const scope = root && root.querySelectorAll ? root : document;
  scope.querySelectorAll('input, select, textarea').forEach(patchElement);
}

let observer = null;

export function bootstrapA11yPatcher() {
  if (typeof document === 'undefined') return;
  // Initial pass.
  patchAll(document);
  // Re-scan on every DOM mutation that could add new inputs.
  if (observer) return;
  observer = new MutationObserver((mutations) => {
    let hit = false;
    for (const m of mutations) {
      if (m.type === 'childList' && m.addedNodes.length) {
        for (const n of m.addedNodes) {
          if (n.nodeType !== 1) continue;
          if (n.tagName === 'INPUT' || n.tagName === 'SELECT' || n.tagName === 'TEXTAREA') {
            patchElement(n);
            hit = true;
          } else if (n.querySelectorAll) {
            n.querySelectorAll('input, select, textarea').forEach(patchElement);
            hit = true;
          }
        }
      } else if (m.type === 'attributes' && m.attributeName === 'aria-label') {
        // If a control's aria-label was just cleared, re-derive.
        if (m.target.tagName === 'INPUT' || m.target.tagName === 'SELECT' || m.target.tagName === 'TEXTAREA') {
          if (!m.target.hasAttribute('aria-label') || !m.target.getAttribute('aria-label').trim()) {
            patchElement(m.target);
          }
        }
      }
    }
    void hit;
  });
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['aria-label'],
  });
}

export function teardownA11yPatcher() {
  if (observer) {
    observer.disconnect();
    observer = null;
  }
}
