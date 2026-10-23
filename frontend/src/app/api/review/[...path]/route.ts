import { NextRequest } from 'next/server';
import {
    appendOpaqueSessionCookies,
    createJsonProxy,
    passthroughRequestHeaders,
} from '@/lib/proxy-factory';
import { getServerServiceURL } from '@/lib/api-config';
import { attestPrivilegedProxyClientIp } from '@/lib/proxy-ip-attestation';

// Proxy review API requests to the Admin backend service.
// Handles the approve/reject actions on flagged extractions — paths like
//   /api/review/{id}/approve
//   /api/review/{id}/reject
// are transformed into
//   ${ADMIN_URL}/v1/admin/review/flagged-extractions/{id}/approve

const ADMIN_URL = (() => {
    const url = process.env.ADMIN_SERVICE_URL || getServerServiceURL('admin');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/review] ADMIN_SERVICE_URL points to internal Railway URL; unreachable from Vercel.');
        return getServerServiceURL('admin');
    }
    return url;
})();

export const dynamic = 'force-dynamic';

const ID_ACTION_RE = /^[0-9a-f-]+\/(approve|reject)$/;

function resolveBackendPath(path: string): string {
    return ID_ACTION_RE.test(path) ? `flagged-extractions/${path}` : path;
}

const { GET, POST, PUT, PATCH, DELETE } = createJsonProxy({
    serviceName: 'review',
    buildTargetUrl: (path, queryString) =>
        `${ADMIN_URL}/v1/admin/review/${resolveBackendPath(path)}${queryString}`,
    prepareHeaders: (headers, request) => attestPrivilegedProxyClientIp(headers, request),
    buildHeaders: (request: NextRequest) => {
        const headers = new Headers({ 'Content-Type': 'application/json' });
        passthroughRequestHeaders(headers, request, [
            'accept',
            'origin',
            'referer',
            'user-agent',
            'x-csrf-token',
            'x-request-id',
            'x-tenant-id',
        ]);
        return appendOpaqueSessionCookies(headers, request);
    },
});

export { GET, POST, PUT, PATCH, DELETE };
