/*
 * Playwright · EvaluationHarness surface (Phase D2 — interactions unlocked).
 *
 * D1 shipped the read-only visualization. D2 unlocks:
 *   - setVerdict  (verdict buttons per criterion)
 *   - setSession  (session-label input)
 *   - setNotes    (notes textarea)
 *   - clearAll    (reset verdicts)
 *   - markAllPass (mark all pass)
 *
 * This spec verifies the anatomy is preserved (no layout drift from D1)
 * and every unlocked interaction updates the store + persists to
 * localStorage. It replaces the D1 read-only spec.
 */
const { test, expect } = require('@playwright/test');

const login = async (page) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const loginForm = page.getByTestId('login-form');
  if (await loginForm.isVisible().catch(() => false)) {
    await page.getByTestId('login-email').fill('operator@coinnike.com');
    await page.getByTestId('login-password').fill('prototype123');
    await page.getByTestId('login-submit').click();
  }
  await page.getByTestId('mission-control').waitFor({ timeout: 20_000 });
};

const clearEvalStorage = async (page) => {
  await page.evaluate(() => {
    try { localStorage.removeItem('sf.eval.v1'); } catch { /* noop */ }
  });
};

const DIM_KEYS = [
  'discoverability',
  'navigation-predictability',
  'cognitive-load',
  'interaction-rhythm',
  'trust',
  'identity',
];

// 24 criterion ids (must match evaluationStore.DIMENSIONS).
const CRITERION_IDS = [
  'disc-1', 'disc-2', 'disc-3', 'disc-4',
  'pred-1', 'pred-2', 'pred-3', 'pred-4',
  'load-1', 'load-2', 'load-3', 'load-4',
  'rhy-1', 'rhy-2', 'rhy-3', 'rhy-4',
  'trust-1', 'trust-2', 'trust-3', 'trust-4',
  'id-1', 'id-2', 'id-3', 'id-4',
];

