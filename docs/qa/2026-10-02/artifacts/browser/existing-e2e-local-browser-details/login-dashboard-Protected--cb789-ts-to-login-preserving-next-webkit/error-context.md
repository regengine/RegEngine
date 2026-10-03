# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: login-dashboard.spec.ts >> Protected deep links >> unauthenticated deep link redirects to login preserving next
- Location: tests/e2e/login-dashboard.spec.ts:165:9

# Error details

```
Error: route.fulfill: Cannot fulfill with redirect status: 307
```

```
Error: page.goto: Test ended.
Call log:
  - navigating to "http://127.0.0.1:3114/reports/abc123", waiting until "load"

```

# Test source

```ts
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
  88  |         await expect(continueButton).toBeFocused();
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
> 166 |         await page.goto('/reports/abc123');
      |                    ^ Error: page.goto: Test ended.
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
  189 |         // remember-me variant (and no re_access_token JWT cookie) anymore.
  190 |         const authCookie = await authSessionCookie(context);
  191 |         expect(authCookie).toBeDefined();
  192 |         expect(authCookie?.httpOnly).toBe(true);
  193 |         expect(authCookie?.expires).toBeGreaterThan(Math.floor(Date.now() / 1000));
  194 | 
  195 |         await logoutViaApi(context);
  196 |         expect(await authSessionCookie(context)).toBeUndefined();
  197 |     });
  198 | });
  199 | 
  200 | test.describe('Dashboard Features', () => {
  201 |     test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
  202 | 
  203 |     test.beforeEach(async ({ page, context }) => {
  204 |         await loginViaApi(context, TEST_USER_EMAIL);
  205 |         await page.goto('/dashboard');
  206 |     });
  207 | 
  208 |     test('dashboard displays user information', async ({ page }) => {
  209 |         test.setTimeout(60000);
  210 | 
  211 |         await expect(page).not.toHaveURL(/\/login/);
  212 | 
  213 |         // Verify some authenticated UI rendered — nav, main content, etc.
  214 |         // The specific page depends on the test user's onboarding state and role.
  215 |         await expect(page.locator('nav, main, [role="navigation"]').first()).toBeVisible({ timeout: 15000 });
  216 |     });
  217 | 
  218 |     test('dashboard has navigation links', async ({ page }) => {
  219 |         // Common navigation items
  220 |         const navItems = ['Energy', 'Opportunity', 'Settings'];
  221 | 
  222 |         for (const item of navItems) {
  223 |             const link = page.locator(`a:has-text("${item}")`).first();
  224 |             if (await link.isVisible()) {
  225 |                 await expect(link).toBeEnabled();
  226 |             }
  227 |         }
  228 |     });
  229 | 
  230 |     test('navigation links work correctly', async ({ page }) => {
  231 |         // Try to navigate to Energy page (if exists)
  232 |         const energyLink = page.locator('a:has-text("Energy")').first();
  233 | 
  234 |         if (await energyLink.isVisible()) {
  235 |             await energyLink.click();
  236 |             // Should navigate away from dashboard
  237 |             await page.waitForTimeout(500);
  238 |             // URL should change
  239 |             const currentUrl = page.url();
  240 |             expect(currentUrl).not.toMatch(/\/dashboard$/);
  241 |         }
  242 |     });
  243 | });
  244 | 
```