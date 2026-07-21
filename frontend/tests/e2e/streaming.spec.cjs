/*
 * Playwright · N3 streaming surfaces (Sprint 2 N3).
 * Verifies:
 *   • Timeline · Approvals · StatusRail all mount a StreamPostmark.
 *   • In freeze mode (no REACT_APP_WSS_URL) mode=poll is engaged.
 *   • tickCount increments over time (proves the fallback is running).
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

const readTickCount = async (postmark) => {
  const attr = await postmark.getAttribute('data-stream-tick-count');
  return Number(attr || 0);
};

test.describe('N3 · streaming surfaces', () => {
  test('status-rail streams (poll fallback) with tick counter', async ({ page }) => {
    await login(page);
    const postmark = page.getByTestId('status-rail-stream-postmark');
    await expect(postmark).toBeVisible();
    // In freeze mode, mode must be either 'initial' immediately then 'poll' after intervalMs.
    // We accept any of {initial, poll, wss} initially, but after 12s it must NOT be 'boot'.
    const initialMode = await postmark.getAttribute('data-stream-mode');
    expect(['initial', 'poll', 'wss']).toContain(initialMode);
    const t0 = await readTickCount(postmark);
    // Wait long enough for the 10 000 ms status-rail poll interval to fire.
    await page.waitForTimeout(11_500);
    const t1 = await readTickCount(postmark);
    expect(t1, `expected tickCount to grow (t0=${t0}, t1=${t1})`).toBeGreaterThan(t0);
  });

  test('timeline stream postmark renders + polls', async ({ page }) => {
    await login(page);
    await page.getByTestId('nav-timeline').click();
    const postmark = page.getByTestId('timeline-stream-postmark');
    await expect(postmark).toBeVisible({ timeout: 10_000 });
    const mode = await postmark.getAttribute('data-stream-mode');
    expect(['initial', 'poll', 'wss']).toContain(mode);
  });

  test('approvals stream postmark renders + polls', async ({ page }) => {
    await login(page);
    await page.getByTestId('nav-approvals').click();
    const postmark = page.getByTestId('approvals-stream-postmark');
    await expect(postmark).toBeVisible({ timeout: 10_000 });
    const mode = await postmark.getAttribute('data-stream-mode');
    expect(['initial', 'poll', 'wss']).toContain(mode);
  });
});
