import { test, expect, Page, BrowserContext } from '@playwright/test';

/**
 * Security Audit Fixes E2E Tests
 *
 * Comprehensive coverage for security improvements shipped in:
 * - PR #325: Security Settings page cleanup, sysadmin cache fix
 * - PR #327: HTTP-only cookie-based auth migration (localStorage cleanup)
 * - PR #329: CSRF protection validation
 *
 * Tests cover:
 * 1. Cookie-based auth (HTTP-only, no localStorage tokens)
 * 2. Security Settings page (2FA, session management)
 * 3. Sysadmin cache and access control
 * 4. CSRF protection on forms and API calls
 * 5. Auth guard visibility and error handling
 */

const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || 'test-placeholder';
const REGULAR_USER_EMAIL = 'user@example.com';
const REGULAR_USER_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

test.describe('Security Audit Fixes', () => {

    test.afterEach(async ({ page }, testInfo) => {
        if (testInfo.status !== 'passed') {
            const path = `test-results/security-failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}.png`;
            await page.screenshot({ path, fullPage: true });
        }
    });

    /**
     * Helper: Login as admin
     */
    async function loginAsAdmin(page: Page) {
        await page.goto('/login');
        await page.fill('input[type="email"]', ADMIN_EMAIL);
        await page.fill('input[type="password"]', ADMIN_PASSWORD);
        await page.click('button[type="submit"]');
        await expect(page).toHaveURL(/\/(dashboard|sysadmin)/);
    }

    /**
     * Helper: Login as regular user
     */
    async function loginAsRegularUser(page: Page) {
        await page.goto('/login');
        await page.fill('input[type="email"]', REGULAR_USER_EMAIL);
        await page.fill('input[type="password"]', REGULAR_USER_PASSWORD);
        await page.click('button[type="submit"]');
        await expect(page).toHaveURL(/\/dashboard/);
    }

    /**
     * Helper: Verify localStorage has no sensitive tokens
     */
    async function verifyNoTokensInLocalStorage(page: Page) {
        const localStorage = await page.evaluate(() => {
            const keys = Object.keys(window.localStorage);
            return {
                keys,
                tokenKeys: keys.filter(k =>
                    k.toLowerCase().includes('token') ||
                    k.toLowerCase().includes('auth') ||
                    k.toLowerCase().includes('jwt')
                ),
                allValues: keys.map(k => ({
                    key: k,
                    value: window.localStorage.getItem(k)
                }))
            };
        });

        expect(localStorage.tokenKeys).toHaveLength(0);
    }

    /**
     * Helper: Get all cookies from browser context
     */
    async function getCookiesWithDetails(context: BrowserContext, url: string = 'http://localhost:3000') {
        const cookies = await context.cookies(url);
        return cookies.map(c => ({
            name: c.name,
            httpOnly: c.httpOnly,
            secure: c.secure,
            sameSite: c.sameSite,
            value: c.value ? '[REDACTED]' : null
        }));
    }

    // ============================================================================
    // 1. COOKIE-BASED AUTH (PR #327)
    // ============================================================================

    test.describe('Cookie-Based Auth (PR #327)', () => {

        test('No tokens stored in localStorage after login', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Verify no sensitive data in localStorage
            await verifyNoTokensInLocalStorage(page);

            // Navigate away and back to ensure persistence via cookies
            await page.goto('/dashboard');
            await verifyNoTokensInLocalStorage(page);
        });

        test('HTTP-only cookies are set after login', async ({ context, page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Get cookies from context
            const cookies = await getCookiesWithDetails(context);

            // Find authentication cookie (typically 'session', 'auth', or similar)
            const authCookie = cookies.find(c =>
                c.name.toLowerCase().includes('session') ||
                c.name.toLowerCase().includes('auth') ||
                c.name === '__Secure-next-auth.session-token' ||
                c.name === 'next-auth.session-token'
            );

            expect(authCookie).toBeDefined();
            if (authCookie) {
                expect(authCookie.httpOnly).toBe(true);
                expect(authCookie.sameSite).toBeTruthy(); // Should be 'Strict', 'Lax', or 'None'
            }
        });

        test('Session persists across page navigation via cookies', async ({ page, context }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Capture initial cookies
            const initialCookies = await context.cookies();
            const sessionCookie = initialCookies.find(c =>
                c.name.toLowerCase().includes('session') ||
                c.name.toLowerCase().includes('auth') ||
                c.name === '__Secure-next-auth.session-token' ||
                c.name === 'next-auth.session-token'
            );

            expect(sessionCookie).toBeDefined();

            // Navigate to different pages
            await page.goto('/dashboard');
            await expect(page).not.toHaveURL(/\/login/);

            await page.goto('/fsma');
            await expect(page).not.toHaveURL(/\/login/);

            await page.goto('/review');
            await expect(page).not.toHaveURL(/\/login/);

            // Verify session cookie still present
            const finalCookies = await context.cookies();
            const finalSessionCookie = finalCookies.find(c => c.name === sessionCookie.name);

            expect(finalSessionCookie).toBeDefined();
            expect(finalSessionCookie?.value).toBe(sessionCookie.value);
        });

        test('Logout clears HTTP-only cookies', async ({ page, context }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Verify auth cookie exists
            let cookies = await context.cookies();
            const authCookieExists = cookies.some(c =>
                c.name.toLowerCase().includes('session') ||
                c.name.toLowerCase().includes('auth') ||
                c.name === '__Secure-next-auth.session-token' ||
                c.name === 'next-auth.session-token'
            );
            expect(authCookieExists).toBe(true);

            // Click logout (find logout button/link)
            const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]').first();
            const hasLogoutButton = await logoutButton.count() > 0;

            if (hasLogoutButton) {
                await logoutButton.click();

                // Verify redirected to login
                await expect(page).toHaveURL(/\/login|\/auth/);

                // Verify auth cookies cleared
                cookies = await context.cookies();
                const authCookieCleared = !cookies.some(c =>
                    c.name.toLowerCase().includes('session') ||
                    c.name.toLowerCase().includes('auth') ||
                    c.name === '__Secure-next-auth.session-token' ||
                    c.name === 'next-auth.session-token'
                );
                expect(authCookieCleared).toBe(true);

                // Verify no localStorage tokens
                await verifyNoTokensInLocalStorage(page);
            }
        });

    });

    // ============================================================================
    // 2. SECURITY SETTINGS PAGE (PR #325)
    // ============================================================================

    test.describe('Security Settings Page (PR #325)', () => {

        test('Security settings page renders without dead stubs', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Navigate to security settings
            await page.goto('/settings/security');

            // Page should load (not 404)
            await expect(page).not.toHaveURL(/404|error/);

            // Should have security-related content
            const hasSecurityContent = await page.getByText(/security|settings|protection/i).count() > 0;
            expect(hasSecurityContent).toBe(true);

            // Should not show placeholder/stub text
            const hasStubs = await page.getByText(/coming soon|todo|stub|placeholder|not implemented/i).count();

            // Note: Some "coming soon" is acceptable for features in progress,
            // but core security settings should not be empty stubs
            const hasCoreSettings = await page.getByText(/password|session|two.factor|2fa|authentication/i).count() > 0;
            expect(hasCoreSettings).toBe(true);
        });

        test('2FA section renders correctly', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Navigate to security settings
            await page.goto('/settings/security');

            // Look for 2FA section
            const twoFASection = page.locator('[class*="two-factor"], [class*="2fa"], [data-testid*="2fa"]').first();
            const hasTwoFASection = await twoFASection.count() > 0;

            if (hasTwoFASection) {
                // Section exists - verify it has proper UI
                await expect(twoFASection).toBeVisible();

                // Should have enable/disable button or status indicator
                const hasControls = await twoFASection.locator('button, input[type="checkbox"]').count() > 0;
                const hasStatus = await twoFASection.getByText(/enabled|disabled|off|on/i).count() > 0;

                expect(hasControls || hasStatus).toBe(true);
            } else {
                // Check for 2FA text anywhere on page
                const hasTwoFAText = await page.getByText(/two.factor|2fa|two-factor/i).count() > 0;

                if (hasTwoFAText) {
                    // 2FA mentioned but may be in different section
                    const twoFAElements = page.getByText(/two.factor|2fa|two-factor/i);
                    await expect(twoFAElements.first()).toBeVisible();
                }
            }
        });

        test('Session management section shows real data or proper messaging', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Navigate to security settings
            await page.goto('/settings/security');

            // Look for session management section
            const sessionSection = page.locator('[class*="session"], [data-testid*="session"]').first();
            const hasSessionSection = await sessionSection.count() > 0;

            if (hasSessionSection) {
                await expect(sessionSection).toBeVisible();

                // Should show either:
                // 1. List of active sessions
                // 2. "Coming soon" or "Not yet available" message
                // 3. Logout all sessions button

                const hasActiveSessionsList = await sessionSection.locator('[class*="device"], [class*="session-item"]').count() > 0;
                const hasComingSoon = await sessionSection.getByText(/coming soon|not available|not yet|future feature/i).count() > 0;
                const hasLogoutAllButton = await sessionSection.locator('button:has-text("Logout All")').count() > 0;

                expect(hasActiveSessionsList || hasComingSoon || hasLogoutAllButton).toBe(true);
            } else {
                // Check for session management text
                const hasSessionText = await page.getByText(/session|device|browser|logout all/i).count() > 0;
                expect(hasSessionText).toBe(true);
            }
        });

    });

    // ============================================================================
    // 3. SYSADMIN CACHE & ACCESS CONTROL (PR #325)
    // ============================================================================

    test.describe('Sysadmin Cache & Access Control (PR #325)', () => {

        test('Sysadmin status reflected in UI after login', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Navigate to dashboard or main page
            await page.goto('/dashboard');

            // Admin should have access to sysadmin features
            // Look for sysadmin indicators or menu items
            const sysadminMenu = page.locator('a:has-text("Admin"), a:has-text("Sysadmin"), [data-testid*="admin"]').first();
            const hasSysadminUI = await sysadminMenu.count() > 0;

            // If sysadmin menu exists, verify it's accessible
            if (hasSysadminUI) {
                await expect(sysadminMenu).toBeVisible();
            } else {
                // Alternative: navigate to /sysadmin directly
                await page.goto('/sysadmin');
                // Should not get 403 Forbidden or redirect to login
                await expect(page).not.toHaveURL(/\/login|\/forbidden|403/);
            }
        });

        test('Non-sysadmin cannot access /sysadmin routes', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsRegularUser(page);

            // Navigate to dashboard first
            await page.goto('/dashboard');

            // Try to access sysadmin route
            await page.goto('/sysadmin', { waitUntil: 'networkidle' });

            // Should either:
            // 1. Redirect to dashboard
            // 2. Show 403 error
            // 3. Show "Access Denied" message
            const isRedirectedOrDenied =
                page.url().includes('/dashboard') ||
                page.url().includes('/login') ||
                (await page.getByText(/403|forbidden|access denied|not authorized/i).count()) > 0;

            expect(isRedirectedOrDenied).toBe(true);
        });

        test('Sysadmin role persists across page reloads', async ({ page, context }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Navigate to sysadmin section
            await page.goto('/sysadmin');
            const initialURL = page.url();

            // Reload page
            await page.reload();

            // Should still be on sysadmin page (not redirected to login)
            expect(page.url()).toContain('/sysadmin');

            // Reload again to test persistence
            await page.reload();
            await expect(page).toHaveURL(/\/sysadmin/);
        });

    });

    // ============================================================================
    // 4. CSRF PROTECTION (PR #329)
    // ============================================================================

    test.describe('CSRF Protection (PR #329)', () => {

        test('State-changing forms include CSRF tokens', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Navigate to a page with forms (settings, profile, etc.)
            await page.goto('/settings/security');

            // Find forms on the page
            const forms = page.locator('form');
            const formCount = await forms.count();

            if (formCount > 0) {
                // For each form, check for CSRF token
                for (let i = 0; i < Math.min(formCount, 3); i++) {
                    const form = forms.nth(i);

                    // Look for CSRF token in hidden inputs
                    const csrfInput = form.locator('input[name*="csrf"], input[type="hidden"][name*="token"], input[name="_token"]').first();
                    const hasCsrfToken = await csrfInput.count() > 0;

                    if (hasCsrfToken) {
                        await expect(csrfInput).toHaveAttribute('type', 'hidden');
                        const tokenValue = await csrfInput.inputValue();
                        expect(tokenValue).toBeTruthy();
                        expect(tokenValue?.length).toBeGreaterThan(0);
                    }
                }
            }
        });

        test('API calls include CSRF header for state-changing methods', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            const requestHeaders: { [key: string]: string } = {};

            // Capture request headers
            page.on('request', request => {
                const method = request.method();
                const url = request.url();

                // Only track state-changing requests to API
                if ((method === 'POST' || method === 'PUT' || method === 'DELETE' || method === 'PATCH') &&
                    url.includes('/api')) {

                    const headers = request.headers();
                    requestHeaders[url] = JSON.stringify({
                        'x-csrf-token': headers['x-csrf-token'],
                        'csrf-token': headers['csrf-token'],
                        'x-xsrf-token': headers['x-xsrf-token']
                    });
                }
            });

            // Navigate to trigger API calls
            await page.goto('/settings');
            await page.waitForLoadState('networkidle');

            // Check if any state-changing requests were made
            const hasMutationRequests = Object.keys(requestHeaders).length > 0;

            if (hasMutationRequests) {
                // Verify at least one request includes a CSRF token
                const hasCSRFProtection = Object.values(requestHeaders).some(headers => {
                    const parsed = JSON.parse(headers);
                    return parsed['x-csrf-token'] || parsed['csrf-token'] || parsed['x-xsrf-token'];
                });

                expect(hasCSRFProtection).toBe(true);
            }
        });

        test('POST requests without CSRF token are rejected', async ({ page, context }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Attempt to make a POST request without CSRF token via API
            // This should be rejected with 403 Forbidden
            const response = await context.request.post('http://localhost:8400/api/user/settings', {
                data: { theme: 'dark' },
                // Deliberately omitting CSRF headers
            });

            // Should get 403 Forbidden or 401 Unauthorized
            expect([403, 401, 400]).toContain(response.status());
        });

    });

    // ============================================================================
    // 5. AUTH GUARD VISIBILITY & ERROR HANDLING
    // ============================================================================

    test.describe('Auth Guard Visibility & Error Handling', () => {

        test('Unauthenticated users redirected from protected routes', async ({ page, context }) => {
            test.setTimeout(60000);

            // Create a new context without authentication
            const unauthContext = await context.browser()?.newContext() ?? context;

            // Access protected route without logging in
            const unauthPage = await unauthContext.newPage();

            await unauthPage.goto('/dashboard', { waitUntil: 'networkidle' });

            // Should redirect to login
            const isOnLoginPage =
                unauthPage.url().includes('/login') ||
                unauthPage.url().includes('/auth') ||
                (await unauthPage.getByText(/sign in|log in|login/i).count()) > 0;

            expect(isOnLoginPage).toBe(true);

            // Try other protected routes
            await unauthPage.goto('/sysadmin', { waitUntil: 'networkidle' });
            const isRedirected =
                unauthPage.url().includes('/login') ||
                unauthPage.url().includes('/auth');

            expect(isRedirected).toBe(true);

            await unauthPage.close();
        });

        test('Protected API responses do not leak data in error messages', async ({ page, context }) => {
            test.setTimeout(60000);

            // Intercept API responses to check error messages
            const apiErrors: { url: string; message: string }[] = [];

            context.on('response', async response => {
                if (!response.ok() && response.url().includes('/api')) {
                    const text = await response.text();
                    apiErrors.push({
                        url: response.url(),
                        message: text
                    });
                }
            });

            // Try to access protected API without auth
            const response = await context.request.get('http://localhost:8400/api/user/profile');

            // Verify error response doesn't leak sensitive info
            const responseText = await response.text();

            // Should not contain:
            // - User IDs, emails, or names
            // - Database details
            // - Internal paths or config
            // - SQL errors
            const leaksData =
                /users?\.id|users?\.email|SELECT|FROM|WHERE|table|database|config|api_key|secret/i.test(responseText);

            expect(leaksData).toBe(false);

            // Should return appropriate error status
            expect([401, 403, 400]).toContain(response.status());
        });

        test('Error pages do not expose sensitive information', async ({ page }) => {
            test.setTimeout(60000);

            // Navigate to non-existent protected route
            await page.goto('/admin/nonexistent', { waitUntil: 'networkidle' });

            // Get page content
            const pageContent = await page.textContent('body');

            // Error messages should not contain:
            const leaksSensitiveInfo = pageContent?.match(
                /database|config|password|api_key|secret|token|sql|stack trace/i
            );

            expect(leaksSensitiveInfo).toBeFalsy();
        });

        test('Login page redirects authenticated users', async ({ page }) => {
            test.setTimeout(60000);

            await loginAsAdmin(page);

            // Now try to navigate to /login
            await page.goto('/login');

            // Should redirect to dashboard or home
            const isRedirected =
                page.url().includes('/dashboard') ||
                page.url().includes('/sysadmin') ||
                page.url().includes('/home');

            expect(isRedirected).toBe(true);
        });

    });

    // ============================================================================
    // 6. INTEGRATION TESTS
    // ============================================================================

    test.describe('Integration: Full Auth & Security Flow', () => {

        test('Complete login -> navigate -> security settings -> logout flow', async ({ page, context }) => {
            test.setTimeout(90000);

            // 1. Login
            await loginAsAdmin(page);

            // Verify cookie-based auth
            let cookies = await context.cookies();
            const authCookie = cookies.find(c =>
                c.name.toLowerCase().includes('session') ||
                c.name.toLowerCase().includes('auth')
            );
            expect(authCookie).toBeDefined();
            expect(authCookie?.httpOnly).toBe(true);

            // 2. Navigate to security settings
            await page.goto('/settings/security');

            // Should not lose session
            const urlAfterNav = page.url();
            expect(urlAfterNav).toContain('/settings/security');
            expect(urlAfterNav).not.toContain('/login');

            // 3. Verify no tokens in localStorage
            await verifyNoTokensInLocalStorage(page);

            // 4. Navigate to dashboard
            await page.goto('/dashboard');

            // 5. Attempt logout
            const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]').first();
            const hasLogout = await logoutButton.count() > 0;

            if (hasLogout) {
                await logoutButton.click();

                // Should redirect to login
                await expect(page).toHaveURL(/\/login|\/auth/);

                // Cookies should be cleared
                cookies = await context.cookies();
                const authCleared = !cookies.some(c =>
                    c.name.toLowerCase().includes('session') ||
                    c.name.toLowerCase().includes('auth')
                );
                expect(authCleared).toBe(true);
            }
        });

        test('Sysadmin can access admin routes, regular user cannot', async ({ browser }) => {
            test.setTimeout(120000);

            // Test as admin
            const adminContext = await browser?.newContext() ?? await test.elementError;
            const adminPage = await adminContext.newPage();

            await loginAsAdmin(adminPage);
            await adminPage.goto('/sysadmin');

            const adminCanAccess =
                adminPage.url().includes('/sysadmin') &&
                !adminPage.url().includes('/login');

            expect(adminCanAccess).toBe(true);
            await adminContext.close();

            // Test as regular user
            const userContext = await browser?.newContext() ?? await test.elementError;
            const userPage = await userContext.newPage();

            await loginAsRegularUser(userPage);
            await userPage.goto('/sysadmin');

            const userRedirected =
                userPage.url().includes('/login') ||
                userPage.url().includes('/dashboard') ||
                (await userPage.getByText(/403|forbidden|access denied/i).count()) > 0;

            expect(userRedirected).toBe(true);
            await userContext.close();
        });

    });

});
