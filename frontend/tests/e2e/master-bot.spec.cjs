/*
 * Playwright · Master Bot dashboard smoke test (Sprint 2 N2).
 * Verifies: /c/masterbot renders identity strip + plan card + decisions log.
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

test.describe('N2 · master bot dashboard', () => {
  test('surface renders identity + plan + decisions via fixture', async ({ page }) => {
    await login(page);
    await page.getByTestId('nav-masterbot').click();
    await expect(page.getByTestId('master-bot')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('mb-identity-strip')).toBeVisible();
    await expect(page.getByTestId('mb-plan-card')).toBeVisible();
    await expect(page.getByTestId('mb-decisions')).toBeVisible();
    // At least one decision row present.
    const decisionRows = page.locator('[data-testid^="mb-decision-"]');
    await expect(decisionRows).toHaveCount(5);
    // At least four guardrail cells present.
    const guardrails = page.locator('[data-testid^="mb-guardrail-"]');
    await expect(guardrails).toHaveCount(4);

    await expect(page).toHaveScreenshot('master-bot-dashboard.png', {
      fullPage: false, maxDiffPixelRatio: 0.02,
    });
  });

  test('reachable via ⌘K palette', async ({ page }) => {
    await login(page);
    await page.keyboard.press('Meta+K');
    await expect(page.getByTestId('cmdk-palette')).toBeVisible();
    await page.getByTestId('cmdk-item-masterbot').click();
    await expect(page.getByTestId('master-bot')).toBeVisible({ timeout: 10_000 });
  });

  test('axe-core · master bot has zero unwaived violations', async ({ page }) => {
    await login(page);
    await page.getByTestId('nav-masterbot').click();
    await page.getByTestId('master-bot').waitFor({ timeout: 10_000 });

    await injectAxe(page);
    const axerc = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', '.axerc.json'), 'utf8'));
    const waivedRules = new Set(axerc.waivers.map((w) => w.rule));
    const raw = await getViolations(page, undefined, {
      axeOptions: { rules: { 'color-contrast': { enabled: true } } },
    });
    const violations = raw.filter((v) => !waivedRules.has(v.id));
    const waived = raw.filter((v) => waivedRules.has(v.id));
    if (violations.length) {
      console.log('MB AXE UNWAIVED:', JSON.stringify(violations.map((v) => ({
        id: v.id, impact: v.impact, nodes: v.nodes.length,
        targets: v.nodes.slice(0, 5).map((n) => n.target),
      })), null, 2));
    }
    if (waived.length) console.log(`MB AXE WAIVED: ${waived.map((v) => v.id).join(', ')}`);
    expect(violations, `${violations.length} unwaived a11y violations on /c/masterbot`).toHaveLength(0);
  });
});
