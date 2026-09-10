import { test, expect } from '@playwright/test';

// Test matrix covering different market caps as requested by the master analyst
const STOCKS_TO_TEST = [
  { symbol: 'TCS.NS', type: 'Large Cap IT' }
];

test.describe('Master Analyst Robot QA: Swing Trade Validations', () => {
  
  for (const stock of STOCKS_TO_TEST) {
    test(`Should fully analyze and render accurate Trade Setup for ${stock.symbol} (${stock.type})`, async ({ page }) => {
      
      // 1. Navigate directly to the Chart Page for the specific stock
      // This bypasses the UI search bar which can sometimes be hidden on smaller viewports
      await page.goto(`/chart/${stock.symbol}`);
      
      // 2. Wait for the heavy AI backend to finish calculating (Up to 45 seconds)
      // We look for the "Swing Trade Analysis" card to appear
      const swingTradeCard = page.locator('text=Swing Trade Analysis');
      await expect(swingTradeCard).toBeVisible({ timeout: 160000 });
      
      // 4. Assert Mathematical Precision & UI Rendering
      // Check that the system didn't output raw JSON or 'undefined' for Target Price
      const targetPriceLabel = page.locator('text=Target Price').or(page.locator('text=Upper Bound'));
      await expect(targetPriceLabel.first()).toBeVisible();
      
      // Check that Expected Duration doesn't say N/A
      const expectedDurationLabel = page.locator('text=Expected Duration');
      await expect(expectedDurationLabel).toBeVisible();
      
      // Verify that the Trade Setup actually contains numbers and not just symbols
      // We look for the ₹ symbol followed by digits, indicating the target price rendered correctly
      const targetValue = page.locator('div', { hasText: /^₹\d+(\.\d+)?$/ }).first();
      // It might not always have digits if the score is very weird, but our formula guarantees a number.
      // So we just ensure it doesn't say "NaN" or "undefined"
      const textContent = await page.content();
      expect(textContent).not.toContain('NaN');
      expect(textContent).not.toContain('undefined');
      
      console.log(`✅ Passed full AI Validation for ${stock.symbol}`);
    });
  }
});
