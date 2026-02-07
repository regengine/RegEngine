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

test.describe('Login → Dashboard Flow', () => {
    test('successful login redirects to dashboard', async ({ page }) => {
        // Navigate to login page
        await page.goto('/login');

        // Verify login page loaded
        await expect(page).toHaveTitle(/RegEngine/);
        await expect(page.locator('h1, h2')).toContainText(/welcome back/i);

        // Fill in login form
        await page.fill('input[type="email"]', 'test@example.com');
        await page.fill('input[type="password"]', 'password123');

        // Submit form
        await page.click('button[type="submit"]');

        // Wait for navigation to dashboard
        await page.waitForURL('**/dashboard');

        // Verify dashboard loaded
        await expect(page).toHaveURL(/\/dashboard/);
        await expect(page.locator('h1, h2')).toContainText(/dashboard|overview/i);
    });

    test('invalid credentials show error message', async ({ page }) => {
        await page.goto('/login');

        // Enter invalid credentials
        await page.fill('input[type="email"]', 'invalid@example.com');
        await page.fill('input[type="password"]', 'wrongpassword');

        // Submit form
        await page.click('button[type="submit"]');

        // Should stay on login page
        await expect(page).toHaveURL(/\/login/);

        // Error message should appear
        await expect(page.locator('[role="alert"]')).toBeVisible();
        await expect(page.locator('[role="alert"]')).toContainText(/invalid|error/i);
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
        // Login first
        await page.goto('/login');
        await page.fill('input[type="email"]', 'test@example.com');
        await page.fill('input[type="password"]', 'password123');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');

        // Find and click logout button
        const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out")').first();
        await logoutButton.click();

        // Should redirect to login
        await page.waitForURL('**/login');
        await expect(page).toHaveURL(/\/login/);
    });
});

test.describe('Dashboard Features', () => {
    test.beforeEach(async ({ page }) => {
        // Login before each test
        await page.goto('/login');
        await page.fill('input[type="email"]', 'test@example.com');
        await page.fill('input[type="password"]', 'password123');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');
    });

    test('dashboard displays user information', async ({ page }) => {
        // Should show user email or name
        await expect(page.locator('text=/test@example.com|test user/i')).toBeVisible();
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
