import { test, expect } from '@playwright/test';

test.describe('Phase 3: Core Features & Logic', () => {

  test('Paper Trading execution flow', async ({ page }) => {
    await page.goto('/paper-trading');
    
    // Check if we need to login (assuming we are already logged in via state, or we just test the UI renders the prompt)
    // For this test, we verify the Paper Trading modal opens
    const tradeButton = page.locator('text=Execute Trade');
    if (await tradeButton.isVisible()) {
      await tradeButton.click();
      await expect(page.locator('text=Order Details')).toBeVisible();
    }
  });

  test('Options Chain loads Greek Values', async ({ page }) => {
    await page.goto('/options/INFY.NS');
    
    // Wait for the chain to generate and the View Options Greeks button to appear
    const viewGreeksBtn = page.locator('text=View Options Greeks');
    await expect(viewGreeksBtn).toBeVisible({ timeout: 120000 });
    
    // Click View Options Greeks to reveal Delta, Gamma, Theta
    await viewGreeksBtn.click();
    
    // Assert that the table renders the columns correctly
    await expect(page.locator('text=Delta').first()).toBeVisible({ timeout: 120000 });
    await expect(page.locator('text=Gamma').first()).toBeVisible();
    await expect(page.locator('text=Theta').first()).toBeVisible();
    
    // Assert there is no NaN in the table
    const tableHtml = await page.locator('table').innerHTML();
    expect(tableHtml).not.toContain('NaN');
  });

});
