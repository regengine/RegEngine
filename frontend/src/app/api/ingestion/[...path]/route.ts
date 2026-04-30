import { NextRequest } from 'next/server';
import { createStreamProxy, applyCookieCredentials, passthroughRequestHeaders, isPublicHost, stripTrailingSlash } from '@/lib/proxy-factory';

const DEFAULT_INGESTION_URL = 'http://localhost:8002';

// force-dynamic ensures the proxy runs as a serverless function on every request,
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
    isUnauthenticatedPath: (path: string) => path.startsWith('api/v1/sandbox/'),
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

        // Inject access token + API key + admin key + tenant ID from cookies.
        // Unlike admin, ingestion overwrites an incoming Authorization header
        // with the cookie token — preserving pre-refactor behavior.
        applyCookieCredentials(headers, request);

        return headers;
    },
});

export { GET, POST, PUT, PATCH, DELETE, OPTIONS };
