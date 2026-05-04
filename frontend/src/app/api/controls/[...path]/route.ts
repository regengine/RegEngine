import { NextRequest } from 'next/server';
import { applyCookieCredentials, createJsonProxy, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { getServerServiceURL } from '@/lib/api-config';

// Proxy controls API requests to the Admin backend service.
// Paths like /api/controls/foo are forwarded to ${ADMIN_URL}/v1/admin/foo.

const ADMIN_URL = (() => {
    const url = process.env.ADMIN_SERVICE_URL || getServerServiceURL('admin');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/controls] ADMIN_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
        return getServerServiceURL('admin');
    }
    return url;
})();

export const dynamic = 'force-dynamic';

const { GET, POST } = createJsonProxy({
    serviceName: 'controls',
    methods: ['GET', 'POST'],
    buildTargetUrl: (path, queryString) => `${ADMIN_URL}/v1/admin/${path}${queryString}`,
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

export { GET, POST };
