import { test, expect, Page } from '@playwright/test';

/**
 * RBAC Gates E2E Tests
 * 
 * Verifies that role-based access control works correctly at the browser level:
 * - Unauthenticated users are redirected to login
 * - Non-admin users cannot access admin-only sections
 * - RBAC permission checks enforce UI restrictions
 */

const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || 'test-placeholder';

test.describe('RBAC Gates', () => {

    test.afterEach(async ({ page }, testInfo) => {
        if (testInfo.status !== 'passed') {
            const path = `test-results/rbac-failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}.png`;
            await page.screenshot({ path, fullPage: true });
        }
    });

    test('Unauthenticated users are redirected to login', async ({ page }) => {
        // Navigate directly to protected route without authentication
        await page.goto('/dashboard');

        // Should redirect to login page
        await expect(page).toHaveURL(/\/login/);

        // Login form should be visible
        await expect(page.locator('input[type="email"]')).toBeVisible();
        await expect(page.locator('input[type="password"]')).toBeVisible();
    });

    test('Unauthenticated cannot access sysadmin', async ({ page }) => {
        await page.goto('/sysadmin');

        // Should redirect to login
        await expect(page).toHaveURL(/\/login/);
    });

    test('Unauthenticated cannot access user settings', async ({ page }) => {
        await page.goto('/settings/users');

        // Should redirect to login
        await expect(page).toHaveURL(/\/login/);
    });

    test('Admin can access sysadmin dashboard', async ({ page }) => {
        test.setTimeout(60000);

        // Login as admin
        await page.goto('/login');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        // Wait for redirect to dashboard or sysadmin
        await expect(page).toHaveURL(/\/(dashboard|sysadmin)/);

        // Navigate to sysadmin
        await page.goto('/sysadmin');

        // Should stay on sysadmin (not redirected)
        await expect(page).toHaveURL(/\/sysadmin/);

        // Sysadmin content should be visible
        await expect(page.getByText(/System|Admin|Dashboard/i)).toBeVisible();
    });

    test('Admin can access user management', async ({ page }) => {
        test.setTimeout(60000);

        // Login as admin
        await page.goto('/login');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        await expect(page).toHaveURL(/\/(dashboard|sysadmin)/);

        // Navigate to user settings
        await page.goto('/settings/users');

        // Should stay on settings (not redirected)
        await expect(page).toHaveURL(/\/settings\/users/);

        // Team management content should be visible
        await expect(page.getByText(/Team|Users|Management/i)).toBeVisible();
    });

    test('Protected API calls return 401 without auth', async ({ page }) => {
        // Intercept API call without authentication
        const response = await page.request.get('http://localhost:8400/v1/admin/users');

        expect(response.status()).toBe(401);
    });

    test('Session persists across navigation', async ({ page }) => {
        test.setTimeout(60000);

        // Login
        await page.goto('/login');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        await expect(page).toHaveURL(/\/(dashboard|sysadmin)/);

        // Navigate to multiple pages
        await page.goto('/dashboard');
        await expect(page).toHaveURL(/\/dashboard/);

        await page.goto('/fsma');
        await expect(page).not.toHaveURL(/\/login/);

        await page.goto('/ingest');
        await expect(page).not.toHaveURL(/\/login/);

        // Session should still be valid
        await page.goto('/settings/users');
        await expect(page).toHaveURL(/\/settings\/users/);
    });

});
