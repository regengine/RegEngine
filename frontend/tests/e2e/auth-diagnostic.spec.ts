/**
 * E2E Auth Diagnostic — isolates each step of the login → cookie → middleware chain.
 * Runs first (alphabetically) so we get diagnostics before other tests fail.
 */
import { test, expect } from '@playwright/test';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

test.describe('Auth Chain Diagnostic', () => {
    test('step-by-step auth chain', async ({ page, request }) => {
        test.setTimeout(90000);
        // ─── Step 0: Env vars ───
        console.log('[diag] TEST_USER_EMAIL:', TEST_USER_EMAIL);
        console.log('[diag] TEST_PASSWORD length:', TEST_PASSWORD?.length);

        // ─── Step 1: Direct login via API context (bypasses browser) ───
        console.log('[diag] Step 1: POST /api/admin/auth/login');
        const loginRes = await request.post('/api/admin/auth/login', {
            data: { email: TEST_USER_EMAIL, password: TEST_PASSWORD },
        });
        console.log('[diag] Login response status:', loginRes.status());
        const loginBody = await loginRes.json().catch(() => loginRes.text());
        console.log('[diag] Login response body keys:', typeof loginBody === 'object' ? Object.keys(loginBody) : 'NOT JSON');
        console.log('[diag] Has access_token:', !!(loginBody as any)?.access_token);
        console.log('[diag] access_token length:', (loginBody as any)?.access_token?.length ?? 0);
        console.log('[diag] tenant_id:', (loginBody as any)?.tenant_id);
        
        expect(loginRes.status()).toBe(200);
        const { access_token, user, tenant_id } = loginBody as any;
        expect(access_token).toBeTruthy();

        // ─── Step 2: POST /api/session to set cookie ───
        console.log('[diag] Step 2: POST /api/session');
        const sessionRes = await request.post('/api/session', {
            data: { access_token, user, tenant_id },
        });
        console.log('[diag] Session response status:', sessionRes.status());
        console.log('[diag] Session response headers:', Object.fromEntries(sessionRes.headersArray().map(h => [h.name, h.value])));

        expect(sessionRes.status()).toBe(200);

        // ─── Step 3: Check JWT structure ───
        console.log('[diag] Step 3: JWT analysis');
        const parts = access_token.split('.');
        console.log('[diag] JWT parts count:', parts.length);
        if (parts.length === 3) {
            try {
                const header = JSON.parse(Buffer.from(parts[0], 'base64url').toString());
                const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString());
                console.log('[diag] JWT header:', JSON.stringify(header));
                console.log('[diag] JWT payload keys:', Object.keys(payload));
                console.log('[diag] JWT exp:', payload.exp, 'now:', Math.floor(Date.now() / 1000));
                console.log('[diag] JWT expired:', payload.exp < Math.floor(Date.now() / 1000));
            } catch (e) {
                console.log('[diag] JWT parse error:', e);
            }
        }

        // ─── Step 4: Browser login flow ───
        console.log('[diag] Step 4: Browser login');
        
        // Listen for ALL network responses
        const responses: { url: string; status: number; headers: Record<string, string> }[] = [];
        page.on('response', (res) => {
            const url = res.url();
            if (url.includes('/api/') || url.includes('/login') || url.includes('/dashboard')) {
                responses.push({
                    url: url.replace(/^http:\/\/localhost:3001/, ''),
                    status: res.status(),
                    headers: res.headers(),
                });
            }
        });

        await page.goto('/login');
        await page.fill('input[type="email"]', TEST_USER_EMAIL);
        await page.fill('input[type="password"]', TEST_PASSWORD);
        
        // Click submit and wait for network idle
        await Promise.all([
            page.waitForResponse(res => res.url().includes('/api/admin/auth/login')),
            page.click('button[type="submit"]'),
        ]);

        // Wait a moment for session cookie to be set
        await page.waitForTimeout(2000);

        // Log all captured responses
        console.log('[diag] Network responses:');
        for (const r of responses) {
            console.log(`[diag]   ${r.status} ${r.url}`);
            if (r.url.includes('/api/session') || r.url.includes('/api/admin/auth/login')) {
                const setCookie = r.headers['set-cookie'] || 'none';
                console.log(`[diag]     set-cookie: ${setCookie.substring(0, 200)}`);
            }
        }

        // Check cookies after login
        const cookies = await page.context().cookies();
        console.log('[diag] Browser cookies after login:');
        for (const c of cookies) {
            console.log(`[diag]   ${c.name} = ${c.value.substring(0, 30)}... (httpOnly=${c.httpOnly}, secure=${c.secure}, path=${c.path})`);
        }
        
        const hasAccessToken = cookies.some(c => c.name === 're_access_token');
        console.log('[diag] Has re_access_token cookie:', hasAccessToken);

        // Check for login error on page
        const errorEl = page.locator('#login-error');
        const hasError = await errorEl.count() > 0 && await errorEl.isVisible();
        if (hasError) {
            console.log('[diag] LOGIN ERROR on page:', await errorEl.textContent());
        }

        // ─── Step 5: Navigate to dashboard ───
        console.log('[diag] Step 5: Navigate to /dashboard');
        const currentUrl = page.url();
        console.log('[diag] Current URL before navigation:', currentUrl);

        if (hasAccessToken) {
            await page.goto('/dashboard');
            await page.waitForTimeout(2000);
            console.log('[diag] URL after /dashboard navigation:', page.url());
        } else {
            console.log('[diag] SKIPPING — no access token cookie set');
        }

        // ─── Step 6: Check JWT diagnostic endpoint ───
        console.log('[diag] Step 6: JWT diagnostic');
        const jwtStatusRes = await request.get('/api/admin/jwt-status').catch(() => null);
        if (jwtStatusRes) {
            console.log('[diag] JWT status:', jwtStatusRes.status(), await jwtStatusRes.text().catch(() => 'no body'));
        }

        // Final assertion
        expect(hasAccessToken).toBe(true);
    });
});
