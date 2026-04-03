/**
 * Auth Smoke Test — verifies the login → cookie → dashboard chain works end-to-end.
 * Runs first alphabetically so auth failures surface early with clear diagnostics.
 */
import { test, expect } from '@playwright/test';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

test.describe('Auth Smoke Test', () => {
    test('login sets cookie and reaches authenticated page', async ({ page }) => {
        test.setTimeout(30000);

        await page.goto('/login');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);

        await Promise.all([
            page.waitForResponse(res => res.url().includes('/api/admin/auth/login')),
            page.click('button[type="submit"]'),
        ]);

        // Wait for redirect to any authenticated page
        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 15000 });

        // Verify auth cookie was set
        const cookies = await page.context().cookies();
        const hasAccessToken = cookies.some(c => c.name === 're_access_token');
        expect(hasAccessToken).toBe(true);
    });
});
