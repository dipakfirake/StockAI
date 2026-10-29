import { test, expect } from '@playwright/test';

test.describe('Phase 3: Frontend Components & Auth Validation', () => {
  // Use a completely clean browser state (no JWT) for testing the Auth page
  test.use({ storageState: { cookies: [], origins: [] } });

  const TEST_EMAIL = `test_qa_${Date.now()}@stockai.com`;
  const TEST_PASSWORD = 'SecurePassword123!';

  test('User Registration Pre-check, Form Validation, and Login Flow', async ({ page, request }) => {
    // 1. Pre-create the user via API so we can test end-to-end login & logout
    const regRes = await request.post('http://127.0.0.1:8000/api/auth/register', {
      data: {
        email: TEST_EMAIL,
        name: 'QA Robot',
        password: TEST_PASSWORD
      }
    });
    expect(regRes.ok()).toBeTruthy();

    await page.goto('/login');
    await expect(page.locator('.auth-card')).toBeVisible({ timeout: 15000 });

    // 2. Toggle to registration view and test validation checklist
    const toggleToRegister = page.locator('text=Register with verified email');
    await expect(toggleToRegister).toBeVisible();
    await toggleToRegister.click();

    // Verify registration fields appear
    await expect(page.locator('input[placeholder="Enter your name"]')).toBeVisible();
    await page.fill('input[placeholder="Enter your name"]', 'QA Robot');
    await page.fill('input[type="email"]', `another_${Date.now()}@stockai.com`);
    await page.fill('input[type="password"]', TEST_PASSWORD);

    // Verify password checklist passes
    await expect(page.locator('text=8 to 128 characters')).toBeVisible();
    await expect(page.locator('text=At least 1 letter (a-z, A-Z)')).toBeVisible();
    await expect(page.locator('text=At least 1 number or special character')).toBeVisible();

    // 3. Toggle back to Sign In
    const toggleToLogin = page.locator('text=Sign in here');
    await toggleToLogin.click();

    // 4. Test invalid login handling
    await page.fill('input[type="email"]', TEST_EMAIL);
    await page.fill('input[type="password"]', 'WrongPassword999!');
    await page.click('button[type="submit"]');
    await expect(page.locator('.auth-error, [class*="error"]')).toBeVisible({ timeout: 5000 });

    // 5. Test successful login with correct credentials
    await page.fill('input[type="password"]', TEST_PASSWORD);
    await page.click('button[type="submit"]');

    // Should redirect to dashboard upon successful login
    await expect(page).toHaveURL(/.*\/dashboard/, { timeout: 15000 });
    await expect(page.locator('main')).toBeVisible();

    // Verify JWT token is stored in localStorage
    const token = await page.evaluate(() => localStorage.getItem('auth_token'));
    expect(token).toBeTruthy();

    // 6. Logout and verify redirect
    const logoutBtn = page.locator('[title="Logout"], button:has-text("Logout"), [aria-label="Logout"]');
    if (await logoutBtn.isVisible().catch(() => false)) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });
    }
  });
});
