# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: login-dashboard.spec.ts >> Login → Dashboard Flow >> login form has proper accessibility and autofill-friendly controls
- Location: tests/e2e/login-dashboard.spec.ts:71:9

# Error details

```
Error: expect(locator).toBeFocused() failed

Locator:  getByRole('button', { name: /^continue/i })
Expected: focused
Received: inactive
Timeout:  15000ms

Call log:
  - Expect "toBeFocused" getByRole('button', { name: /^continue/i }) with timeout 15000ms
  - waiting for getByRole('button', { name: /^continue/i })
    34 × locator resolved to <button type="submit" class="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border text-ui font-medium transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none [&_svg]:size-4 [&_svg]:shrink-0 border-transparent bg-re-brand text-re-brand-foreground hover:bg-re-brand-dark acti…>…</button>
       - unexpected value "inactive"

```

```yaml
- button "Continue"
```

# Test source

```ts
  1   | /**
  2   |  * E2E Test: Login → Dashboard Flow (passwordless)
  3   |  *
  4   |  * The app has no password login: /login collects an email, POST
  5   |  * /api/admin/auth/challenges issues a sign-in code, and /auth/verify exchanges
  6   |  * the code for the opaque __Host-regengine_session cookie. Locally the backend
  7   |  * runs with REGENGINE_E2E_MODE=true and writes OTPs to the outbox fixture, so
  8   |  * these tests complete real logins end to end.
  9   |  *
  10  |  * Critical user journeys:
  11  |  * 1. Email OTP login lands on the dashboard with a hydrated session
  12  |  * 2. Wrong codes surface an error and never authenticate
  13  |  * 3. Logout tears the session down and protected pages stay gated
  14  |  */
  15  | 
  16  | import { test, expect, type BrowserContext, type Page } from '@playwright/test';
  17  | import { hasPasswordlessE2E, passwordlessE2ESkipReason } from './auth-prereqs';
  18  | import { AUTH_SESSION_COOKIE, loginWithEmailOtp, seedPasswordlessUser } from './auth-helpers';
  19  | import { loginViaApi, logoutViaApi } from './support/api-auth';
  20  | 
  21  | const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'playwright-e2e@example.com';
  22  | 
  23  | function uniqueEmail(prefix: string): string {
  24  |     return `${prefix}+${Date.now()}@example.com`;
  25  | }
  26  | 
  27  | async function authSessionCookie(context: BrowserContext) {
  28  |     const cookies = await context.cookies();
  29  |     return cookies.find(cookie => cookie.name === AUTH_SESSION_COOKIE);
  30  | }
  31  | 
  32  | async function startChallengeFromLoginPage(page: Page, email: string): Promise<void> {
  33  |     await page.goto('/login');
  34  |     await expect(page.getByRole('heading', { name: /continue to regengine/i })).toBeVisible();
  35  |     await page.getByLabel(/email address/i).fill(email);
  36  |     await page.getByRole('button', { name: /^continue/i }).click();
  37  | }
  38  | 
  39  | test.describe('Login → Dashboard Flow', () => {
  40  |     test('successful email OTP login redirects to dashboard', async ({ page, context }) => {
  41  |         test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  42  | 
  43  |         const email = uniqueEmail('playwright-login-dashboard');
  44  |         seedPasswordlessUser(email);
  45  | 
  46  |         await page.goto('/login');
  47  |         await expect(page).toHaveTitle(/RegEngine/);
  48  | 
  49  |         // loginWithEmailOtp asserts the full journey: /login → /auth/verify →
  50  |         // /dashboard plus the opaque session cookie attributes.
  51  |         await loginWithEmailOtp(page, context, email);
  52  |     });
  53  | 
  54  |     test('wrong verification code shows an error and does not authenticate', async ({ page, context }) => {
  55  |         test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  56  | 
  57  |         // Anti-enumeration: unseeded addresses still get a challenge_id, so no
  58  |         // seeding is needed to exercise the failure path.
  59  |         await startChallengeFromLoginPage(page, uniqueEmail('playwright-wrong-code'));
  60  |         await expect(page).toHaveURL(/\/auth\/verify$/);
  61  | 
  62  |         await page.getByLabel(/verification code/i).fill('000000');
  63  |         await page.getByRole('button', { name: /verify and continue/i }).click();
  64  | 
  65  |         await expect(page.locator('#otp-error')).toBeVisible();
  66  |         await expect(page.locator('#otp-error')).toContainText(/incorrect or expired/i);
  67  |         await expect(page).toHaveURL(/\/auth\/verify$/);
  68  |         expect(await authSessionCookie(context)).toBeUndefined();
  69  |     });
  70  | 
  71  |     test('login form has proper accessibility and autofill-friendly controls', async ({ page }) => {
  72  |         await page.goto('/login');
  73  | 
  74  |         await expect(page.getByRole('heading', { name: /continue to regengine/i })).toBeVisible();
  75  | 
  76  |         const emailInput = page.locator('#email');
  77  |         await expect(emailInput).toHaveAttribute('name', 'email');
  78  |         await expect(emailInput).toHaveAttribute('type', 'email');
  79  |         await expect(emailInput).toHaveAttribute('autocomplete', 'email');
  80  | 
  81  |         const continueButton = page.getByRole('button', { name: /^continue/i });
  82  |         await expect(continueButton).toBeEnabled();
  83  |         await expect(page.getByRole('button', { name: /sign in with passkey/i })).toBeVisible();
  84  | 
  85  |         await emailInput.focus();
  86  |         await expect(emailInput).toBeFocused();
  87  |         await page.keyboard.press('Tab');
> 88  |         await expect(continueButton).toBeFocused();
      |                                      ^ Error: expect(locator).toBeFocused() failed
  89  |     });
  90  | 
  91  |     test('rapid double submit starts only one sign-in challenge', async ({ page }) => {
  92  |         test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  93  | 
  94  |         let challengeRequests = 0;
  95  |         page.on('request', (request) => {
  96  |             if (request.method() === 'POST' && request.url().includes('/api/admin/auth/challenges')) {
  97  |                 challengeRequests += 1;
  98  |             }
  99  |         });
  100 | 
  101 |         await page.goto('/login');
  102 |         await page.getByLabel(/email address/i).fill(uniqueEmail('playwright-double-submit'));
  103 | 
  104 |         const continueButton = page.getByRole('button', { name: /^continue/i });
  105 |         const box = await continueButton.boundingBox();
  106 |         expect(box).toBeTruthy();
  107 |         await page.mouse.dblclick(box!.x + box!.width / 2, box!.y + box!.height / 2);
  108 | 
  109 |         await expect(page).toHaveURL(/\/auth\/verify$/);
  110 |         expect(challengeRequests).toBe(1);
  111 |     });
  112 | 
  113 |     test('challenge network failure keeps the form filled and shows a clear error', async ({ page }) => {
  114 |         await page.route('**/api/admin/auth/challenges', (route) => route.abort('failed'));
  115 | 
  116 |         await page.goto('/login');
  117 |         const email = 'network-fail@example.com';
  118 |         await page.getByLabel(/email address/i).fill(email);
  119 |         await page.getByRole('button', { name: /^continue/i }).click();
  120 | 
  121 |         await expect(page.locator('#login-error')).toBeVisible();
  122 |         // Chromium surfaces aborted fetches as "Failed to fetch"; the client
  123 |         // falls back to its own copy when the error carries no message.
  124 |         await expect(page.locator('#login-error')).toContainText(/failed to fetch|unable to start sign-in/i);
  125 |         await expect(page).toHaveURL(/\/login/);
  126 |         await expect(page.getByLabel(/email address/i)).toHaveValue(email);
  127 |     });
  128 | 
  129 |     test('logout from dashboard redirects to login', async ({ page, context }) => {
  130 |         test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  131 |         test.setTimeout(60000);
  132 | 
  133 |         const email = uniqueEmail('playwright-logout');
  134 |         seedPasswordlessUser(email);
  135 |         await loginWithEmailOtp(page, context, email);
  136 | 
  137 |         const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]').first();
  138 |         if (await logoutButton.isVisible({ timeout: 5000 })) {
  139 |             await logoutButton.click();
  140 |             await page.waitForURL(/\/login/, { timeout: 15000 });
  141 |             await expect(page).toHaveURL(/\/login/);
  142 |         }
  143 |     });
  144 | 
  145 |     test('back after logout does not restore a protected dashboard from cache', async ({ page, context }) => {
  146 |         test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  147 |         test.setTimeout(60000);
  148 | 
  149 |         const email = uniqueEmail('playwright-back-cache');
  150 |         seedPasswordlessUser(email);
  151 |         await loginWithEmailOtp(page, context, email);
  152 | 
  153 |         await logoutViaApi(context);
  154 |         await context.clearCookies();
  155 |         await page.goto('/login');
  156 |         await expect(page).toHaveURL(/\/login/);
  157 | 
  158 |         await page.goBack({ waitUntil: 'domcontentloaded' });
  159 |         await page.waitForURL(/\/login/, { timeout: 15000 });
  160 |         await expect(page.getByRole('heading', { name: /continue to regengine/i })).toBeVisible();
  161 |     });
  162 | });
  163 | 
  164 | test.describe('Protected deep links', () => {
  165 |     test('unauthenticated deep link redirects to login preserving next', async ({ page }) => {
  166 |         await page.goto('/reports/abc123');
  167 |         await expect(page).toHaveURL((url) =>
  168 |             url.pathname === '/login' && url.searchParams.get('next') === '/reports/abc123',
  169 |         );
  170 |     });
  171 | 
  172 |     test('deep link is reachable after API login', async ({ page, context }) => {
  173 |         test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  174 | 
  175 |         await loginViaApi(context, TEST_USER_EMAIL);
  176 |         await page.goto('/reports/abc123');
  177 |         await expect(page).toHaveURL((url) => url.pathname === '/reports/abc123', { timeout: 15000 });
  178 |     });
  179 | });
  180 | 
  181 | test.describe('Login session cookie mode', () => {
  182 |     test('email OTP login sets a persistent opaque session cookie', async ({ context }) => {
  183 |         test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  184 | 
  185 |         await context.clearCookies();
  186 |         await loginViaApi(context, TEST_USER_EMAIL);
  187 | 
  188 |         // The backend always issues a 7-day opaque session cookie; there is no
```