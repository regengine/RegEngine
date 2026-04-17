import { NextRequest } from 'next/server';
import { createJsonProxy } from '@/lib/proxy-factory';
import { getServerApiKey } from '@/lib/api-proxy';
import { getServerServiceURL } from '@/lib/api-config';

// Proxy graph API requests to the Graph backend service
// (via a frontend function so browser clients don't need to deal with CORS).

function getGraphUrl(): string {
    const url = process.env.GRAPH_SERVICE_URL || getServerServiceURL('graph');
    // Guard: *.railway.internal URLs are unreachable from Vercel serverless
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/graph] GRAPH_SERVICE_URL points to internal Railway URL — unreachable from Vercel. Set a public Railway URL.');
        return getServerServiceURL('graph');
    }
    return url;
}

const GRAPH_URL = getGraphUrl();

export const dynamic = 'force-dynamic';

const { GET, POST, PUT, PATCH, DELETE } = createJsonProxy({
    serviceName: 'graph',
    buildTargetUrl: (path, queryString) => `${GRAPH_URL}/${path}${queryString}`,
    buildHeaders: (_request: NextRequest) => {
        const headers = new Headers({ 'Content-Type': 'application/json' });
        const apiKey = getServerApiKey();
        if (apiKey) {
            headers.set('X-RegEngine-API-Key', apiKey);
        }
        return headers;
    },
});

export { GET, POST, PUT, PATCH, DELETE };
