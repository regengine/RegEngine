/**
 * Proxy sanitization tests.
 *
 * Covers the path-segment validators used by all catch-all and named-segment
 * proxy routes under src/app/api/**. These helpers sit between user input
 * (the dynamic segments of the proxy URL) and the backend fetch — a bug here
 * is a direct path-traversal / injection to the backend, so regressions must
 * be caught at unit-test time.
 *
 * Related fixes:
 *   #1152 — controls proxy skipped path sanitization
 *   #1152-follow-on — UUID validation on [tenantId]/[snapshotId] routes
 */

import { afterEach, describe, it, expect, vi } from 'vitest';
import { createHmac } from 'node:crypto';
import { createServerClient } from '@supabase/ssr';
import { requireAdminCapability, requireProxyAuth, sanitizePath, validateProxySession, validateUuid, safeSegment, hasSupabaseSessionCookies } from '@/lib/api-proxy';
import { applyCookieCredentials, applyFirstPartyServiceCredentials, createStreamProxy, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { _resetForTesting as resetJwtKeysForTesting } from '@/lib/jwt-keys';
import type { NextRequest } from 'next/server';

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(),
}));

const ORIGINAL_REGENGINE_API_KEY = process.env.REGENGINE_API_KEY;
const ORIGINAL_API_KEY = process.env.API_KEY;
const ORIGINAL_JWT_SIGNING_KEY = process.env.JWT_SIGNING_KEY;
const ORIGINAL_AUTH_SECRET_KEY = process.env.AUTH_SECRET_KEY;
const ORIGINAL_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

afterEach(() => {
    if (ORIGINAL_REGENGINE_API_KEY === undefined) {
        delete process.env.REGENGINE_API_KEY;
    } else {
        process.env.REGENGINE_API_KEY = ORIGINAL_REGENGINE_API_KEY;
    }
    if (ORIGINAL_API_KEY === undefined) {
        delete process.env.API_KEY;
    } else {
        process.env.API_KEY = ORIGINAL_API_KEY;
    }
    if (ORIGINAL_JWT_SIGNING_KEY === undefined) {
        delete process.env.JWT_SIGNING_KEY;
    } else {
        process.env.JWT_SIGNING_KEY = ORIGINAL_JWT_SIGNING_KEY;
    }
    if (ORIGINAL_AUTH_SECRET_KEY === undefined) {
        delete process.env.AUTH_SECRET_KEY;
    } else {
        process.env.AUTH_SECRET_KEY = ORIGINAL_AUTH_SECRET_KEY;
    }
    if (ORIGINAL_SUPABASE_URL === undefined) {
        delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    } else {
        process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_SUPABASE_URL;
    }
    if (ORIGINAL_SUPABASE_KEY === undefined) {
        delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    } else {
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ORIGINAL_SUPABASE_KEY;
    }
    vi.mocked(createServerClient).mockReset();
    resetJwtKeysForTesting();
});

function makeProxyRequest(
    headers: Record<string, string>,
    cookies: Record<string, string> = {},
    url = 'http://localhost/api/proxy',
): NextRequest {
    return {
        url,
        headers: new Headers(headers),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
    } as unknown as NextRequest;
}

function base64url(value: string): string {
    return Buffer.from(value, 'utf8').toString('base64url');
}

function primeJwtEnv(secret: string): void {
    process.env.JWT_SIGNING_KEY = secret;
    process.env.AUTH_SECRET_KEY = secret;
    resetJwtKeysForTesting();
}

function primeJwtMigrationEnv({
    jwtSecret,
    legacyAuthSecret,
}: {
    jwtSecret: string;
    legacyAuthSecret: string;
}): void {
    process.env.JWT_SIGNING_KEY = jwtSecret;
    process.env.AUTH_SECRET_KEY = legacyAuthSecret;
    delete process.env.JWT_PREVIOUS_KEY;
    resetJwtKeysForTesting();
}

