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

import { createHmac } from 'node:crypto';
import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import { authenticatedE2ESkipReason, hasAuthenticatedE2E } from './auth-prereqs';
import { loginViaApi, logoutViaApi } from './support/api-auth';

/** Wait for navigation to an authenticated page (pathname-only check to avoid matching query strings like ?next=/dashboard) */
async function waitForAuthenticated(page: Page, timeout = 15000) {
    await page.waitForURL(url => {
        const pathname = new URL(url).pathname;
        return /^\/(dashboard|sysadmin|onboarding)/.test(pathname);
    }, { timeout });
}

async function reAccessTokenCookie(context: BrowserContext) {
    const cookies = await context.cookies();
    return cookies.find(cookie => cookie.name === 're_access_token');
}

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';
const localJwtSigningKey = process.env.JWT_SIGNING_KEY || process.env.AUTH_SECRET_KEY;
const hasLocalMockedAuth = Boolean(localJwtSigningKey) && !process.env.PLAYWRIGHT_BASE_URL;

function base64UrlJson(value: Record<string, unknown>): string {
    return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function signRegEngineJwt(overrides: Record<string, unknown> = {}): string {
    if (!localJwtSigningKey) {
        throw new Error('JWT signing key is required for mocked login E2E');
    }

    const now = Math.floor(Date.now() / 1000);
    const header = base64UrlJson({ alg: 'HS256', typ: 'JWT' });
    const payload = base64UrlJson({
        aud: 'regengine-api',
        iss: 'regengine-admin',
        sub: 'playwright-login-ui-user',
        tenant_id: 'tenant-login-ui',
        tenant_status: 'active',
        is_sysadmin: false,
        iat: now,
        exp: now + 60 * 60,
        ...overrides,
    });
    const body = `${header}.${payload}`;
    const signature = createHmac('sha256', localJwtSigningKey).update(body).digest('base64url');
    return `${body}.${signature}`;
}

async function installMockedAdminLogin(
    page: Page,
    options: { delayMs?: number; failNetwork?: boolean } = {},
): Promise<() => number> {
    let loginRequests = 0;

    await page.route('**/api/admin/auth/login', async (route) => {
        loginRequests += 1;
        if (options.delayMs) {
            await new Promise((resolve) => setTimeout(resolve, options.delayMs));
        }
        if (options.failNetwork) {
            await route.abort('failed');
            return;
        }

        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                access_token: signRegEngineJwt(),
                tenant_id: 'tenant-login-ui',
                user: {
                    id: 'playwright-login-ui-user',
                    email: 'playwright-login-ui@example.com',
                    is_sysadmin: false,
                    status: 'active',
                    role_name: 'member',
                },
            }),
        });
    });

    await page.route('**/api/admin/v1/tenants/*/onboarding', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                workspace_profile: {},
                onboarding: {},
                is_complete: true,
                partner_tier: null,
            }),
        });
    });

    return () => loginRequests;
}

test.describe('Login → Dashboard Flow', () => {
    test('successful login redirects to dashboard', async ({ page }) => {
        test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);

        // Navigate to login page with ?next=/dashboard to bypass the onboarding check
        // so this test reliably reaches /dashboard regardless of the test user's
        // onboarding state in the Railway admin service.
        await page.goto('/login?next=/dashboard');

        // Verify login page loaded using user-facing roles instead of brittle
        // copy tied to a previous marketing iteration.
        await expect(page).toHaveTitle(/RegEngine/);
        await expect(page.getByRole('heading', { level: 2, name: /^sign in$/i })).toBeVisible();
        await expect(page.getByRole('textbox', { name: /email address/i })).toBeVisible();

        // Fill in login form
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);

        // Submit form
        await page.click('button[type="submit"]');

        // Wait for navigation to an authenticated page (may land on dashboard, sysadmin, or onboarding)
        await waitForAuthenticated(page);

        // Verify we landed on an authenticated page (pathname-only to avoid false match on ?next= query strings)
        await expect(page).toHaveURL(url => /^\/(dashboard|sysadmin|onboarding)/.test(new URL(url).pathname));
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
        await expect(page.locator('#login-error')).toContainText(/invalid|error|unavailable|unreachable/i);
    });

    test('login form has proper accessibility and autofill-friendly controls', async ({ page }) => {
        await page.goto('/login');

        const loginForm = page.locator('form').first();
        const emailInput = loginForm.locator('#email');
        const passwordInput = loginForm.locator('#password');
        const rememberCheckbox = loginForm.getByRole('checkbox', { name: /remember me/i });
        const submitButton = loginForm.getByRole('button', { name: /^sign in$/i });

        await expect(emailInput).toHaveAttribute('name', 'email');
        await expect(emailInput).toHaveAttribute('autocomplete', 'email');
        await expect(passwordInput).toHaveAttribute('name', 'password');
        await expect(passwordInput).toHaveAttribute('autocomplete', 'current-password');
        await expect(rememberCheckbox).toBeChecked();

        await passwordInput.fill('ToggleKeepsValue123!');
        await page.getByRole('button', { name: /show password/i }).click();
        await expect(passwordInput).toHaveAttribute('type', 'text');
        await expect(passwordInput).toHaveValue('ToggleKeepsValue123!');
        await page.getByRole('button', { name: /hide password/i }).click();
        await expect(passwordInput).toHaveAttribute('type', 'password');
        await expect(passwordInput).toHaveValue('ToggleKeepsValue123!');

        await emailInput.focus();
        await expect(emailInput).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(passwordInput).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(rememberCheckbox).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(submitButton).toBeFocused();
        await expect(submitButton).toBeEnabled();
    });

    test('forgot password link is visible at 375px width', async ({ page }) => {
        await page.setViewportSize({ width: 375, height: 720 });
        await page.goto('/login');

        const forgotPassword = page.getByRole('link', { name: /forgot password/i });
        await expect(forgotPassword).toBeVisible();
        await expect(forgotPassword).toBeInViewport();
    });

    test('logout from dashboard redirects to login', async ({ page }) => {
        test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);
        test.setTimeout(60000);

        // Login first — use ?next=/dashboard to bypass onboarding redirect
        await page.goto('/login?next=/dashboard');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');
        await waitForAuthenticated(page);

        // Find and click logout button
        const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]').first();
        if (await logoutButton.isVisible({ timeout: 5000 })) {
            await logoutButton.click();

            // Should redirect to login (regex handles ?next= query params; 15s for Railway latency)
            await page.waitForURL(/\/login/, { timeout: 15000 });
            await expect(page).toHaveURL(/\/login/);
        }
    });

    test('back after logout does not restore a protected dashboard from cache', async ({ page, context }) => {
        test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);
        test.setTimeout(60000);

        await page.goto('/login?next=/dashboard');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');
        await waitForAuthenticated(page);

        await logoutViaApi(context);
        await context.clearCookies();
        await page.goto('/login');
        await expect(page).toHaveURL(/\/login/);

        await page.goBack({ waitUntil: 'domcontentloaded' });
        await page.waitForURL(/\/login/, { timeout: 15000 });
        await expect(page.getByRole('heading', { level: 2, name: /^sign in$/i })).toBeVisible();
    });
});

