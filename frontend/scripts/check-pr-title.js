#!/usr/bin/env node
/*
 * scripts/check-pr-title.js — Sprint 2 N1 · PR title convention lint.
 *
 * Enforces the Freeze §4 rule 3 · every PR title must include one of:
 *   N1 · N2 · N3 · N4 · N5 · chore · docs · fix · test
 * plus a colon-separated summary. Example:
 *   "N1 · storybook + axe baseline"
 *
 * Consumed by CI via `PR_TITLE=$(gh pr view --json title -q .title)` and
 * pipes into this script's stdin OR passes as $1.
 */

const title = process.argv[2] || process.env.PR_TITLE || '';
const RE = /^(N[1-5]|chore|docs|fix|test|feat|refactor)\s*[·:]\s+.+/i;

if (!title.trim()) {
  console.error('✖ PR title is empty.');
  process.exit(1);
}
if (!RE.test(title)) {
  console.error(`✖ PR title does not match the Sprint 2 convention.\n\n  Got:      "${title}"\n  Expected: "N1 · <summary>"   (or chore/docs/fix/test/feat/refactor)\n`);
  process.exit(1);
}
console.log(`✓ PR title OK — "${title}"`);