describe('requireProxyAuth', () => {
    it('does not treat REGENGINE_API_KEY as a caller credential', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret

        const response = requireProxyAuth(makeProxyRequest({}));

        expect(response?.status).toBe(401);
    });

    it('does not treat cookie-managed placeholders as caller credentials', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret

        const response = requireProxyAuth(makeProxyRequest(
            {
                authorization: 'Bearer cookie-managed',
                'x-regengine-api-key': 'cookie-managed',
                'x-admin-key': 'cookie-managed',
                'x-api-key': 'cookie-managed',
            },
            {
                re_access_token: 'cookie-managed',
                ['re_api_' + 'key']: 'cookie-managed',
                re_admin_key: 'cookie-managed',
            },
        ));

        expect(response?.status).toBe(401);
    });

    it('allows real caller credentials from cookies or headers', () => {
        expect(requireProxyAuth(makeProxyRequest({}, { re_access_token: 'real-token' }))).toBeNull();
        expect(requireProxyAuth(makeProxyRequest({ authorization: 'Bearer real-token' }))).toBeNull();
        expect(requireProxyAuth(makeProxyRequest({ 'x-regengine-api-key': 'real-api-key' }))).toBeNull();
    });

    it('detects Supabase cookies without treating them as raw caller credentials', () => {
        const request = makeProxyRequest({}, { 'sb-test-auth-token': 'supabase-cookie' });

        expect(requireProxyAuth(request)?.status).toBe(401);
        expect(hasSupabaseSessionCookies(request)).toBe(true);
    });
});

describe('requireAdminCapability', () => {
    it('rejects authenticated callers without admin capability', () => {
        const response = requireAdminCapability(
            makeProxyRequest(
                {},
                {
                    re_access_token: 'real-token',
                    re_user: JSON.stringify({
                        id: 'user-1',
                        email: 'member@example.com',
                        is_sysadmin: false,
                        role_name: 'member',
                        status: 'active',
                    }),
                },
            ),
        );

        expect(response?.status).toBe(403);
    });

    it('allows sysadmin and owner/admin sessions or explicit admin keys', () => {
        expect(
            requireAdminCapability(
                makeProxyRequest(
                    {},
                    {
                        re_access_token: 'real-token',
                        re_user: JSON.stringify({
                            id: 'user-1',
                            email: 'owner@example.com',
                            is_sysadmin: false,
                            role_name: 'owner',
                            status: 'active',
                        }),
                    },
                ),
            ),
        ).toBeNull();

        expect(
            requireAdminCapability(
                makeProxyRequest({}, { re_admin_key: 'real-admin-key' }),
            ),
        ).toBeNull();
    });
});

describe('sanitizePath (catch-all [...path] proxies)', () => {
    it('joins valid path segments with slashes', () => {
        expect(sanitizePath(['api', 'v1', 'compliance'])).toBe('api/v1/compliance');
    });

    it('accepts alphanumeric, hyphen, underscore, dot, and slash', () => {
        expect(sanitizePath(['my-tenant_1.0', 'endpoint'])).toBe('my-tenant_1.0/endpoint');
    });

    it('rejects empty input', () => {
        expect(sanitizePath([])).toBeNull();
    });

    it('rejects traversal attempts with ../', () => {
        expect(sanitizePath(['..', 'admin', 'key'])).toBeNull();
        expect(sanitizePath(['foo', '..', 'bar'])).toBeNull();
    });

    it('rejects null-byte injection', () => {
        expect(sanitizePath(['foo\0bar'])).toBeNull();
    });

    it('rejects path segments with disallowed chars', () => {
        expect(sanitizePath(['foo bar'])).toBeNull();     // space
        expect(sanitizePath(['foo?bar'])).toBeNull();     // query injection
        expect(sanitizePath(['foo#bar'])).toBeNull();     // fragment injection
        expect(sanitizePath(['foo<script>'])).toBeNull(); // angle brackets
        expect(sanitizePath(['foo%2e%2e'])).toBeNull();   // % is not allowed
        expect(sanitizePath(['foo;bar'])).toBeNull();     // shell metachar
    });
});

