import { NextRequest } from 'next/server';
import { applyCookieCredentials, createJsonProxy, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { getServerServiceURL } from '@/lib/api-config';

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
        console.warn('[proxy/review] ADMIN_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
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
    transformBody: (body) => ({
        reviewer_id: 'web-frontend',
        notes: 'Action via web interface',
        ...(body as Record<string, unknown>),
    }),
    defaultBody: (path) => ({
        reviewer_id: 'web-frontend',
        notes: `${path.includes('approve') ? 'Approved' : 'Rejected'} via web interface`,
    }),
});

export { GET, POST, PUT, PATCH, DELETE };
