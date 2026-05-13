import { expect, type BrowserContext, type APIRequestContext } from '@playwright/test';

type LoginResponse = {
    access_token: string;
    tenant_id: string | null;
    user: {
        id: string;
        email: string;
        is_sysadmin?: boolean;
        status?: string;
        role_id?: string | null;
        role_name?: string | null;
        permissions?: string[];
    };
};

export type ApiSession = LoginResponse & {
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

export async function loginViaApi(
    context: BrowserContext,
    email = process.env.TEST_ADMIN_EMAIL || process.env.TEST_USER_EMAIL || '',
    password = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_PASSWORD || '',
    options: { remember?: boolean } = {},
): Promise<ApiSession> {
    expect(email, 'E2E login email is configured').toBeTruthy();
    expect(password, 'E2E login password is configured').toBeTruthy();

    const login = await context.request.post('/api/admin/auth/login', {
        data: { email, password },
    });
    expect(login.ok(), await login.text()).toBeTruthy();
    const payload = await login.json() as LoginResponse;
    expect(payload.access_token).toBeTruthy();
    expect(payload.tenant_id).toBeTruthy();

    await context.request.get('/api/session');
    const apiKey = localApiKey();
    const session = await context.request.post('/api/session', {
        headers: {
            'Content-Type': 'application/json',
            Origin: baseOrigin(),
            ...(await csrfHeader(context)),
        },
        data: {
            access_token: payload.access_token,
            api_key: apiKey,
            tenant_id: payload.tenant_id,
            user: payload.user,
            remember_me: options.remember ?? true,
        },
    });
    expect(session.ok(), await session.text()).toBeTruthy();

    const hydrated = await context.request.get('/api/session');
    expect(hydrated.ok()).toBeTruthy();
    const hydratedPayload = await hydrated.json() as { authenticated: boolean; tenant_id?: string };
    expect(hydratedPayload.authenticated).toBe(true);
    expect(hydratedPayload.tenant_id).toBe(String(payload.tenant_id));

    return { ...payload, apiKey };
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
