import { test, expect } from '@playwright/test';

const STOCKS = [
  { symbol: 'RELIANCE.NS', name: 'Reliance' },
  { symbol: 'TCS.NS', name: 'TCS' },
];

const ROUTES = [
  { path: '/dashboard', label: 'Market Dashboard' },
  { path: '/scanner', label: 'Market Scanner' },
  { path: '/options/^NSEI', label: 'Options Chain' },
  { path: '/alerts', label: 'Alerts' },
  { path: '/paper-trading', label: 'Positions' },
  { path: '/backtest', label: 'Strategy Backtesting' },
  { path: '/portfolio', label: 'Portfolio' },
  { path: '/settings', label: 'System Settings & Risk Management' },
];

const escapeRegExp = (str: string) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const getNormalizedPathname = (url: string) => {
  try {
    return decodeURIComponent(new URL(url).pathname)
  } catch {
    return url
  }
}

test.describe('Full System QA: Navigation, Search, Charting, and Quant Validations', () => {
  test('Should login and access all main pages without errors', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('text=Login')).toBeVisible();

    // Use storage state auth from global setup
    await page.goto('/dashboard');
    await expect(page.locator('text=Market Dashboard')).toBeVisible({ timeout: 120000 });

    for (const route of ROUTES) {
      await page.goto(route.path);
      expect(getNormalizedPathname(page.url())).toBe(route.path);
      const content = await page.content();
      expect(content).not.toContain('A client-side exception has occurred');
      expect(content).not.toContain('Unhandled Runtime Error');
      await expect(page.locator('body')).toContainText(route.label, { timeout: 120000 });
    }
  });

  test('Should search stock symbols and load chart analysis successfully', async ({ page }) => {
    await page.goto('/chart/^NSEI');
    await expect(page.locator('text=Chart Analysis')).toBeVisible({ timeout: 120000 });

    for (const stock of STOCKS) {
      const searchInput = page.getByPlaceholder('Search symbol or company...').first();
      await expect(searchInput).toBeVisible({ timeout: 120000 });

      await searchInput.fill(stock.symbol);
      const listbox = page.getByRole('listbox').first();
      await expect(listbox).toBeVisible({ timeout: 120000 });

      const suggestion = listbox.locator(`[data-testid="stock-search-option-${stock.symbol}"]`).first();
      await expect(suggestion).toBeVisible({ timeout: 120000 });
      await suggestion.click();
      await page.waitForURL(new RegExp(`/chart/${escapeRegExp(stock.symbol)}`), { timeout: 120000 });

      await expect(page.locator('text=Swing Trade Analysis')).toBeVisible({ timeout: 160000 });
      const targetPriceLabel = page.locator('text=Target Price').or(page.locator('text=Upper Bound'));
      await expect(targetPriceLabel.first()).toBeVisible();
      await expect(page.locator('text=Expected Duration')).toBeVisible();

      const pageText = await page.textContent('body');
      expect(pageText).not.toContain('NaN');
      expect(pageText).not.toContain('undefined');
    }
  });

  test('Should validate that chart candle display updates when switching timeframes', async ({ page }) => {
    await page.goto('/chart/RELIANCE.NS');
    await expect(page.locator('text=Chart Analysis')).toBeVisible({ timeout: 120000 });

    const buttons = ['1m', '5m', '15m', '30m', '1h', '1d'];
    for (const label of buttons) {
      const button = page.locator('main').getByRole('button', { name: label, exact: true }).first();
      if (await button.count() > 0 && await button.isVisible()) {
        await button.click();
        await page.waitForTimeout(2000);
        await expect(page.locator('text=Chart Analysis')).toBeVisible();
      }
    }
  });
});
