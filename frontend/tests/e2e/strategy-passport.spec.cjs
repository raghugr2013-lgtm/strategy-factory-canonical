/*
 * Playwright · Strategy Passport (Sprint 2 N5).
 * Verifies:
 *   • /c/strategies clicking a row navigates to /c/strategies/:id
 *   • /c/strategies/strat-014 renders all seven passport sections
 *   • /c/strategies/strat-999 renders the fallback shell
 *   • axe-core · zero unwaived violations
 */
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { injectAxe, getViolations } = require('axe-playwright');

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

test.describe('N5 · strategy passport', () => {
  test('explorer row click → passport surface renders all sections', async ({ page }) => {
    await login(page);
    await page.getByTestId('nav-strategies').click();
    await page.getByTestId('strategies-table').waitFor({ timeout: 10_000 });
    // Click the first row (row testid pattern comes from the caption, not testId prop).
    await page.locator('[data-testid="strategies-table"] [role="row"]').nth(1).click();
    await expect(page.getByTestId('strategy-passport')).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/c\/strategies\/[^/]+$/);
    // Sections present
    await expect(page.getByTestId('passport-signature')).toBeVisible();
    await expect(page.getByTestId('passport-metrics')).toBeVisible();
    await expect(page.getByTestId('passport-provenance')).toBeVisible();
    await expect(page.getByTestId('passport-lineage')).toBeVisible();
    await expect(page.getByTestId('passport-guardrails')).toBeVisible();
    await expect(page.getByTestId('passport-equity')).toBeVisible();
    await expect(page.getByTestId('passport-backtest')).toBeVisible();
    await expect(page.getByTestId('passport-approvals')).toBeVisible();
    // Baseline snapshot
    await expect(page).toHaveScreenshot('strategy-passport.png', {
      fullPage: false, maxDiffPixelRatio: 0.02,
    });
  });

  test('unknown id → fallback shell renders', async ({ page }) => {
    await login(page);
    await page.goto('/c/strategies/strat-does-not-exist');
    await expect(page.getByTestId('strategy-passport')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('passport-fallback-notice')).toBeVisible();
  });

  test('back link returns to explorer', async ({ page }) => {
    await login(page);
    await page.goto('/c/strategies/strat-014');
    await expect(page.getByTestId('strategy-passport')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('passport-back-link').click();
    await expect(page.getByTestId('strategies-table')).toBeVisible();
  });

  test('axe-core · strategy passport has zero unwaived violations', async ({ page }) => {
    await login(page);
    await page.goto('/c/strategies/strat-014');
    await page.getByTestId('strategy-passport').waitFor({ timeout: 10_000 });
    await injectAxe(page);
    const axerc = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', '.axerc.json'), 'utf8'));
    const waivedRules = new Set(axerc.waivers.map((w) => w.rule));
    const raw = await getViolations(page, undefined, {
      axeOptions: { rules: { 'color-contrast': { enabled: true } } },
    });
    const violations = raw.filter((v) => !waivedRules.has(v.id));
    if (violations.length) {
      console.log('PASSPORT AXE UNWAIVED:', JSON.stringify(violations.map((v) => ({
        id: v.id, impact: v.impact, nodes: v.nodes.length,
        targets: v.nodes.slice(0, 5).map((n) => n.target),
      })), null, 2));
    }
    expect(violations, `${violations.length} unwaived a11y violations on /c/strategies/:id`).toHaveLength(0);
  });
});
