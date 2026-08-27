/**
 * #2806 — the first-party service proxy must bind the injected backend master
 * key to a SERVER-derived tenant, never to the client-writable `re_tenant_id`
 * cookie.
 *
 * `POST /api/session` deliberately sets `re_tenant_id` with `httpOnly: false`
 * (`app/api/session/route.ts`), so any script on an allowed origin can
 * overwrite it with `document.cookie` — and a non-browser client can simply
 * replay its own session cookie with any tenant it likes.
 *
 * For JWT callers this is already defended: `validateProxySession`
 * (`lib/api-proxy.ts`) cross-checks the `re_access_token` `tenant_id` claim
 * against `re_tenant_id` and 403s on mismatch.
 *
 * For OPAQUE `__Host-regengine_session` callers (SSO / passkey / email-OTP)
 * there was no such check: `validateProxySession` returns `null` immediately,
 * and `applyFirstPartyServiceCredentials` then attached
 * `REGENGINE_API_KEY` — the backend master key, which
 * `services/ingestion/app/authz.py` maps to a `scopes=["*"]` principal for
 * WHATEVER tenant the header names — alongside the forged tenant id.
 *
 * These tests exercise the two production entry points that reach
 * `applyFirstPartyServiceCredentials`: the ingestion catch-all
 * (`prepareHeaders` → `applyInflowWorkbenchReadCredentials`) and
 * `POST /api/nlp/ask`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

import { applyInflowWorkbenchReadCredentials } from '@/lib/inflow-workbench-proxy';
import { applyFirstPartyServiceCredentials, applyCookieCredentials } from '@/lib/proxy-factory';
import { POST as NLP_ASK_POST } from '@/app/api/nlp/ask/route';

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(),
}));

/** Tenant the attacker's opaque session actually belongs to (per /auth/me). */
const ATTACKER_TENANT = '11111111-1111-4111-8111-111111111111';
/** Victim tenant the attacker forges into the non-httpOnly cookie. */
const VICTIM_TENANT = '22222222-2222-4222-8222-222222222222';

/** Synthetic stand-in for REGENGINE_API_KEY — never a real value. */
const SERVER_MASTER_KEY = 'synthetic-master-key-for-tests'; // pragma: allowlist secret

/** Any ingestion path other than the one readiness route that already resolves
 *  the tenant server-side — i.e. the fall-through to the first-party key. */
const INGEST_PATH = 'api/v1/ingest/events';

const ORIGINAL = {
    REGENGINE_API_KEY: process.env.REGENGINE_API_KEY,
    NEXT_PUBLIC_ADMIN_URL: process.env.NEXT_PUBLIC_ADMIN_URL,
    NLP_SERVICE_URL: process.env.NLP_SERVICE_URL,
    EXPERIMENTAL: process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES,
};

function restoreEnv(): void {
    const map: Record<string, string | undefined> = {
        REGENGINE_API_KEY: ORIGINAL.REGENGINE_API_KEY,
        NEXT_PUBLIC_ADMIN_URL: ORIGINAL.NEXT_PUBLIC_ADMIN_URL,
        NLP_SERVICE_URL: ORIGINAL.NLP_SERVICE_URL,
        NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES: ORIGINAL.EXPERIMENTAL,
    };
    for (const [key, value] of Object.entries(map)) {
        if (value === undefined) delete process.env[key];
        else process.env[key] = value;
    }
}

function makeRequest(options: {
    url?: string;
    cookies?: Record<string, string>;
    headers?: Record<string, string>;
    jsonBody?: unknown;
} = {}): NextRequest {
    const cookies = options.cookies ?? {};
    return {
        url: options.url ?? `https://www.regengine.co/api/ingestion/${INGEST_PATH}`,
        headers: new Headers(options.headers ?? {}),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
        json: async () => options.jsonBody ?? { query: 'where did lot 42 ship?' },
    } as unknown as NextRequest;
}

