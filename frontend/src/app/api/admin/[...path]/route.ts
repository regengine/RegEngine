import { NextRequest } from 'next/server';
import {
    appendOpaqueSessionCookies,
    applyCookieCredentials,
    createStreamProxy,
    passthroughRequestHeaders,
} from '@/lib/proxy-factory';
import { getAdminTargets as resolveAdminTargets, shouldRetryAdminProxyResponse } from '@/lib/admin-targets';
import { attestPrivilegedProxyClientIp } from '@/lib/proxy-ip-attestation';

// force-dynamic makes the proxy run as a serverless function on every request.
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
function getAdminTargets(): string[] {
    const candidates = resolveAdminTargets(process.env);
    const runningOnVercel = Boolean(
        process.env.VERCEL || process.env.VERCEL_URL || process.env.VERCEL_ENV,
    );

    if (candidates.length === 0 && runningOnVercel) {
        console.error(
            '[proxy/admin] No admin backend URL configured; set NEXT_PUBLIC_ADMIN_URL, NEXT_PUBLIC_API_BASE_URL, or ADMIN_SERVICE_URL',
        );
    }

    return candidates;
}

function isUnauthenticatedAuthPath(path: string): boolean {
    return UNAUTHENTICATED_AUTH_PATHS.has(path) || AUTH_CHALLENGE_VERIFY_PATH.test(path);
}

const { GET, POST, PUT, PATCH, DELETE, OPTIONS } = createStreamProxy({
    serviceName: 'admin',
    resolveTargetBases: getAdminTargets,
    shouldRetry: shouldRetryAdminProxyResponse,
    isUnauthenticatedPath: isUnauthenticatedAuthPath,
    prepareHeaders: (headers, request) => attestPrivilegedProxyClientIp(headers, request),
    prepareHeadersForUnauthenticatedPaths: true,
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
            'accept',
            'authorization',
            'origin',
            'referer',
            'user-agent',
            'x-api-key',
            'x-csrf-token',
            'x-regengine-api-key',
            'x-request-id',
            'x-tenant-id',
        ]);

        // Inject access token from HTTP-only cookie as Bearer token.
        applyCookieCredentials(headers, request, { respectExistingAuthHeader: true });
        appendOpaqueSessionCookies(headers, request, { includeBrowserNonce: true });

        return headers;
    },
});

export { GET, POST, PUT, PATCH, DELETE, OPTIONS };
