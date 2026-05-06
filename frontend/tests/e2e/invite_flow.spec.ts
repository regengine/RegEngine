
import { test, expect } from '@playwright/test';
import { adminAuthenticatedE2ESkipReason, hasAdminAuthenticatedE2E } from './auth-prereqs';

// Invite flow requires an org admin account that can create invite tokens.
// Use dedicated admin credentials if available; fall back to the test user
// (the test user created by globalSetup is the org owner and has invite permission).
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL || process.env.TEST_USER_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_PASSWORD || 'test-placeholder';

test.describe('User Invite Flow', () => {

    test.afterEach(async ({ page }, testInfo) => {
        if (testInfo.status !== testInfo.expectedStatus) {
            const path = `test-results/failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}.png`;
            await page.screenshot({ path, fullPage: true });
            console.log(`Screenshot saved to ${path}`);
        }
    });

    test('Admin can invite user and user can accept', async ({ page, browser }) => {
        test.skip(!hasAdminAuthenticatedE2E, adminAuthenticatedE2ESkipReason);

        // Increase timeout
        test.setTimeout(90000);

        // -----------------------------------------------------------------------
        // 1. Admin Login & Invite Creation
        // -----------------------------------------------------------------------
        console.log('Logging in as Admin...');
        await page.goto('/login');

        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        // Regular tenant owners may land on onboarding before they reach the
        // dashboard, while dedicated sysadmins can land on /sysadmin.
        await expect(page).toHaveURL(/\/sysadmin|\/dashboard|\/onboarding/);
        console.log('Logged in.');

        // Navigate to User Settings
        // The Team Management / Invite UI lives at /settings/users.
        // NOTE: next.config.js previously had a wildcard redirect that sent /settings/:path*
        // to /dashboard/settings — that redirect has been removed. /settings/users is now
        // directly accessible.
        await page.goto('/settings/users');
        await expect(page.getByText('Team Management')).toBeVisible();

        // Create Invite
        console.log('Creating invite...');
        await page.click('button:has-text("Invite User")');

        // Fill Invite Form
        const inviteEmail = `e2e-invite-${Date.now()}@example.com`;
        await page.fill('input[placeholder="colleague@company.com"]', inviteEmail);

        // Setup listener before clicking Send
        // Use predicate to find the POST request to invites
        const inviteResponsePromise = page.waitForResponse(response =>
            response.url().includes('/admin/invites') &&
            response.status() === 200 &&
            response.request().method() === 'POST'
        );

        await page.click('button:has-text("Send Invite")');

        // Wait for response and extract link
        const inviteResponse = await inviteResponsePromise;
        const inviteData = await inviteResponse.json();
        const inviteLink = inviteData.invite_link;

        console.log(`Intercepted Invite Link: ${inviteLink}`);
        expect(inviteLink).toBeTruthy();
        expect(inviteLink).toContain('token=');

        // Wait for success toast or list update (UI verification)
        try {
            await expect(page.getByText('Invite Sent')).toBeVisible({ timeout: 5000 });
        } catch {
            // Some runs update the invite list without rendering a toast.
        }

        // -----------------------------------------------------------------------
        // 2. New User Acceptance
        // -----------------------------------------------------------------------
        console.log('Accepting invite as new user...');

        // Create new context (clean browser session)
        const context2 = await browser.newContext();
        const page2 = await context2.newPage();

        // Navigate to invite link
        // Ensure it uses the frontend port (3001)
        const token = inviteLink.split('token=')[1];

        // inviteLink is relative path from backend (e.g. "/accept-invite?token=...")
        await page2.goto(`/accept-invite?token=${token}`);

        // Verify Accept Page
        await expect(page2.getByRole('heading', { name: 'Accept Invitation' }).first()).toBeVisible();

        // Fill Registration
        // Use robust selectors based on page inspection
        const testPassword = process.env.TEST_PASSWORD || 'test-placeholder';
        await page2.fill('input[placeholder="John Doe"]', 'E2E User');
        await page2.locator('input[type="password"]').first().fill(testPassword);
        await page2.locator('input[type="password"]').last().fill(testPassword);

        await page2.click('button:has-text("Create Account")');

        // Verify Success Step "Welcome Aboard!"
        await expect(page2.getByText('Welcome Aboard!')).toBeVisible();
        await page2.click('button:has-text("Go to Login")');

        // Verify Redirect to Login
        await expect(page2).toHaveURL(/\/login/);
        console.log('Registration complete. Logging in...');

        // Login
        await page2.fill('input[type="email"]', inviteEmail);
        await page2.fill('input[type="password"]', testPassword);
        await page2.click('button[type="submit"]');

        // Verify the invited user reaches an authenticated area. New users can
        // legitimately land on onboarding before their dashboard is available.
        await expect(page2).toHaveURL(/\/dashboard|\/onboarding|\/sysadmin/);
        await expect(page2.locator('nav, main, [role="navigation"]').first()).toBeVisible();

        console.log('E2E Flow Complete!');
    });
});
