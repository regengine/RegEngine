import { NextRequest } from 'next/server';
import { createStreamProxy, applyCookieCredentials, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { getAdminTargets as resolveAdminTargets, shouldRetryAdminProxyResponse } from '@/lib/admin-targets';

// force-dynamic ensures the proxy runs as a serverless function on every request.
export const dynamic = 'force-dynamic';
export const revalidate = 0;
// Allow bulk uploads and long-running admin operations (Pro plan: up to 300s).
// 10K-row commits with SHA-256 hashing + Merkle tree can take 2-3 minutes.
export const maxDuration = 300;

// Auth endpoints are unauthenticated by design when they start or complete a
// passwordless ceremony. Protected WebAuthn registration and admin routes use
// the backend's opaque session cookie.
const UNAUTHENTICATED_AUTH_PATHS = new Set([
    'auth/challenges',
    'auth/webauthn/login/generate-options',
    'auth/webauthn/login/verify',
    'auth/refresh',
    'auth/register',
    'auth/accept-invite',
    'v1/auth/accept-invite',
]);

const AUTH_CHALLENGE_VERIFY_PATH = /^auth\/challenges\/[0-9a-fA-F-]{36}\/verify$/;
const AUTH_COOKIES_TO_FORWARD = [
    '__Host-regengine_session',
    'regengine_auth_browser_nonce',
] as const;

function getAdminTargets(): string[] {
    const candidates = resolveAdminTargets(process.env);
    const runningOnVercel = Boolean(
        process.env.VERCEL || process.env.VERCEL_URL || process.env.VERCEL_ENV,
    );

    if (candidates.length === 0 && runningOnVercel) {
        console.error(
            '[proxy/admin] No admin backend URL configured — set NEXT_PUBLIC_ADMIN_URL, NEXT_PUBLIC_API_BASE_URL, or ADMIN_SERVICE_URL',
        );
    }

    return candidates;
}

function isUnauthenticatedAuthPath(path: string): boolean {
    return UNAUTHENTICATED_AUTH_PATHS.has(path) || AUTH_CHALLENGE_VERIFY_PATH.test(path);
}

function appendSelectedCookies(headers: Headers, request: NextRequest): void {
    const cookies = AUTH_COOKIES_TO_FORWARD
        .map((name) => {
            const value = request.cookies.get(name)?.value;
            return value ? `${name}=${value}` : null;
        })
        .filter((cookie): cookie is string => cookie !== null);

    if (cookies.length > 0) {
        headers.set('cookie', cookies.join('; '));
    }
}

const { GET, POST, PUT, PATCH, DELETE, OPTIONS } = createStreamProxy({
    serviceName: 'admin',
    resolveTargetBases: getAdminTargets,
    shouldRetry: shouldRetryAdminProxyResponse,
    isUnauthenticatedPath: isUnauthenticatedAuthPath,
    buildHeaders: (request: NextRequest) => {
        const headers = new Headers();
        const hasRequestBody = !['GET', 'OPTIONS'].includes(request.method);
        const contentType = request.headers.get('content-type');
        if (contentType) {
            headers.set('Content-Type', contentType);
        } else if (hasRequestBody) {
            headers.set('Content-Type', 'application/json');
        }

        passthroughRequestHeaders(headers, request, [
            'authorization',
            'x-api-key',
            'x-admin-key',
            'x-regengine-api-key',
            'x-tenant-id',
        ]);

        // Inject access token from HTTP-only cookie as Bearer token.
        applyCookieCredentials(headers, request, { respectExistingAuthHeader: true });
        appendSelectedCookies(headers, request);

        return headers;
    },
});

export { GET, POST, PUT, PATCH, DELETE, OPTIONS };