describe('validateUuid (named [tenantId]/[snapshotId] proxies)', () => {
    it('accepts lowercase UUID v4', () => {
        const u = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';
        expect(validateUuid(u)).toBe(u);
    });

    it('normalizes uppercase UUIDs to lowercase', () => {
        expect(validateUuid('6BA7B810-9DAD-41D1-A0B4-00C04FD430C8')).toBe(
            '6ba7b810-9dad-41d1-a0b4-00c04fd430c8',
        );
    });

    it('rejects path-traversal payloads', () => {
        expect(validateUuid('../admin/key')).toBeNull();
        expect(validateUuid('..%2fadmin')).toBeNull();
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c8/../admin')).toBeNull();
    });

    it('rejects malformed UUIDs', () => {
        expect(validateUuid('not-a-uuid')).toBeNull();
        expect(validateUuid('')).toBeNull();
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c')).toBeNull();   // too short
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c8X')).toBeNull(); // extra char
    });

    it('rejects null and undefined', () => {
        expect(validateUuid(null)).toBeNull();
        expect(validateUuid(undefined)).toBeNull();
    });

    it('rejects the nil UUID (v0) — not a real tenant', () => {
        expect(validateUuid('00000000-0000-0000-0000-000000000000')).toBeNull();
    });

    it('rejects UUIDs with injected control chars', () => {
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c8\r\n')).toBeNull();
    });
});

describe('safeSegment (general-purpose path segment encoder)', () => {
    it('encodes a plain segment unchanged', () => {
        expect(safeSegment('hello')).toBe('hello');
    });

    it('percent-encodes reserved chars', () => {
        expect(safeSegment('hello world')).toBe('hello%20world');
        expect(safeSegment('foo@bar.com')).toBe('foo%40bar.com');
    });

    it('rejects path separators', () => {
        expect(safeSegment('foo/bar')).toBeNull();
        expect(safeSegment('foo\\bar')).toBeNull();
    });

    it('rejects dot-dot traversal', () => {
        expect(safeSegment('..')).toBeNull();
        expect(safeSegment('.')).toBeNull();
    });

    it('rejects null byte and control chars', () => {
        expect(safeSegment('foo\0bar')).toBeNull();
        expect(safeSegment('foo\nbar')).toBeNull();
    });

    it('rejects oversized input', () => {
        expect(safeSegment('a'.repeat(257))).toBeNull();
    });

    it('rejects null/undefined', () => {
        expect(safeSegment(null)).toBeNull();
        expect(safeSegment(undefined)).toBeNull();
        expect(safeSegment('')).toBeNull();
    });
});

describe('URL shape: forwarded URLs for malicious input should not include the attack', () => {
    // These assertions document the intended behavior: the proxy builds the
    // upstream URL only after validation, so a malicious input never reaches
    // the fetch() call. We simulate the proxy's decision by running
    // validateUuid and asserting nothing survives that could escape the path.
    const maliciousInputs = [
        '../../admin/key',
        '../../../etc/passwd',
        'valid-looking-6ba7b810-9dad-41d1-a0b4-00c04fd430c8/../admin',
        '%2e%2e%2fadmin',
        'foo?tenant=other',
    ];

    for (const input of maliciousInputs) {
        it(`blocks "${input}"`, () => {
            expect(validateUuid(input)).toBeNull();
        });
    }

    it('forwards a valid UUID as-is (no injection in interpolation)', () => {
        const u = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';
        const validated = validateUuid(u);
        const forwardedUrl = `https://api.example.com/v1/compliance/snapshots/${validated}`;
        expect(forwardedUrl).toBe(
            'https://api.example.com/v1/compliance/snapshots/6ba7b810-9dad-41d1-a0b4-00c04fd430c8',
        );
    });
});

