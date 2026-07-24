/*
 * Playwright · EvaluationHarness surface (Phase D1).
 *
 * Verifies the net-new /c/evaluation surface as a READ-ONLY preview:
 *   - Surface header anatomy (eyebrow · headline · briefing · trailer)
 *   - Six dimension sections are present (all 24 criteria rendered)
 *   - Overall readiness card defaults to "unstarted"
 *   - Session Summary strip renders one card per dimension
 *   - Verdict buttons are visible but disabled (D2 unlocks them)
 *   - Session input and notes textarea are readOnly
 *   - Discovery link from Mission Control routes here
 *   - Back-to-Mission button navigates home
 *
 * NOTE: This spec cleans localStorage before each test so the cold-load
 * readiness verdict is deterministic (unstarted).
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

test.describe('Phase D1 · Evaluation Harness (read-only)', () => {
  test('surface header + readiness card render at cold-load', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('eval-header-eyebrow')).toContainText(/Interactive Prototype Gate/i);
    await expect(page.getByTestId('eval-header-headline')).toBeVisible();
    await expect(page.getByTestId('eval-header-briefing')).toContainText(/Phase D1|read-only/i);
    await expect(page.getByTestId('eval-header-status')).toContainText(/24 criteria/i);
    // Readiness verdict = unstarted at cold-load.
    const readiness = page.getByTestId('eval-readiness');
    await expect(readiness).toBeVisible();
    await expect(readiness).toHaveAttribute('data-verdict', 'unstarted');
    await expect(page.getByTestId('eval-count-unset')).toContainText(/24 unset/);
    await expect(page.getByTestId('eval-readiness-pct')).toContainText(/0% of 24/);
  });

  test('all six dimensions and 24 criteria are present', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();
    for (const key of DIM_KEYS) {
      await expect(page.getByTestId(`eval-dim-${key}`)).toBeVisible();
      await expect(page.getByTestId(`eval-summary-${key}`)).toBeVisible();
    }
    for (const id of CRITERION_IDS) {
      await expect(page.getByTestId(`eval-criterion-${id}`)).toBeVisible();
    }
  });

  test('verdict buttons are rendered but disabled (D2 unlock)', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();
    // Sample a handful of verdict buttons across dimensions.
    for (const combo of [
      ['disc-1', 'pass'], ['pred-2', 'review'], ['trust-2', 'fail'],
      ['id-4', 'unset'], ['rhy-3', 'pass'],
    ]) {
      const btn = page.getByTestId(`eval-verdict-${combo[0]}-${combo[1]}`);
      await expect(btn).toBeVisible();
      await expect(btn).toBeDisabled();
      await expect(btn).toHaveAttribute('aria-disabled', 'true');
    }
    // Reset + mark-all-pass + session input + notes are all disabled/readonly.
    await expect(page.getByTestId('eval-reset')).toBeDisabled();
    await expect(page.getByTestId('eval-mark-all-pass')).toBeDisabled();
    await expect(page.getByTestId('eval-session-label')).toHaveAttribute('readonly', '');
    await expect(page.getByTestId('eval-notes')).toHaveAttribute('readonly', '');
  });

  test('discovery link from Mission Control routes to the harness', async ({ page }) => {
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

  test('back-to-mission button navigates home', async ({ page }) => {
    await login(page);
    await clearEvalStorage(page);
    await page.goto('/c/evaluation');
    await expect(page.getByTestId('evaluation-harness')).toBeVisible();
    await page.getByTestId('eval-back-mission').click();
    await expect(page).toHaveURL(/\/c\/mission/);
    await expect(page.getByTestId('mission-control')).toBeVisible();
  });
});
