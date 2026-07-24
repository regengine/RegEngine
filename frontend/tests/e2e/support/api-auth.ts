import { expect, type BrowserContext, type APIRequestContext } from '@playwright/test';
import { waitForOtp } from '../auth-helpers';

type SessionUser = {
    id: string;
    email: string;
    is_sysadmin?: boolean;
    status?: string;
    role_name?: string | null;
    organization_id?: string | null;
    auth_method?: string;
    permissions?: string[];
};

type HydratedSession = {
    authenticated: boolean;
    auth_method?: string | null;
    tenant_id?: string | null;
    user?: SessionUser | null;
};

export type ApiSession = {
    tenant_id: string;
    auth_method: string;
    user: SessionUser;
    apiKey?: string;
};

function localApiKey(): string | undefined {
    if (process.env.API_KEY) return process.env.API_KEY;
    if (process.env.REGENGINE_API_KEY) return process.env.REGENGINE_API_KEY;
    if (!process.env.PLAYWRIGHT_BASE_URL) return 'playwright-local-regengine-api-key-2026';
    return undefined;
}

function baseOrigin(): string {
    return new URL(process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001').origin;
}

export async function csrfHeader(context: BrowserContext): Promise<Record<string, string>> {
    const cookies = await context.cookies();
    const csrf = cookies.find(cookie => cookie.name === 're_csrf')?.value;
    return csrf ? { 'x-csrf-token': csrf } : {};
}

/**
 * API-level passwordless login (email OTP).
 *
 * The app has no password login (POST /api/admin/auth/login is gone). This
 * drives the challenge ceremony over the same proxied endpoints the login UI
 * uses: POST /api/admin/auth/challenges issues a challenge (and a
 * browser-binding nonce cookie), the backend writes the sign-in code to the
 * Playwright OTP outbox (REGENGINE_E2E_MODE=true only), and the verify call
 * sets the opaque __Host-regengine_session cookie. GET /api/session then
 * hydrates tenant/user context from /auth/me.
 *
 * Local stack only — see hasPasswordlessE2E in auth-prereqs.ts.
 */
export async function loginViaApi(
    context: BrowserContext,
    email = process.env.TEST_USER_EMAIL || '',
): Promise<ApiSession> {
    expect(email, 'E2E login email is configured').toBeTruthy();

    // Bootstrap the CSRF double-submit cookies before any mutating request.
    await context.request.get('/api/session');

    const challenge = await context.request.post('/api/admin/auth/challenges', {
        data: { email },
    });
    expect(challenge.ok(), await challenge.text()).toBeTruthy();
    const challengePayload = await challenge.json() as { challenge_id?: string };
    expect(challengePayload.challenge_id, 'challenge create returns a challenge_id').toBeTruthy();
    const challengeId = String(challengePayload.challenge_id);

    const code = await waitForOtp(email, challengeId);

    const verify = await context.request.post(`/api/admin/auth/challenges/${challengeId}/verify`, {
        data: { code },
    });
    expect(verify.ok(), await verify.text()).toBeTruthy();

    const hydrated = await context.request.get('/api/session');
    expect(hydrated.ok()).toBeTruthy();
    const session = await hydrated.json() as HydratedSession;
    expect(session.authenticated, 'passwordless session hydrates as authenticated').toBe(true);
    expect(session.auth_method).toBe('email_otp');
    expect(session.tenant_id, 'passwordless session resolves a tenant_id').toBeTruthy();
    expect(session.user?.email).toBe(email.toLowerCase());

    const apiKey = localApiKey();
    if (apiKey) {
        const response = await context.request.post('/api/session', {
            headers: {
                'Content-Type': 'application/json',
                Origin: baseOrigin(),
                ...(await csrfHeader(context)),
            },
            data: {
                api_key: apiKey,
                tenant_id: session.tenant_id,
            },
        });
        expect(response.ok(), await response.text()).toBeTruthy();
    }

    return {
        tenant_id: String(session.tenant_id),
        auth_method: 'email_otp',
        user: session.user as SessionUser,
        apiKey,
    };
}

export async function logoutViaApi(context: BrowserContext): Promise<void> {
    await context.request.get('/api/session');
    await context.request.delete('/api/session', {
        headers: await csrfHeader(context),
    });
}

export async function expectOk(response: Awaited<ReturnType<APIRequestContext['get']>>): Promise<void> {
    expect(response.ok(), await response.text()).toBeTruthy();
}