describe('cookie-managed credential passthrough', () => {
    it('does not forward placeholder credentials from client headers', () => {
        const outgoing = new Headers();
        const request = makeProxyRequest({
            authorization: 'Bearer cookie-managed',
            'x-regengine-api-key': 'cookie-managed',
            'x-admin-key': 'cookie-managed',
            'x-tenant-id': 'tenant-123',
        });

        passthroughRequestHeaders(outgoing, request, [
            'authorization',
            'x-regengine-api-key',
            'x-admin-key',
            'x-tenant-id',
        ]);

        expect(outgoing.has('authorization')).toBe(false);
        expect(outgoing.has('x-regengine-api-key')).toBe(false);
        expect(outgoing.has('x-admin-key')).toBe(false);
        expect(outgoing.get('x-tenant-id')).toBe('tenant-123');
    });

    it('overrides placeholder auth with HTTP-only cookie credentials', () => {
        const outgoing = new Headers({
            authorization: 'Bearer cookie-managed',
            'x-regengine-api-key': 'cookie-managed',
            'x-admin-key': 'cookie-managed',
        });
        const request = makeProxyRequest(
            { authorization: 'Bearer cookie-managed' },
            {
                re_access_token: 'real-token',
                re_api_key: 'real-api-key', // pragma: allowlist secret
                re_admin_key: 'real-admin-key', // pragma: allowlist secret
            },
        );

        applyCookieCredentials(outgoing, request, { respectExistingAuthHeader: true });

        expect(outgoing.get('authorization')).toBe('Bearer real-token');
        expect(outgoing.get('x-regengine-api-key')).toBe('real-api-key');
        expect(outgoing.get('x-admin-key')).toBe('real-admin-key');
    });

    it('does not inject the server API key without a real caller credential', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers();
        const request = makeProxyRequest({});

        applyCookieCredentials(outgoing, request);

        expect(outgoing.has('x-regengine-api-key')).toBe(false);
    });

    it('keeps cookie credential injection separate from server API key injection', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers();
        const request = makeProxyRequest({}, { re_access_token: 'real-token' });

        applyCookieCredentials(outgoing, request);

        expect(outgoing.get('authorization')).toBe('Bearer real-token');
        expect(outgoing.has('x-regengine-api-key')).toBe(false);
    });

    it('injects a server API key for first-party service calls with a valid tenant cookie', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers();
        const request = makeProxyRequest(
            {},
            {
                re_access_token: 'real-token',
                re_tenant_id: '11111111-1111-4111-8111-111111111111',
            },
        );

        applyCookieCredentials(outgoing, request);
        const error = applyFirstPartyServiceCredentials(outgoing, request);

        expect(error).toBeNull();
        expect(outgoing.get('authorization')).toBe('Bearer real-token');
        expect(outgoing.get('x-regengine-api-key')).toBe('server-side-key');
        expect(outgoing.get('x-tenant-id')).toBe('11111111-1111-4111-8111-111111111111');
    });

    it('accepts the built-in system tenant context for first-party service calls', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers();
        const request = makeProxyRequest(
            {},
            {
                re_access_token: 'real-token',
                re_tenant_id: '00000000-0000-0000-0000-000000000001',
            },
        );

        applyCookieCredentials(outgoing, request);
        const error = applyFirstPartyServiceCredentials(outgoing, request);

        expect(error).toBeNull();
        expect(outgoing.get('x-regengine-api-key')).toBe('server-side-key');
        expect(outgoing.get('x-tenant-id')).toBe('00000000-0000-0000-0000-000000000001');
    });

    it('injects a server API key with a valid backend-provided tenant header', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers({
            'x-tenant-id': '22222222-2222-4222-8222-222222222222',
        });
        const request = makeProxyRequest({}, { re_access_token: 'real-token' });

        applyCookieCredentials(outgoing, request);
        const error = applyFirstPartyServiceCredentials(outgoing, request);

        expect(error).toBeNull();
        expect(outgoing.get('x-regengine-api-key')).toBe('server-side-key');
        expect(outgoing.get('x-tenant-id')).toBe('22222222-2222-4222-8222-222222222222');
    });

    it('does not overwrite a real direct client API key during first-party service injection', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers({
            'x-regengine-api-key': 'caller-api-key',
            'x-tenant-id': '33333333-3333-4333-8333-333333333333',
        });
        const request = makeProxyRequest({}, { re_access_token: 'real-token' });

        const error = applyFirstPartyServiceCredentials(outgoing, request);

        expect(error).toBeNull();
        expect(outgoing.get('x-regengine-api-key')).toBe('caller-api-key');
        expect(outgoing.get('x-tenant-id')).toBe('33333333-3333-4333-8333-333333333333');
    });

    it('overwrites browser-provided API keys with the server key for first-party calls', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers({
            'x-regengine-api-key': 'browser-visible-key',
            'x-tenant-id': '33333333-3333-4333-8333-333333333333',
        });
        const request = makeProxyRequest(
            {
                origin: 'https://regengine.co',
                'x-regengine-api-key': 'browser-visible-key',
            },
            {
                re_access_token: 'real-token',
                re_tenant_id: '11111111-1111-4111-8111-111111111111',
            },
        );

        applyCookieCredentials(outgoing, request);
        const error = applyFirstPartyServiceCredentials(outgoing, request);

        expect(error).toBeNull();
        expect(outgoing.get('x-regengine-api-key')).toBe('server-side-key');
        expect(outgoing.get('x-tenant-id')).toBe('11111111-1111-4111-8111-111111111111');
    });

    it('fails closed when server API key injection lacks tenant context', async () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers();
        const request = makeProxyRequest({}, { re_access_token: 'real-token' });

        applyCookieCredentials(outgoing, request);
        const error = applyFirstPartyServiceCredentials(outgoing, request);

        expect(error?.status).toBe(401);
        await expect(error?.json()).resolves.toMatchObject({
            code: 'TENANT_CONTEXT_REQUIRED',
        });
        expect(outgoing.has('x-regengine-api-key')).toBe(false);
    });

    it('fails closed without forwarding the server API key when tenant cookie is invalid', async () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers();
        const request = makeProxyRequest(
            {},
            {
                re_access_token: 'real-token',
                re_tenant_id: '../tenant',
            },
        );

        applyCookieCredentials(outgoing, request);
        const error = applyFirstPartyServiceCredentials(outgoing, request);

        expect(error?.status).toBe(401);
        await expect(error?.json()).resolves.toMatchObject({
            code: 'TENANT_CONTEXT_REQUIRED',
        });
        expect(outgoing.has('x-regengine-api-key')).toBe(false);
    });

    it('prefers the tenant cookie over browser-provided tenant headers', () => {
        const outgoing = new Headers({ 'x-tenant-id': 'browser-tenant' });
        const request = makeProxyRequest(
            { origin: 'https://regengine.co', 'x-tenant-id': 'browser-tenant' },
            { re_access_token: 'real-token', re_tenant_id: 'cookie-tenant' },
        );

        applyCookieCredentials(outgoing, request);

        expect(outgoing.get('x-tenant-id')).toBe('cookie-tenant');
    });

    it('drops browser-provided tenant headers when no tenant cookie is present', () => {
        const outgoing = new Headers({ 'x-tenant-id': 'browser-tenant' });
        const request = makeProxyRequest(
            { origin: 'https://regengine.co', 'x-tenant-id': 'browser-tenant' },
            { re_access_token: 'real-token' },
        );

        applyCookieCredentials(outgoing, request);

        expect(outgoing.has('x-tenant-id')).toBe(false);
    });
});

