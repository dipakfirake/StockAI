import { test, expect } from '@playwright/test';

test.describe('Phase 3: Navigation & Page Rendering', () => {

  const ROUTES = [
    { path: '/dashboard', title: 'Market Dashboard' },
    { path: '/scanner', title: 'Market Scanner' },
    { path: '/alerts', title: 'Alerts' },
    { path: '/backtest', title: 'Strategy Backtesting' },
    { path: '/pricing', title: 'Upgrade to PRO' },
    { path: '/heatmap', title: 'Market Heatmap' },
    { path: '/options/NIFTY', title: 'Options Chain' },
    { path: '/paper-trading', title: 'Positions' },
    { path: '/portfolio', title: 'Portfolio' },
    { path: '/settings', title: 'System Settings & Risk Management' }
  ];

  const escapeRegExp = (str: string) => str.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&');

  test('Should render all main routes without crashing', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('text=Market Dashboard')).toBeVisible({ timeout: 120000 });

    for (const route of ROUTES) {
      await page.goto(route.path);
      await expect(page).toHaveURL(new RegExp(`${escapeRegExp(route.path)}$`), { timeout: 120000 });
      await expect(page.locator('main')).toBeVisible({ timeout: 120000 });
      const content = await page.content();
      expect(content).not.toContain('A client-side exception has occurred');
      expect(content).not.toContain('Unhandled Runtime Error');
    }
  });

});
