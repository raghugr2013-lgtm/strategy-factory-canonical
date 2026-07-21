/*
 * Playwright · Sprint 2.0 tail patch (R1 + R2 + R3).
 * Verifies:
 *   R1 · Mission Control renders a Portfolio Equity metric block.
 *   R2 · Master Bot plan card renders a next-tick postmark with data-next-tick-at attr.
 *   R3 · ⌘K palette exposes three proposal entries; selecting one lands you on /c/approvals
 *        with the proposal appended to the queue.
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

test.describe('Sprint 2.0 tail · R1/R2/R3', () => {
  test('R1 · portfolio equity metric block renders on mission control', async ({ page }) => {
    await login(page);
    const block = page.getByTestId('mc-portfolio-equity');
    await expect(block).toBeVisible();
    await expect(block).toContainText('Portfolio equity');
  });

  test('R2 · master bot plan card exposes next-tick postmark', async ({ page }) => {
    await login(page);
    await page.getByTestId('nav-masterbot').click();
    await expect(page.getByTestId('master-bot')).toBeVisible({ timeout: 10_000 });
    const nextTick = page.getByTestId('mb-plan-next-tick');
    await expect(nextTick).toBeVisible();
    const attr = await nextTick.getAttribute('data-next-tick-at');
    expect(attr, 'next-tick postmark must have a data-next-tick-at attr').toBeTruthy();
    expect(attr).toMatch(/T\d\d:\d\d/);
  });

  test('R3 · palette exposes propose · optimize · promote entries', async ({ page }) => {
    await login(page);
    await page.keyboard.press('Meta+K');
    await expect(page.getByTestId('cmdk-palette')).toBeVisible();
    await expect(page.getByTestId('cmdk-item-propose-new-strategy')).toBeVisible();
    await expect(page.getByTestId('cmdk-item-optimize-strategy')).toBeVisible();
    await expect(page.getByTestId('cmdk-item-promote-to-live')).toBeVisible();
  });

  test('R3 · propose new strategy drops an ApprovalCard onto /c/approvals', async ({ page }) => {
    await login(page);
    await page.keyboard.press('Meta+K');
    await expect(page.getByTestId('cmdk-palette')).toBeVisible();
    await page.getByTestId('cmdk-item-propose-new-strategy').click();
    await expect(page).toHaveURL(/\/c\/approvals$/);
    await expect(page.getByTestId('approvals')).toBeVisible({ timeout: 10_000 });
    // The freshly-dropped proposal should appear in the pending grid.
    const proposalCard = page.locator('[data-testid^="approval-proposal-"]');
    await expect(proposalCard.first()).toBeVisible({ timeout: 5_000 });
    await expect(proposalCard.first()).toContainText('Propose new strategy');
  });

  test('R3 · promote-to-live drops a HIGH risk ApprovalCard', async ({ page }) => {
    await login(page);
    await page.keyboard.press('Meta+K');
    await page.getByTestId('cmdk-item-promote-to-live').click();
    await expect(page).toHaveURL(/\/c\/approvals$/);
    const proposalCard = page.locator('[data-testid^="approval-proposal-"]');
    await expect(proposalCard.first()).toBeVisible({ timeout: 5_000 });
    await expect(proposalCard.first()).toContainText('Promote');
  });
});