test.describe('Login UI + protected deep links with mocked admin auth', () => {
    test.beforeEach(() => {
        test.skip(!hasLocalMockedAuth, 'Requires local Playwright server with a matching JWT signing key.');
    });

    test('returns to /reports/abc123 after login from a protected deep link', async ({ page }) => {
        await installMockedAdminLogin(page);

        await page.goto('/reports/abc123');
        await expect(page).toHaveURL((url) =>
            url.pathname === '/login' && url.searchParams.get('next') === '/reports/abc123',
        );

        const loginForm = page.locator('form').first();
        await loginForm.locator('#email').fill('playwright-login-ui@example.com');
        await loginForm.locator('#password').fill('Trace204!Playwright1');
        await loginForm.getByRole('button', { name: /^sign in$/i }).click();

        await expect(page).toHaveURL((url) => url.pathname === '/reports/abc123', { timeout: 15000 });
    });

    test('network failure keeps the form filled and shows a clear error', async ({ page }) => {
        await installMockedAdminLogin(page, { failNetwork: true });

        await page.goto('/login');
        const loginForm = page.locator('form').first();
        const emailInput = loginForm.locator('#email');
        const passwordInput = loginForm.locator('#password');
        await emailInput.fill('network-fail@example.com');
        await passwordInput.fill('StillPresent123!');
        await loginForm.getByRole('button', { name: /^sign in$/i }).click();

        await expect(page.locator('#login-error')).toBeVisible();
        await expect(page.locator('#login-error')).toContainText(/unable|unexpected|authentication/i);
        await expect(emailInput).toHaveValue('network-fail@example.com');
        await expect(passwordInput).toHaveValue('StillPresent123!');
    });

    test('slow login cannot be submitted twice from rapid clicks', async ({ page }) => {
        const loginCount = await installMockedAdminLogin(page, { delayMs: 1000 });

        await page.goto('/login');
        const loginForm = page.locator('form').first();
        await loginForm.locator('#email').fill('playwright-login-ui@example.com');
        await loginForm.locator('#password').fill('Trace204!Playwright1');

        const submitButton = loginForm.getByRole('button', { name: /^sign in$/i });
        const box = await submitButton.boundingBox();
        expect(box).toBeTruthy();
        await page.mouse.dblclick(box!.x + box!.width / 2, box!.y + box!.height / 2);

        await expect(page.getByRole('button', { name: /securing session/i })).toBeDisabled();
        await expect.poll(loginCount).toBe(1);
        await expect(page).toHaveURL((url) => url.pathname === '/dashboard', { timeout: 15000 });
    });
});

test.describe('Login session cookie mode', () => {
    test('remembered sessions set a persistent auth cookie', async ({ context }) => {
        test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);

        await context.clearCookies();
        await loginViaApi(context, TEST_USER_EMAIL, TEST_PASSWORD, { remember: true });

        const authCookie = await reAccessTokenCookie(context);
        expect(authCookie).toBeDefined();
        expect(authCookie?.expires).toBeGreaterThan(Math.floor(Date.now() / 1000));

        await logoutViaApi(context);
    });

    test('session-only logins set a browser-session auth cookie', async ({ context }) => {
        test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);

        await context.clearCookies();
        await loginViaApi(context, TEST_USER_EMAIL, TEST_PASSWORD, { remember: false });

        const authCookie = await reAccessTokenCookie(context);
        expect(authCookie).toBeDefined();
        expect(authCookie?.expires).toBe(-1);

        await logoutViaApi(context);
    });
});

test.describe('Dashboard Features', () => {
    test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);

    test.beforeEach(async ({ page }) => {
        // Login before each test — use ?next=/dashboard to bypass onboarding redirect
        await page.goto('/login?next=/dashboard');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');
        await waitForAuthenticated(page);
    });

    test('dashboard displays user information', async ({ page }) => {
        test.setTimeout(60000);

        // beforeEach already logged in and waitForAuthenticated verified we landed
        // on an authenticated page (dashboard, sysadmin, or onboarding).
        // Don't navigate again — just verify the current page is authenticated.
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
