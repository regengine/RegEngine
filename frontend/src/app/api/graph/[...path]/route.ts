import { NextRequest, NextResponse } from 'next/server';
import {
    appendOpaqueSessionCookies,
    applyCookieCredentials,
    createJsonProxy,
    passthroughRequestHeaders,
    type ProxyHandler,
} from '@/lib/proxy-factory';
import { getServerServiceURL } from '@/lib/api-config';

// Proxy graph API requests to the Graph backend service
// (via a frontend function so browser clients don't need to deal with CORS).

function getGraphUrl(): string {
    const url = process.env.GRAPH_SERVICE_URL || getServerServiceURL('graph');
    // Guard: *.railway.internal URLs are unreachable from Vercel serverless
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/graph] GRAPH_SERVICE_URL points to internal Railway URL; unreachable from Vercel. Set a public Railway URL.');
        return getServerServiceURL('graph');
    }
    return url;
}

const GRAPH_URL = getGraphUrl();

export const dynamic = 'force-dynamic';

const graphProxy = createJsonProxy({
    serviceName: 'graph',
    buildTargetUrl: (path, queryString) => `${GRAPH_URL}/${path}${queryString}`,
    buildHeaders: (request: NextRequest) => {
        const headers = new Headers({ 'Content-Type': 'application/json' });
        passthroughRequestHeaders(headers, request, [
            'authorization',
            'x-regengine-api-key',
            'x-api-key',
        ]);
        applyCookieCredentials(headers, request, { respectExistingAuthHeader: true });
        appendOpaqueSessionCookies(headers, request);
        return headers;
    },
});

function releaseDisabled(handler: ProxyHandler | undefined): ProxyHandler {
    return async (request, context) => {
        // Graph/Neo4j is deliberately outside the release router inventory.
        // Production stays 404 until a tenant/auth matrix and manifest adapter
        // are added in a future code change. Developers must opt in explicitly.
        if (process.env.NODE_ENV === 'production' || process.env.REGENGINE_ENABLE_GRAPH_PROXY !== '1') {
            return new NextResponse(null, { status: 404 });
        }
        if (!handler) return new NextResponse(null, { status: 404 });
        return handler(request, context);
    };
}

export const GET = releaseDisabled(graphProxy.GET);
export const POST = releaseDisabled(graphProxy.POST);
export const PUT = releaseDisabled(graphProxy.PUT);
export const PATCH = releaseDisabled(graphProxy.PATCH);
export const DELETE = releaseDisabled(graphProxy.DELETE);
