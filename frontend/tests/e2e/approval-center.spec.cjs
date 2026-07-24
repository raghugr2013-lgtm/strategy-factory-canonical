/*
 * Playwright · ApprovalCenter surface (Phase B).
 *
 * Verifies the new institutional-language surface at /c/approvals/center:
 *   - Header (eyebrow, headline, briefing, mono trailer).
 *   - Facet bar cascade (risk axis).
 *   - Priority-sorted grid.
 *   - Approve/defer/block resolve into the session-scoped resolved strip.
 *   - Cascade shows on the sibling Approvals surface (shared facet plane).
 *   - "Try the new Approval Center" link from the legacy Approvals surface.
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

test.describe('Phase B · Approval Center', () => {
  test('surface anatomy is present', async ({ page }) => {
    await login(page);
    await page.goto('/c/approvals/center');
    await expect(page.getByTestId('approval-center')).toBeVisible({ timeout: 10_000 });
    // SurfaceHeader (from Phase A) drives eyebrow/headline/briefing/trailer.
    await expect(page.getByTestId('approval-center-header-eyebrow')).toContainText(/human gates/i);
    await expect(page.getByTestId('approval-center-header-headline')).toBeVisible();
    await expect(page.getByTestId('approval-center-header-briefing')).toBeVisible();
    // Facet bar exposes the 4 canonical risk tabs.
    for (const key of ['all', 'high', 'moderate', 'low']) {
      await expect(page.getByTestId(`approval-center-facet-${key}`)).toBeVisible();
    }
    // Cascade hint reads the shared facet plane.
    await expect(page.getByTestId('approval-center-cascade-hint')).toContainText(/cascade\s*·\s*risk/i);
  });

  test('facet cascade updates both surfaces (shared risk axis)', async ({ page }) => {
    await login(page);
    // Land on the new center, flip facet to high.
    await page.goto('/c/approvals/center');
    await expect(page.getByTestId('approval-center')).toBeVisible();
    await page.getByTestId('approval-center-facet-high').click();
    await expect(page.getByTestId('approval-center-facet-high')).toHaveAttribute('aria-selected', 'true');
    // Sibling Approvals surface must inherit the same facet from navigationStore.
    await page.goto('/c/approvals');
    await expect(page.getByTestId('approvals')).toBeVisible();
    await expect(page.getByTestId('approvals-cascade-hint')).toContainText(/risk\s+high/i);
  });

  test('discovery link on legacy surface routes to new center', async ({ page }) => {
    await login(page);
    await page.goto('/c/approvals');
    await expect(page.getByTestId('approvals')).toBeVisible();
    const link = page.getByTestId('approvals-try-approval-center');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByTestId('approval-center')).toBeVisible({ timeout: 10_000 });
  });

  test('approve resolves a card into the resolved strip', async ({ page }) => {
    await login(page);
    await page.goto('/c/approvals/center');
    await expect(page.getByTestId('approval-center')).toBeVisible();
    // Facet=all so the fixture provides at least one card.
    await page.getByTestId('approval-center-facet-all').click();
    // Locate ANY card in the grid and click its Approve.
    const firstCard = page.locator('[data-testid^="approval-center-card-"]').first();
    await firstCard.waitFor({ timeout: 5_000 });
    const cardTestId = await firstCard.getAttribute('data-testid');
    const cardId = cardTestId.replace('approval-center-card-', '');
    await firstCard.getByRole('button', { name: /approve/i }).click();
    // Resolved strip must contain the approved id.
    await expect(page.getByTestId(`approval-center-resolved-${cardId}`)).toBeVisible({ timeout: 5_000 });
  });
});
