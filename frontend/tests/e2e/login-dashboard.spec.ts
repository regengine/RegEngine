/**
 * E2E Test: Login → Dashboard Flow (passwordless)
 *
 * The app has no password login: /login collects an email, POST
 * /api/admin/auth/challenges issues a sign-in code, and /auth/verify exchanges
 * the code for the opaque __Host-regengine_session cookie. Locally the backend
 * runs with REGENGINE_E2E_MODE=true and writes OTPs to the outbox fixture, so
 * these tests complete real logins end to end.
 *
 * Critical user journeys:
 * 1. Email OTP login lands on the dashboard with a hydrated session
 * 2. Wrong codes surface an error and never authenticate
 * 3. Logout tears the session down and protected pages stay gated
 */

import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import { hasPasswordlessE2E, passwordlessE2ESkipReason } from './auth-prereqs';
import { AUTH_SESSION_COOKIE, loginWithEmailOtp, seedPasswordlessUser } from './auth-helpers';
import { loginViaApi, logoutViaApi } from './support/api-auth';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'playwright-e2e@example.com';

function uniqueEmail(prefix: string): string {
    return `${prefix}+${Date.now()}@example.com`;
}

async function authSessionCookie(context: BrowserContext) {
    const cookies = await context.cookies();
    return cookies.find(cookie => cookie.name === AUTH_SESSION_COOKIE);
}

async function startChallengeFromLoginPage(page: Page, email: string): Promise<void> {
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: /continue to regengine/i })).toBeVisible();
    await page.getByLabel(/email address/i).fill(email);
    await page.getByRole('button', { name: /^continue/i }).click();
}

test.describe('Login → Dashboard Flow', () => {
    test('successful email OTP login redirects to dashboard', async ({ page, context }) => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);

        const email = uniqueEmail('playwright-login-dashboard');
        seedPasswordlessUser(email);

        await page.goto('/login');
        await expect(page).toHaveTitle(/RegEngine/);

        // loginWithEmailOtp asserts the full journey: /login → /auth/verify →
        // /dashboard plus the opaque session cookie attributes.
        await loginWithEmailOtp(page, context, email);
    });

    test('wrong verification code shows an error and does not authenticate', async ({ page, context }) => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);

        // Anti-enumeration: unseeded addresses still get a challenge_id, so no
        // seeding is needed to exercise the failure path.
        await startChallengeFromLoginPage(page, uniqueEmail('playwright-wrong-code'));
        await expect(page).toHaveURL(/\/auth\/verify$/);

        await page.getByLabel(/verification code/i).fill('000000');
        await page.getByRole('button', { name: /verify and continue/i }).click();

        await expect(page.locator('#otp-error')).toBeVisible();
        await expect(page.locator('#otp-error')).toContainText(/incorrect or expired/i);
        await expect(page).toHaveURL(/\/auth\/verify$/);
        expect(await authSessionCookie(context)).toBeUndefined();
    });

    test('login form has proper accessibility and autofill-friendly controls', async ({ page }) => {
        await page.goto('/login');

        await expect(page.getByRole('heading', { name: /continue to regengine/i })).toBeVisible();

        const emailInput = page.locator('#email');
        await expect(emailInput).toHaveAttribute('name', 'email');
        await expect(emailInput).toHaveAttribute('type', 'email');
        await expect(emailInput).toHaveAttribute('autocomplete', 'email');

        const continueButton = page.getByRole('button', { name: /^continue/i });
        await expect(continueButton).toBeEnabled();
        await expect(page.getByRole('button', { name: /sign in with passkey/i })).toBeVisible();

        await emailInput.focus();
        await expect(emailInput).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(continueButton).toBeFocused();
    });

    test('rapid double submit starts only one sign-in challenge', async ({ page }) => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);

        let challengeRequests = 0;
        page.on('request', (request) => {
            if (request.method() === 'POST' && request.url().includes('/api/admin/auth/challenges')) {
                challengeRequests += 1;
            }
        });

        await page.goto('/login');
        await page.getByLabel(/email address/i).fill(uniqueEmail('playwright-double-submit'));

        const continueButton = page.getByRole('button', { name: /^continue/i });
        const box = await continueButton.boundingBox();
        expect(box).toBeTruthy();
        await page.mouse.dblclick(box!.x + box!.width / 2, box!.y + box!.height / 2);

        await expect(page).toHaveURL(/\/auth\/verify$/);
        expect(challengeRequests).toBe(1);
    });

    test('challenge network failure keeps the form filled and shows a clear error', async ({ page }) => {
        await page.route('**/api/admin/auth/challenges', (route) => route.abort('failed'));

        await page.goto('/login');
        const email = 'network-fail@example.com';
        await page.getByLabel(/email address/i).fill(email);
        await page.getByRole('button', { name: /^continue/i }).click();

        await expect(page.locator('#login-error')).toBeVisible();
        // Chromium surfaces aborted fetches as "Failed to fetch"; the client
        // falls back to its own copy when the error carries no message.
        await expect(page.locator('#login-error')).toContainText(/failed to fetch|unable to start sign-in/i);
        await expect(page).toHaveURL(/\/login/);
        await expect(page.getByLabel(/email address/i)).toHaveValue(email);
    });

    test('logout from dashboard redirects to login', async ({ page, context }) => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
        test.setTimeout(60000);

        const email = uniqueEmail('playwright-logout');
        seedPasswordlessUser(email);
        await loginWithEmailOtp(page, context, email);

        const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]').first();
        if (await logoutButton.isVisible({ timeout: 5000 })) {
            await logoutButton.click();
            await page.waitForURL(/\/login/, { timeout: 15000 });
            await expect(page).toHaveURL(/\/login/);
        }
    });

    test('back after logout does not restore a protected dashboard from cache', async ({ page, context }) => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
        test.setTimeout(60000);

        const email = uniqueEmail('playwright-back-cache');
        seedPasswordlessUser(email);
        await loginWithEmailOtp(page, context, email);

        await logoutViaApi(context);
        await context.clearCookies();
        await page.goto('/login');
        await expect(page).toHaveURL(/\/login/);

        await page.goBack({ waitUntil: 'domcontentloaded' });
        await page.waitForURL(/\/login/, { timeout: 15000 });
        await expect(page.getByRole('heading', { name: /continue to regengine/i })).toBeVisible();
    });
});

