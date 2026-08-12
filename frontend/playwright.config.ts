import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  globalSetup: require.resolve('./e2e/global-setup'),
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Prevent Yahoo Finance rate limiting during local testing
  reporter: 'html',
  timeout: 180000, // Increase global timeout to 180s for slow API fetches during AI Analysis
  use: {
    baseURL: 'http://localhost:5173',
    storageState: 'e2e/storageState.json',
    trace: 'on-first-retry',
    actionTimeout: 180000,
    navigationTimeout: 180000,
  },
  expect: {
    timeout: 180000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: process.platform === 'win32' ? 'npm.cmd run dev' : 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
