import { NextRequest, NextResponse } from 'next/server';
import {
    createStreamProxy,
    applyCookieCredentials,
    passthroughRequestHeaders,
    isPublicHost,
    stripTrailingSlash,
    type ProxyHandler,
} from '@/lib/proxy-factory';
import { applyInflowWorkbenchReadCredentials } from '@/lib/inflow-workbench-proxy';

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

const ingestionProxy = createStreamProxy({
    serviceName: 'ingestion',
    resolveTargetBases: getIngestionTargets,
    isUnauthenticatedPath: (path: string) => {
        if (path.startsWith('api/v1/sandbox/')) return true;
        if (path.startsWith('api/v1/proof/')) return true;
        const portalMatch = path.match(/^api\/v1\/portal\/([^/]+)(?:\/(submit|preflight))?$/);
        return Boolean(portalMatch && portalMatch[1] !== 'links');
    },
    prepareHeaders: (headers: Headers, request: NextRequest, path: string) => {
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
        ]);

        // Forward the real client IP so the backend's trusted-proxy resolver
        // can apply per-IP rate limits (e.g. the unauthenticated sandbox
        // endpoints) instead of lumping every public caller behind this
        // proxy's egress IP into a single bucket. Vercel sets x-real-ip and
        // the left-most x-forwarded-for hop to the true client IP at the edge;
        // we normalize to a SINGLE X-Forwarded-For value (preferring the
        // Vercel-trustworthy x-real-ip) so a client-supplied header can't
        // forge extra hops. The backend still trusts this only when the peer
        // is a configured trusted proxy — otherwise it uses the socket IP.
        const realClientIp =
            request.headers.get('x-real-ip')?.trim() ||
            request.headers.get('x-forwarded-for')?.split(',')[0]?.trim();
        if (realClientIp) {
            headers.set('x-forwarded-for', realClientIp);
            headers.set('x-real-ip', realClientIp);
        }

        // Inject access token + tenant API key + tenant ID from cookies.
        // Unlike admin, ingestion overwrites an incoming Authorization header
        // with the cookie token — preserving pre-refactor behavior.
        applyCookieCredentials(headers, request);

        return headers;
    },
});

function isRemediationAlias(path: string[]): boolean {
    return path[0] === 'api' && path[1] === 'v1' && path[2] === 'remediation';
}

function releaseDisabledRemediation(handler: ProxyHandler | undefined): ProxyHandler {
    return async (request, context) => {
        const { path } = await context.params;
        // Remediation is release-deferred pending product/compliance sign-off,
        // worker/UI verification, and an operation-complete security adapter.
        // Deny before the stream proxy evaluates credentials or upstreams.
        if (isRemediationAlias(path)) {
            return new NextResponse(null, { status: 404 });
        }
        if (!handler) return new NextResponse(null, { status: 404 });
        return handler(request, context);
    };
}

export const GET = releaseDisabledRemediation(ingestionProxy.GET);
export const POST = releaseDisabledRemediation(ingestionProxy.POST);
export const PUT = releaseDisabledRemediation(ingestionProxy.PUT);
export const PATCH = releaseDisabledRemediation(ingestionProxy.PATCH);
export const DELETE = releaseDisabledRemediation(ingestionProxy.DELETE);
export const OPTIONS = releaseDisabledRemediation(ingestionProxy.OPTIONS);
