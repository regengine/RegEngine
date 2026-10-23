import { NextRequest } from 'next/server';
import {
    createStreamProxy,
    applyCookieCredentials,
    passthroughRequestHeaders,
    isPublicHost,
    stripTrailingSlash,
} from '@/lib/proxy-factory';
import { applyInflowWorkbenchReadCredentials } from '@/lib/inflow-workbench-proxy';
import { acceptsWorkspaceSession } from '@/lib/ingestion-session-routes';

const DEFAULT_INGESTION_URL = 'http://localhost:8002';

// force-dynamic makes the proxy run as a serverless function on every request,
// forwarding auth headers and query params to the ingestion backend.
export const dynamic = 'force-dynamic';
export const revalidate = 0;

function getIngestionTargets(): string[] {
    const candidates: string[] = [];
    const publicIngestionUrl = process.env.NEXT_PUBLIC_INGESTION_URL;
    const internalIngestionUrl = process.env.INGESTION_SERVICE_URL;

    if (publicIngestionUrl) {
        candidates.push(publicIngestionUrl);
    }

    // NOTE: NEXT_PUBLIC_API_BASE_URL is intentionally NOT used here.
    // It points at the admin service, which doesn't serve ingestion routes.

    const runningOnVercel = Boolean(
        process.env.VERCEL || process.env.VERCEL_URL || process.env.VERCEL_ENV,
    );
    if (internalIngestionUrl && (!runningOnVercel || isPublicHost(internalIngestionUrl))) {
        candidates.push(internalIngestionUrl);
    }

    if (candidates.length === 0) {
        const productionUrl = process.env.INGESTION_PRODUCTION_URL;
        if (productionUrl) {
            candidates.push(productionUrl);
        } else if (runningOnVercel) {
            console.error(
                '[proxy/ingestion] No ingestion backend URL configured — set NEXT_PUBLIC_INGESTION_URL, INGESTION_SERVICE_URL, or INGESTION_PRODUCTION_URL',
            );
        } else {
            candidates.push(DEFAULT_INGESTION_URL);
        }
    }

    return Array.from(new Set(candidates.map(stripTrailingSlash)));
}

const { GET, POST, PUT, PATCH, DELETE, OPTIONS } = createStreamProxy({
    serviceName: 'ingestion',
    resolveTargetBases: getIngestionTargets,
    isUnauthenticatedPath: (path: string) => {
        if (path.startsWith('api/v1/sandbox/')) return true;
        if (path.startsWith('api/v1/proof/')) return true;
        const portalMatch = path.match(/^api\/v1\/portal\/([^/]+)(?:\/(submit|preflight))?$/);
        return Boolean(portalMatch && portalMatch[1] !== 'links');
    },
    prepareHeaders: (headers: Headers, request: NextRequest, path: string) => {
        // Session-capable routes use the verified session. Key-only routes
        // retain caller credentials even when the browser also has a session.
        if (request.cookies.get('__Host-regengine_session')?.value && acceptsWorkspaceSession(path)) {
            headers.delete('authorization');
            headers.delete('x-api-key');
            headers.delete('x-regengine-api-key');
        }
        return applyInflowWorkbenchReadCredentials(headers, request, path);
    },
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
            'x-regengine-api-key',
            'x-tenant-id',
            // #3229: signed partners send X-Webhook-Signature; the proxy
            // must not strip it or every browser-relayed signed post
            // arrives unsigned at the HMAC gate.
            'x-webhook-signature',
        ]);

        // Inject access token + tenant API key + tenant ID from cookies.
        // Unlike admin, ingestion overwrites an incoming Authorization header
        // with the cookie token — preserving pre-refactor behavior.
        applyCookieCredentials(headers, request);

        return headers;
    },
});

export { GET, POST, PUT, PATCH, DELETE, OPTIONS };
