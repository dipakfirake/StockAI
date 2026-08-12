import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';

test.describe('Phase 3: Frontend Components & Auth Validation', () => {
  // Use a completely clean browser state (no JWT) for testing the Auth page
  test.use({ storageState: { cookies: [], origins: [] } });

  const TEST_EMAIL = `test_QA_AUTH_${Date.now()}@stockai.com`;
  const TEST_PASSWORD = 'SecurePassword123!';

  test('User Registration and Login Flow', async ({ page }) => {
    await page.goto('/login');
    
    // Toggle to registration
    await page.click('text=Register here');
    
    // Fill out registration form
    await page.fill('input[type="text"]', 'QA Robot');
    await page.fill('input[type="email"]', TEST_EMAIL);
    await page.fill('input[type="password"]', TEST_PASSWORD);
    
    // Submit
    await page.click('button[type="submit"]');
    
    // Should show success message after registration
    await expect(page.locator('text=Registration successful. Please login.')).toBeVisible();
    
    // Now actually log in
    await page.fill('input[type="email"]', TEST_EMAIL);
    await page.fill('input[type="password"]', TEST_PASSWORD);
    await page.click('button[type="submit"]');

    // Should redirect to dashboard upon successful login
    await expect(page).toHaveURL(/.*\/dashboard/);
    await expect(page.locator('text=Market Dashboard')).toBeVisible();

    // Verify JWT token is stored in localStorage
    const token = await page.evaluate(() => localStorage.getItem('auth_token'));
    expect(token).toBeTruthy();
    
    // Logout
    await page.click('[title="Logout"]');
    await expect(page).toHaveURL(/.*\/login/);
  });

});
