/*
 * Playwright config · Sprint 2 N1.
 * Runs against the CRA production build served via `serve` so headless clicks
 * are not intercepted by the CRA WDS overlay iframe (Sprint 1 §5 L1).
 * See BASELINE_URL for override (default: http://127.0.0.1:4173).
 */
const { defineConfig, devices } = require('@playwright/test');

const PORT = process.env.PORT || 4173;
const BASE_URL = process.env.BASELINE_URL || `http://127.0.0.1:${PORT}`;

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: process.env.PLAYWRIGHT_NO_SERVER ? undefined : {
    command: `npx serve -s build -l ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