describe('validateProxySession RegEngine JWT hardening', () => {
    const testSigningMaterial = 'frontend-session-validation-material';

    async function signToken(payload: Record<string, unknown>) {
        const claims = {
            ...payload,
            exp: Math.floor(Date.now() / 1000) + 3600,
        };
        const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
        const body = base64url(JSON.stringify(claims));
        const signature = createHmac('sha256', testSigningMaterial)
            .update(`${header}.${body}`)
            .digest('base64url');
        return `${header}.${body}.${signature}`;
    }

    it('rejects forged RegEngine session cookies before proxying', async () => {
        primeJwtEnv(testSigningMaterial);

        const response = await validateProxySession(makeProxyRequest({}, {
            re_access_token: 'not-a-jwt',
            re_tenant_id: 'tenant-a',
        }));

        expect(response?.status).toBe(401);
    });

    it('rejects tenant cookies that do not match the JWT tenant claim', async () => {
        primeJwtEnv(testSigningMaterial);
        const token = await signToken({ tenant_id: 'tenant-a' });

        const response = await validateProxySession(makeProxyRequest({}, {
            re_access_token: token,
            re_tenant_id: 'tenant-b',
        }));

        expect(response?.status).toBe(403);
    });

    it('accepts a valid RegEngine JWT with matching tenant context', async () => {
        primeJwtEnv(testSigningMaterial);
        const token = await signToken({ tenant_id: 'tenant-a' });

        const response = await validateProxySession(makeProxyRequest({}, {
            re_access_token: token,
            re_tenant_id: 'tenant-a',
        }));

        expect(response).toBeNull();
    });

    it('accepts legacy AUTH_SECRET_KEY-signed tokens during JWT_SIGNING_KEY rollout', async () => {
        const rolloutSigningMaterial = 'new-rollout-jwt-material';

        primeJwtMigrationEnv({
            jwtSecret: rolloutSigningMaterial,
            legacyAuthSecret: testSigningMaterial,
        });
        const token = await signToken({ tenant_id: 'tenant-a' });

        const response = await validateProxySession(makeProxyRequest({}, {
            re_access_token: token,
            re_tenant_id: 'tenant-a',
        }));

        expect(response).toBeNull();
    });
});

