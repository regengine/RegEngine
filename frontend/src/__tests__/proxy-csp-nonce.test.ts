/**
 * #2821 — CSP nonce must reach Next.js on the REQUEST headers.
 * #2886 — GATED_DEV_ROUTES must name real page paths.
 *
 * #2821 background: proxy.ts set the nonce as an `x-nonce` REQUEST header and
 * the CSP on the RESPONSE only. Next.js derives the nonce for its own
 * bootstrap/chunk <script> tags exclusively from the INCOMING REQUEST's
 * `content-security-policy` header:
 *
 *   node_modules/next/dist/server/app-render/app-render.js:209-210
 *     const csp = headers['content-security-policy'] || headers['...-report-only'];
 *     const nonce = typeof csp === 'string' ? getScriptNonceFromHeader(csp) : undefined;
 *
 * There is no `x-nonce` convention inside the framework — `x-nonce` is purely
 * this app's own channel to layout.tsx / providers.tsx. Because buildCsp()
 * emits 'strict-dynamic', CSP3 browsers ignore 'self' for scripts, so with no
 * nonce on the framework's own tags every /_next/static/chunks/*.js was
 * refused and NO page hydrated in production.
 *
 * NextResponse.next({ request: { headers } }) encodes the overridden request
 * headers onto the response as `x-middleware-override-headers` (the list) plus
 * one `x-middleware-request-<name>` per header; Next.js reads those back to
 * rebuild the request. Asserting on them is how we prove the header actually
 * reaches the framework rather than just being set on a local Headers object.
 */

import { describe, it, expect } from 'vitest';
import { NextRequest } from 'next/server';
import { proxy } from '@/proxy';

const NONCE_IN_SCRIPT_SRC = /script-src[^;]*'nonce-([A-Za-z0-9+/=]+)'/;

function overriddenRequestHeaders(res: Response): string[] {
    return (res.headers.get('x-middleware-override-headers') ?? '')
        .split(',')
        .map((name) => name.trim())
        .filter(Boolean);
}

describe('#2821 CSP nonce reaches Next.js via request headers', () => {
    it('sets Content-Security-Policy on the forwarded REQUEST headers', async () => {
        const res = await proxy(new NextRequest(new URL('http://localhost/docs')));

        expect(overriddenRequestHeaders(res)).toContain('content-security-policy');

        const requestCsp = res.headers.get('x-middleware-request-content-security-policy');
        expect(requestCsp).toBeTruthy();
        // Must be parseable by Next.js's getScriptNonceFromHeader, which looks
        // for a nonce source inside script-src (falling back to default-src).
        expect(requestCsp).toMatch(NONCE_IN_SCRIPT_SRC);
    });

    it('uses the SAME nonce on the request CSP, the response CSP, and x-nonce', async () => {
        const res = await proxy(new NextRequest(new URL('http://localhost/docs')));

        const requestCsp = res.headers.get('x-middleware-request-content-security-policy') ?? '';
        const responseCsp = res.headers.get('content-security-policy') ?? '';
        const xNonce = res.headers.get('x-middleware-request-x-nonce');

        const requestNonce = requestCsp.match(NONCE_IN_SCRIPT_SRC)?.[1];
        const responseNonce = responseCsp.match(NONCE_IN_SCRIPT_SRC)?.[1];

        expect(requestNonce).toBeTruthy();
        // A mismatch between any of these three means the browser rejects the
        // scripts the server nonced.
        expect(responseNonce).toBe(requestNonce);
        expect(xNonce).toBe(requestNonce);
    });

    it('keeps the x-nonce request header the app components read', async () => {
        // layout.tsx:51 and lib/providers.tsx read headers().get('x-nonce');
        // #2821's fix must not replace that channel, only add the CSP one.
        const res = await proxy(new NextRequest(new URL('http://localhost/docs')));
        expect(overriddenRequestHeaders(res)).toContain('x-nonce');
        expect(res.headers.get('x-middleware-request-x-nonce')).toBeTruthy();
    });

    it('still sets the enforced CSP on the response', async () => {
        const res = await proxy(new NextRequest(new URL('http://localhost/docs')));
        const responseCsp = res.headers.get('content-security-policy');
        expect(responseCsp).toContain("'strict-dynamic'");
        expect(responseCsp).toContain("frame-ancestors 'none'");
    });
});

describe('#2886 gated developer routes', () => {
    // isGatedRoute() matches `pathname === route || pathname.startsWith(route + '/')`,
    // so an entry with no corresponding page under src/app gates nothing. The
    // portal lives at src/app/developer/portal; GATED_DEV_ROUTES names that root,
    // so the landing page and every sub-path (e.g. /keys) are gated.
    // Unauthenticated + gated => redirect to /login with the path as `next`.
    async function statusFor(pathname: string): Promise<number> {
        const res = await proxy(new NextRequest(new URL(`http://localhost${pathname}`)));
        return res.status;
    }

    it('gates the portal landing page', async () => {
        expect(await statusFor('/developer/portal')).toBe(307);
    });

    it('gates the keys page', async () => {
        expect(await statusFor('/developer/portal/keys')).toBe(307);
    });

    it('gates sub-paths of the portal', async () => {
        expect(await statusFor('/developer/portal/keys/new')).toBe(307);
    });

    it.each([
        ['/developer/portal', '%2Fdeveloper%2Fportal'],
        ['/developer/portal/keys', '%2Fdeveloper%2Fportal%2Fkeys'],
    ])('redirects %s to /login with an encoded next', async (pathname, encodedNext) => {
        const res = await proxy(new NextRequest(new URL(`http://localhost${pathname}`)));
        const raw = res.headers.get('location') ?? '';
        const location = new URL(raw, 'http://localhost');
        expect(location.pathname).toBe('/login');
        expect(location.searchParams.get('next')).toBe(pathname);
        expect(raw).toContain(`next=${encodedNext}`);
    });

    it('lets a request with a session cookie through to the page (the page and the backend then decide)', async () => {
        const res = await proxy(new NextRequest(new URL('http://localhost/developer/portal'), {
            headers: { cookie: '__Host-regengine_session=opaque-test-value' },
        }));
        expect(res.status).toBe(200);
    });

    it('leaves public docs and the developers page ungated', async () => {
        // Developer evaluation needs docs and the marketing page without an account.
        expect(await statusFor('/docs')).toBe(200);
        expect(await statusFor('/docs/api')).toBe(200);
        expect(await statusFor('/developers')).toBe(200);
    });

    it('does not gate a look-alike path that is not under the portal', async () => {
        // '/developer/portalx' must not match '/developer/portal': the gate
        // matches on a path-segment boundary, not a bare string prefix.
        expect(await statusFor('/developer/portalx')).toBe(200);
    });
});
