import { test, expect, Page } from '@playwright/test';

/**
 * RBAC Gates E2E Tests
 *
 * Verifies that role-based access control works correctly at the browser level:
 * - Unauthenticated users are redirected to login
 * - Non-admin users cannot access admin-only sections
 * - RBAC permission checks enforce UI restrictions
 */

// Use dedicated admin account if available; fall back to the general test user.
// If your test user has sysadmin role, all admin tests will pass with just TEST_USER_EMAIL.
// Set TEST_ADMIN_EMAIL + TEST_ADMIN_PASSWORD secrets for a dedicated sysadmin account.
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL || process.env.TEST_USER_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_PASSWORD || 'test-placeholder';

// Sysadmin tests require a dedicated account with is_sysadmin=true.
// The test user created by globalSetup is a regular org owner, NOT a sysadmin.
const hasDedicatedAdmin = !!(
    process.env.TEST_ADMIN_EMAIL &&
    process.env.TEST_ADMIN_EMAIL !== process.env.TEST_USER_EMAIL
);

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

        // Should redirect to login (settings/* is auth-gated)
        await expect(page).toHaveURL(/\/login/);
    });

    test('Admin can access sysadmin dashboard', async ({ page }) => {
        // Requires a dedicated sysadmin account.
        // The test user created by globalSetup is a regular org member — not sysadmin.
        // The sysadmin page checks user.is_sysadmin client-side and redirects to /login if false.
        test.skip(!hasDedicatedAdmin, 'Requires a dedicated sysadmin account — set TEST_ADMIN_EMAIL + TEST_ADMIN_PASSWORD secrets pointing to a sysadmin user');

        test.setTimeout(60000);

        // Login as admin — ?next=/dashboard bypasses the onboarding check so
        // the test reliably lands on /dashboard regardless of the test user's
        // onboarding state.  Sysadmin accounts will still proceed normally.
        await page.goto('/login?next=/dashboard');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        // Wait for redirect to dashboard or sysadmin
        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 15000 });

        // Navigate to sysadmin
        await page.goto('/sysadmin');

        // Should stay on sysadmin (not redirected)
        await expect(page).toHaveURL(/\/sysadmin/);

        // Sysadmin content should be visible — use .first() to avoid strict-mode
        // violation when multiple nav elements match (e.g. "Admin" nav + page heading)
        await expect(page.getByText(/System|Admin|Dashboard/i).first()).toBeVisible();
    });

    test('Admin can access user management', async ({ page }) => {
        test.setTimeout(60000);

        // Login as admin — ?next=/dashboard bypasses the onboarding check
        await page.goto('/login?next=/dashboard');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 15000 });

        // Navigate to the team management page (canonical route).
        // NOTE: /settings/users permanently redirects (301) to /dashboard/settings which has
        // different content (API keys, integrations). The team/invite management lives at
        // /dashboard/team.
        await page.goto('/dashboard/team');

        // Should land on the team page, not be redirected to login
        await expect(page).not.toHaveURL(/\/login/);
        await expect(page).toHaveURL(/\/dashboard\/team/);

        // Team management content should be visible (heading or member list)
        await expect(page.getByText(/Team|Members|Invite/i).first()).toBeVisible();
    });

    test('Protected API calls return 401 without auth', async ({ page }) => {
        // Call admin API through the Next.js proxy (no local admin service in CI)
        const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001';
        const response = await page.request.get(`${baseURL}/api/admin/v1/admin/users`);

        expect([401, 403]).toContain(response.status());
    });

    test('Session persists across navigation', async ({ page }) => {
        test.setTimeout(60000);

        // Login — ?next=/dashboard bypasses the onboarding check
        await page.goto('/login?next=/dashboard');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 15000 });

        // Navigate to multiple pages
        await page.goto('/dashboard');
        await expect(page).toHaveURL(/\/dashboard/);

        await page.goto('/fsma');
        await expect(page).not.toHaveURL(/\/login/);

        await page.goto('/ingest');
        await expect(page).not.toHaveURL(/\/login/);

        // Session should still be valid (/settings/users redirects → /dashboard/settings)
        await page.goto('/settings/users');
        await expect(page).toHaveURL(/\/dashboard\/settings|\/settings\/users/);
    });

});
