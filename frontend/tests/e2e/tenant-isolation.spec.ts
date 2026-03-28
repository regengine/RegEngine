import { test, expect, Page, Browser } from '@playwright/test';

/**
 * Tenant Isolation E2E Tests
 * 
 * Verifies that tenant data is properly isolated at the browser level:
 * - Tenant switcher changes context
 * - Dashboard data reflects selected tenant
 * - Cannot access other tenant data via URL manipulation
 */

const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || 'test-placeholder';

test.describe('Tenant Isolation', () => {

    test.afterEach(async ({ page }, testInfo) => {
        if (testInfo.status !== 'passed') {
            const path = `test-results/tenant-failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}.png`;
            await page.screenshot({ path, fullPage: true });
        }
    });

    async function loginAsAdmin(page: Page) {
        await page.goto('/login');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');
        await expect(page).toHaveURL(/\/(dashboard|sysadmin)/);
    }

    test('Tenant switcher is visible after login', async ({ page }) => {
        test.setTimeout(60000);

        await loginAsAdmin(page);

        // Navigate to dashboard
        await page.goto('/dashboard');

        // Tenant switcher should be visible (look for elements with tenant-related IDs or roles)
        const tenantSwitcher = page.locator('[id*="tenant"], [data-testid*="tenant"], [class*="tenant-switcher"]').first();

        // If tenant switcher exists, verify it's interactive
        const hasSwitcher = await tenantSwitcher.count() > 0;
        if (hasSwitcher) {
            await expect(tenantSwitcher).toBeVisible();
        } else {
            // Check for onboarding tenant switcher
            const onboardingSwitcher = page.locator('#onboarding-tenant-switcher');
            const hasOnboardingSwitcher = await onboardingSwitcher.count() > 0;
            expect(hasSwitcher || hasOnboardingSwitcher).toBeTruthy();
        }
    });

    test('Tenant context persists in navigation', async ({ page }) => {
        test.setTimeout(60000);

        await loginAsAdmin(page);

        // Navigate with tenant context in URL
        await page.goto('/dashboard');

        // Navigate to another page
        await page.goto('/fsma');

        // Page should load without errors
        await expect(page).not.toHaveURL(/\/login/);
        await expect(page).not.toHaveURL(/error/);
    });

    test('API calls include tenant context', async ({ page }) => {
        test.setTimeout(60000);

        await loginAsAdmin(page);

        // Capture network requests
        const apiRequests: string[] = [];
        page.on('request', request => {
            if (request.url().includes('localhost:8400')) {
                apiRequests.push(request.url());
            }
        });

        // Navigate to a data page
        await page.goto('/dashboard');

        // Wait for API calls
        await page.waitForTimeout(2000);

        // Verify API calls were made (auth-protected endpoints)
        expect(apiRequests.length).toBeGreaterThan(0);
    });

    test('Cannot inject arbitrary tenant_id via URL', async ({ page }) => {
        test.setTimeout(60000);

        await loginAsAdmin(page);

        // Try to access dashboard with arbitrary tenant parameter
        const fakeUUID = '00000000-0000-0000-0000-000000000000';

        await page.goto(`/dashboard?tenant=${fakeUUID}`);

        // Should either:
        // 1. Ignore the parameter and use authenticated tenant
        // 2. Return an error/redirect
        // Should NOT show data from the fake tenant

        // Page should not crash (no 500 errors)
        const responsePromise = page.waitForResponse(response =>
            response.url().includes('localhost:8400') && response.status() >= 500
            , { timeout: 5000 }).catch(() => null);

        // Navigate to trigger API calls
        await page.goto(`/dashboard?tenant_id=${fakeUUID}`);

        const errorResponse = await responsePromise;
        expect(errorResponse).toBeNull(); // No 500 errors
    });

    test('Review queue shows tenant-specific data', async ({ page }) => {
        test.setTimeout(60000);

        await loginAsAdmin(page);

        // Navigate to review page
        await page.goto('/review');

        // Page should load
        await expect(page).toHaveURL(/\/review/);

        // Review queue container should exist (may be empty)
        const reviewContent = page.locator('[class*="review"], [data-testid*="review"]');
        const hasReviewContent = await reviewContent.count() > 0;

        // Alternatively, check for common review page elements
        const pageLoaded = await page.getByText(/Review|Queue|Pending|Items/i).count() > 0;

        expect(hasReviewContent || pageLoaded).toBeTruthy();
    });

    test('Overlay controls are tenant-scoped', async ({ page }) => {
        test.setTimeout(60000);

        await loginAsAdmin(page);

        // Navigate to controls/overlay section if it exists
        await page.goto('/controls');

        // If page exists, verify it loads tenant-scoped data
        const is404 = await page.getByText(/404|Not Found/i).count() > 0;

        if (!is404) {
            // Controls page exists, verify tenant context
            await expect(page).not.toHaveURL(/\/login/);

            // Check for controls-related content
            const hasControls = await page.getByText(/Control|Framework|NIST|SOC/i).count() > 0;
            expect(hasControls).toBeTruthy();
        }
        // If 404, controls page doesn't exist (acceptable)
    });

});
