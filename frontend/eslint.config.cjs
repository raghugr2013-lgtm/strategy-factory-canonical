/*
 * ESLint 9 flat config · Sprint 2 N1 finalisation.
 * Minimal permissive config so eslint doesn't error when it walks
 * the frontend workspace. Real lint gates live in scripts/check-testids.js
 * + scripts/check-pr-title.js.
 */
module.exports = [
  {
    ignores: [
      'node_modules/**',
      'build/**',
      'storybook-static/**',
      '.archive/**',
      'playwright-report/**',
      'test-results/**',
      'tests/e2e/**/*.spec.cjs-snapshots/**',
    ],
  },
];
