import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

import { CSRF_COOKIE, CSRF_HEADER, CSRF_SIG_COOKIE, signCsrfToken } from '@/lib/csrf';
import { proxy } from '@/proxy';

async function makeMutation({
    origin = 'https://app.regengine.test',
    pathname = '/api/session',
    token = 'csrf-token',
    signature,
}: {
    origin?: string | null;
    pathname?: string;
    token?: string | null;
    signature?: string | null;
} = {}): Promise<NextRequest> {
    const headers = new Headers();
    if (origin !== null) headers.set('origin', origin);
    if (token !== null) headers.set(CSRF_HEADER, token);
    if (token !== null || signature !== null) {
        const cookieParts: string[] = [];
        if (token !== null) cookieParts.push(`${CSRF_COOKIE}=${token}`);
        if (signature !== null) cookieParts.push(`${CSRF_SIG_COOKIE}=${signature}`);
        headers.set('cookie', cookieParts.join('; '));
    }
    return new NextRequest(`https://app.regengine.test${pathname}`, {
        method: 'POST',
        headers,
        body: '{}',
    });
}

afterEach(() => {
    vi.unstubAllEnvs();
});

describe('proxy CSRF gate', () => {
    it('returns exact 404 for a release-disabled graph mutation before CSRF', async () => {
        vi.stubEnv('NODE_ENV', 'production');

        const response = await proxy(
            await makeMutation({
                origin: null,
                pathname: '/api/graph/release-gate-probe',
                token: null,
                signature: null,
            }),
        );

        expect(response.status).toBe(404);
        await expect(response.text()).resolves.toBe('');
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
