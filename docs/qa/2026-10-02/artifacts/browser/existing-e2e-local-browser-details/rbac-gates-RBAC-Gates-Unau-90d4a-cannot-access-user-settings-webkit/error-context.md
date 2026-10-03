# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: rbac-gates.spec.ts >> RBAC Gates >> Unauthenticated cannot access user settings
- Location: tests/e2e/rbac-gates.spec.ts:65:9

# Error details

```
Error: route.fulfill: Cannot fulfill with redirect status: 307
```

```
Error: page.goto: Test ended.
Call log:
  - navigating to "http://127.0.0.1:3114/settings/users", waiting until "load"

```

# Test source

```ts
  1   | import { test, expect, type Page } from '@playwright/test';
  2   | import { adminAuthenticatedE2ESkipReason, hasAdminAuthenticatedE2E } from './auth-prereqs';
  3   | import { fillPasswordLogin, selectPasswordLogin } from './support/ui-auth';
  4   | 
  5   | /** Wait for navigation to an authenticated page (pathname-only check to avoid matching query strings like ?next=/dashboard) */
  6   | async function waitForAuthenticated(page: Page, timeout = 15000) {
  7   |     await page.waitForURL(url => {
  8   |         const pathname = new URL(url).pathname;
  9   |         return /^\/(dashboard|sysadmin|onboarding)/.test(pathname);
  10  |     }, { timeout });
  11  | }
  12  | 
  13  | /**
  14  |  * RBAC Gates E2E Tests
  15  |  *
  16  |  * Verifies that role-based access control works correctly at the browser level:
  17  |  * - Unauthenticated users are redirected to login
  18  |  * - Non-admin users cannot access admin-only sections
  19  |  * - RBAC permission checks enforce UI restrictions
  20  |  */
  21  | 
  22  | // Use dedicated admin account if available; fall back to the general test user.
  23  | // If your test user has sysadmin role, all admin tests will pass with just TEST_USER_EMAIL.
  24  | // Set TEST_ADMIN_EMAIL + TEST_ADMIN_PASSWORD secrets for a dedicated sysadmin account.
  25  | const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL || process.env.TEST_USER_EMAIL || 'admin@example.com';
  26  | const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_PASSWORD || 'test-placeholder';
  27  | 
  28  | // Sysadmin tests require a dedicated account with is_sysadmin=true.
  29  | // The test user created by globalSetup is a regular org owner, NOT a sysadmin.
  30  | const hasDedicatedAdmin = !!(
  31  |     process.env.TEST_ADMIN_EMAIL &&
  32  |     process.env.TEST_ADMIN_PASSWORD &&
  33  |     process.env.TEST_ADMIN_EMAIL !== process.env.TEST_USER_EMAIL
  34  | );
  35  | 
  36  | test.describe('RBAC Gates', () => {
  37  | 
  38  |     test.afterEach(async ({ page }, testInfo) => {
  39  |         if (testInfo.status !== testInfo.expectedStatus) {
  40  |             const path = `test-results/rbac-failure-${testInfo.title.replace(/\s+/g, '-').toLowerCase()}.png`;
  41  |             await page.screenshot({ path, fullPage: true });
  42  |         }
  43  |     });
  44  | 
  45  |     test('Unauthenticated users are redirected to login', async ({ page }) => {
  46  |         // Navigate directly to protected route without authentication
  47  |         await page.goto('/dashboard');
  48  | 
  49  |         // Should redirect to login page
  50  |         await expect(page).toHaveURL(/\/login/);
  51  | 
  52  |         // Login form should be visible
  53  |         await expect(page.getByRole('textbox', { name: /email address/i }).first()).toBeVisible();
  54  |         await selectPasswordLogin(page);
  55  |         await expect(page.getByLabel(/password/i).first()).toBeVisible();
  56  |     });
  57  | 
  58  |     test('Unauthenticated cannot access sysadmin', async ({ page }) => {
  59  |         await page.goto('/sysadmin');
  60  | 
  61  |         // Should redirect to login
  62  |         await expect(page).toHaveURL(/\/login/);
  63  |     });
  64  | 
  65  |     test('Unauthenticated cannot access user settings', async ({ page }) => {
> 66  |         await page.goto('/settings/users');
      |                    ^ Error: page.goto: Test ended.
  67  | 
  68  |         // Should redirect to login (settings/* is auth-gated)
  69  |         await expect(page).toHaveURL(/\/login/);
  70  |     });
  71  | 
  72  |     test('Admin can access sysadmin dashboard', async ({ page }) => {
  73  |         // Requires a dedicated sysadmin account.
  74  |         // The test user created by globalSetup is a regular org member — not sysadmin.
  75  |         // The sysadmin page checks user.is_sysadmin client-side and redirects to /login if false.
  76  |         test.skip(!hasDedicatedAdmin, 'Requires a dedicated sysadmin account — set TEST_ADMIN_EMAIL + TEST_ADMIN_PASSWORD secrets pointing to a sysadmin user');
  77  |         test.skip(!hasAdminAuthenticatedE2E, adminAuthenticatedE2ESkipReason);
  78  | 
  79  |         test.setTimeout(60000);
  80  | 
  81  |         // Login as admin — ?next=/dashboard bypasses the onboarding check so
  82  |         // the test reliably lands on /dashboard regardless of the test user's
  83  |         // onboarding state.  Sysadmin accounts will still proceed normally.
  84  |         await page.goto('/login?next=/dashboard');
  85  |         await fillPasswordLogin(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  86  |         await page.click('button[type="submit"]');
  87  | 
  88  |         // Wait for redirect to dashboard or sysadmin
  89  |         await waitForAuthenticated(page);
  90  | 
  91  |         // Navigate to sysadmin
  92  |         await page.goto('/sysadmin');
  93  | 
  94  |         // Should stay on sysadmin (not redirected)
  95  |         await expect(page).toHaveURL(/\/sysadmin/);
  96  | 
  97  |         // Sysadmin content should be visible — use .first() to avoid strict-mode
  98  |         // violation when multiple nav elements match (e.g. "Admin" nav + page heading)
  99  |         await expect(page.getByText(/System|Admin|Dashboard/i).first()).toBeVisible();
  100 |     });
  101 | 
  102 |     test('Admin can access user management', async ({ page }) => {
  103 |         test.skip(!hasAdminAuthenticatedE2E, adminAuthenticatedE2ESkipReason);
  104 |         test.setTimeout(60000);
  105 | 
  106 |         // Login as admin — ?next=/settings/users to navigate directly to the team page
  107 |         await page.goto('/login?next=/settings/users');
  108 |         await fillPasswordLogin(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  109 |         await page.click('button[type="submit"]');
  110 | 
  111 |         await waitForAuthenticated(page);
  112 | 
  113 |         // Should not be on login page (auth works)
  114 |         await expect(page).not.toHaveURL(/\/login/);
  115 | 
  116 |         // May land on /settings/users, /dashboard, or /onboarding depending
  117 |         // on the test user's onboarding state and role. All are valid.
  118 |         // Verify some authenticated content rendered.
  119 |         await expect(page.locator('nav, main, [role="navigation"]').first()).toBeVisible({ timeout: 15000 });
  120 |     });
  121 | 
  122 |     test('Protected API calls return 401 without auth', async ({ page }) => {
  123 |         // Call admin API through the Next.js proxy (no local admin service in CI)
  124 |         const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001';
  125 |         const response = await page.request.get(`${baseURL}/api/admin/v1/admin/users`);
  126 | 
  127 |         expect([401, 403]).toContain(response.status());
  128 |     });
  129 | 
  130 |     test('Session persists across navigation', async ({ page }) => {
  131 |         test.skip(!hasAdminAuthenticatedE2E, adminAuthenticatedE2ESkipReason);
  132 |         test.setTimeout(60000);
  133 | 
  134 |         // Login — ?next=/dashboard bypasses the onboarding check
  135 |         await page.goto('/login?next=/dashboard');
  136 |         await fillPasswordLogin(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  137 |         await page.click('button[type="submit"]');
  138 | 
  139 |         await waitForAuthenticated(page);
  140 | 
  141 |         // Navigate to multiple pages
  142 |         await page.goto('/dashboard');
  143 |         await expect(page).toHaveURL(/\/dashboard/);
  144 | 
  145 |         await page.goto('/fsma');
  146 |         await expect(page).not.toHaveURL(/\/login/);
  147 | 
  148 |         await page.goto('/ingest');
  149 |         await expect(page).not.toHaveURL(/\/login/);
  150 | 
  151 |         // Session should still be valid (/settings/users redirects → /dashboard/settings)
  152 |         await page.goto('/settings/users');
  153 |         await expect(page).toHaveURL(/\/dashboard\/settings|\/settings\/users/);
  154 |     });
  155 | 
  156 | });
  157 | 
```