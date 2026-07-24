/*
 * Playwright · TimelineExplorer surface (Phase E).
 *
 * Verifies the new discovery surface at /c/timeline/explorer:
 *   - SurfaceHeader anatomy (eyebrow / headline / briefing / trailer).
 *   - Facet bar (actor axis, 8 filters) drives adapter fetch.
 *   - Row memory keyed by pathname (Predictable Return).
 *   - Discovery link from legacy Timeline surface.
 *   - Evidence drawer opens on row click.
 *   - "open passport" footer action appears when subject references a
 *     strategy id, sets the return crumb and navigates to
 *     /c/strategies/:id.
 *   - Legacy Timeline surface still renders (regression).
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

const clearNavStorage = async (page) => {
  await page.evaluate(() => {
    try { sessionStorage.removeItem('sf-navigation-v1'); } catch { /* noop */ }
  });
};

test.describe('Phase E · Timeline Explorer', () => {
  test('surface anatomy is present', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline/explorer');
    await expect(page.getByTestId('timeline-explorer')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('timeline-explorer-header-eyebrow'))
      .toContainText(/Timeline Explorer/i);
    await expect(page.getByTestId('timeline-explorer-header-headline')).toBeVisible();
    await expect(page.getByTestId('timeline-explorer-header-briefing')).toBeVisible();
    // Facet bar carries 8 actor filters.
    for (const key of ['all', 'governance', 'master-bot', 'llm', 'ingestion', 'operator', 'validator', 'scheduler']) {
      await expect(page.getByTestId(`timeline-explorer-facet-${key}`)).toBeVisible();
    }
    // Time-window chip + stream postmark + cascade hint.
    await expect(page.getByTestId('timeline-explorer-time-window')).toBeVisible();
    await expect(page.getByTestId('timeline-explorer-stream-postmark')).toBeVisible();
    await expect(page.getByTestId('timeline-explorer-cascade-hint'))
      .toContainText(/cascade\s*·\s*actor/i);
  });

  test('event list renders from the timeline adapter', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline/explorer');
    await expect(page.getByTestId('timeline-explorer-list')).toBeVisible({ timeout: 10_000 });
    // Fixture contains a governance row referencing strat-014.
    await expect(page.getByTestId('timeline-explorer-row-e-01')).toBeVisible();
  });

  test('facet cascade updates the legacy Timeline surface', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline/explorer');
    await expect(page.getByTestId('timeline-explorer')).toBeVisible();
    await page.getByTestId('timeline-explorer-facet-governance').click();
    await expect(page.getByTestId('timeline-explorer-facet-governance'))
      .toHaveAttribute('aria-selected', 'true');
    // Navigate to legacy Timeline — cascade hint should reflect governance.
    await page.goto('/c/timeline');
    await expect(page.getByTestId('timeline')).toBeVisible();
    await expect(page.getByTestId('timeline-cascade-hint'))
      .toContainText(/actor\s+governance/i);
  });

  test('discovery link routes from legacy Timeline to the explorer', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline');
    await expect(page.getByTestId('timeline')).toBeVisible();
    const link = page.getByTestId('timeline-try-explorer');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByTestId('timeline-explorer')).toBeVisible({ timeout: 10_000 });
  });

  test('row click opens the evidence drawer', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline/explorer');
    await expect(page.getByTestId('timeline-explorer-list')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('timeline-explorer-row-e-01').click();
    // Evidence drawer becomes visible.
    await expect(page.getByTestId('evidence-drawer')).toBeVisible({ timeout: 5_000 });
    // strat-014 is referenced in the subject → passport shortcut visible.
    await expect(page.getByTestId('timeline-explorer-drawer-open-passport'))
      .toBeVisible();
  });

  test('open-passport shortcut sets the return crumb and navigates', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline/explorer');
    await expect(page.getByTestId('timeline-explorer-list')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('timeline-explorer-row-e-01').click();
    await expect(page.getByTestId('timeline-explorer-drawer-open-passport')).toBeVisible();
    await page.getByTestId('timeline-explorer-drawer-open-passport').click();
    // Land on strategy passport for strat-014.
    await expect(page).toHaveURL(/\/c\/strategies\/strat-014/);
    // Return crumb should read "back to timeline".
    await expect(page.getByText(/back to timeline/i)).toBeVisible({ timeout: 5_000 });
  });

  test('row memory restores selection on return', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline/explorer');
    await expect(page.getByTestId('timeline-explorer-list')).toBeVisible();
    await page.getByTestId('timeline-explorer-row-e-02').click();
    await expect(page.getByTestId('evidence-drawer')).toBeVisible();
    // Navigate away and back — the drawer should re-open for e-02.
    await page.goto('/c/mission');
    await expect(page.getByTestId('mission-control')).toBeVisible();
    await page.goto('/c/timeline/explorer');
    await expect(page.getByTestId('timeline-explorer-list')).toBeVisible();
    await expect(page.getByTestId('evidence-drawer')).toBeVisible({ timeout: 5_000 });
  });

  test('legacy Timeline surface still renders (regression)', async ({ page }) => {
    await login(page);
    await clearNavStorage(page);
    await page.goto('/c/timeline');
    await expect(page.getByTestId('timeline')).toBeVisible();
    await expect(page.getByTestId('timeline-list')).toBeVisible();
    // Facet + stream postmark stayed on the legacy surface.
    await expect(page.getByTestId('timeline-facet-all')).toBeVisible();
    await expect(page.getByTestId('timeline-stream-postmark')).toBeVisible();
  });
});
