import { NextRequest } from 'next/server';
import { applyCookieCredentials, createJsonProxy, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { getServerServiceURL } from '@/lib/api-config';

// Proxy compliance API requests to the Compliance backend service
// (via a frontend function so browser clients don't need to deal with CORS).

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    // Guard: *.railway.internal URLs are unreachable from Vercel serverless
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/compliance] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel. Set a public Railway URL.');
        return getServerServiceURL('compliance'); // Will fail with a clear connection error
    }
    return url;
}

const COMPLIANCE_URL = getComplianceUrl();

export const dynamic = 'force-dynamic';

const { GET, POST, PUT, PATCH, DELETE } = createJsonProxy({
    serviceName: 'compliance',
    buildTargetUrl: (path, queryString) => `${COMPLIANCE_URL}/${path}${queryString}`,
    buildHeaders: (request: NextRequest) => {
        const headers = new Headers({ 'Content-Type': 'application/json' });
        passthroughRequestHeaders(headers, request, [
            'authorization',
            'x-regengine-api-key',
            'x-api-key',
            'x-admin-key',
            'x-tenant-id',
        ]);
        return applyCookieCredentials(headers, request);
    },
});

export { GET, POST, PUT, PATCH, DELETE };
