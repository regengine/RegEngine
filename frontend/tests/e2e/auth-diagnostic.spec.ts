/**
 * Auth Smoke Test
 *
 * Verifies the end-to-end authentication chain works in CI:
 *   1. Login API returns a valid JWT
 *   2. /api/session sets the re_access_token cookie
 *   3. An authenticated page is reachable without redirecting to /login
 *
 * Runs before other test files (alphabetically) so infrastructure failures
 * are surfaced immediately rather than appearing as dozens of test timeouts.
 */
import { test, expect } from '@playwright/test';
import { authenticatedE2ESkipReason, hasAuthenticatedE2E } from './auth-prereqs';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

test.describe('Auth Smoke', () => {
    test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);

    test('login API → session cookie → authenticated page', async ({ page }) => {
        test.setTimeout(60000);

        // Step 1: Login via browser (the real user flow)
        await page.goto('/login');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');

        // Step 2: Should reach an authenticated destination
        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 30000 });

        // Step 3: re_access_token cookie must be present and HTTP-only
        const cookies = await page.context().cookies();
        const accessToken = cookies.find(c => c.name === 're_access_token');
        expect(accessToken).toBeDefined();
        expect(accessToken?.httpOnly).toBe(true);

        // Step 4: Navigating to /dashboard must not redirect to /login
        await page.goto('/dashboard');
        await page.waitForLoadState('networkidle');
        await expect(page).not.toHaveURL(/\/login/);
    });
});
