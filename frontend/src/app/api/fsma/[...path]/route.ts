import { NextRequest, NextResponse } from 'next/server';
import {
    applyCookieCredentials,
    createJsonProxy,
    passthroughRequestHeaders,
    type ProxyHandler,
} from '@/lib/proxy-factory';

// Proxy the release-approved FSMA compliance routes. Graph-routed aliases are
// retained only as an explicit exact-404 boundary until graph/Neo4j receives a
// route-complete tenant/auth review and is promoted into the release manifest.
//
// The disabled aliases previously mapped to graph sub-routers:
//
//   compliance/, traceability/, recall/, science/, metrics/, gaps, export/
//
//   `drift/` is deliberately absent: there is NO drift router anywhere in the
//   backend. `grep -rn "/drift" services/ server/` returns zero results, and no
//   route decorator or APIRouter prefix mentions drift. The former 'drift/'
//   entry pointed at /api/v1/fsma/drift/* which has never existed. Do not add
//   it back without a real backend router to point it at.
//
//   Compliance service — services/compliance/app/routes.py:64 declares
//   `APIRouter(tags=["fsma-compliance"])` with NO prefix, and server/main.py:929
//   mounts it with no prefix either (`app.include_router(fsma_router, ...)`), so
//   its routes are /industries, /checklists, /checklists/{id} and
//   /v1/fsma/audit/spreadsheet. The previous `/fsma-204/` fallback segment is
//   registered by nothing (`grep -rn "fsma-204" services/ server/ --include=*.py`
//   matches only a JSON payload field in services/graph/app/fsma_metrics.py:350),
//   so it is dropped.

function guardUrl(envVar: string, fallback: string): string {
    const url = process.env[envVar] || process.env.NEXT_PUBLIC_API_BASE_URL;
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (url) {
        if (onVercel && url.includes('.railway.internal')) {
            console.warn(`[proxy/fsma] ${envVar} points to internal Railway URL — unreachable from Vercel.`);
            return '';
        }
        return url;
    }
    if (onVercel) {
        console.error(`[proxy/fsma] ${envVar} not configured — localhost is unreachable from Vercel`);
        return '';
    }
    return fallback;
}

const COMPLIANCE_URL = guardUrl('COMPLIANCE_SERVICE_URL', 'http://localhost:8500');
const GRAPH_ALIAS_SEGMENTS = new Set([
    'compliance',
    'traceability',
    'recall',
    'science',
    'metrics',
    'gaps',
    'export',
]);

function isGraphAlias(pathParts: string[]): boolean {
    return GRAPH_ALIAS_SEGMENTS.has(pathParts[0] ?? '');
}

export const dynamic = 'force-dynamic';

const fsmaProxy = createJsonProxy({
    serviceName: 'fsma',
    buildTargetUrl: (path, queryString) => {
        if (!COMPLIANCE_URL) return undefined;
        return `${COMPLIANCE_URL}/${path}${queryString}`;
    },
    buildHeaders: (request: NextRequest) => {
        const headers = new Headers({ 'Content-Type': 'application/json' });
        passthroughRequestHeaders(headers, request, [
            'authorization',
            'x-regengine-api-key',
            'x-api-key',
            'x-tenant-id',
        ]);
        return applyCookieCredentials(headers, request);
    },
});

function releaseDisabledGraphAlias(handler: ProxyHandler | undefined): ProxyHandler {
    return async (request, context) => {
        const { path } = await context.params;
        if (isGraphAlias(path)) {
            return new NextResponse(null, { status: 404 });
        }
        if (!handler) return new NextResponse(null, { status: 404 });
        return handler(request, context);
    };
}

export const GET = releaseDisabledGraphAlias(fsmaProxy.GET);
export const POST = releaseDisabledGraphAlias(fsmaProxy.POST);
export const PUT = releaseDisabledGraphAlias(fsmaProxy.PUT);
export const PATCH = releaseDisabledGraphAlias(fsmaProxy.PATCH);
export const DELETE = releaseDisabledGraphAlias(fsmaProxy.DELETE);
export const OPTIONS = releaseDisabledGraphAlias(undefined);
