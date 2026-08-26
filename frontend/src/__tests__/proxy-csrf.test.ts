import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

import { CSRF_COOKIE, CSRF_HEADER, CSRF_SIG_COOKIE, signCsrfToken } from '@/lib/csrf';
import { proxy } from '@/proxy';

async function makeMutation({
    method = 'POST',
    origin = 'https://app.regengine.test',
    pathname = '/api/session',
    token = 'csrf-token',
    signature,
    credentialed = false,
}: {
    method?: string;
    origin?: string | null;
    pathname?: string;
    token?: string | null;
    signature?: string | null;
    credentialed?: boolean;
} = {}): Promise<NextRequest> {
    const headers = new Headers();
    if (origin !== null) headers.set('origin', origin);
    if (token !== null) headers.set(CSRF_HEADER, token);
    if (credentialed) {
        headers.set('authorization', 'Bearer attacker-controlled-token');
        headers.set('x-api-key', 'attacker-api-key');
        headers.set('x-admin-key', 'retired-admin-key');
    }
    const cookieParts: string[] = [];
    if (credentialed) cookieParts.push('__Host-regengine_session=attacker-session');
    if (token !== null) cookieParts.push(`${CSRF_COOKIE}=${token}`);
    if (signature !== null) cookieParts.push(`${CSRF_SIG_COOKIE}=${signature}`);
    if (cookieParts.length > 0) {
        headers.set('cookie', cookieParts.join('; '));
    }
    const body = ['GET', 'HEAD', 'OPTIONS'].includes(method) ? undefined : '{}';
    return new NextRequest(`https://app.regengine.test${pathname}`, {
        method,
        headers,
        ...(body === undefined ? {} : { body }),
    });
}

afterEach(() => {
    vi.unstubAllEnvs();
});

describe('proxy CSRF gate', () => {
    const disabledMethods = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'];
    const disabledPaths = [
        '/api/controls/controls/abc123',
        '/api/fsma/compliance/score',
        '/api/fsma/traceability/trace/forward/LOT-1',
        '/api/fsma/recall/readiness',
        '/api/fsma/science/mass-balance/LOT-1',
        '/api/fsma/metrics/dashboard',
        '/api/fsma/gaps/orphans',
        '/api/fsma/export/trace/LOT-1',
        '/api/ingestion/api/v1/remediation/manifests',
        '/api/graph/release-gate-probe',
    ];
    const disabledCases = disabledMethods.flatMap((method) =>
        disabledPaths.flatMap((pathname) => [
            [method, pathname, 'anonymous', false] as const,
            [method, pathname, 'credential-bearing', true] as const,
        ]),
    );

    it.each(disabledCases)(
        'returns exact 404 for release-disabled %s %s with %s credentials before CSRF/auth',
        async (method, pathname, _label, credentialed) => {
            vi.stubEnv('NODE_ENV', 'production');

            const response = await proxy(
                await makeMutation({
                    method,
                    origin: null,
                    pathname,
                    token: null,
                    signature: null,
                    credentialed,
                }),
            );

            expect(response.status).toBe(404);
            await expect(response.text()).resolves.toBe('');
        },
    );

    it('does not classify approved FSMA compliance aliases as release-disabled', async () => {
        const response = await proxy(
            await makeMutation({
                origin: null,
                pathname: '/api/fsma/checklists',
                token: null,
                signature: null,
            }),
        );

        expect(response.status).toBe(403);
        await expect(response.json()).resolves.toEqual({ error: 'Cross-origin mutation rejected' });
    });

    it('keeps CSRF active when graph is explicitly enabled for local development', async () => {
        vi.stubEnv('NODE_ENV', 'development');
        vi.stubEnv('REGENGINE_ENABLE_GRAPH_PROXY', '1');

        const response = await proxy(
            await makeMutation({
                origin: null,
                pathname: '/api/graph/release-gate-probe',
                token: null,
                signature: null,
            }),
        );

        expect(response.status).toBe(403);
        await expect(response.json()).resolves.toEqual({ error: 'Cross-origin mutation rejected' });
    });

    it('rejects a cross-origin cookie mutation even with a valid token', async () => {
        vi.stubEnv('CSRF_SECRET', 'csrf-test-secret');
        const token = 'valid-token';
        const signature = await signCsrfToken(token);

        const response = await proxy(
            await makeMutation({ origin: 'https://attacker.example', token, signature }),
        );

        expect(response.status).toBe(403);
        await expect(response.json()).resolves.toEqual({ error: 'Cross-origin mutation rejected' });
    });

    it('rejects missing and invalid tokens from the same origin', async () => {
        vi.stubEnv('CSRF_SECRET', 'csrf-test-secret');

        const missing = await proxy(
            await makeMutation({ origin: 'https://app.regengine.test', token: null, signature: null }),
        );
        expect(missing.status).toBe(403);
        await expect(missing.json()).resolves.toEqual({ error: 'Missing CSRF token' });

        const invalid = await proxy(
            await makeMutation({ origin: 'https://app.regengine.test', signature: 'invalid' }),
        );
        expect(invalid.status).toBe(403);
        await expect(invalid.json()).resolves.toEqual({ error: 'Invalid CSRF token' });
    });

    it('allows a valid same-origin mutation through the CSRF gate', async () => {
        vi.stubEnv('CSRF_SECRET', 'csrf-test-secret');
        const token = 'valid-token';
        const signature = await signCsrfToken(token);

        const response = await proxy(
            await makeMutation({ origin: 'https://app.regengine.test', token, signature }),
        );

        const body = await response.clone().text();
        expect(body).not.toContain('CSRF');
        expect(body).not.toContain('Cross-origin mutation rejected');
    });
});