test.describe('Protected deep links', () => {
    test('unauthenticated deep link redirects to login preserving next', async ({ page }) => {
        await page.goto('/reports/abc123');
        await expect(page).toHaveURL((url) =>
            url.pathname === '/login' && url.searchParams.get('next') === '/reports/abc123',
        );
    });

    test('deep link is reachable after API login', async ({ page, context }) => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);

        await loginViaApi(context, TEST_USER_EMAIL);
        await page.goto('/reports/abc123');
        await expect(page).toHaveURL((url) => url.pathname === '/reports/abc123', { timeout: 15000 });
    });
});

test.describe('Login session cookie mode', () => {
    test('email OTP login sets a persistent opaque session cookie', async ({ context }) => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);

        await context.clearCookies();
        await loginViaApi(context, TEST_USER_EMAIL);

        // The backend always issues a 7-day opaque session cookie; there is no
        // remember-me variant (and no re_access_token JWT cookie) anymore.
        const authCookie = await authSessionCookie(context);
        expect(authCookie).toBeDefined();
        expect(authCookie?.httpOnly).toBe(true);
        expect(authCookie?.expires).toBeGreaterThan(Math.floor(Date.now() / 1000));

        await logoutViaApi(context);
        expect(await authSessionCookie(context)).toBeUndefined();
    });
});

test.describe('Dashboard Features', () => {
    test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);

    test.beforeEach(async ({ page, context }) => {
        await loginViaApi(context, TEST_USER_EMAIL);
        await page.goto('/dashboard');
    });

    test('dashboard displays user information', async ({ page }) => {
        test.setTimeout(60000);

        await expect(page).not.toHaveURL(/\/login/);

        // Verify some authenticated UI rendered — nav, main content, etc.
        // The specific page depends on the test user's onboarding state and role.
        await expect(page.locator('nav, main, [role="navigation"]').first()).toBeVisible({ timeout: 15000 });
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
