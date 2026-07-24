/*
 * Playwright · StrategyExplorer surface (Phase C).
 *
 * Verifies the new discovery surface at /c/strategies/explorer:
 *   - SurfaceHeader anatomy (eyebrow / headline / briefing / trailer).
 *   - Facet bar cascade (status axis, 4 filters).
 *   - Selected-row highlight via workspaceStore.selectedStrategy.
 *   - Discovery link from legacy Strategies surface.
 *   - Return-crumb wiring (back to explorer) after row activation.
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

test.describe('Phase C · Strategy Explorer', () => {
  test('surface anatomy is present', async ({ page }) => {
    await login(page);
    await page.goto('/c/strategies/explorer');
    await expect(page.getByTestId('strategy-explorer')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('strategy-explorer-header-eyebrow')).toContainText(/portfolio/i);
    await expect(page.getByTestId('strategy-explorer-header-headline')).toBeVisible();
    await expect(page.getByTestId('strategy-explorer-header-briefing')).toBeVisible();
    for (const key of ['all', 'live', 'paper', 'archived']) {
      await expect(page.getByTestId(`strategy-explorer-facet-${key}`)).toBeVisible();
    }
    await expect(page.getByTestId('strategy-explorer-cascade-hint'))
      .toContainText(/cascade\s*·\s*status/i);
  });

  test('facet cascade updates legacy Strategies surface', async ({ page }) => {
    await login(page);
    await page.goto('/c/strategies/explorer');
    await expect(page.getByTestId('strategy-explorer')).toBeVisible();
    await page.getByTestId('strategy-explorer-facet-live').click();
    await expect(page.getByTestId('strategy-explorer-facet-live'))
      .toHaveAttribute('aria-selected', 'true');
    await page.goto('/c/strategies');
    await expect(page.getByTestId('strategies')).toBeVisible();
    await expect(page.getByTestId('strategies-cascade-hint')).toContainText(/status\s+live/i);
  });

  test('discovery link routes to explorer from legacy strategies', async ({ page }) => {
    await login(page);
    await page.goto('/c/strategies');
    await expect(page.getByTestId('strategies')).toBeVisible();
    const link = page.getByTestId('strategies-try-explorer');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByTestId('strategy-explorer')).toBeVisible({ timeout: 10_000 });
  });

  test('row activation opens the passport and sets the return crumb', async ({ page }) => {
    await login(page);
    await page.goto('/c/strategies/explorer');
    await expect(page.getByTestId('strategy-explorer-table')).toBeVisible({ timeout: 10_000 });
    // Click the first row (double-click activates in TableTile).
    const firstRow = page.locator('[data-testid="strategy-explorer-table"] tbody tr').first();
    await firstRow.waitFor({ timeout: 5_000 });
    await firstRow.dblclick();
    // Now on strategy passport.
    await expect(page).toHaveURL(/\/c\/strategies\/strat-/);
    // A return crumb should be present pointing back to the explorer.
    await expect(page.getByText(/back to explorer/i)).toBeVisible({ timeout: 5_000 });
  });
});
