/*
 * Playwright · Morning-routine smoke test.
 * Runs against `yarn build` static output served on :4173.
 * Verifies: LoginScreen renders → operator can reach MissionControl.
 * Fixture-mode auth via authStore fallback (operator@coinnike.com).
 */
const { test, expect } = require('@playwright/test');
const { injectAxe, checkA11y } = require('axe-playwright');

test.describe('N1 · morning routine', () => {
  test('login screen loads and reaches mission control via fixture auth', async ({ page }) => {
    await page.goto('/');

    // Screen may redirect to /login OR mount LoginScreen at root.
    await page.waitForLoadState('networkidle');

    // Look for login form or an already-authenticated shell.
    const loginForm = page.getByTestId('login-form');
    const missionControl = page.getByTestId('mission-control');

    const loginVisible = await loginForm.isVisible().catch(() => false);
    if (loginVisible) {
      await page.getByTestId('login-email').fill('operator@coinnike.com');
      await page.getByTestId('login-password').fill('prototype123');
      await page.getByTestId('login-submit').click();
    }

    await expect(missionControl).toBeVisible({ timeout: 20_000 });

    // Baseline visual snapshot for regression matrix.
    await expect(page).toHaveScreenshot('mission-control-morning.png', {
      fullPage: false,
      maxDiffPixelRatio: 0.02,
    });
  });

  test('axe-core · mission control has zero violations', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const loginForm = page.getByTestId('login-form');
    const loginVisible = await loginForm.isVisible().catch(() => false);
    if (loginVisible) {
      await page.getByTestId('login-email').fill('operator@coinnike.com');
      await page.getByTestId('login-password').fill('prototype123');
      await page.getByTestId('login-submit').click();
      await page.getByTestId('mission-control').waitFor({ timeout: 20_000 });
    }

    await injectAxe(page);
    const { getViolations } = require('axe-playwright');
    // Sprint 2 N1 · load allowlist per SPRINT_2_PLANNING.md §7 R4.
    const path = require('path');
    const fs = require('fs');
    const axerc = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', '.axerc.json'), 'utf8'));
    const waivedRules = new Set(axerc.waivers.map((w) => w.rule));

    const rawViolations = await getViolations(page, undefined, {
      axeOptions: { rules: { 'color-contrast': { enabled: true } } },
    });
    const violations = rawViolations.filter((v) => !waivedRules.has(v.id));
    const waived = rawViolations.filter((v) => waivedRules.has(v.id));

    if (violations.length) {
      console.log('AXE UNWAIVED VIOLATIONS:', JSON.stringify(violations.map((v) => ({
        id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
        targets: v.nodes.slice(0, 5).map((n) => n.target),
      })), null, 2));
    }
    if (waived.length) {
      console.log(`AXE WAIVED (documented in .axerc.json): ${waived.map((v) => v.id).join(', ')}`);
    }
    expect(violations, `${violations.length} unwaived a11y violations`).toHaveLength(0);
  });
});
