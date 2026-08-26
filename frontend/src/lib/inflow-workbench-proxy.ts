import { NextRequest, NextResponse } from 'next/server';

import {
    isUsableCallerCredential,
    proxyError,
    resolveOpaqueSessionTenantId,
    validateUuid,
} from './api-proxy';
import { finalizeCallerServiceCredentials } from './proxy-factory';

const READINESS_SUMMARY_PATH = 'api/v1/inflow-workbench/readiness/summary';
const AUTH_SESSION_COOKIE = '__Host-regengine_session';

/**
 * Apply the least-privilege service credential used by the browser-only
 * Inflow Workbench readiness summary.
 *
 * Direct API-key callers keep their own key and remain backend-authorized.
 * Passwordless browser callers receive the server-held inflow.read key only
 * after /auth/me validates the opaque session and binds it to the requested
 * tenant. Other ingestion routes forward caller-owned credentials only.
 */
export async function applyInflowWorkbenchReadCredentials(
    headers: Headers,
    request: NextRequest,
    path: string,
): Promise<NextResponse | null> {
    if (path !== READINESS_SUMMARY_PATH) {
        return finalizeCallerServiceCredentials(headers, request);
    }

    // Cookie-backed and direct API-key integrations remain authoritative at
    // the ingestion service. The scoped bridge is only for passwordless
    // browser sessions that have no API key of their own.
    if (isUsableCallerCredential(headers.get('x-regengine-api-key'))) {
        return null;
    }

    const sessionToken = request.cookies.get(AUTH_SESSION_COOKIE)?.value;
    if (!isUsableCallerCredential(sessionToken)) {
        return proxyError('Passwordless session required for readiness proxy', 401, {
            code: 'SESSION_CREDENTIAL_REQUIRED',
        });
    }

    const requestUrl = new URL(request.url);
    const queryTenantRaw = requestUrl.searchParams.get('tenant_id');
    const headerTenantRaw = headers.get('x-tenant-id');
    const queryTenant = queryTenantRaw ? validateUuid(queryTenantRaw) : null;
    const headerTenant = headerTenantRaw ? validateUuid(headerTenantRaw) : null;

    if ((queryTenantRaw && !queryTenant) || (headerTenantRaw && !headerTenant)) {
        return proxyError('Invalid tenant context', 400, { code: 'INVALID_TENANT_CONTEXT' });
    }
    if (queryTenant && headerTenant && queryTenant !== headerTenant) {
        return proxyError('Tenant context does not match authenticated session', 403, {
            code: 'TENANT_CONTEXT_MISMATCH',
        });
    }

    const requestedTenant = queryTenant || headerTenant;
    if (!requestedTenant) {
        return proxyError('Tenant context required for readiness proxy', 401, {
            code: 'TENANT_CONTEXT_REQUIRED',
        });
    }

    const authenticatedTenant = await resolveOpaqueSessionTenantId(sessionToken);
    if (!authenticatedTenant) {
        return proxyError('Passwordless session is invalid or expired', 401, {
            code: 'SESSION_INVALID',
        });
    }
    if (authenticatedTenant !== requestedTenant) {
        return proxyError('Tenant context does not match authenticated session', 403, {
            code: 'TENANT_CONTEXT_MISMATCH',
        });
    }

    const scopedApiKey = process.env.INFLOW_WORKBENCH_READ_API_KEY;
    if (!isUsableCallerCredential(scopedApiKey)) {
        return proxyError('Inflow Workbench readiness proxy is not configured', 503, {
            code: 'SERVICE_CREDENTIAL_UNAVAILABLE',
        });
    }

    headers.set('x-regengine-api-key', scopedApiKey);
    headers.set('x-tenant-id', authenticatedTenant);
    return null;
}
