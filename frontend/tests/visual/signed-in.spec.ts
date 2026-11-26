/**
 * Signed-in read-only page checks. This project exists ONLY when
 * VISUAL_AUTH=1 (conditional project in the config, not test.skip), and no
 * workflow sets that flag — manual runs only.
 *
 * Auth: the app has no password login (passwordless email OTP, see
 * tests/e2e/auth-helpers.ts loginWithEmailOtp, which needs the local OTP
 * outbox and cannot run against a deployment). Instead this spec injects the
 * opaque session cookie (name reused from AUTH_SESSION_COOKIE, no edits to
 * the helper) with a value provisioned out-of-band at runtime:
 *
 * - VISUAL_USER_EMAIL: expected session email, asserted against /api/session
 * - VISUAL_SESSION_TOKEN: opaque __Host-regengine_session cookie value
 *
 * Only env var NAMES appear here; values are never committed or logged.
 * Everything is GET-only. Key-like values on screen are masked before any
 * screenshot is taken.
 */
import { expect, test, type Page } from '@playwright/test';
import { AUTH_SESSION_COOKIE } from '../e2e/auth-helpers';
import { screenshotMasks, stabilize } from './helpers';

test.describe.configure({ mode: 'parallel' });

interface SessionResponse {
    authenticated?: boolean;
    user?: { email?: string } | null;
}

/** Collect every >= 400 response URL+status for the failure attachment. */
function watchRequests(page: Page): string[] {
    const bad: string[] = [];
    page.on('response', (response) => {
        if (response.status() >= 400) {
            bad.push(
                `${response.status()} ${response.request().method()} ${response.url()}`.slice(
                    0,
                    300,
                ),
            );
        }
    });
    return bad;
}

async function attachRequests(testInfoTitle: string, bad: string[]): Promise<void> {
    await test.info().attach('failing-requests', {
        body: JSON.stringify({ test: testInfoTitle, failingRequests: bad }, null, 2),
        contentType: 'application/json',
    });
}

/** Mask key/token-like values (leaf elements only) before screenshotting. */
async function maskKeyValues(page: Page): Promise<void> {
    await page.evaluate(() => {
        const patterns = [
            /\bsk_(live|test)_[A-Za-z0-9_-]{4,}/,
            /\bre_[A-Za-z0-9_-]{8,}/,
            /\bapi[_-]?keys?\b\s*[:=]\s*\S+/i,
            /\bbearer\s+[A-Za-z0-9._-]{8,}/i,
            /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/,
        ];
        for (const el of document.querySelectorAll('body *')) {
            if (!(el instanceof HTMLElement)) continue;
            if (el.hasAttribute('data-visual-mask')) continue;
            if (el.children.length > 0) continue;
            const text = (el.textContent || '').trim();
            if (text.length === 0 || text.length > 500) continue;
            if (patterns.some((re) => re.test(text))) {
                el.setAttribute('data-visual-mask', 'secret');
            }
        }
    });
}

test.beforeEach(async ({ page, context }, testInfo) => {
    const email = process.env.VISUAL_USER_EMAIL;
    const token = process.env.VISUAL_SESSION_TOKEN;
    if (!email || !token) {
        throw new Error(
            'signed-in project requires VISUAL_USER_EMAIL and VISUAL_SESSION_TOKEN in the environment',
        );
    }
    const baseURL = testInfo.project.use.baseURL ?? 'https://regengine.co';
    // __Host- cookies: Secure + Path=/, no Domain — hence the url form.
    await context.addCookies([
        {
            name: AUTH_SESSION_COOKIE,
            value: token,
            url: baseURL,
            path: '/',
            httpOnly: true,
            secure: true,
            sameSite: 'Lax',
        },
    ]);
    await expect
        .poll(
            async () => {
                const response = await page.request.get('/api/session');
                if (!response.ok()) return '';
                const body = (await response.json()) as SessionResponse;
                return body.authenticated === true ? (body.user?.email ?? '') : '';
            },
            { message: 'opaque session hydrates', timeout: 15_000 },
        )
        .toBe(email);
});

test('non-admin is blocked from /sysadmin', async ({ page }, testInfo) => {
    const bad = watchRequests(page);
    await page.goto('/sysadmin', { waitUntil: 'domcontentloaded' });
    // Non-sysadmin sessions always end on /dashboard, via one of two paths:
    // - JWT/Supabase sessions: proxy.ts requireAppAuth() redirects to
    //   /dashboard (src/proxy.ts:276, :435, :446).
    // - Opaque __Host-regengine_session (what this spec injects): proxy.ts
    //   Strategy 1 passes through with no sysadmin check (src/proxy.ts:244),
    //   then SysAdminDashboard pushes /login for !user?.is_sysadmin
    //   (src/app/sysadmin/page.tsx:73-77), and the login page forwards the
    //   still-authenticated user to safeNextPath(null) = /dashboard
    //   (src/app/login/PasswordlessEntryClient.tsx:46-54).
    await expect
        .poll(() => new URL(page.url()).pathname, {
            message: 'non-admin /sysadmin visit lands on /dashboard',
            timeout: 15_000,
        })
        .toBe('/dashboard');
    await attachRequests(testInfo.title, bad);
});

test('non-admin is blocked from /admin', async ({ page }, testInfo) => {
    const bad = watchRequests(page);
    await page.goto('/admin', { waitUntil: 'domcontentloaded' });
    // /admin has no proxy-level denial: non-high-assurance sessions stay on
    // the page and see the exact denial card below (src/app/admin/page.tsx:
    // canManageKeys at :42 requires is_sysadmin + WebAuthn/SSO; denial card
    // at :142-169).
    await expect(page).toHaveURL(/\/admin\/?$/);
    await expect(page.getByText('High-assurance sign-in required')).toBeVisible();
    await expect(
        page.getByText('Live credential management requires a WebAuthn or SSO sysadmin session.'),
    ).toBeVisible();
    await attachRequests(testInfo.title, bad);
});

const SURFACES = [
    { name: 'Products', route: '/dashboard/products' },
    { name: 'Compliance', route: '/dashboard/compliance' },
    { name: 'Integrations', route: '/dashboard/integrations' },
    // No standalone billing page exists (only /api/billing/checkout); the
    // billing section lives in dashboard settings (src/app/dashboard/settings).
    { name: 'Billing', route: '/dashboard/settings' },
] as const;

for (const surface of SURFACES) {
    test(`signed-in surface loads: ${surface.name}`, async ({ page }, testInfo) => {
        const bad = watchRequests(page);
        const pageErrors: string[] = [];
        page.on('pageerror', (error) => pageErrors.push(String(error).slice(0, 500)));
        await stabilize(page, surface.route);
        const text = (await page.locator('body').innerText()).trim();
        expect(text.length, `${surface.route}: empty page`).toBeGreaterThanOrEqual(20);
        expect(pageErrors, `${surface.route}: page errors`).toEqual([]);
        await maskKeyValues(page);
        await expect(page).toHaveScreenshot(
            `signed-in__${surface.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.png`,
            { mask: screenshotMasks(page) },
        );
        await attachRequests(testInfo.title, bad);
    });
}