function authMeResponse(tenantId: string): Response {
    return new Response(
        JSON.stringify({
            user_id: '33333333-3333-4333-8333-333333333333',
            email: 'member@example.com',
            tenant_id: tenantId,
            organization_id: tenantId,
            role: 'member',
            auth_method: 'webauthn',
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
    );
}

/** fetch stub that answers /auth/me and records every other (upstream) call. */
function stubFetch(authMe: Response | (() => Response)): ReturnType<typeof vi.fn> {
    const mock = vi.fn(async (input: unknown) => {
        const url = typeof input === 'string' ? input : String((input as { url?: string })?.url ?? '');
        if (url.includes('/auth/me')) {
            return typeof authMe === 'function' ? authMe() : authMe.clone();
        }
        return new Response(JSON.stringify({ answer: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        });
    });
    vi.stubGlobal('fetch', mock);
    return mock as unknown as ReturnType<typeof vi.fn>;
}

beforeEach(() => {
    vi.clearAllMocks();
    process.env.REGENGINE_API_KEY = SERVER_MASTER_KEY;
    process.env.NEXT_PUBLIC_ADMIN_URL = 'https://admin.example.com';
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    restoreEnv();
});

describe('#2806 — opaque-session callers cannot forge the tenant the master key is bound to', () => {
    it('rejects a forged re_tenant_id on the ingestion catch-all instead of injecting the master key', async () => {
        // Attacker: legitimate low-privilege member of ATTACKER_TENANT holding
        // only an opaque session. They overwrite the non-httpOnly re_tenant_id
        // cookie with the victim tenant and call any ingestion path.
        stubFetch(authMeResponse(ATTACKER_TENANT));

        const request = makeRequest({
            headers: { origin: 'https://www.regengine.co' },
            cookies: {
                '__Host-regengine_session': 'opaque-session-token',
                re_tenant_id: VICTIM_TENANT,
            },
        });

        const headers = new Headers();
        applyCookieCredentials(headers, request);
        const error = await applyInflowWorkbenchReadCredentials(headers, request, INGEST_PATH);

        // Pre-fix this was `null` with the master key attached to VICTIM_TENANT.
        expect(headers.get('x-regengine-api-key')).not.toBe(SERVER_MASTER_KEY);
        expect(headers.get('x-tenant-id')).not.toBe(VICTIM_TENANT);
        expect(error?.status).toBe(403);
        await expect(error?.json()).resolves.toMatchObject({
            code: 'TENANT_CONTEXT_MISMATCH',
        });
    });

    it('still serves an opaque-session caller requesting its own tenant', async () => {
        stubFetch(authMeResponse(ATTACKER_TENANT));

        const request = makeRequest({
            headers: { origin: 'https://www.regengine.co' },
            cookies: {
                '__Host-regengine_session': 'opaque-session-token',
                re_tenant_id: ATTACKER_TENANT,
            },
        });

        const headers = new Headers();
        applyCookieCredentials(headers, request);
        const error = await applyInflowWorkbenchReadCredentials(headers, request, INGEST_PATH);

        expect(error).toBeNull();
        expect(headers.get('x-regengine-api-key')).toBe(SERVER_MASTER_KEY);
        expect(headers.get('x-tenant-id')).toBe(ATTACKER_TENANT);
    });

    it('fails closed when the backend cannot resolve the opaque session', async () => {
        stubFetch(() => new Response(null, { status: 401 }));

        const request = makeRequest({
            headers: { origin: 'https://www.regengine.co' },
            cookies: {
                '__Host-regengine_session': 'expired-session-token',
                re_tenant_id: VICTIM_TENANT,
            },
        });

        const headers = new Headers();
        applyCookieCredentials(headers, request);
        const error = await applyInflowWorkbenchReadCredentials(headers, request, INGEST_PATH);

        expect(headers.has('x-regengine-api-key')).toBe(false);
        expect(error?.status).toBe(403);
    });

    it('leaks nothing through /api/nlp/ask when the tenant cookie is forged', async () => {
        process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES = 'true';
        process.env.NLP_SERVICE_URL = 'http://nlp.test';
        const fetchMock = stubFetch(authMeResponse(ATTACKER_TENANT));

        const response = await NLP_ASK_POST(
            makeRequest({
                url: 'https://www.regengine.co/api/nlp/ask',
                headers: { origin: 'https://www.regengine.co' },
                cookies: {
                    '__Host-regengine_session': 'opaque-session-token',
                    re_tenant_id: VICTIM_TENANT,
                },
                jsonBody: { query: 'list every lot for this tenant' },
            }),
        );

        const upstreamCalls = fetchMock.mock.calls.filter(
            ([input]: unknown[]) => !String(input).includes('/auth/me'),
        );
        // Pre-fix: one upstream call carrying the master key + VICTIM_TENANT.
        expect(upstreamCalls).toHaveLength(0);
        expect(response.status).toBe(403);
    });

    it('does not require a server round-trip for API-key or JWT callers', async () => {
        // The JWT branch is already cross-checked by validateProxySession, and
        // direct API-key callers keep their own key. Neither should start
        // paying an /auth/me hop because of this fix.
        const fetchMock = stubFetch(authMeResponse(ATTACKER_TENANT));

        const headers = new Headers();
        const request = makeRequest({
            cookies: { re_access_token: 'opaque-jwt-material', re_tenant_id: VICTIM_TENANT },
        });
        applyCookieCredentials(headers, request);
        const error = applyFirstPartyServiceCredentials(headers, request);

        expect(error).toBeNull();
        expect(headers.get('x-regengine-api-key')).toBe(SERVER_MASTER_KEY);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('fails closed when a route forgets to resolve the opaque session tenant', async () => {
        // Structural guard: the sync helper must not silently trust the cookie
        // just because its caller skipped the server-side resolution step.
        const headers = new Headers();
        const request = makeRequest({
            headers: { origin: 'https://www.regengine.co' },
            cookies: {
                '__Host-regengine_session': 'opaque-session-token',
                re_tenant_id: VICTIM_TENANT,
            },
        });
        applyCookieCredentials(headers, request);
        const error = applyFirstPartyServiceCredentials(headers, request);

        expect(headers.has('x-regengine-api-key')).toBe(false);
        expect(error?.status).toBe(403);
    });
});
