import { NextRequest } from 'next/server';
import { applyCookieCredentials, createJsonProxy, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { getServerServiceURL } from '@/lib/api-config';

// Proxy controls API requests to the Admin backend service.
// Paths like /api/controls/foo are forwarded to ${ADMIN_URL}/v1/overlay/foo.
//
// #2835 This used to build ${ADMIN_URL}/v1/admin/${path}, but the controls CRUD
// lives on the compliance-overlay router, not the admin router:
//   services/admin/app/api_overlay.py:55
//     router = APIRouter(prefix="/v1/overlay", tags=["overlay"])
//   services/admin/app/api_overlay.py:123  @router.post("/controls")
//   services/admin/app/api_overlay.py:168  @router.get("/controls")
//   services/admin/app/api_overlay.py:207  @router.get("/controls/{control_id}")
//   services/admin/app/api_overlay.py:241  @router.put("/controls/{control_id}")
//   services/admin/app/api_overlay.py:293  @router.delete("/controls/{control_id}")
// and it is mounted prefix-free in server/main.py:794
//   app.include_router(overlay_router, tags=["Compliance Overlay"])
// so the effective paths are /v1/overlay/controls[/{id}]. Every request under
// the old /v1/admin/ prefix 404'd.

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

const { GET, POST, PUT, PATCH, DELETE } = createJsonProxy({
    serviceName: 'controls',
    buildTargetUrl: (path, queryString) => `${ADMIN_URL}/v1/overlay/${path}${queryString}`,
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
