import { NextRequest } from 'next/server';
import { createStreamProxy, applyCookieCredentials, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { getAdminTargets as resolveAdminTargets, shouldRetryAdminProxyResponse } from '@/lib/admin-targets';

// force-dynamic ensures the proxy runs as a serverless function on every request.
export const dynamic = 'force-dynamic';
export const revalidate = 0;
// Allow bulk uploads and long-running admin operations (Pro plan: up to 300s).
// 10K-row commits with SHA-256 hashing + Merkle tree can take 2-3 minutes.
export const maxDuration = 300;

// Auth endpoints are unauthenticated by design — login, signup, refresh, and
// the bootstrap register route must be reachable before any credentials exist.
const UNAUTHENTICATED_AUTH_PATHS = new Set([
    'auth/login',
    'auth/signup',
    'auth/refresh',
    'auth/register',
    'auth/accept-invite',
    'v1/auth/accept-invite',
    // Password reset — caller passes a Supabase recovery token, not a RegEngine JWT.
    // Backend validates it via sb.auth.get_user(); no RegEngine session required.
    'auth/reset-password',
]);

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

const { GET, POST, PUT, PATCH, DELETE, OPTIONS } = createStreamProxy({
    serviceName: 'admin',
    resolveTargetBases: getAdminTargets,
    shouldRetry: shouldRetryAdminProxyResponse,
    isUnauthenticatedPath: (path) => UNAUTHENTICATED_AUTH_PATHS.has(path),
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
        // Respect an existing Authorization header so recovery flows
        // (auth/reset-password) pass a Supabase token that must not be
        // overwritten by a stale RegEngine cookie.
        applyCookieCredentials(headers, request, { respectExistingAuthHeader: true });

        return headers;
    },
});

export { GET, POST, PUT, PATCH, DELETE, OPTIONS };
