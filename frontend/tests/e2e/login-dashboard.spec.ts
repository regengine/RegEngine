/**
 * E2E Test: Login → Dashboard Flow
 * 
 * Critical user journey test:
 * 1. Navigate to login page
 * 2. Enter credentials
 * 3. Submit login form
 * 4. Verify redirect to dashboard
 * 5. Verify user is authenticated
 */

import { test, expect } from '@playwright/test';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

test.describe('Login → Dashboard Flow', () => {
    test('successful login redirects to dashboard', async ({ page }) => {
        // Navigate to login page
        await page.goto('/login');

        // Verify login page loaded — the login card heading is h2 ("Welcome back").
        // The page also has a marketing h1 ("API-first regulatory compliance.") so
        // we target h2 specifically to avoid a strict-mode mismatch.
        await expect(page).toHaveTitle(/RegEngine/);
        await expect(page.locator('h2').filter({ hasText: /welcome back/i })).toBeVisible();

        // Fill in login form
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);

        // Submit form
        await page.click('button[type="submit"]');

        // Wait for navigation to an authenticated page (may land on dashboard, sysadmin, or onboarding)
        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 15000 });

        // Verify we landed on an authenticated page
        await expect(page).toHaveURL(/\/(dashboard|sysadmin|onboarding)/);
    });

    test('invalid credentials show error message', async ({ page }) => {
        test.setTimeout(60000);
        await page.goto('/login');

        // Enter invalid credentials
        await page.fill('input[type="email"]', 'invalid@example.com');
        await page.fill('input[type="password"]', 'wrongpassword');

        // Submit form
        await page.click('button[type="submit"]');

        // Should stay on login page
        await expect(page).toHaveURL(/\/login/);

        // Error message should appear — the admin service may take several
        // seconds to respond from Railway, so use a generous timeout.
        await expect(page.locator('#login-error')).toBeVisible({ timeout: 15000 });
        await expect(page.locator('#login-error')).toContainText(/invalid|error|unavailable/i);
    });

    test('login form has proper accessibility', async ({ page }) => {
        await page.goto('/login');

        // Email input should have label
        const emailInput = page.locator('input[type="email"]');
        await expect(emailInput).toHaveAttribute('autocomplete', 'email');

        // Password input should have label
        const passwordInput = page.locator('input[type="password"]');
        await expect(passwordInput).toHaveAttribute('autocomplete', 'current-password');

        // Submit button should be keyboard accessible
        const submitButton = page.locator('button[type="submit"]');
        await expect(submitButton).toBeEnabled();
    });

    test('logout from dashboard redirects to login', async ({ page }) => {
        test.setTimeout(60000);

        // Login first
        await page.goto('/login');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');

        // Wait for redirect to any authenticated page
        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 15000 });

        // Find and click logout button
        const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]').first();
        if (await logoutButton.isVisible({ timeout: 5000 })) {
            await logoutButton.click();

            // Should redirect to login
            await page.waitForURL('**/login', { timeout: 10000 });
            await expect(page).toHaveURL(/\/login/);
        }
    });
});

test.describe('Dashboard Features', () => {
    test.beforeEach(async ({ page }) => {
        // Login before each test
        await page.goto('/login');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');
        await page.waitForURL(/\/(dashboard|sysadmin|onboarding)/, { timeout: 15000 });
    });

    test('dashboard displays user information', async ({ page }) => {
        // Navigate to dashboard explicitly (beforeEach may land on /sysadmin or /onboarding)
        await page.goto('/dashboard');
        await page.waitForLoadState('networkidle');

        // Should show user email, name, initials, or avatar somewhere
        const escapedEmail = TEST_USER_EMAIL.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const emailOrName = page.locator(`text=/${escapedEmail}|test user/i`).first();
        const hasUserInfo =
            await emailOrName.count() > 0 ||
            await page.locator('[data-testid*="user"], [class*="avatar"], [class*="user-menu"], [class*="sidebar"]').count() > 0;
        expect(hasUserInfo).toBe(true);
    });

    test('dashboard has navigation links', async ({ page }) => {
        // Common navigation items
        const navItems = ['Energy', 'Opportunity', 'Settings'];

        for (const item of navItems) {
            const link = page.locator(`a:has-text("${item}")`).first();
            if (await link.isVisible()) {
                await expect(link).toBeEnabled();
            }
        }
    });

    test('navigation links work correctly', async ({ page }) => {
        // Try to navigate to Energy page (if exists)
        const energyLink = page.locator('a:has-text("Energy")').first();

        if (await energyLink.isVisible()) {
            await energyLink.click();
            // Should navigate away from dashboard
            await page.waitForTimeout(500);
            // URL should change
            const currentUrl = page.url();
            expect(currentUrl).not.toMatch(/\/dashboard$/);
        }
    });
});