describe('validateProxySession Supabase fallback', () => {
    function primeSupabaseEnv() {
        process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'test-anon-key'; // pragma: allowlist secret
    }

    it('fails closed when Supabase cookies are the only credential but validation is unavailable', async () => {
        const response = await validateProxySession(
            makeProxyRequest({}, { 'sb-test-auth-token': 'supabase-cookie' }),
            { requireSupabaseSession: true },
        );

        expect(response?.status).toBe(401);
    });

    it('accepts Supabase-only proxy calls after server-side session validation', async () => {
        primeSupabaseEnv();
        vi.mocked(createServerClient).mockReturnValue({
            auth: {
                getUser: vi.fn().mockResolvedValue({
                    data: { user: { id: 'supabase-user' } },
                    error: null,
                }),
            },
        } as unknown as ReturnType<typeof createServerClient>);

        const response = await validateProxySession(
            makeProxyRequest({}, { 'sb-test-auth-token': 'supabase-cookie' }),
            { requireSupabaseSession: true },
        );

        expect(response).toBeNull();
        expect(createServerClient).toHaveBeenCalled();
    });

    it('lets stream proxies reach prepareHeaders after a valid Supabase-only session', async () => {
        primeSupabaseEnv();
        vi.mocked(createServerClient).mockReturnValue({
            auth: {
                getUser: vi.fn().mockResolvedValue({
                    data: { user: { id: 'supabase-user' } },
                    error: null,
                }),
            },
        } as unknown as ReturnType<typeof createServerClient>);
        const prepareHeaders = vi.fn(() => null);
        const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
            new Response(JSON.stringify({ ok: true }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );
        const { GET } = createStreamProxy({
            serviceName: 'test',
            resolveTargetBases: () => ['https://upstream.example'],
            buildHeaders: () => new Headers(),
            prepareHeaders,
        });

        const response = await GET!(
            makeProxyRequest({}, { 'sb-test-auth-token': 'supabase-cookie' }),
            { params: Promise.resolve({ path: ['api', 'v1', 'thing'] }) },
        );

        expect(response.status).toBe(200);
        expect(prepareHeaders).toHaveBeenCalled();
        expect(fetchMock).toHaveBeenCalledWith(
            'https://upstream.example/api/v1/thing',
            expect.objectContaining({ method: 'GET' }),
        );
        fetchMock.mockRestore();
    });
});
