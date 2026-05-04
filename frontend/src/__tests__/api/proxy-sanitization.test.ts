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

import { afterEach, describe, it, expect } from 'vitest';
import { createHmac } from 'node:crypto';
import { requireProxyAuth, sanitizePath, validateProxySession, validateUuid, safeSegment } from '@/lib/api-proxy';
import { applyCookieCredentials, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { _resetForTesting as resetJwtKeysForTesting } from '@/lib/jwt-keys';
import type { NextRequest } from 'next/server';

const ORIGINAL_REGENGINE_API_KEY = process.env.REGENGINE_API_KEY;
const ORIGINAL_JWT_SIGNING_KEY = process.env.JWT_SIGNING_KEY;
const ORIGINAL_AUTH_SECRET_KEY = process.env.AUTH_SECRET_KEY;

afterEach(() => {
    if (ORIGINAL_REGENGINE_API_KEY === undefined) {
        delete process.env.REGENGINE_API_KEY;
    } else {
        process.env.REGENGINE_API_KEY = ORIGINAL_REGENGINE_API_KEY;
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
    resetJwtKeysForTesting();
});

function makeProxyRequest(headers: Record<string, string>, cookies: Record<string, string> = {}): NextRequest {
    return {
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

    it('does not convert a session credential into the server API key', () => {
        process.env.REGENGINE_API_KEY = 'server-side-key'; // pragma: allowlist secret
        const outgoing = new Headers();
        const request = makeProxyRequest({}, { re_access_token: 'real-token' });

        applyCookieCredentials(outgoing, request);

        expect(outgoing.get('authorization')).toBe('Bearer real-token');
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
});
