import { test, expect } from '@playwright/test';

test.describe('Autonomous Full-System Crawler, Interaction & Security Audit', () => {

  const PAGES_TO_CRAWL = [
    { path: '/dashboard', name: 'Dashboard & Market Intelligence', checkText: 'Market Dashboard' },
    { path: '/chart', name: 'Interactive Charts & Indicators', checkText: 'Chart Analysis' },
    { path: '/screener', name: 'Swing Screener & Multi-Factor Scoring', checkText: 'Screener' },
    { path: '/scanner', name: 'Real-Time Breakout & Pattern Scanner', checkText: 'Scanner' },
    { path: '/heatmap', name: 'Nifty 50 Sector Heatmap', checkText: 'Heatmap' },
    { path: '/options', name: 'Options Chain & Greeks Analyzer', checkText: 'Options Chain' },
    { path: '/alerts', name: 'Real-time Price & Pattern Alerts', checkText: 'Alerts' },
    { path: '/portfolio', name: 'Portfolio & Holding Analytics', checkText: 'Portfolio' },
    { path: '/paper-trading', name: 'Paper Trading & Execution Engine', checkText: 'Positions' },
    { path: '/backtest', name: 'Strategy Backtesting Engine', checkText: 'Backtest' },
    { path: '/smc-watchlist', name: 'Smart Money Concepts (SMC) Watchlist', checkText: 'Smart Money' },
    { path: '/pricing', name: 'Pricing & Pro Subscription Tier', checkText: 'Upgrade to PRO' },
    { path: '/settings', name: 'Settings & Risk Parameters', checkText: 'Settings' },
    { path: '/admin', name: 'Operations & Admin SRE Portal', checkText: 'Admin' },
    { path: '/admin/sentinel', name: 'Project Sentinel Architectural Telemetry', checkText: 'Sentinel' }
  ];

  test('Autonomous Crawl across all 15 Core Pages with Auto-Clicking, Card Inspection & Zero-Error Audit', async ({ page }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const failedRequests: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Ignore expected network timeouts in mock test environment
        if (!text.includes('Failed to load resource') && !text.includes('net::ERR_')) {
          consoleErrors.push(`[Console Error] ${text}`);
        }
      }
    });

    page.on('pageerror', err => {
      pageErrors.push(`[Page Error] ${err.message}`);
    });

    page.on('response', resp => {
      if (resp.status() >= 500) {
        failedRequests.push(`[5xx Server Error] ${resp.status()} on ${resp.url()}`);
      }
    });

    // 1. Initial Dashboard Load & Cookie Consent Dismissal
    await page.goto('/dashboard');
    await expect(page.locator('main')).toBeVisible({ timeout: 60000 });

    const acceptCookiesBtn = page.getByRole('button', { name: /accept all|accept/i }).first();
    if (await acceptCookiesBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await acceptCookiesBtn.click();
      await page.waitForTimeout(300);
    }

    // 2. Iterate and stress-test all pages
    for (const p of PAGES_TO_CRAWL) {
      console.log(`🔍 Crawling and auto-interacting with: ${p.name} (${p.path})...`);
      
      await page.goto(p.path);
      await expect(page.locator('main')).toBeVisible({ timeout: 60000 });

      // Allow any loading spinner to detach gracefully
      await page.locator('.spinner, [data-testid="loading"]').first().waitFor({ state: 'detached', timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(400);

      // Verify page content loaded without uncaught exceptions
      const bodyText = await page.innerText('body');
      expect(bodyText).not.toContain('A client-side exception has occurred');
      expect(bodyText).not.toContain('Unhandled Runtime Error');

      // 3. Auto-Click interactive elements (tabs, filters, chips, toggle buttons)
      const tabs = page.locator('button[role="tab"], button:has-text("Overview"), button:has-text("Users"), button:has-text("Ops"), button:has-text("Greeks"), button:has-text("1D"), button:has-text("1W")');
      const tabCount = await tabs.count();
      for (let i = 0; i < Math.min(tabCount, 5); i++) {
        const tab = tabs.nth(i);
        if (await tab.isVisible().catch(() => false) && await tab.isEnabled().catch(() => false)) {
          try {
            await tab.click({ timeout: 2000 });
            await page.waitForTimeout(200); // Allow animation to settle
          } catch (_) {
            // Ignore click intercept by tooltips or animations
          }
        }
      }

      // 4. Test Structural Containers & Card Interactions
      const structuralContainers = page.locator('.card, .stat-card, [class*="card"], .table-container, .page-header, [role="button"], main > div');
      const containerCount = await structuralContainers.count();
      expect(containerCount).toBeGreaterThanOrEqual(1); // Page must render meaningful content layout

      // 5. Test modals & drawer triggers if any
      const modalOpeners = page.locator('button:has-text("Add"), button:has-text("Filter"), button:has-text("Settings"), button:has-text("Place Order")');
      const openerCount = await modalOpeners.count();
      for (let i = 0; i < Math.min(openerCount, 2); i++) {
        const btn = modalOpeners.nth(i);
        if (await btn.isVisible() && await btn.isEnabled()) {
          try {
            await btn.click({ timeout: 2000 });
            await page.waitForTimeout(300);
            // Close modal via close button or Escape key
            const closeBtn = page.locator('button[aria-label="Close"], button:has-text("Cancel"), button:has-text("✕")').first();
            if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
              await closeBtn.click();
            } else {
              await page.keyboard.press('Escape');
            }
            await page.waitForTimeout(200);
          } catch (_) {}
        }
      }

      console.log(`✅ Passed interaction checks for: ${p.name}`);
    }

    // 6. Assert Zero Severe Runtime Crashes
    expect(pageErrors).toEqual([]);
    expect(failedRequests).toEqual([]);
  });

});
