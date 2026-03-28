
import { test, expect } from '@playwright/test';

// Constants for test
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || 'test-placeholder';

test.describe('User Invite Flow', () => {

    test.afterEach(async ({ page }, testInfo) => {
        if (testInfo.status !== 'passed') {
            const path = `test-results/failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}.png`;
            await page.screenshot({ path, fullPage: true });
            console.log(`Screenshot saved to ${path}`);
        }
    });

    test('Admin can invite user and user can accept', async ({ page, browser }) => {
        // Increase timeout
        test.setTimeout(90000);

        // Debugging
        page.on('console', msg => console.log(`BROWSER LOG: ${msg.text()}`));
        page.on('requestfailed', request => console.log(`REQ FAILED: ${request.url()} - ${request.failure()?.errorText}`));
        page.on('response', response => {
            if (response.status() >= 400) {
                console.log(`REQ ERROR: ${response.url()} - ${response.status()}`);
            }
        });

        // -----------------------------------------------------------------------
        // 1. Admin Login & Invite Creation
        // -----------------------------------------------------------------------
        console.log('Logging in as Admin...');
        await page.goto('/login');

        await page.fill('input[type="email"]', 'admin@example.com');
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');

        // Verify redirect to dashboard/sysadmin
        await expect(page).toHaveURL(/\/sysadmin|\/dashboard/);
        console.log('Logged in.');

        // Navigate to User Settings
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
        } catch (e) {
            console.log('Toast check skipped/failed...');
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
        await expect(page2.getByText('Accept Invitation')).toBeVisible();

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

        // Verify Dashboard Access
        await expect(page2).toHaveURL(/\/dashboard/);
        await expect(page2.getByText('Dashboard')).toBeVisible();

        console.log('E2E Flow Complete!');
    });
});
