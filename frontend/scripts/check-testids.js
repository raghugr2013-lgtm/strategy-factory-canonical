#!/usr/bin/env node
/*
 * scripts/check-testids.js — Sprint 2 N1 · data-testid coverage lint.
 *
 * Rules:
 *   • Every interactive JSX element (button, a[href], input, select, textarea)
 *     inside /src/os/**\/*.jsx (excluding *.stories.jsx) must carry a
 *     data-testid attribute somewhere in its opening tag (which may span
 *     multiple lines).
 *   • `// testids-ignore-next-line` on the line above the opening tag
 *     silences the violation.
 *
 * Uses a multi-line, brace-aware scan of every opening tag.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', 'src', 'os');
const STORY_RE = /\.stories\.jsx?$/;
const INTERACTIVE = new Set(['button', 'input', 'select', 'textarea', 'a']);
const IGNORE_RE = /testids-ignore-next-line/i;

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, files);
    else if (/\.jsx?$/.test(entry.name) && !STORY_RE.test(entry.name)) files.push(p);
  }
  return files;
}

/**
 * Walk char-by-char to find opening tags (<button …>, <input …/>, etc.)
 * and capture the entire attribute span while respecting `{ … }` JSX
 * expression braces (which may themselves contain `>` and `<`).
 */
function findOpenings(src) {
  const openings = [];
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (ch !== '<') { i++; continue; }
    // Must be a tag name char after `<`.
    const nameMatch = /^<([A-Za-z][A-Za-z0-9]*)/.exec(src.slice(i));
    if (!nameMatch) { i++; continue; }
    const name = nameMatch[1];
    let j = i + nameMatch[0].length;
    let depth = 0; // JSX expression brace depth
    let quote = null;
    while (j < src.length) {
      const c = src[j];
      if (quote) {
        if (c === quote) quote = null;
      } else if (c === '"' || c === "'" || c === '`') {
        quote = c;
      } else if (c === '{') {
        depth++;
      } else if (c === '}') {
        if (depth > 0) depth--;
      } else if (c === '>' && depth === 0) {
        break;
      }
      j++;
    }
    if (j >= src.length) break;
    const attrsSpan = src.slice(i + nameMatch[0].length, j);
    openings.push({ name, index: i, endIndex: j, attrs: attrsSpan });
    i = j + 1;
  }
  return openings;
}

function isAnchorHref(name, attrs) {
  if (name.toLowerCase() !== 'a') return true;
  return /\bhref\s*=\s*[{"']/.test(attrs);
}

const violations = [];
for (const file of walk(ROOT)) {
  const src = fs.readFileSync(file, 'utf8');
  const lines = src.split('\n');
  for (const o of findOpenings(src)) {
    if (!INTERACTIVE.has(o.name.toLowerCase())) continue;
    if (!isAnchorHref(o.name, o.attrs)) continue;
    if (/\bdata-testid\s*=\s*[{"']/.test(o.attrs)) continue;
    if (/aria-hidden(\s|=|>)/.test(o.attrs)) continue;

    const before = src.slice(0, o.index);
    const lineNo = before.split('\n').length;
    const prev = lines[lineNo - 2] || '';
    if (IGNORE_RE.test(prev)) continue;

    const ctxLine = (lines[lineNo - 1] || '').trim();
    violations.push({ file: path.relative(process.cwd(), file), lineNo, tag: o.name, ctx: ctxLine });
  }
}

if (violations.length) {
  console.error(`\n✖ ${violations.length} data-testid violation(s) found:\n`);
  for (const v of violations) {
    console.error(`  ${v.file}:${v.lineNo} <${v.tag}> — ${v.ctx.slice(0, 120)}`);
  }
  console.error('\nAdd data-testid=… to each element, or place `// testids-ignore-next-line` on the previous line.');
  process.exit(1);
}

console.log('✓ data-testid coverage: OK (every interactive element in src/os has a data-testid).');