test.describe('Phase D2 · Evaluation Harness (interactions live)', () => {
  test('surface anatomy is preserved from D1 (no layout drift)', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('evaluation-harness'))
      .toHaveAttribute('data-phase', 'd2');
    await expect(page.getByTestId('eval-header-eyebrow')).toContainText(/Interactive Prototype Gate/i);
    await expect(page.getByTestId('eval-header-headline')).toBeVisible();
    await expect(page.getByTestId('eval-header-briefing')).toBeVisible();
    await expect(page.getByTestId('eval-header-status')).toContainText(/24 criteria/i);
    // Readiness verdict = unstarted at cold-load.
    const readiness = page.getByTestId('eval-readiness');
    await expect(readiness).toHaveAttribute('data-verdict', 'unstarted');
    await expect(page.getByTestId('eval-count-unset')).toContainText(/24 unset/);
    // All 6 dimensions + 24 criteria still render.
    for (const key of DIM_KEYS) {
      await expect(page.getByTestId(`eval-dim-${key}`)).toBeVisible();
      await expect(page.getByTestId(`eval-summary-${key}`)).toBeVisible();
    }
    for (const id of CRITERION_IDS) {
      await expect(page.getByTestId(`eval-criterion-${id}`)).toBeVisible();
    }
  });

  test('verdict buttons + reset + mark-all + inputs are now interactive', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();
    // Every write-side control is enabled and editable.
    await expect(page.getByTestId('eval-reset')).toBeEnabled();
    await expect(page.getByTestId('eval-mark-all-pass')).toBeEnabled();
    await expect(page.getByTestId('eval-session-label')).not.toHaveAttribute('readonly', '');
    await expect(page.getByTestId('eval-notes')).not.toHaveAttribute('readonly', '');
    // Sample verdict buttons across dimensions are enabled.
    for (const combo of [
      ['disc-1', 'pass'], ['pred-2', 'review'], ['trust-2', 'fail'],
      ['id-4', 'unset'], ['rhy-3', 'pass'],
    ]) {
      const btn = page.getByTestId(`eval-verdict-${combo[0]}-${combo[1]}`);
      await expect(btn).toBeEnabled();
    }
  });

  test('setVerdict updates the criterion pill + dimension summary + readiness', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();

    // Click a pass verdict on disc-1.
    await page.getByTestId('eval-verdict-disc-1-pass').click();
    await expect(page.getByTestId('eval-criterion-disc-1'))
      .toHaveAttribute('data-verdict', 'pass');
    await expect(page.getByTestId('eval-verdict-disc-1-pass'))
      .toHaveAttribute('aria-pressed', 'true');
    // Discoverability summary now reads 1/4 passing.
    await expect(page.getByTestId('eval-summary-discoverability'))
      .toContainText(/1\/4 passing/);
    // Readiness transitions to "nearly" (some unset, no fails).
    await expect(page.getByTestId('eval-readiness'))
      .toHaveAttribute('data-verdict', 'nearly');
    await expect(page.getByTestId('eval-count-pass')).toContainText(/1 pass/);
    await expect(page.getByTestId('eval-count-unset')).toContainText(/23 unset/);

    // Click a fail verdict on trust-2 → readiness must escalate to "blocked".
    await page.getByTestId('eval-verdict-trust-2-fail').click();
    await expect(page.getByTestId('eval-readiness'))
      .toHaveAttribute('data-verdict', 'blocked');
    await expect(page.getByTestId('eval-count-fail')).toContainText(/1 fail/);
    await expect(page.getByTestId('eval-summary-trust'))
      .toHaveAttribute('data-verdict', 'fail');
  });

  test('setSession + setNotes persist to the store and localStorage', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();

    await page.getByTestId('eval-session-label').fill('2026-02-04 walk-through #1');
    await page.getByTestId('eval-notes').fill('Kill-posture chip needs a stronger tone in dark theme.');

    // Values are echoed by the controlled inputs.
    await expect(page.getByTestId('eval-session-label'))
      .toHaveValue('2026-02-04 walk-through #1');
    await expect(page.getByTestId('eval-notes'))
      .toHaveValue('Kill-posture chip needs a stronger tone in dark theme.');

    // Persisted to localStorage under the sf.eval.v1 namespace.
    const persisted = await page.evaluate(() => localStorage.getItem('sf.eval.v1'));
    const parsed = JSON.parse(persisted);
    expect(parsed.session).toBe('2026-02-04 walk-through #1');
    expect(parsed.notes).toBe('Kill-posture chip needs a stronger tone in dark theme.');
  });

  test('markAllPass flips every criterion to pass and readiness to READY', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();

    await page.getByTestId('eval-mark-all-pass').click();

    await expect(page.getByTestId('eval-readiness'))
      .toHaveAttribute('data-verdict', 'ready');
    await expect(page.getByTestId('eval-count-pass')).toContainText(/24 pass/);
    await expect(page.getByTestId('eval-count-unset')).toContainText(/0 unset/);
    // Spot-check a few criteria carry data-verdict='pass'.
    for (const id of ['disc-1', 'trust-2', 'id-4']) {
      await expect(page.getByTestId(`eval-criterion-${id}`))
        .toHaveAttribute('data-verdict', 'pass');
    }
  });

  test('clearAll wipes every verdict and returns readiness to UNSTARTED', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();

    // Prime some verdicts first.
    await page.getByTestId('eval-mark-all-pass').click();
    await expect(page.getByTestId('eval-readiness'))
      .toHaveAttribute('data-verdict', 'ready');

    // Reset.
    await page.getByTestId('eval-reset').click();
    await expect(page.getByTestId('eval-readiness'))
      .toHaveAttribute('data-verdict', 'unstarted');
    await expect(page.getByTestId('eval-count-unset')).toContainText(/24 unset/);
    await expect(page.getByTestId('eval-criterion-disc-1'))
      .toHaveAttribute('data-verdict', 'unset');
  });

  test('verdicts persist across a page reload (localStorage restore)', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();

    await page.getByTestId('eval-verdict-load-1-review').click();
    await page.getByTestId('eval-verdict-rhy-4-fail').click();

    await page.reload();
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();
    await expect(page.getByTestId('eval-criterion-load-1'))
      .toHaveAttribute('data-verdict', 'review');
    await expect(page.getByTestId('eval-criterion-rhy-4'))
      .toHaveAttribute('data-verdict', 'fail');
    await expect(page.getByTestId('eval-readiness'))
      .toHaveAttribute('data-verdict', 'blocked');
  });

  test('discovery link from Mission Control still routes to the harness', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/mission');
    await expect(page.getByTestId('mission-control')).toBeVisible();
    const link = page.getByTestId('mc-open-evaluation');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/c\/evaluation/);
    await expect(page.getByTestId('evaluation-harness')).toBeVisible({ timeout: 10_000 });
  });

  test('back-to-Mission button navigates home', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();
    await page.getByTestId('eval-back-mission').click();
    await expect(page).toHaveURL(/\/c\/mission/);
    await expect(page.getByTestId('mission-control')).toBeVisible();
  });
});
