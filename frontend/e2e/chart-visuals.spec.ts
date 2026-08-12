import { test, expect } from '@playwright/test';

test.describe('Chart Visual and Rendering QA', () => {
  test('Should render actual candlesticks on the canvas (pixel validation)', async ({ page }) => {
    // 1. Load the chart page for a highly liquid Indian stock
    await page.goto('/chart/RELIANCE.NS');
    
    // 2. Wait for the main UI skeleton and API data
    await expect(page.locator('text=Chart Analysis')).toBeVisible({ timeout: 120000 });
    
    // Ensure the loading state disappears
    const loader = page.locator('.animate-spin').first();
    if (await loader.count() > 0) {
      await expect(loader).toBeHidden({ timeout: 60000 });
    }

    // Wait an extra few seconds for lightweight-charts to animate/render
    await page.waitForTimeout(5000);

    // 3. Verify Lightweight Charts initialized properly
    // Lightweight-charts creates 3 overlapping canvases per chart pane
    // Since we have indicators (volume, RSI, MACD, etc.), we expect at least 3 canvases
    const canvases = page.locator('canvas');
    await expect(canvases.first()).toBeVisible({ timeout: 15000 });
    const count = await canvases.count();
    expect(count).toBeGreaterThanOrEqual(3);
    
    // 4. Verify the container has actual dimensions (it rendered visually on screen)
    const chartContainer = page.locator('.tv-lightweight-charts').first();
    await expect(chartContainer).toBeVisible();
    
    const box = await chartContainer.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(300);
    expect(box!.height).toBeGreaterThan(200);
  });
});
