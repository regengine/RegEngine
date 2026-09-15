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
 * Finalize caller-owned credentials for every ingestion route other than the
 * readiness summary.
 *
 * The ingestion service cannot validate the opaque `__Host-regengine_session`
 * cookie, so when that cookie is the caller's only credential the proxy must
 * prove it against backend `/auth/me` before contacting the upstream. The
 * client-writable `re_tenant_id` cookie and caller-supplied `x-tenant-id` /
 * `tenant_id` are never the tenant authority for an opaque session: the
 * forwarded tenant is bound to the `/auth/me` response and any conflicting
 * caller context is rejected. No server-held credential is ever attached.
 */
export async function finalizeIngestionCallerCredentials(
    headers: Headers,
    request: NextRequest,
): Promise<NextResponse | null> {
    const credentialError = finalizeCallerServiceCredentials(headers, request);
    if (credentialError) return credentialError;

    // API-key and bearer callers stay backend-authorized: the upstream binds
    // tenant to the key row / token claims and rejects a conflicting tenant.
    if (
        isUsableCallerCredential(headers.get('x-regengine-api-key')) ||
        isUsableCallerCredential(headers.get('authorization'))
    ) {
        return null;
    }

    const sessionToken = request.cookies.get(AUTH_SESSION_COOKIE)?.value;
    if (!isUsableCallerCredential(sessionToken)) {
        return null;
    }

    const requestUrl = new URL(request.url);
    const queryTenantRaw = requestUrl.searchParams.get('tenant_id');
    const headerTenantRaw = headers.get('x-tenant-id');
    const queryTenant = queryTenantRaw ? validateUuid(queryTenantRaw) : null;
    const headerTenant = headerTenantRaw ? validateUuid(headerTenantRaw) : null;

    if ((queryTenantRaw && !queryTenant) || (headerTenantRaw && !headerTenant)) {
        headers.delete('x-tenant-id');
        return proxyError('Invalid tenant context', 400, { code: 'INVALID_TENANT_CONTEXT' });
    }

    const authenticatedTenant = await resolveOpaqueSessionTenantId(sessionToken);
    if (!authenticatedTenant) {
        headers.delete('x-tenant-id');
        return proxyError('Passwordless session is invalid or expired', 401, {
            code: 'SESSION_INVALID',
        });
    }

    for (const requestedTenant of [queryTenant, headerTenant]) {
        if (requestedTenant && requestedTenant !== authenticatedTenant) {
            headers.delete('x-tenant-id');
            return proxyError('Tenant context does not match authenticated session', 403, {
                code: 'TENANT_CONTEXT_MISMATCH',
            });
        }
    }

    headers.set('x-tenant-id', authenticatedTenant);
    return null;
}

/**
 * Apply the least-privilege service credential used by the browser-only
 * Inflow Workbench readiness summary.
 *
 * Direct API-key callers keep their own key and remain backend-authorized.
 * Passwordless browser callers receive the server-held inflow.read key only
 * after /auth/me validates the opaque session and binds it to the requested
 * tenant. Other ingestion routes forward caller-owned credentials only, with
 * opaque sessions validated by `finalizeIngestionCallerCredentials`.
 */
export async function applyInflowWorkbenchReadCredentials(
    headers: Headers,
    request: NextRequest,
    path: string,
): Promise<NextResponse | null> {
    if (path !== READINESS_SUMMARY_PATH) {
        return finalizeIngestionCallerCredentials(headers, request);
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
