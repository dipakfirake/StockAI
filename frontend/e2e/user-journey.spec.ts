import { test, expect } from '@playwright/test';

test.describe('Full User-Journey Functional Testing', () => {
  test('Should complete search, analyze, and paper trade journey', async ({ page }) => {
    // 1. Navigate to the dashboard
    await page.goto('/dashboard');
    await expect(page.locator('text=Market Dashboard')).toBeVisible({ timeout: 120000 });
    
    // 2. Test the Theme Toggle Button
    const htmlElement = page.locator('html');
    const initialTheme = await htmlElement.getAttribute('class');
    
    // Find theme toggle button (usually an icon button in the navbar, we'll look for sun/moon or theme toggle aria label)
    // Looking for the button that switches theme
    const themeBtn = page.getByRole('button', { name: /theme|dark mode|light mode/i }).first();
    if (await themeBtn.count() > 0) {
      await themeBtn.click();
      await page.waitForTimeout(500);
      const newTheme = await htmlElement.getAttribute('class');
      expect(newTheme).not.toBe(initialTheme);
      // Click again to revert
      await themeBtn.click();
    }
    
    // 3. Use the Global Search Bar
    const searchInput = page.getByPlaceholder('Search symbol or company...').first();
    await searchInput.fill('TCS.NS');
    
    // Wait for dropdown suggestion and click it
    const listbox = page.getByRole('listbox').first();
    await expect(listbox).toBeVisible({ timeout: 120000 });
    const suggestion = listbox.locator('[data-testid="stock-search-option-TCS.NS"]').first();
    await expect(suggestion).toBeVisible({ timeout: 60000 });
    await suggestion.click();
    
    // Verify it navigates to the chart
    await page.waitForURL(/\/chart\/TCS\.NS/, { timeout: 120000 });
    await expect(page.locator('text=Chart Analysis')).toBeVisible({ timeout: 120000 });
    
    // 4. Test Paper Trading Execution
    await page.goto('/paper-trading');
    await expect(page.locator('text=Orders & Positions')).toBeVisible({ timeout: 120000 });
    
    // Click Place Order to open the modal
    const placeOrderBtn = page.getByRole('button', { name: 'Place Order' }).first();
    await expect(placeOrderBtn).toBeVisible({ timeout: 60000 });
    await placeOrderBtn.click();
    
    // Fill out the Place Order form
    await page.getByPlaceholder('e.g. RELIANCE.NS').fill('HDFCBANK.NS');
    await page.locator('input[type="number"]').first().fill('50');
    
    // Click BUY button
    const buyButton = page.getByRole('button', { name: 'BUY' }).first();
    await expect(buyButton).toBeVisible();
    await buyButton.click();
    
    // Wait for success toast or position to appear in the table
    // The table should eventually contain HDFCBANK.NS
    const positionsTable = page.getByRole('table').first();
    await expect(positionsTable).toContainText('HDFCBANK.NS', { timeout: 60000 });
  });
});
